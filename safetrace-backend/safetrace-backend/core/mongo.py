from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.results import InsertOneResult, UpdateResult


class OperacionInmutableError(Exception):
    """Intento de modificar o borrar un registro inmutable (RNF-12, RNF-13, RNF-16)."""

    def __init__(self, coleccion: str, operacion: str, motivo: str):
        self.coleccion = coleccion
        self.operacion = operacion
        self.motivo = motivo
        super().__init__(f"[{coleccion}] '{operacion}' bloqueado: {motivo}")


OPERACIONES_APPEND_ONLY = frozenset({"insert_one", "find", "find_one", "count_documents", "aggregate"})
ETAPAS_AGG_PROHIBIDAS = frozenset({"$out", "$merge"})


def validar_pipeline_solo_lectura(coleccion: str, pipeline: list[Mapping[str, Any]]) -> None:
    for etapa in pipeline:
        prohibida = ETAPAS_AGG_PROHIBIDAS.intersection(etapa.keys())
        if prohibida:
            raise OperacionInmutableError(coleccion, "aggregate", f"etapa de escritura {sorted(prohibida)}")


ESTADO_EDITABLE = "BORRADOR"

# Campos que nunca cambian después del insert (identidad y cadena de versiones).
CAMPOS_IDENTIDAD_INSPECCION = frozenset(
    {
        "_id",
        "inmueble_id",
        "solicitud_id",
        "perito_id",
        "version",
        "raiz_id",
        "inspeccion_previa_id",
        "created_at",
        "nivel_confianza",
    }
)
# Campos que solo puede escribir la operación de firma (sellar_firma).
CAMPOS_SOLO_FIRMA = frozenset({"estado", "firma", "constancia"})
OPERADORES_UPDATE_PERMITIDOS = frozenset({"$set", "$unset", "$push", "$pull", "$addToSet", "$currentDate"})


def _raiz(ruta: str) -> str:
    return ruta.split(".", 1)[0]


def validar_update_borrador(update: Mapping[str, Any] | list) -> None:
    """Reglas para editar un borrador de inspección (RF-50/RF-51)."""
    if isinstance(update, list):
        raise OperacionInmutableError("inspecciones", "update", "no se admiten pipelines de actualización")
    if not update:
        raise OperacionInmutableError("inspecciones", "update", "actualización vacía")
    for operador, campos in update.items():
        if not operador.startswith("$"):
            raise OperacionInmutableError("inspecciones", "update", "reemplazo de documento completo no permitido")
        if operador not in OPERADORES_UPDATE_PERMITIDOS:
            raise OperacionInmutableError("inspecciones", "update", f"operador {operador} no permitido")
        for ruta in campos:
            raiz = _raiz(ruta)
            if raiz in CAMPOS_IDENTIDAD_INSPECCION:
                raise OperacionInmutableError("inspecciones", "update", f"campo de identidad '{raiz}'")
            if raiz in CAMPOS_SOLO_FIRMA:
                raise OperacionInmutableError("inspecciones", "update", f"'{raiz}' solo lo escribe la firma")


def filtro_solo_borradores(filtro: Mapping[str, Any]) -> dict[str, Any]:
    """Fuerza que el update solo pueda tocar borradores, aunque el llamador olvide el filtro.

    Se combina con $and para que un filtro malicioso como {"estado": "FIRMADA"}
    no pueda sobrescribir la condición.
    """
    return {"$and": [dict(filtro), {"estado": ESTADO_EDITABLE}]}


TRANSICIONES_EVIDENCIA = {
    "ACTIVA": frozenset({"INVALIDADA_POR_ERROR", "REEMPLAZADA"}),
    "INVALIDADA_POR_ERROR": frozenset(),
    "REEMPLAZADA": frozenset(),
}


def validar_cambio_evidencia(actual: str, nuevo: str, motivo: str | None) -> None:
    if nuevo not in TRANSICIONES_EVIDENCIA.get(actual, frozenset()):
        raise OperacionInmutableError("eventos", "invalidar_evidencia", f"{actual} → {nuevo} no permitido (RF-27)")
    if not motivo or len(motivo.strip()) < 5:
        raise OperacionInmutableError("eventos", "invalidar_evidencia", "se requiere un motivo (RNF-21)")


# ---------------- Envoltorios de colección ----------------


