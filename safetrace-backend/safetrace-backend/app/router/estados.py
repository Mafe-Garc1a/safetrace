"""Rutas de G · Estados del inmueble (RF-46, RF-47).

Aquí solo se consulta: los cambios de estado los piden E, F y H con `crud.estados.pedir_transicion`.
"""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.crud import estados as crud_estados
from app.router.dependencies import get_current_user, obtener_inmueble_autorizado
from app.schemas.estados import EstadoActual, HistorialPage
from core.database import get_db, serializar
from core.paginacion import Pagina

router = APIRouter()


@router.get(
    "/inmuebles/{inmueble_id}/estado",
    response_model=EstadoActual,
    summary="Estado actual (propietario, perito asignado, administrador)",
    description="RF-47",
)
def consultar_estado(inmueble_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    return inmueble["estado"]


@router.get(
    "/inmuebles/{inmueble_id}/historial-estados",
    response_model=HistorialPage,
    summary="Historial de cambios de estado",
    description="RF-46",
)
def historial_estados(
    inmueble_id: str,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    datos, total = crud_estados.historial(db, inmueble["_id"], pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)
