"""Modelos Pydantic de entrada y salida de B · Peritos (RF-13 a RF-16)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

EstadoCredencial = Literal["REGISTRADO", "PENDIENTE_VALIDACION", "VALIDADO", "RECHAZADO", "VENCIDO", "INCONSISTENTE"]


class Archivo(BaseModel):
    """Referencia a un archivo ya subido al proveedor: la base guarda solo la ruta y la huella."""

    ruta: str = Field(min_length=3, max_length=300)
    hash_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DocumentoIdentidad(BaseModel):
    tipo: Literal["CC", "CE", "PA", "PPT"]
    numero: str = Field(min_length=5, max_length=20)


class PeritoBase(BaseModel):
    documento: DocumentoIdentidad
    profesion: str = Field(min_length=3, max_length=100)
    especialidad: str | None = Field(default=None, max_length=100)
    matricula_profesional: str = Field(min_length=3, max_length=40)
    vigencia_matricula: datetime | None = None  # si la tarjeta profesional tiene vencimiento


class PeritoCreate(PeritoBase):
    pass


class DocumentoEntrada(BaseModel):
    tipo: Literal["MATRICULA", "TITULO", "CEDULA", "OTRO"]
    archivo: Archivo


class DocumentosCreate(BaseModel):
    documentos: list[DocumentoEntrada] = Field(min_length=1, max_length=10)


class DocumentoPerito(BaseModel):
    documento_id: str
    tipo: str
    archivo: Archivo
    cargado_en: datetime


class Validacion(BaseModel):
    decision: Literal["APROBADO", "RECHAZADO", "INCONSISTENTE"]
    motivo: str | None = None
    validado_por: str
    fecha: datetime
    documentos_revisados: list[str] = []


class ValidacionCreate(BaseModel):
    decision: Literal["APROBADO", "RECHAZADO"]
    motivo: str | None = Field(default=None, max_length=500)
    documentos_revisados: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def motivo_si_rechaza(self):
        if self.decision == "RECHAZADO" and not self.motivo:
            raise ValueError("El rechazo debe indicar el motivo")
        return self


class InconsistenciaCreate(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


class PeritoOut(PeritoBase):
    id: str
    usuario_id: str
    estado_credencial: EstadoCredencial
    documentos: list[DocumentoPerito] = []
    validaciones: list[Validacion] = []
    creado_en: datetime
    actualizado_en: datetime
