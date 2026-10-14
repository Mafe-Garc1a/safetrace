"""Fechas en UTC con la misma precisión que guarda MongoDB (milisegundos)."""

from datetime import UTC, datetime


def ahora() -> datetime:
    """Fecha actual en UTC, recortada a milisegundos para que sea igual antes y después de guardarla."""
    momento = datetime.now(UTC)
    return momento.replace(microsecond=momento.microsecond // 1000 * 1000)


def en_utc(fecha: datetime) -> datetime:
    """Una fecha sin zona horaria se toma como UTC (así la guarda MongoDB)."""
    return fecha.replace(tzinfo=UTC) if fecha.tzinfo is None else fecha.astimezone(UTC)


def sumar_meses(fecha: datetime, meses: int) -> datetime:
    """Suma meses respetando el último día del mes (31 de agosto + 6 meses = 28 de febrero)."""
    mes = fecha.month - 1 + meses
    anio = fecha.year + mes // 12
    mes = mes % 12 + 1
    bisiesto = anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0)
    dias_mes = [31, 29 if bisiesto else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
    return fecha.replace(year=anio, month=mes, day=min(fecha.day, dias_mes))
