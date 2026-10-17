"""Modelos Pydantic de salida de K · Notificaciones y procesos (RF-69 a RF-71)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.estados import Referencia


class TareaOut(BaseModel):
    """Estado de una operación en segundo plano (RF-71). No expone `datos`."""

    id: str
    tipo: str
    estado: Literal["PENDIENTE", "PROCESANDO", "COMPLETADA", "FALLIDA"]
    intentos: int
    max_intentos: int
    creado_en: datetime
    finalizada_en: datetime | None = None


class NotificacionOut(BaseModel):
    id: str
    tipo: str
    referencia: Referencia | None = None
    estado: Literal["PENDIENTE", "ENVIADA", "FALLIDA"]
    creado_en: datetime
    enviada_en: datetime | None = None


class NotificacionPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[NotificacionOut]
