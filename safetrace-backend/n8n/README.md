# Flujos de n8n

Exportar aquí cada flujo en JSON para versionarlo con el código:

| Flujo | Frecuencia | Llama a |
|---|---|---|
| `sismos.json` | cada 5 min o menos (RNF-04) | `POST /interno/sismos` |
| `vencimiento_constancias.json` | diario | `POST /interno/constancias/vencimientos` |
| `vencimiento_matriculas.json` | diario | `POST /interno/peritos/vencimientos` |
| `recordatorio_semestral.json` | diario | `POST /interno/recordatorios-semestrales` |
| `respaldo.json` | diario | `mongodump` a almacenamiento externo (RNF-23) |

Todas las llamadas envían el encabezado `X-Credencial-Servicio` con el valor de `CREDENCIAL_SERVICIO_N8N`.
n8n no escribe directo en la base: siempre pasa por la API.

Cuerpo de `POST /interno/sismos` (uno por sismo; repetirlo no lo duplica, RF-32):

```json
{ "fuente": "SGC", "id_externo": "SGC2026tbcd", "fecha_hora": "2026-10-08T03:10:41Z",
  "magnitud": 5.4, "profundidad_km": 112.0, "longitud": -75.98, "latitud": 4.63 }
```
