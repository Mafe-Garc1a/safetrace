"""Datos iniciales: configuración de sismos, catálogo de zonas y primer administrador general.

Ejecutar:  python -m db.semillas
Se puede ejecutar varias veces: no duplica ni sobrescribe lo que ya existe.
"""

from core.config import settings
from core.database import obtener_db
from core.fechas import ahora
from core.security import hash_contrasena

CONFIGURACION = {"_id": "parametros_sismo", "magnitud_minima": 5.0, "radio_afectacion_km": 200}  # RF-11, RF-12

# Lista de ejemplo: la definitiva está pendiente (RF-23)
ZONAS = [
    {"_id": "MURO_SALA", "nombre": "Muro de la sala", "grupo": "MUROS", "activo": True},
    {"_id": "MURO_HABITACION", "nombre": "Muro de habitación", "grupo": "MUROS", "activo": True},
    {"_id": "MURO_COCINA", "nombre": "Muro de la cocina", "grupo": "MUROS", "activo": True},
    {"_id": "MURO_BANO", "nombre": "Muro del baño", "grupo": "MUROS", "activo": True},
    {"_id": "COLUMNA", "nombre": "Columna", "grupo": "ESTRUCTURA", "activo": True},
    {"_id": "VIGA", "nombre": "Viga", "grupo": "ESTRUCTURA", "activo": True},
    {"_id": "PLACA_ENTREPISO", "nombre": "Placa de entrepiso", "grupo": "ESTRUCTURA", "activo": True},
    {"_id": "ESCALERA", "nombre": "Escalera", "grupo": "ESTRUCTURA", "activo": True},
    {"_id": "CUBIERTA", "nombre": "Cubierta o techo", "grupo": "EXTERIOR", "activo": True},
    {"_id": "FACHADA", "nombre": "Fachada", "grupo": "EXTERIOR", "activo": True},
    {"_id": "PISO", "nombre": "Piso", "grupo": "INTERIOR", "activo": True},
]


def cargar(db=None):
    db = db if db is not None else obtener_db()
    db["configuracion"].update_one({"_id": CONFIGURACION["_id"]}, {"$setOnInsert": CONFIGURACION}, upsert=True)
    for zona in ZONAS:
        db["zonas"].update_one({"_id": zona["_id"]}, {"$setOnInsert": zona}, upsert=True)
    print(f"ok  configuracion y {len(ZONAS)} zonas")

    if settings.admin_correo and settings.admin_contrasena:
        correo = settings.admin_correo.lower()
        momento = ahora()
        resultado = db["usuarios"].update_one(
            {"correo": correo},
            {
                "$setOnInsert": {
                    "correo": correo,
                    "contrasena_hash": hash_contrasena(settings.admin_contrasena),
                    "rol": "ADMINISTRADOR_GENERAL",
                    "nombre_completo": "Administrador general",
                    "activo": True,
                    "consentimiento": {"aceptado": True, "version_politica": "v1.0", "fecha": momento},
                    "schema_version": 2,
                    "creado_en": momento,
                    "actualizado_en": momento,
                }
            },
            upsert=True,
        )
        print("ok  administrador general " + ("creado" if resultado.upserted_id else "ya existía"))
    else:
        print("--  sin ADMIN_CORREO / ADMIN_CONTRASENA en .env: no se creó el administrador general")


if __name__ == "__main__":
    cargar()
