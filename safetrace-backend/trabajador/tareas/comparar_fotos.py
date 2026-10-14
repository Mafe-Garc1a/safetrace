"""COMPARAR_FOTOS: descarga las dos fotos, ejecuta el modelo y guarda el resultado (RF-62 a RF-65)."""

from app.crud import bitacora as crud_bitacora
from app.crud import ia_indice as crud_ia_indice
from core import almacenamiento

_modelo = None


def ejecutar(db, tarea: dict) -> None:
    global _modelo
    analisis = crud_ia_indice.marcar_procesando(db, tarea["datos"]["analisis_id"])
    if analisis is None:
        return  # reemplazado o ya completado: no hay nada que hacer
    if _modelo is None:
        _modelo = crud_ia_indice.cargar_modelo()
    anterior = crud_bitacora.obtener_evidencia(db, analisis["evidencia_anterior_id"])
    nueva = crud_bitacora.obtener_evidencia(db, analisis["evidencia_nueva_id"])
    resultado = crud_ia_indice.comparar(
        almacenamiento.descargar(anterior["archivo"]["ruta"]),
        almacenamiento.descargar(nueva["archivo"]["ruta"]),
    )
    crud_ia_indice.guardar_resultado(db, analisis["_id"], resultado)


def al_fallar(db, tarea: dict, definitiva: bool) -> None:
    crud_ia_indice.marcar_fallido(db, tarea["datos"]["analisis_id"], definitiva)
