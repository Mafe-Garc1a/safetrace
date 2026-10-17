"""Acceso a datos de los módulos (como en avisena).

Colecciones de las que es dueño: modulos. El `_id` es el nombre del módulo (p. ej. "inmuebles"),
el mismo que declara cada router en su variable `modulo`.

Reglas clave:
- Un módulo inactivo niega el acceso a todos los roles.
- Los módulos de administración de permisos no se desactivan (nadie podría volver a activarlos).
"""

from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.crud import auditoria
from app.crud import modulo_permisos as crud_modulo_permisos
from app.crud.roles import SUPERADMIN
from app.schemas.modulos import ModuloCreate, ModuloUpdate
from core.fechas import ahora

MODULOS_PROTEGIDOS = ("roles", "modulos", "permisos")


class ModuloDuplicado(Exception):
    """Ya existe un módulo con ese nombre."""


class ModuloProtegido(Exception):
    """Los módulos de administración de permisos no se desactivan."""


def crear_modulo(db: Database, modulo: ModuloCreate, actor: dict) -> dict:
    """Crea el módulo y da al SUPERADMIN todos los permisos sobre él."""
    momento = ahora()
    documento = {"_id": modulo.nombre_modulo, **modulo.model_dump(), "creado_en": momento, "actualizado_en": momento}
    try:
        db["modulos"].insert_one(documento)
    except DuplicateKeyError:
        raise ModuloDuplicado() from None
    crud_modulo_permisos.dar_todos_los_permisos(db, SUPERADMIN, modulo.nombre_modulo)
    auditoria.registrar(db, "modulos", modulo.nombre_modulo, "CREAR_MODULO", actor, {"estado": modulo.estado})
    return documento


def listar_modulos(db: Database) -> list[dict]:
    return list(db["modulos"].find({}).sort("_id", 1))


def obtener_modulo(db: Database, nombre_modulo: str) -> dict | None:
    return db["modulos"].find_one({"_id": nombre_modulo})


def actualizar_modulo(db: Database, nombre_modulo: str, cambios: ModuloUpdate, actor: dict) -> dict | None:
    datos = cambios.model_dump(exclude_unset=True, exclude_none=True)
    if not datos:
        return obtener_modulo(db, nombre_modulo)
    datos["actualizado_en"] = ahora()
    actualizado = db["modulos"].find_one_and_update(
        {"_id": nombre_modulo}, {"$set": datos}, return_document=ReturnDocument.AFTER
    )
    if actualizado:
        auditoria.registrar(db, "modulos", nombre_modulo, "ACTUALIZAR_MODULO", actor, {"campos": ["descripcion"]})
    return actualizado


def cambiar_estado_modulo(db: Database, nombre_modulo: str, estado: bool, actor: dict) -> dict | None:
    if nombre_modulo in MODULOS_PROTEGIDOS and not estado:
        raise ModuloProtegido()
    anterior = db["modulos"].find_one_and_update(
        {"_id": nombre_modulo}, {"$set": {"estado": estado, "actualizado_en": ahora()}}
    )
    if anterior is None:
        return None
    auditoria.registrar(
        db, "modulos", nombre_modulo, "CAMBIAR_ESTADO_MODULO", actor, {"anterior": anterior["estado"], "nuevo": estado}
    )
    return obtener_modulo(db, nombre_modulo)
