"""ENVIAR_CORREO: envía la notificación y actualiza `notificaciones` (RF-37, RF-69, RF-70)."""

from app.crud import notificaciones as crud_notificaciones
from app.crud import usuarios as crud_usuarios
from core import email


def ejecutar(db, tarea: dict) -> None:
    notificacion = crud_notificaciones.obtener_notificacion(db, tarea["datos"]["notificacion_id"])
    if notificacion is None or notificacion["estado"] == "ENVIADA":
        return
    usuario = crud_usuarios.obtener_usuario(db, notificacion["usuario_id"])
    if usuario is None or not usuario["activo"]:
        crud_notificaciones.marcar_notificacion(db, notificacion["_id"], "FALLIDA")
        return
    email.enviar(usuario["correo"], notificacion["tipo"], {"referencia": notificacion["referencia"]})
    crud_notificaciones.marcar_notificacion(db, notificacion["_id"], "ENVIADA")


def al_fallar(db, tarea: dict, definitiva: bool) -> None:
    if definitiva:
        crud_notificaciones.marcar_notificacion(db, tarea["datos"]["notificacion_id"], "FALLIDA")
