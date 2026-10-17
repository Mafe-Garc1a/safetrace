"""Rutas de los permisos por rol y módulo (como en avisena). Por defecto, solo el SUPERADMIN las usa.

Los permisos del SUPERADMIN no se modifican: siempre tiene las cuatro acciones en todos los módulos.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import modulo_permisos as crud_modulo_permisos
from app.crud.auditoria import actor_usuario
from app.crud.roles import SUPERADMIN
from app.router.dependencies import requiere_permiso
from app.schemas.permisos import PermisoCreate, PermisoOut, PermisoUpdate
from core.database import get_db, serializar

router = APIRouter()
modulo = "permisos"


@router.get("/admin/permisos", response_model=list[PermisoOut], summary="Permisos, filtrados por rol o módulo")
def listar_permisos(
    rol: str | None = None,
    modulo_id: str | None = None,
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    filtros = {}
    if rol:
        filtros["rol"] = rol
    if modulo_id:
        filtros["modulo"] = modulo_id
    return serializar(crud_modulo_permisos.listar_permisos(db, filtros))


@router.post(
    "/admin/permisos", response_model=PermisoOut, status_code=status.HTTP_201_CREATED, summary="Crear un permiso"
)
def crear_permiso(
    permiso: PermisoCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    try:
        return serializar(crud_modulo_permisos.crear_permiso(db, permiso, actor_usuario(usuario)))
    except crud_modulo_permisos.ReferenciaInvalida as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except crud_modulo_permisos.PermisoDuplicado:
        raise HTTPException(status_code=409, detail="Ya existe un permiso para ese rol y módulo") from None


@router.get("/admin/permisos/{modulo_id}/{rol}", response_model=PermisoOut, summary="Permiso de un rol en un módulo")
def obtener_permiso(
    modulo_id: str,
    rol: str,
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    permiso = crud_modulo_permisos.obtener_permiso(db, modulo_id, rol)
    if permiso is None:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")
    return serializar(permiso)


@router.put("/admin/permisos/{modulo_id}/{rol}", response_model=PermisoOut, summary="Cambiar un permiso")
def actualizar_permiso(
    modulo_id: str,
    rol: str,
    cambios: PermisoUpdate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    if rol == SUPERADMIN:
        raise HTTPException(status_code=409, detail="Los permisos del SUPERADMIN no se modifican")
    permiso = crud_modulo_permisos.actualizar_permiso(db, modulo_id, rol, cambios, actor_usuario(usuario))
    if permiso is None:
        raise HTTPException(status_code=404, detail="Permiso no encontrado")
    return serializar(permiso)
