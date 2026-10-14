"""Contraseñas y tokens de sesión (RNF-09, RNF-11)."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from core.config import settings


# Función para generar el hash de una contraseña (bcrypt con sal, RNF-09)
def hash_contrasena(contrasena: str) -> str:
    return bcrypt.hashpw(contrasena.encode(), bcrypt.gensalt(rounds=12)).decode()


# Función para verificar una contraseña contra su hash
def verificar_contrasena(contrasena: str, hash_guardado: str) -> bool:
    return bcrypt.checkpw(contrasena.encode(), hash_guardado.encode())


# Función para crear un token JWT. `jti` hace único cada token aunque se creen en el mismo segundo.
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(tz=UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    to_encode.update({"exp": expire, "jti": secrets.token_hex(8)})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# Función para verificar si un token JWT es válido. Devuelve el id del usuario o None.
def verify_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:  # firma inválida o token vencido
        return None


def hash_token(token: str) -> str:
    """Hash con el que se guarda y se busca la sesión: nunca se guarda el token (diseño 5.2)."""
    return hashlib.sha256(token.encode()).hexdigest()
