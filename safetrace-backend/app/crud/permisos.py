"""Verificación de permisos por rol y módulo (como `verify_permissions` de avisena).

Solo lee las colecciones `permisos` y `modulos`; las escriben `crud/modulo_permisos.py` y `crud/modulos.py`.
"""

from pymongo.database import Database

ACCIONES = ("insertar", "actualizar", "seleccionar", "borrar")


def verificar_permisos(db: Database, rol: str, modulo: str, accion: str) -> bool:
    """True si el rol tiene la acción sobre el módulo y el módulo está activo."""
    if accion not in ACCIONES:
        raise ValueError(f"Acción desconocida: {accion}")
    permiso = db["permisos"].find_one({"rol": rol, "modulo": modulo}, {accion: 1})
    if not permiso or not permiso.get(accion):
        return False
    return db["modulos"].count_documents({"_id": modulo, "estado": True}, limit=1) > 0


def permisos_de_rol(db: Database, rol: str) -> list[dict]:
    """Todos los permisos del rol, para que el frontend arme el menú."""
    return list(db["permisos"].find({"rol": rol}, {"_id": 0}).sort("modulo", 1))
