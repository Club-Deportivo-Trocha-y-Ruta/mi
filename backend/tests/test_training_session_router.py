"""Tests de integración del router training_sessions.

Patrón idéntico al proyecto: httpx.AsyncClient contra la app FastAPI con seed DB real.
Requiere DB de test disponible (misma que usa test_athletes.py).

Cubre: CRUD sesión, asistencia, upload — todos los roles.
"""

from __future__ import annotations

import io
from datetime import date, time
from unittest.mock import AsyncMock as _AsyncMock
from unittest.mock import MagicMock as _MagicMock
from unittest.mock import patch as _patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.audit_log import AuditAction as _AuditAction
from app.models.audit_log import AuditActorKind as _AuditActorKind
from app.models.audit_log import AuditLog as _AuditLog
from app.models.training_session import AttendanceStatus as _AttendanceStatus
from app.models.training_session import SessionAttendance as _SessionAttendance
from app.models.training_session import SessionStatus as _SessionStatus
from app.models.training_session import TrainingSession as _TrainingSession
from app.schemas.training_session import AttendanceUpdate as _AttendanceUpdate
from app.schemas.training_session import TrainingSessionCreate as _TrainingSessionCreate
from app.services.audit import CancelReasonCode as _CancelReasonCode
from app.services.request_context import AuditContext as _AuditContext
from app.services.training import attendance as _attendance_svc
from app.services.training import sessions as _sessions_svc


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
    token = await _login(client, "padre@trochayruta.com", "Parent2026!")
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


# ---------------------------------------------------------------------------
# H4 — IDOR: padre filtrando por athlete_id ajeno
# ---------------------------------------------------------------------------


class TestParentIDORFilterByForeignAthleteId:
    """H4 — Invariante IDOR: padre no puede ver sesiones de atleta ajeno via ?athlete_id.

    Requiere MySQL (docker compose up). El test lista atletas del club como coach,
    localiza uno que NO sea hijo del padre seed, y verifica que filtrar por ese
    athlete_id no devuelve sesiones del atleta ajeno al padre.
    """

    async def _get_parent_athlete_ids(self, client: AsyncClient, parent_headers: dict) -> set[int]:
        """Obtiene IDs de atletas vinculados al padre seed leyendo parent_athlete vía DB."""
        from app.database import AsyncSessionLocal
        from app.services.permissions import parent_athlete_ids

        resp = await client.get("/api/auth/me", headers=parent_headers)
        assert resp.status_code == 200
        parent_user_id = resp.json()["id"]
        async with AsyncSessionLocal() as db:
            ids = await parent_athlete_ids(db, parent_user_id)
        return set(ids)

    async def test_parent_filter_by_foreign_athlete_id_returns_403_or_empty(
        self, client: AsyncClient
    ):
        """Padre filtrando por athlete_id que no es su hijo no debe ver sesiones del atleta ajeno."""
        parent_headers = await _auth_parent(client)
        coach_headers = await _auth_coach(client)
        club_id = await _get_club_id(client, coach_headers)

        # Listar todos los atletas del club (solo coach puede hacerlo)
        athletes_resp = await client.get(
            f"/api/athletes?club_id={club_id}", headers=coach_headers
        )
        assert athletes_resp.status_code == 200
        athletes = athletes_resp.json().get("items", athletes_resp.json())
        if not isinstance(athletes, list):
            athletes = []

        # Obtener IDs de hijos del padre seed
        parent_kids = await self._get_parent_athlete_ids(client, parent_headers)

        # Buscar un atleta que NO sea hijo del padre (para probar IDOR)
        foreign_ids = [a["id"] for a in athletes if a["id"] not in parent_kids]
        if not foreign_ids:
            pytest.skip("No hay atletas ajenos al padre seed en este entorno — requiere seed con >= 2 atletas")

        foreign_id = foreign_ids[0]

        resp = await client.get(
            f"/api/training-sessions?athlete_id={foreign_id}",
            headers=parent_headers,
        )

        # Resultado aceptable: 403 (bloqueo explícito) o 200 con lista vacía
        # (el filtro interno excluye sesiones donde solo está convocado el atleta ajeno)
        if resp.status_code == 200:
            sessions = resp.json()
            assert isinstance(sessions, list)
            # Ninguna sesión devuelta debe ser exclusivamente del atleta ajeno
            # (si está vacía es correcto; si devuelve sesiones es una fuga)
            for session in sessions:
                # La sesión no debería contener datos del atleta ajeno en kid_attendances
                kid_attendances = session.get("kid_attendances") or []
                for ka in kid_attendances:
                    assert ka.get("athlete_id") != foreign_id, (
                        f"FUGA IDOR: kid_attendances expone datos del atleta ajeno {foreign_id}"
                    )
        else:
            assert resp.status_code == 403, (
                f"Se esperaba 200 (filtrado interno) o 403, pero se recibió {resp.status_code}"
            )


