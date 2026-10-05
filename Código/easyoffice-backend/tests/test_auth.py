"""
Pruebas del login del panel: /api/auth/login, /me, /refresh y /logout.
El usuario semilla (conftest.seed) es agente@easyoffice.cl con PASSWORD_PRUEBA.
"""
from datetime import timedelta

import pytest

from app import models
from app.seguridad import MAX_INTENTOS_FALLIDOS, ahora_utc

EMAIL = "agente@easyoffice.cl"


@pytest.fixture()
def login(client, seed):
    """login(email=..., password=...) -> respuesta de /api/auth/login.
    Sin argumentos usa las credenciales correctas del usuario semilla."""
    def _login(email=EMAIL, password=None):
        password = seed["password"] if password is None else password
        return client.post("/api/auth/login", json={"email": email, "password": password})

    return _login


def _me(client, access_token):
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})


def _refresh_con_cookie(client, refresh_token):
    """Llama a /refresh mandando exactamente este refresh token (y no el que
    el TestClient tenga guardado de respuestas anteriores)."""
    client.cookies.clear()
    return client.post("/api/auth/refresh", headers={"Cookie": f"refresh_token={refresh_token}"})


# ===========================================================================
# 1. Login
# ===========================================================================

class TestLogin:

    def test_login_correcto_entrega_token_y_cookie(self, client, login):
        resp = login()
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert resp.cookies.get("refresh_token")

    def test_login_normaliza_email(self, client, login):
        resp = login(email="  Agente@EasyOffice.CL ")
        assert resp.status_code == 200

    def test_password_incorrecta_401(self, client, login):
        resp = login(password="incorrecta")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Email o contraseña incorrectos"

    def test_email_inexistente_da_el_mismo_mensaje(self, client, login):
        # Mismo mensaje que con contraseña incorrecta: no revela qué correos existen.
        resp = login(email="nadie@easyoffice.cl")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Email o contraseña incorrectos"

    def test_usuario_inactivo_no_puede_entrar(self, client, login, db_session, seed):
        usuario = db_session.get(models.Usuario, seed["usuario"].id_usuario)
        usuario.activo = False
        db_session.commit()
        assert login().status_code == 401

    def test_login_exitoso_registra_ultimo_login(self, client, login, db_session, seed):
        login()
        db_session.expire_all()
        usuario = db_session.get(models.Usuario, seed["usuario"].id_usuario)
        assert usuario.ultimo_login is not None
        assert usuario.intentos_fallidos == 0

    def test_hash_invalido_en_bd_no_da_500(self, client, login, db_session, seed):
        # Como el usuario de prueba de db/init/02_seed.sql, cuyo hash es ficticio.
        usuario = db_session.get(models.Usuario, seed["usuario"].id_usuario)
        usuario.password_hash = "CAMBIAR_CUANDO_EXISTA_AUTH"
        db_session.commit()
        assert login().status_code == 401


# ===========================================================================
# 2. Bloqueo por intentos fallidos
# ===========================================================================

class TestBloqueo:

    def test_se_bloquea_al_llegar_al_maximo(self, client, login):
        for _ in range(MAX_INTENTOS_FALLIDOS - 1):
            assert login(password="incorrecta").status_code == 401
        assert login(password="incorrecta").status_code == 423

    def test_bloqueada_rechaza_incluso_la_password_correcta(self, client, login):
        for _ in range(MAX_INTENTOS_FALLIDOS):
            login(password="incorrecta")
        assert login().status_code == 423

    def test_bloqueo_vencido_permite_entrar(self, client, login, db_session, seed):
        usuario = db_session.get(models.Usuario, seed["usuario"].id_usuario)
        usuario.intentos_fallidos = MAX_INTENTOS_FALLIDOS
        usuario.bloqueado_hasta = ahora_utc() - timedelta(minutes=1)
        db_session.commit()
        assert login().status_code == 200

    def test_login_exitoso_reinicia_el_contador(self, client, login, db_session, seed):
        for _ in range(MAX_INTENTOS_FALLIDOS - 1):
            login(password="incorrecta")
        assert login().status_code == 200
        db_session.expire_all()
        assert db_session.get(models.Usuario, seed["usuario"].id_usuario).intentos_fallidos == 0


# ===========================================================================
# 3. /me (endpoint protegido)
# ===========================================================================

class TestMe:

    def test_me_con_token_valido(self, client, login):
        token = login().json()["access_token"]
        resp = _me(client, token)
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == EMAIL
        assert body["rol_nombre"] == "agente"
        assert "password_hash" not in body

    def test_me_sin_token_401(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_con_token_alterado_401(self, client, login):
        token = login().json()["access_token"]
        assert _me(client, token[:-2] + "xx").status_code == 401

    def test_me_usuario_desactivado_despues_del_login_401(self, client, login, db_session, seed):
        token = login().json()["access_token"]
        usuario = db_session.get(models.Usuario, seed["usuario"].id_usuario)
        usuario.activo = False
        db_session.commit()
        assert _me(client, token).status_code == 401


# ===========================================================================
# 4. Refresh (rotación) y logout
# ===========================================================================

class TestRefreshYLogout:

    def test_refresh_entrega_token_nuevo_y_rota_la_cookie(self, client, login):
        viejo = login().cookies.get("refresh_token")
        resp = _refresh_con_cookie(client, viejo)
        assert resp.status_code == 200
        assert resp.json()["access_token"]
        nuevo = resp.cookies.get("refresh_token")
        assert nuevo and nuevo != viejo

    def test_refresh_sin_cookie_401(self, client):
        client.cookies.clear()
        assert client.post("/api/auth/refresh").status_code == 401

    def test_reusar_token_rotado_cierra_todas_las_sesiones(self, client, login):
        viejo = login().cookies.get("refresh_token")
        nuevo = _refresh_con_cookie(client, viejo).cookies.get("refresh_token")

        # Alguien reusa el token viejo (ya rotado): señal de robo.
        assert _refresh_con_cookie(client, viejo).status_code == 401
        # ...y como castigo también queda revocado el token nuevo.
        assert _refresh_con_cookie(client, nuevo).status_code == 401

    def test_refresh_token_expirado_401(self, client, login, db_session):
        cookie = login().cookies.get("refresh_token")
        for registro in db_session.query(models.RefreshToken).all():
            registro.expira_en = ahora_utc() - timedelta(seconds=1)
        db_session.commit()
        assert _refresh_con_cookie(client, cookie).status_code == 401

    def test_logout_revoca_el_refresh_token(self, client, login):
        cookie = login().cookies.get("refresh_token")
        client.cookies.clear()
        resp = client.post("/api/auth/logout", headers={"Cookie": f"refresh_token={cookie}"})
        assert resp.status_code == 204
        assert _refresh_con_cookie(client, cookie).status_code == 401

    def test_bd_guarda_solo_el_hash_del_refresh_token(self, client, login, db_session):
        cookie = login().cookies.get("refresh_token")
        hashes = [r.token_hash for r in db_session.query(models.RefreshToken).all()]
        assert cookie not in hashes
        assert len(hashes) == 1 and len(hashes[0]) == 64
