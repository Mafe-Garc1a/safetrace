"""Modelos Pydantic de entrada y salida de A · Cuentas: usuarios y supresión de datos.

Nombres en español y en snake_case, igual que los campos de MongoDB (Diseño DataBase V2).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.roles import PATRON_ROL

# Los roles válidos están en la colección `roles` (PROPIETARIO, PERITO, ADMINISTRADOR_GENERAL, SUPERADMIN, ...)
Rol = str


class Consentimiento(BaseModel):
    aceptado: bool
    version_politica: str
    fecha: datetime


class UsuarioBase(BaseModel):
    nombre_completo: str = Field(min_length=3, max_length=100)
    correo: EmailStr


class UsuarioCreate(UsuarioBase):
    """Datos mínimos (RNF-17): sin teléfono ni documento; el documento solo lo da el perito."""

    contrasena: str = Field(min_length=8, max_length=72)
    rol: Literal["PROPIETARIO", "PERITO"] = "PROPIETARIO"  # el administrador general no se registra solo
    acepta_politica: bool  # consentimiento de tratamiento de datos (RF-07, Ley 1581 de 2012)
    version_politica: str = "v1.0"


class UsuarioOut(UsuarioBase):
    id: str
    rol: Rol
    activo: bool
    consentimiento: Consentimiento | None = None
    creado_en: datetime


class UsuarioPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[UsuarioOut]


class UsuarioEstado(BaseModel):
    activo: bool


class UsuarioRol(BaseModel):
    rol: str = Field(pattern=PATRON_ROL)  # debe existir y estar activo en `roles`


class DatoConservado(BaseModel):
    dato: str
    motivo: str


class SolicitudSupresionOut(BaseModel):
    id: str
    usuario_id: str
    fecha_solicitud: datetime
    estado: Literal["RECIBIDA", "ATENDIDA"]
    datos_eliminados: list[str] = []
    datos_conservados: list[DatoConservado] = []
    atendida_por: str | None = None
    fecha_atencion: datetime | None = None
