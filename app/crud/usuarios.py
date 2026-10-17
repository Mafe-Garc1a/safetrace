"""Acceso a datos y reglas de A · Cuentas y administración (RF-01 a RF-09).

Colecciones de las que es dueño: usuarios, sesiones, solicitudes_supresion.
Solo este archivo las escribe.

Reglas clave:
- La contraseña se guarda con hash y sal (RNF-09).
- La sesión vence a los 30 minutos sin actividad (RNF-11).
- Solo se piden los datos necesarios (RNF-17).
"""

from datetime import timedelta

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.crud import auditoria
from app.schemas.usuarios import UsuarioCreate
from core.config import settings
from core.fechas import ahora
from core.security import hash_contrasena

# El hash de la contraseña nunca sale de este archivo, salvo para el inicio de sesión
SIN_CONTRASENA = {"contrasena_hash": 0}


class CorreoDuplicado(Exception):
    """Ya existe una cuenta con ese correo."""


def crear_usuario(db: Database, usuario: UsuarioCreate, rol: str) -> dict:
    """Registro con consentimiento (RF-01, RF-07). El correo se guarda en minúsculas."""
    correo = usuario.correo.lower()
    if db["usuarios"].find_one({"correo": correo}, {"_id": 1}):
        raise CorreoDuplicado()
    momento = ahora()
    documento = {
        "correo": correo,
        "contrasena_hash": hash_contrasena(usuario.contrasena),
        "rol": rol,
        "nombre_completo": usuario.nombre_completo,
        "activo": True,
        "consentimiento": {
            "aceptado": True,
            "version_politica": usuario.version_politica,
            "fecha": momento,
        },
        "schema_version": 2,
        "creado_en": momento,
        "actualizado_en": momento,
    }
    try:
        resultado = db["usuarios"].insert_one(documento)
    except DuplicateKeyError:
        raise CorreoDuplicado() from None
    documento["_id"] = resultado.inserted_id
    actor = {"tipo": "USUARIO", "id": resultado.inserted_id, "rol": rol}
    auditoria.registrar(db, "usuarios", resultado.inserted_id, "REGISTRAR_USUARIO", actor, {"rol": rol})
    documento.pop("contrasena_hash")
    return documento


def obtener_usuario(db: Database, usuario_id: ObjectId) -> dict | None:
    """Datos básicos del usuario (sin contraseña). Lo usan todos."""
    return db["usuarios"].find_one({"_id": usuario_id}, SIN_CONTRASENA)


def obtener_usuario_por_correo(db: Database, correo: str) -> dict | None:
    """Usuario con su hash de contraseña, solo para el inicio de sesión (RF-02)."""
    return db["usuarios"].find_one({"correo": correo.lower()})


def obtener_hash_contrasena(db: Database, usuario_id: ObjectId) -> str | None:
    """Hash de la contraseña para confirmar la firma de una inspección (RF-52)."""
    usuario = db["usuarios"].find_one({"_id": usuario_id}, {"contrasena_hash": 1})
    return usuario["contrasena_hash"] if usuario else None


def listar_usuarios(db: Database, filtros: dict, saltar: int = 0, limite: int = 20) -> tuple[list[dict], int]:
    """Lista de usuarios para el administrador general (RF-04)."""
    total = db["usuarios"].count_documents(filtros)
    datos = list(db["usuarios"].find(filtros, SIN_CONTRASENA).sort("creado_en", -1).skip(saltar).limit(limite))
    return datos, total


def cambiar_activo(db: Database, usuario_id: ObjectId, activo: bool, actor: dict) -> dict | None:
    """Activa o desactiva una cuenta (RF-05). Al desactivarla se cierran sus sesiones."""
    anterior = db["usuarios"].find_one_and_update(
        {"_id": usuario_id},
        {"$set": {"activo": activo, "actualizado_en": ahora()}},
        projection=SIN_CONTRASENA,
    )
    if anterior is None:
        return None
    if not activo:
        db["sesiones"].delete_many({"usuario_id": usuario_id})
    auditoria.registrar(
        db, "usuarios", usuario_id, "CAMBIAR_ACTIVO", actor, {"anterior": anterior["activo"], "nuevo": activo}
    )
    return obtener_usuario(db, usuario_id)


def cambiar_rol(db: Database, usuario_id: ObjectId, rol: str, actor: dict) -> dict | None:
    """Cambia el rol (RF-06). Se cierran sus sesiones para que el nuevo rol aplique al volver a entrar."""
    anterior = db["usuarios"].find_one_and_update(
        {"_id": usuario_id},
        {"$set": {"rol": rol, "actualizado_en": ahora()}},
        projection=SIN_CONTRASENA,
    )
    if anterior is None:
        return None
    db["sesiones"].delete_many({"usuario_id": usuario_id})
    auditoria.registrar(db, "usuarios", usuario_id, "CAMBIAR_ROL", actor, {"anterior": anterior["rol"], "nuevo": rol})
    return obtener_usuario(db, usuario_id)


