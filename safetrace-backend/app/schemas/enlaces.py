"""Modelos Pydantic de entrada y salida de I · Enlace público (RF-59 a RF-61).

El estado del inmueble no es un campo compartible (RNF-19).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CampoCompartido = Literal["LINEA_CRONOLOGICA", "FOTOS", "INSPECCIONES_FIRMADAS"]


class EnlaceCreate(BaseModel):
    campos_compartidos: list[CampoCompartido] = Field(min_length=1)


class EnlaceOut(BaseModel):
    id: str
    inmueble_id: str
    codigo: str
    campos_compartidos: list[CampoCompartido]
    activo: bool
    creado_por: str
    creado_en: datetime
    revocado_en: datetime | None = None
