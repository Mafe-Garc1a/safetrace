"""Acceso a datos de A · Cuentas: configuración de sismos (RF-11, RF-12).

Colecciones de las que es dueño: configuracion. Es un solo documento con _id fijo.
"""

from pymongo import ReturnDocument
from pymongo.database import Database

from app.crud import auditoria
from core.fechas import ahora

ID_PARAMETROS = "parametros_sismo"
POR_DEFECTO = {"magnitud_minima": 5.0, "radio_afectacion_km": 200}


def obtener_configuracion_sismos(db: Database) -> dict:
    """Magnitud mínima y radio vigentes. Lo usa F."""
    return db["configuracion"].find_one({"_id": ID_PARAMETROS}) or {"_id": ID_PARAMETROS, **POR_DEFECTO}


def actualizar_configuracion_sismos(db: Database, magnitud_minima: float, radio_afectacion_km: float, actor: dict):
    """Cada cambio queda en auditoría con el valor anterior y el nuevo."""
    anterior = obtener_configuracion_sismos(db)
    nuevo = db["configuracion"].find_one_and_update(
        {"_id": ID_PARAMETROS},
        {
            "$set": {
                "magnitud_minima": magnitud_minima,
                "radio_afectacion_km": radio_afectacion_km,
                "actualizado_por": actor["id"],
                "actualizado_en": ahora(),
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    auditoria.registrar(
        db,
        "configuracion",
        ID_PARAMETROS,
        "ACTUALIZAR_CONFIGURACION",
        actor,
        {
            "anterior": {k: anterior.get(k) for k in POR_DEFECTO},
            "nuevo": {"magnitud_minima": magnitud_minima, "radio_afectacion_km": radio_afectacion_km},
        },
    )
    return nuevo
