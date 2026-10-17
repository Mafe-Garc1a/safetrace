"""Acceso a datos y reglas de F · Sismos (RF-31 a RF-37).

Colecciones de las que es dueño: sismos.

Reglas clave:
- Cada sismo se guarda una sola vez aunque llegue repetido (RF-32).
- Un sismo reportado por el SGC y el USGS se guarda una vez, con ambas fuentes.
- Relevante si magnitud ≥ magnitud mínima configurada (RF-34).
"""

import math
from datetime import timedelta

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from app.crud import bitacora as crud_bitacora
from app.crud import configuracion as crud_configuracion
from app.crud import estados as crud_estados
from app.crud import ia_indice as crud_ia_indice
from app.crud import inmuebles as crud_inmuebles
from app.crud import notificaciones as crud_notificaciones
from app.crud.estados import EstadoInmueble as E
from app.schemas.sismos import SismoCreate
from core.errores import TransicionRechazada
from core.fechas import ahora, en_utc
from core.registro import obtener_logger

log = obtener_logger("sismos")

# Criterio para saber que dos reportes son el mismo sismo (propuesta pendiente, sección 11.2)
VENTANA_EMPAREJAR = timedelta(minutes=2)
DISTANCIA_EMPAREJAR_KM = 100
FUENTE_PRINCIPAL = "SGC"  # su magnitud prevalece si las fuentes no coinciden (propuesta)
PROCESO = {"tipo": "PROCESO", "id": "sismos-n8n"}


def distancia_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Distancia sobre la superficie de la Tierra (fórmula del haversine)."""
    radio = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radio * math.asin(math.sqrt(a))


def _buscar_pareja(db: Database, datos: SismoCreate) -> dict | None:
    """Sismo de la otra fuente cercano en tiempo y distancia."""
    fecha = en_utc(datos.fecha_hora)
    candidatos = db["sismos"].find(
        {
            "fecha_hora": {"$gte": fecha - VENTANA_EMPAREJAR, "$lte": fecha + VENTANA_EMPAREJAR},
            "fuentes.fuente": {"$ne": datos.fuente},
        }
    )
    for candidato in candidatos:
        lon, lat = candidato["epicentro"]["coordinates"]
        if distancia_km(lon, lat, datos.longitud, datos.latitud) <= DISTANCIA_EMPAREJAR_KM:
            return candidato
    return None


def recibir_sismo(db: Database, datos: SismoCreate) -> tuple[dict, str]:
    """Guarda el sismo sin duplicados y, si es relevante, marca los inmuebles del radio (RF-31 a RF-35).

    Devuelve (sismo, resultado) con resultado NUEVO, FUENTE_AGREGADA o DUPLICADO.
    """
    repetido = db["sismos"].find_one(
        {"fuentes": {"$elemMatch": {"fuente": datos.fuente, "id_externo": datos.id_externo}}}
    )
    if repetido:
        return repetido, "DUPLICADO"  # operación repetible sin efecto (RF-32)

    configuracion = crud_configuracion.obtener_configuracion_sismos(db)
    fuente = {"fuente": datos.fuente, "id_externo": datos.id_externo, "magnitud": datos.magnitud}

    pareja = _buscar_pareja(db, datos)
    if pareja:
        cambios = {}
        if datos.fuente == FUENTE_PRINCIPAL:
            cambios["magnitud"] = datos.magnitud
        magnitud = cambios.get("magnitud", pareja["magnitud"])
        cambios["es_relevante"] = magnitud >= configuracion["magnitud_minima"]
        sismo = db["sismos"].find_one_and_update(
            {"_id": pareja["_id"]},
            {"$push": {"fuentes": fuente}, "$set": cambios},
            return_document=ReturnDocument.AFTER,
        )
        if sismo["es_relevante"] and not pareja["es_relevante"]:
            sismo = marcar_inmuebles(db, sismo, configuracion["radio_afectacion_km"])
        return sismo, "FUENTE_AGREGADA"

    sismo = {
        "fecha_hora": en_utc(datos.fecha_hora),
        "magnitud": datos.magnitud,
        "profundidad_km": datos.profundidad_km,
        "epicentro": {"type": "Point", "coordinates": [datos.longitud, datos.latitud]},
        "fuentes": [fuente],
        "es_relevante": datos.magnitud >= configuracion["magnitud_minima"],
        "inmuebles_marcados": 0,
        "recibido_en": ahora(),
    }
    sismo["_id"] = db["sismos"].insert_one(sismo).inserted_id
    if sismo["es_relevante"]:
        sismo = marcar_inmuebles(db, sismo, configuracion["radio_afectacion_km"])
    return sismo, "NUEVO"


def marcar_inmuebles(db: Database, sismo: dict, radio_km: float) -> dict:
    """Para cada inmueble del radio: estado 2 (G), evento externo (D), índice (J) y aviso (K). RF-35 a RF-37."""
    lon, lat = sismo["epicentro"]["coordinates"]
    marcados = 0
    for inmueble in crud_inmuebles.buscar_en_radio(db, lon, lat, radio_km):
        i_lon, i_lat = inmueble["ubicacion"]["coordinates"]
        distancia = distancia_km(lon, lat, i_lon, i_lat)
        actual = inmueble["estado"]["codigo"]
        if actual != E.MARCADO_POR_EVENTO_SISMICO:
            try:
                crud_estados.pedir_transicion(
                    db, inmueble["_id"], actual, E.MARCADO_POR_EVENTO_SISMICO, "SISMO_RELEVANTE",
                    {"tipo": "SISMO", "id": sismo["_id"]}, PROCESO,
                )  # fmt: skip
            except TransicionRechazada:
                log.warning("inmueble %s cambió de estado mientras se marcaba", inmueble["_id"])
                continue
        crud_bitacora.registrar_evento_sistema(db, inmueble["_id"], sismo, distancia)
        try:
            crud_ia_indice.calcular_indice(db, inmueble["_id"], sismo, distancia)
        except NotImplementedError:
            pass  # pesos del índice pendientes: el marcado sigue sin el índice (RNF-24)
        crud_notificaciones.notificar(
            db, inmueble["propietario_id"], "INMUEBLE_MARCADO_POR_SISMO", {"tipo": "SISMO", "id": sismo["_id"]}
        )
        marcados += 1
    return db["sismos"].find_one_and_update(
        {"_id": sismo["_id"]}, {"$inc": {"inmuebles_marcados": marcados}}, return_document=ReturnDocument.AFTER
    )


def obtener_sismo(db: Database, sismo_id: ObjectId) -> dict | None:
    """Magnitud, epicentro y fecha. Lo usa J."""
    return db["sismos"].find_one({"_id": sismo_id})


def listar_sismos(db: Database, solo_relevantes: bool, saltar: int, limite: int) -> tuple[list[dict], int]:
    filtros = {"es_relevante": True} if solo_relevantes else {}
    total = db["sismos"].count_documents(filtros)
    datos = list(db["sismos"].find(filtros).sort("fecha_hora", -1).skip(saltar).limit(limite))
    return datos, total
