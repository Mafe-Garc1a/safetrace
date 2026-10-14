# SafeTrace · Backend

API en **Python + FastAPI** y **MongoDB**, con los 11 módulos de la ERS v2 (A a K) y las 20 colecciones
del *Diseño DataBase V2*. Sigue la misma organización que el backend de **avisena**: `main.py` y `core/`
en la raíz, y dentro de `app/` una carpeta por capa (`router`, `crud`, `schemas`) con un archivo por módulo.

No usa Docker: se ejecuta con un entorno virtual de Python y una base MongoDB (Atlas o instalada en el equipo).

## Cómo arrancar (Windows, VS Code)

1. Crear el entorno virtual e instalar dependencias (en la carpeta `safetrace-backend`):
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements-dev.txt
   copy .env.example .env
   ```
2. Tener una base MongoDB y poner su dirección en `MONGO_URI` del `.env` (ver la sección siguiente).
3. Completar en `.env` `JWT_SECRET`, `CREDENCIAL_SERVICIO_N8N`, `ADMIN_CORREO` y `ADMIN_CONTRASENA`.
4. Crear índices y datos iniciales (configuración, zonas y el primer administrador general):
   ```powershell
   python -m core.database      # ¿Conexión exitosa?: True
   python -m db.indices
   python -m db.semillas
   ```
5. Levantar la API: pestaña **Ejecutar y depurar** → **API (uvicorn)**, o `uvicorn main:app --reload`.
   Abrir http://localhost:8000/docs; el botón **Authorize** inicia sesión (en *username* va el correo).
6. Levantar el trabajador (correos y comparación de fotos) en otra terminal: `python -m trabajador.main`.
7. Pruebas: pestaña **Testing** de VS Code, o `pytest`. No necesitan MongoDB (usan mongomock).

## Base de datos sin Docker

| Opción | Cuándo | `MONGO_URI` |
|---|---|---|
| **MongoDB Atlas** (capa gratuita M0) — recomendada | Equipo y despliegue. Es un conjunto de réplicas, así que tiene transacciones (sección 7.2 del diseño). | `mongodb+srv://USUARIO:CONTRASENA@CLUSTER.mongodb.net/?retryWrites=true&w=majority` |
| **MongoDB Community** instalado en Windows | Trabajo sin internet. | `mongodb://localhost:27017` |

**Atlas:** crear el clúster M0, un usuario de base de datos (*Database Access*) y permitir la IP del equipo
(*Network Access*). Copiar la cadena de *Connect → Drivers* en `MONGO_URI`.

