def test_salud(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok"}


def test_raiz(cliente):
    assert cliente.get("/").json()["message"] == "ok"


def test_ruta_protegida_sin_token_responde_401(cliente):
    assert cliente.get("/zonas").status_code == 401


def test_ruta_interna_sin_credencial_de_n8n(cliente):
    r = cliente.post("/interno/peritos/vencimientos", headers={"X-Credencial-Servicio": "otra"})
    assert r.status_code == 401
