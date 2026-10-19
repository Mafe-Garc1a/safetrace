"""Rutas de A · Cuentas: configuración de sismos (RF-11, RF-12). Solo el administrador general."""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.crud import configuracion as crud_configuracion
from app.crud.auditoria import actor_usuario
from app.router.dependencies import requiere_permiso
from app.schemas.configuracion import ConfiguracionOut, ConfiguracionUpdate
from core.database import get_db, serializar

router = APIRouter()
modulo = "configuracion"


@router.get(
    "/admin/configuracion",
    response_model=ConfiguracionOut,
    summary="Ver magnitud mínima y radio",
    description="RF-11, RF-12",
)
def obtener_configuracion(db: Database = Depends(get_db), _: dict = Depends(requiere_permiso(modulo, "seleccionar"))):
    return serializar(crud_configuracion.obtener_configuracion_sismos(db))


@router.put(
    "/admin/configuracion",
    response_model=ConfiguracionOut,
    summary="Cambiar magnitud mínima y radio",
    description="RF-11, RF-12",
)
def actualizar_configuracion(
    configuracion: ConfiguracionUpdate,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    nueva = crud_configuracion.actualizar_configuracion_sismos(
        db, configuracion.magnitud_minima, configuracion.radio_afectacion_km, actor_usuario(admin)
    )
    return serializar(nueva)
