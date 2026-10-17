"""Modelos Pydantic de entrada y salida de A · Cuentas: registro e inicio de sesión."""

from pydantic import BaseModel

from app.schemas.usuarios import UsuarioOut


class ResponseLoggin(BaseModel):
    usuario: UsuarioOut
    access_token: str
    token_type: str = "bearer"
    minutos_inactividad: int
