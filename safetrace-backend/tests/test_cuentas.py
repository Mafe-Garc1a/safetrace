"""A · Cuentas y administración (RF-01 a RF-12)."""

from bson import ObjectId

from tests.conftest import CONTRASENA, iniciar_sesion, registrar


def test_registro_exige_consentimiento(cliente):
    datos = {"nombre_completo": "Ana", "correo": "a@b.co", "contrasena": CONTRASENA, "acepta_politica": False}
    assert cliente.post("/auth/registro", json=datos).status_code == 400


def test_registro_guarda_correo_en_minusculas_y_no_devuelve_contrasena(cliente, db):
    usuario = registrar(cliente, "Ana.Perez@Correo.com")
    assert usuario["correo"] == "ana.perez@correo.com"
    assert usuario["rol"] == "PROPIETARIO"
    assert "contrasena_hash" not in usuario
    assert db["usuarios"].find_one({"correo": "ana.perez@correo.com"})["contrasena_hash"].startswith("$2b$")


def test_correo_duplicado(cliente):
    registrar(cliente, "ana@correo.com")
    datos = {
        "nombre_completo": "Otra Ana",
        "correo": "ANA@correo.com",
        "contrasena": CONTRASENA,
        "acepta_politica": True,
    }
    assert cliente.post("/auth/registro", json=datos).status_code == 409


def test_no_se_registra_un_administrador(cliente):
    datos = {
        "nombre_completo": "Intruso",
        "correo": "x@y.co",
        "contrasena": CONTRASENA,
        "rol": "ADMINISTRADOR_GENERAL",
        "acepta_politica": True,
    }
    assert cliente.post("/auth/registro", json=datos).status_code == 422


def test_inicio_y_cierre_de_sesion(cliente, db):
    registrar(cliente, "ana@correo.com")
    malas = cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": "incorrecta"})
    assert malas.status_code == 401

    cabecera = iniciar_sesion(cliente, "ana@correo.com")
    assert cliente.get("/auth/yo", headers=cabecera).json()["correo"] == "ana@correo.com"
    sesion = db["sesiones"].find_one()
    assert "token" not in sesion and len(sesion["token_hash"]) == 64  # solo el hash del token

    assert cliente.delete("/auth/sesion", headers=cabecera).status_code == 204
    assert cliente.get("/auth/yo", headers=cabecera).status_code == 401
    assert db["sesiones"].count_documents({}) == 0


def test_solo_el_administrador_lista_usuarios(cliente, admin, propietario):
    assert cliente.get("/admin/usuarios", headers=propietario).status_code == 403
    r = cliente.get("/admin/usuarios", params={"rol": "PROPIETARIO"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_desactivar_usuario_cierra_sus_sesiones_y_queda_en_auditoria(cliente, db, admin):
    usuario = registrar(cliente, "ana@correo.com")
    cabecera = iniciar_sesion(cliente, "ana@correo.com")
    r = cliente.patch(f"/admin/usuarios/{usuario['id']}/estado", json={"activo": False}, headers=admin)
    assert r.status_code == 200 and r.json()["activo"] is False
    assert cliente.get("/auth/yo", headers=cabecera).status_code == 401
    assert cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA}).status_code == 403
    auditoria = cliente.get("/admin/auditoria", params={"accion": "CAMBIAR_ACTIVO"}, headers=admin).json()
    assert auditoria["datos"][0]["cambios"] == {"anterior": True, "nuevo": False}


def test_configuracion_de_sismos(cliente, admin):
    assert cliente.get("/admin/configuracion", headers=admin).json()["magnitud_minima"] == 5.0
    r = cliente.put("/admin/configuracion", json={"magnitud_minima": 4.5, "radio_afectacion_km": 150}, headers=admin)
    assert r.status_code == 200
    assert r.json()["radio_afectacion_km"] == 150


def test_supresion_anonimiza_y_lista_lo_conservado(cliente, db, admin):
    usuario = registrar(cliente, "ana@correo.com")
    cabecera = iniciar_sesion(cliente, "ana@correo.com")
    solicitud = cliente.post("/cuentas/supresion", headers=cabecera).json()
    r = cliente.post(f"/admin/solicitudes-supresion/{solicitud['id']}/atencion", headers=admin)
    assert r.status_code == 200
    assert r.json()["estado"] == "ATENDIDA" and r.json()["datos_conservados"]
    guardado = db["usuarios"].find_one({"_id": ObjectId(usuario["id"])})
    assert guardado["correo"].endswith("@safetrace.invalid") and guardado["activo"] is False
