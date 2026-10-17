"""Rutas de A · Cuentas: administración de usuarios y supresión de datos (RF-04 a RF-06, RF-08, RF-09)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.database import Database

from app.crud import roles as crud_roles
from app.crud import usuarios as crud_usuarios
from app.crud.auditoria import actor_usuario
from app.crud.roles import SUPERADMIN
from app.router.dependencies import get_current_user, requiere_permiso
from app.schemas.usuarios import SolicitudSupresionOut, UsuarioEstado, UsuarioOut, UsuarioPage, UsuarioRol
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()
modulo = "usuarios"
modulo_supresion = "supresion"


def _obtener_objetivo(db: Database, usuario_id: str) -> dict:
    usuario = crud_usuarios.obtener_usuario(db, a_object_id(usuario_id))
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


def _proteger_superadmin(admin: dict, *roles_involucrados: str) -> None:
    """Solo un SUPERADMIN asigna, quita o modifica a otro SUPERADMIN."""
    if SUPERADMIN in roles_involucrados and admin["rol"] != SUPERADMIN:
        raise HTTPException(
            status_code=403, detail="Solo un superadministrador puede gestionar a un superadministrador"
        )


@router.get(
    "/admin/usuarios",
    response_model=UsuarioPage,
    summary="Lista de usuarios",
    description="RF-04",
)
def listar_usuarios(
    rol: str | None = None,
    activo: bool | None = None,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    filtros = {}
    if rol is not None:
        filtros["rol"] = rol
    if activo is not None:
        filtros["activo"] = activo
    datos, total = crud_usuarios.listar_usuarios(db, filtros, saltar=pagina.saltar, limite=pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.patch(
    "/admin/usuarios/{usuario_id}/estado",
    response_model=UsuarioOut,
    summary="Activar o desactivar una cuenta",
    description="RF-05",
)
def activar_desactivar_usuario(
    usuario_id: str,
    cambio: UsuarioEstado,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    objetivo = _obtener_objetivo(db, usuario_id)
    if objetivo["_id"] == admin["_id"] and not cambio.activo:
        raise HTTPException(status_code=400, detail="No puede desactivar su propia cuenta")
    _proteger_superadmin(admin, objetivo["rol"])
    usuario = crud_usuarios.cambiar_activo(db, objetivo["_id"], cambio.activo, actor_usuario(admin))
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return serializar(usuario)


@router.patch(
    "/admin/usuarios/{usuario_id}/rol",
    response_model=UsuarioOut,
    summary="Cambiar el rol de un usuario",
    description="RF-06",
)
def cambiar_rol(
    usuario_id: str,
    cambio: UsuarioRol,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    objetivo = _obtener_objetivo(db, usuario_id)
    if objetivo["_id"] == admin["_id"]:
        raise HTTPException(status_code=400, detail="No puede cambiar su propio rol")
    if not crud_roles.rol_activo(db, cambio.rol):
        raise HTTPException(status_code=400, detail=f"Rol inexistente o inactivo: {cambio.rol}")
    _proteger_superadmin(admin, objetivo["rol"], cambio.rol)
    usuario = crud_usuarios.cambiar_rol(db, objetivo["_id"], cambio.rol, actor_usuario(admin))
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return serializar(usuario)


@router.post(
    "/cuentas/supresion",
    response_model=SolicitudSupresionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar la supresión de datos personales",
    description="RF-08",
)
def solicitar_supresion(db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    return serializar(crud_usuarios.solicitar_supresion(db, usuario["_id"]))


@router.get(
    "/admin/solicitudes-supresion",
    summary="Solicitudes de supresión",
    description="RF-08, RF-09",
)
def listar_solicitudes_supresion(
    estado: Literal["RECIBIDA", "ATENDIDA"] | None = Query(None),
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo_supresion, "seleccionar")),
):
    datos, total = crud_usuarios.listar_solicitudes_supresion(db, estado, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.post(
    "/admin/solicitudes-supresion/{solicitud_id}/atencion",
    response_model=SolicitudSupresionOut,
    summary="Atender una solicitud: anonimiza y lista lo que se conserva",
    description="RF-09",
)
def atender_supresion(
    solicitud_id: str,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo_supresion, "actualizar")),
):
    solicitud = crud_usuarios.atender_supresion(db, a_object_id(solicitud_id), actor_usuario(admin))
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada o ya atendida")
    return serializar(solicitud)
