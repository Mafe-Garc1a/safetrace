"""Pruebas sin servidor de MongoDB: la API usa una base en memoria (mongomock)."""

import os

os.environ["CREDENCIAL_SERVICIO_N8N"] = "credencial-de-prueba"
os.environ["ENTORNO"] = "pruebas"

import mongomock  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.crud import inmuebles as crud_inmuebles  # noqa: E402
from app.crud.sismos import distancia_km  # noqa: E402
from core.database import get_db  # noqa: E402
from core.fechas import ahora  # noqa: E402
from core.security import hash_contrasena  # noqa: E402
from db import indices, semillas  # noqa: E402
from main import app  # noqa: E402

CONTRASENA = "Contrasena-segura-1"
N8N = {"X-Credencial-Servicio": "credencial-de-prueba"}


@pytest.fixture
def db(monkeypatch):
    base = mongomock.MongoClient(tz_aware=True)["safetrace_pruebas"]
    indices.crear(base)
    semillas.cargar(base)

    # mongomock no soporta $geoWithin: se filtra en Python con la misma distancia
    def buscar_en_radio(db, longitud, latitud, radio_km):
        return [
            i
            for i in db["inmuebles"].find({}, {"propietario_id": 1, "ubicacion": 1, "estado": 1})
            if distancia_km(longitud, latitud, *i["ubicacion"]["coordinates"]) <= radio_km
        ]

    monkeypatch.setattr(crud_inmuebles, "buscar_en_radio", buscar_en_radio)
    return base


@pytest.fixture
def cliente(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def registrar(cliente, correo: str, rol: str = "PROPIETARIO") -> dict:
    datos = {
        "nombre_completo": "Persona de Prueba",
        "correo": correo,
        "contrasena": CONTRASENA,
        "rol": rol,
        "acepta_politica": True,
    }
    r = cliente.post("/auth/registro", json=datos)
    assert r.status_code == 201, r.text
    return r.json()


def iniciar_sesion(cliente, correo: str) -> dict:
    r = cliente.post("/auth/sesion", data={"username": correo, "password": CONTRASENA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def crear_usuario_directo(db, correo: str, rol: str) -> None:
    """Inserta un usuario sin pasar por el registro (los administradores no se registran solos)."""
    momento = ahora()
    db["usuarios"].insert_one(
        {
            "correo": correo,
            "contrasena_hash": hash_contrasena(CONTRASENA),
            "rol": rol,
            "nombre_completo": "Administrador",
            "activo": True,
            "consentimiento": {"aceptado": True, "version_politica": "v1.0", "fecha": momento},
            "creado_en": momento,
            "actualizado_en": momento,
        }
    )


@pytest.fixture
def admin(cliente, db):
    crear_usuario_directo(db, "admin@safetrace.co", "ADMINISTRADOR_GENERAL")
    return iniciar_sesion(cliente, "admin@safetrace.co")


@pytest.fixture
def superadmin(cliente, db):
    crear_usuario_directo(db, "super@safetrace.co", "SUPERADMIN")
    return iniciar_sesion(cliente, "super@safetrace.co")


@pytest.fixture
def propietario(cliente):
    registrar(cliente, "ana@correo.com")
    return iniciar_sesion(cliente, "ana@correo.com")


@pytest.fixture
def inmueble(cliente, propietario) -> dict:
    datos = {
        "tipo_inmueble": "APARTAMENTO",
        "direccion": "Calle 14 #23-45 Apto 502",
        "ciudad": "Pereira",
        "anio_construccion": 1998,
        "sistema_constructivo": "MAMPOSTERIA_CONFINADA",
        "numero_pisos": 5,
        "longitud": -75.69611,
        "latitud": 4.81333,
    }
    r = cliente.post("/inmuebles", json=datos, headers=propietario)
    assert r.status_code == 201, r.text
    return r.json()
