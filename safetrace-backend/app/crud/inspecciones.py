"""Acceso a datos y reglas de H · Inspecciones y constancias (RF-48 a RF-58).

Colecciones de las que es dueño: solicitudes_inspeccion, inspecciones.

Reglas clave:
- Solo se asigna, registra y firma con un perito VALIDADO (RF-49, RNF-14, RNF-15).
- Firmada = inmutable; corregir crea una versión nueva (RNF-13). Después de firmar solo
  cambian `constancia.estado` (VIGENTE → VENCIDA) y `es_version_activa`.
- Código de constancia aleatorio; huella SHA-256 del contenido (RF-52, RF-54, RF-58).
"""

import hashlib
import json
import secrets
from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from app.crud import auditoria
from app.crud import bitacora as crud_bitacora
from app.crud import estados as crud_estados
from app.crud import notificaciones as crud_notificaciones
from app.crud import peritos as crud_peritos
from app.crud.estados import EstadoInmueble as E
from app.schemas.inspecciones import CorreccionCreate, InspeccionCreate, InspeccionUpdate, SolicitudCreate
from core.errores import TransicionRechazada
from core.fechas import ahora, en_utc, sumar_meses

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para evitar confusiones
AVISO_LEGAL = (
    "Esta inspección no certifica el cumplimiento de la NSR-10 ni la habitabilidad del inmueble. "
    "Registra la evaluación del perito que la firma, quien responde por su juicio técnico. "
    "SafeTrace solo garantiza que el documento no ha sido alterado desde su firma."
)
ABIERTAS = ("SOLICITADA", "ASIGNADA")


class ReglaInspeccion(Exception):
    """La acción no está permitida por las reglas del módulo H."""


def generar_codigo(longitud: int = 16) -> str:
    """Código aleatorio con generador criptográfico; nunca consecutivo."""
    return "".join(secrets.choice(ALFABETO) for _ in range(longitud))


def _normalizar(valor):
    """Fechas en UTC con milisegundos e ids como texto: igual antes y después de guardar en MongoDB."""
    if isinstance(valor, datetime):
        return en_utc(valor).isoformat(timespec="milliseconds")
    return str(valor)


def huella_contenido(contenido: dict) -> str:
    """SHA-256 del contenido firmado, en JSON canónico (claves ordenadas)."""
    canonico = json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=_normalizar, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def contenido_firmable(inspeccion: dict) -> dict:
    """Campos que cubre la firma. `constancia.estado` y `es_version_activa` quedan fuera porque pueden cambiar."""
    constancia = inspeccion.get("constancia") or {}
    return {
        "id": inspeccion["_id"],
        "solicitud_id": inspeccion["solicitud_id"],
        "inmueble_id": inspeccion["inmueble_id"],
        "perito_id": inspeccion["perito_id"],
        "version": inspeccion["version"],
        "version_anterior_id": inspeccion.get("version_anterior_id"),
        "fecha_inspeccion": inspeccion["fecha_inspeccion"],
        "motivo": inspeccion["motivo"],
        "observaciones": inspeccion["observaciones"],
        "hallazgos": inspeccion["hallazgos"],
        "resultado": inspeccion["resultado"],
        "evidencias_ids": inspeccion.get("evidencias_ids", []),
        "aviso_legal": inspeccion["aviso_legal"],
        "firma_fecha": inspeccion["firma"]["fecha"],
        "constancia_codigo": constancia.get("codigo"),
        "constancia_emitida_en": constancia.get("emitida_en"),
        "constancia_vigente_hasta": constancia.get("vigente_hasta"),
    }


# --- Solicitudes (RF-48, RF-49, RF-69) ---------------------------------------


