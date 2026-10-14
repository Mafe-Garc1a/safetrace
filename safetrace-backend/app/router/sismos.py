"""Rutas de F · Sismos (RF-31 a RF-37)."""

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.crud import sismos as crud_sismos
from app.router.dependencies import get_current_user, requiere_servicio_n8n
from app.schemas.sismos import SismoCreate, SismoOut, SismoPage, SismoRecibido
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()


@router.post(
    "/interno/sismos",
    response_model=SismoRecibido,
    summary="n8n entrega un sismo (credencial de servicio)",
    description="RF-31 a RF-35",
    dependencies=[Depends(requiere_servicio_n8n)],
)
def recibir_sismo(datos: SismoCreate, db: Database = Depends(get_db)):
    sismo, resultado = crud_sismos.recibir_sismo(db, datos)
    return {"sismo": serializar(sismo), "resultado": resultado}


@router.get(
    "/sismos",
    response_model=SismoPage,
    summary="Sismos recibidos, del más reciente al más antiguo",
    description="RF-33",
)
def listar_sismos(
    solo_relevantes: bool = False,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    datos, total = crud_sismos.listar_sismos(db, solo_relevantes, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.get(
    "/sismos/{sismo_id}",
    response_model=SismoOut,
    summary="Datos de un sismo",
    description="RF-33",
)
def obtener_sismo(sismo_id: str, db: Database = Depends(get_db), _: dict = Depends(get_current_user)):
    sismo = crud_sismos.obtener_sismo(db, a_object_id(sismo_id))
    if sismo is None:
        raise HTTPException(status_code=404, detail="Sismo no encontrado")
    return serializar(sismo)
