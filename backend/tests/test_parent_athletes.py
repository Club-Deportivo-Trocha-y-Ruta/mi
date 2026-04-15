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


async def _auth_admin(client):
    token = await _login(client, "admin@trochyruta.com", "Admin2026!")
    return {"Authorization": f"Bearer {token}"}


async def _auth_parent(client):
    token = await _login(client, "padre@trochyruta.com", "Parent2026!")
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


async def _create_parent_user(client, headers, club_id) -> int:
    """Crea un usuario parent y retorna su ID."""
    resp = await client.post(
        "/api/users",
        headers=headers,
        json={
            "email": f"parent-{uuid4().hex[:8]}@test.com",
            "first_name": "Padre",
            "last_name": "Test",
            "role": "parent",
            "club_id": club_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# TestParentAthleteLink
# ---------------------------------------------------------------------------

class TestParentAthleteLink:
    """Tests de vinculación parent-athlete."""

    async def test_coach_links_parent_to_athlete(self, client):
        """Coach puede vincular padre con atleta de su club → 201"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)
        parent_id = await _create_parent_user(client, headers, club_id)

        resp = await client.post(
            "/api/parent-athletes",
            headers=headers,
            json={"parent_id": parent_id, "athlete_id": athlete_id, "relationship": "padre"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["parent_id"] == parent_id
        assert body["athlete_id"] == athlete_id
        assert body["relationship"] == "padre"
        assert body["parent_name"] == "Padre Test"
        assert "athlete_name" in body

    async def test_duplicate_link_returns_409(self, client):
        """Vincular mismo par parent-athlete dos veces → 409"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)
        parent_id = await _create_parent_user(client, headers, club_id)
        payload = {"parent_id": parent_id, "athlete_id": athlete_id, "relationship": "madre"}

        r1 = await client.post("/api/parent-athletes", headers=headers, json=payload)
        assert r1.status_code == 201
        r2 = await client.post("/api/parent-athletes", headers=headers, json=payload)
        assert r2.status_code == 409

    async def test_max_3_parents_per_athlete(self, client):
        """No se pueden vincular más de 3 padres por atleta → 422 al cuarto"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)

        for _ in range(3):
            p_id = await _create_parent_user(client, headers, club_id)
            r = await client.post(
                "/api/parent-athletes",
                headers=headers,
                json={"parent_id": p_id, "athlete_id": athlete_id, "relationship": "acudiente"},
            )
            assert r.status_code == 201

        # 4to intento debe ser rechazado
        p4_id = await _create_parent_user(client, headers, club_id)
        r4 = await client.post(
            "/api/parent-athletes",
            headers=headers,
            json={"parent_id": p4_id, "athlete_id": athlete_id, "relationship": "acudiente"},
        )
        assert r4.status_code == 422

    async def test_non_parent_role_rejected(self, client):
        """Usar un coach como parent_id → 422"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)

        # Obtener ID del propio coach (que tiene role=coach, no parent)
        me = await client.get("/api/auth/me", headers=headers)
        coach_id = me.json()["id"]

        resp = await client.post(
            "/api/parent-athletes",
            headers=headers,
            json={"parent_id": coach_id, "athlete_id": athlete_id, "relationship": "padre"},
        )
        assert resp.status_code in (400, 422)

    async def test_coach_unlinks_parent(self, client):
        """Coach puede desvincular relación → 204"""
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _create_athlete(client, headers, club_id)
        parent_id = await _create_parent_user(client, headers, club_id)

        link = await client.post(
            "/api/parent-athletes",
            headers=headers,
            json={"parent_id": parent_id, "athlete_id": athlete_id, "relationship": "madre"},
        )
        assert link.status_code == 201
        relation_id = link.json()["id"]

        delete_resp = await client.delete(f"/api/parent-athletes/{relation_id}", headers=headers)
        assert delete_resp.status_code == 204


# ---------------------------------------------------------------------------
# TestParentPortal
# ---------------------------------------------------------------------------

class TestParentPortal:
    """Tests del portal de padres."""

    async def test_parent_sees_own_athletes(self, client):
        """Parent ve su lista de atletas vinculados → 200"""
        parent_headers = await _auth_parent(client)

        resp = await client.get("/api/parent-athletes/my-athletes", headers=parent_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # El seed crea 1 vinculación para el padre seed
        assert len(body) >= 1
        item = body[0]
        assert "athlete_id" in item
        assert "athlete_first_name" in item
        assert "measurement_status" in item
        assert item["measurement_status"] in ("ok", "due_soon", "overdue", "never")

    async def test_parent_accesses_own_athlete_detail(self, client):
        """Parent puede ver detalle de su atleta vinculado → 200 con AthleteParentView"""
        parent_headers = await _auth_parent(client)

        # Obtener ID del atleta vinculado
        my_athletes = await client.get("/api/parent-athletes/my-athletes", headers=parent_headers)
        assert my_athletes.status_code == 200
        athlete_id = my_athletes.json()[0]["athlete_id"]

        resp = await client.get(f"/api/athletes/{athlete_id}", headers=parent_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == athlete_id
        assert "first_name" in body
        # AthleteParentView NO tiene user_id ni created_at
        assert "user_id" not in body

    async def test_parent_cannot_access_unlinked_athlete(self, client):
        """Parent no puede ver atleta que no es su hijo → 403"""
        # Crear un atleta nuevo sin vincular al padre seed
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        athlete_id = await _create_athlete(client, coach_headers, club_id)

        parent_headers = await _auth_parent(client)
        resp = await client.get(f"/api/athletes/{athlete_id}", headers=parent_headers)
        assert resp.status_code == 403

    async def test_parent_sees_anthropometry_without_notes(self, client):
        """Parent ve historial antropométrico de su hijo, pero notes=null"""
        coach_headers = await _auth_coach(client)
        parent_headers = await _auth_parent(client)

        # Obtener atleta vinculado al padre seed
        my_athletes = await client.get("/api/parent-athletes/my-athletes", headers=parent_headers)
        athlete_id = my_athletes.json()[0]["athlete_id"]

        # Coach crea medición con notas
        await client.post(
            f"/api/athletes/{athlete_id}/anthropometry",
            headers=coach_headers,
            json={
                "evaluation_date": "2026-01-15",
                "weight_kg": "42.5",
                "standing_height_cm": "152.0",
                "sitting_height_cm": "79.5",
                "notes": "Nota privada del entrenador",
            },
        )

        # Parent obtiene el historial
        resp = await client.get(f"/api/athletes/{athlete_id}/anthropometry", headers=parent_headers)
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) >= 1
        # Ningún registro debe tener notes para el parent
        for record in records:
            assert record.get("notes") is None

    async def test_parent_cannot_list_all_athletes(self, client):
        """Parent no puede listar todos los atletas del club → 403"""
        parent_headers = await _auth_parent(client)
        resp = await client.get("/api/athletes", headers=parent_headers)
        assert resp.status_code == 403

    async def test_parent_cannot_create_anthropometry(self, client):
        """Parent no puede crear registros antropométricos → 403"""
        parent_headers = await _auth_parent(client)

        my_athletes = await client.get("/api/parent-athletes/my-athletes", headers=parent_headers)
        athlete_id = my_athletes.json()[0]["athlete_id"]

        resp = await client.post(
            f"/api/athletes/{athlete_id}/anthropometry",
            headers=parent_headers,
            json={
                "evaluation_date": "2026-01-15",
                "weight_kg": "42.5",
                "standing_height_cm": "152.0",
                "sitting_height_cm": "79.5",
            },
        )
        assert resp.status_code == 403
