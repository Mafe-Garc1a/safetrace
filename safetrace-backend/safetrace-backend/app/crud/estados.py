"""Acceso a datos y reglas de G · Estados del inmueble (RF-38 a RF-47).

Colecciones de las que es dueño: historial_estados (y el campo `inmuebles.estado`).

Reglas clave:
- Único módulo que cambia el estado.
- La IA y el índice nunca piden transiciones (RNF-37).
- Los estados describen la etapa del proceso de revisión, nunca la seguridad
  del inmueble (RNF-27, RNF-33).
"""

from enum import IntEnum

from bson import ObjectId
from pymongo.database import Database

from app.crud import inmuebles as crud_inmuebles
from core.database import soporta_transacciones
from core.errores import TransicionRechazada
from core.fechas import ahora


class EstadoInmueble(IntEnum):
    SIN_EVENTO_PENDIENTE = 1
    MARCADO_POR_EVENTO_SISMICO = 2
    REVISION_PROPIETARIO_REGISTRADA = 3
    INSPECCION_SOLICITADA = 4
    INSPECCION_FIRMADA = 5


E = EstadoInmueble

# (estado de origen, estado destino) -> requerimiento que la permite
TRANSICIONES = {
    (E.SIN_EVENTO_PENDIENTE, E.MARCADO_POR_EVENTO_SISMICO): "RF-39",
    (E.MARCADO_POR_EVENTO_SISMICO, E.REVISION_PROPIETARIO_REGISTRADA): "RF-40",
    (E.MARCADO_POR_EVENTO_SISMICO, E.INSPECCION_SOLICITADA): "RF-41",
    (E.REVISION_PROPIETARIO_REGISTRADA, E.INSPECCION_SOLICITADA): "RF-41",
    (E.INSPECCION_SOLICITADA, E.INSPECCION_FIRMADA): "RF-42",
    (E.REVISION_PROPIETARIO_REGISTRADA, E.SIN_EVENTO_PENDIENTE): "RF-43",
    (E.INSPECCION_FIRMADA, E.SIN_EVENTO_PENDIENTE): "RF-44",
    # RF-45: un nuevo sismo relevante lleva al estado 2 desde cualquier otro
    (E.REVISION_PROPIETARIO_REGISTRADA, E.MARCADO_POR_EVENTO_SISMICO): "RF-45",
    (E.INSPECCION_SOLICITADA, E.MARCADO_POR_EVENTO_SISMICO): "RF-45",
    (E.INSPECCION_FIRMADA, E.MARCADO_POR_EVENTO_SISMICO): "RF-45",
}

CAUSAS = (
    "SISMO_RELEVANTE",
    "REVISION_REGISTRADA",
    "SIN_CAMBIOS",
    "INSPECCION_SOLICITADA",
    "INSPECCION_FIRMADA",
    "CONSTANCIA_VENCIDA",
)


def transicion_permitida(desde: int, hacia: int) -> bool:
    """True si el paso desde -> hacia está permitido por la ERS."""
    return (EstadoInmueble(desde), EstadoInmueble(hacia)) in TRANSICIONES


def estado_inicial() -> dict:
    """Estado con el que nace un inmueble: 1, versión 1."""
    return {
        "codigo": int(E.SIN_EVENTO_PENDIENTE),
        "nombre": E.SIN_EVENTO_PENDIENTE.name,
        "desde": ahora(),
        "version": 1,
    }


def consultar_estado(db: Database, inmueble_id: ObjectId) -> dict | None:
    """Estado actual del inmueble: {codigo, nombre, desde, version}."""
    inmueble = crud_inmuebles.obtener_inmueble(db, inmueble_id, proyeccion={"estado": 1})
    return inmueble["estado"] if inmueble else None


def pedir_transicion(
    db: Database,
    inmueble_id: ObjectId,
    esperado: int,
    nuevo: int,
    causa: str,
    referencia: dict | None,
    producido_por: dict,
) -> dict:
    """Cambia el estado si sigue siendo el esperado y guarda la fila del historial (sección 7.2).

    Lanza TransicionRechazada si el paso no está permitido o si otro proceso cambió
    el estado antes (quien llamó debe volver a leer el estado). La usan E, F y H.
    """
    if causa not in CAUSAS:
        raise ValueError(f"Causa desconocida: {causa}")
    if not transicion_permitida(esperado, nuevo):
        raise TransicionRechazada(f"No se permite pasar del estado {esperado} al {nuevo}")
    actual = consultar_estado(db, inmueble_id)
    if actual is None or actual["codigo"] != esperado:
        raise TransicionRechazada("El estado del inmueble cambió; vuelva a consultarlo")

    momento = ahora()
    nuevo_estado = {
        "codigo": int(nuevo),
        "nombre": EstadoInmueble(nuevo).name,
        "desde": momento,
        "version": actual["version"] + 1,
    }
    fila = {
        "inmueble_id": inmueble_id,
        "estado_anterior": int(esperado),
        "estado_nuevo": int(nuevo),
        "fecha": momento,
        "causa": causa,
        "referencia": referencia,
        "producido_por": producido_por,
    }

    def aplicar(session=None):
        cambiado = crud_inmuebles.escribir_estado(
            db, inmueble_id, esperado, actual["version"], nuevo_estado, session=session
        )
        if not cambiado:
            raise TransicionRechazada("El estado del inmueble cambió; vuelva a consultarlo")
        db["historial_estados"].insert_one(fila, session=session)

    if soporta_transacciones(db):
        with db.client.start_session() as sesion:
            sesion.with_transaction(aplicar)
    else:
        # Sin conjunto de réplicas: la condición sobre `estado.version` sigue impidiendo pisar cambios
        aplicar()
    return nuevo_estado


def historial(db: Database, inmueble_id: ObjectId, saltar: int, limite: int) -> tuple[list[dict], int]:
    """Cambios de estado del inmueble, del más reciente al más antiguo (RF-46)."""
    filtros = {"inmueble_id": inmueble_id}
    total = db["historial_estados"].count_documents(filtros)
    datos = list(db["historial_estados"].find(filtros).sort("fecha", -1).skip(saltar).limit(limite))
    return datos, total