def crear_solicitud(db: Database, inmueble: dict, datos: SolicitudCreate, usuario: dict) -> dict:
    """El propietario solicita una inspección. Desde el estado 2 o 3 el inmueble pasa al 4 (RF-41)."""
    if db["solicitudes_inspeccion"].count_documents({"inmueble_id": inmueble["_id"], "estado": {"$in": ABIERTAS}}):
        raise ReglaInspeccion("El inmueble ya tiene una solicitud de inspección en curso")
    momento = ahora()
    documento = {
        "inmueble_id": inmueble["_id"],
        "solicitada_por": usuario["_id"],
        **datos.model_dump(),
        "estado": "SOLICITADA",
        "perito_id": None,
        "asignada_por": None,
        "cambios_estado": [{"estado": "SOLICITADA", "fecha": momento}],
        "creado_en": momento,
    }
    documento["_id"] = db["solicitudes_inspeccion"].insert_one(documento).inserted_id

    actual = inmueble["estado"]["codigo"]
    if crud_estados.transicion_permitida(actual, E.INSPECCION_SOLICITADA):
        crud_estados.pedir_transicion(
            db, inmueble["_id"], actual, E.INSPECCION_SOLICITADA, "INSPECCION_SOLICITADA",
            {"tipo": "SOLICITUD_INSPECCION", "id": documento["_id"]}, {"tipo": "USUARIO", "id": usuario["_id"]},
        )  # fmt: skip
    crud_notificaciones.notificar(
        db, inmueble["propietario_id"], "CAMBIO_SOLICITUD", {"tipo": "SOLICITUD_INSPECCION", "id": documento["_id"]}
    )
    auditoria.registrar(
        db, "solicitudes_inspeccion", documento["_id"], "SOLICITAR_INSPECCION", auditoria.actor_usuario(usuario)
    )
    return documento


def obtener_solicitud(db: Database, solicitud_id: ObjectId) -> dict | None:
    return db["solicitudes_inspeccion"].find_one({"_id": solicitud_id})


def listar_solicitudes(db: Database, filtros: dict, saltar: int, limite: int) -> tuple[list[dict], int]:
    total = db["solicitudes_inspeccion"].count_documents(filtros)
    datos = list(db["solicitudes_inspeccion"].find(filtros).sort("creado_en", -1).skip(saltar).limit(limite))
    return datos, total


def asignar_perito(db: Database, solicitud: dict, perito_id: ObjectId, propietario_id: ObjectId, actor: dict) -> dict:
    """El administrador asigna un perito VALIDADO (RF-49, RNF-15). Se avisa al propietario (RF-69)."""
    if solicitud["estado"] not in ABIERTAS:
        raise ReglaInspeccion(f"La solicitud está {solicitud['estado']}")
    if not crud_peritos.perito_habilitado(db, perito_id):
        raise ReglaInspeccion("Solo se puede asignar un perito con credenciales VALIDADAS")
    if db["inspecciones"].count_documents({"solicitud_id": solicitud["_id"]}):
        raise ReglaInspeccion("El perito asignado ya registró la inspección")
    momento = ahora()
    actualizada = db["solicitudes_inspeccion"].find_one_and_update(
        {"_id": solicitud["_id"], "estado": {"$in": ABIERTAS}},
        {
            "$set": {"estado": "ASIGNADA", "perito_id": perito_id, "asignada_por": actor["id"]},
            "$push": {"cambios_estado": {"estado": "ASIGNADA", "fecha": momento}},
        },
        return_document=ReturnDocument.AFTER,
    )
    crud_notificaciones.notificar(
        db, propietario_id, "CAMBIO_SOLICITUD", {"tipo": "SOLICITUD_INSPECCION", "id": solicitud["_id"]}
    )
    auditoria.registrar(
        db, "solicitudes_inspeccion", solicitud["_id"], "ASIGNAR_PERITO", actor, {"perito_id": perito_id}
    )
    return actualizada


def perito_asignado_a_inmueble(db: Database, inmueble_id: ObjectId, usuario_id: ObjectId) -> bool:
    """True si el usuario es el perito asignado a alguna solicitud del inmueble (RF-47, RNF-10)."""
    perito = crud_peritos.obtener_por_usuario(db, usuario_id)
    if perito is None:
        return False
    return (
        db["solicitudes_inspeccion"].count_documents(
            {"inmueble_id": inmueble_id, "perito_id": perito["_id"], "estado": {"$in": ["ASIGNADA", "FIRMADA"]}},
            limit=1,
        )
        > 0
    )


# --- Inspecciones (RF-50 a RF-53) ----------------------------------------------


