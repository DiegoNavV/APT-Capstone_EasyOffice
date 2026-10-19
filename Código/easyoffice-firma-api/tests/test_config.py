import secrets

import pytest
from pydantic import ValidationError

from app.core.config import DEV_MASTER_KEY_HEX, DEV_SECRET, Settings

CLAVE_VALIDA = secrets.token_hex(32)


def _prod(**kwargs) -> Settings:
    base = {
        "app_env": "production",
        "s3_secret_key": "s3-real",
        "master_key_hex": CLAVE_VALIDA,
        "token_pepper": "pimienta-real",
    }
    base.update(kwargs)
    return Settings(**base)


class TestSecretosEnProduccion:
    def test_produccion_con_secretos_reales_arranca(self):
        assert _prod().app_env == "production"

    @pytest.mark.parametrize("campo", ["s3_secret_key", "master_key_hex", "token_pepper"])
    def test_produccion_rechaza_secreto_de_desarrollo(self, campo):
        with pytest.raises(ValidationError) as err:
            _prod(**{campo: DEV_SECRET})
        assert campo in str(err.value)

    def test_master_key_largo_incorrecto(self):
        with pytest.raises(ValidationError):
            _prod(master_key_hex="abcd")

    def test_master_key_no_hex(self):
        with pytest.raises(ValidationError):
            _prod(master_key_hex="z" * 64)

    def test_desarrollo_acepta_secretos_de_desarrollo(self):
        # Valores explícitos: el test no depende del .env ni de las variables
        # de entorno de quien lo ejecute.
        s = Settings(
            app_env="development",
            s3_secret_key=DEV_SECRET,
            master_key_hex=DEV_MASTER_KEY_HEX,
            token_pepper=DEV_SECRET,
        )
        assert s.master_key_hex == DEV_MASTER_KEY_HEX

    def test_produccion_rechaza_master_key_de_desarrollo(self):
        with pytest.raises(ValidationError) as err:
            _prod(master_key_hex=DEV_MASTER_KEY_HEX)
        assert "master_key_hex" in str(err.value)


class TestMasterKeyEnTodosLosEntornos:
    """Revisión de Diego (PR #31): el formato se valida también en desarrollo,
    para que el cifrado AES-256-GCM no falle solo fuera de producción."""

    def test_clave_de_desarrollo_es_hex_valido(self):
        assert len(bytes.fromhex(DEV_MASTER_KEY_HEX)) == 32

    @pytest.mark.parametrize("entorno", ["development", "test", "production"])
    @pytest.mark.parametrize("clave", [DEV_SECRET, "abcd", "z" * 64])
    def test_rechaza_formato_invalido(self, entorno, clave):
        with pytest.raises(ValidationError):
            Settings(app_env=entorno, master_key_hex=clave)

    def test_normaliza_mayusculas(self):
        assert Settings(master_key_hex="AB" * 32).master_key_hex == "ab" * 32


class TestParametros:
    def test_cors_lista(self):
        s = Settings(cors_origins=" http://a.cl , http://b.cl ,")
        assert s.cors_origin_list == ["http://a.cl", "http://b.cl"]

    def test_cors_vacio(self):
        assert Settings(cors_origins="").cors_origin_list == []

    def test_retencion_debe_ser_positiva(self):
        with pytest.raises(ValidationError):
            Settings(retention_years=0)
