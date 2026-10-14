"""Errores comunes de la API. `main.py` los convierte en respuestas HTTP."""


class TransicionRechazada(Exception):
    """El cambio de estado no está permitido o el estado cambió antes de guardarlo (concurrencia). Responde 409."""
