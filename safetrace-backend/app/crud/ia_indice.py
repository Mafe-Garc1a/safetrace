"""Acceso a datos y reglas de J · Análisis de IA e índice de priorización (RF-62 a RF-68).

Colecciones de las que es dueño: analisis_ia, indices_priorizacion (y el campo `inmuebles.ultimo_indice`).

Reglas clave:
- Leyenda exacta: «Análisis automático mediante IA» (RF-65).
- Un par de fotos se analiza una sola vez (RNF-25).
- Nada de este módulo cambia el estado del inmueble (RNF-37).
"""

import hashlib
from pathlib import Path

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.crud import bitacora as crud_bitacora
from app.crud import inmuebles as crud_inmuebles
from app.crud import notificaciones as crud_notificaciones
from app.crud import revisiones as crud_revisiones
from core.fechas import ahora

# --- Comparador de fotos (RF-62) ---------------------------------------------
# El modelo se entrena en Colab y sus pesos se copian a `modelos_ia/`
# (carpeta ignorada por git). Solo lo usa el trabajador, nunca la API.

RUTA_MODELO = Path(__file__).resolve().parents[2] / "modelos_ia"
LEYENDA = "Análisis automático mediante IA"  # texto exacto de RF-65
MODELO_VERSION = "comparador-v1"


def cargar_modelo():
    """Carga los pesos desde RUTA_MODELO una sola vez al arrancar el trabajador."""
    raise NotImplementedError("Modelo de comparación pendiente (se entrena en Colab)")


def comparar(foto_anterior: bytes, foto_nueva: bytes) -> dict:
    """Devuelve {cambio_detectado, descripcion, confianza}."""
    raise NotImplementedError("Modelo de comparación pendiente (se entrena en Colab)")


# --- Índice de priorización (RF-66, RF-67) -----------------------------------
# Función pura: recibe las variables y devuelve el valor. Los pesos están
# pendientes de definir; cada cambio de fórmula sube FORMULA_VERSION.

FORMULA_VERSION = "v1"
AVISO = "Índice orientativo calculado por el sistema; no es una evaluación profesional."  # RF-68


def calcular(variables: dict) -> float:
    """variables: anio_construccion, sistema_constructivo, numero_pisos, magnitud,
    distancia_km, antecedentes_danos, antecedentes_mantenimiento, fecha_ultima_revision."""
    raise NotImplementedError("Pesos pendientes de definir (decisión abierta, sección 11.2)")


# --- Análisis de fotos ---------------------------------------------------------


def clave_par(evidencia_anterior_id: ObjectId, evidencia_nueva_id: ObjectId) -> str:
    return hashlib.sha256(f"{evidencia_anterior_id}|{evidencia_nueva_id}".encode()).hexdigest()


def solicitar_comparacion(db: Database, foto_nueva: dict) -> ObjectId | None:
    """Crea el análisis PENDIENTE y su tarea si hay foto anterior de la zona y el par no existe. La usa D."""
    anterior = crud_bitacora.foto_anterior(db, foto_nueva["inmueble_id"], foto_nueva["zona_id"], foto_nueva)
    if anterior is None:
        return None
    clave = clave_par(anterior["_id"], foto_nueva["_id"])
    existente = db["analisis_ia"].find_one({"clave_par": clave}, {"_id": 1})
    if existente:
        return existente["_id"]
    try:
        analisis_id = (
            db["analisis_ia"]
            .insert_one(
                {
                    "inmueble_id": foto_nueva["inmueble_id"],
                    "zona_id": foto_nueva["zona_id"],
                    "evidencia_anterior_id": anterior["_id"],
                    "evidencia_nueva_id": foto_nueva["_id"],
                    "clave_par": clave,
                    "estado": "PENDIENTE",
                    "tarea_id": None,
                    "resultado": None,
                    "leyenda": LEYENDA,
                    "modelo_version": MODELO_VERSION,
                    "completado_en": None,
                    "creado_en": ahora(),
                }
            )
            .inserted_id
        )
    except DuplicateKeyError:  # otro proceso creó el mismo par al mismo tiempo
        return db["analisis_ia"].find_one({"clave_par": clave}, {"_id": 1})["_id"]
    tarea_id = crud_notificaciones.encolar_tarea(db, "COMPARAR_FOTOS", {"analisis_id": analisis_id})
    db["analisis_ia"].update_one({"_id": analisis_id}, {"$set": {"tarea_id": tarea_id}})
    return analisis_id


def marcar_reemplazados(db: Database, evidencia_id: ObjectId) -> int:
    """Si una foto se invalida o reemplaza, sus análisis pasan a REEMPLAZADO (RNF-25)."""
    return (
        db["analisis_ia"]
        .update_many(
            {
                "$or": [{"evidencia_anterior_id": evidencia_id}, {"evidencia_nueva_id": evidencia_id}],
                "estado": {"$ne": "REEMPLAZADO"},
            },
            {"$set": {"estado": "REEMPLAZADO"}},
        )
        .modified_count
    )


