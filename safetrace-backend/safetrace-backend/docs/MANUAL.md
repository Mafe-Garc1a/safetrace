# Manual de mantenimiento del backend de SafeTrace

Guía para **modificar, ampliar o actualizar** la API. Para instalar y arrancar el proyecto por primera vez,
ver el [README](../README.md); aquí se asume que ya corre en local.

Contenido:

1. [Cómo está armado](#1-cómo-está-armado)
2. [Recorrido de una petición](#2-recorrido-de-una-petición)
3. [Mapa de módulos y colecciones](#3-mapa-de-módulos-y-colecciones)
4. [Convenciones que hay que respetar](#4-convenciones-que-hay-que-respetar)
5. [Recetas: cambios frecuentes paso a paso](#5-recetas-cambios-frecuentes-paso-a-paso)
6. [Reglas de negocio delicadas](#6-reglas-de-negocio-delicadas)
7. [Procesos en segundo plano: trabajador y n8n](#7-procesos-en-segundo-plano-trabajador-y-n8n)
8. [Pruebas y calidad](#8-pruebas-y-calidad)
9. [Configuración y despliegue](#9-configuración-y-despliegue)
10. [Actualizar dependencias](#10-actualizar-dependencias)
11. [Problemas comunes](#11-problemas-comunes)
12. [Pendientes conocidos](#12-pendientes-conocidos)
13. [Catálogo de endpoints](#13-catálogo-de-endpoints)

---

## 1. Cómo está armado

| Pieza | Tecnología | Archivo de entrada |
|---|---|---|
| API HTTP | FastAPI + Uvicorn (síncrona) | `main.py` |
| Base de datos | MongoDB con PyMongo **síncrono** | `core/database.py` |
| Validación | Pydantic v2 | `app/schemas/` |
| Autenticación | JWT (python-jose) + sesión guardada en MongoDB + bcrypt | `core/security.py`, `app/router/dependencies.py` |
| Trabajos lentos | Proceso aparte que consume la colección `tareas` | `trabajador/main.py` |
| Procesos programados | n8n (externo) llama a rutas `/interno/*` | `n8n/README.md` |

Hay **dos procesos** que comparten la misma base:

```
            ┌──────────────┐  /interno/* (X-Credencial-Servicio)
  n8n ─────►│              │
            │  API         │──── escribe ───►  MongoDB  ◄──── lee/escribe ───┐
 frontend ─►│  (uvicorn)   │                 (colección tareas)              │
            └──────────────┘                                          ┌──────┴──────┐
                                                                      │ trabajador  │
                                                                      │ (correo, IA)│
                                                                      └─────────────┘
```

La API nunca envía correos ni ejecuta el modelo de IA: deja una tarea en `tareas` y el trabajador la procesa.

### Las tres capas dentro de `app/`

Cada módulo funcional (A…K) tiene **un archivo con el mismo nombre** en cada capa:

| Capa | Responsabilidad | Qué NO debe hacer |
|---|---|---|
| `app/router/<modulo>.py` | Declarar rutas, pedir el usuario/rol con `Depends`, convertir ids con `a_object_id`, llamar al CRUD, traducir excepciones a `HTTPException`, devolver `serializar(...)`. | Consultar MongoDB directamente. |
| `app/schemas/<modulo>.py` | Modelos Pydantic de entrada (`Create`, `Update`) y salida (`Out`, `Page`). | Lógica de negocio. |
| `app/crud/<modulo>.py` | Hablar con MongoDB y aplicar las reglas de negocio. Funciones síncronas que reciben `db` como primer parámetro. | Lanzar `HTTPException` o leer el `Request`. |

`core/` contiene lo compartido por todos (configuración, conexión, seguridad, fechas, paginación, logs, errores).

---

## 2. Recorrido de una petición

Ejemplo: `PUT /inmuebles/{id}` (corregir un inmueble).

1. **`main.py`** tiene registrado `inmuebles.router` con `app.include_router(...)`.
2. **`app/router/inmuebles.py` → `actualizar_inmueble`**
   - `Depends(requiere_permiso(modulo, "actualizar"))` con `modulo = "inmuebles"` → `get_current_user` valida el
     JWT, busca la sesión por su hash, extiende la sesión 30 min y verifica que el usuario esté activo. Luego
     `verificar_permisos` busca en `permisos` si el rol tiene `actualizar` sobre `inmuebles` (y si el módulo está activo).
   - El cuerpo se valida con `InmuebleUpdate` (`app/schemas/inmuebles.py`).
   - `obtener_inmueble_autorizado(db, id, usuario, solo_propietario=True)` → 404 si no existe, 403 si no es suyo.
3. **`app/crud/inmuebles.py` → `actualizar_inmueble`** hace el `$set`, actualiza `actualizado_en` y llama a
   `auditoria.registrar(...)`.
4. El router responde `serializar(documento)`: `_id` pasa a `id` y todos los `ObjectId` a texto.
   FastAPI filtra la salida con `response_model=InmuebleOut`.

Errores que se manejan de forma global en `main.py`:

| Excepción | Respuesta |
|---|---|
| `core.errores.TransicionRechazada` | 409 con el mensaje |
| Cualquier `pymongo.errors.PyMongoError` | 500 `"Error de base de datos"` (el detalle solo va al log) |
| Errores de validación de Pydantic | 422 (comportamiento estándar de FastAPI) |

Las excepciones propias de cada CRUD (`CorreoDuplicado`, `PerfilDuplicado`, `EstadoNoPermitido`, `ReglaInspeccion`)
las traduce **el router** a `HTTPException` (normalmente 409).

---

## 3. Mapa de módulos y colecciones

**Regla de oro: cada colección tiene un solo archivo dueño, y solo ese archivo la escribe.** Los demás módulos
llaman a funciones del dueño.

| Módulo | Archivo (router / crud / schemas) | Colecciones de las que es dueño | RF |
|---|---|---|---|
| A · Acceso | `auth.py` | (usa las de `usuarios`) | RF-01–03, RF-07 |
| A · Usuarios | `usuarios.py` | `usuarios`, `sesiones`, `solicitudes_supresion` | RF-04–09 |
| A · Auditoría | `auditoria.py` | `auditoria` (solo insertar) | RF-10 |
| A · Configuración | `configuracion.py` | `configuracion` (un documento `_id="parametros_sismo"`) | RF-11–12 |
| Permisos (avisena) | `roles.py`, `modulos.py`, `permisos.py` / `modulo_permisos.py` | `roles`, `modulos`, `permisos` | RNF-08 |
| B · Peritos | `peritos.py` | `peritos` | RF-13–16 |
| C · Inmuebles | `inmuebles.py` | `inmuebles`, `zonas` | RF-17–21, RF-23 |
| D · Bitácora | `bitacora.py` | `eventos`, `evidencias`, campo `inmuebles.ultimos_eventos` | RF-22–27 |
| E · Revisiones | `revisiones.py` | `revisiones`, campo `inmuebles.revision_semestral` | RF-28–30 |
| F · Sismos | `sismos.py` | `sismos` | RF-31–37 |
| G · Estados | `estados.py` | `historial_estados`, campo `inmuebles.estado` | RF-38–47 |
| H · Inspecciones | `inspecciones.py` | `solicitudes_inspeccion`, `inspecciones` | RF-48–58 |
| I · Enlace público | `enlaces.py` | `enlaces_publicos` | RF-59–61 |
| J · IA e índice | `ia_indice.py` | `analisis_ia`, `indices_priorizacion`, campo `inmuebles.ultimo_indice` | RF-62–68 |
| K · Notificaciones | `notificaciones.py` | `tareas`, `notificaciones` | RF-69–71 |

Los campos calculados de `inmuebles` se escriben **solo** con estas funciones de `app/crud/inmuebles.py`:

| Campo | Función | Quién puede llamarla |
|---|---|---|
| `estado` | `escribir_estado` | solo `crud/estados.py` |
| `ultimo_indice` | `escribir_ultimo_indice` | solo `crud/ia_indice.py` |
| `ultimos_eventos` | `agregar_ultimo_evento` | solo `crud/bitacora.py` |
| `revision_semestral` | `escribir_revision_semestral`, `marcar_recordatorio_enviado` | solo `crud/revisiones.py` |

### Dependencias entre CRUD

```
sismos ──► estados ──► inmuebles
   │──► bitacora ──► ia_indice ──► notificaciones
   │──► ia_indice
   └──► notificaciones
revisiones ──► estados, bitacora, inmuebles, notificaciones
inspecciones ──► estados, bitacora, peritos, notificaciones
enlaces ──► inmuebles, bitacora, inspecciones, peritos, usuarios
casi todos ──► auditoria
```

Cuidado con los **imports circulares**: `bitacora` importa `ia_indice` e `ia_indice` importa `bitacora`.
Funciona porque ambos usan `from app.crud import x as crud_x` y solo acceden a sus funciones dentro de otras
funciones. No cambie esto por `from app.crud.bitacora import funcion` en esos archivos.

---

## 4. Convenciones que hay que respetar

**Nombres**
- Todo en español y `snake_case`, igual que los campos en MongoDB.
- Fechas de creación/actualización: `creado_en` y `actualizado_en`.
- Documentos versionados con `schema_version` (actualmente `2` en `usuarios`, `inmuebles`, `peritos`).

**Ids y respuestas**
- Un id que llega en la URL o en el cuerpo se convierte con `a_object_id(valor)` (responde 400 si es inválido).
- Toda respuesta con documentos de MongoDB pasa por `serializar(...)`.
- En los esquemas `Out`, los ids son `str`.

**Fechas**
- Use siempre `core.fechas.ahora()` (UTC, recortada a milisegundos). No use `datetime.now()` ni `datetime.utcnow()`.
- Fechas recibidas del cliente: `en_utc(fecha)` antes de guardarlas.
- Sumar meses: `sumar_meses(fecha, n)`.

**Coordenadas**
- GeoJSON `{"type": "Point", "coordinates": [longitud, latitud]}`; la longitud va **primero**.

**Listados**
- Todo historial va paginado con `core.paginacion.Pagina` (máximo 50 por página):
  ```python
  def listar(pagina: Pagina = Depends(), db: Database = Depends(get_db), ...):
      datos, total = crud_x.listar(db, filtros, pagina.saltar, pagina.tamano)
      return pagina.respuesta(serializar(datos), total)
  ```
  Las funciones CRUD de listados devuelven `(datos, total)`.

**Permisos**
- Ruta con sesión: `usuario: dict = Depends(get_current_user)`.
- Ruta protegida por permiso (como en avisena): el router declara `modulo = "nombre"` arriba y la ruta pide
  `usuario: dict = Depends(requiere_permiso(modulo, "insertar"))`. Acciones: `insertar`, `actualizar`,
  `seleccionar`, `borrar`. Si un router cubre varias áreas, declara varias variables (`modulo_validacion = ...`).
- Para decidir dentro de una ruta (no para bloquearla), use `verificar_permisos(db, usuario["rol"], modulo, accion)`
  o `puede_supervisar(db, usuario)`. **No compare `usuario["rol"]` con un texto** para dar acceso: así el
  permiso no se puede administrar.
- Ruta para n8n: `dependencies=[Depends(requiere_servicio_n8n)]` y prefijo `/interno/`.
- Ruta sobre un inmueble: `obtener_inmueble_autorizado(db, inmueble_id, usuario, solo_propietario=...)`.
  Con `solo_propietario=True` solo el dueño pasa (para escribir); con `False` también pasan quienes tienen
  `supervision_inmuebles.seleccionar` (administrador y superadmin) y el perito asignado (solo lectura).
  El permiso de módulo dice *qué* puede hacer el rol; esta función dice *sobre qué inmuebles*. Se necesitan los dos.
- Ruta pública (sin cuenta): no lleva ninguna dependencia de usuario. Hoy solo `/publico/{codigo}` y `/constancias/{codigo}`.

**Auditoría y datos personales (RNF-20)**
- Toda acción que cambia datos de negocio llama a `auditoria.registrar(db, coleccion, id, ACCION, actor, cambios)`.
  El actor se arma con `actor_usuario(usuario)` o `actor_proceso("nombre")`.
- **Nunca** guarde nombre, correo, documento ni teléfono en `cambios`, en `tareas.datos` ni en los logs.
  En `tareas.datos` van solo ids.
- Use `core.registro.obtener_logger("nombre")` para los logs.

**Estilo**
- Línea máxima 120 caracteres; `ruff` ordena los imports. VS Code formatea al guardar (`.vscode/settings.json`).
- Las llamadas a `pedir_transicion` con muchos argumentos llevan `# fmt: skip` para conservar la forma.

---

## 5. Recetas: cambios frecuentes paso a paso

### 5.1 Agregar un endpoint a un módulo existente

Ejemplo: permitir al propietario consultar un evento puntual de la bitácora.

1. **Schema** (si hace falta uno nuevo) en `app/schemas/bitacora.py`. Aquí ya existe `EventoOut`.
2. **CRUD** en `app/crud/bitacora.py`: ya existe `obtener_evento(db, evento_id)`. Si no existiera, créela ahí.
3. **Router** en `app/router/bitacora.py`:
   ```python
   @router.get(
       "/eventos/{evento_id}",
       response_model=EventoOut,
       summary="Detalle de un evento",
       description="RF-26",
   )
   def obtener_evento(evento_id: str, db: Database = Depends(get_db), usuario: dict = Depends(get_current_user)):
       evento = crud_bitacora.obtener_evento(db, a_object_id(evento_id))
       if evento is None:
           raise HTTPException(status_code=404, detail="Evento no encontrado")
       obtener_inmueble_autorizado(db, evento["inmueble_id"], usuario)  # permiso sobre el inmueble
       return serializar(evento)
   ```
4. **Prueba** en `tests/` (ver sección 8).
5. No hace falta tocar `main.py`: el router del módulo ya está registrado.

Ponga siempre el RF en `description`: así aparece en `/docs` y se puede rastrear contra la ERS.

### 5.2 Agregar un campo a una colección

Ejemplo: agregar `estrato` al inmueble.

1. **Schemas** (`app/schemas/inmuebles.py`):
   - En `InmuebleBase` (entra y sale): `estrato: int | None = Field(default=None, ge=1, le=6)`.
   - En `InmuebleUpdate`: el mismo campo, opcional.
   - Si debe ser obligatorio en registros nuevos, pero ya hay documentos sin él, deje `None` por defecto en `Out`
     para no romper la lectura de los viejos.
2. **CRUD**: `crear_inmueble` usa `inmueble.model_dump(...)`, así que el campo se guarda solo. Revise si alguna
   proyección lo excluye (por ejemplo `datos_publicos`; agréguelo ahí **solo** si no identifica al propietario).
3. **Índice** si se va a filtrar por él: agréguelo en `db/indices.py` y ejecute `python -m db.indices`.
4. **Documentos existentes**: si necesitan un valor, cree una migración (sección 5.8) y suba `schema_version`.
5. Actualice `http/ejemplos.http` y la fixture `inmueble` de `tests/conftest.py` si el campo es obligatorio.

### 5.3 Crear un módulo nuevo

Ejemplo: módulo L · Mensajes.

1. Cree los tres archivos: `app/schemas/mensajes.py`, `app/crud/mensajes.py`, `app/router/mensajes.py`.
2. En el docstring del CRUD declare qué colecciones le pertenecen (como los demás archivos).
3. El router empieza con `router = APIRouter()`.
4. Regístrelo en `main.py`:
   ```python
   from app.router import mensajes
   app.include_router(mensajes.router, tags=["Mensajes"])
   ```
5. Agregue sus índices en `db/indices.py`.
6. Agregue la fila en la tabla de la sección 3 de este manual y en el README.

### 5.4 Agregar un tipo de tarea para el trabajador

Ejemplo: generar el PDF de la constancia.

1. Cree `trabajador/tareas/generar_pdf.py` con:
   ```python
   def ejecutar(db, tarea: dict) -> None:
       """Lanza una excepción si falla: el bucle reintenta o deja la tarea FALLIDA."""
       inspeccion_id = tarea["datos"]["inspeccion_id"]
       ...

   def al_fallar(db, tarea: dict, definitiva: bool) -> None:  # opcional
       ...
   ```
   La función debe ser **idempotente**: puede ejecutarse más de una vez si un intento anterior falló a medias.
2. Regístrelo en `trabajador/tareas/__init__.py`:
   ```python
   EJECUTORES = {..., "GENERAR_PDF": generar_pdf}
   ```
3. Encole la tarea desde el CRUD dueño del dato:
   `crud_notificaciones.encolar_tarea(db, "GENERAR_PDF", {"inspeccion_id": inspeccion["_id"]})`.
4. Reinicie el trabajador (no tiene recarga automática).

Si un tipo de tarea no tiene ejecutor, la tarea falla con `NotImplementedError` y se reintenta hasta `max_intentos`.

### 5.5 Agregar un tipo de notificación

1. Agregue el nombre a `TIPOS_NOTIFICACION` en `app/crud/notificaciones.py`.
2. Llame a `crud_notificaciones.notificar(db, usuario_id, "NUEVO_TIPO", {"tipo": "...", "id": ...})`.
3. Cuando se integre el proveedor de correo, cree la plantilla con ese mismo nombre (`core/email.py` recibe
   el tipo como `plantilla`).

### 5.6 Cambiar la máquina de estados del inmueble

Todo está en `app/crud/estados.py`:

- `EstadoInmueble`: los 5 estados (el número es el que se guarda en `estado.codigo`).
- `TRANSICIONES`: pares `(desde, hacia)` permitidos, con el RF que los justifica.
- `CAUSAS`: motivos válidos para el historial.

Para agregar una transición: agregue el par a `TRANSICIONES`, la causa a `CAUSAS` si es nueva, y una línea en
`tests/unit/test_maquina_estados.py`. **Nunca** cambie el estado con un `update_one` directo: use siempre
`crud_estados.pedir_transicion(...)`, que valida el paso, controla la concurrencia y escribe el historial.

### 5.7 Agregar o cambiar un índice

1. Edite el diccionario `INDICES` en `db/indices.py`.
2. Ejecute `python -m db.indices` contra cada base (local, Atlas).
3. Crear un índice nuevo es seguro y repetible. **Cambiar las opciones** de uno existente (por ejemplo volverlo
   `unique`) falla con `IndexOptionsConflict`: primero bórrelo en `mongosh`
   (`db.coleccion.dropIndex("nombre")`) o hágalo desde una migración.

### 5.8 Escribir una migración

Las migraciones van en `db/migraciones/`, numeradas: `0001_descripcion.py`, `0002_...`. Plantilla:

```python
"""0001 · Agrega `estrato: null` a los inmuebles existentes. Ejecutar: python -m db.migraciones.0001_estrato"""

from core.database import obtener_db


def aplicar(db=None):
    db = db if db is not None else obtener_db()
    r = db["inmuebles"].update_many(
        {"schema_version": 2, "estrato": {"$exists": False}},
        {"$set": {"estrato": None, "schema_version": 3}},
    )
    print(f"ok  {r.modified_count} inmuebles migrados")


if __name__ == "__main__":
    aplicar()
```

Reglas: debe poder ejecutarse varias veces sin efecto extra (filtre por `schema_version`), sube
`schema_version` en lo que toca, y se prueba antes contra una copia de la base. Ejecútela siempre con
`python -m ...` desde la raíz del proyecto (así encuentra `core`); un nombre que empieza por número funciona con
`-m`, pero no se puede usar en una sentencia `import`.

### 5.9 Cambiar los datos iniciales (zonas, configuración)

Edite `ZONAS` o `CONFIGURACION` en `db/semillas.py` y ejecute `python -m db.semillas`.
La semilla usa `$setOnInsert`: **agrega lo que falta pero no modifica lo que ya existe**. Para cambiar el
nombre de una zona ya cargada o desactivarla (`activo: false`), hágalo con una migración o en `mongosh`.
No borre zonas: hay evidencias que las referencian.

La magnitud mínima y el radio se cambian en producción desde `PUT /admin/configuracion` (queda auditado),
no desde la semilla.

### 5.10 Agregar una variable de entorno

1. Agréguela a la clase `Settings` en `core/config.py` (con valor por defecto).
2. Agréguela a `.env.example` con un comentario.
3. Configúrela en cada despliegue. Úsela con `from core.config import settings`.

### 5.11 Permisos: proteger una ruta, crear un rol, cambiar permisos

**Proteger una ruta nueva**
1. En el router, use el `modulo` que ya declara o declare uno nuevo (`modulo_reportes = "reportes"`).
2. En la ruta: `usuario: dict = Depends(requiere_permiso(modulo_reportes, "seleccionar"))`.
3. Si el módulo es nuevo, agréguelo a `MODULOS` en `db/semillas.py` y, si otros roles deben usarlo, a `PERMISOS`.
   La prueba `test_todo_modulo_usado_en_los_routers_existe_en_las_semillas` falla si olvida este paso.
4. Ejecute `python -m db.semillas` en cada base. El SUPERADMIN recibe todos los permisos del módulo nuevo.

**Crear un rol o cambiar permisos sin tocar código** (como superadmin, desde `/docs`):
- `POST /admin/roles` `{"nombre_rol": "AUDITOR", "descripcion": "..."}`.
- `POST /admin/permisos` `{"rol": "AUDITOR", "modulo": "auditoria", "seleccionar": true}`.
- `PUT /admin/permisos/{modulo}/{rol}` `{"insertar": false}` cambia solo lo enviado.
- `PATCH /admin/usuarios/{id}/rol` `{"rol": "AUDITOR"}` asigna el rol (cierra las sesiones del usuario).

**Reglas que no se pueden saltar**
- El SUPERADMIN tiene todo y sus permisos no se modifican; su rol no se desactiva; los módulos `roles`, `modulos`
  y `permisos` no se desactivan (así nadie queda fuera del sistema).
- Solo un SUPERADMIN asigna o quita el rol SUPERADMIN o modifica a un usuario SUPERADMIN.
- Desactivar un rol cierra las sesiones de sus usuarios y les impide iniciar sesión. Un módulo inactivo niega el
  acceso a todos (salvo los tres protegidos).
- Los permisos **no saltan las reglas de negocio**: aunque un rol tenga `inspecciones.actualizar`, solo firma un
  perito VALIDADO y asignado; aunque tenga `bitacora.borrar`, las evidencias no se borran (RNF-13, RNF-16).
- `semillas.py` usa `$setOnInsert`: volver a ejecutarlo **no** revierte los permisos cambiados desde la API.
  Para cambiar el permiso inicial de una base ya cargada, use la API.

---

## 6. Reglas de negocio delicadas

Antes de tocar estos puntos, lea el docstring del archivo correspondiente.

| Regla | Dónde | Por qué importa |
|---|---|---|
| Solo G cambia el estado, vía `pedir_transicion`. | `crud/estados.py` | Control de concurrencia con `estado.version` y transacción si hay réplicas. Si otro proceso cambió el estado lanza `TransicionRechazada` (409). |
| La IA y el índice nunca cambian el estado. | `crud/ia_indice.py` | RNF-37. |
| Eventos y evidencias no se modifican ni se borran. | `crud/bitacora.py` | Una evidencia errónea se marca `INVALIDA`/`REEMPLAZADA` con motivo. |
| Una inspección firmada es inmutable. | `crud/inspecciones.py` | Corregir = nueva versión (`crear_correccion`) que se firma aparte. |
| La huella SHA-256 cubre `contenido_firmable(...)`. | `crud/inspecciones.py` | **Si agrega o quita campos de esa función, todas las constancias ya emitidas dejarán de verificar como íntegras.** Si hay que cambiarla, versionar la función y guardar la versión usada en la firma. |
| Solo un perito `VALIDADO` se asigna, registra y firma. | `crud/peritos.py` → `perito_habilitado` | RNF-14, RNF-15. |
| La firma exige la contraseña del perito. | `router/inspecciones.py` → `firmar_inspeccion` | Método `CONFIRMACION_CONTRASENA`. |
| El enlace público y la verificación de constancias no exponen estado ni datos del propietario. | `crud/enlaces.py`, `crud/inmuebles.py` → `datos_publicos` | RNF-18, RNF-19. Revise esto al agregar campos. |
| Un sismo repetido no se duplica; SGC y USGS se emparejan (±2 min, ≤100 km). | `crud/sismos.py` | Constantes `VENTANA_EMPAREJAR`, `DISTANCIA_EMPAREJAR_KM`, `FUENTE_PRINCIPAL`. |
| Sesión: JWT + documento en `sesiones` con TTL. | `crud/usuarios.py` | Cerrar sesión, desactivar o cambiar rol borra las sesiones. Cambiar `MINUTOS_SESION` afecta solo a sesiones nuevas o renovadas. |
| El administrador no puede desactivarse ni cambiarse el rol a sí mismo. | `router/usuarios.py` | Evita quedarse sin administradores. |

---

## 7. Procesos en segundo plano: trabajador y n8n

### Trabajador (`trabajador/main.py`)

- Bucle infinito: `tomar_tarea` (atómica, `PENDIENTE → PROCESANDO`), ejecuta y marca `COMPLETADA`.
- Si falla y quedan intentos vuelve a `PENDIENTE` con espera creciente (60 s × intento); al agotar `max_intentos`
  (3 por defecto) queda `FALLIDA`.
- Las tareas `COMPLETADA` se borran solas a los 30 días (índice TTL).
- Se ejecuta con `python -m trabajador.main` o con la configuración **Trabajador** de VS Code.
- Para varias instancias, cambie `NOMBRE` (hoy fijo en `"trabajador-1"`) para distinguirlas en `tomada_por`.

Ver tareas atascadas en `mongosh`:
```js
db.tareas.find({ estado: { $in: ["FALLIDA", "PROCESANDO"] } }).sort({ creado_en: -1 })
```
Una tarea en `PROCESANDO` durante mucho tiempo indica que el trabajador se cayó a mitad. Hoy no hay recuperación
automática: devuélvala a mano con `{$set: {estado: "PENDIENTE"}}`.

### n8n

n8n **no escribe en la base**: llama a la API con el encabezado `X-Credencial-Servicio`.

| Ruta | Frecuencia | Función CRUD |
|---|---|---|
| `POST /interno/sismos` | ≤ 5 min | `crud.sismos.recibir_sismo` |
| `POST /interno/constancias/vencimientos` | diaria | `crud.inspecciones.vencer_constancias` |
| `POST /interno/peritos/vencimientos` | diaria | `crud.peritos.marcar_vencidos` |
| `POST /interno/recordatorios-semestrales` | diaria | `crud.revisiones.enviar_recordatorios` |

Todas son repetibles sin efecto duplicado. Exporte los flujos a `n8n/*.json` cada vez que los cambie.

---

## 8. Pruebas y calidad

```powershell
pytest                     # todas (no necesitan MongoDB)
pytest tests/unit          # solo unitarias
pytest -k sismo            # por nombre
pytest --cov=app --cov=core --cov-report=term-missing
ruff check .               # lint
ruff check . --fix         # corrige lo automático
ruff format .              # formato
```

- Las pruebas usan **mongomock** (`tests/conftest.py`): cada prueba recibe una base en memoria limpia con
  índices y semillas cargados.
- mongomock **no soporta** `$geoWithin` ni transacciones. Por eso `conftest.py` reemplaza
  `crud_inmuebles.buscar_en_radio` con un filtro en Python. Si agrega otra consulta geoespacial, haga lo mismo
  o escriba la prueba en `tests/integracion/` contra un MongoDB real (`MONGO_URI_PRUEBAS`).
- Fixtures disponibles: `db`, `cliente`, `admin`, `propietario`, `inmueble` (las tres últimas devuelven las
  cabeceras `Authorization` o el inmueble creado), y las funciones `registrar(...)` e `iniciar_sesion(...)`.
  `N8N` son las cabeceras para las rutas `/interno/*`.

Plantilla de prueba de endpoint:

```python
def test_propietario_consulta_su_inmueble(cliente, propietario, inmueble):
    r = cliente.get(f"/inmuebles/{inmueble['id']}", headers=propietario)
    assert r.status_code == 200
    assert r.json()["estado"]["codigo"] == 1


def test_otro_usuario_no_ve_el_inmueble(cliente, inmueble):
    from tests.conftest import iniciar_sesion, registrar
    registrar(cliente, "otro@correo.com")
    r = cliente.get(f"/inmuebles/{inmueble['id']}", headers=iniciar_sesion(cliente, "otro@correo.com"))
    assert r.status_code == 403
```

El escenario completo (sismo → revisión → solicitud → firma → constancia → enlace) está en
`tests/test_flujo_sismo.py`; es el mejor punto de partida para entender cómo se encadenan los módulos.

**CI** (`.github/workflows/ci.yml`): en cada pull request y push a `main` ejecuta `ruff check .` y `pytest`
con Python 3.12. Debe quedar en verde antes de unir.

Prueba manual: `http/ejemplos.http` (extensión REST Client) o `http://localhost:8000/docs` con **Authorize**.

---

## 9. Configuración y despliegue

Variables (`core/config.py`, plantilla en `.env.example`):

| Variable | Uso | Por defecto |
|---|---|---|
| `ENTORNO` | `local` / `pruebas` / `produccion` | `local` |
| `MONGO_URI`, `MONGO_DB` | Conexión | `mongodb://localhost:27017`, `safetrace` |
| `JWT_SECRET` | Firma de tokens. **Obligatorio en producción**; cambiarlo invalida todas las sesiones. | valor inseguro |
| `JWT_ALGORITHM` | | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Vida máxima del token | `480` |
| `MINUTOS_SESION` | Cierre por inactividad | `30` |
| `CREDENCIAL_SERVICIO_N8N` | Rutas `/interno/*` | valor inseguro |
| `SUPERADMIN_CORREO`, `SUPERADMIN_CONTRASENA` | Superadministrador (`db.semillas`) | vacío |
| `ADMIN_CORREO`, `ADMIN_CONTRASENA` | Primer administrador (`db.semillas`) | vacío |
| `PROVEEDOR_ARCHIVOS_URL` | Subida de archivos | vacío → 501 |
| `CORREO_API_KEY` | Correo | vacío → se simula en el log |

Despliegue (`Procfile`): dos procesos, `web` (uvicorn) y `worker` (trabajador). Ambos necesitan las mismas
variables. Después de desplegar un cambio que toque índices o semillas, ejecute `python -m db.indices` y
`python -m db.semillas` contra la base de producción.

Antes de producción conviene revisar: CORS está abierto a cualquier origen (`allow_origins=["*"]` en `main.py`);
restrínjalo al dominio del frontend.

---

## 10. Actualizar dependencias

- `requirements.txt` (ejecución) y `requirements-dev.txt` (pruebas y lint, incluye el anterior) usan versiones
  mínimas (`>=`). Para actualizar:
  ```powershell
  venv\Scripts\activate
  pip install -U -r requirements-dev.txt
  pytest; ruff check .
  ```
- Si algo se rompe tras actualizar, fije la versión que funcionaba (`paquete==x.y.z`) y abra una tarjeta.
- Puntos sensibles: **PyMongo** (el código usa la API síncrona; `pymongo.asynchronous` no se usa),
  **mongomock** (suele ir detrás de PyMongo), **bcrypt** (las contraseñas tienen máximo 72 bytes, por eso
  `max_length=72` en `UsuarioCreate`) y **Pydantic** (v2: `model_dump`, `model_validator`).
- Python mínimo: 3.12 (`pyproject.toml`, `UTC` de `datetime`).

---

## 11. Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| `ServerSelectionTimeoutError` al arrancar o en `python -m core.database` | MongoDB apagado, URI mal escrita o IP no permitida en Atlas | Revisar `MONGO_URI`, el servicio de Windows o *Network Access* de Atlas. |
| Todas las rutas responden 401 "Sesión cerrada o vencida" | Pasaron 30 min sin actividad, se cambió `JWT_SECRET` o se cambió el rol | Iniciar sesión de nuevo. |
| 403 "Sin permiso para esta acción" en rutas que antes funcionaban, o 401 "Rol inactivo" al entrar | La base no tiene cargados `roles`, `modulos` y `permisos` (por ejemplo, tras actualizar el código), o el permiso/módulo/rol se desactivó | `python -m db.semillas`; luego revisar `GET /admin/permisos?rol=...` como superadmin. |
| 500 "Error de base de datos" | Cualquier `PyMongoError` | Ver el log de la API: muestra el tipo de excepción. |
| 409 "El estado del inmueble cambió" | Otra operación cambió el estado entre la lectura y la escritura | Volver a consultar el estado y repetir. |
| `DuplicateKeyError` inesperado | Índice único (correo, matrícula, código, etc.) | Esperado: el CRUD debería traducirlo; si no, capturarlo allí. |
| Búsqueda por radio vacía en local | Falta el índice `2dsphere` | `python -m db.indices`. |
| La prueba geoespacial pasa en local pero no en mongomock | mongomock no soporta `$geoWithin` | Ver sección 8. |
| Correos no llegan | `CORREO_API_KEY` vacía (se simulan) o trabajador apagado | Revisar el log del trabajador y la colección `tareas`. |
| Análisis de IA quedan `FALLIDO` | El modelo no está implementado aún | Esperado hasta integrar el modelo (sección 12). |

---

## 12. Pendientes conocidos

| Qué | Dónde | Estado actual |
|---|---|---|
| Pesos del índice de priorización | `crud/ia_indice.py` → `calcular` | `NotImplementedError`; el marcado por sismo continúa sin índice. Al definirlos, subir `FORMULA_VERSION`. |
| Modelo de comparación de fotos | `crud/ia_indice.py` → `cargar_modelo`, `comparar` | Los análisis fallan tras 3 intentos. Pesos en `modelos_ia/`. Al cambiar de modelo, subir `MODELO_VERSION`. |
| Proveedor de archivos | `core/almacenamiento.py` | `POST /archivos/autorizacion` responde 501. |
| Proveedor de correo | `core/email.py` | Sin API key, se simula. |
| Criterio SGC/USGS definitivo | `crud/sismos.py` | Propuesta ±2 min y ≤100 km. |
| Lista definitiva de zonas | `db/semillas.py` | Lista de ejemplo. |
| Validadores `$jsonSchema` | `db/validadores/` | Sin crear. |
| Migraciones | `db/migraciones/` | Ninguna todavía. |
| Recuperar tareas atascadas en `PROCESANDO` | `crud/notificaciones.py` | Manual (sección 7). |
| `core/mongo.py` | — | Borrador **sin uso**: está escrito para PyMongo asíncrono (el resto del proyecto es síncrono), sus nombres de campos no coinciden con los de `crud/inspecciones.py` (`estado: "BORRADOR"` frente a `firma.firmada`) y es el único archivo que no pasa `ruff check`, así que el CI falla mientras exista. Hay que decidir si se adapta o se borra. |

---

## 13. Catálogo de endpoints

Roles con permiso **según las semillas iniciales** (el superadmin entra a todas; los permisos pueden cambiarse
desde `/admin/permisos`): **P** propietario, **R** perito, **A** administrador general, **SA** solo superadmin,
**S** cualquier sesión, **N** n8n, **—** público.

| Método y ruta | Rol | Archivo |
|---|---|---|
| `GET /`, `GET /salud` | — | `main.py` |
| `POST /auth/registro` | — | `auth.py` |
| `POST /auth/sesion` · `DELETE /auth/sesion` · `GET /auth/yo` · `GET /auth/yo/permisos` | — / S / S / S | `auth.py` |
| `GET·POST /admin/roles` · `GET·PUT /admin/roles/{rol}` · `PATCH /admin/roles/{rol}/estado` | SA | `roles.py` |
| `GET·POST /admin/modulos` · `GET·PUT /admin/modulos/{modulo}` · `PATCH /admin/modulos/{modulo}/estado` | SA | `modulos.py` |
| `GET·POST /admin/permisos` · `GET·PUT /admin/permisos/{modulo}/{rol}` | SA | `permisos.py` |
| `GET /admin/usuarios` | A | `usuarios.py` |
| `PATCH /admin/usuarios/{id}/estado` · `PATCH /admin/usuarios/{id}/rol` | A | `usuarios.py` |
| `POST /cuentas/supresion` | S | `usuarios.py` |
| `GET /admin/solicitudes-supresion` · `POST /admin/solicitudes-supresion/{id}/atencion` | A | `usuarios.py` |
| `GET /admin/auditoria` | A | `auditoria.py` |
| `GET /admin/configuracion` · `PUT /admin/configuracion` | A | `configuracion.py` |
| `POST /peritos/perfil` · `POST /peritos/documentos` · `GET /peritos/mi-estado` | R | `peritos.py` |
| `GET /admin/peritos` · `POST /admin/peritos/{id}/validacion` · `POST /admin/peritos/{id}/inconsistencia` | A | `peritos.py` |
| `POST /interno/peritos/vencimientos` | N | `peritos.py` |
| `POST /inmuebles` · `PUT /inmuebles/{id}` | P | `inmuebles.py` |
| `GET /inmuebles` | P, A | `inmuebles.py` |
| `GET /inmuebles/{id}` · `GET /zonas` | S | `inmuebles.py` |
| `POST /inmuebles/{id}/eventos` · `POST /inmuebles/{id}/evidencias` · `PATCH /evidencias/{id}/invalidacion` | P | `bitacora.py` |
| `GET /inmuebles/{id}/linea-cronologica` | S | `bitacora.py` |
| `POST /archivos/autorizacion` | P, R | `bitacora.py` |
| `POST /peritos/archivos/autorizacion` | R | `bitacora.py` |
| `POST /inmuebles/{id}/revisiones` | P | `revisiones.py` |
| `GET /inmuebles/{id}/revisiones` | S | `revisiones.py` |
| `POST /interno/recordatorios-semestrales` | N | `revisiones.py` |
| `POST /interno/sismos` | N | `sismos.py` |
| `GET /sismos` · `GET /sismos/{id}` | S | `sismos.py` |
| `GET /inmuebles/{id}/estado` · `GET /inmuebles/{id}/historial-estados` | S | `estados.py` |
| `POST /inmuebles/{id}/solicitudes-inspeccion` | P | `inspecciones.py` |
| `GET /inmuebles/{id}/solicitudes-inspeccion` · `GET /inmuebles/{id}/inspecciones` · `GET /inspecciones/{id}` | S | `inspecciones.py` |
| `GET /admin/solicitudes-inspeccion` · `POST /admin/solicitudes-inspeccion/{id}/asignacion` | A | `inspecciones.py` |
| `GET /peritos/solicitudes` · `POST /solicitudes-inspeccion/{id}/inspeccion` | R | `inspecciones.py` |
| `PUT /inspecciones/{id}` · `POST /inspecciones/{id}/firma` · `POST /inspecciones/{id}/correccion` | R | `inspecciones.py` |
| `GET /constancias/{codigo}` | — | `inspecciones.py` |
| `POST /interno/constancias/vencimientos` | N | `inspecciones.py` |
| `POST /inmuebles/{id}/enlaces` · `GET /inmuebles/{id}/enlaces` · `DELETE /enlaces/{id}` | P | `enlaces.py` |
| `GET /publico/{codigo}` | — | `enlaces.py` |
| `GET /inmuebles/{id}/analisis-ia` · `GET /inmuebles/{id}/indice` | S | `ia_indice.py` |
| `POST /analisis-ia/{id}/reintento` | P, A | `ia_indice.py` |
| `GET /admin/sismos/{id}/priorizacion` | A | `ia_indice.py` |
| `GET /tareas/{id}` · `GET /notificaciones` | S | `notificaciones.py` |

"S" en rutas sobre un inmueble significa sesión **y** permiso sobre ese inmueble (`obtener_inmueble_autorizado`).
El detalle de cada cuerpo y respuesta está siempre actualizado en `http://localhost:8000/docs`.

Mantenga este manual al día: si un cambio contradice algo de aquí, actualice la sección en el mismo pull request.
