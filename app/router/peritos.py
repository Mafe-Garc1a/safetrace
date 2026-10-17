"""Rutas de B · Peritos (RF-13 a RF-16, RNF-15)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import peritos as crud_peritos
from app.crud.auditoria import actor_usuario
from app.router.dependencies import requiere_permiso, requiere_servicio_n8n
from app.schemas.peritos import (
    DocumentosCreate,
    EstadoCredencial,
    InconsistenciaCreate,
    PeritoCreate,
    PeritoOut,
    ValidacionCreate,
)
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina

router = APIRouter()
modulo = "perfil_perito"
modulo_validacion = "validacion_peritos"


def _mi_perfil(db: Database, usuario: dict) -> dict:
    perito = crud_peritos.obtener_por_usuario(db, usuario["_id"])
    if perito is None:
        raise HTTPException(status_code=404, detail="Primero registre su perfil profesional")
    return perito


@router.post(
    "/peritos/perfil",
    response_model=PeritoOut,
    status_code=status.HTTP_201_CREATED,
    summary="El perito registra su perfil profesional",
    description="RF-13",
)
def registrar_perfil(
    perfil: PeritoCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    try:
        perito = crud_peritos.crear_perfil(db, usuario["_id"], perfil)
    except crud_peritos.PerfilDuplicado:
        raise HTTPException(status_code=409, detail="El perfil o la matrícula ya están registrados") from None
    return serializar(perito)


@router.post(
    "/peritos/documentos",
    response_model=PeritoOut,
    summary="Registrar referencias de documentos ya subidos al proveedor",
    description="RF-14",
)
def registrar_documentos(
    datos: DocumentosCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    perito = _mi_perfil(db, usuario)
    return serializar(crud_peritos.agregar_documentos(db, perito, datos.documentos))


@router.get(
    "/peritos/mi-estado",
    response_model=PeritoOut,
    summary="El perito consulta el estado de sus credenciales",
    description="RF-13",
)
def consultar_mi_estado(
    db: Database = Depends(get_db), usuario: dict = Depends(requiere_permiso(modulo, "seleccionar"))
):
    return serializar(_mi_perfil(db, usuario))


@router.get(
    "/admin/peritos",
    summary="Peritos por estado (p. ej. PENDIENTE_VALIDACION)",
    description="RF-15",
)
def listar_peritos(
    estado: EstadoCredencial | None = None,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo_validacion, "seleccionar")),
):
    datos, total = crud_peritos.listar_por_estado(db, estado, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.post(
    "/admin/peritos/{perito_id}/validacion",
    response_model=PeritoOut,
    summary="Aprobar o rechazar, con documentos revisados",
    description="RF-15, RF-16",
)
def validar_credenciales(
    perito_id: str,
    validacion: ValidacionCreate,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo_validacion, "actualizar")),
):
    try:
        perito = crud_peritos.validar(
            db,
            a_object_id(perito_id),
            validacion.decision,
            validacion.motivo,
            validacion.documentos_revisados,
            actor_usuario(admin),
        )
    except crud_peritos.EstadoNoPermitido as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    if perito is None:
        raise HTTPException(status_code=404, detail="Perito no encontrado")
    return serializar(perito)


@router.post(
    "/admin/peritos/{perito_id}/inconsistencia",
    response_model=PeritoOut,
    summary="Marcar credenciales inconsistentes",
    description="RNF-15",
)
def marcar_inconsistencia(
    perito_id: str,
    datos: InconsistenciaCreate,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo_validacion, "actualizar")),
):
    perito = crud_peritos.marcar_inconsistente(db, a_object_id(perito_id), datos.motivo, actor_usuario(admin))
    if perito is None:
        raise HTTPException(status_code=404, detail="Perito no encontrado")
    return serializar(perito)


@router.post(
    "/interno/peritos/vencimientos",
    summary="Tarea diaria de n8n: matrículas vencidas",
    description="RNF-15",
    dependencies=[Depends(requiere_servicio_n8n)],
)
def marcar_vencimientos(db: Database = Depends(get_db)):
    return {"peritos_vencidos": crud_peritos.marcar_vencidos(db)}
