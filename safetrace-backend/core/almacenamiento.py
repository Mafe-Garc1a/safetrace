"""Proveedor de archivos: genera autorizaciones temporales para que el
navegador suba fotos y documentos directo, y descarga fotos para el trabajador.

La base de datos solo guarda la ruta y la huella SHA-256 de cada archivo.
Si falla, el resto de la API sigue funcionando (RNF-24).
"""

from core.config import settings


def autorizacion_subida(ruta: str, tipo_contenido: str) -> dict:
    """Devuelve {url_subida, campos, expira_en} para que el navegador suba el archivo a `ruta`."""
    if not settings.proveedor_archivos_url:
        raise NotImplementedError("Proveedor de archivos sin configurar (PROVEEDOR_ARCHIVOS_URL)")
    # TODO: integrar el proveedor de archivos elegido
    raise NotImplementedError("Proveedor de archivos pendiente de integrar")


def descargar(ruta: str) -> bytes:
    if not settings.proveedor_archivos_url:
        raise NotImplementedError("Proveedor de archivos sin configurar (PROVEEDOR_ARCHIVOS_URL)")
    # TODO: integrar el proveedor de archivos elegido
    raise NotImplementedError("Proveedor de archivos pendiente de integrar")
