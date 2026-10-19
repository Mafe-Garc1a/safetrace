"""Acceso a datos y reglas de E · Revisión del propietario (RF-28 a RF-30).

Colecciones de las que es dueño: revisiones (y el campo `inmuebles.revision_semestral`).

Reglas clave:
- Solo pide el paso 2 → 3 si el inmueble está en el estado 2; si no, se guarda sin cambiar el estado.
- Sin cambios y sin inspección → pide el paso 3 → 1 (RF-43).
"""

from datetime import datetime

from bson import ObjectId
from pymongo.database import Database

from app.crud import auditoria
from app.crud import bitacora as crud_bitacora
from app.crud import estados as crud_estados
from app.crud import inmuebles as crud_inmuebles
from app.crud import notificaciones as crud_notificaciones
from app.crud.estados import EstadoInmueble as E
from app.schemas.revisiones import RevisionCreate
from core.fechas import ahora, sumar_meses

MESES_REVISION_SEMESTRAL = 6


def registrar_revision(db: Database, inmueble: dict, revision: RevisionCreate, usuario: dict) -> dict:
    """Guarda la revisión con sus fotos y pide los cambios de estado que correspondan (RF-28, RF-29, RF-40, RF-43)."""
    momento = ahora()
    marcado = inmueble["estado"]["codigo"] == E.MARCADO_POR_EVENTO_SISMICO
    documento = {
        "inmueble_id": inmueble["_id"],
        "fecha": momento,
        "observaciones": revision.observaciones,
        "hubo_cambios": revision.hubo_cambios,
        "solicitara_inspeccion": revision.solicitara_inspeccion,
        "evidencias_ids": [],
        "cambio_estado_aplicado": marcado,
        "registrada_por": usuario["_id"],
        "creado_en": momento,
    }
    documento["_id"] = db["revisiones"].insert_one(documento).inserted_id

    # Fotos: cada una es una evidencia con origen REVISION (D) y, si hay foto anterior de la zona, se compara (J)
    ids = [
        crud_bitacora.registrar_evidencia(db, inmueble["_id"], "REVISION", documento["_id"], foto, usuario)["_id"]
        for foto in revision.fotos
    ]
    if ids:
        db["revisiones"].update_one({"_id": documento["_id"]}, {"$set": {"evidencias_ids": ids}})
        documento["evidencias_ids"] = ids

    crud_inmuebles.escribir_revision_semestral(
        db, inmueble["_id"], momento, sumar_meses(momento, MESES_REVISION_SEMESTRAL)
    )

    if marcado:
        referencia = {"tipo": "REVISION", "id": documento["_id"]}
        producido_por = {"tipo": "USUARIO", "id": usuario["_id"]}
        crud_estados.pedir_transicion(
            db, inmueble["_id"], E.MARCADO_POR_EVENTO_SISMICO, E.REVISION_PROPIETARIO_REGISTRADA,
            "REVISION_REGISTRADA", referencia, producido_por,
        )  # fmt: skip
        if not revision.hubo_cambios and not revision.solicitara_inspeccion:
            crud_estados.pedir_transicion(
                db, inmueble["_id"], E.REVISION_PROPIETARIO_REGISTRADA, E.SIN_EVENTO_PENDIENTE,
                "SIN_CAMBIOS", referencia, producido_por,
            )  # fmt: skip

    auditoria.registrar(
        db, "revisiones", documento["_id"], "REGISTRAR_REVISION", auditoria.actor_usuario(usuario), {"fotos": len(ids)}
    )
    return documento


def listar_revisiones(db: Database, inmueble_id: ObjectId, saltar: int, limite: int) -> tuple[list[dict], int]:
    filtros = {"inmueble_id": inmueble_id}
    total = db["revisiones"].count_documents(filtros)
    datos = list(db["revisiones"].find(filtros).sort("fecha", -1).skip(saltar).limit(limite))
    return datos, total


def fecha_ultima_revision(db: Database, inmueble_id: ObjectId) -> datetime | None:
    """Fecha de la última revisión. La usa J."""
    ultima = db["revisiones"].find_one({"inmueble_id": inmueble_id}, {"fecha": 1}, sort=[("fecha", -1)])
    return ultima["fecha"] if ultima else None


def enviar_recordatorios(db: Database) -> int:
    """Tarea diaria de n8n: avisa a quien le llegó la revisión semestral (RF-30). Un aviso por periodo."""
    momento = ahora()
    enviados = 0
    for inmueble in crud_inmuebles.con_revision_vencida(db, momento):
        revision = inmueble.get("revision_semestral") or {}
        if revision.get("recordatorio_enviado_en"):
            continue
        crud_notificaciones.notificar(
            db, inmueble["propietario_id"], "RECORDATORIO_SEMESTRAL", {"tipo": "INMUEBLE", "id": inmueble["_id"]}
        )
        crud_inmuebles.marcar_recordatorio_enviado(db, inmueble["_id"], momento)
        enviados += 1
    return enviados
