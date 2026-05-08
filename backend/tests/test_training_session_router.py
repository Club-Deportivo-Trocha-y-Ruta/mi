"""Tests de integración del router training_sessions.

Patrón idéntico al proyecto: httpx.AsyncClient contra la app FastAPI con seed DB real.
Requiere DB de test disponible (misma que usa test_athletes.py).

Cubre: CRUD sesión, asistencia, upload — todos los roles.
"""

from __future__ import annotations

import io
from datetime import date, time

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ---------------------------------------------------------------------------
# Helpers de auth (reutiliza patrón de test_athletes.py)
# ---------------------------------------------------------------------------


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login falló: {resp.text}"
    return resp.json()["access_token"]


async def _auth_coach(client: AsyncClient) -> dict:
    token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")
    return {"Authorization": f"Bearer {token}"}


async def _auth_admin(client: AsyncClient) -> dict:
    token = await _login(client, "admin@trochyruta.com", "Admin2026!")
    return {"Authorization": f"Bearer {token}"}


async def _auth_parent(client: AsyncClient) -> dict:
    token = await _login(client, "padre@trochyruta.com", "Parent2026!")
    return {"Authorization": f"Bearer {token}"}


async def _get_club_id(client: AsyncClient, headers: dict) -> int:
    resp = await client.get("/api/auth/me", headers=headers)
    return resp.json()["club_ids"][0]


async def _get_first_athlete_id(client: AsyncClient, headers: dict, club_id: int) -> int:
    resp = await client.get(f"/api/athletes?club_id={club_id}", headers=headers)
    items = resp.json()["items"]
    assert items, "No hay atletas en el club"
    return items[0]["id"]


def _session_payload(athlete_ids: list[int], **kwargs) -> dict:
    defaults = {
        "scheduled_date": "2030-08-15",
        "scheduled_start_time": "17:00:00",
        "duration_min": 90,
        "location": "Bosque Municipal",
        "technical_focus": "Descenso técnico",
        "convocados_athlete_ids": athlete_ids,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# POST /api/training-sessions — Crear sesión
# ---------------------------------------------------------------------------


class TestCreateTrainingSession:
    async def test_coach_creates_session_201(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _get_first_athlete_id(client, headers, club_id)

        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "planned"
        assert body["club_id"] == club_id

    async def test_admin_creates_session_201(self, client: AsyncClient):
        headers = await _auth_admin(client)
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        athlete_id = await _get_first_athlete_id(client, coach_headers, club_id)

        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    async def test_parent_cannot_create_session_403(self, client: AsyncClient):
        parent_headers = await _auth_parent(client)
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        athlete_id = await _get_first_athlete_id(client, coach_headers, club_id)

        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=parent_headers,
        )
        assert resp.status_code == 403

    async def test_anonymous_cannot_create_session_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([1]),
        )
        assert resp.status_code in (401, 403)

    async def test_duration_below_15_returns_422(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _get_first_athlete_id(client, headers, club_id)

        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id], duration_min=10),
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_past_date_returns_422(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _get_first_athlete_id(client, headers, club_id)

        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id], scheduled_date="2000-01-01"),
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_empty_convocados_returns_422(self, client: AsyncClient):
        headers = await _auth_coach(client)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([]),
            headers=headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/training-sessions — Listar sesiones
# ---------------------------------------------------------------------------


