"""Rutas de J · Análisis de IA e índice de priorización (RF-62 a RF-68).

Nada de aquí cambia el estado del inmueble (RNF-37).
"""

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.crud import ia_indice as crud_ia_indice
from app.router.dependencies import ADMIN, get_current_user, obtener_inmueble_autorizado, requiere_rol
from app.schemas.ia_indice import AnalisisOut, AnalisisPage, IndiceOut, IndicePage
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()


@router.get(
    "/inmuebles/{inmueble_id}/analisis-ia",
    response_model=AnalisisPage,
    summary="Análisis del inmueble con su leyenda",
    description="RF-63 a RF-65",
)
def listar_analisis(
    inmueble_id: str,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    datos, total = crud_ia_indice.listar_analisis(db, inmueble["_id"], pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.post(
    "/analisis-ia/{analisis_id}/reintento",
    response_model=AnalisisOut,
    summary="Reintentar un análisis fallido",
    description="RF-64, RNF-24",
)
def reintentar_analisis(
    analisis_id: str,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_rol("PROPIETARIO", ADMIN)),
):
    analisis = crud_ia_indice.obtener_analisis(db, a_object_id(analisis_id))
    if analisis is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    obtener_inmueble_autorizado(db, analisis["inmueble_id"], usuario)
    reintentado = crud_ia_indice.reintentar(db, analisis["_id"])
    if reintentado is None:
        raise HTTPException(status_code=409, detail="Solo se reintenta un análisis FALLIDO")
    return serializar(reintentado)


@router.get(
    "/inmuebles/{inmueble_id}/indice",
    response_model=IndiceOut,
    summary="Índice con variables y aviso orientativo",
    description="RF-67, RF-68",
)
def consultar_indice(inmueble_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    indice = crud_ia_indice.ultimo_indice(db, inmueble["_id"])
    if indice is None:
        raise HTTPException(status_code=404, detail="El inmueble aún no tiene índice calculado")
    return serializar(indice)


@router.get(
    "/admin/sismos/{sismo_id}/priorizacion",
    response_model=IndicePage,
    summary="Inmuebles de un sismo ordenados por índice (qué revisar primero)",
    description="RF-66",
)
def priorizacion(
    sismo_id: str,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_rol(ADMIN)),
):
    datos, total = crud_ia_indice.priorizacion_por_sismo(db, a_object_id(sismo_id), pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)
