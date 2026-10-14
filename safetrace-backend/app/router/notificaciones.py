"""Rutas de K · Notificaciones y procesos (RF-69 a RF-71)."""

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.crud import notificaciones as crud_notificaciones
from app.router.dependencies import get_current_user
from app.schemas.notificaciones import NotificacionPage, TareaOut
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()


@router.get(
    "/tareas/{tarea_id}",
    response_model=TareaOut,
    summary="Estado de una operación en segundo plano",
    description="RF-71",
)
def consultar_tarea(tarea_id: str, db: Database = Depends(get_db), _: dict = Depends(get_current_user)):
    tarea = crud_notificaciones.obtener_tarea(db, a_object_id(tarea_id))
    if tarea is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return serializar(tarea)


@router.get(
    "/notificaciones",
    response_model=NotificacionPage,
    summary="Avisos enviados al usuario de la sesión",
    description="RF-37, RF-69, RF-70",
)
def mis_notificaciones(
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    datos, total = crud_notificaciones.listar_notificaciones(db, usuario["_id"], pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)
