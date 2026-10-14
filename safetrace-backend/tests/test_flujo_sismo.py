"""Escenario completo de la sección 10 del Diseño DataBase V2:
sismo → estado 2 → revisión → solicitud → perito validado → inspección firmada → constancia → enlace público.
"""

from datetime import datetime

from bson import ObjectId

from tests.conftest import CONTRASENA, N8N, iniciar_sesion, registrar

FOTO = {
    "tipo_archivo": "FOTO",
    "zona_id": "MURO_SALA",
    "archivo": {"ruta": "inmuebles/x/f1.jpg", "hash_sha256": "a" * 64},
}
SISMO = {
    "fuente": "SGC",
    "id_externo": "SGC2026tbcd",
    "fecha_hora": "2026-10-08T03:10:41Z",
    "magnitud": 5.4,
    "profundidad_km": 112.0,
    "longitud": -75.98,
    "latitud": 4.63,
}


def perito_validado(cliente, admin) -> tuple[dict, str]:
    registrar(cliente, "perito@correo.com", rol="PERITO")
    cabecera = iniciar_sesion(cliente, "perito@correo.com")
    perfil = {
        "documento": {"tipo": "CC", "numero": "1098765432"},
        "profesion": "Ingeniero civil",
        "especialidad": "Estructuras",
        "matricula_profesional": "MP-102938475",
    }
    perito = cliente.post("/peritos/perfil", json=perfil, headers=cabecera).json()
    assert perito["estado_credencial"] == "REGISTRADO"
    documentos = {"documentos": [{"tipo": "MATRICULA", "archivo": {"ruta": "peritos/m.pdf", "hash_sha256": "b" * 64}}]}
    assert cliente.post("/peritos/documentos", json=documentos, headers=cabecera).json()["estado_credencial"] == (
        "PENDIENTE_VALIDACION"
    )
    validacion = {"decision": "APROBADO", "documentos_revisados": ["DOC-1"]}
    r = cliente.post(f"/admin/peritos/{perito['id']}/validacion", json=validacion, headers=admin)
    assert r.json()["estado_credencial"] == "VALIDADO"
    assert r.json()["validaciones"][0]["documentos_revisados"] == ["DOC-1"]
    return cabecera, perito["id"]


def test_sismo_repetido_se_guarda_una_vez_y_empareja_fuentes(cliente, db, inmueble):
    primero = cliente.post("/interno/sismos", json=SISMO, headers=N8N).json()
    assert primero["resultado"] == "NUEVO" and primero["sismo"]["inmuebles_marcados"] == 1
    assert cliente.post("/interno/sismos", json=SISMO, headers=N8N).json()["resultado"] == "DUPLICADO"

    usgs = {
        **SISMO,
        "fuente": "USGS",
        "id_externo": "us7000q1ab",
        "magnitud": 5.3,
        "fecha_hora": "2026-10-08T03:11:10Z",
    }
    r = cliente.post("/interno/sismos", json=usgs, headers=N8N).json()
    assert r["resultado"] == "FUENTE_AGREGADA"
    assert r["sismo"]["magnitud"] == 5.4  # prevalece el SGC
    assert db["sismos"].count_documents({}) == 1
    assert db["eventos"].count_documents({"tipo": "EVENTO_EXTERNO"}) == 1


def test_sismo_bajo_la_magnitud_minima_no_marca(cliente, db, inmueble):
    r = cliente.post("/interno/sismos", json={**SISMO, "magnitud": 4.0}, headers=N8N).json()
    assert r["sismo"]["es_relevante"] is False
    assert db["inmuebles"].find_one()["estado"]["codigo"] == 1


