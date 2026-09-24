import pytest


async def _login(client, email, password):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


async def _auth(client, email="entrenador@trochyruta.com", password="Coach2026!"):
    token = await _login(client, email, password)
    return {"Authorization": f"Bearer {token}"}


async def _admin_auth(client):
    return await _auth(client, "admin@trochyruta.com", "Admin2026!")


async def _get_coach_club_id(client, headers):
    """Obtiene el club_id del coach via /api/auth/me."""
    resp = await client.get("/api/auth/me", headers=headers)
    return resp.json()["club_ids"][0]


# ---------------------------------------------------------------------------
# CRUD Atletas
# ---------------------------------------------------------------------------
class TestCreateAthlete:
    async def test_coach_creates_athlete(self, client):
        headers = await _auth(client)
        club_id = await _get_coach_club_id(client, headers)
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "Santiago",
                "last_name": "López",
                "birth_date": "2013-06-15",
                "sex": "M",
                "club_join_date": "2024-01-01",
                "club_id": club_id,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["first_name"] == "Santiago"
        assert body["sex"] == "M"
        assert body["age_decimal"] is not None
        assert body["category"] == "Pre-juvenil A"
        assert body["club_id"] == club_id

    async def test_coach_creates_female_athlete(self, client):
        headers = await _auth(client)
        club_id = await _get_coach_club_id(client, headers)
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "Valentina",
                "last_name": "García",
                "birth_date": "2014-03-20",
                "sex": "F",
                "club_id": club_id,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["category"] == "Infantil B femenino"

    async def test_admin_creates_athlete(self, client):
        headers = await _admin_auth(client)
        me = await client.get("/api/auth/me", headers=headers)
        club_id = me.json()["club_ids"][0]
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "Admin",
                "last_name": "Atleta",
                "birth_date": "2015-01-01",
                "sex": "M",
                "club_id": club_id,
            },
            headers=headers,
        )
        assert resp.status_code == 201

    async def test_coach_cannot_create_in_foreign_club(self, client):
        headers = await _auth(client)
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "Test",
                "last_name": "Fail",
                "birth_date": "2013-01-01",
                "sex": "M",
                "club_id": 9999,
            },
            headers=headers,
        )
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_create(self, client):
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "Test",
                "last_name": "NoAuth",
                "birth_date": "2013-01-01",
                "sex": "M",
                "club_id": 1,
            },
        )
        assert resp.status_code in (401, 403)


class TestListAthletes:
    async def test_coach_lists_athletes(self, client):
        headers = await _auth(client)
        resp = await client.get("/api/athletes", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)
        assert body["total"] >= 1

    async def test_coach_filters_by_club(self, client):
        headers = await _auth(client)
        club_id = await _get_coach_club_id(client, headers)
        resp = await client.get(f"/api/athletes?club_id={club_id}", headers=headers)
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["club_id"] == club_id

    async def test_coach_cannot_filter_foreign_club(self, client):
        headers = await _auth(client)
        resp = await client.get("/api/athletes?club_id=9999", headers=headers)
        assert resp.status_code == 403

    async def test_all_athletes_have_computed_fields(self, client):
        headers = await _auth(client)
        resp = await client.get("/api/athletes", headers=headers)
        for item in resp.json()["items"]:
            assert item["age_decimal"] is not None
            assert item["category"] is not None


