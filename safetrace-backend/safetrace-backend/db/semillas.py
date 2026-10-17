"""Datos iniciales: configuración de sismos, zonas, roles, módulos, permisos y usuarios iniciales
(administrador general y superadministrador).

Ejecutar:  python -m db.semillas
Se puede ejecutar varias veces: no duplica ni sobrescribe lo que ya existe (los permisos cambiados
desde la API se conservan). Si se agrega un módulo nuevo aquí, la próxima ejecución lo crea con sus permisos.
"""

from app.crud.modulo_permisos import dar_todos_los_permisos
from app.crud.roles import SUPERADMIN
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

ROLES = {
    SUPERADMIN: "Acceso total: gestiona roles, módulos, permisos y administradores",
    "ADMINISTRADOR_GENERAL": "Administra usuarios, peritos, solicitudes y configuración; consulta todo",
    "PERITO": "Registra, firma y corrige inspecciones asignadas",
    "PROPIETARIO": "Registra sus inmuebles, bitácora, revisiones y enlaces públicos",
}

# Nombre del módulo (el mismo de la variable `modulo` de cada router) → descripción
MODULOS = {
    "usuarios": "Administración de usuarios (RF-04 a RF-06)",
    "supresion": "Solicitudes de supresión de datos (RF-08, RF-09)",
    "auditoria": "Consulta de auditoría (RF-10)",
    "configuracion": "Magnitud mínima y radio de afectación (RF-11, RF-12)",
    "roles": "Roles",
    "modulos": "Módulos",
    "permisos": "Permisos por rol y módulo",
    "perfil_perito": "Perfil y documentos del perito (RF-13, RF-14)",
    "validacion_peritos": "Validación de credenciales de peritos (RF-15, RF-16)",
    "inmuebles": "Registro y consulta de inmuebles (RF-17 a RF-21)",
    "supervision_inmuebles": "Ver todos los inmuebles y su información, solo lectura (RNF-10)",
    "bitacora": "Eventos y evidencias (RF-22 a RF-27)",
    "archivos": "Autorización de subida de archivos (RF-24, RF-25)",
    "revisiones": "Revisión del propietario (RF-28, RF-29)",
    "solicitudes_inspeccion": "Solicitar inspecciones (RF-48)",
    "asignacion_peritos": "Asignar peritos a solicitudes (RF-49)",
    "inspecciones": "Registrar, editar, firmar y corregir inspecciones (RF-50 a RF-53)",
    "enlaces": "Enlaces públicos del inmueble (RF-59 a RF-61)",
    "analisis_ia": "Reintentar análisis de IA (RF-64)",
    "priorizacion": "Priorización de inmuebles por sismo (RF-66)",
}

# Permisos iniciales por rol (el SUPERADMIN recibe todos en todos los módulos).
# Las rutas sin permiso de módulo (consultas sobre un inmueble autorizado, /auth, /publico, /constancias,
# /interno) se controlan con la sesión y `obtener_inmueble_autorizado`.
PERMISOS = {
    "ADMINISTRADOR_GENERAL": {
        "usuarios": ("seleccionar", "actualizar"),
        "supresion": ("seleccionar", "actualizar"),
        "auditoria": ("seleccionar",),
        "configuracion": ("seleccionar", "actualizar"),
        "validacion_peritos": ("seleccionar", "actualizar"),
        "inmuebles": ("seleccionar",),
        "supervision_inmuebles": ("seleccionar",),
        "asignacion_peritos": ("seleccionar", "actualizar"),
        "analisis_ia": ("actualizar",),
        "priorizacion": ("seleccionar",),
    },
    "PERITO": {
        "perfil_perito": ("insertar", "seleccionar"),
        "archivos": ("insertar",),
        "inspecciones": ("insertar", "seleccionar", "actualizar"),
    },
    "PROPIETARIO": {
        "inmuebles": ("insertar", "seleccionar", "actualizar"),
        "bitacora": ("insertar", "actualizar"),
        "archivos": ("insertar",),
        "revisiones": ("insertar",),
        "solicitudes_inspeccion": ("insertar",),
        "enlaces": ("insertar", "seleccionar", "borrar"),
        "analisis_ia": ("actualizar",),
    },
}
ACCIONES = ("insertar", "actualizar", "seleccionar", "borrar")


def _cargar_permisos(db) -> None:
    momento = ahora()
    for rol, descripcion in ROLES.items():
        db["roles"].update_one(
            {"_id": rol},
            {
                "$setOnInsert": {
                    "nombre_rol": rol,
                    "descripcion": descripcion,
                    "estado": True,
                    "creado_en": momento,
                    "actualizado_en": momento,
                }
            },
            upsert=True,
        )
    for modulo, descripcion in MODULOS.items():
        db["modulos"].update_one(
            {"_id": modulo},
            {
                "$setOnInsert": {
                    "nombre_modulo": modulo,
                    "descripcion": descripcion,
                    "estado": True,
                    "creado_en": momento,
                    "actualizado_en": momento,
                }
            },
            upsert=True,
        )
        dar_todos_los_permisos(db, SUPERADMIN, modulo)
    for rol, modulos in PERMISOS.items():
        for modulo, acciones in modulos.items():
            db["permisos"].update_one(
                {"rol": rol, "modulo": modulo},
                {"$setOnInsert": {accion: accion in acciones for accion in ACCIONES}},
                upsert=True,
            )
    print(f"ok  {len(ROLES)} roles, {len(MODULOS)} módulos y sus permisos")


def _crear_usuario_inicial(db, correo: str, contrasena: str, rol: str, nombre: str) -> None:
    correo = correo.lower()
    momento = ahora()
    resultado = db["usuarios"].update_one(
        {"correo": correo},
        {
            "$setOnInsert": {
                "correo": correo,
                "contrasena_hash": hash_contrasena(contrasena),
                "rol": rol,
                "nombre_completo": nombre,
                "activo": True,
                "consentimiento": {"aceptado": True, "version_politica": "v1.0", "fecha": momento},
                "schema_version": 2,
                "creado_en": momento,
                "actualizado_en": momento,
            }
        },
        upsert=True,
    )
    print(f"ok  {nombre.lower()} " + ("creado" if resultado.upserted_id else "ya existía"))


def cargar(db=None):
    db = db if db is not None else obtener_db()
    db["configuracion"].update_one({"_id": CONFIGURACION["_id"]}, {"$setOnInsert": CONFIGURACION}, upsert=True)
    for zona in ZONAS:
        db["zonas"].update_one({"_id": zona["_id"]}, {"$setOnInsert": zona}, upsert=True)
    print(f"ok  configuracion y {len(ZONAS)} zonas")

    _cargar_permisos(db)

    usuarios_iniciales = [
        (settings.superadmin_correo, settings.superadmin_contrasena, SUPERADMIN, "Superadministrador"),
        (settings.admin_correo, settings.admin_contrasena, "ADMINISTRADOR_GENERAL", "Administrador general"),
    ]
    for correo, contrasena, rol, nombre in usuarios_iniciales:
        if correo and contrasena:
            _crear_usuario_inicial(db, correo, contrasena, rol, nombre)
        else:
            print(f"--  sin correo o contraseña en .env: no se creó el {nombre.lower()}")


if __name__ == "__main__":
    cargar()
