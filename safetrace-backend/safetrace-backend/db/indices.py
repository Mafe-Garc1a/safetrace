"""Crea los índices del Diseño DataBase V2 (sección 6). Ejecutar:  python -m db.indices

Se puede ejecutar varias veces: si un índice ya existe, MongoDB no lo duplica.
"""

from datetime import timedelta

from pymongo import ASCENDING as A
from pymongo import DESCENDING as D
from pymongo import GEOSPHERE

from core.database import obtener_db

INDICES = {
    "usuarios": [([("correo", A)], {"unique": True}), ([("rol", A), ("activo", A)], {})],
    "sesiones": [([("expira_en", A)], {"expireAfterSeconds": 0}), ([("token_hash", A)], {"unique": True})],
    "permisos": [([("rol", A), ("modulo", A)], {"unique": True})],
    "solicitudes_supresion": [([("usuario_id", A)], {}), ([("estado", A), ("fecha_solicitud", A)], {})],
    "peritos": [
        ([("usuario_id", A)], {"unique": True}),
        ([("matricula_profesional", A)], {"unique": True}),
        ([("estado_credencial", A)], {}),
    ],
    "inmuebles": [
        ([("ubicacion", GEOSPHERE)], {}),
        ([("propietario_id", A)], {}),
        ([("estado.codigo", A)], {}),
        ([("revision_semestral.proxima", A)], {}),
    ],
    "eventos": [([("inmueble_id", A), ("fecha_evento", D)], {})],
    "evidencias": [
        ([("inmueble_id", A), ("zona_id", A), ("creado_en", D)], {}),
        ([("origen.tipo", A), ("origen.id", A)], {}),
    ],
    "revisiones": [([("inmueble_id", A), ("fecha", D)], {})],
    "sismos": [
        ([("fuentes.fuente", A), ("fuentes.id_externo", A)], {"unique": True}),
        ([("fecha_hora", D)], {}),
        ([("epicentro", GEOSPHERE)], {}),
    ],
    "historial_estados": [([("inmueble_id", A), ("fecha", D)], {})],
    "solicitudes_inspeccion": [
        ([("inmueble_id", A), ("creado_en", D)], {}),
        ([("perito_id", A), ("estado", A)], {}),
        ([("estado", A)], {}),
    ],
    "inspecciones": [
        (
            [("constancia.codigo", A)],
            {"unique": True, "partialFilterExpression": {"constancia.codigo": {"$exists": True, "$type": "string"}}},
        ),
        ([("inmueble_id", A), ("es_version_activa", A)], {}),
        ([("constancia.estado", A), ("constancia.vigente_hasta", A)], {}),
    ],
    "enlaces_publicos": [([("codigo", A)], {"unique": True}), ([("inmueble_id", A), ("activo", A)], {})],
    "analisis_ia": [
        ([("clave_par", A)], {"unique": True}),
        ([("inmueble_id", A), ("creado_en", D)], {}),
        ([("estado", A)], {}),
    ],
    "indices_priorizacion": [
        ([("inmueble_id", A), ("sismo_id", A)], {"unique": True}),
        ([("sismo_id", A), ("valor", D)], {}),
    ],
    "tareas": [
        ([("estado", A), ("disponible_desde", A), ("creado_en", A)], {}),
        (
            [("finalizada_en", A)],
            {
                "expireAfterSeconds": int(timedelta(days=30).total_seconds()),
                "partialFilterExpression": {"estado": "COMPLETADA"},
            },
        ),
    ],
    "notificaciones": [([("usuario_id", A), ("creado_en", D)], {})],
    "auditoria": [
        ([("coleccion", A), ("documento_id", A), ("fecha", D)], {}),
        ([("actor.id", A), ("fecha", D)], {}),
        ([("fecha", D)], {}),
    ],
}


def crear(db=None):
    db = db if db is not None else obtener_db()
    for coleccion, indices in INDICES.items():
        for claves, opciones in indices:
            db[coleccion].create_index(claves, **opciones)
        print(f"ok  {coleccion}: {len(indices)} índices")


if __name__ == "__main__":
    crear()
