"""Acceso a datos de los roles (como en avisena).

Colecciones de las que es dueño: roles. El `_id` es el nombre del rol (p. ej. "PROPIETARIO").

Reglas clave:
- SUPERADMIN tiene todos los permisos y no se desactiva.
- Desactivar un rol cierra las sesiones de sus usuarios y les impide iniciar sesión.
"""

from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.crud import auditoria
from app.crud import usuarios as crud_usuarios
from app.schemas.roles import RolCreate, RolUpdate
from core.fechas import ahora

SUPERADMIN = "SUPERADMIN"


class RolDuplicado(Exception):
    """Ya existe un rol con ese nombre."""


class RolProtegido(Exception):
    """El rol SUPERADMIN no se desactiva."""


def crear_rol(db: Database, rol: RolCreate, actor: dict) -> dict:
    momento = ahora()
    documento = {"_id": rol.nombre_rol, **rol.model_dump(), "creado_en": momento, "actualizado_en": momento}
    try:
        db["roles"].insert_one(documento)
    except DuplicateKeyError:
        raise RolDuplicado() from None
    auditoria.registrar(db, "roles", rol.nombre_rol, "CREAR_ROL", actor, {"estado": rol.estado})
    return documento


def obtener_rol(db: Database, nombre_rol: str) -> dict | None:
    return db["roles"].find_one({"_id": nombre_rol})


def rol_activo(db: Database, nombre_rol: str) -> bool:
    """True si el rol existe y está activo. Lo usan el inicio de sesión y el cambio de rol."""
    return db["roles"].count_documents({"_id": nombre_rol, "estado": True}, limit=1) > 0


def listar_roles(db: Database, saltar: int = 0, limite: int = 20) -> tuple[list[dict], int]:
    total = db["roles"].count_documents({})
    datos = list(db["roles"].find({}).sort("_id", 1).skip(saltar).limit(limite))
    return datos, total


def actualizar_rol(db: Database, nombre_rol: str, cambios: RolUpdate, actor: dict) -> dict | None:
    datos = cambios.model_dump(exclude_unset=True, exclude_none=True)
    if not datos:
        return obtener_rol(db, nombre_rol)
    datos["actualizado_en"] = ahora()
    actualizado = db["roles"].find_one_and_update(
        {"_id": nombre_rol}, {"$set": datos}, return_document=ReturnDocument.AFTER
    )
    if actualizado:
        auditoria.registrar(db, "roles", nombre_rol, "ACTUALIZAR_ROL", actor, {"campos": ["descripcion"]})
    return actualizado


def cambiar_estado_rol(db: Database, nombre_rol: str, estado: bool, actor: dict) -> dict | None:
    if nombre_rol == SUPERADMIN and not estado:
        raise RolProtegido()
    anterior = db["roles"].find_one_and_update(
        {"_id": nombre_rol}, {"$set": {"estado": estado, "actualizado_en": ahora()}}
    )
    if anterior is None:
        return None
    if not estado:
        crud_usuarios.cerrar_sesiones_por_rol(db, nombre_rol)
    auditoria.registrar(
        db, "roles", nombre_rol, "CAMBIAR_ESTADO_ROL", actor, {"anterior": anterior["estado"], "nuevo": estado}
    )
    return obtener_rol(db, nombre_rol)
