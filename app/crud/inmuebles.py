"""Acceso a datos y reglas de C · Inmuebles (RF-17 a RF-21).

Colecciones de las que es dueño: inmuebles, zonas.

Reglas clave:
- Coordenadas en GeoJSON: [longitud, latitud].
- Cada campo calculado tiene un único módulo que lo escribe:
  `estado` solo G, `ultimo_indice` solo J, `ultimos_eventos` solo D
  y `revision_semestral` solo E.
"""

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from app.crud import auditoria
from app.schemas.inmuebles import InmuebleCreate, InmuebleUpdate
from core.fechas import ahora, sumar_meses

RADIO_TIERRA_KM = 6378.1
MAXIMO_ULTIMOS_EVENTOS = 5  # patrón Subset (sección 3.3)


def _punto(longitud: float, latitud: float) -> dict:
    return {"type": "Point", "coordinates": [longitud, latitud]}


def crear_inmueble(db: Database, propietario_id: ObjectId, inmueble: InmuebleCreate, estado: dict, actor: dict) -> dict:
    """Registra un inmueble (RF-17 a RF-20). El estado inicial lo entrega G."""
    momento = ahora()
    datos = inmueble.model_dump(exclude={"longitud", "latitud"})
    documento = {
        "propietario_id": propietario_id,
        **datos,
        "ubicacion": _punto(inmueble.longitud, inmueble.latitud),
        "fecha_registro": momento,
        "estado": estado,
        "ultimo_indice": None,
        "revision_semestral": {"ultima": None, "proxima": sumar_meses(momento, 6)},
        "ultimos_eventos": [],
        "schema_version": 2,
        "creado_en": momento,
        "actualizado_en": momento,
    }
    documento["_id"] = db["inmuebles"].insert_one(documento).inserted_id
    auditoria.registrar(db, "inmuebles", documento["_id"], "REGISTRAR_INMUEBLE", actor)
    return documento


def actualizar_inmueble(db: Database, inmueble_id: ObjectId, cambios: InmuebleUpdate, actor: dict) -> dict | None:
    """Corrige datos de registro. Nunca toca los campos calculados."""
    datos = cambios.model_dump(exclude_unset=True, exclude={"longitud", "latitud"})
    if cambios.longitud is not None and cambios.latitud is not None:
        datos["ubicacion"] = _punto(cambios.longitud, cambios.latitud)
    if not datos:
        return obtener_inmueble(db, inmueble_id)
    datos["actualizado_en"] = ahora()
    actualizado = db["inmuebles"].find_one_and_update(
        {"_id": inmueble_id}, {"$set": datos}, return_document=ReturnDocument.AFTER
    )
    auditoria.registrar(
        db,
        "inmuebles",
        inmueble_id,
        "ACTUALIZAR_INMUEBLE",
        actor,
        {"campos": sorted(k for k in datos if k != "actualizado_en")},
    )
    return actualizado


def obtener_inmueble(db: Database, inmueble_id: ObjectId, proyeccion: dict | None = None) -> dict | None:
    """Ficha del inmueble. La usan casi todos."""
    return db["inmuebles"].find_one({"_id": inmueble_id}, proyeccion)


def datos_publicos(db: Database, inmueble_id: ObjectId) -> dict:
    """Datos que no identifican al propietario ni revelan el estado (RNF-18, RNF-19). Los usan H e I."""
    inmueble = obtener_inmueble(
        db,
        inmueble_id,
        {
            "_id": 0,
            "tipo_inmueble": 1,
            "ciudad": 1,
            "anio_construccion": 1,
            "numero_pisos": 1,
            "sistema_constructivo": 1,
        },
    )
    return inmueble or {}


def listar_inmuebles(db: Database, filtros: dict, saltar: int, limite: int) -> tuple[list[dict], int]:
    """«Mis inmuebles» del propietario (RF-21) o todos para el administrador."""
    total = db["inmuebles"].count_documents(filtros)
    datos = list(db["inmuebles"].find(filtros).sort("creado_en", -1).skip(saltar).limit(limite))
    return datos, total


def buscar_en_radio(db: Database, longitud: float, latitud: float, radio_km: float) -> list[dict]:
    """Inmuebles dentro del radio (RF-35), con su ubicación y estado. Lo usa F."""
    return list(
        db["inmuebles"].find(
            {"ubicacion": {"$geoWithin": {"$centerSphere": [[longitud, latitud], radio_km / RADIO_TIERRA_KM]}}},
            {"propietario_id": 1, "ubicacion": 1, "estado": 1},
        )
    )


def con_revision_vencida(db: Database, fecha: object) -> list[dict]:
    """Inmuebles cuya próxima revisión semestral ya llegó (RF-30). Lo usa E."""
    return list(
        db["inmuebles"].find(
            {"revision_semestral.proxima": {"$lte": fecha}},
            {"propietario_id": 1, "revision_semestral": 1},
        )
    )


# --- Campos calculados: cada uno con un único módulo que lo escribe -----------


def escribir_estado(
    db: Database, inmueble_id: ObjectId, esperado: int, version: int, estado: dict, session=None
) -> bool:
    """Campo calculado `estado`. SOLO lo llama G, y solo cambia si nadie lo cambió antes (sección 7.2)."""
    resultado = db["inmuebles"].update_one(
        {"_id": inmueble_id, "estado.codigo": esperado, "estado.version": version},
        {"$set": {"estado": estado, "actualizado_en": ahora()}},
        session=session,
    )
    return resultado.modified_count == 1


def escribir_ultimo_indice(db: Database, inmueble_id: ObjectId, indice: dict) -> None:
    """Campo calculado `ultimo_indice`. SOLO lo llama J."""
    db["inmuebles"].update_one({"_id": inmueble_id}, {"$set": {"ultimo_indice": indice, "actualizado_en": ahora()}})


def agregar_ultimo_evento(db: Database, inmueble_id: ObjectId, resumen: dict) -> None:
    """Subset `ultimos_eventos` (máx. 5, del más reciente al más antiguo). SOLO lo llama D."""
    db["inmuebles"].update_one(
        {"_id": inmueble_id},
        {
            "$push": {
                "ultimos_eventos": {"$each": [resumen], "$sort": {"fecha": -1}, "$slice": MAXIMO_ULTIMOS_EVENTOS}
            },
            "$set": {"actualizado_en": ahora()},
        },
    )


def escribir_revision_semestral(db: Database, inmueble_id: ObjectId, ultima, proxima) -> None:
    """Campo calculado `revision_semestral`. SOLO lo llama E."""
    db["inmuebles"].update_one(
        {"_id": inmueble_id},
        {
            "$set": {
                "revision_semestral": {"ultima": ultima, "proxima": proxima, "recordatorio_enviado_en": None},
                "actualizado_en": ahora(),
            }
        },
    )


def marcar_recordatorio_enviado(db: Database, inmueble_id: ObjectId, fecha) -> None:
    """Evita repetir el recordatorio semestral cada día. SOLO lo llama E."""
    db["inmuebles"].update_one({"_id": inmueble_id}, {"$set": {"revision_semestral.recordatorio_enviado_en": fecha}})


# --- Zonas: catálogo cerrado (RF-23) -------------------------------------------


def listar_zonas(db: Database) -> list[dict]:
    return list(db["zonas"].find({"activo": True}).sort([("grupo", 1), ("nombre", 1)]))


def zona_activa(db: Database, zona_id: str) -> bool:
    return db["zonas"].count_documents({"_id": zona_id, "activo": True}, limit=1) > 0
