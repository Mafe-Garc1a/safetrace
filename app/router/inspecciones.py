"""Rutas de H · Inspecciones y constancias (RF-48 a RF-58)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.crud import inmuebles as crud_inmuebles
from app.crud import inspecciones as crud_inspecciones
from app.crud import peritos as crud_peritos
from app.crud import usuarios as crud_usuarios
from app.crud.auditoria import actor_usuario
from app.router.bitacora import validar_zona
from app.router.dependencies import (
    get_current_user,
    obtener_inmueble_autorizado,
    requiere_permiso,
    requiere_servicio_n8n,
)
from app.schemas.inspecciones import (
    AsignacionCreate,
    CorreccionCreate,
    EstadoSolicitud,
    FirmaCreate,
    InspeccionCreate,
    InspeccionOut,
    InspeccionUpdate,
    SolicitudCreate,
    SolicitudOut,
    SolicitudPage,
    VerificacionOut,
)
from core.database import a_object_id, get_db, serializar
from core.paginacion import Pagina
from core.security import verificar_contrasena

router = APIRouter()
modulo = "inspecciones"
modulo_solicitudes = "solicitudes_inspeccion"
modulo_asignacion = "asignacion_peritos"


def _regla(e: crud_inspecciones.ReglaInspeccion):
    return HTTPException(status_code=409, detail=str(e))


def _obtener_solicitud(db: Database, solicitud_id: str) -> dict:
    solicitud = crud_inspecciones.obtener_solicitud(db, a_object_id(solicitud_id))
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


def _obtener_inspeccion(db: Database, inspeccion_id: str, usuario: dict) -> dict:
    inspeccion = crud_inspecciones.obtener_inspeccion(db, a_object_id(inspeccion_id))
    if inspeccion is None:
        raise HTTPException(status_code=404, detail="Inspección no encontrada")
    obtener_inmueble_autorizado(db, inspeccion["inmueble_id"], usuario)
    return inspeccion


# --- Solicitudes ----------------------------------------------------------------


@router.post(
    "/inmuebles/{inmueble_id}/solicitudes-inspeccion",
    response_model=SolicitudOut,
    status_code=status.HTTP_201_CREATED,
    summary="El propietario solicita una inspección",
    description="RF-48",
)
def solicitar_inspeccion(
    inmueble_id: str,
    solicitud: SolicitudCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo_solicitudes, "insertar")),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=True)
    try:
        return serializar(crud_inspecciones.crear_solicitud(db, inmueble, solicitud, usuario))
    except crud_inspecciones.ReglaInspeccion as e:
        raise _regla(e) from None


@router.get(
    "/inmuebles/{inmueble_id}/solicitudes-inspeccion",
    response_model=SolicitudPage,
    summary="Solicitudes de inspección del inmueble",
    description="RF-48, RF-69",
)
def listar_solicitudes_inmueble(
    inmueble_id: str,
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    datos, total = crud_inspecciones.listar_solicitudes(
        db, {"inmueble_id": inmueble["_id"]}, pagina.saltar, pagina.tamano
    )
    return pagina.respuesta(serializar(datos), total)


@router.get(
    "/admin/solicitudes-inspeccion",
    response_model=SolicitudPage,
    summary="Solicitudes por estado, para asignar peritos",
    description="RF-49",
)
def listar_solicitudes(
    estado: EstadoSolicitud | None = "SOLICITADA",
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    _: dict = Depends(requiere_permiso(modulo_asignacion, "seleccionar")),
):
    filtros = {"estado": estado} if estado else {}
    datos, total = crud_inspecciones.listar_solicitudes(db, filtros, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.get(
    "/peritos/solicitudes",
    response_model=SolicitudPage,
    summary="Solicitudes asignadas al perito",
    description="RF-49, RF-50",
)
def listar_solicitudes_perito(
    pagina: Pagina = Depends(),
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "seleccionar")),
):
    perito = crud_peritos.obtener_por_usuario(db, usuario["_id"])
    if perito is None:
        raise HTTPException(status_code=404, detail="Primero registre su perfil profesional")
    datos, total = crud_inspecciones.listar_solicitudes(db, {"perito_id": perito["_id"]}, pagina.saltar, pagina.tamano)
    return pagina.respuesta(serializar(datos), total)


@router.post(
    "/admin/solicitudes-inspeccion/{solicitud_id}/asignacion",
    response_model=SolicitudOut,
    summary="Asignar un perito validado",
    description="RF-49",
)
def asignar_perito(
    solicitud_id: str,
    asignacion: AsignacionCreate,
    db: Database = Depends(get_db),
    admin: dict = Depends(requiere_permiso(modulo_asignacion, "actualizar")),
):
    solicitud = _obtener_solicitud(db, solicitud_id)
    inmueble = obtener_inmueble_autorizado(db, solicitud["inmueble_id"], admin)
    try:
        actualizada = crud_inspecciones.asignar_perito(
            db, solicitud, a_object_id(asignacion.perito_id), inmueble["propietario_id"], actor_usuario(admin)
        )
    except crud_inspecciones.ReglaInspeccion as e:
        raise _regla(e) from None
    return serializar(actualizada)


# --- Inspecciones -----------------------------------------------------------------


@router.post(
    "/solicitudes-inspeccion/{solicitud_id}/inspeccion",
    response_model=InspeccionOut,
    status_code=status.HTTP_201_CREATED,
    summary="El perito registra la inspección",
    description="RF-50, RF-51",
)
def registrar_inspeccion(
    solicitud_id: str,
    inspeccion: InspeccionCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    solicitud = _obtener_solicitud(db, solicitud_id)
    for evidencia in inspeccion.evidencias:
        validar_zona(db, evidencia.zona_id)
    try:
        return serializar(crud_inspecciones.registrar_inspeccion(db, solicitud, inspeccion, usuario))
    except crud_inspecciones.ReglaInspeccion as e:
        raise _regla(e) from None


@router.get(
    "/inmuebles/{inmueble_id}/inspecciones",
    response_model=list[InspeccionOut],
    summary="Inspecciones del inmueble con todas sus versiones",
    description="RF-50, RF-53",
)
def listar_inspecciones(inmueble_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    inmueble = obtener_inmueble_autorizado(db, inmueble_id, usuario)
    return serializar(crud_inspecciones.listar_inspecciones(db, inmueble["_id"]))


@router.get(
    "/inspecciones/{inspeccion_id}",
    response_model=InspeccionOut,
    summary="Detalle de una inspección",
    description="RF-50",
)
def obtener_inspeccion(inspeccion_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
    return serializar(_obtener_inspeccion(db, inspeccion_id, usuario))


@router.put(
    "/inspecciones/{inspeccion_id}",
    response_model=InspeccionOut,
    summary="Editar la inspección antes de firmarla",
    description="RF-50, RNF-13",
)
def editar_inspeccion(
    inspeccion_id: str,
    cambios: InspeccionUpdate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    inspeccion = _obtener_inspeccion(db, inspeccion_id, usuario)
    try:
        return serializar(crud_inspecciones.actualizar_borrador(db, inspeccion, cambios, usuario))
    except crud_inspecciones.ReglaInspeccion as e:
        raise _regla(e) from None


@router.post(
    "/inspecciones/{inspeccion_id}/firma",
    response_model=InspeccionOut,
    summary="Firmar con contraseña y emitir constancia",
    description="RF-52, RF-54, RF-55, RF-57",
)
def firmar_inspeccion(
    inspeccion_id: str,
    firma: FirmaCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "actualizar")),
):
    inspeccion = _obtener_inspeccion(db, inspeccion_id, usuario)
    hash_guardado = crud_usuarios.obtener_hash_contrasena(db, usuario["_id"])
    if not hash_guardado or not verificar_contrasena(firma.contrasena, hash_guardado):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta: no se firmó la inspección")
    try:
        return serializar(crud_inspecciones.firmar(db, inspeccion, firma.vigencia_meses, usuario))
    except crud_inspecciones.ReglaInspeccion as e:
        raise _regla(e) from None


@router.post(
    "/inspecciones/{inspeccion_id}/correccion",
    response_model=InspeccionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Nueva versión de una inspección firmada",
    description="RF-53",
)
def corregir_inspeccion(
    inspeccion_id: str,
    correccion: CorreccionCreate,
    db: Database = Depends(get_db),
    usuario: dict = Depends(requiere_permiso(modulo, "insertar")),
):
    inspeccion = _obtener_inspeccion(db, inspeccion_id, usuario)
    for evidencia in correccion.evidencias:
        validar_zona(db, evidencia.zona_id)
    try:
        return serializar(crud_inspecciones.crear_correccion(db, inspeccion, correccion, usuario))
    except crud_inspecciones.ReglaInspeccion as e:
        raise _regla(e) from None


# --- Constancias --------------------------------------------------------------------


@router.get(
    "/constancias/{codigo}",
    response_model=VerificacionOut,
    summary="Verificación pública por código o QR (sin cuenta)",
    description="RF-56, RF-58",
)
def verificar_constancia(codigo: str, db: Database = Depends(get_db)):
    inspeccion = crud_inspecciones.obtener_por_codigo(db, codigo.strip().upper())
    if inspeccion is None:
        raise HTTPException(status_code=404, detail="No existe una constancia con ese código")
    perito = crud_peritos.obtener_perito(db, inspeccion["perito_id"])
    usuario_perito = crud_usuarios.obtener_usuario(db, perito["usuario_id"])
    inmueble = crud_inmuebles.datos_publicos(db, inspeccion["inmueble_id"])
    constancia = inspeccion["constancia"]
    return {
        "codigo": constancia["codigo"],
        "estado": constancia["estado"],
        "integra": crud_inspecciones.es_integra(inspeccion),
        "es_version_activa": inspeccion["es_version_activa"],
        "version": inspeccion["version"],
        "emitida_en": constancia["emitida_en"],
        "vigente_hasta": constancia["vigente_hasta"],
        "fecha_inspeccion": inspeccion["fecha_inspeccion"],
        "huella_sha256": inspeccion["firma"]["huella_sha256"],
        "perito": {
            "nombre_completo": usuario_perito["nombre_completo"],
            "profesion": perito["profesion"],
            "matricula_profesional": perito["matricula_profesional"],
        },
        "inmueble": inmueble,
        "aviso_legal": inspeccion["aviso_legal"],
    }


@router.post(
    "/interno/constancias/vencimientos",
    summary="Tarea diaria de n8n",
    description="RF-44, RF-56",
    dependencies=[Depends(requiere_servicio_n8n)],
)
def vencer_constancias(db: Database = Depends(get_db)):
    return crud_inspecciones.vencer_constancias(db)