def test_escenario_completo(cliente, db, admin, propietario, inmueble):
    inmueble_id = inmueble["id"]
    assert inmueble["estado"]["codigo"] == 1

    # 1. n8n entrega el sismo: el inmueble pasa al 2, con evento externo y aviso
    cliente.post("/interno/sismos", json=SISMO, headers=N8N)
    assert cliente.get(f"/inmuebles/{inmueble_id}/estado", headers=propietario).json()["codigo"] == 2
    linea = cliente.get(f"/inmuebles/{inmueble_id}/linea-cronologica", headers=propietario).json()
    assert linea["datos"][0]["tipo"] == "EVENTO_EXTERNO" and linea["datos"][0]["origen"] == "SISTEMA"
    assert db["notificaciones"].find_one()["tipo"] == "INMUEBLE_MARCADO_POR_SISMO"

    # 2. Ana registra eventos y revisiones con fotos de la misma zona: se pide la comparación con IA
    evento = {
        "tipo": "DANO",
        "fecha_evento": "2026-08-10T18:00:00Z",
        "descripcion": "Fisura en el muro",
        "zona_id": "MURO_SALA",
    }
    evento_id = cliente.post(f"/inmuebles/{inmueble_id}/eventos", json=evento, headers=propietario).json()["id"]
    r = cliente.post(f"/inmuebles/{inmueble_id}/evidencias", json={**FOTO, "evento_id": evento_id}, headers=propietario)
    assert r.status_code == 201
    revision = {
        "observaciones": "La fisura creció",
        "hubo_cambios": True,
        "solicitara_inspeccion": True,
        "fotos": [FOTO],
    }
    r = cliente.post(f"/inmuebles/{inmueble_id}/revisiones", json=revision, headers=propietario)
    assert r.status_code == 201 and r.json()["cambio_estado_aplicado"] is True
    assert cliente.get(f"/inmuebles/{inmueble_id}/estado", headers=propietario).json()["codigo"] == 3
    analisis = cliente.get(f"/inmuebles/{inmueble_id}/analisis-ia", headers=propietario).json()["datos"]
    assert analisis[0]["estado"] == "PENDIENTE" and analisis[0]["leyenda"] == "Análisis automático mediante IA"
    assert db["tareas"].count_documents({"tipo": "COMPARAR_FOTOS"}) == 1

    # 3. Solicitud de inspección: estado 4. Solo se asigna un perito VALIDADO
    solicitud = cliente.post(
        f"/inmuebles/{inmueble_id}/solicitudes-inspeccion",
        json={"motivo": "Fisura creció tras el sismo"},
        headers=propietario,
    ).json()
    assert cliente.get(f"/inmuebles/{inmueble_id}/estado", headers=propietario).json()["codigo"] == 4
    perito, perito_id = perito_validado(cliente, admin)
    assert cliente.get(f"/inmuebles/{inmueble_id}", headers=perito).status_code == 403  # aún no asignado
    r = cliente.post(
        f"/admin/solicitudes-inspeccion/{solicitud['id']}/asignacion", json={"perito_id": perito_id}, headers=admin
    )
    assert r.json()["estado"] == "ASIGNADA"
    assert cliente.get(f"/inmuebles/{inmueble_id}", headers=perito).status_code == 200

    # 4. El perito registra y firma con su contraseña: huella, constancia y estado 5
    datos = {
        "fecha_inspeccion": "2026-10-12T14:00:00Z",
        "motivo": "Evaluación posterior al sismo",
        "observaciones": "Revisión visual",
        "hallazgos": "Fisura en el revoque del muro de la sala",
        "resultado": "No compromete columnas ni vigas",
    }
    inspeccion = cliente.post(
        f"/solicitudes-inspeccion/{solicitud['id']}/inspeccion", json=datos, headers=perito
    ).json()
    assert inspeccion["firma"]["firmada"] is False
    mala = cliente.post(f"/inspecciones/{inspeccion['id']}/firma", json={"contrasena": "otra"}, headers=perito)
    assert mala.status_code == 401
    firmada = cliente.post(
        f"/inspecciones/{inspeccion['id']}/firma", json={"contrasena": CONTRASENA, "vigencia_meses": 6}, headers=perito
    ).json()
    codigo = firmada["constancia"]["codigo"]
    assert len(codigo) == 16 and len(firmada["firma"]["huella_sha256"]) == 64
    assert cliente.get(f"/inmuebles/{inmueble_id}/estado", headers=propietario).json()["codigo"] == 5
    assert (
        cliente.put(f"/inspecciones/{inspeccion['id']}", json={"hallazgos": "cambio"}, headers=perito).status_code
        == 409
    )

    # 5. Verificación pública por código: íntegra; si alguien altera la base, deja de serlo
    verificacion = cliente.get(f"/constancias/{codigo}").json()
    assert verificacion["integra"] is True and verificacion["estado"] == "VIGENTE"
    assert "direccion" not in verificacion["inmueble"]
    db["inspecciones"].update_one({"_id": ObjectId(inspeccion["id"])}, {"$set": {"hallazgos": "alterado"}})
    assert cliente.get(f"/constancias/{codigo}").json()["integra"] is False
    db["inspecciones"].update_one({"_id": ObjectId(inspeccion["id"])}, {"$set": {"hallazgos": datos["hallazgos"]}})

    # 6. Corrección: versión 2 firmada; la 1 deja de estar activa pero no se borra
    v2 = cliente.post(f"/inspecciones/{inspeccion['id']}/correccion", json={"resultado": "Corregido"}, headers=perito)
    assert v2.status_code == 201 and v2.json()["version"] == 2
    cliente.post(f"/inspecciones/{v2.json()['id']}/firma", json={"contrasena": CONTRASENA}, headers=perito)
    versiones = cliente.get(f"/inmuebles/{inmueble_id}/inspecciones", headers=propietario).json()
    assert [(v["version"], v["es_version_activa"]) for v in versiones] == [(2, True), (1, False)]

    # 7. Enlace público: sin estado ni datos personales; revocar no borra
    enlace = cliente.post(
        f"/inmuebles/{inmueble_id}/enlaces",
        json={"campos_compartidos": ["LINEA_CRONOLOGICA", "INSPECCIONES_FIRMADAS"]},
        headers=propietario,
    ).json()
    vista = cliente.get(f"/publico/{enlace['codigo']}").json()
    assert "estado" not in vista["inmueble"] and "direccion" not in vista["inmueble"]
    assert "fotos" not in vista
    assert vista["inspecciones_firmadas"][0]["perito"]["matricula_profesional"] == "MP-102938475"
    cliente.delete(f"/enlaces/{enlace['id']}", headers=propietario)
    assert cliente.get(f"/publico/{enlace['codigo']}").status_code == 404
    assert db["enlaces_publicos"].count_documents({}) == 1

    # 8. Vencimiento: constancia VENCIDA y el inmueble vuelve al 1
    db["inspecciones"].update_many({}, {"$set": {"constancia.vigente_hasta": datetime(2026, 1, 1)}})
    r = cliente.post("/interno/constancias/vencimientos", headers=N8N).json()
    assert r["inmuebles_a_estado_1"] == 1
    historial = cliente.get(f"/inmuebles/{inmueble_id}/historial-estados", headers=propietario).json()
    assert [h["estado_nuevo"] for h in historial["datos"]] == [1, 5, 4, 3, 2]