def _perito_habilitado_de(db: Database, usuario: dict) -> dict:
    perito = crud_peritos.obtener_por_usuario(db, usuario["_id"])
    if perito is None or perito["estado_credencial"] != "VALIDADO":
        raise ReglaInspeccion("Solo un perito con credenciales VALIDADAS puede registrar y firmar (RNF-14)")
    return perito


def _registrar_evidencias(db, inspeccion_id, inmueble_id, entradas, usuario) -> list[ObjectId]:
    return [
        crud_bitacora.registrar_evidencia(db, inmueble_id, "INSPECCION", inspeccion_id, entrada, usuario)["_id"]
        for entrada in entradas
    ]


def registrar_inspeccion(db: Database, solicitud: dict, datos: InspeccionCreate, usuario: dict) -> dict:
    """El perito validado y asignado registra la inspección (RF-50, RF-51). Queda sin firmar."""
    perito = _perito_habilitado_de(db, usuario)
    if solicitud["estado"] != "ASIGNADA" or solicitud["perito_id"] != perito["_id"]:
        raise ReglaInspeccion("La solicitud no está asignada a este perito")
    if db["inspecciones"].count_documents({"solicitud_id": solicitud["_id"]}):
        raise ReglaInspeccion("La inspección ya fue registrada; edítela antes de firmar o corrija la versión firmada")
    documento = {
        "solicitud_id": solicitud["_id"],
        "inmueble_id": solicitud["inmueble_id"],
        "perito_id": perito["_id"],
        "version": 1,
        "version_anterior_id": None,
        "es_version_activa": True,
        **datos.model_dump(exclude={"evidencias"}),
        "evidencias_ids": [],
        "firma": {"firmada": False, "fecha": None, "metodo": None, "huella_sha256": None},
        "constancia": None,
        "aviso_legal": AVISO_LEGAL,
        "creado_en": ahora(),
    }
    documento["_id"] = db["inspecciones"].insert_one(documento).inserted_id
    ids = _registrar_evidencias(db, documento["_id"], solicitud["inmueble_id"], datos.evidencias, usuario)
    if ids:
        db["inspecciones"].update_one({"_id": documento["_id"]}, {"$set": {"evidencias_ids": ids}})
        documento["evidencias_ids"] = ids
    auditoria.registrar(db, "inspecciones", documento["_id"], "REGISTRAR_INSPECCION", auditoria.actor_usuario(usuario))
    return documento


def obtener_inspeccion(db: Database, inspeccion_id: ObjectId) -> dict | None:
    return db["inspecciones"].find_one({"_id": inspeccion_id})


def listar_inspecciones(db: Database, inmueble_id: ObjectId) -> list[dict]:
    return list(db["inspecciones"].find({"inmueble_id": inmueble_id}).sort([("creado_en", -1)]))


def _verificar_autor(db: Database, inspeccion: dict, usuario: dict) -> dict:
    perito = _perito_habilitado_de(db, usuario)
    if inspeccion["perito_id"] != perito["_id"]:
        raise ReglaInspeccion("Solo el perito que registró la inspección puede modificarla o firmarla")
    return perito


def actualizar_borrador(db: Database, inspeccion: dict, cambios: InspeccionUpdate, usuario: dict) -> dict:
    """Antes de firmar, el perito puede ajustar su registro."""
    _verificar_autor(db, inspeccion, usuario)
    datos = cambios.model_dump(exclude_unset=True)
    if not datos:
        return inspeccion
    actualizada = db["inspecciones"].find_one_and_update(
        {"_id": inspeccion["_id"], "firma.firmada": False},
        {"$set": datos},
        return_document=ReturnDocument.AFTER,
    )
    if actualizada is None:
        raise ReglaInspeccion("Una inspección firmada no se modifica; registre una corrección (RNF-13)")
    return actualizada


