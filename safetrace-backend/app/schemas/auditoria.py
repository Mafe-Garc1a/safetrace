"""Modelos Pydantic de salida de A · Cuentas: consulta de auditoría (RF-10)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Actor(BaseModel):
    tipo: str  # USUARIO | PROCESO
    id: str
    rol: str | None = None


class AuditoriaOut(BaseModel):
    id: str
    coleccion: str
    documento_id: str
    accion: str
    actor: Actor
    cambios: dict[str, Any] = {}
    fecha: datetime


class AuditoriaPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[AuditoriaOut]
