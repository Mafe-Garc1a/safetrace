"""Conexión única a MongoDB (cliente síncrono de PyMongo) y utilidades para sus documentos."""

import logging
from collections.abc import Generator

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from core.config import settings

# Configurar el módulo de logging de Python y se usa para crear un registrador de eventos (logger)
logger = logging.getLogger(__name__)

# Crear el cliente con configuraciones adecuadas. El cliente ya maneja un pool de conexiones,
# así que se crea una sola vez y se reutiliza en toda la aplicación.
# - tz_aware=True: las fechas se leen en UTC con zona horaria
# - serverSelectionTimeoutMS: tiempo máximo para encontrar el servidor antes de fallar
cliente: MongoClient = MongoClient(
    settings.MONGO_URI,
    tz_aware=True,
    maxPoolSize=20,
    serverSelectionTimeoutMS=10000,
)


def obtener_db() -> Database:
    """Base de datos de SafeTrace. La usan el trabajador y los scripts de `db/`."""
    return cliente[settings.MONGO_DB]


def get_db() -> Generator[Database, None, None]:
    """
    Dependencia para obtener la base de datos en FastAPI.

    Example:
        ```python
        @router.get("/inmuebles")
        def listar(db: Database = Depends(get_db)):
            return crud_inmuebles.listar_por_propietario(db, ...)
        ```
    """
    yield obtener_db()


def check_database_connection() -> bool:
    """
    Verifica la conexión a la base de datos.

    Returns:
        bool: True si la conexión es exitosa, False en caso contrario.
    """
    try:
        cliente.admin.command("ping")
        return True
    except PyMongoError as e:
        logger.error(f"Error de conexión a la base de datos: {e}")
        return False


_transacciones: dict[int, bool] = {}


def soporta_transacciones(db: Database) -> bool:
    """True si el servidor es un conjunto de réplicas (Atlas siempre lo es).

    Un MongoDB local instalado sin réplicas no admite transacciones; en ese caso
    los cambios de estado siguen protegidos por la versión (sección 7.2 del diseño).
    """
    clave = id(db.client)
    if clave not in _transacciones:
        try:
            hola = db.client.admin.command("hello")
            _transacciones[clave] = bool(hola.get("setName")) or hola.get("msg") == "isdbgrid"
        except Exception:
            _transacciones[clave] = False
    return _transacciones[clave]


def a_object_id(valor) -> ObjectId:
    """Convierte un id recibido en la URL o en el cuerpo; responde 400 si no es válido."""
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(str(valor))
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Identificador inválido: {valor}") from None


def serializar(documento):
    """Prepara un documento de MongoDB para la respuesta: `_id` pasa a `id` y los ObjectId a texto."""
    if isinstance(documento, list):
        return [serializar(d) for d in documento]
    if isinstance(documento, dict):
        salida = {}
        for clave, valor in documento.items():
            salida["id" if clave == "_id" else clave] = serializar(valor)
        return salida
    if isinstance(documento, ObjectId):
        return str(documento)
    return documento


if __name__ == "__main__":
    resultado = check_database_connection()
    print("¿Conexión exitosa?:", resultado)
