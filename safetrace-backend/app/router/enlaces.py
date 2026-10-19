"""Rutas de I · Enlace público (RF-59 a RF-61)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import enlaces as crud_enlaces
from app.router.dependencies import obtener_inmueble_autorizado, requiere_permiso
from app.schemas.enlaces import EnlaceCreate, EnlaceOut
from core.database import a_object_id, get_db, serializar

router = APIRouter()
modulo = "enlaces"


@router.post(
    "/inmuebles/{inmueble_id}/enlaces",
    response_model=EnlaceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear enlace eligiendo qué se comparte",
    description="RF-59, RF-60",
)
def crear_enlace(
    inmueble_id: str,
    enlace: EnlaceCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=True)
    return serializar(crud_enlaces.crear_enlace(db, inmueble["_id"], enlace.campos_compartidos, usuario))


@router.get(
    "/inmuebles/{inmueble_id}/enlaces",
    response_model=list[EnlaceOut],
    summary="Enlaces creados para el inmueble (activos y revocados)",
    description="RF-59, RF-61",
)
def listar_enlaces(
    inmueble_id: str,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=True)
    return serializar(crud_enlaces.listar_enlaces(db, inmueble["_id"]))


@router.delete(
    "/enlaces/{enlace_id}",
    response_model=EnlaceOut,
    summary="Revocar un enlace (no se borra)",
    description="RF-61",
)
def revocar_enlace(
    enlace_id: str,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "borrar")),
):
    enlace = crud_enlaces.obtener_enlace(db, a_object_id(enlace_id))
    if enlace is None:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    obtener_inmueble_autorizado(db, enlace["inmueble_id"], usuario, solo_propietario=True)
    revocado = crud_enlaces.revocar_enlace(db, enlace, usuario)
    if revocado is None:
        raise HTTPException(status_code=409, detail="El enlace ya estaba revocado")
    return serializar(revocado)


@router.get(
    "/publico/{codigo}",
    summary="Vista pública de solo lectura, sin estado (sin cuenta)",
    description="RF-59, RNF-18, RNF-19",
)
def ver_enlace_publico(codigo: str, db: Database = Depends(get_db)):
    vista = crud_enlaces.vista_publica(db, codigo)
    if vista is None:
        raise HTTPException(status_code=404, detail="Enlace inexistente o revocado")
    return vista
