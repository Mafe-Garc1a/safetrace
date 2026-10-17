"""Rutas de C · Inmuebles y zonas (RF-17 a RF-21, RF-23)."""

from fastapi import APIRouter, Depends, status
from pymongo.database import Database

from app.crud import estados as crud_estados
from app.crud import inmuebles as crud_inmuebles
from app.crud.auditoria import actor_usuario
from app.router.dependencies import (
    get_current_user,
    obtener_inmueble_autorizado,
    puede_supervisar,
    requiere_permiso,
)
from app.schemas.inmuebles import InmuebleCreate, InmuebleOut, InmueblePage, InmuebleUpdate, ZonaOut
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()
modulo = "inmuebles"


@router.post(
    "/inmuebles",
    response_model=InmuebleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un inmueble",
    description="RF-17 a RF-20",
)
def registrar_inmueble(
    inmueble: InmuebleCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    creado = crud_inmuebles.crear_inmueble(
        db, usuario["_id"], inmueble, crud_estados.estado_inicial(), actor_usuario(usuario)
    )
    return serializar(creado)


@router.get(
    "/inmuebles",
    response_model=InmueblePage,
    summary="Inmuebles del propietario (el administrador ve todos)",
    description="RF-21",
)
def listar_mis_inmuebles(
    propietario_id: str | None = None,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    if puede_supervisar(db, usuario):
        filtros = {"propietario_id": a_object_id(propietario_id)} if propietario_id else {}
    else:
        filtros = {"propietario_id": usuario["_id"]}
    datos, total = crud_inmuebles.listar_inmuebles(db, filtros, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.get(
    "/inmuebles/{inmueble_id}",
    response_model=InmuebleOut,
    summary="Ficha del inmueble",
    description="RF-17 a RF-20",
)
def obtener_ficha(inmueble_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    return serializar(obtener_inmueble_autorizado(db, inmueble_id, usuario))


@router.put(
    "/inmuebles/{inmueble_id}",
    response_model=InmuebleOut,
    summary="Corregir datos de registro del inmueble",
    description="RF-17 a RF-20",
)
def actualizar_inmueble(
    inmueble_id: str,
    cambios: InmuebleUpdate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=True)
    actualizado = crud_inmuebles.actualizar_inmueble(db, inmueble["_id"], cambios, actor_usuario(usuario))
    return serializar(actualizado)


@router.get(
    "/zonas",
    response_model=list[ZonaOut],
    summary="Catálogo cerrado de zonas",
    description="RF-23",
)
def listar_zonas(db: Database = Depends(get_db), _: dict = Depends(get_current_user)):
    return serializar(crud_inmuebles.listar_zonas(db))
