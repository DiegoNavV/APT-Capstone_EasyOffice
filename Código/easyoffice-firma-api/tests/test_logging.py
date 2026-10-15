import json
import logging

from app.core.logging_config import JsonRedactingFormatter, redactar, request_id_var


class TestRedaccion:
    def test_correo(self):
        assert redactar("login de juan.perez@empresa.cl") == "login de j***@empresa.cl"

    def test_rut_con_y_sin_puntos(self):
        assert redactar("rut 12.345.678-9 y 9876543-K") == "rut [RUT] y [RUT]"

    def test_api_key(self):
        assert "abc123" not in redactar("key fk_live_abc123XYZ")

    def test_bearer(self):
        assert redactar("Authorization: Bearer eyJhbGciOi.xxx") == "Authorization: Bearer [REDACTADO]"

    def test_texto_normal_no_cambia(self):
        assert redactar("documento 42 completado") == "documento 42 completado"


class TestFormatter:
    def test_salida_json_redactada(self):
        registro = logging.LogRecord("firma", logging.INFO, __file__, 1, "OTP enviado a %s", ("ana@x.cl",), None)
        registro.request_id = "req-12345678"
        data = json.loads(JsonRedactingFormatter().format(registro))
        assert data["msg"] == "OTP enviado a a***@x.cl"
        assert data["level"] == "INFO"
        assert data["request_id"] == "req-12345678"

    def test_toma_request_id_del_contexto(self):
        registro = logging.LogRecord("firma", logging.INFO, __file__, 1, "hola", (), None)
        token = request_id_var.set("ctx-ABCDEFGH")
        try:
            data = json.loads(JsonRedactingFormatter().format(registro))
        finally:
            request_id_var.reset(token)
        assert data["request_id"] == "ctx-ABCDEFGH"

    def test_sin_contexto_no_hay_request_id(self):
        registro = logging.LogRecord("firma", logging.INFO, __file__, 1, "hola", (), None)
        assert "request_id" not in json.loads(JsonRedactingFormatter().format(registro))