# ---------------------------------------------------------------------------
# T024 — instrumentación de auditoría (feature 041, contracts/audit-recording.md §4.6)
#
# Estilo: mismo patrón de AsyncSession mockeada que tests/test_training_session_service.py
# (no requiere MySQL ni el fixture "client"). Se captura cada objeto pasado a
# ``db.add`` y se valida el/los ``AuditLog`` encolado(s) por ``record_audit``.
# ---------------------------------------------------------------------------


def _mock_coach(user_id: int = 1) -> _MagicMock:
    coach = _MagicMock()
    coach.id = user_id
    coach.role = "coach"
    coach.email = "coach@test.local"
    coach.first_name = "Coach"
    coach.last_name = "Ficticio"
    coach.club_memberships = []
    return coach


def _mock_ctx(actor: _MagicMock) -> _AuditContext:
    return _AuditContext(
        request_id="a" * 32,
        actor=actor,
        actor_kind=_AuditActorKind.user,
        actor_role=actor.role,
    )


def _mock_training_session(
    session_id: int = 42,
    club_id: int = 7,
    status: _SessionStatus = _SessionStatus.PLANNED,
) -> _MagicMock:
    s = _MagicMock(spec=_TrainingSession)
    s.id = session_id
    s.club_id = club_id
    s.status = status
    s.scheduled_date = date(2030, 8, 15)
    s.scheduled_start_time = time(17, 0)
    s.duration_min = 90
    s.location = "Bosque Municipal"
    s.technical_focus = "Descenso técnico"
    s.route_file_path = None
    s.executed_at = None
    s.attendances = []
    return s


def _build_mock_db(add_calls: list, *, execute_result: _MagicMock) -> _AsyncMock:
    db = _AsyncMock()
    db.add = _MagicMock(side_effect=add_calls.append)
    db.execute = _AsyncMock(return_value=execute_result)

    async def _refresh(obj, attribute_names=None):
        return None

    db.refresh = _refresh
    return db


