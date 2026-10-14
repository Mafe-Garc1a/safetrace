"""Modelos Pydantic de entrada y salida de A · Cuentas: configuración de sismos (RF-11, RF-12)."""

from datetime import datetime

from pydantic import BaseModel, Field


class ConfiguracionBase(BaseModel):
    magnitud_minima: float = Field(ge=0, le=10)
    radio_afectacion_km: float = Field(gt=0, le=2000)


class ConfiguracionUpdate(ConfiguracionBase):
    pass


class ConfiguracionOut(ConfiguracionBase):
    actualizado_por: str | None = None
    actualizado_en: datetime | None = None
