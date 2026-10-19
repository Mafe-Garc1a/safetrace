# Pruebas de integración

Las pruebas de `tests/` usan una base en memoria (mongomock), así que corren sin MongoDB
en el equipo y en el CI. mongomock no soporta consultas geoespaciales ni transacciones:
`tests/conftest.py` reemplaza la búsqueda por radio con un filtro en Python.

Aquí van las pruebas que necesitan un MongoDB real (Atlas o local), por ejemplo
`$geoWithin` sobre el índice `2dsphere` o la transacción de `crud.estados.pedir_transicion`.
Deben leer la URI de una variable aparte (`MONGO_URI_PRUEBAS`) para no tocar la base de desarrollo.
