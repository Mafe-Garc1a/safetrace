"""Punto de entrada de la API: crea FastAPI y registra los routers.

Ejecutar en local:  uvicorn main:app --reload
Documentación interactiva: http://localhost:8000/docs
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.router import (
    auditoria,
    auth,
    bitacora,
    configuracion,
    enlaces,
    estados,
    ia_indice,
    inmuebles,
    inspecciones,
    notificaciones,
    peritos,
    revisiones,
    sismos,
    usuarios,
)
from core.config import settings
from core.errores import TransicionRechazada
from core.registro import obtener_logger

log = obtener_logger("api")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=settings.PROJECT_DESCRIPTION,
)

# Incluir en el objeto app los routers
app.include_router(auth.router, prefix="/auth", tags=["Acceso"])
app.include_router(usuarios.router, tags=["Usuarios"])
app.include_router(auditoria.router, tags=["Auditoría"])
app.include_router(configuracion.router, tags=["Configuración"])
app.include_router(peritos.router, tags=["Peritos"])
app.include_router(inmuebles.router, tags=["Inmuebles"])
app.include_router(bitacora.router, tags=["Bitácora y evidencias"])
app.include_router(revisiones.router, tags=["Revisión del propietario"])
app.include_router(sismos.router, tags=["Sismos"])
app.include_router(estados.router, tags=["Estados del inmueble"])
app.include_router(inspecciones.router, tags=["Inspecciones y constancias"])
app.include_router(enlaces.router, tags=["Enlace público"])
app.include_router(ia_indice.router, tags=["IA e índice de priorización"])
app.include_router(notificaciones.router, tags=["Notificaciones y procesos"])

# Configuración de CORS para permitir todas las solicitudes desde cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permitir solicitudes desde cualquier origen
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],  # Permitir estos métodos HTTP
    allow_headers=["*"],  # Permitir cualquier encabezado en las solicitudes
)


# Errores comunes: se responden igual en todos los routers y sin filtrar detalles internos
@app.exception_handler(TransicionRechazada)
def transicion_rechazada(_: Request, exc: TransicionRechazada):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(PyMongoError)
def error_base_datos(_: Request, exc: PyMongoError):
    log.error("Error de base de datos: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Error de base de datos"})


@app.get("/", tags=["Sistema"])
def read_root():
    return {"message": "ok", "proyecto": settings.PROJECT_NAME, "version": settings.PROJECT_VERSION}


@app.get("/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok"}
