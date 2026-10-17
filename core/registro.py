"""Logs de la aplicación sin datos personales (RNF-20)."""

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def obtener_logger(nombre: str) -> logging.Logger:
    return logging.getLogger(nombre)
