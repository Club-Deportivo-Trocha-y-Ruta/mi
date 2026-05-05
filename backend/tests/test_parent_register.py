from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _login(client, email, password):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


async def _auth_coach(client):
    token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")
    return {"Authorization": f"Bearer {token}"}


async def _get_club_id(client, headers):
    me = await client.get("/api/auth/me", headers=headers)
    return me.json()["club_ids"][0]


async def _create_athlete(client, headers, club_id) -> int:
    """Crea un atleta de prueba y retorna su ID."""
    resp = await client.post(
        "/api/athletes",
        headers=headers,
        json={
            "first_name": "Test",
            "last_name": f"Atleta-{uuid4().hex[:6]}",
            "birth_date": "2013-06-15",
            "sex": "M",
            "club_id": club_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# TestParentInviteFlow
# ---------------------------------------------------------------------------

class TestParentInviteFlow:
    """Tests del flujo de invitación y registro de padres."""

    async def test_coach_creates_invite(self, client):
        """Coach genera invitación para un atleta → 201 con token"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)

        resp = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={"athlete_id": athlete_id, "email": f"parent-invite-{uuid4().hex[:8]}@test.com"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["athlete_id"] == athlete_id
        assert "token" in body
        assert body["used"] is False

    async def test_validate_invite_token_valid(self, client):
        """GET /api/auth/invite/{token} con token válido → valid=True"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)
        email = f"parent-val-{uuid4().hex[:8]}@test.com"

        invite = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={"athlete_id": athlete_id, "email": email},
        )
        token = invite.json()["token"]

        resp = await client.get(f"/api/auth/invite/{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["email"] == email

    async def test_validate_invite_token_not_found(self, client):
        """Token inexistente → 404"""
        resp = await client.get("/api/auth/invite/tokeninexistente123")
        assert resp.status_code == 404

    async def test_parent_register_with_valid_token(self, client):
        """POST /api/auth/parent-register con token válido → 201, cuenta creada y vinculada"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)
        email = f"parent-reg-{uuid4().hex[:8]}@test.com"

        invite = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={"athlete_id": athlete_id, "email": email},
        )
        token = invite.json()["token"]

        resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "María",
                "last_name": "Rodríguez",
                "password": "Parent2026!",
                "phone": "3001234567",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == email
        assert body["first_name"] == "María"

        # Verificar que puede hacer login
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "Parent2026!"},
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()

    async def test_parent_register_token_single_use(self, client):
        """El token no puede usarse dos veces → 410 en segundo intento"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)
        email = f"parent-su-{uuid4().hex[:8]}@test.com"

        invite = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={"athlete_id": athlete_id, "email": email},
        )
        token = invite.json()["token"]

        # Primer uso → éxito
        r1 = await client.post(
            "/api/auth/parent-register",
            json={"token": token, "first_name": "Ana", "last_name": "Test", "password": "Abc12345!"},
        )
        assert r1.status_code == 201

        # Segundo uso → 410
        r2 = await client.post(
            "/api/auth/parent-register",
            json={"token": token, "first_name": "Otra", "last_name": "Persona", "password": "Xyz67890!"},
        )
        assert r2.status_code == 410

    async def test_parent_register_invalid_token(self, client):
        """Token inválido → 404"""
        resp = await client.post(
            "/api/auth/parent-register",
            json={"token": "tokeninvalido123", "first_name": "X", "last_name": "Y", "password": "Abc12345!"},
        )
        assert resp.status_code == 404

    async def test_invite_rejected_when_email_already_linked(self, client):
        """Si el email ya pertenece a un padre vinculado al atleta → 409 al intentar invitar de nuevo."""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)
        email = f"parent-link-{uuid4().hex[:8]}@test.com"

        # 1. Coach genera invitación
        invite = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={"athlete_id": athlete_id, "email": email},
        )
        assert invite.status_code == 201
        token = invite.json()["token"]

        # 2. Padre se registra (crea user + parent_athlete)
        register = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Luis",
                "last_name": "Mora",
                "password": "Parent2026!",
            },
        )
        assert register.status_code == 201

        # 3. Coach intenta invitar nuevamente al mismo email para el mismo atleta
        retry = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={"athlete_id": athlete_id, "email": email},
        )
        assert retry.status_code == 409
        assert "vinculado" in retry.json()["detail"].lower()
