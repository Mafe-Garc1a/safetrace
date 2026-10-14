"""Rutas de E · Revisión del propietario (RF-28 a RF-30)."""

from fastapi import APIRouter, Depends, status
from pymongo.database import Database

from app.crud import revisiones as crud_revisiones
from app.router.bitacora import validar_zona
from app.router.dependencies import get_current_user, obtener_inmueble_autorizado, requiere_rol, requiere_servicio_n8n
from app.schemas.revisiones import RevisionCreate, RevisionOut, RevisionPage
from core.database import get_db, serializar
from core.paginacion import Pagina

router = APIRouter()


@router.post(
    "/inmuebles/{inmueble_id}/revisiones",
    response_model=RevisionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una revisión con fotos",
    description="RF-28, RF-29",
)
def registrar_revision(
    inmueble_id: str,
    revision: RevisionCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_rol("PROPIETARIO")),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=True)
    for foto in revision.fotos:
        validar_zona(db, foto.zona_id)
    return serializar(crud_revisiones.registrar_revision(db, inmueble, revision, usuario))


@router.get(
    "/inmuebles/{inmueble_id}/revisiones",
    response_model=RevisionPage,
    summary="Revisiones del inmueble",
    description="RF-28",
)
def listar_revisiones(
    inmueble_id: str,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    datos, total = crud_revisiones.listar_revisiones(db, inmueble["_id"], pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.post(
    "/interno/recordatorios-semestrales",
    summary="Tarea diaria de n8n",
    description="RF-30",
    dependencies=[Depends(requiere_servicio_n8n)],
)
def enviar_recordatorios(db: Database = Depends(get_db)):
    return {"recordatorios_enviados": crud_revisiones.enviar_recordatorios(db)}