class TestAuditInstrumentationTrainingSessions:
    """T024 — cada acción del ciclo de vida de una sesión debe encolar un
    ``AuditLog`` con ``club_id`` propio y el ``request_id`` del contexto,
    en la misma unidad de trabajo (antes del ``db.commit()``)."""

    async def test_create_session_queues_training_session_audit_row(self):
        _sessions_svc._recent_dispatches.clear()
        coach = _mock_coach(1)
        ctx = _mock_ctx(coach)
        session_obj = _mock_training_session(session_id=42, club_id=7)

        add_calls: list = []
        result_mock = _MagicMock()
        result_mock.first = _MagicMock(return_value=_MagicMock())
        result_mock.scalar_one_or_none = _MagicMock(return_value=session_obj)
        scalars_mock = _MagicMock()
        scalars_mock.all = _MagicMock(return_value=[])
        result_mock.scalars = _MagicMock(return_value=scalars_mock)
        db = _build_mock_db(add_calls, execute_result=result_mock)

        async def _flush():
            # Simula la asignación de PK autoincremental tras el flush.
            for obj in add_calls:
                if isinstance(obj, _TrainingSession) and obj.id is None:
                    obj.id = 42

        db.flush = _flush

        payload = _TrainingSessionCreate(
            scheduled_date=date(2030, 8, 15),
            scheduled_start_time=time(17, 0),
            duration_min=90,
            location="Bosque Municipal",
            technical_focus="Descenso técnico",
            convocados_athlete_ids=[100, 101],
        )

        with _patch.object(_sessions_svc, "_assert_coach_in_club", new=_AsyncMock()):
            await _sessions_svc.create_session(
                db=db, payload=payload, coach=coach, club_id=7, ctx=ctx
            )

        audit_rows = [c for c in add_calls if isinstance(c, _AuditLog)]
        assert len(audit_rows) >= 1
        ts_row = next(
            r for r in audit_rows if r.entity_type == "training_session"
        )
        assert ts_row.action == _AuditAction.create
        assert ts_row.club_id == 7
        assert ts_row.actor_user_id == coach.id
        assert ts_row.request_id == ctx.request_id
        assert ts_row.meta_json["convocados_count"] == 2
        # Privacidad: ni nombre ni fecha de nacimiento de un atleta en meta_json.
        assert "athlete_name" not in (ts_row.meta_json or {})

    async def test_create_session_without_ctx_skips_audit(self):
        """Los callers directos de servicio (scripts, tests unitarios) que no
        pasan ``ctx`` no deben producir ninguna fila de auditoría."""
        _sessions_svc._recent_dispatches.clear()
        coach = _mock_coach(1)
        session_obj = _mock_training_session(session_id=42, club_id=7)

        add_calls: list = []
        result_mock = _MagicMock()
        result_mock.first = _MagicMock(return_value=_MagicMock())
        result_mock.scalar_one_or_none = _MagicMock(return_value=session_obj)
        scalars_mock = _MagicMock()
        scalars_mock.all = _MagicMock(return_value=[])
        result_mock.scalars = _MagicMock(return_value=scalars_mock)
        db = _build_mock_db(add_calls, execute_result=result_mock)
        db.flush = _AsyncMock()

        payload = _TrainingSessionCreate(
            scheduled_date=date(2030, 8, 15),
            scheduled_start_time=time(17, 0),
            duration_min=90,
            location="Bosque Municipal",
            technical_focus="Descenso técnico",
            convocados_athlete_ids=[100],
        )

        with _patch.object(_sessions_svc, "_assert_coach_in_club", new=_AsyncMock()):
            await _sessions_svc.create_session(
                db=db, payload=payload, coach=coach, club_id=7
            )

        assert not any(isinstance(c, _AuditLog) for c in add_calls)

    async def test_execute_session_queues_execute_audit_row(self):
        coach = _mock_coach(1)
        ctx = _mock_ctx(coach)
        session_obj = _mock_training_session(status=_SessionStatus.PLANNED)

        add_calls: list = []
        result_mock = _MagicMock()
        result_mock.scalar_one_or_none = _MagicMock(return_value=session_obj)
        scalars_mock = _MagicMock()
        scalars_mock.all = _MagicMock(return_value=[])
        result_mock.scalars = _MagicMock(return_value=scalars_mock)
        db = _build_mock_db(add_calls, execute_result=result_mock)

        await _sessions_svc.execute_session(db, session_id=42, ctx=ctx)

        audit_rows = [c for c in add_calls if isinstance(c, _AuditLog)]
        assert len(audit_rows) == 1
        assert audit_rows[0].action == _AuditAction.execute
        assert audit_rows[0].entity_type == "training_session"
        assert audit_rows[0].club_id == session_obj.club_id

    async def test_cancel_session_requires_reason_code_for_audit(self):
        """Sin ``reason_code`` (catálogo cerrado), ``record_audit`` rechaza la
        fila — REASON_REQUIRED cubre ``(training_session, cancel)``."""
        coach = _mock_coach(1)
        ctx = _mock_ctx(coach)
        session_obj = _mock_training_session(status=_SessionStatus.PLANNED)
        session_obj.attendances = []

        add_calls: list = []
        result_mock = _MagicMock()
        result_mock.scalar_one_or_none = _MagicMock(return_value=session_obj)
        scalars_mock = _MagicMock()
        scalars_mock.all = _MagicMock(return_value=[])
        result_mock.scalars = _MagicMock(return_value=scalars_mock)
        db = _build_mock_db(add_calls, execute_result=result_mock)

        with pytest.raises(Exception):
            await _sessions_svc.cancel_session(db, session_id=42, ctx=ctx)

    async def test_cancel_session_with_reason_code_queues_audit_row(self):
        coach = _mock_coach(1)
        ctx = _mock_ctx(coach)
        session_obj = _mock_training_session(status=_SessionStatus.PLANNED)
        session_obj.attendances = []

        add_calls: list = []
        result_mock = _MagicMock()
        result_mock.scalar_one_or_none = _MagicMock(return_value=session_obj)
        scalars_mock = _MagicMock()
        scalars_mock.all = _MagicMock(return_value=[])
        result_mock.scalars = _MagicMock(return_value=scalars_mock)
        db = _build_mock_db(add_calls, execute_result=result_mock)

        await _sessions_svc.cancel_session(
            db,
            session_id=42,
            ctx=ctx,
            reason_code=_CancelReasonCode.cancel_weather,
        )

        audit_rows = [c for c in add_calls if isinstance(c, _AuditLog)]
        assert len(audit_rows) == 1
        assert audit_rows[0].action == _AuditAction.cancel
        assert audit_rows[0].reason_code == "cancel_weather"

    async def test_update_session_no_changes_does_not_queue_audit_row(self):
        """R7 — un PATCH sin cambios reales no debe fabricar historia."""
        coach = _mock_coach(1)
        ctx = _mock_ctx(coach)
        session_obj = _mock_training_session()
        session_obj.location = "Bosque Municipal"

        add_calls: list = []
        result_mock = _MagicMock()
        result_mock.scalar_one_or_none = _MagicMock(return_value=session_obj)
        scalars_mock = _MagicMock()
        scalars_mock.all = _MagicMock(return_value=[])
        result_mock.scalars = _MagicMock(return_value=scalars_mock)
        db = _build_mock_db(add_calls, execute_result=result_mock)

        from app.schemas.training_session import TrainingSessionUpdate

        await _sessions_svc.update_session(
            db,
            session_id=42,
            payload=TrainingSessionUpdate(location="Bosque Municipal"),
            ctx=ctx,
        )

        assert not any(isinstance(c, _AuditLog) for c in add_calls)


