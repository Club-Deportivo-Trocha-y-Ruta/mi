import pytest
from uuid import uuid4


async def _admin_token(client):
    login = await client.post(
        "/api/auth/login",
        json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
    )
    return login.json()["access_token"]


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


class TestCreateClub:
    async def test_admin_creates_club_success(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]
        code = f"test-{uuid4().hex[:8]}"

        resp = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Club de Prueba", "code": code, "location": "Valle del Cauca"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["code"] == code
        assert body["name"] == "Club de Prueba"
        assert body["location"] == "Valle del Cauca"
        assert body["is_active"] is True
        assert "id" in body
        assert "created_at" in body

    async def test_create_club_duplicate_code(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        # El club seed ya existe con este code
        resp = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Duplicado", "code": "trocha-y-ruta"},
        )
        assert resp.status_code == 409

    async def test_coach_cannot_create_club(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "entrenador@trochyruta.com", "password": "Coach2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Club No Permitido", "code": f"no-permitido-{uuid4().hex[:8]}"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_create_club(self, client):
        resp = await client.post(
            "/api/clubs/",
            json={"name": "Sin Token", "code": f"sin-token-{uuid4().hex[:8]}"},
        )
        assert resp.status_code in (401, 403)


class TestListClubs:
    async def test_list_clubs_authenticated(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.get(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        # El club seed debe estar en la lista
        codes = [c["code"] for c in body]
        assert "trocha-y-ruta" in codes


class TestGetClub:
    async def test_get_club_detail_with_members(self, client):
        token = await _admin_token(client)
        club_id = await _seed_club_id(client, token)

        resp = await client.get(
            f"/api/clubs/{club_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == club_id
        assert body["code"] == "trocha-y-ruta"
        assert "members" in body
        assert isinstance(body["members"], list)
        # Admin y coach son miembros del club seed
        assert len(body["members"]) >= 1
        member = body["members"][0]
        assert "user_id" in member
        assert "first_name" in member
        assert "last_name" in member
        assert "role_in_club" in member

    async def test_get_club_not_found(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.get(
            "/api/clubs/999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


class TestUpdateClub:
    async def test_admin_updates_club(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        # Primero crear un club para no modificar el seed de forma permanente
        code = f"test-update-{uuid4().hex[:8]}"
        create_resp = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Club Original", "code": code, "location": "Cali"},
        )
        assert create_resp.status_code == 201
        club_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/clubs/{club_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Club Actualizado", "location": "Palmira"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Club Actualizado"
        assert body["location"] == "Palmira"
        assert body["id"] == club_id

    async def test_coach_cannot_update_club(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "entrenador@trochyruta.com", "password": "Coach2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.patch(
            "/api/clubs/1",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Intento Coach"},
        )
        assert resp.status_code == 403


class TestAddMember:
    async def test_admin_adds_member_to_club(self, client):
        admin_login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = admin_login.json()["access_token"]

        # Crear un club nuevo para este test
        club_code = f"test-members-{uuid4().hex[:8]}"
        club_resp = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Club Para Miembros", "code": club_code},
        )
        assert club_resp.status_code == 201
        club_id = club_resp.json()["id"]

        # Crear un usuario nuevo para agregar como miembro
        email = f"test-{uuid4().hex[:8]}@test.com"
        user_resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": email,
                "password": "Test2026!",
                "first_name": "Nuevo",
                "last_name": "Miembro",
                "role": "coach",
            },
        )
        assert user_resp.status_code == 201
        user_id = user_resp.json()["id"]

        # Agregar el usuario al club
        resp = await client.post(
            f"/api/clubs/{club_id}/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": user_id, "role_in_club": "coach"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["user_id"] == user_id
        assert body["role_in_club"] == "coach"
        assert "first_name" in body
        assert "joined_at" in body

    async def test_add_duplicate_member(self, client):
        token = await _admin_token(client)
        club_id = await _seed_club_id(client, token)

        # Obtener el ID del admin via /me
        me_resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        admin_id = me_resp.json()["id"]

        # Admin ya es miembro del club seed
        resp = await client.post(
            f"/api/clubs/{club_id}/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": admin_id, "role_in_club": "admin"},
        )
        assert resp.status_code == 409

    async def test_add_member_nonexistent_user(self, client):
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = login.json()["access_token"]

        resp = await client.post(
            "/api/clubs/1/members",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": 999999, "role_in_club": "coach"},
        )
        assert resp.status_code == 404