def firmar(db: Database, inspeccion: dict, vigencia_meses: int, usuario: dict) -> dict:
    """Firma, calcula la huella y emite la constancia (RF-52, RF-54, RF-55, RF-57).

    El inmueble pasa de 4 a 5 solo si sigue en el 4; si un sismo nuevo lo devolvió al 2,
    la firma se guarda sin cambiar el estado (decisión pendiente de la Product Owner).
    """
    _verificar_autor(db, inspeccion, usuario)
    if inspeccion["firma"]["firmada"]:
        raise ReglaInspeccion("La inspección ya está firmada")

    momento = ahora()
    codigo = generar_codigo()
    while db["inspecciones"].count_documents({"constancia.codigo": codigo}, limit=1):
        codigo = generar_codigo()
    firma = {"firmada": True, "fecha": momento, "metodo": "CONFIRMACION_CONTRASENA", "huella_sha256": None}
    constancia = {
        "codigo": codigo,
        "emitida_en": momento,
        "vigencia_meses": vigencia_meses,
        "vigente_hasta": sumar_meses(momento, vigencia_meses),
        "estado": "VIGENTE",
    }
    firma["huella_sha256"] = huella_contenido(
        contenido_firmable({**inspeccion, "firma": firma, "constancia": constancia})
    )

    firmada = db["inspecciones"].find_one_and_update(
        {"_id": inspeccion["_id"], "firma.firmada": False},
        {"$set": {"firma": firma, "constancia": constancia, "es_version_activa": True}},
        return_document=ReturnDocument.AFTER,
    )
    if firmada is None:
        raise ReglaInspeccion("La inspección ya está firmada")
    if inspeccion.get("version_anterior_id"):
        db["inspecciones"].update_one(
            {"_id": inspeccion["version_anterior_id"]}, {"$set": {"es_version_activa": False}}
        )

    solicitud = obtener_solicitud(db, inspeccion["solicitud_id"])
    if solicitud["estado"] != "FIRMADA":
        db["solicitudes_inspeccion"].update_one(
            {"_id": solicitud["_id"]},
            {"$set": {"estado": "FIRMADA"}, "$push": {"cambios_estado": {"estado": "FIRMADA", "fecha": momento}}},
        )

    estado = crud_estados.consultar_estado(db, inspeccion["inmueble_id"])
    if estado and estado["codigo"] == E.INSPECCION_SOLICITADA:
        try:
            crud_estados.pedir_transicion(
                db, inspeccion["inmueble_id"], E.INSPECCION_SOLICITADA, E.INSPECCION_FIRMADA, "INSPECCION_FIRMADA",
                {"tipo": "INSPECCION", "id": inspeccion["_id"]}, {"tipo": "USUARIO", "id": usuario["_id"]},
            )  # fmt: skip
        except TransicionRechazada:
            pass  # otro proceso cambió el estado (p. ej. un sismo): la firma queda guardada igual

    crud_notificaciones.notificar(
        db, solicitud["solicitada_por"], "CONSTANCIA_DISPONIBLE", {"tipo": "INSPECCION", "id": inspeccion["_id"]}
    )
    auditoria.registrar(
        db,
        "inspecciones",
        inspeccion["_id"],
        "FIRMAR_INSPECCION",
        auditoria.actor_usuario(usuario),
        {"firma.huella_sha256": firma["huella_sha256"], "version": inspeccion["version"]},
    )
    return firmada


