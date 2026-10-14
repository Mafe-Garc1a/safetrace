"""Modelos Pydantic de entrada y salida de E · Revisión del propietario (RF-28 a RF-30)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.bitacora import ArchivoEntrada


class RevisionBase(BaseModel):
    observaciones: str = Field(min_length=3, max_length=2000)
    hubo_cambios: bool
    solicitara_inspeccion: bool


class RevisionCreate(RevisionBase):
    fotos: list[ArchivoEntrada] = Field(default=[], max_length=20)  # archivos ya subidos al proveedor


class RevisionOut(RevisionBase):
    id: str
    inmueble_id: str
    fecha: datetime
    evidencias_ids: list[str] = []
    cambio_estado_aplicado: bool
    registrada_por: str
    creado_en: datetime


class RevisionPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[RevisionOut]
