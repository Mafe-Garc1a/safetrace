"""Acceso a datos y reglas de D · Bitácora y evidencias (RF-22 a RF-27).

Colecciones de las que es dueño: eventos, evidencias (y el campo `inmuebles.ultimos_eventos`).

Reglas clave:
- Eventos y evidencias no se modifican ni se borran (RNF-16).
- Una evidencia equivocada se marca INVALIDA o REEMPLAZADA (RF-27).
"""

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from app.crud import auditoria
from app.crud import ia_indice as crud_ia_indice
from app.crud import inmuebles as crud_inmuebles
from app.schemas.bitacora import ArchivoEntrada, EventoCreate
from core.fechas import ahora

LARGO_RESUMEN = 80


def _resumir(texto: str) -> str:
    return texto if len(texto) <= LARGO_RESUMEN else texto[: LARGO_RESUMEN - 1] + "…"


def _insertar_evento(db: Database, documento: dict) -> dict:
    documento["_id"] = db["eventos"].insert_one(documento).inserted_id
    crud_inmuebles.agregar_ultimo_evento(
        db,
        documento["inmueble_id"],
        {
            "evento_id": documento["_id"],
            "tipo": documento["tipo"],
            "fecha": documento["fecha_evento"],
            "resumen": _resumir(documento["descripcion"]),
        },
    )
    return documento


def registrar_evento(db: Database, inmueble_id: ObjectId, evento: EventoCreate, usuario: dict) -> dict:
    """Evento registrado por el propietario (RF-22, RF-23)."""
    documento = {
        "inmueble_id": inmueble_id,
        **evento.model_dump(),
        "origen": "USUARIO",
        "sismo_id": None,
        "registrado_por": usuario["_id"],
        "creado_en": ahora(),
    }
    documento = _insertar_evento(db, documento)
    auditoria.registrar(db, "eventos", documento["_id"], "REGISTRAR_EVENTO", auditoria.actor_usuario(usuario))
    return documento


def registrar_evento_sistema(db: Database, inmueble_id: ObjectId, sismo: dict, distancia_km: float) -> dict:
    """EVENTO_EXTERNO de origen SISTEMA cuando un sismo relevante marca el inmueble (RF-36). Lo usa F."""
    magnitud = f"{sismo['magnitud']:.1f}".replace(".", ",")
    documento = {
        "inmueble_id": inmueble_id,
        "tipo": "EVENTO_EXTERNO",
        "fecha_evento": sismo["fecha_hora"],
        "descripcion": f"Sismo M{magnitud} a {distancia_km:.0f} km",
        "zona_id": None,
        "origen": "SISTEMA",
        "sismo_id": sismo["_id"],
        "registrado_por": None,
        "creado_en": ahora(),
    }
    return _insertar_evento(db, documento)


def obtener_evento(db: Database, evento_id: ObjectId) -> dict | None:
    return db["eventos"].find_one({"_id": evento_id})


def linea_cronologica(db: Database, inmueble_id: ObjectId, saltar: int, limite: int) -> tuple[list[dict], int]:
    """Eventos del más reciente al más antiguo, cada uno con sus evidencias (RF-26, RNF-30)."""
    filtros = {"inmueble_id": inmueble_id}
    total = db["eventos"].count_documents(filtros)
    eventos = list(db["eventos"].find(filtros).sort("fecha_evento", -1).skip(saltar).limit(limite))
    ids = [e["_id"] for e in eventos]
    evidencias: dict = {}
    for evidencia in db["evidencias"].find({"origen.tipo": "EVENTO", "origen.id": {"$in": ids}}).sort("creado_en", 1):
        evidencias.setdefault(evidencia["origen"]["id"], []).append(evidencia)
    for evento in eventos:
        evento["evidencias"] = evidencias.get(evento["_id"], [])
    return eventos, total


# --- Evidencias ----------------------------------------------------------------


