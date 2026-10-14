"""Un archivo por tipo de tarea, con `ejecutar(db, tarea)` (lanza una excepción si falla) y,
opcional, `al_fallar(db, tarea, definitiva)`. El bucle del trabajador marca la tarea COMPLETADA,
la reintenta o la deja FALLIDA (RNF-24)."""

from trabajador.tareas import comparar_fotos, enviar_correo

EJECUTORES = {
    "COMPARAR_FOTOS": comparar_fotos,
    "ENVIAR_CORREO": enviar_correo,
}
