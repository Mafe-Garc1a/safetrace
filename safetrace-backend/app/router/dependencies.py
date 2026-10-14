"""Dependencias compartidas por los routers: usuario actual y permisos (RNF-08, RNF-10).

Uso en una ruta:
    @router.get("/inmuebles")
    def listar(usuario: dict = Depends(requiere_rol("PROPIETARIO")), db: Database = Depends(get_db)):
"""

import secrets

from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pymongo.database import Database

from app.crud import inmuebles as crud_inmuebles
from app.crud import inspecciones as crud_inspecciones
from app.crud.usuarios import obtener_sesion_vigente, obtener_usuario, obtener_usuario_por_correo
from core.config import settings
from core.database import a_object_id, get_db
from core.security import hash_token, verificar_contrasena, verify_token

ROLES = ("PROPIETARIO", "PERITO", "ADMINISTRADOR_GENERAL")
ADMIN = "ADMINISTRADOR_GENERAL"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/sesion")


def get_current_user(token: str = Depends(oauth2_scheme), db: Database = Depends(get_db)) -> dict:
    """Valida el token, busca la sesión vigente y extiende su vencimiento 30 min (RNF-11)."""
    usuario_id = verify_token(token)
    if usuario_id is None:
        raise HTTPException(status_code=401, detail="Token inválido", headers={"WWW-Authenticate": "Bearer"})
    sesion = obtener_sesion_vigente(db, hash_token(token))
    if sesion is None:
        raise HTTPException(status_code=401, detail="Sesión cerrada o vencida", headers={"WWW-Authenticate": "Bearer"})
    usuario = obtener_usuario(db, sesion["usuario_id"])
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not usuario["activo"]:
        raise HTTPException(status_code=403, detail="Usuario inactivo. No autorizado")
    return usuario


def authenticate_user(correo: str, contrasena: str, db: Database) -> dict | None:
    usuario = obtener_usuario_por_correo(db, correo)
    if not usuario:
        return None
    if not verificar_contrasena(contrasena, usuario["contrasena_hash"]):
        return None
    return usuario


def requiere_rol(*roles: str):
    """Permite la ruta solo a los roles indicados (RNF-08)."""

    def _verificar(usuario: dict = Depends(get_current_user)) -> dict:
        if usuario["rol"] not in roles:
            raise HTTPException(status_code=403, detail="Sin permiso para esta acción")
        return usuario

    return _verificar


def requiere_servicio_n8n(x_credencial_servicio: str = Header(...)) -> None:
    """Valida la credencial de servicio de n8n en las rutas /interno/*."""
    if not secrets.compare_digest(x_credencial_servicio, settings.credencial_servicio_n8n):
        raise HTTPException(status_code=401, detail="Credencial de servicio inválida")


def obtener_inmueble_autorizado(db: Database, inmueble_id: str, usuario: dict, solo_propietario: bool = False) -> dict:
    """Devuelve el inmueble si el usuario puede verlo (RNF-10).

    - El propietario ve y modifica los suyos.
    - El administrador general y el perito asignado solo consultan (solo_propietario=False).
      El administrador no modifica historial, evidencias ni inspecciones (RNF-12).
    """
    inmueble = crud_inmuebles.obtener_inmueble(db, a_object_id(inmueble_id))
    if inmueble is None:
        raise HTTPException(status_code=404, detail="Inmueble no encontrado")
    if inmueble["propietario_id"] == usuario["_id"]:
        return inmueble
    if not solo_propietario:
        if usuario["rol"] == ADMIN:
            return inmueble
        if usuario["rol"] == "PERITO" and crud_inspecciones.perito_asignado_a_inmueble(
            db, inmueble["_id"], usuario["_id"]
        ):
            return inmueble
    raise HTTPException(status_code=403, detail="Sin permiso sobre este inmueble")