class _ColeccionRestringida:
    """Base: cualquier atributo no definido explícitamente se rechaza.

    Bloquea, entre otros: update_one, update_many, replace_one, delete_one,
    delete_many, find_one_and_update/replace/delete, bulk_write, insert_many,
    drop, rename, create_index, watch...
    """

    _operaciones: frozenset[str] = frozenset()

    def __init__(self, coleccion: AsyncCollection):
        object.__setattr__(self, "_c", coleccion)

    @property
    def name(self) -> str:
        return self._c.name

    def __getattr__(self, item: str) -> Any:  # solo se llama si el atributo NO existe
        raise OperacionInmutableError(self._c.name, item, "operación fuera de la lista blanca")

    def __setattr__(self, key: str, value: Any) -> None:
        raise AttributeError("Envoltorio inmutable")

    # Lecturas comunes
    def find(self, *args: Any, **kwargs: Any):
        return self._c.find(*args, **kwargs)

    async def find_one(self, *args: Any, **kwargs: Any):
        return await self._c.find_one(*args, **kwargs)

    async def count_documents(self, filtro: Mapping[str, Any], **kwargs: Any) -> int:
        return await self._c.count_documents(filtro, **kwargs)

    async def aggregate(self, pipeline: list[Mapping[str, Any]], **kwargs: Any):
        validar_pipeline_solo_lectura(self._c.name, pipeline)
        return await self._c.aggregate(pipeline, **kwargs)


class ColeccionAppendOnly(_ColeccionRestringida):
    """audit_logs y cambios_estado: solo insertar y leer."""

    _operaciones = OPERACIONES_APPEND_ONLY

    async def insert_one(
        self, documento: Mapping[str, Any], *, session: AsyncClientSession | None = None
    ) -> InsertOneResult:
        return await self._c.insert_one(documento, session=session)


class ColeccionInspecciones(_ColeccionRestringida):
    """inspecciones: insertar borradores, editarlos y firmarlos. Nada más.

    Una inspección FIRMADA no puede cambiar por ningún método de esta clase:
    todo update se combina con {estado: 'BORRADOR'} y no puede tocar los
    campos de identidad ni los de firma.
    """

    async def insert_one(
        self, documento: Mapping[str, Any], *, session: AsyncClientSession | None = None
    ) -> InsertOneResult:
        if documento.get("estado") != ESTADO_EDITABLE or "firma" in documento or "constancia" in documento:
            raise OperacionInmutableError(
                "inspecciones",
                "insert_one",
                "toda inspección (también una corrección) nace como BORRADOR y se firma después",
            )
        return await self._c.insert_one(documento, session=session)

    async def actualizar_borrador(
        self, filtro: Mapping[str, Any], update: Mapping[str, Any], *, session: AsyncClientSession | None = None
    ) -> UpdateResult:
        validar_update_borrador(update)
        resultado = await self._c.update_one(filtro_solo_borradores(filtro), update, session=session)
        if resultado.matched_count == 0:
            await self._explicar_fallo(filtro, "actualizar_borrador", session)
        return resultado

    async def sellar_firma(
        self,
        inspeccion_id: Any,
        perito_id: Any,
        firma: Mapping[str, Any],
        constancia: Mapping[str, Any],
        *,
        session: AsyncClientSession,
    ) -> Mapping[str, Any]:
        """Transición única BORRADOR → FIRMADA (RF-52). Debe ejecutarse en una transacción."""
        if session is None or not session.in_transaction:
            raise OperacionInmutableError(
                "inspecciones", "sellar_firma", "la firma debe ejecutarse dentro de una transacción"
            )
        doc = await self._c.find_one_and_update(
            {"_id": inspeccion_id, "perito_id": perito_id, "estado": ESTADO_EDITABLE},
            {
                "$set": {
                    "estado": "FIRMADA",
                    "firma": dict(firma),
                    "constancia": dict(constancia),
                    "updated_at": firma["firmado_en"],
                }
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if doc is None:
            await self._explicar_fallo({"_id": inspeccion_id}, "sellar_firma", session)
        return doc

    async def _explicar_fallo(
        self, filtro: Mapping[str, Any], operacion: str, session: AsyncClientSession | None
    ) -> None:
        existente = await self._c.find_one(filtro, {"estado": 1}, session=session)
        if existente is None:
            raise LookupError("Inspección no encontrada")
        if existente.get("estado") == "FIRMADA":
            raise OperacionInmutableError(
                "inspecciones", operacion, "la inspección está FIRMADA; use crear_version_correccion (RF-53, RNF-13)"
            )
        raise OperacionInmutableError("inspecciones", operacion, "el borrador pertenece a otro perito (RNF-14)")
