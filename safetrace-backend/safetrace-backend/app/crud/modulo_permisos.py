"""Acceso a datos de los permisos por rol y módulo (como en avisena).

Colecciones de las que es dueño: permisos. Un documento por par (rol, módulo).
"""

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.crud import auditoria
from app.schemas.permisos import PermisoCreate, PermisoUpdate


class PermisoDuplicado(Exception):
    """Ya existe un permiso para ese rol y módulo."""


class ReferenciaInvalida(Exception):
    """El rol o el módulo no existen."""


def crear_permiso(db: Database, permiso: PermisoCreate, actor: dict) -> dict:
    if db["roles"].count_documents({"_id": permiso.rol}, limit=1) == 0:
        raise ReferenciaInvalida(f"El rol {permiso.rol} no existe")
    if db["modulos"].count_documents({"_id": permiso.modulo}, limit=1) == 0:
        raise ReferenciaInvalida(f"El módulo {permiso.modulo} no existe")
    documento = permiso.model_dump()
    try:
        documento["_id"] = db["permisos"].insert_one(documento).inserted_id
    except DuplicateKeyError:
        raise PermisoDuplicado() from None
    auditoria.registrar(db, "permisos", documento["_id"], "CREAR_PERMISO", actor, permiso.model_dump())
    return documento


def listar_permisos(db: Database, filtros: dict) -> list[dict]:
    return list(db["permisos"].find(filtros).sort([("modulo", 1), ("rol", 1)]))


def obtener_permiso(db: Database, modulo: str, rol: str) -> dict | None:
    return db["permisos"].find_one({"modulo": modulo, "rol": rol})


def actualizar_permiso(db: Database, modulo: str, rol: str, cambios: PermisoUpdate, actor: dict) -> dict | None:
    datos = cambios.model_dump(exclude_unset=True, exclude_none=True)
    if not datos:
        return obtener_permiso(db, modulo, rol)
    anterior = db["permisos"].find_one_and_update({"modulo": modulo, "rol": rol}, {"$set": datos})
    if anterior is None:
        return None
    auditoria.registrar(
        db,
        "permisos",
        anterior["_id"],
        "ACTUALIZAR_PERMISO",
        actor,
        {"modulo": modulo, "rol": rol, "anterior": {k: anterior.get(k) for k in datos}, "nuevo": datos},
    )
    return db["permisos"].find_one({"_id": anterior["_id"]})


def dar_todos_los_permisos(db: Database, rol: str, modulo: str) -> None:
    """Crea o completa el permiso con las cuatro acciones. Lo usan las semillas y la creación de módulos."""
    db["permisos"].update_one(
        {"rol": rol, "modulo": modulo},
        {"$set": {"insertar": True, "actualizar": True, "seleccionar": True, "borrar": True}},
        upsert=True,
    )