**Local:** instalar [MongoDB Community Server](https://www.mongodb.com/try/download/community) como servicio
de Windows (opcionalmente con MongoDB Compass). Funciona sin más configuración: sin conjunto de réplicas,
`crud/estados.py` hace el cambio de estado sin transacción y lo sigue protegiendo con `estado.version`.
Para tener transacciones también en local, convertirlo en conjunto de réplicas de un nodo:

1. En `C:\Program Files\MongoDB\Server\<versión>\bin\mongod.cfg` agregar:
   ```yaml
   replication:
     replSetName: rs0
   ```
2. Reiniciar el servicio (`net stop MongoDB` y `net start MongoDB` en una terminal de administrador).
3. En `mongosh`: `rs.initiate()`.
4. Usar `MONGO_URI=mongodb://localhost:27017/?replicaSet=rs0`.

## Estructura

```
safetrace-backend/
├── main.py                      # crea FastAPI, CORS, manejadores de error y registra los routers
├── core/                        # lo compartido por toda la API
│   ├── config.py                #   variables de entorno (.env) → `settings`
│   ├── database.py              #   cliente de MongoDB, `get_db`, ids y serialización
│   ├── security.py              #   bcrypt y tokens JWT (RNF-09, RNF-11)
│   ├── fechas.py                #   UTC con milisegundos, suma de meses
│   ├── email.py                 #   correo transaccional (sin proveedor: se simula)
│   ├── almacenamiento.py        #   proveedor de archivos (pendiente de elegir)
│   ├── paginacion.py            #   máximo 50 por página (RNF-30)
│   ├── errores.py               #   transición de estado rechazada (409)
│   └── registro.py              #   logs sin datos personales (RNF-20)
├── app/
│   ├── router/                  # capa de entrada: endpoints de FastAPI
│   │   ├── dependencies.py      #   usuario actual, roles, credencial de n8n y acceso al inmueble
│   │   ├── auth.py              #   A · registro e inicio/cierre de sesión   RF-01 a RF-03, RF-07
│   │   ├── usuarios.py          #   A · administración de usuarios y supresión RF-04 a RF-06, RF-08, RF-09
│   │   ├── auditoria.py         #   A · consulta de auditoría                RF-10
│   │   ├── configuracion.py     #   A · magnitud mínima y radio              RF-11, RF-12
│   │   ├── peritos.py           #   B · Peritos                    RF-13 a RF-16
│   │   ├── inmuebles.py         #   C · Inmuebles y zonas          RF-17 a RF-21, RF-23
│   │   ├── bitacora.py          #   D · Bitácora y evidencias      RF-22 a RF-27
│   │   ├── revisiones.py        #   E · Revisión del propietario   RF-28 a RF-30
│   │   ├── sismos.py            #   F · Sismos                     RF-31 a RF-37
│   │   ├── estados.py           #   G · Estados del inmueble       RF-38 a RF-47
│   │   ├── inspecciones.py      #   H · Inspecciones y constancias RF-48 a RF-58
│   │   ├── enlaces.py           #   I · Enlace público             RF-59 a RF-61
│   │   ├── ia_indice.py         #   J · IA e índice                RF-62 a RF-68
│   │   └── notificaciones.py    #   K · Notificaciones y procesos  RF-69 a RF-71
│   ├── crud/                    # acceso a MongoDB y reglas de negocio (mismos nombres)
│   └── schemas/                 # modelos Pydantic Base / Create / Update / Out (mismos nombres)
├── trabajador/                  # proceso aparte que ejecuta la colección `tareas`
├── db/
│   ├── indices.py               # crea los índices del Diseño DataBase V2
│   ├── semillas.py              # configuración, zonas y primer administrador general
│   ├── validadores/             # $jsonSchema por colección
│   └── migraciones/             # cambios de esquema numerados (RNF-22)
├── n8n/                         # flujos exportados (sismos y tareas diarias)
├── modelos_ia/                  # pesos del modelo entrenado en Colab (no van a git)
├── tests/                       # pruebas con mongomock (sin MongoDB)
├── http/ejemplos.http           # peticiones de prueba (extensión REST Client)
├── .vscode/                     # intérprete, depuración y extensiones
├── .github/workflows/ci.yml     # integración continua (RNF-32)
├── Procfile                     # despliegue: web (uvicorn) y worker (trabajador)
└── requirements.txt / requirements-dev.txt / pyproject.toml / .env.example
```

### Las tres capas (como en avisena)

| Carpeta | Qué va ahí |
|---|---|
| `app/router/` | Endpoints. Reciben `db: Database = Depends(get_db)` y el usuario con `Depends(get_current_user)` o `Depends(requiere_rol(...))`, validan con `app.schemas` y llaman a `app.crud`. |
| `app/schemas/` | Modelos Pydantic de lo que entra y sale (`Base` / `Create` / `Update` / `Out` y `Page` para listas paginadas). |
| `app/crud/` | Único lugar que habla con MongoDB; cada archivo solo escribe las colecciones de su módulo. Funciones síncronas que reciben `db` como primer parámetro. |

Diferencias con avisena, por lo que pide el diseño:

- **MongoDB en vez de MySQL:** `get_db` entrega la base de PyMongo; los ids son `ObjectId` y `serializar()` los devuelve como texto en `id`.
- **Sesiones con cierre por inactividad (RNF-11):** el token es un JWT como en avisena, pero además se guarda su hash en
  `sesiones`; cada petición extiende la sesión 30 minutos y cerrar sesión la borra (RF-03).
- **Permisos por rol:** en lugar de la tabla `permisos`, los tres roles fijos del MVP (`PROPIETARIO`, `PERITO`,
  `ADMINISTRADOR_GENERAL`) con `requiere_rol(...)`, y `obtener_inmueble_autorizado(...)` para el acceso a cada inmueble.
- **Errores:** los de base de datos se responden con un 500 genérico desde `main.py` (sin filtrar detalles internos);
  un cambio de estado rechazado responde 409.

## Reglas del equipo

1. **Cada colección tiene un dueño.** Solo el archivo de `app/crud` de ese módulo la escribe; los demás
   llaman a sus funciones. En `inmuebles`, los campos calculados se escriben con funciones de `crud/inmuebles.py`:
   `estado` solo G, `ultimo_indice` solo J, `ultimos_eventos` solo D y `revision_semestral` solo E.
2. **Solo G cambia el estado**, con `crud.estados.pedir_transicion`. J (IA e índice) nunca la llama (RNF-37).
3. **Lo lento va a la cola:** `crud.notificaciones.encolar_tarea` / `notificar`, y lo ejecuta el trabajador.
4. **Nada de datos personales en logs, tareas ni auditoría** (RNF-20).
5. **Ramas y revisión:** una rama por tarjeta del tablero (`feat/b-validar-credenciales`),
   pull request revisado por otro integrante y CI en verde antes de unir a `main` (RNF-32).

## Pendiente (decisiones abiertas del diseño, sección 11.2)

| Qué | Dónde | Comportamiento actual |
|---|---|---|
| Pesos del índice de priorización | `crud/ia_indice.py` → `calcular` | Lanza `NotImplementedError`; el marcado por sismo sigue sin índice. |
| Modelo de comparación de fotos (Colab) | `crud/ia_indice.py` → `cargar_modelo`, `comparar` | El análisis queda PENDIENTE y la tarea falla tras 3 intentos (FALLIDO, se puede reintentar). |
| Proveedor de archivos | `core/almacenamiento.py` | `POST /archivos/autorizacion` responde 501. Las evidencias se registran con ruta y huella. |
| Proveedor de correo | `core/email.py` | Sin `CORREO_API_KEY` el envío se simula (se registra en el log). |
| Criterio para emparejar SGC y USGS | `crud/sismos.py` | Propuesta: ±2 min y ≤ 100 km; prevalece la magnitud del SGC. |
| Lista definitiva de zonas | `db/semillas.py` | Lista de ejemplo. |
| Validadores `$jsonSchema` y usuarios de BD | `db/validadores/`, sección 7.3 | Por crear. |
