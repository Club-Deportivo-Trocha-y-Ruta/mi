"""
Tests de seguridad — SEC-001 a SEC-008
"""
import pytest
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from app.config import settings


async def _login(client, email: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    return resp.json()["access_token"]


async def _coach_headers(client) -> dict:
    token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")
    return {"Authorization": f"Bearer {token}"}


async def _admin_headers(client) -> dict:
    token = await _login(client, "admin@trochyruta.com", "Admin2026!")
    return {"Authorization": f"Bearer {token}"}


class TestSQLInjection:
    async def test_sql_injection_in_email_field(self, client):
        """SEC-001: SQL Injection en campo email → 401 o 422, sin error de DB expuesto."""
        resp = await client.post(
            "/api/auth/login",
            json={"email": "' OR '1'='1", "password": "cualquiera"},
        )
        assert resp.status_code in (401, 422)
        body = resp.text
        # No debe exponer stack trace ni mensajes de base de datos
        assert "sqlalchemy" not in body.lower()
        assert "traceback" not in body.lower()
        assert "syntax error" not in body.lower()


class TestXSSInput:
    async def test_xss_in_athlete_first_name(self, client):
        """SEC-002: XSS en nombre de atleta → 422 o cadena almacenada sin interpretar."""
        headers = await _coach_headers(client)
        # Obtener club del coach
        me = await client.get("/api/auth/me", headers=headers)
        club_id = me.json()["club_ids"][0]

        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "<script>alert(1)</script>",
                "last_name": "Test",
                "birth_date": "2013-01-01",
                "sex": "M",
                "club_id": club_id,
            },
            headers=headers,
        )
        # La API puede aceptar (almacenamiento sin ejecución) o rechazar con 422.
        # En ningún caso debe devolver un 500.
        assert resp.status_code in (201, 422)
        assert resp.status_code != 500


class TestRBACEnforcement:
    async def test_coach_cannot_create_club(self, client):
        """SEC-003: token de coach no puede acceder a rutas de admin (POST /api/clubs/)."""
        headers = await _coach_headers(client)
        resp = await client.post(
            "/api/clubs/",
            json={"name": "Club Intruso", "city": "Cali"},
            headers=headers,
        )
        assert resp.status_code == 403


class TestExpiredToken:
    async def test_expired_token_denied(self, client):
        """SEC-004: token con exp en el pasado retorna 401."""
        expired_payload = {
            "sub": "1",
            "role": "admin",
            "club_ids": [],
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
        }
        token = pyjwt.encode(
            expired_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


class TestTamperedToken:
    async def test_tampered_token_denied(self, client):
        """SEC-005: token con firma inválida retorna 401."""
        # Crear un token válido en estructura pero firmado con clave falsa
        forged_payload = {
            "sub": "1",
            "role": "admin",
            "club_ids": [],
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        }
        forged_token = pyjwt.encode(
            forged_payload,
            "clave-falsa-que-no-es-la-real",
            algorithm=settings.jwt_algorithm,
        )
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {forged_token}"},
        )
        assert resp.status_code == 401


class TestPathTraversal:
    async def test_path_traversal_outside_api_scope(self, client):
        """SEC-007: paths que intentan salir del scope de la API retornan 404."""
        headers = await _coach_headers(client)
        # Intentar acceder a rutas fuera del prefijo /api
        resp = await client.get(
            "/etc/passwd",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_numeric_id_with_special_chars(self, client):
        """SEC-007 (variante): ID de atleta con caracteres especiales retorna 422."""
        headers = await _coach_headers(client)
        resp = await client.get(
            "/api/athletes/1%2F..%2Fusers",
            headers=headers,
        )
        # FastAPI rechaza IDs no enteros con 422 o 404
        assert resp.status_code in (404, 422)


class TestParentRoleRestriction:
    async def test_parent_cannot_list_athletes(self, client):
        """SEC-008: usuario con rol parent (o no coach/admin) no puede listar atletas."""
        # Primero creamos un parent con el admin
        admin_headers = await _admin_headers(client)
        me = await client.get("/api/auth/me", headers=admin_headers)
        club_id = me.json()["club_ids"][0]

        # Crear un usuario parent
        create_resp = await client.post(
            "/api/users",
            json={
                "first_name": "Padre",
                "last_name": "SecTest",
                "email": "parent_sec_test@trochyruta.com",
                "password": "Parent2026!",
                "role": "parent",
                "club_id": club_id,
            },
            headers=admin_headers,
        )
        # Si ya existe por runs anteriores (409), ignorar
        assert create_resp.status_code in (201, 409)

        # Login como parent
        login_resp = await client.post(
            "/api/auth/login",
            json={
                "email": "parent_sec_test@trochyruta.com",
                "password": "Parent2026!",
            },
        )
        # Si el parent tiene can_login=true (depende de la implementación)
        if login_resp.status_code == 200:
            parent_token = login_resp.json()["access_token"]
            parent_headers = {"Authorization": f"Bearer {parent_token}"}
            # El parent no debería poder listar atletas (ruta restringida a admin/coach)
            resp = await client.get("/api/athletes", headers=parent_headers)
            assert resp.status_code in (401, 403)
        else:
            # Si el parent no puede hacer login, la restricción ya está aplicada
            assert login_resp.status_code == 401
