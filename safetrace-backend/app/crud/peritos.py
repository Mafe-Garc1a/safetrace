"""Acceso a datos y reglas de B · Peritos (RF-13 a RF-16).

Colecciones de las que es dueño: peritos.

Reglas clave:
- Cada validación agrega un elemento a `validaciones` (quién, cuándo, documentos revisados).
- Solo VALIDADO habilita al perito (RNF-15).
"""

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.crud import auditoria
from app.schemas.peritos import DocumentoEntrada, PeritoCreate
from core.fechas import ahora


class PerfilDuplicado(Exception):
    """El usuario ya tiene perfil o la matrícula ya está registrada."""


class EstadoNoPermitido(Exception):
    """La acción no aplica en el estado actual de la credencial."""


def crear_perfil(db: Database, usuario_id: ObjectId, perfil: PeritoCreate) -> dict:
    """Perfil profesional del usuario con rol PERITO (RF-13). Empieza en REGISTRADO."""
    if db["peritos"].find_one(
        {"$or": [{"usuario_id": usuario_id}, {"matricula_profesional": perfil.matricula_profesional}]}
    ):
        raise PerfilDuplicado()
    momento = ahora()
    documento = {
        "usuario_id": usuario_id,
        **perfil.model_dump(),
        "estado_credencial": "REGISTRADO",
        "documentos": [],
        "validaciones": [],
        "schema_version": 2,
        "creado_en": momento,
        "actualizado_en": momento,
    }
    try:
        documento["_id"] = db["peritos"].insert_one(documento).inserted_id
    except DuplicateKeyError:
        raise PerfilDuplicado() from None
    return documento


def obtener_por_usuario(db: Database, usuario_id: ObjectId) -> dict | None:
    return db["peritos"].find_one({"usuario_id": usuario_id})


def obtener_perito(db: Database, perito_id: ObjectId) -> dict | None:
    return db["peritos"].find_one({"_id": perito_id})


def agregar_documentos(db: Database, perito: dict, documentos: list[DocumentoEntrada]) -> dict:
    """Registra documentos ya subidos (RF-14) y deja la credencial pendiente de validación."""
    momento = ahora()
    siguiente = len(perito.get("documentos", [])) + 1
    nuevos = [
        {
            "documento_id": f"DOC-{siguiente + i}",
            "tipo": d.tipo,
            "archivo": d.archivo.model_dump(),
            "cargado_en": momento,
        }
        for i, d in enumerate(documentos)
    ]
    cambios = {"actualizado_en": momento}
    if perito["estado_credencial"] != "VALIDADO":
        cambios["estado_credencial"] = "PENDIENTE_VALIDACION"
    return db["peritos"].find_one_and_update(
        {"_id": perito["_id"]},
        {"$push": {"documentos": {"$each": nuevos}}, "$set": cambios},
        return_document=ReturnDocument.AFTER,
    )


def listar_por_estado(db: Database, estado: str | None, saltar: int, limite: int) -> tuple[list[dict], int]:
    """Lista para el administrador, por ejemplo los pendientes (RF-15)."""
    filtros = {"estado_credencial": estado} if estado else {}
    total = db["peritos"].count_documents(filtros)
    datos = list(db["peritos"].find(filtros).sort("actualizado_en", 1).skip(saltar).limit(limite))
    return datos, total


def validar(db: Database, perito_id: ObjectId, decision: str, motivo, documentos_revisados: list[str], actor: dict):
    """Aprobar o rechazar (RF-15, RF-16). `validaciones` solo crece."""
    perito = obtener_perito(db, perito_id)
    if perito is None:
        return None
    if perito["estado_credencial"] not in ("PENDIENTE_VALIDACION", "INCONSISTENTE", "VENCIDO"):
        raise EstadoNoPermitido(f"La credencial está en {perito['estado_credencial']}")
    existentes = {d["documento_id"] for d in perito.get("documentos", [])}
    faltantes = set(documentos_revisados) - existentes
    if faltantes:
        raise EstadoNoPermitido(f"Documentos inexistentes: {', '.join(sorted(faltantes))}")
    nuevo_estado = "VALIDADO" if decision == "APROBADO" else "RECHAZADO"
    return _agregar_validacion(db, perito, nuevo_estado, decision, motivo, documentos_revisados, actor)


def marcar_inconsistente(db: Database, perito_id: ObjectId, motivo: str, actor: dict):
    """Credenciales inconsistentes: el perito deja de estar habilitado (RNF-15)."""
    perito = obtener_perito(db, perito_id)
    if perito is None:
        return None
    return _agregar_validacion(db, perito, "INCONSISTENTE", "INCONSISTENTE", motivo, [], actor)


def _agregar_validacion(db, perito, nuevo_estado, decision, motivo, documentos_revisados, actor):
    momento = ahora()
    validacion = {
        "decision": decision,
        "motivo": motivo,
        "validado_por": actor["id"],
        "fecha": momento,
        "documentos_revisados": documentos_revisados,
    }
    actualizado = db["peritos"].find_one_and_update(
        {"_id": perito["_id"]},
        {"$push": {"validaciones": validacion}, "$set": {"estado_credencial": nuevo_estado, "actualizado_en": momento}},
        return_document=ReturnDocument.AFTER,
    )
    auditoria.registrar(
        db,
        "peritos",
        perito["_id"],
        "VALIDAR_PERITO",
        actor,
        {"anterior": perito["estado_credencial"], "nuevo": nuevo_estado, "documentos_revisados": documentos_revisados},
    )
    return actualizado


def marcar_vencidos(db: Database) -> int:
    """Tarea diaria de n8n: VALIDADO con matrícula vencida pasa a VENCIDO (RNF-15)."""
    momento = ahora()
    vencidos = list(
        db["peritos"].find(
            {"estado_credencial": "VALIDADO", "vigencia_matricula": {"$ne": None, "$lt": momento}}, {"_id": 1}
        )
    )
    for perito in vencidos:
        db["peritos"].update_one(
            {"_id": perito["_id"]}, {"$set": {"estado_credencial": "VENCIDO", "actualizado_en": momento}}
        )
        auditoria.registrar(
            db,
            "peritos",
            perito["_id"],
            "VENCER_MATRICULA",
            auditoria.actor_proceso("n8n"),
            {"anterior": "VALIDADO", "nuevo": "VENCIDO"},
        )
    return len(vencidos)


def perito_habilitado(db: Database, perito_id: ObjectId) -> bool:
    """True solo si el estado es VALIDADO. Lo usa H (RF-49, RNF-14)."""
    return db["peritos"].count_documents({"_id": perito_id, "estado_credencial": "VALIDADO"}, limit=1) > 0
