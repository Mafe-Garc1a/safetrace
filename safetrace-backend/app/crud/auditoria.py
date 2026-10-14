"""Registro en la colección `auditoria` (RNF-16, RNF-21). Solo agregar.

Nunca guardar nombre, documento, correo ni teléfono en `cambios` (RNF-20).
"""

from pymongo.database import Database

from core.fechas import ahora


def actor_usuario(usuario: dict) -> dict:
    """Actor de auditoría a partir del usuario de la sesión."""
    return {"tipo": "USUARIO", "id": usuario["_id"], "rol": usuario["rol"]}


def actor_proceso(nombre: str) -> dict:
    """Actor de auditoría para procesos (n8n, trabajador)."""
    return {"tipo": "PROCESO", "id": nombre}


def registrar(
    db: Database, coleccion: str, documento_id, accion: str, actor: dict, cambios: dict | None = None, session=None
) -> None:
    db["auditoria"].insert_one(
        {
            "coleccion": coleccion,
            "documento_id": documento_id,
            "accion": accion,
            "actor": actor,
            "cambios": cambios or {},
            "fecha": ahora(),
        },
        session=session,
    )


def consultar(db: Database, filtros: dict, saltar: int = 0, limite: int = 20) -> tuple[list[dict], int]:
    """Registros de auditoría, del más reciente al más antiguo (RF-10)."""
    total = db["auditoria"].count_documents(filtros)
    datos = list(db["auditoria"].find(filtros).sort("fecha", -1).skip(saltar).limit(limite))
    return datos, total
