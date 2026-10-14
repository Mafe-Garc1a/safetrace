from datetime import datetime

from app.crud.inspecciones import generar_codigo, huella_contenido, sumar_meses


def test_codigos_aleatorios_y_distintos():
    codigos = {generar_codigo() for _ in range(1000)}
    assert len(codigos) == 1000
    assert all(len(c) == 16 for c in codigos)


def test_huella_no_depende_del_orden_de_las_claves():
    assert huella_contenido({"a": 1, "b": 2}) == huella_contenido({"b": 2, "a": 1})
    assert huella_contenido({"a": 1}) != huella_contenido({"a": 2})


def test_vigencia_seis_meses():
    assert sumar_meses(datetime(2026, 10, 12), 6) == datetime(2027, 4, 12)
    assert sumar_meses(datetime(2026, 8, 31), 6) == datetime(2027, 2, 28)
