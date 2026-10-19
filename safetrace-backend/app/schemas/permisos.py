"""Modelos Pydantic de entrada y salida de los permisos por rol y módulo (como en avisena)."""

from typing import Literal

from pydantic import BaseModel

Accion = Literal["insertar", "actualizar", "seleccionar", "borrar"]


class PermisoBase(BaseModel):
    modulo: str
    rol: str
    insertar: bool = False
    actualizar: bool = False
    seleccionar: bool = False
    borrar: bool = False


class PermisoCreate(PermisoBase):
    pass


class PermisoUpdate(BaseModel):
    insertar: bool | None = None
    actualizar: bool | None = None
    seleccionar: bool | None = None
    borrar: bool | None = None


class PermisoOut(PermisoBase):
    id: str
