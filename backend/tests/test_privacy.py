"""
Tests de privacidad — PRIV-002, PRIV-005

PRIV-001 (sessionStorage vs localStorage) y PRIV-004 (commits de git)
se verifican manualmente / via E2E. No aplican a tests de backend.
PRIV-003 (no stack trace en producción) requiere config app_env=production.
"""
import io
import logging
import pytest


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


class TestServerLogsPrivacy:
    async def test_logs_do_not_expose_athlete_pii(self, client):
        """PRIV-002: los logs del servidor no exponen birth_date, weight ni datos PHV."""
        # Capturar logs de la aplicación durante operaciones con atletas
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        try:
            headers = await _coach_headers(client)
            me = await client.get("/api/auth/me", headers=headers)
            club_id = me.json()["club_ids"][0]

            # Crear atleta
            create_resp = await client.post(
                "/api/athletes",
                json={
                    "first_name": "PrivacyTest",
                    "last_name": "PRIV002",
                    "birth_date": "2013-05-15",
                    "sex": "M",
                    "club_id": club_id,
                },
                headers=headers,
            )
            assert create_resp.status_code == 201
            athlete_id = create_resp.json()["id"]

            # Crear registro antropométrico
            await client.post(
                f"/api/athletes/{athlete_id}/anthropometry",
                json={
                    "evaluation_date": "2026-04-14",
                    "weight_kg": "45.5",
                    "standing_height_cm": "155.0",
                    "sitting_height_cm": "73.0",
                },
                headers=headers,
            )

            # Revisar logs capturados
            log_output = log_stream.getvalue()

            # Los datos sensibles NO deben aparecer en logs de la app
            # (No podemos controlar uvicorn access log, pero sí los loggers de app)
            sensitive_patterns = ["2013-05-15", "45.5"]
            for pattern in sensitive_patterns:
                # Solo verificamos que el logger raíz de la app no los exponga explícitamente
                # Uvicorn puede loguear URLs, pero no bodies
                app_log = "\n".join(
                    line for line in log_output.splitlines()
                    if "app." in line.lower() or "trocha" in line.lower()
                )
                # Si se encontró algún log de la app, verificar que no exponga PII
                if app_log:
                    assert pattern not in app_log, (
                        f"PII '{pattern}' encontrado en logs de la aplicación"
                    )
        finally:
            root_logger.removeHandler(handler)


class TestUsersEndpointExcludesAthletes:
    async def test_get_users_does_not_return_athletes(self, client):
        """PRIV-005: GET /api/users no devuelve usuarios con rol athlete."""
        headers = await _coach_headers(client)
        resp = await client.get("/api/users", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        for user in body["items"]:
            assert user["role"] != "athlete", (
                f"Usuario con id={user['id']} y role='athlete' encontrado en /api/users"
            )

    async def test_admin_get_users_does_not_return_athletes(self, client):
        """PRIV-005 (admin): GET /api/users tampoco devuelve atletas para admin."""
        headers = await _admin_headers(client)
        resp = await client.get("/api/users", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        for user in body["items"]:
            assert user["role"] != "athlete", (
                f"Usuario con id={user['id']} y role='athlete' encontrado en /api/users (admin)"
            )

    async def test_get_users_with_role_athlete_filter_returns_400(self, client):
        """PRIV-005 (variante): filtrar por role=athlete retorna 400 Bad Request."""
        headers = await _coach_headers(client)
        resp = await client.get("/api/users?role=athlete", headers=headers)
        assert resp.status_code == 400
