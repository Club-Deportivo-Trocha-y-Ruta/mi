import pytest
from uuid import uuid4


async def _login(client, email, password):
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    return resp.json()["access_token"]


async def _seed_club_id(client, token):
    """Busca el club seed 'trocha-y-ruta' y retorna su ID."""
    resp = await client.get(
        "/api/clubs/",
        headers={"Authorization": f"Bearer {token}"},
    )
    for club in resp.json():
        if club["code"] == "trocha-y-ruta":
            return club["id"]
    raise RuntimeError("Club seed 'trocha-y-ruta' no encontrado")


async def _admin_id(client, token):
    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    return me.json()["id"]


class TestCreateUser:
    async def test_admin_creates_coach(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]
        email = f"coach-{uuid4().hex[:8]}@test.com"

        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": email,
                "password": "Coach2026!",
                "first_name": "Carlos",
                "last_name": "Perez",
                "role": "coach",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == email
        assert body["role"] == "coach"
        assert body["can_login"] is True
        assert body["is_active"] is True
        assert "id" in body
        assert "created_at" in body

    async def test_admin_creates_parent(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]
        email = f"padre-{uuid4().hex[:8]}@test.com"

        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": email,
                "first_name": "Ana",
                "last_name": "Gomez",
                "role": "parent",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"] == "parent"
        # Parent sin password puede crearse sin problemas
        assert "id" in body

    async def test_coach_creates_parent_in_own_club(self, client):
        # Obtener el club_id real del seed
        admin_token = await _login(client, "admin@trochyruta.com", "Admin2026!")
        club_id = await _seed_club_id(client, admin_token)

        token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")
        email = f"padre-coach-{uuid4().hex[:8]}@test.com"

        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": email,
                "first_name": "Luis",
                "last_name": "Rodriguez",
                "role": "parent",
                "club_id": club_id,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["role"] == "parent"

    async def test_coach_cannot_create_coach(self, client):
        admin_token = await _login(client, "admin@trochyruta.com", "Admin2026!")
        seed_club_id = await _seed_club_id(client, admin_token)

        token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")

        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": f"otro-coach-{uuid4().hex[:8]}@test.com",
                "password": "Coach2026!",
                "first_name": "Otro",
                "last_name": "Coach",
                "role": "coach",
                "club_id": seed_club_id,
            },
        )
        assert resp.status_code == 403

    async def test_coach_must_provide_club_id(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "entrenador@trochyruta.com", "password": "Coach2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": f"sin-club-{uuid4().hex[:8]}@test.com",
                "first_name": "Sin",
                "last_name": "Club",
                "role": "parent",
                # sin club_id
            },
        )
        assert resp.status_code == 422

    async def test_coach_cannot_create_in_other_club(self, client):
        # Primero crear un segundo club con admin
        admin_login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        admin_token = admin_login.json()["access_token"]

        club_code = f"otro-club-{uuid4().hex[:8]}"
        club_resp = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Otro Club", "code": club_code},
        )
        assert club_resp.status_code == 201
        otro_club_id = club_resp.json()["id"]

        # Coach intenta crear un usuario en ese otro club
        coach_login = await client.post(
            "/api/auth/login",
            json={"email": "entrenador@trochyruta.com", "password": "Coach2026!"},
        )
        coach_token = coach_login.json()["access_token"]

        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {coach_token}"},
            json={
                "email": f"padre-otro-{uuid4().hex[:8]}@test.com",
                "first_name": "Padre",
                "last_name": "Otro",
                "role": "parent",
                "club_id": otro_club_id,
            },
        )
        assert resp.status_code == 403

    async def test_create_coach_without_password_fails(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": f"coach-sin-pass-{uuid4().hex[:8]}@test.com",
                "first_name": "Sin",
                "last_name": "Password",
                "role": "coach",
                # sin password
            },
        )
        assert resp.status_code == 422

    async def test_duplicate_email_fails(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]
        email = f"dup-{uuid4().hex[:8]}@test.com"

        # Crear usuario por primera vez
        first = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": email,
                "password": "Coach2026!",
                "first_name": "Primero",
                "last_name": "Usuario",
                "role": "coach",
            },
        )
        assert first.status_code == 201

        # Intentar crear otro con el mismo email
        second = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": email,
                "password": "Coach2026!",
                "first_name": "Segundo",
                "last_name": "Usuario",
                "role": "coach",
            },
        )
        assert second.status_code == 409


