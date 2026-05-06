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

    async def test_pre_created_parent_is_updated_not_duplicated(self, client):
        """Flujo Opción A: coach pre-crea padre con nombre → invita atando
        parent_user_id → padre completa onboarding → actualiza el usuario
        existente, no crea otro."""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)

        # 1. Coach pre-crea al padre sin email ni password (POST /api/users)
        create_resp = await client.post(
            "/api/users",
            headers=headers,
            json={
                "first_name": "Coach-creado",
                "last_name": "Padre",
                "role": "parent",
                "club_id": club_id,
            },
        )
        assert create_resp.status_code == 201
        pre_user_id = create_resp.json()["id"]

        # 2. Coach vincula al atleta con parentesco "madre"
        link_resp = await client.post(
            "/api/parent-athletes",
            headers=headers,
            json={
                "parent_id": pre_user_id,
                "athlete_id": athlete_id,
                "relationship": "madre",
            },
        )
        assert link_resp.status_code == 201

        # 3. Coach genera invitación pasando parent_user_id y relationship_type
        email = f"opciona-{uuid4().hex[:8]}@test.com"
        invite_resp = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "email": email,
                "parent_user_id": pre_user_id,
                "relationship_type": "madre",
            },
        )
        assert invite_resp.status_code == 201
        token = invite_resp.json()["token"]

        # 4. Endpoint validate_invite devuelve los datos pre-cargados
        validate_resp = await client.get(f"/api/auth/invite/{token}")
        assert validate_resp.status_code == 200
        validate_body = validate_resp.json()
        assert validate_body["parent_user_id"] == pre_user_id
        assert validate_body["first_name"] == "Coach-creado"
        assert validate_body["last_name"] == "Padre"
        assert validate_body["relationship_type"] == "madre"

        # 5. Padre completa onboarding cambiando nombre/apellido y parentesco
        register_resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Renombrada",
                "last_name": "Apellido-Nuevo",
                "password": "Parent2026!",
                "relationship_type": "padre",
            },
        )
        assert register_resp.status_code == 201
        register_body = register_resp.json()

        # 6. Verifica que NO se creó otro user — el id devuelto coincide con el pre-existente
        assert register_body["id"] == pre_user_id
        assert register_body["first_name"] == "Renombrada"
        assert register_body["last_name"] == "Apellido-Nuevo"
        assert register_body["email"] == email

        # 7. Verifica que el vínculo no se duplicó: solo una fila ParentAthlete
        list_resp = await client.get(
            f"/api/parent-athletes?athlete_id={athlete_id}",
            headers=headers,
        )
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        matching = [it for it in items if it["parent_id"] == pre_user_id]
        assert len(matching) == 1
        # Y el parentesco quedó como el padre lo eligió en el wizard
        assert matching[0]["relationship"] == "padre"

        # 8. El padre puede iniciar sesión con email + password recién creados
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "Parent2026!"},
        )
        assert login_resp.status_code == 200

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

    async def test_consume_invite_rejects_email_belonging_to_another_user(self, client):
        """consume_invite Opción A: si el email del invite pertenece a otro user
        distinto del parent_user_id → 409; el padre pre-creado no se modifica."""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)

        # 1. Coach pre-crea padre A sin email ni password
        padre_a_resp = await client.post(
            "/api/users",
            headers=headers,
            json={
                "first_name": "PadreA",
                "last_name": "SinEmail",
                "role": "parent",
                "club_id": club_id,
            },
        )
        assert padre_a_resp.status_code == 201
        padre_a_id = padre_a_resp.json()["id"]

        # 2. Vincular padre A al atleta
        link_resp = await client.post(
            "/api/parent-athletes",
            headers=headers,
            json={"parent_id": padre_a_id, "athlete_id": athlete_id, "relationship": "madre"},
        )
        assert link_resp.status_code == 201

        # 3. Crear padre B con email ya tomado (cuenta con login completo)
        email_tomado = f"tomado-{uuid4().hex[:8]}@test.com"
        padre_b_resp = await client.post(
            "/api/users",
            headers=headers,
            json={
                "first_name": "PadreB",
                "last_name": "EmailTomado",
                "email": email_tomado,
                "password": "PadreB2026!",
                "role": "parent",
                "club_id": club_id,
            },
        )
        assert padre_b_resp.status_code == 201

        # 4. Coach genera invite para el atleta apuntando a padre A pero con el
        #    email de padre B — simula un error de configuración del coach
        invite_resp = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "email": email_tomado,
                "parent_user_id": padre_a_id,
                "relationship_type": "madre",
            },
        )
        assert invite_resp.status_code == 201
        token = invite_resp.json()["token"]

        # 5. Padre A intenta completar onboarding con ese token
        register_resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "PadreA",
                "last_name": "SinEmail",
                "password": "PadreA2026!",
            },
        )
        assert register_resp.status_code == 409
        detail = register_resp.json()["detail"].lower()
        assert "correo" in detail

        # 6. Verificar que padre A NO quedó modificado — email no debe ser el del padre B
        #    Usamos GET /api/users?club_id= para listar y filtrar por id
        users_resp = await client.get(
            f"/api/users?club_id={club_id}", headers=headers
        )
        assert users_resp.status_code == 200
        all_users = users_resp.json()["items"]
        padre_a_data = next((u for u in all_users if u["id"] == padre_a_id), None)
        assert padre_a_data is not None
        assert padre_a_data["email"] is None or padre_a_data["email"] != email_tomado
        assert padre_a_data["is_active"] is True  # sigue activo (no se modificó)

    async def test_validate_invite_legacy_returns_null_prefill(self, client):
        """GET /api/auth/invite/{token} sin parent_user_id → prefill fields son null."""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)
        email = f"legacy-prefill-{uuid4().hex[:8]}@test.com"

        # Coach genera invite legacy (sin parent_user_id ni relationship_type)
        invite_resp = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={"athlete_id": athlete_id, "email": email},
        )
        assert invite_resp.status_code == 201
        token = invite_resp.json()["token"]

        # Validar el token
        validate_resp = await client.get(f"/api/auth/invite/{token}")
        assert validate_resp.status_code == 200
        body = validate_resp.json()

        assert body["valid"] is True
        assert body["email"] == email
        assert body["parent_user_id"] is None
        assert body["first_name"] is None
        assert body["last_name"] is None
        assert body["phone"] is None
        assert body["relationship_type"] is None

    async def test_consume_invite_reactivates_inactive_pre_created_user(self, client):
        """BUG-2: si el user pre-creado tenía is_active=False cuando el padre
        consume el invite, el flujo Opción A debe reactivarlo (is_active=True)
        para que el login posterior funcione."""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)

        # 1. Coach pre-crea padre con nombre+apellido, sin email ni password
        padre_resp = await client.post(
            "/api/users",
            headers=headers,
            json={
                "first_name": "Padre-Inactivo",
                "last_name": "Test-Reactiva",
                "role": "parent",
                "club_id": club_id,
            },
        )
        assert padre_resp.status_code == 201
        padre_id = padre_resp.json()["id"]

        # 2. Coach vincula al atleta
        link_resp = await client.post(
            "/api/parent-athletes",
            headers=headers,
            json={"parent_id": padre_id, "athlete_id": athlete_id, "relationship": "madre"},
        )
        assert link_resp.status_code == 201

        # 3. Coach desactiva al padre vía PATCH /api/users/{padre_id}
        deactivate_resp = await client.patch(
            f"/api/users/{padre_id}",
            headers=headers,
            json={"is_active": False},
        )
        assert deactivate_resp.status_code == 200
        assert deactivate_resp.json()["is_active"] is False

        # 4. Confirmar que quedó inactivo vía GET /api/users?club_id=
        confirm_resp = await client.get(f"/api/users?club_id={club_id}", headers=headers)
        assert confirm_resp.status_code == 200
        all_users_confirm = confirm_resp.json()["items"]
        padre_data_after_deactivate = next(
            (u for u in all_users_confirm if u["id"] == padre_id), None
        )
        assert padre_data_after_deactivate is not None
        assert padre_data_after_deactivate["is_active"] is False

        # 5. Coach genera invite con parent_user_id y email
        email = f"reactiva-{uuid4().hex[:8]}@test.com"
        invite_resp = await client.post(
            "/api/parent-athletes/invite",
            headers=headers,
            json={
                "athlete_id": athlete_id,
                "email": email,
                "parent_user_id": padre_id,
                "relationship_type": "madre",
            },
        )
        assert invite_resp.status_code == 201
        token = invite_resp.json()["token"]

        # 6. Padre completa onboarding
        register_resp = await client.post(
            "/api/auth/parent-register",
            json={
                "token": token,
                "first_name": "Padre-Inactivo",
                "last_name": "Test-Reactiva",
                "password": "Reactiva2026!",
            },
        )
        assert register_resp.status_code == 201
        assert register_resp.json()["id"] == padre_id

        # 7. Login del padre → debe ser 200 (is_active se restableció)
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "Reactiva2026!"},
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()
