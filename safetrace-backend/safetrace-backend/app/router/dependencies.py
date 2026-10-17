"""Dependencias compartidas por los routers: usuario actual y permisos (RNF-08, RNF-10).

Los permisos siguen el esquema de avisena: cada router declara su `modulo` y cada ruta pide
una acción (insertar, actualizar, seleccionar o borrar), que se busca en la colección `permisos`
para el rol del usuario.

Uso en una ruta:
    modulo = "inmuebles"

    @router.post("/inmuebles")
    def registrar(usuario: dict = Depends(requiere_permiso(modulo, "insertar")), db: Database = Depends(get_db)):
"""

import secrets

from fastapi import Depends, Header, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pymongo.database import Database

from app.crud import inmuebles as crud_inmuebles
from app.crud import inspecciones as crud_inspecciones
from app.crud.permisos import verificar_permisos
from app.crud.usuarios import obtener_sesion_vigente, obtener_usuario, obtener_usuario_por_correo
from core.config import settings
from core.database import a_object_id, get_db
from core.security import hash_token, verificar_contrasena, verify_token

# Permiso para ver todos los inmuebles y su información en solo lectura (administrador y superadmin)
MODULO_SUPERVISION = "supervision_inmuebles"

# Módulos que usa el código; una prueba comprueba que todos existan en `db/semillas.py`
MODULOS_USADOS: set[str] = {MODULO_SUPERVISION}

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


def requiere_permiso(modulo: str, accion: str):
    """Permite la ruta solo si el rol del usuario tiene la acción sobre el módulo (RNF-08)."""
    MODULOS_USADOS.add(modulo)

    def _verificar(usuario: dict = Depends(get_current_user), db: Database = Depends(get_db)) -> dict:
        if not verificar_permisos(db, usuario["rol"], modulo, accion):
            raise HTTPException(status_code=403, detail="Sin permiso para esta acción")
        return usuario

    return _verificar


def requiere_servicio_n8n(x_credencial_servicio: str = Header(...)) -> None:
    """Valida la credencial de servicio de n8n en las rutas /interno/*."""
    if not secrets.compare_digest(x_credencial_servicio, settings.credencial_servicio_n8n):
        raise HTTPException(status_code=401, detail="Credencial de servicio inválida")


def puede_supervisar(db: Database, usuario: dict) -> bool:
    """True si el rol puede ver todos los inmuebles (administrador general y superadmin)."""
    return verificar_permisos(db, usuario["rol"], MODULO_SUPERVISION, "seleccionar")


def obtener_inmueble_autorizado(db: Database, inmueble_id: str, usuario: dict, solo_propietario: bool = False) -> dict:
    """Devuelve el inmueble si el usuario puede verlo (RNF-10).

    - El propietario ve y modifica los suyos.
    - Quien tiene permiso de supervisión y el perito asignado solo consultan (solo_propietario=False).
      El administrador no modifica historial, evidencias ni inspecciones (RNF-12).
    """
    inmueble = crud_inmuebles.obtener_inmueble(db, a_object_id(inmueble_id))
    if inmueble is None:
        raise HTTPException(status_code=404, detail="Inmueble no encontrado")
    if inmueble["propietario_id"] == usuario["_id"]:
        return inmueble
    if not solo_propietario:
        if puede_supervisar(db, usuario):
            return inmueble
        if usuario["rol"] == "PERITO" and crud_inspecciones.perito_asignado_a_inmueble(
            db, inmueble["_id"], usuario["_id"]
        ):
            return inmueble
    raise HTTPException(status_code=403, detail="Sin permiso sobre este inmueble")
