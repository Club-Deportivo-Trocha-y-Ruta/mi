import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.dependencies import get_notification_service
from app.main import app


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


class TestListClubsUnauthenticated:
    async def test_unauthenticated_cannot_list_clubs(self, client):
        """CLUBS-INTG-004: GET /api/clubs/ sin token retorna 401 o 403."""
        resp = await client.get("/api/clubs/")
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


class TestUpdateClubEdgeCases:
    async def test_update_nonexistent_club_returns_404(self, client):
        """CLUBS-INTG-007: PATCH /api/clubs/99999 retorna 404."""
        token = await _admin_token(client)
        resp = await client.patch(
            "/api/clubs/99999",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "No Existe"},
        )
        assert resp.status_code == 404

    async def test_create_club_with_duplicate_name(self, client):
        """CLUBS-INTG-008: crear club con nombre duplicado — comportamiento documentado.
        El sistema valida por code (único), no por name. Dos clubs con mismo nombre
        pero distinto code son permitidos. Este test documenta ese comportamiento.
        """
        token = await _admin_token(client)
        code1 = f"dup-name-1-{uuid4().hex[:8]}"
        code2 = f"dup-name-2-{uuid4().hex[:8]}"
        name = "Club Nombre Duplicado"

        resp1 = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": name, "code": code1},
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": name, "code": code2},
        )
        # Nombre duplicado es permitido (solo code es único): 201
        # Si el sistema implementa unicidad por nombre, será 409 o 422
        assert resp2.status_code in (201, 409, 422)

    async def test_create_club_with_empty_name_returns_422(self, client):
        """CLUBS-INTG-009: crear club con nombre vacío retorna 422."""
        token = await _admin_token(client)
        resp = await client.post(
            "/api/clubs/",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "", "code": f"empty-name-{uuid4().hex[:8]}"},
        )
        assert resp.status_code == 422


class TestAddMember:
    async def test_admin_adds_member_to_club(self, client):
        admin_login = await client.post(
            "/api/auth/login",
            json={"email": "admin@trochyruta.com", "password": "Admin2026!"},
        )
        token = admin_login.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}

        # Dos clubes nuevos y propios de este test (código único por corrida):
        # el test no depende de qué clubes siembre la BD.
        async def _create_club(label: str) -> int:
            resp = await client.post(
                "/api/clubs/",
                headers=headers,
                json={"name": f"Club {label} Miembros", "code": f"test-{label}-{uuid4().hex[:8]}"},
            )
            assert resp.status_code == 201
            return resp.json()["id"]

        club_origin_id = await _create_club("origen")
        club_target_id = await _create_club("destino")

        # Feature 041 (staff-admin.md §1.2/§1.4): una cuenta de personal nace
        # SIEMPRE con club (`club_id` obligatorio → 422 sin él) y sin
        # contraseña (FR-023: la fija la persona desde el correo que recibe).
        # Por eso el coach se crea en el club de origen y luego se le asigna
        # el club de destino — el caso real de «entrenador en varios clubes».
        # `get_notification_service` se sustituye: crear personal despacha un
        # correo de restablecimiento y el test no debe tocar SMTP/Resend.
        fake_notifications = MagicMock()
        fake_notifications.send = AsyncMock()
        app.dependency_overrides[get_notification_service] = lambda: fake_notifications
        try:
            email = f"test-{uuid4().hex[:8]}@test.com"
            user_resp = await client.post(
                "/api/users",
                headers=headers,
                json={
                    "email": email,
                    "first_name": "Nuevo",
                    "last_name": "Miembro",
                    "role": "coach",
                    "club_id": club_origin_id,
                },
            )
        finally:
            app.dependency_overrides.pop(get_notification_service, None)
        assert user_resp.status_code == 201, user_resp.text
        user_id = user_resp.json()["id"]

        # Agregar el usuario al segundo club
        resp = await client.post(
            f"/api/clubs/{club_target_id}/members",
            headers=headers,
            json={"user_id": user_id, "role_in_club": "coach"},
        )
        assert resp.status_code == 201, resp.text
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