# --- Sesiones (RF-02, RF-03, RNF-11) -----------------------------------------


def crear_sesion(db: Database, usuario_id: ObjectId, token_hash: str) -> None:
    momento = ahora()
    db["sesiones"].insert_one(
        {
            "usuario_id": usuario_id,
            "token_hash": token_hash,
            "ultima_actividad": momento,
            "expira_en": momento + timedelta(minutes=settings.minutos_sesion),
        }
    )


def obtener_sesion_vigente(db: Database, token_hash: str) -> dict | None:
    """Sesión vigente por hash de token; extiende su vencimiento 30 min (RNF-11).

    Se filtra también por `expira_en` porque MongoDB borra las sesiones vencidas
    (índice TTL) cada minuto, no al instante.
    """
    momento = ahora()
    return db["sesiones"].find_one_and_update(
        {"token_hash": token_hash, "expira_en": {"$gt": momento}},
        {"$set": {"ultima_actividad": momento, "expira_en": momento + timedelta(minutes=settings.minutos_sesion)}},
        return_document=ReturnDocument.AFTER,
    )


def cerrar_sesion(db: Database, token_hash: str) -> bool:
    """Cerrar sesión borra el documento (RF-03)."""
    return db["sesiones"].delete_one({"token_hash": token_hash}).deleted_count > 0


def cerrar_sesiones_por_rol(db: Database, rol: str) -> int:
    """Cierra las sesiones de todos los usuarios del rol. Lo usa `crud/roles.py` al desactivar un rol."""
    ids = [u["_id"] for u in db["usuarios"].find({"rol": rol}, {"_id": 1})]
    if not ids:
        return 0
    return db["sesiones"].delete_many({"usuario_id": {"$in": ids}}).deleted_count


# --- Supresión de datos personales (RF-08, RF-09) ----------------------------


def solicitar_supresion(db: Database, usuario_id: ObjectId) -> dict:
    existente = db["solicitudes_supresion"].find_one({"usuario_id": usuario_id, "estado": "RECIBIDA"})
    if existente:
        return existente
    documento = {
        "usuario_id": usuario_id,
        "fecha_solicitud": ahora(),
        "estado": "RECIBIDA",
        "datos_eliminados": [],
        "datos_conservados": [],
        "atendida_por": None,
        "fecha_atencion": None,
    }
    documento["_id"] = db["solicitudes_supresion"].insert_one(documento).inserted_id
    return documento


def listar_solicitudes_supresion(db: Database, estado: str | None, saltar: int, limite: int) -> tuple[list, int]:
    filtros = {"estado": estado} if estado else {}
    total = db["solicitudes_supresion"].count_documents(filtros)
    datos = list(db["solicitudes_supresion"].find(filtros).sort("fecha_solicitud", 1).skip(saltar).limit(limite))
    return datos, total


def atender_supresion(db: Database, solicitud_id: ObjectId, actor: dict) -> dict | None:
    """Anonimiza la cuenta y deja constancia de lo que se conserva y por qué (RF-09)."""
    solicitud = db["solicitudes_supresion"].find_one({"_id": solicitud_id, "estado": "RECIBIDA"})
    if solicitud is None:
        return None
    usuario_id = solicitud["usuario_id"]
    db["usuarios"].update_one(
        {"_id": usuario_id},
        {
            "$set": {
                "nombre_completo": "Usuario suprimido",
                "correo": f"suprimido-{usuario_id}@safetrace.invalid",
                "contrasena_hash": hash_contrasena(ObjectId().binary.hex()),
                "activo": False,
                "actualizado_en": ahora(),
            }
        },
    )
    db["sesiones"].delete_many({"usuario_id": usuario_id})
    cambios = {
        "estado": "ATENDIDA",
        "datos_eliminados": ["nombre_completo", "correo"],
        "datos_conservados": [
            {"dato": "inmuebles, bitácora y evidencias", "motivo": "Historial del inmueble (RNF-12, RNF-16)"},
            {"dato": "inspecciones firmadas", "motivo": "Trazabilidad técnica (RNF-12)"},
            {"dato": "auditoría", "motivo": "Registro de seguridad (RNF-21)"},
        ],
        "atendida_por": actor["id"],
        "fecha_atencion": ahora(),
    }
    db["solicitudes_supresion"].update_one({"_id": solicitud_id}, {"$set": cambios})
    auditoria.registrar(db, "usuarios", usuario_id, "SUPRIMIR_DATOS", actor, {"solicitud_id": solicitud_id})
    return db["solicitudes_supresion"].find_one({"_id": solicitud_id})
