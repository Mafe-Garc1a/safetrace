"""Acceso a datos y reglas de K · Notificaciones y procesos (RF-69 a RF-71).

Colecciones de las que es dueño: tareas, notificaciones.

Reglas clave:
- Solo avisos que piden acción o informan un hecho relevante (RNF-29).
- `datos` de una tarea guarda solo identificadores, nunca datos personales.
- Si una tarea falla y quedan intentos, vuelve a PENDIENTE más adelante (RNF-24).
"""

from datetime import timedelta

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from core.fechas import ahora

TIPOS_NOTIFICACION = (
    "INMUEBLE_MARCADO_POR_SISMO",
    "CAMBIO_SOLICITUD",
    "CONSTANCIA_DISPONIBLE",
    "RECORDATORIO_SEMESTRAL",
)
SEGUNDOS_ENTRE_INTENTOS = 60


def encolar_tarea(db: Database, tipo: str, datos: dict, max_intentos: int = 3) -> ObjectId:
    """Crea una tarea PENDIENTE en la colección `tareas`. La usan todos."""
    momento = ahora()
    return (
        db["tareas"]
        .insert_one(
            {
                "tipo": tipo,
                "estado": "PENDIENTE",
                "datos": datos,
                "intentos": 0,
                "max_intentos": max_intentos,
                "disponible_desde": momento,
                "tomada_por": None,
                "error": None,
                "creado_en": momento,
                "finalizada_en": None,
            }
        )
        .inserted_id
    )


def obtener_tarea(db: Database, tarea_id: ObjectId) -> dict | None:
    return db["tareas"].find_one({"_id": tarea_id})


def tomar_tarea(db: Database, trabajador: str) -> dict | None:
    """Toma UNA tarea pendiente de forma atómica: dos trabajadores nunca toman la misma."""
    momento = ahora()
    return db["tareas"].find_one_and_update(
        {"estado": "PENDIENTE", "disponible_desde": {"$lte": momento}},
        {"$set": {"estado": "PROCESANDO", "tomada_por": trabajador}, "$inc": {"intentos": 1}},
        sort=[("disponible_desde", 1), ("creado_en", 1)],
        return_document=ReturnDocument.AFTER,
    )


def completar_tarea(db: Database, tarea_id: ObjectId) -> None:
    db["tareas"].update_one(
        {"_id": tarea_id}, {"$set": {"estado": "COMPLETADA", "error": None, "finalizada_en": ahora()}}
    )


def fallar_tarea(db: Database, tarea: dict, error: str) -> bool:
    """Devuelve True si la tarea quedó FALLIDA definitivamente; False si se reintentará."""
    momento = ahora()
    if tarea["intentos"] < tarea["max_intentos"]:
        espera = timedelta(seconds=SEGUNDOS_ENTRE_INTENTOS * tarea["intentos"])
        db["tareas"].update_one(
            {"_id": tarea["_id"]},
            {"$set": {"estado": "PENDIENTE", "error": error[:300], "disponible_desde": momento + espera}},
        )
        return False
    db["tareas"].update_one(
        {"_id": tarea["_id"]}, {"$set": {"estado": "FALLIDA", "error": error[:300], "finalizada_en": momento}}
    )
    return True


def notificar(db: Database, usuario_id: ObjectId, tipo: str, referencia: dict | None) -> ObjectId:
    """Registra la notificación y encola el correo (RF-37, RF-69, RF-70). No guarda el texto del correo."""
    if tipo not in TIPOS_NOTIFICACION:
        raise ValueError(f"Tipo de notificación desconocido: {tipo}")
    notificacion_id = (
        db["notificaciones"]
        .insert_one(
            {
                "usuario_id": usuario_id,
                "tipo": tipo,
                "referencia": referencia,
                "estado": "PENDIENTE",
                "creado_en": ahora(),
                "enviada_en": None,
            }
        )
        .inserted_id
    )
    encolar_tarea(db, "ENVIAR_CORREO", {"notificacion_id": notificacion_id})
    return notificacion_id


def obtener_notificacion(db: Database, notificacion_id: ObjectId) -> dict | None:
    return db["notificaciones"].find_one({"_id": notificacion_id})


def marcar_notificacion(db: Database, notificacion_id: ObjectId, estado: str) -> None:
    cambios = {"estado": estado}
    if estado == "ENVIADA":
        cambios["enviada_en"] = ahora()
    db["notificaciones"].update_one({"_id": notificacion_id}, {"$set": cambios})


def listar_notificaciones(db: Database, usuario_id: ObjectId, saltar: int, limite: int) -> tuple[list[dict], int]:
    filtros = {"usuario_id": usuario_id}
    total = db["notificaciones"].count_documents(filtros)
    datos = list(db["notificaciones"].find(filtros).sort("creado_en", -1).skip(saltar).limit(limite))
    return datos, total
