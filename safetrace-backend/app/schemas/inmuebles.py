"""Modelos Pydantic de entrada y salida de C · Inmuebles y zonas (RF-17 a RF-21, RF-23)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.estados import EstadoActual

TipoInmueble = Literal["CASA", "APARTAMENTO", "LOCAL", "OFICINA"]
SistemaConstructivo = Literal[
    "MAMPOSTERIA_CONFINADA",
    "MAMPOSTERIA_NO_REFORZADA",
    "MAMPOSTERIA_REFORZADA",
    "PORTICOS_CONCRETO",
    "MUROS_CONCRETO",
    "ESTRUCTURA_METALICA",
    "BAHAREQUE",
    "TAPIA_ADOBE",
    "MADERA",
    "OTRO",
]


class InmuebleBase(BaseModel):
    tipo_inmueble: TipoInmueble
    direccion: str = Field(min_length=5, max_length=150)
    ciudad: str = Field(min_length=2, max_length=60)
    matricula_inmobiliaria: str | None = Field(default=None, max_length=30)  # null si no aplica
    anio_construccion: int = Field(ge=1800, le=2100)
    sistema_constructivo: SistemaConstructivo
    numero_pisos: int = Field(ge=1, le=200)


class InmuebleCreate(InmuebleBase):
    # Se reciben por separado y se guardan en GeoJSON como [longitud, latitud]
    longitud: float = Field(ge=-180, le=180)
    latitud: float = Field(ge=-90, le=90)


class InmuebleUpdate(BaseModel):
    tipo_inmueble: TipoInmueble | None = None
    direccion: str | None = Field(default=None, min_length=5, max_length=150)
    ciudad: str | None = Field(default=None, min_length=2, max_length=60)
    matricula_inmobiliaria: str | None = Field(default=None, max_length=30)
    anio_construccion: int | None = Field(default=None, ge=1800, le=2100)
    sistema_constructivo: SistemaConstructivo | None = None
    numero_pisos: int | None = Field(default=None, ge=1, le=200)
    longitud: float | None = Field(default=None, ge=-180, le=180)
    latitud: float | None = Field(default=None, ge=-90, le=90)

    @model_validator(mode="after")
    def coordenadas_juntas(self):
        if (self.longitud is None) != (self.latitud is None):
            raise ValueError("Envíe longitud y latitud juntas")
        return self


class Ubicacion(BaseModel):
    type: Literal["Point"]
    coordinates: list[float]  # [longitud, latitud]


class UltimoIndice(BaseModel):
    valor: float
    sismo_id: str
    calculado_en: datetime


class RevisionSemestral(BaseModel):
    ultima: datetime | None = None
    proxima: datetime | None = None


class UltimoEvento(BaseModel):
    evento_id: str
    tipo: str
    fecha: datetime
    resumen: str


class InmuebleOut(InmuebleBase):
    id: str
    propietario_id: str
    ubicacion: Ubicacion
    fecha_registro: datetime
    estado: EstadoActual
    ultimo_indice: UltimoIndice | None = None
    revision_semestral: RevisionSemestral | None = None
    ultimos_eventos: list[UltimoEvento] = []
    creado_en: datetime
    actualizado_en: datetime


class InmueblePage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[InmuebleOut]


class ZonaOut(BaseModel):
    id: str
    nombre: str
    grupo: str
