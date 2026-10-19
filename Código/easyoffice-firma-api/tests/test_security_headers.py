import logging

from app.core.middleware import SECURITY_HEADERS


class TestHeadersDeSeguridad:
    def test_headers_presentes(self, client):
        resp = client.get("/api/v1/health")
        for nombre, valor in SECURITY_HEADERS.items():
            assert resp.headers.get(nombre) == valor

    def test_sin_hsts_fuera_de_produccion(self, client):
        resp = client.get("/api/v1/health")
        assert "strict-transport-security" not in resp.headers

    def test_docs_sin_csp_para_que_cargue(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "content-security-policy" not in resp.headers


class TestRequestId:
    def test_genera_id_si_no_viene(self, client):
        resp = client.get("/api/v1/health")
        assert len(resp.headers["X-Request-ID"]) == 36

    def test_respeta_id_valido(self, client):
        resp = client.get("/api/v1/health", headers={"X-Request-ID": "tramite-ABCD1234"})
        assert resp.headers["X-Request-ID"] == "tramite-ABCD1234"

    def test_reemplaza_id_invalido(self, client):
        malicioso = "<script>alert(1)</script>"
        resp = client.get("/api/v1/health", headers={"X-Request-ID": malicioso})
        assert resp.headers["X-Request-ID"] != malicioso
        assert len(resp.headers["X-Request-ID"]) == 36


class TestCors:
    def test_sin_origenes_configurados_no_hay_cors(self, client):
        resp = client.options(
            "/api/v1/health",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in resp.headers


class TestLogDeAcceso:
    """Revisión de Diego (PR #31): la URL con query string no debe llegar a los logs."""

    def test_no_registra_query_string(self, client, caplog):
        caplog.set_level(logging.INFO, logger="firma.access")
        client.get("/api/v1/health?email=juan.perez@empresa.cl&token=fk_live_abc123")
        lineas = [r.getMessage() for r in caplog.records if r.name == "firma.access"]
        assert any("GET /api/v1/health 200" in linea for linea in lineas)
        texto = caplog.text
        assert "juan.perez" not in texto
        assert "fk_live_abc123" not in texto
        assert "token=" not in texto


def test_entrypoint_desactiva_log_de_acceso_de_uvicorn():
    from pathlib import Path

    script = (Path(__file__).resolve().parent.parent / "scripts" / "entrypoint.sh").read_text(encoding="utf-8")
    lineas_uvicorn = [linea for linea in script.splitlines() if linea.strip().startswith("exec uvicorn")]
    assert len(lineas_uvicorn) == 2
    assert all("--no-access-log" in linea for linea in lineas_uvicorn)


def test_red_compartida_es_externa():
    from pathlib import Path

    import yaml

    compose = yaml.safe_load((Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text(encoding="utf-8"))
    assert compose["networks"]["easyoffice-net"] == {"external": True}
