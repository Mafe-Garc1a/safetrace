"""Rutas de A · Cuentas: registro e inicio/cierre de sesión (RF-01 a RF-03, RF-07)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pymongo.database import Database

from app.crud import usuarios as crud_usuarios
from app.router.dependencies import authenticate_user, get_current_user, oauth2_scheme
from app.schemas.auth import ResponseLoggin
from app.schemas.usuarios import UsuarioCreate, UsuarioOut
from core.config import settings
from core.database import get_db, serializar
from core.security import create_access_token, hash_token

router = APIRouter()


@router.post(
    "/registro",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registro con correo, contraseña y consentimiento de datos",
    description="RF-01, RF-07",
)
def registrar_usuario(usuario: UsuarioCreate, db: Database = Depends(get_db)):
    if not usuario.acepta_politica:
        raise HTTPException(status_code=400, detail="Debe aceptar la política de tratamiento de datos")
    try:
        creado = crud_usuarios.crear_usuario(db, usuario, usuario.rol)
    except crud_usuarios.CorreoDuplicado:
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo") from None
    return serializar(creado)


@router.post(
    "/sesion",
    response_model=ResponseLoggin,
    summary="Inicio de sesión (en `username` va el correo)",
    description="RF-02",
)
def iniciar_sesion(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Database = Depends(get_db)):
    usuario = authenticate_user(form_data.username, form_data.password, db)
    if not usuario:
        raise HTTPException(
            status_code=401,
            detail="Datos incorrectos en correo o contraseña",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario["activo"]:
        raise HTTPException(status_code=403, detail="Usuario inactivo. No autorizado")

    data = {"sub": str(usuario["_id"]), "rol": usuario["rol"]}
    access_token = create_access_token(data)
    crud_usuarios.crear_sesion(db, usuario["_id"], hash_token(access_token))

    usuario.pop("contrasena_hash")
    return ResponseLoggin(
        usuario=serializar(usuario),
        access_token=access_token,
        minutos_inactividad=settings.minutos_sesion,
    )


@router.delete(
    "/sesion",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cierre de sesión",
    description="RF-03",
)
def cerrar_sesion(
    token: str = Depends(oauth2_scheme),
    _: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    crud_usuarios.cerrar_sesion(db, hash_token(token))


@router.get("/yo", response_model=UsuarioOut, summary="Usuario de la sesión actual")
def usuario_actual(usuario: dict = Depends(get_current_user)):
    return serializar(usuario)
