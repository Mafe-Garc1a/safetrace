"""Rutas de los roles (como en avisena). Por defecto, solo el SUPERADMIN tiene permisos sobre este módulo."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import roles as crud_roles
from app.crud.auditoria import actor_usuario
from app.router.dependencies import requiere_permiso
from app.schemas.roles import RolCreate, RolEstado, RolOut, RolPage, RolUpdate
from core.database import get_db, serializar
from core.paginacion import Pagina

router = APIRouter()
modulo = "roles"


def _obtener(db: Database, rol_id: str) -> dict:
    rol = crud_roles.obtener_rol(db, rol_id)
    if rol is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    return rol


@router.post("/admin/roles", response_model=RolOut, status_code=status.HTTP_201_CREATED, summary="Crear un rol")
def crear_rol(
    rol: RolCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    try:
        return serializar(crud_roles.crear_rol(db, rol, actor_usuario(usuario)))
    except crud_roles.RolDuplicado:
        raise HTTPException(status_code=409, detail="Ya existe un rol con ese nombre") from None


@router.get("/admin/roles", response_model=RolPage, summary="Roles, paginados")
def listar_roles(
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    datos, total = crud_roles.listar_roles(db, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.get("/admin/roles/{rol_id}", response_model=RolOut, summary="Un rol por su nombre")
def obtener_rol(
    rol_id: str, db: Database = Depends(get_db), _: dict = Depends(requiere_permiso(modulo, "seleccionar"))
):
    return serializar(_obtener(db, rol_id))


@router.put("/admin/roles/{rol_id}", response_model=RolOut, summary="Cambiar la descripción de un rol")
def actualizar_rol(
    rol_id: str,
    cambios: RolUpdate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    _obtener(db, rol_id)
    return serializar(crud_roles.actualizar_rol(db, rol_id, cambios, actor_usuario(usuario)))


@router.patch(
    "/admin/roles/{rol_id}/estado",
    response_model=RolOut,
    summary="Activar o desactivar un rol (cierra las sesiones de sus usuarios)",
)
def cambiar_estado_rol(
    rol_id: str,
    cambio: RolEstado,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    try:
        rol = crud_roles.cambiar_estado_rol(db, rol_id, cambio.estado, actor_usuario(usuario))
    except crud_roles.RolProtegido:
        raise HTTPException(status_code=409, detail="El rol SUPERADMIN no se desactiva") from None
    if rol is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    return serializar(rol)