class TestCreateUserEdgeCases:
    async def test_weak_password_returns_422(self, client):
        """USERS-INTG-010: crear usuario con contraseña débil (<8 chars) retorna 422."""
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": f"weak-pass-{uuid4().hex[:8]}@test.com",
                "password": "123",
                "first_name": "Pass",
                "last_name": "Debil",
                "role": "coach",
            },
        )
        assert resp.status_code == 422


class TestListUsers:
    async def test_admin_lists_all_users(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] >= 2  # al menos admin y coach del seed
        # Verificar que no hay atletas en la lista
        roles = [u["role"] for u in body["items"]]
        assert "athlete" not in roles

    async def test_admin_filters_by_role(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.get(
            "/api/users?role=coach",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        # Todos los items deben ser coaches
        for user in body["items"]:
            assert user["role"] == "coach"

    async def test_coach_sees_only_own_club_users(self, client):
        admin_token = await _login(client, "admin@trochyruta.com", "Admin2026!")
        club_id = await _seed_club_id(client, admin_token)

        # Crear un padre en el club del coach para que haya algo que ver
        email = f"padre-visible-{uuid4().hex[:8]}@test.com"
        await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "email": email,
                "first_name": "Padre",
                "last_name": "Visible",
                "role": "parent",
                "club_id": club_id,
            },
        )

        coach_login = await client.post(
            "/api/auth/login",
            json={"email": "entrenador@trochyruta.com", "password": "Coach2026!"},
        )
        coach_token = coach_login.json()["access_token"]

        resp = await client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {coach_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        # El coach solo ve usuarios, no debe tener atletas
        roles = [u["role"] for u in body["items"]]
        assert "athlete" not in roles

    async def test_athlete_role_filter_rejected(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.get(
            "/api/users?role=athlete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400


class TestUpdateUser:
    async def test_admin_updates_user(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        # Crear usuario para editar
        email = f"edit-me-{uuid4().hex[:8]}@test.com"
        create_resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": email,
                "password": "Coach2026!",
                "first_name": "Antes",
                "last_name": "Apellido",
                "role": "coach",
            },
        )
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/users/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"first_name": "Despues"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["first_name"] == "Despues"
        assert body["id"] == user_id

    async def test_coach_updates_parent_in_club(self, client):
        admin_token = await _login(client, "admin@trochyruta.com", "Admin2026!")
        club_id = await _seed_club_id(client, admin_token)

        # Crear padre en club del coach
        email = f"padre-editable-{uuid4().hex[:8]}@test.com"
        create_resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "email": email,
                "first_name": "Padre",
                "last_name": "Original",
                "role": "parent",
                "club_id": club_id,
            },
        )
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        coach_login = await client.post(
            "/api/auth/login",
            json={"email": "entrenador@trochyruta.com", "password": "Coach2026!"},
        )
        coach_token = coach_login.json()["access_token"]

        resp = await client.patch(
            f"/api/users/{user_id}",
            headers={"Authorization": f"Bearer {coach_token}"},
            json={"last_name": "Editado"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_name"] == "Editado"

    async def test_coach_cannot_update_admin(self, client):
        # Obtener el ID real del admin
        admin_token = await _login(client, "admin@trochyruta.com", "Admin2026!")
        admin_id = await _admin_id(client, admin_token)

        coach_token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")

        resp = await client.patch(
            f"/api/users/{admin_id}",
            headers={"Authorization": f"Bearer {coach_token}"},
            json={"first_name": "Hackeado"},
        )
        assert resp.status_code == 403

    async def test_update_nonexistent_user(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.patch(
            "/api/users/999999",
            headers={"Authorization": f"Bearer {token}"},
            json={"first_name": "Nadie"},
        )
        assert resp.status_code == 404