def crear_correccion(db: Database, inspeccion: dict, datos: CorreccionCreate, usuario: dict) -> dict:
    """Nueva versión de una inspección firmada; la anterior no se toca hasta firmar la nueva (RF-53, RNF-13)."""
    _verificar_autor(db, inspeccion, usuario)
    if not inspeccion["firma"]["firmada"] or not inspeccion["es_version_activa"]:
        raise ReglaInspeccion("Solo se corrige la versión firmada y activa")
    if db["inspecciones"].count_documents({"version_anterior_id": inspeccion["_id"]}, limit=1):
        raise ReglaInspeccion("Ya existe una corrección de esta versión")
    cambios = datos.model_dump(exclude_unset=True, exclude={"evidencias"})
    documento = {
        "solicitud_id": inspeccion["solicitud_id"],
        "inmueble_id": inspeccion["inmueble_id"],
        "perito_id": inspeccion["perito_id"],
        "version": inspeccion["version"] + 1,
        "version_anterior_id": inspeccion["_id"],
        "es_version_activa": False,  # pasa a activa cuando se firme
        "fecha_inspeccion": cambios.get("fecha_inspeccion", inspeccion["fecha_inspeccion"]),
        "motivo": cambios.get("motivo", inspeccion["motivo"]),
        "observaciones": cambios.get("observaciones", inspeccion["observaciones"]),
        "hallazgos": cambios.get("hallazgos", inspeccion["hallazgos"]),
        "resultado": cambios.get("resultado", inspeccion["resultado"]),
        "evidencias_ids": list(inspeccion.get("evidencias_ids", [])),
        "firma": {"firmada": False, "fecha": None, "metodo": None, "huella_sha256": None},
        "constancia": None,
        "aviso_legal": AVISO_LEGAL,
        "creado_en": ahora(),
    }
    documento["_id"] = db["inspecciones"].insert_one(documento).inserted_id
    nuevas = _registrar_evidencias(db, documento["_id"], inspeccion["inmueble_id"], datos.evidencias, usuario)
    if nuevas:
        documento["evidencias_ids"] += nuevas
        db["inspecciones"].update_one(
            {"_id": documento["_id"]}, {"$set": {"evidencias_ids": documento["evidencias_ids"]}}
        )
    auditoria.registrar(
        db,
        "inspecciones",
        documento["_id"],
        "CORREGIR_INSPECCION",
        auditoria.actor_usuario(usuario),
        {"version_anterior_id": inspeccion["_id"], "version": documento["version"]},
    )
    return documento


# --- Constancias (RF-54 a RF-58) ----------------------------------------------


def obtener_por_codigo(db: Database, codigo: str) -> dict | None:
    return db["inspecciones"].find_one({"constancia.codigo": codigo, "firma.firmada": True})


def es_integra(inspeccion: dict) -> bool:
    """Recalcula la huella y la compara con la firmada (RF-58)."""
    return huella_contenido(contenido_firmable(inspeccion)) == inspeccion["firma"]["huella_sha256"]


def constancias_vigentes(db: Database, inmueble_id: ObjectId) -> list[dict]:
    """Inspecciones firmadas y activas del inmueble, con su constancia. La usa I."""
    return list(
        db["inspecciones"]
        .find({"inmueble_id": inmueble_id, "firma.firmada": True, "es_version_activa": True})
        .sort("firma.fecha", -1)
    )


def vencer_constancias(db: Database) -> dict:
    """Tarea diaria de n8n (RF-44, RF-56). Vencer no borra; pide 5 → 1 solo si el inmueble sigue en el 5."""
    momento = ahora()
    vencidas = 0
    inmuebles_liberados = 0
    for inspeccion in db["inspecciones"].find(
        {"firma.firmada": True, "constancia.estado": "VIGENTE", "constancia.vigente_hasta": {"$lt": momento}}
    ):
        db["inspecciones"].update_one(
            {"_id": inspeccion["_id"], "constancia.estado": "VIGENTE"}, {"$set": {"constancia.estado": "VENCIDA"}}
        )
        vencidas += 1
        auditoria.registrar(
            db, "inspecciones", inspeccion["_id"], "VENCER_CONSTANCIA", auditoria.actor_proceso("n8n"),
            {"constancia.estado": "VENCIDA"},
        )  # fmt: skip
        if not inspeccion["es_version_activa"]:
            continue
        estado = crud_estados.consultar_estado(db, inspeccion["inmueble_id"])
        if estado and estado["codigo"] == E.INSPECCION_FIRMADA:
            try:
                crud_estados.pedir_transicion(
                    db, inspeccion["inmueble_id"], E.INSPECCION_FIRMADA, E.SIN_EVENTO_PENDIENTE, "CONSTANCIA_VENCIDA",
                    {"tipo": "INSPECCION", "id": inspeccion["_id"]}, {"tipo": "PROCESO", "id": "vencimientos-n8n"},
                )  # fmt: skip
                inmuebles_liberados += 1
            except TransicionRechazada:
                pass
    return {"constancias_vencidas": vencidas, "inmuebles_a_estado_1": inmuebles_liberados}
