"""Roles, módulos y permisos (esquema de avisena) y el superadministrador."""

from app.router.dependencies import MODULOS_USADOS
from db.semillas import MODULOS
from tests.conftest import CONTRASENA, crear_usuario_directo, iniciar_sesion, registrar


def test_todo_modulo_usado_en_los_routers_existe_en_las_semillas():
    assert MODULOS_USADOS <= set(MODULOS)


def test_superadmin_entra_a_las_rutas_del_administrador_y_a_las_de_permisos(cliente, superadmin):
    for ruta in ("/admin/usuarios", "/admin/auditoria", "/admin/configuracion", "/admin/peritos", "/inmuebles"):
        assert cliente.get(ruta, headers=superadmin).status_code == 200, ruta
    for ruta in ("/admin/roles", "/admin/modulos", "/admin/permisos"):
        assert cliente.get(ruta, headers=superadmin).status_code == 200, ruta


def test_superadmin_ve_cualquier_inmueble(cliente, superadmin, inmueble):
    assert cliente.get(f"/inmuebles/{inmueble['id']}", headers=superadmin).status_code == 200


def test_el_administrador_no_gestiona_permisos(cliente, admin):
    for ruta in ("/admin/roles", "/admin/modulos", "/admin/permisos"):
        assert cliente.get(ruta, headers=admin).status_code == 403, ruta


def test_permisos_de_la_sesion(cliente, propietario):
    permisos = cliente.get("/auth/yo/permisos", headers=propietario).json()
    inmuebles = next(p for p in permisos if p["modulo"] == "inmuebles")
    assert inmuebles == {
        "modulo": "inmuebles",
        "rol": "PROPIETARIO",
        "insertar": True,
        "actualizar": True,
        "seleccionar": True,
        "borrar": False,
    }
    assert not any(p["modulo"] == "usuarios" for p in permisos)


def test_solo_un_superadmin_asigna_o_modifica_superadmins(cliente, db, admin, superadmin):
    usuario = registrar(cliente, "ana@correo.com")
    ruta_rol = f"/admin/usuarios/{usuario['id']}/rol"
    assert cliente.patch(ruta_rol, json={"rol": "SUPERADMIN"}, headers=admin).status_code == 403
    assert cliente.patch(ruta_rol, json={"rol": "SUPERADMIN"}, headers=superadmin).json()["rol"] == "SUPERADMIN"

    # El administrador tampoco desactiva ni degrada a un superadmin
    assert (
        cliente.patch(f"/admin/usuarios/{usuario['id']}/estado", json={"activo": False}, headers=admin).status_code
        == 403
    )
    assert cliente.patch(ruta_rol, json={"rol": "PROPIETARIO"}, headers=admin).status_code == 403


def test_cambiar_a_un_rol_inexistente(cliente, superadmin):
    usuario = registrar(cliente, "ana@correo.com")
    r = cliente.patch(f"/admin/usuarios/{usuario['id']}/rol", json={"rol": "NO_EXISTE"}, headers=superadmin)
    assert r.status_code == 400


def test_quitar_un_permiso_bloquea_la_ruta_y_queda_en_auditoria(cliente, superadmin, propietario):
    r = cliente.put("/admin/permisos/inmuebles/PROPIETARIO", json={"insertar": False}, headers=superadmin)
    assert r.status_code == 200 and r.json()["insertar"] is False and r.json()["seleccionar"] is True
    datos = {
        "tipo_inmueble": "CASA",
        "direccion": "Calle 1 #2-3",
        "ciudad": "Pereira",
        "anio_construccion": 2000,
        "sistema_constructivo": "OTRO",
        "numero_pisos": 1,
        "longitud": -75.7,
        "latitud": 4.8,
    }
    assert cliente.post("/inmuebles", json=datos, headers=propietario).status_code == 403
    assert cliente.get("/inmuebles", headers=propietario).status_code == 200

    auditoria = cliente.get("/admin/auditoria", params={"accion": "ACTUALIZAR_PERMISO"}, headers=superadmin).json()
    assert auditoria["datos"][0]["cambios"]["nuevo"] == {"insertar": False}


def test_los_permisos_del_superadmin_no_se_modifican(cliente, superadmin):
    r = cliente.put("/admin/permisos/permisos/SUPERADMIN", json={"actualizar": False}, headers=superadmin)
    assert r.status_code == 409
    assert (
        cliente.patch("/admin/roles/SUPERADMIN/estado", json={"estado": False}, headers=superadmin).status_code == 409
    )
    assert (
        cliente.patch("/admin/modulos/permisos/estado", json={"estado": False}, headers=superadmin).status_code == 409
    )


def test_rol_inactivo_cierra_sesiones_e_impide_entrar(cliente, superadmin, propietario):
    r = cliente.patch("/admin/roles/PROPIETARIO/estado", json={"estado": False}, headers=superadmin)
    assert r.status_code == 200 and r.json()["estado"] is False
    assert cliente.get("/auth/yo", headers=propietario).status_code == 401
    r = cliente.post("/auth/sesion", data={"username": "ana@correo.com", "password": CONTRASENA})
    assert r.status_code == 401 and r.json()["detail"] == "Rol inactivo"


def test_modulo_inactivo_niega_el_acceso(cliente, superadmin, propietario, inmueble):
    cliente.patch("/admin/modulos/enlaces/estado", json={"estado": False}, headers=superadmin)
    r = cliente.get(f"/inmuebles/{inmueble['id']}/enlaces", headers=propietario)
    assert r.status_code == 403


def test_rol_nuevo_con_un_permiso(cliente, db, superadmin):
    rol = {"nombre_rol": "AUDITOR", "descripcion": "Solo consulta la auditoría"}
    assert cliente.post("/admin/roles", json=rol, headers=superadmin).status_code == 201
    assert cliente.post("/admin/roles", json=rol, headers=superadmin).status_code == 409
    permiso = {"rol": "AUDITOR", "modulo": "auditoria", "seleccionar": True}
    assert cliente.post("/admin/permisos", json=permiso, headers=superadmin).status_code == 201
    assert cliente.post("/admin/permisos", json={**permiso, "rol": "NADIE"}, headers=superadmin).status_code == 400

    crear_usuario_directo(db, "auditor@safetrace.co", "AUDITOR")
    auditor = iniciar_sesion(cliente, "auditor@safetrace.co")
    assert cliente.get("/admin/auditoria", headers=auditor).status_code == 200
    assert cliente.get("/admin/usuarios", headers=auditor).status_code == 403


def test_modulo_nuevo_da_todos_los_permisos_al_superadmin(cliente, superadmin):
    modulo = {"nombre_modulo": "reportes", "descripcion": "Reportes del sistema"}
    assert cliente.post("/admin/modulos", json=modulo, headers=superadmin).status_code == 201
    permiso = cliente.get("/admin/permisos/reportes/SUPERADMIN", headers=superadmin).json()
    assert all(permiso[a] for a in ("insertar", "actualizar", "seleccionar", "borrar"))