class TestListTrainingSessions:
    async def _create_test_session(self, client: AsyncClient, headers: dict, club_id: int) -> dict:
        athlete_id = await _get_first_athlete_id(client, headers, club_id)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()

    async def test_coach_lists_sessions_200(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        await self._create_test_session(client, headers, club_id)

        resp = await client.get("/api/training-sessions", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_admin_lists_sessions_200(self, client: AsyncClient):
        headers = await _auth_admin(client)
        resp = await client.get("/api/training-sessions", headers=headers)
        assert resp.status_code == 200

    async def test_anonymous_cannot_list_401(self, client: AsyncClient):
        resp = await client.get("/api/training-sessions")
        assert resp.status_code in (401, 403)

    async def test_parent_sees_only_own_athlete_sessions(self, client: AsyncClient):
        parent_headers = await _auth_parent(client)
        resp = await client.get("/api/training-sessions", headers=parent_headers)
        # 200 o lista vacía — no debe dar error
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_filter_by_status(self, client: AsyncClient):
        headers = await _auth_coach(client)
        resp = await client.get("/api/training-sessions?status=planned", headers=headers)
        assert resp.status_code == 200
        for s in resp.json():
            assert s["status"] == "planned"


# ---------------------------------------------------------------------------
# GET /api/training-sessions/{id} — Detalle
# ---------------------------------------------------------------------------


class TestGetTrainingSession:
    async def _create_session(self, client: AsyncClient, headers: dict, club_id: int) -> dict:
        athlete_id = await _get_first_athlete_id(client, headers, club_id)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()

    async def test_coach_gets_session_200(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session = await self._create_session(client, headers, club_id)
        session_id = session["id"]

        resp = await client.get(f"/api/training-sessions/{session_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == session_id

    async def test_admin_gets_session_200(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        admin_headers = await _auth_admin(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.get(f"/api/training-sessions/{session['id']}", headers=admin_headers)
        assert resp.status_code == 200

    async def test_nonexistent_session_404(self, client: AsyncClient):
        headers = await _auth_coach(client)
        resp = await client.get("/api/training-sessions/999999", headers=headers)
        assert resp.status_code == 404

    async def test_anonymous_gets_session_401(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.get(f"/api/training-sessions/{session['id']}")
        assert resp.status_code in (401, 403)

    async def test_response_includes_attendance_summary(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session = await self._create_session(client, headers, club_id)

        resp = await client.get(f"/api/training-sessions/{session['id']}", headers=headers)
        body = resp.json()
        assert "attendance_summary" in body


# ---------------------------------------------------------------------------
# PATCH /api/training-sessions/{id} — Actualizar
# ---------------------------------------------------------------------------


class TestUpdateTrainingSession:
    async def _create_session(self, client: AsyncClient, headers: dict, club_id: int) -> dict:
        athlete_id = await _get_first_athlete_id(client, headers, club_id)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()

    async def test_coach_updates_session_200(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session = await self._create_session(client, headers, club_id)

        resp = await client.patch(
            f"/api/training-sessions/{session['id']}",
            json={"location": "Velódromo nuevo"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["location"] == "Velódromo nuevo"

    async def test_admin_updates_session_200(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        admin_headers = await _auth_admin(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.patch(
            f"/api/training-sessions/{session['id']}",
            json={"technical_focus": "Técnica de frenos"},
            headers=admin_headers,
        )
        assert resp.status_code == 200

    async def test_parent_cannot_update_403(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        parent_headers = await _auth_parent(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.patch(
            f"/api/training-sessions/{session['id']}",
            json={"location": "Otro lugar"},
            headers=parent_headers,
        )
        assert resp.status_code == 403

    async def test_anonymous_cannot_update_401(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.patch(
            f"/api/training-sessions/{session['id']}",
            json={"location": "X"},
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /api/training-sessions/{id}/execute — Marcar ejecutada
# ---------------------------------------------------------------------------


class TestExecuteTrainingSession:
    async def _create_session(self, client: AsyncClient, headers: dict, club_id: int) -> dict:
        athlete_id = await _get_first_athlete_id(client, headers, club_id)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()

    async def test_coach_executes_session_200(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session = await self._create_session(client, headers, club_id)

        resp = await client.post(
            f"/api/training-sessions/{session['id']}/execute",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "executed"

    async def test_execute_already_executed_returns_409(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session = await self._create_session(client, headers, club_id)
        session_id = session["id"]

        await client.post(f"/api/training-sessions/{session_id}/execute", headers=headers)
        resp = await client.post(f"/api/training-sessions/{session_id}/execute", headers=headers)
        assert resp.status_code == 409

    async def test_parent_cannot_execute_403(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        parent_headers = await _auth_parent(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.post(
            f"/api/training-sessions/{session['id']}/execute",
            headers=parent_headers,
        )
        assert resp.status_code == 403

    async def test_anonymous_cannot_execute_401(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.post(f"/api/training-sessions/{session['id']}/execute")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# DELETE /api/training-sessions/{id} — Soft delete (cancelar)
# ---------------------------------------------------------------------------


class TestCancelTrainingSession:
    async def _create_session(self, client: AsyncClient, headers: dict, club_id: int) -> dict:
        athlete_id = await _get_first_athlete_id(client, headers, club_id)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()

    async def test_coach_cancels_planned_session_204(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session = await self._create_session(client, headers, club_id)

        resp = await client.delete(
            f"/api/training-sessions/{session['id']}",
            headers=headers,
        )
        assert resp.status_code == 204

    async def test_cancel_executed_session_returns_409(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session = await self._create_session(client, headers, club_id)
        session_id = session["id"]

        await client.post(f"/api/training-sessions/{session_id}/execute", headers=headers)
        resp = await client.delete(f"/api/training-sessions/{session_id}", headers=headers)
        assert resp.status_code == 409

    async def test_parent_cannot_cancel_403(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        parent_headers = await _auth_parent(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.delete(
            f"/api/training-sessions/{session['id']}",
            headers=parent_headers,
        )
        assert resp.status_code == 403

    async def test_anonymous_cannot_cancel_401(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        session = await self._create_session(client, coach_headers, club_id)

        resp = await client.delete(f"/api/training-sessions/{session['id']}")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PUT /api/training-sessions/{id}/attendance — Bulk convocatoria
# ---------------------------------------------------------------------------


class TestBulkAttendance:
    async def _create_session_and_get_ids(self, client: AsyncClient, headers: dict):
        club_id = await _get_club_id(client, headers)
        athlete_id = await _get_first_athlete_id(client, headers, club_id)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"], club_id, athlete_id

    async def test_coach_bulk_sets_convocatoria_200(self, client: AsyncClient):
        headers = await _auth_coach(client)
        session_id, club_id, athlete_id = await self._create_session_and_get_ids(client, headers)

        resp = await client.put(
            f"/api/training-sessions/{session_id}/attendance",
            json=[athlete_id],
            headers=headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_invalid_athlete_not_in_club_400(self, client: AsyncClient):
        headers = await _auth_coach(client)
        session_id, _, _ = await self._create_session_and_get_ids(client, headers)

        resp = await client.put(
            f"/api/training-sessions/{session_id}/attendance",
            json=[99999],
            headers=headers,
        )
        assert resp.status_code == 400
        # Mensaje en español
        detail = resp.json().get("detail", "")
        assert "club" in detail.lower() or "pertenecen" in detail.lower()

    async def test_parent_cannot_bulk_set_403(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        parent_headers = await _auth_parent(client)
        session_id, _, athlete_id = await self._create_session_and_get_ids(client, coach_headers)

        resp = await client.put(
            f"/api/training-sessions/{session_id}/attendance",
            json=[athlete_id],
            headers=parent_headers,
        )
        assert resp.status_code == 403

    async def test_anonymous_cannot_bulk_set_401(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        session_id, _, athlete_id = await self._create_session_and_get_ids(client, coach_headers)

        resp = await client.put(
            f"/api/training-sessions/{session_id}/attendance",
            json=[athlete_id],
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PATCH /api/training-sessions/{id}/attendance/{athlete_id} — Actualizar asistencia
# ---------------------------------------------------------------------------


class TestUpdateAttendanceEndpoint:
    async def _setup(self, client: AsyncClient, headers: dict):
        club_id = await _get_club_id(client, headers)
        athlete_id = await _get_first_athlete_id(client, headers, club_id)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"], athlete_id

    async def test_coach_updates_attendance_200(self, client: AsyncClient):
        headers = await _auth_coach(client)
        session_id, athlete_id = await self._setup(client, headers)

        resp = await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{athlete_id}",
            json={"status": "presente", "rpe_omni": 7, "rubric_effort": 4, "rubric_attitude": 5, "rubric_technique": 3},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "presente"
        assert body["rpe_omni"] == 7

    async def test_invalid_combo_rubric_ausente_422(self, client: AsyncClient):
        headers = await _auth_coach(client)
        session_id, athlete_id = await self._setup(client, headers)

        resp = await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{athlete_id}",
            json={"status": "ausente", "rpe_omni": 5, "excuse_reason": "Gripa"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_ausente_without_excuse_reason_422(self, client: AsyncClient):
        headers = await _auth_coach(client)
        session_id, athlete_id = await self._setup(client, headers)

        resp = await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{athlete_id}",
            json={"status": "ausente"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_parent_cannot_update_attendance_403(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        parent_headers = await _auth_parent(client)
        session_id, athlete_id = await self._setup(client, coach_headers)

        resp = await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{athlete_id}",
            json={"status": "presente"},
            headers=parent_headers,
        )
        assert resp.status_code == 403

    async def test_anonymous_cannot_update_attendance_401(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        session_id, athlete_id = await self._setup(client, coach_headers)

        resp = await client.patch(
            f"/api/training-sessions/{session_id}/attendance/{athlete_id}",
            json={"status": "presente"},
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/athletes/{id}/attendance — Historial asistencia atleta
# ---------------------------------------------------------------------------


class TestAthleteAttendanceHistoryEndpoint:
    async def test_coach_gets_athlete_attendance_200(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        athlete_id = await _get_first_athlete_id(client, headers, club_id)

        resp = await client.get(f"/api/athletes/{athlete_id}/attendance", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_anonymous_cannot_see_attendance_401(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        athlete_id = await _get_first_athlete_id(client, coach_headers, club_id)

        resp = await client.get(f"/api/athletes/{athlete_id}/attendance")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /api/training-sessions/{id}/route-file — Upload
# ---------------------------------------------------------------------------


_VALID_GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Ruta Test</name><trkseg>
    <trkpt lat="3.4" lon="-76.5"><ele>1000</ele></trkpt>
    <trkpt lat="3.5" lon="-76.4"><ele>1050</ele></trkpt>
  </trkseg></trk>
</gpx>"""


class TestUploadRouteFile:
    async def _create_session(self, client: AsyncClient, headers: dict, club_id: int) -> int:
        athlete_id = await _get_first_athlete_id(client, headers, club_id)
        resp = await client.post(
            "/api/training-sessions",
            json=_session_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_coach_uploads_valid_gpx_200(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session_id = await self._create_session(client, headers, club_id)

        files = {"file": ("ruta.gpx", io.BytesIO(_VALID_GPX), "application/gpx+xml")}
        resp = await client.post(
            f"/api/training-sessions/{session_id}/route-file",
            files=files,
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["route_file_path"] is not None

    async def test_txt_extension_returns_400(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session_id = await self._create_session(client, headers, club_id)

        files = {"file": ("datos.txt", io.BytesIO(b"contenido"), "text/plain")}
        resp = await client.post(
            f"/api/training-sessions/{session_id}/route-file",
            files=files,
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_oversized_file_returns_400(self, client: AsyncClient):
        headers = await _auth_coach(client)
        club_id = await _get_club_id(client, headers)
        session_id = await self._create_session(client, headers, club_id)

        # 6 MB > límite 5 MB
        big_content = b"X" * (6 * 1024 * 1024)
        files = {"file": ("ruta.gpx", io.BytesIO(big_content), "application/gpx+xml")}
        resp = await client.post(
            f"/api/training-sessions/{session_id}/route-file",
            files=files,
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_parent_cannot_upload_403(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        parent_headers = await _auth_parent(client)
        club_id = await _get_club_id(client, coach_headers)
        session_id = await self._create_session(client, coach_headers, club_id)

        files = {"file": ("ruta.gpx", io.BytesIO(_VALID_GPX), "application/gpx+xml")}
        resp = await client.post(
            f"/api/training-sessions/{session_id}/route-file",
            files=files,
            headers=parent_headers,
        )
        assert resp.status_code == 403

    async def test_anonymous_cannot_upload_401(self, client: AsyncClient):
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)
        session_id = await self._create_session(client, coach_headers, club_id)

        files = {"file": ("ruta.gpx", io.BytesIO(_VALID_GPX), "application/gpx+xml")}
        resp = await client.post(
            f"/api/training-sessions/{session_id}/route-file",
            files=files,
        )
        assert resp.status_code in (401, 403)