def obtener_analisis(db: Database, analisis_id: ObjectId) -> dict | None:
    return db["analisis_ia"].find_one({"_id": analisis_id})


def listar_analisis(db: Database, inmueble_id: ObjectId, saltar: int, limite: int) -> tuple[list[dict], int]:
    filtros = {"inmueble_id": inmueble_id, "estado": {"$ne": "REEMPLAZADO"}}
    total = db["analisis_ia"].count_documents(filtros)
    datos = list(db["analisis_ia"].find(filtros).sort("creado_en", -1).skip(saltar).limit(limite))
    return datos, total


def marcar_procesando(db: Database, analisis_id: ObjectId) -> dict | None:
    return db["analisis_ia"].find_one_and_update(
        {"_id": analisis_id, "estado": {"$in": ["PENDIENTE", "PROCESANDO"]}},
        {"$set": {"estado": "PROCESANDO"}},
        return_document=ReturnDocument.AFTER,
    )


def guardar_resultado(db: Database, analisis_id: ObjectId, resultado: dict) -> None:
    """Una vez completado, el resultado no se modifica (RNF-35)."""
    db["analisis_ia"].update_one(
        {"_id": analisis_id, "estado": "PROCESANDO"},
        {"$set": {"estado": "COMPLETADO", "resultado": resultado, "completado_en": ahora()}},
    )


def marcar_fallido(db: Database, analisis_id: ObjectId, definitivo: bool) -> None:
    db["analisis_ia"].update_one(
        {"_id": analisis_id, "estado": "PROCESANDO"},
        {"$set": {"estado": "FALLIDO" if definitivo else "PENDIENTE"}},
    )


def reintentar(db: Database, analisis_id: ObjectId) -> dict | None:
    """Un análisis FALLIDO vuelve a PENDIENTE con una tarea nueva (RF-64, RNF-24)."""
    analisis = db["analisis_ia"].find_one_and_update(
        {"_id": analisis_id, "estado": "FALLIDO"}, {"$set": {"estado": "PENDIENTE"}}
    )
    if analisis is None:
        return None
    tarea_id = crud_notificaciones.encolar_tarea(db, "COMPARAR_FOTOS", {"analisis_id": analisis_id})
    return db["analisis_ia"].find_one_and_update(
        {"_id": analisis_id}, {"$set": {"tarea_id": tarea_id}}, return_document=ReturnDocument.AFTER
    )


# --- Índice ----------------------------------------------------------------------


def calcular_indice(db: Database, inmueble_id: ObjectId, sismo: dict, distancia_km: float) -> dict:
    """Calcula y guarda el índice con las variables usadas (RF-66, RF-67). La usa F.

    Nunca cambia el estado del inmueble (RNF-37).
    """
    inmueble = crud_inmuebles.obtener_inmueble(db, inmueble_id)
    variables = {
        "anio_construccion": inmueble["anio_construccion"],
        "sistema_constructivo": inmueble["sistema_constructivo"],
        "numero_pisos": inmueble["numero_pisos"],
        "magnitud": sismo["magnitud"],
        "distancia_km": round(distancia_km, 1),
        **crud_bitacora.antecedentes(db, inmueble_id),
        "fecha_ultima_revision": crud_revisiones.fecha_ultima_revision(db, inmueble_id),
    }
    valor = calcular(variables)
    momento = ahora()
    documento = {
        "inmueble_id": inmueble_id,
        "sismo_id": sismo["_id"],
        "valor": valor,
        "variables": variables,
        "aviso": AVISO,
        "formula_version": FORMULA_VERSION,
        "calculado_en": momento,
    }
    db["indices_priorizacion"].update_one(
        {"inmueble_id": inmueble_id, "sismo_id": sismo["_id"]}, {"$set": documento}, upsert=True
    )
    crud_inmuebles.escribir_ultimo_indice(
        db, inmueble_id, {"valor": valor, "sismo_id": sismo["_id"], "calculado_en": momento}
    )
    return documento


def ultimo_indice(db: Database, inmueble_id: ObjectId) -> dict | None:
    return db["indices_priorizacion"].find_one({"inmueble_id": inmueble_id}, sort=[("calculado_en", -1)])


def priorizacion_por_sismo(db: Database, sismo_id: ObjectId, saltar: int, limite: int) -> tuple[list[dict], int]:
    """Inmuebles de un sismo ordenados por índice: qué revisar primero."""
    filtros = {"sismo_id": sismo_id}
    total = db["indices_priorizacion"].count_documents(filtros)
    datos = list(db["indices_priorizacion"].find(filtros).sort("valor", -1).skip(saltar).limit(limite))
    return datos, total