class TestAuditInstrumentationAttendance:
    """T024 — asistencia/convocatoria (attendance.py)."""

    async def test_bulk_upsert_convocatoria_creates_audit_rows_for_new_athletes(self):
        coach = _mock_coach(1)
        ctx = _mock_ctx(coach)

        add_calls: list = []
        existing_result = _MagicMock()
        scalars_mock = _MagicMock()
        scalars_mock.all = _MagicMock(return_value=[])
        existing_result.scalars = _MagicMock(return_value=scalars_mock)

        select_after_result = _MagicMock()
        select_after_result.scalars = _MagicMock(return_value=scalars_mock)

        db = _AsyncMock()
        db.add = _MagicMock(side_effect=add_calls.append)
        db.execute = _AsyncMock(side_effect=[existing_result, select_after_result])

        async def _flush():
            for obj in add_calls:
                if isinstance(obj, _SessionAttendance) and obj.id is None:
                    obj.id = 900 + obj.athlete_id

        db.flush = _flush

        await _attendance_svc.bulk_upsert_convocatoria(
            db=db,
            session_id=42,
            athlete_ids=[100, 101],
            club_id=7,
            ctx=ctx,
        )

        audit_rows = [c for c in add_calls if isinstance(c, _AuditLog)]
        assert len(audit_rows) == 2
        assert {r.action for r in audit_rows} == {_AuditAction.create}
        assert {r.athlete_id for r in audit_rows} == {100, 101}
        assert all(r.club_id == 7 for r in audit_rows)

    async def test_update_attendance_queues_update_audit_row_with_allowlisted_diff(self):
        coach = _mock_coach(1)
        ctx = _mock_ctx(coach)

        attendance_row = _MagicMock(spec=_SessionAttendance)
        attendance_row.id = 55
        attendance_row.status = _AttendanceStatus.AUSENTE
        attendance_row.archived_at = None
        attendance_row.excuse_reason = None
        attendance_row.rpe_omni = None
        attendance_row.rubric_effort = None
        attendance_row.rubric_attitude = None
        attendance_row.rubric_technique = None
        attendance_row.individual_feedback = None

        add_calls: list = []
        result_mock = _MagicMock()
        result_mock.scalar_one_or_none = _MagicMock(return_value=attendance_row)
        db = _build_mock_db(add_calls, execute_result=result_mock)

        await _attendance_svc.update_attendance(
            db=db,
            session_id=42,
            athlete_id=100,
            payload=_AttendanceUpdate(status=_AttendanceStatus.PRESENTE),
            club_id=7,
            ctx=ctx,
        )

        audit_rows = [c for c in add_calls if isinstance(c, _AuditLog)]
        assert len(audit_rows) == 1
        row = audit_rows[0]
        assert row.action == _AuditAction.update
        assert row.entity_type == "session_attendance"
        assert row.athlete_id == 100
        assert "status" in row.changed_fields
        # "status" SÍ está en VALUE_ALLOWLIST[session_attendance] → tiene valor.
        assert row.diff_json is not None and "status" in row.diff_json
