"""Modelos Pydantic de salida de J · Análisis de IA e índice de priorización (RF-62 a RF-68)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ResultadoAnalisis(BaseModel):
    cambio_detectado: bool
    descripcion: str
    confianza: float


class AnalisisOut(BaseModel):
    id: str
    inmueble_id: str
    zona_id: str
    evidencia_anterior_id: str
    evidencia_nueva_id: str
    estado: Literal["PENDIENTE", "PROCESANDO", "COMPLETADO", "FALLIDO", "REEMPLAZADO"]
    tarea_id: str | None = None
    resultado: ResultadoAnalisis | None = None
    leyenda: str  # «Análisis automático mediante IA» (RF-65)
    modelo_version: str
    completado_en: datetime | None = None
    creado_en: datetime


class AnalisisPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[AnalisisOut]


class IndiceOut(BaseModel):
    id: str
    inmueble_id: str
    sismo_id: str
    valor: float
    variables: dict[str, Any]  # tal como se usaron (RF-67)
    aviso: str  # orientativo, no es evaluación profesional (RF-68)
    formula_version: str
    calculado_en: datetime


class IndicePage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[IndiceOut]