def registrar_evidencia(
    db: Database, inmueble_id: ObjectId, origen_tipo: str, origen_id: ObjectId, entrada: ArchivoEntrada, usuario: dict
) -> dict:
    """Guarda la referencia de un archivo ya subido. La usan D, E y H."""
    documento = {
        "inmueble_id": inmueble_id,
        "origen": {"tipo": origen_tipo, "id": origen_id},
        "tipo_archivo": entrada.tipo_archivo,
        "categoria_documento": entrada.categoria_documento,
        "zona_id": entrada.zona_id,
        "archivo": entrada.archivo.model_dump(),
        "estado": "VIGENTE",
        "reemplazada_por": None,
        "invalidacion": None,
        "cargado_por": usuario["_id"],
        "creado_en": ahora(),
    }
    documento["_id"] = db["evidencias"].insert_one(documento).inserted_id
    if documento["tipo_archivo"] == "FOTO" and documento["zona_id"]:
        # J compara con la foto anterior de la misma zona, si existe (RF-62)
        crud_ia_indice.solicitar_comparacion(db, documento)
    return documento


def obtener_evidencia(db: Database, evidencia_id: ObjectId) -> dict | None:
    return db["evidencias"].find_one({"_id": evidencia_id})


def evidencias_por_ids(db: Database, ids: list[ObjectId]) -> list[dict]:
    return list(db["evidencias"].find({"_id": {"$in": ids}}))


def fotos_vigentes(db: Database, inmueble_id: ObjectId, limite: int = 50) -> list[dict]:
    """Fotos vigentes del inmueble. La usa I para el enlace público."""
    return list(
        db["evidencias"]
        .find({"inmueble_id": inmueble_id, "tipo_archivo": "FOTO", "estado": "VIGENTE"})
        .sort("creado_en", -1)
        .limit(limite)
    )


def invalidar_evidencia(
    db: Database, evidencia: dict, estado: str, motivo: str, reemplazada_por: ObjectId | None, usuario: dict
) -> dict | None:
    """Marca la evidencia INVALIDA o REEMPLAZADA; nunca se borra (RF-27). Queda en auditoría."""
    actualizada = db["evidencias"].find_one_and_update(
        {"_id": evidencia["_id"], "estado": "VIGENTE"},
        {
            "$set": {
                "estado": estado,
                "reemplazada_por": reemplazada_por,
                "invalidacion": {"usuario_id": usuario["_id"], "fecha": ahora(), "motivo": motivo},
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if actualizada:
        crud_ia_indice.marcar_reemplazados(db, evidencia["_id"])
        auditoria.registrar(
            db,
            "evidencias",
            evidencia["_id"],
            "INVALIDAR_EVIDENCIA",
            auditoria.actor_usuario(usuario),
            {"estado": estado, "reemplazada_por": reemplazada_por},
        )
    return actualizada


def foto_anterior(db: Database, inmueble_id: ObjectId, zona_id: str, foto_nueva: dict) -> dict | None:
    """Foto vigente anterior de la misma zona (RF-62). La usa J."""
    return db["evidencias"].find_one(
        {
            "inmueble_id": inmueble_id,
            "zona_id": zona_id,
            "tipo_archivo": "FOTO",
            "estado": "VIGENTE",
            "_id": {"$ne": foto_nueva["_id"]},
            "creado_en": {"$lte": foto_nueva["creado_en"]},
        },
        sort=[("creado_en", -1)],
    )


def antecedentes(db: Database, inmueble_id: ObjectId) -> dict:
    """Conteo de daños y mantenimientos registrados. Lo usa J para el índice."""
    return {
        "antecedentes_danos": db["eventos"].count_documents({"inmueble_id": inmueble_id, "tipo": "DANO"}),
        "antecedentes_mantenimiento": db["eventos"].count_documents(
            {"inmueble_id": inmueble_id, "tipo": "MANTENIMIENTO"}
        ),
    }
