"""Modelos Pydantic de entrada y salida de los módulos (como en avisena).

El nombre del módulo es su identificador: cada router lo declara en su variable `modulo`.
"""

from pydantic import BaseModel, Field

PATRON_MODULO = r"^[a-z][a-z_]{2,39}$"  # p. ej. inmuebles, validacion_peritos


class ModuloBase(BaseModel):
    nombre_modulo: str = Field(pattern=PATRON_MODULO)
    descripcion: str = Field(min_length=3, max_length=200)
    estado: bool = True


class ModuloCreate(ModuloBase):
    pass


class ModuloUpdate(BaseModel):
    # El nombre no se cambia: los routers lo usan en el código
    descripcion: str | None = Field(default=None, min_length=3, max_length=200)


class ModuloEstado(BaseModel):
    estado: bool


class ModuloOut(ModuloBase):
    id: str