def test_revision_sin_cambios_devuelve_al_estado_1(cliente, propietario, inmueble):
    cliente.post("/interno/sismos", json=SISMO, headers=N8N)
    revision = {"observaciones": "Todo igual", "hubo_cambios": False, "solicitara_inspeccion": False}
    cliente.post(f"/inmuebles/{inmueble['id']}/revisiones", json=revision, headers=propietario)
    assert cliente.get(f"/inmuebles/{inmueble['id']}/estado", headers=propietario).json()["codigo"] == 1


def test_revision_semestral_en_estado_1_no_cambia_el_estado(cliente, propietario, inmueble):
    revision = {"observaciones": "Revisión semestral", "hubo_cambios": False, "solicitara_inspeccion": False}
    r = cliente.post(f"/inmuebles/{inmueble['id']}/revisiones", json=revision, headers=propietario)
    assert r.json()["cambio_estado_aplicado"] is False
    ficha = cliente.get(f"/inmuebles/{inmueble['id']}", headers=propietario).json()
    assert ficha["estado"]["codigo"] == 1 and ficha["revision_semestral"]["ultima"] is not None


def test_otro_propietario_no_ve_el_inmueble(cliente, inmueble):
    registrar(cliente, "otro@correo.com")
    otro = iniciar_sesion(cliente, "otro@correo.com")
    assert cliente.get(f"/inmuebles/{inmueble['id']}", headers=otro).status_code == 403