class TestGetAthlete:
    async def test_get_athlete_detail(self, client):
        headers = await _auth(client)
        listing = await client.get("/api/athletes", headers=headers)
        athletes = listing.json()["items"]
        assert len(athletes) > 0
        athlete_id = athletes[0]["id"]

        resp = await client.get(f"/api/athletes/{athlete_id}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == athlete_id
        assert "latest_anthropometry" in body
        assert body["age_decimal"] is not None
        assert body["category"] is not None

    async def test_get_nonexistent_athlete(self, client):
        headers = await _auth(client)
        resp = await client.get("/api/athletes/99999", headers=headers)
        assert resp.status_code == 404

    async def test_get_athlete_detail_when_latest_record_has_skinfolds(self, client):
        """Regresión (feature 046): GET /api/athletes/{id} devolvía 500
        (`MissingGreenlet` — lazy-load fuera de contexto async) en cuanto el
        registro antropométrico más reciente tenía una medición de pliegues.
        `AnthropometryOut` ganó el campo `skinfolds` pero `get_athlete` (a
        diferencia de `list_anthropometry`) nunca se actualizó para
        precargar la relación ni para poblar el campo con `skinfold_set_out`.
        Hallado corriendo `frontend/e2e/body-composition.spec.ts` contra el
        stack e2e aislado — ver `docs/21-body-composition/qa.md` §2.3.
        """
        headers = await _auth(client)
        club_id = await _get_coach_club_id(client, headers)

        created = await client.post(
            "/api/athletes",
            json={
                "first_name": "Atleta",
                "last_name": "PliegueFicticio",
                "birth_date": "2013-06-15",
                "sex": "M",
                "club_join_date": "2024-01-01",
                "club_id": club_id,
            },
            headers=headers,
        )
        assert created.status_code == 201
        athlete_id = created.json()["id"]

        record_resp = await client.post(
            f"/api/athletes/{athlete_id}/anthropometry",
            json={
                "evaluation_date": "2026-05-01",
                "weight_kg": "46.0",
                "standing_height_cm": "156.0",
                "sitting_height_cm": "74.0",
            },
            headers=headers,
        )
        assert record_resp.status_code == 201
        record_id = record_resp.json()["id"]

        skinfolds_resp = await client.put(
            f"/api/athletes/{athlete_id}/anthropometry/{record_id}/skinfolds",
            json={
                "caliper_model": "slim_guide",
                "sites": {
                    "triceps": {"readings": [8.5, 9.0]},
                    "biceps": {"readings": [6.0, 6.5]},
                    "subscapular": {"readings": [7.0, 7.5]},
                    "medial_calf": {"readings": [10.0, 10.5]},
                    "iliac_crest": {"declined": True},
                    "supraspinale": {"readings": [9.0, 9.5]},
                },
            },
            headers=headers,
        )
        assert skinfolds_resp.status_code == 200

        resp = await client.get(f"/api/athletes/{athlete_id}", headers=headers)
        assert resp.status_code == 200  # antes de la corrección: 500 (MissingGreenlet)
        latest = resp.json()["latest_anthropometry"]
        assert latest is not None
        assert latest["skinfolds"] is not None
        assert latest["skinfolds"]["sum4_mm"] is not None
        assert latest["skinfolds"]["sites"]["triceps"]["value_mm"] is not None
        assert latest["skinfolds"]["sites"]["iliac_crest"]["declined"] is True


class TestUpdateAthlete:
    async def test_update_athlete_name(self, client):
        headers = await _auth(client)
        listing = await client.get("/api/athletes", headers=headers)
        athlete_id = listing.json()["items"][0]["id"]

        resp = await client.patch(
            f"/api/athletes/{athlete_id}",
            json={"first_name": "NombreActualizado"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["first_name"] == "NombreActualizado"

    async def test_update_nonexistent_athlete(self, client):
        headers = await _auth(client)
        resp = await client.patch(
            "/api/athletes/99999",
            json={"first_name": "X"},
            headers=headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Antropometría
# ---------------------------------------------------------------------------
class TestCreateAnthropometry:
    async def test_create_record(self, client):
        headers = await _auth(client)
        listing = await client.get("/api/athletes", headers=headers)
        athlete_id = listing.json()["items"][0]["id"]

        resp = await client.post(
            f"/api/athletes/{athlete_id}/anthropometry",
            json={
                "evaluation_date": "2026-04-14",
                "weight_kg": "45.5",
                "standing_height_cm": "155.0",
                "arm_span_cm": "157.0",
                "sitting_height_cm": "73.0",
                "notes": "Primera evaluación del cuatrimestre",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["athlete_id"] == athlete_id
        assert body["leg_length_cm"] == 82.0
        assert body["maturation_status"] in ("Pre-PHV", "Circa-PHV", "Post-PHV")
        assert body["maturity_offset"] is not None
        assert body["age_at_phv"] is not None
        assert body["training_implications"] is not None
        # Métricas morfológicas (envergadura) — arm_span_cm presente
        assert body["morphology"] is not None
        morph = body["morphology"]
        assert morph["ape_index"] == round(157.0 / 155.0, 3)
        assert morph["arm_span_height_delta_cm"] == 2.0
        assert morph["posture_screening_flag"] is False
        assert morph["bike_fit_category"] in ("short_reach", "standard", "long_reach")
        assert morph["bike_fit_guidance"]

    async def test_create_record_for_nonexistent_athlete(self, client):
        headers = await _auth(client)
        resp = await client.post(
            "/api/athletes/99999/anthropometry",
            json={
                "evaluation_date": "2026-04-14",
                "weight_kg": "40.0",
                "standing_height_cm": "150.0",
                "sitting_height_cm": "70.0",
            },
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_created_record_is_immediately_visible_in_list(self, client):
        """Regresión (parte 1/2 — contrato end-to-end): tras el 201, el
        registro ya debe estar visible en el GET de la lista. Ver la nota
        de la parte 2/2 (`test_create_record_commits_before_returning`,
        debajo) para por qué esta aserción sola no basta como regresión.
        """
        headers = await _auth(client)
        listing = await client.get("/api/athletes", headers=headers)
        athlete_id = listing.json()["items"][0]["id"]

        # Fecha deliberadamente anterior a la usada por
        # `TestAthleteDetailWithAnthropometry.test_detail_includes_latest_record`
        # (2026-04-14) más abajo en este archivo: `client` comparte una MySQL
        # real sin rollback entre tests (ver docstring de la clase de abajo),
        # así que un registro con fecha posterior para el mismo atleta
        # sembrado ("items[0]") rompería esa aserción de "más reciente".
        created = await client.post(
            f"/api/athletes/{athlete_id}/anthropometry",
            json={
                "evaluation_date": "2026-02-02",
                "weight_kg": "45.0",
                "standing_height_cm": "154.0",
                "sitting_height_cm": "73.0",
            },
            headers=headers,
        )
        assert created.status_code == 201
        new_id = created.json()["id"]

        listed = await client.get(
            f"/api/athletes/{athlete_id}/anthropometry", headers=headers
        )
        assert listed.status_code == 200
        listed_ids = [r["id"] for r in listed.json()]
        assert new_id in listed_ids

    async def test_create_record_commits_before_returning(self, client, monkeypatch):
        """Regresión (parte 2/2): `create_anthropometry` sólo hacía
        `db.add()` + `db.flush()`, dejando el `COMMIT` real al teardown de
        `get_db` (post-`yield`). FastAPI cierra ese `AsyncExitStack`
        DESPUÉS de enviar la respuesta al cliente
        (`fastapi.routing.request_response::app`: `await response(...)`
        corre dentro del `async with AsyncExitStack()` pero antes de que
        ese bloque salga), así que el 201 podía llegar al cliente antes de
        que el registro fuera durable/visible para cualquier OTRA
        conexión — confirmado reproduciendo con `httpx` contra la MySQL
        aislada de e2e (real, no `ASGITransport`): ~80% de las veces el
        registro faltaba en un GET disparado justo después del POST.

        `httpx.ASGITransport` (usado por el fixture `client`, un solo
        proceso/loop) no puede reproducir esa carrera de red real — por
        eso esta prueba no verifica el timing contra el cliente, sino que
        el propio endpoint invoca `commit()` de forma explícita (además
        del commit implícito del teardown de `get_db`): sin el fix hay
        exactamente 1 `commit()` por request (el del teardown); con el fix
        hay 2 (el explícito del endpoint + el del teardown, redundante e
        inofensivo). Ver `docs/21-body-composition/qa.md` §2.3 y
        `test_created_record_is_immediately_visible_in_list` arriba para
        el contrato end-to-end (necesario pero no suficiente como
        regresión por la limitación de `ASGITransport` recién explicada).
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        headers = await _auth(client)
        listing = await client.get("/api/athletes", headers=headers)
        athlete_id = listing.json()["items"][0]["id"]

        commit_calls = 0
        original_commit = AsyncSession.commit

        async def counting_commit(self, *args, **kwargs):
            nonlocal commit_calls
            commit_calls += 1
            return await original_commit(self, *args, **kwargs)

        monkeypatch.setattr(AsyncSession, "commit", counting_commit)

        resp = await client.post(
            f"/api/athletes/{athlete_id}/anthropometry",
            json={
                # Ver comentario en `test_created_record_is_immediately_visible_in_list`
                # sobre por qué esta fecha debe quedar antes de 2026-04-14.
                "evaluation_date": "2026-02-03",
                "weight_kg": "45.0",
                "standing_height_cm": "154.0",
                "sitting_height_cm": "73.0",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        assert commit_calls >= 2, (
            "create_anthropometry debe hacer su propio commit() explícito "
            "(no solo el implícito del teardown de get_db) — si esto vuelve "
            "a 1, el 201 puede llegar al cliente antes de que el registro "
            "sea visible para otras conexiones (ver docstring)."
        )


class TestListAnthropometry:
    async def test_list_records(self, client):
        headers = await _auth(client)
        listing = await client.get("/api/athletes", headers=headers)
        athlete_id = listing.json()["items"][0]["id"]

        resp = await client.get(
            f"/api/athletes/{athlete_id}/anthropometry", headers=headers
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_records_ordered_desc(self, client):
        headers = await _auth(client)
        listing = await client.get("/api/athletes", headers=headers)
        athlete_id = listing.json()["items"][0]["id"]

        # Crear un registro con fecha anterior
        await client.post(
            f"/api/athletes/{athlete_id}/anthropometry",
            json={
                "evaluation_date": "2026-01-10",
                "weight_kg": "43.0",
                "standing_height_cm": "153.0",
                "sitting_height_cm": "72.0",
            },
            headers=headers,
        )

        resp = await client.get(
            f"/api/athletes/{athlete_id}/anthropometry", headers=headers
        )
        records = resp.json()
        if len(records) >= 2:
            assert records[0]["evaluation_date"] >= records[1]["evaluation_date"]


class TestAthleteDetailWithAnthropometry:
    async def test_detail_includes_latest_record(self, client):
        headers = await _auth(client)
        listing = await client.get("/api/athletes", headers=headers)
        athlete_id = listing.json()["items"][0]["id"]

        # Crear una medición
        await client.post(
            f"/api/athletes/{athlete_id}/anthropometry",
            json={
                "evaluation_date": "2026-04-14",
                "weight_kg": "46.0",
                "standing_height_cm": "156.0",
                "sitting_height_cm": "74.0",
            },
            headers=headers,
        )

        resp = await client.get(f"/api/athletes/{athlete_id}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["latest_anthropometry"] is not None
        assert body["latest_anthropometry"]["evaluation_date"] == "2026-04-14"


# ---------------------------------------------------------------------------
# Casos de borde — ATHLETES-INTG-014 a ATHLETES-INTG-017
# ---------------------------------------------------------------------------
class TestAthleteEdgeCases:
    async def test_create_without_club_join_date_uses_default(self, client):
        """ATHLETES-INTG-014: atleta sin club_join_date resulta en years_in_club null."""
        headers = await _auth(client)
        club_id = await _get_coach_club_id(client, headers)
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "SinFecha",
                "last_name": "EnClub",
                "birth_date": "2013-01-01",
                "sex": "M",
                "club_id": club_id,
                # No incluye club_join_date
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["club_join_date"] is None
        assert body["years_in_club"] is None

    async def test_create_athlete_with_future_birth_date(self, client):
        """ATHLETES-INTG-015: fecha de nacimiento futura retorna 422."""
        headers = await _auth(client)
        club_id = await _get_coach_club_id(client, headers)
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "Futuro",
                "last_name": "Test",
                "birth_date": "2030-01-01",
                "sex": "M",
                "club_id": club_id,
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_create_athlete_with_invalid_sex(self, client):
        """ATHLETES-INTG-016: sexo inválido retorna 422."""
        headers = await _auth(client)
        club_id = await _get_coach_club_id(client, headers)
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "SexoInvalido",
                "last_name": "Test",
                "birth_date": "2013-01-01",
                "sex": "X",
                "club_id": club_id,
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_create_athlete_creates_user_and_club_member(self, client):
        """ATHLETES-INTG-017: crear atleta crea user con role=athlete y ClubMember."""
        headers = await _admin_auth(client)
        club_id = await _get_coach_club_id(client, await _auth(client))

        # Crear atleta
        resp = await client.post(
            "/api/athletes",
            json={
                "first_name": "TransaccionTest",
                "last_name": "Atomico",
                "birth_date": "2014-05-10",
                "sex": "F",
                "club_id": club_id,
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()

        # El usuario vinculado debe existir (user_id presente en la respuesta)
        assert "user_id" in body
        assert body["user_id"] is not None

        # El atleta creado debe estar visible en el listado del club
        list_resp = await client.get(f"/api/athletes?club_id={club_id}", headers=headers)
        assert list_resp.status_code == 200
        ids = [a["id"] for a in list_resp.json()["items"]]
        assert body["id"] in ids
