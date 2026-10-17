"""Modelos Pydantic de entrada y salida de los roles (como en avisena).

El nombre del rol es su identificador: se guarda como `_id` en `roles` y como `rol` en `usuarios`.
"""

from pydantic import BaseModel, Field

PATRON_ROL = r"^[A-Z][A-Z_]{2,29}$"  # p. ej. PROPIETARIO, ADMINISTRADOR_GENERAL


class RolBase(BaseModel):
    nombre_rol: str = Field(pattern=PATRON_ROL)
    descripcion: str = Field(min_length=3, max_length=500)
    estado: bool = True


class RolCreate(RolBase):
    pass


class RolUpdate(BaseModel):
    # El nombre no se cambia: los usuarios lo tienen guardado en `usuarios.rol`
    descripcion: str | None = Field(default=None, min_length=3, max_length=500)


class RolEstado(BaseModel):
    estado: bool


class RolOut(RolBase):
    id: str


class RolPage(BaseModel):
    pagina: int
    tamano: int
    total: int
    total_paginas: int
    datos: list[RolOut]
