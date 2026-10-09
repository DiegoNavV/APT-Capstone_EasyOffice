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
