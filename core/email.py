"""Servicio de correo transaccional. Solo lo llama el trabajador.

Si falla, el resto de la API sigue funcionando (RNF-24).
"""

from core.config import settings
from core.registro import obtener_logger

log = obtener_logger("correo")


def enviar(destinatario: str, plantilla: str, datos: dict) -> None:
    if not settings.correo_api_key:
        # Sin proveedor configurado (desarrollo local): se simula el envío. Sin datos personales en el log (RNF-20).
        log.info("correo simulado plantilla=%s", plantilla)
        return
    # TODO: integrar el proveedor de correo elegido usando settings.correo_api_key
    raise NotImplementedError("Proveedor de correo pendiente de integrar")
