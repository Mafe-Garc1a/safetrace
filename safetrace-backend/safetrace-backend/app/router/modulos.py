"""Rutas de los módulos (como en avisena). Por defecto, solo el SUPERADMIN tiene permisos sobre este módulo.

Crear un módulo aquí solo registra su nombre: para que proteja rutas, un router debe declararlo en `modulo`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import modulos as crud_modulos
from app.crud.auditoria import actor_usuario
from app.router.dependencies import requiere_permiso
from app.schemas.modulos import ModuloCreate, ModuloEstado, ModuloOut, ModuloUpdate
from core.database import get_db, serializar

router = APIRouter()
modulo = "modulos"


def _obtener(db: Database, modulo_id: str) -> dict:
    encontrado = crud_modulos.obtener_modulo(db, modulo_id)
    if encontrado is None:
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    return encontrado


@router.get("/admin/modulos", response_model=list[ModuloOut], summary="Todos los módulos")
def listar_modulos(db: Database = Depends(get_db), _: dict = Depends(requiere_permiso(modulo, "seleccionar"))):
    return serializar(crud_modulos.listar_modulos(db))


@router.post(
    "/admin/modulos",
    response_model=ModuloOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un módulo (el SUPERADMIN recibe todos los permisos sobre él)",
)
def crear_modulo(
    datos: ModuloCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    try:
        return serializar(crud_modulos.crear_modulo(db, datos, actor_usuario(usuario)))
    except crud_modulos.ModuloDuplicado:
        raise HTTPException(status_code=409, detail="Ya existe un módulo con ese nombre") from None


@router.get("/admin/modulos/{modulo_id}", response_model=ModuloOut, summary="Un módulo por su nombre")
def obtener_modulo(
    modulo_id: str, db: Database = Depends(get_db), _: dict = Depends(requiere_permiso(modulo, "seleccionar"))
):
    return serializar(_obtener(db, modulo_id))


@router.put("/admin/modulos/{modulo_id}", response_model=ModuloOut, summary="Cambiar la descripción de un módulo")
def actualizar_modulo(
    modulo_id: str,
    cambios: ModuloUpdate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    _obtener(db, modulo_id)
    return serializar(crud_modulos.actualizar_modulo(db, modulo_id, cambios, actor_usuario(usuario)))


@router.patch(
    "/admin/modulos/{modulo_id}/estado",
    response_model=ModuloOut,
    summary="Activar o desactivar un módulo (inactivo: nadie lo usa)",
)
def cambiar_estado_modulo(
    modulo_id: str,
    cambio: ModuloEstado,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    try:
        actualizado = crud_modulos.cambiar_estado_modulo(db, modulo_id, cambio.estado, actor_usuario(usuario))
    except crud_modulos.ModuloProtegido:
        raise HTTPException(status_code=409, detail="Los módulos roles, modulos y permisos no se desactivan") from None
    if actualizado is None:
        raise HTTPException(status_code=404, detail="Módulo no encontrado")
    return serializar(actualizado)
