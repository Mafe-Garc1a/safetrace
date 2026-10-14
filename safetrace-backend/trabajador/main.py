"""Bucle del trabajador: ejecuta la colección `tareas` (RNF-03).

Ejecutar en otra terminal, junto a la API:  python -m trabajador.main
"""

import time

from app.crud import notificaciones as crud_notificaciones
from core.database import obtener_db
from core.registro import obtener_logger
from trabajador.tareas import EJECUTORES

log = obtener_logger("trabajador")
NOMBRE = "trabajador-1"
ESPERA_SEGUNDOS = 2


def ejecutar(db, tarea: dict) -> None:
    """Ejecuta una tarea; si falla la devuelve a PENDIENTE o la deja FALLIDA (RNF-24)."""
    log.info("tarea %s tipo=%s intento=%s", tarea["_id"], tarea["tipo"], tarea["intentos"])  # sin datos personales
    modulo = EJECUTORES.get(tarea["tipo"])
    try:
        if modulo is None:
            raise NotImplementedError(f"Tipo de tarea sin ejecutor: {tarea['tipo']}")
        modulo.ejecutar(db, tarea)
        crud_notificaciones.completar_tarea(db, tarea["_id"])
    except Exception as e:
        definitiva = crud_notificaciones.fallar_tarea(db, tarea, f"{type(e).__name__}: {e}")
        log.warning("tarea %s falló (%s); definitiva=%s", tarea["_id"], type(e).__name__, definitiva)
        al_fallar = getattr(modulo, "al_fallar", None)
        if al_fallar:
            al_fallar(db, tarea, definitiva)


def ciclo():
    db = obtener_db()
    log.info("trabajador iniciado")
    while True:
        tarea = crud_notificaciones.tomar_tarea(db, NOMBRE)
        if tarea is None:
            time.sleep(ESPERA_SEGUNDOS)
            continue
        ejecutar(db, tarea)


if __name__ == "__main__":
    ciclo()
