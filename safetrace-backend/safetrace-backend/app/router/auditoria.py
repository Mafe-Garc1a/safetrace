"""Rutas de A · Cuentas: consulta de auditoría (RF-10). Solo el administrador general."""

from bson import ObjectId
from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.crud import auditoria as crud_auditoria
from app.router.dependencies import requiere_permiso
from app.schemas.auditoria import AuditoriaPage
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()
modulo = "auditoria"


@router.get(
    "/admin/auditoria",
    response_model=AuditoriaPage,
    summary="Consultar registros de auditoría",
    description="RF-10",
)
def consultar_auditoria(
    coleccion: str | None = None,
    documento_id: str | None = None,
    actor_id: str | None = None,
    accion: str | None = None,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    filtros = {}
    if coleccion:
        filtros["coleccion"] = coleccion
    if documento_id:
        # Casi todos son ObjectId; la configuración usa un _id fijo de texto ("parametros_sismo")
        filtros["documento_id"] = ObjectId(documento_id) if ObjectId.is_valid(documento_id) else documento_id
    if actor_id:
        filtros["actor.id"] = a_object_id(actor_id)
    if accion:
        filtros["accion"] = accion
    datos, total = crud_auditoria.consultar(db, filtros, saltar=pagina.saltar, limite=pagina.tamano)
    return pagina.respuesta(serializar(datos), total)
