from app.services.health import check_database, run_checks


class TestLiveness:
    def test_responde_200_sin_tocar_dependencias(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["env"] == "test"
        assert "version" in data


class TestReadiness:
    def test_todo_ok_200(self, client, fake_checks):
        fake_checks(database=True, redis=True, storage=True)
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "checks": {"database": "ok", "redis": "ok", "storage": "ok"},
        }

    def test_una_dependencia_caida_503(self, client, fake_checks):
        fake_checks(database=True, redis=False, storage=True)
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"] == "ConnectionError"

    def test_detalle_no_expone_urls_ni_credenciales(self, client, fake_checks):
        fake_checks(database=False, redis=False, storage=False)
        texto = client.get("/api/v1/health/ready").text
        for prohibido in ("postgresql", "redis://", "password", "secret"):
            assert prohibido not in texto.lower()


class TestChequeos:
    def test_check_database_con_sqlite(self):
        assert check_database() == (True, "ok")

    def test_run_checks_agrega_resultados(self):
        ok, resultados = run_checks({"a": lambda: (True, "ok"), "b": lambda: (False, "Timeout")})
        assert ok is False
        assert resultados == {"a": "ok", "b": "Timeout"}

    def test_run_checks_vacio_es_ok(self):
        assert run_checks({}) == (True, {})


class TestDependenciasCaidas:
    """Con servicios inalcanzables, los chequeos reales deben fallar rápido y
    sin exponer detalles (no deben quedar colgados)."""

    def _con_entorno(self, monkeypatch, **variables):
        from app.core.config import get_settings

        for nombre, valor in variables.items():
            monkeypatch.setenv(nombre, valor)
        get_settings.cache_clear()

    def test_redis_inalcanzable(self, monkeypatch):
        import time

        from app.core.config import get_settings
        from app.services.health import check_redis

        self._con_entorno(monkeypatch, REDIS_URL="redis://127.0.0.1:1/0", DEPENDENCY_TIMEOUT_SECONDS="1")
        try:
            inicio = time.monotonic()
            ok, detalle = check_redis()
            assert ok is False
            assert "127.0.0.1" not in detalle
            assert time.monotonic() - inicio < 10
        finally:
            get_settings.cache_clear()

    def test_storage_inalcanzable(self, monkeypatch):
        import time

        from app.core.config import get_settings
        from app.services.health import check_storage

        self._con_entorno(monkeypatch, S3_ENDPOINT="127.0.0.1:1", DEPENDENCY_TIMEOUT_SECONDS="1")
        try:
            inicio = time.monotonic()
            ok, detalle = check_storage()
            assert ok is False
            assert "127.0.0.1" not in detalle
            assert time.monotonic() - inicio < 10
        finally:
            get_settings.cache_clear()
