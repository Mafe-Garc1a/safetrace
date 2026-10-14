"""Modelos Pydantic de entrada y salida de F · Sismos (RF-31 a RF-37)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.inmuebles import Ubicacion

Fuente = Literal["SGC", "USGS"]


class SismoCreate(BaseModel):
    """Lo que entrega n8n desde el feed del SGC o del USGS."""

    fuente: Fuente
    id_externo: str = Field(min_length=1, max_length=60)
    fecha_hora: datetime
    magnitud: float = Field(ge=0, le=10)
    profundidad_km: float = Field(ge=0, le=800)
    longitud: float = Field(ge=-180, le=180)
    latitud: float = Field(ge=-90, le=90)


class FuenteSismo(BaseModel):
    fuente: Fuente
    id_externo: str
    magnitud: float


class SismoOut(BaseModel):
    id: str
    fecha_hora: datetime
    magnitud: float
    profundidad_km: float
    epicentro: Ubicacion
    fuentes: list[FuenteSismo]
    es_relevante: bool
    inmuebles_marcados: int
    recibido_en: datetime


class SismoRecibido(BaseModel):
    sismo: SismoOut
    resultado: Literal["NUEVO", "FUENTE_AGREGADA", "DUPLICADO"]


class SismoPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[SismoOut]
