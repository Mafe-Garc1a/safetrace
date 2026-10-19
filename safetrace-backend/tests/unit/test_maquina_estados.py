import pytest

from app.crud.estados import EstadoInmueble as E
from app.crud.estados import transicion_permitida


@pytest.mark.parametrize(
    "desde,hacia",
    [
        (E.SIN_EVENTO_PENDIENTE, E.MARCADO_POR_EVENTO_SISMICO),  # RF-39
        (E.MARCADO_POR_EVENTO_SISMICO, E.REVISION_PROPIETARIO_REGISTRADA),  # RF-40
        (E.MARCADO_POR_EVENTO_SISMICO, E.INSPECCION_SOLICITADA),  # RF-41
        (E.INSPECCION_SOLICITADA, E.INSPECCION_FIRMADA),  # RF-42
        (E.REVISION_PROPIETARIO_REGISTRADA, E.SIN_EVENTO_PENDIENTE),  # RF-43
        (E.INSPECCION_FIRMADA, E.SIN_EVENTO_PENDIENTE),  # RF-44
        (E.INSPECCION_FIRMADA, E.MARCADO_POR_EVENTO_SISMICO),  # RF-45
    ],
)
def test_transiciones_permitidas(desde, hacia):
    assert transicion_permitida(desde, hacia)


@pytest.mark.parametrize(
    "desde,hacia",
    [
        (E.SIN_EVENTO_PENDIENTE, E.INSPECCION_FIRMADA),
        (E.SIN_EVENTO_PENDIENTE, E.REVISION_PROPIETARIO_REGISTRADA),  # revisión semestral: no cambia estado
        (E.MARCADO_POR_EVENTO_SISMICO, E.INSPECCION_FIRMADA),  # firma tras sismo nuevo: no cambia
    ],
)
def test_transiciones_rechazadas(desde, hacia):
    assert not transicion_permitida(desde, hacia)
