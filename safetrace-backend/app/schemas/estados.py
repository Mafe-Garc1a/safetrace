"""Modelos Pydantic de salida de G · Estados del inmueble (RF-38 a RF-47).

El estado describe la etapa del proceso de revisión, nunca la seguridad del inmueble (RNF-27, RNF-33).
"""

from datetime import datetime

from pydantic import BaseModel


class EstadoActual(BaseModel):
    codigo: int
    nombre: str
    desde: datetime
    version: int


class Referencia(BaseModel):
    tipo: str
    id: str


class HistorialEstadoOut(BaseModel):
    id: str
    inmueble_id: str
    estado_anterior: int
    estado_nuevo: int
    fecha: datetime
    causa: str
    referencia: Referencia | None = None
    producido_por: Referencia


class HistorialPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[HistorialEstadoOut]
