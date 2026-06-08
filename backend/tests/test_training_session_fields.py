"""Tests para la persistencia de `session_kind` y `objectives` en sesiones.

Regresión del defecto: estos dos campos se renderizaban y validaban en el
formulario pero el backend (`TrainingSessionCreate`/`Update` + `create_session`)
los descartaba silenciosamente. Estas pruebas fijan el contrato de extremo a
extremo.

- Clase `TestSessionKindObjectivesSchema` / `TestUpdateDiffHumanize`: unitarias,
  corren sin base de datos (solo Pydantic + helpers del servicio).
- Clase `TestSessionFieldsRoundTrip`: integración httpx contra la app con seed DB
  (corre en CI con MySQL/SQLite sembrada, igual que test_training_session_router).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.training_session import SessionKind
from app.schemas.training_session import (
    TrainingSessionCreate,
    TrainingSessionRead,
    TrainingSessionReadParent,
    TrainingSessionUpdate,
)


# ---------------------------------------------------------------------------
# Unitarias — sin DB
# ---------------------------------------------------------------------------


class TestSessionKindObjectivesSchema:
    def test_create_accepts_session_kind_and_objectives(self):
        c = TrainingSessionCreate(
            scheduled_date="2030-08-15",
            scheduled_start_time="17:00:00",
            duration_min=90,
            location="Bosque Municipal",
            technical_focus="Descenso técnico",
            session_kind="salida",
            objectives="Mejorar trazado en curvas",
            convocados_athlete_ids=[1],
        )
        assert c.session_kind == SessionKind.SALIDA
        assert c.objectives == "Mejorar trazado en curvas"

    def test_create_omitting_session_kind_yields_none_for_service_default(self):
        # El servicio aplica el server_default del modelo ('entrenamiento')
        # cuando el payload llega con None.
        c = TrainingSessionCreate(
            scheduled_date="2030-08-15",
            scheduled_start_time="17:00:00",
            duration_min=90,
            location="B",
            technical_focus="D",
            convocados_athlete_ids=[1],
        )
        assert c.session_kind is None

    def test_objectives_over_1000_chars_rejected(self):
        with pytest.raises(ValueError):
            TrainingSessionCreate(
                scheduled_date="2030-08-15",
                scheduled_start_time="17:00:00",
                duration_min=90,
                location="B",
                technical_focus="D",
                objectives="a" * 1001,
                convocados_athlete_ids=[1],
            )

    def test_update_partial_only_includes_set_fields(self):
        u = TrainingSessionUpdate(session_kind="otro")
        dumped = u.model_dump(exclude_unset=True)
        assert dumped == {"session_kind": SessionKind.OTRO}

    def test_read_schemas_expose_new_fields(self):
        assert "session_kind" in TrainingSessionRead.model_fields
        assert "objectives" in TrainingSessionRead.model_fields
        # La vista de padre también los expone (no son sensibles) pero sigue
        # omitiendo coach_notes y route_file_path.
        assert "session_kind" in TrainingSessionReadParent.model_fields
        assert "objectives" in TrainingSessionReadParent.model_fields
        assert "coach_notes" not in TrainingSessionReadParent.model_fields
        assert "route_file_path" not in TrainingSessionReadParent.model_fields


class TestUpdateDiffHumanize:
    """El diff de actualización debe rotular y humanizar los nuevos campos sin
    filtrar datos sensibles (privacidad menores)."""

    def test_humanize_enum_uses_value_not_repr(self):
        from app.services.training.sessions import _humanize

        assert _humanize(SessionKind.SALIDA) == "salida"

    def test_field_labels_include_new_fields(self):
        from app.services.training.sessions import _FIELD_LABELS

        assert _FIELD_LABELS["session_kind"] == "Tipo de sesión"
        assert _FIELD_LABELS["objectives"] == "Objetivos"


# ---------------------------------------------------------------------------
# Integración — requiere app + seed DB (corre en CI)
# ---------------------------------------------------------------------------


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, f"Login falló: {resp.text}"
    return resp.json()["access_token"]


async def _auth_coach(client: AsyncClient) -> dict:
    token = await _login(client, "entrenador@trochyruta.com", "Coach2026!")
    return {"Authorization": f"Bearer {token}"}


async def _club_and_athlete(client: AsyncClient, headers: dict) -> tuple[int, int]:
    me = await client.get("/api/auth/me", headers=headers)
    club_id = me.json()["club_ids"][0]
    ath = await client.get(f"/api/athletes?club_id={club_id}", headers=headers)
    athlete_id = ath.json()["items"][0]["id"]
    return club_id, athlete_id


def _payload(athlete_ids: list[int], **kwargs) -> dict:
    base = {
        "scheduled_date": "2030-09-20",
        "scheduled_start_time": "16:30:00",
        "duration_min": 75,
        "location": "Pista La Buitrera",
        "technical_focus": "Frenada en descenso",
        "convocados_athlete_ids": athlete_ids,
    }
    base.update(kwargs)
    return base


@pytest.mark.integration
class TestSessionFieldsRoundTrip:
    async def test_create_persists_kind_and_objectives_roundtrip(
        self, client: AsyncClient
    ):
        headers = await _auth_coach(client)
        _, athlete_id = await _club_and_athlete(client, headers)

        resp = await client.post(
            "/api/training-sessions",
            json=_payload(
                [athlete_id], session_kind="salida", objectives="Resistencia base"
            ),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["session_kind"] == "salida"
        assert created["objectives"] == "Resistencia base"

        # GET detalle — round-trip completo
        detail = await client.get(
            f"/api/training-sessions/{created['id']}", headers=headers
        )
        assert detail.status_code == 200
        body = detail.json()
        assert body["session_kind"] == "salida"
        assert body["objectives"] == "Resistencia base"

    async def test_create_without_kind_defaults_entrenamiento(
        self, client: AsyncClient
    ):
        headers = await _auth_coach(client)
        _, athlete_id = await _club_and_athlete(client, headers)

        resp = await client.post(
            "/api/training-sessions",
            json=_payload([athlete_id]),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["session_kind"] == "entrenamiento"

    async def test_patch_updates_kind_and_objectives(self, client: AsyncClient):
        headers = await _auth_coach(client)
        _, athlete_id = await _club_and_athlete(client, headers)

        created = (
            await client.post(
                "/api/training-sessions",
                json=_payload([athlete_id], session_kind="entrenamiento"),
                headers=headers,
            )
        ).json()

        patch = await client.patch(
            f"/api/training-sessions/{created['id']}",
            json={"session_kind": "actividad_conjunta", "objectives": "Trabajo en grupo"},
            headers=headers,
        )
        assert patch.status_code == 200, patch.text
        body = patch.json()
        assert body["session_kind"] == "actividad_conjunta"
        assert body["objectives"] == "Trabajo en grupo"

    async def test_objectives_too_long_returns_422(self, client: AsyncClient):
        headers = await _auth_coach(client)
        _, athlete_id = await _club_and_athlete(client, headers)
        resp = await client.post(
            "/api/training-sessions",
            json=_payload([athlete_id], objectives="x" * 1001),
            headers=headers,
        )
        assert resp.status_code == 422
