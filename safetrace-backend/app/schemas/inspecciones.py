"""Modelos Pydantic de entrada y salida de H · Inspecciones y constancias (RF-48 a RF-58)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.bitacora import ArchivoEntrada

EstadoSolicitud = Literal["SOLICITADA", "ASIGNADA", "FIRMADA", "CANCELADA"]


# --- Solicitudes --------------------------------------------------------------


class SolicitudCreate(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)
    tipo_inspeccion: Literal["POST_SISMO", "PREVENTIVA", "SEGUIMIENTO"] = "POST_SISMO"
    fecha_propuesta: datetime | None = None


class AsignacionCreate(BaseModel):
    perito_id: str


class CambioSolicitud(BaseModel):
    estado: EstadoSolicitud
    fecha: datetime


class SolicitudOut(BaseModel):
    id: str
    inmueble_id: str
    solicitada_por: str
    motivo: str
    tipo_inspeccion: str
    fecha_propuesta: datetime | None = None
    estado: EstadoSolicitud
    perito_id: str | None = None
    asignada_por: str | None = None
    cambios_estado: list[CambioSolicitud] = []
    creado_en: datetime


class SolicitudPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[SolicitudOut]


# --- Inspecciones -------------------------------------------------------------


class InspeccionBase(BaseModel):
    fecha_inspeccion: datetime
    motivo: str = Field(min_length=5, max_length=500)
    observaciones: str = Field(min_length=3, max_length=5000)
    hallazgos: str = Field(min_length=3, max_length=5000)
    resultado: str = Field(min_length=3, max_length=5000)


class InspeccionCreate(InspeccionBase):
    evidencias: list[ArchivoEntrada] = Field(default=[], max_length=30)


class InspeccionUpdate(BaseModel):
    """Solo antes de firmar."""

    fecha_inspeccion: datetime | None = None
    motivo: str | None = Field(default=None, min_length=5, max_length=500)
    observaciones: str | None = Field(default=None, min_length=3, max_length=5000)
    hallazgos: str | None = Field(default=None, min_length=3, max_length=5000)
    resultado: str | None = Field(default=None, min_length=3, max_length=5000)


class CorreccionCreate(InspeccionUpdate):
    evidencias: list[ArchivoEntrada] = Field(default=[], max_length=30)  # se suman a las de la versión anterior


class FirmaCreate(BaseModel):
    contrasena: str  # el perito firma confirmando su contraseña (RF-52)
    vigencia_meses: int = Field(default=6, ge=1, le=6)  # 6 o menos (RF-54, RF-55)


class Firma(BaseModel):
    firmada: bool
    fecha: datetime | None = None
    metodo: str | None = None
    huella_sha256: str | None = None


class Constancia(BaseModel):
    codigo: str
    emitida_en: datetime
    vigencia_meses: int
    vigente_hasta: datetime
    estado: Literal["VIGENTE", "VENCIDA"]


class InspeccionOut(InspeccionBase):
    id: str
    solicitud_id: str
    inmueble_id: str
    perito_id: str
    version: int
    version_anterior_id: str | None = None
    es_version_activa: bool
    evidencias_ids: list[str] = []
    firma: Firma
    constancia: Constancia | None = None
    aviso_legal: str
    creado_en: datetime


class PeritoPublico(BaseModel):
    nombre_completo: str
    profesion: str
    matricula_profesional: str


class VerificacionOut(BaseModel):
    """Lo que ve cualquiera que escanea el QR: sin datos personales del propietario."""

    codigo: str
    estado: Literal["VIGENTE", "VENCIDA"]
    integra: bool  # la huella recalculada coincide con la firmada (RF-58)
    es_version_activa: bool
    version: int
    emitida_en: datetime
    vigente_hasta: datetime
    fecha_inspeccion: datetime
    huella_sha256: str
    perito: PeritoPublico
    inmueble: dict
    aviso_legal: str
