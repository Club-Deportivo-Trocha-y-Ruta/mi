"""Tests — Feature 022, T030 (regresión).

Verifica que ``regenerate_block`` (servicio, invocado por el endpoint
``POST /{club_id}/monthly-reports/{year}/{month}/blocks/{block_key}/regenerate``)
solo toca el bloque narrativo objetivo (``ai_draft``/``ai_generated_at``/
``ai_model`` — y ``final_text`` cuando el coach no lo había editado). El
resto del reporte debe quedar byte-por-byte intacto:

1. Todas las DEMÁS claves de ``narrative_blocks`` (contenido y estructura).
2. ``metrics_snapshot`` completo.
3. ``competition_results`` completo (lista de dicts).

Esto protege contra una regresión donde `regenerate_block` sobreescriba
accidentalmente el snapshot completo del reporte en vez de mutar solo el
bloque solicitado (riesgo real dado que todo vive en columnas JSON
adicionales sin migración, feature 022).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.training.reports import regenerate_block


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canned_text() -> str:
    return (
        "Borrador regenerado del bloque objetivo, con contenido nuevo "
        "generado por la IA para este mes en particular del mesociclo."
    )


def _full_metrics_snapshot() -> dict:
    """Snapshot representativo — debe permanecer 100% intacto tras regenerar."""
    return {
        "total_sessions_planned": 8,
        "total_sessions_executed": 7,
        "total_sessions_cancelled": 1,
        "attendance_by_athlete": {"1": 0.85, "2": 0.7},
        "technical_focus_list": ["Frenado progresivo", "Cadencia en subida"],
        "avg_rpe": 6.2,
        "avg_rubric_effort": 3.9,
        "avg_rubric_attitude": 4.2,
        "avg_rubric_technique": 3.6,
        "custom_extra_key_added_by_feature_022": {"nested": [1, 2, 3]},
    }


def _full_narrative_blocks() -> dict:
    """Múltiples bloques narrativos ya poblados — solo `objetivo` debe cambiar."""
    fixed_dt = "2026-06-01T10:00:00+00:00"
    return {
        "objetivo": {
            "ai_draft": "Borrador viejo del objetivo.",
            "final_text": "Borrador viejo del objetivo.",
            "ai_model": "old-model",
            "ai_generated_at": fixed_dt,
        },
        "plan_entrenamiento": {
            "ai_draft": "Plan de entrenamiento sin tocar.",
            "final_text": "Plan de entrenamiento sin tocar (editado por coach).",
            "ai_model": "old-model",
            "ai_generated_at": fixed_dt,
        },
        "desarrollo": {
            "ai_draft": "Desarrollo del mes sin tocar.",
            "final_text": "Desarrollo del mes sin tocar.",
            "ai_model": "old-model",
            "ai_generated_at": fixed_dt,
        },
        "competencia": {
            "ai_draft": "Bloque de competencia sin tocar.",
            "final_text": "Bloque de competencia sin tocar.",
            "ai_model": "old-model",
            "ai_generated_at": fixed_dt,
        },
    }


def _full_competition_results() -> list:
    """Lista de resultados de competencia — debe permanecer intacta."""
    return [
        {
            "event_id": 10,
            "event_name": "Copa Valle III",
            "athlete_pseudonym": "Atleta A",
            "position": 3,
            "category": "Sub-13",
        },
        {
            "event_id": 11,
            "event_name": "Copa Valle IV",
            "athlete_pseudonym": "Atleta B",
            "position": 1,
            "category": "Sub-15",
        },
    ]


def _make_user(uid: int = 1) -> MagicMock:
    u = MagicMock()
    u.id = uid
    return u


def _make_report(rid: int = 1, club_id: int = 1, year: int = 2026, month: int = 6) -> MagicMock:
    r = MagicMock()
    r.id = rid
    r.club_id = club_id
    r.year = year
    r.month = month
    r.ai_summary = "Resumen de prueba."
    r.metrics_snapshot = _full_metrics_snapshot()
    r.narrative_blocks = _full_narrative_blocks()
    r.competition_results = _full_competition_results()
    r.coach_observations = None
    r.generated_by_user_id = 1
    r.generated_at = datetime.now(timezone.utc)
    r.athlete_names = {}
    return r


def _make_execute_sequence(report: MagicMock, club: MagicMock):
    """Emula la secuencia de queries de `regenerate_block`: reporte, club, atletas."""
    call_count = {"n": 0}

    async def mock_execute(stmt):
        call_count["n"] += 1
        result = MagicMock()
        if call_count["n"] == 1:
            result.scalar_one_or_none.return_value = report
        elif call_count["n"] == 2:
            result.scalar_one_or_none.return_value = club
        else:
            result.scalars.return_value.all.return_value = []
        return result

    return mock_execute


# ---------------------------------------------------------------------------
# 1. Happy path — regenerar "objetivo" no toca el resto del reporte
# ---------------------------------------------------------------------------


class TestRegenerateBlockDoesNotLeakIntoOtherFields:
    @pytest.mark.asyncio
    async def test_regenerar_objetivo_preserva_otros_bloques_metricas_y_resultados(self):
        report = _make_report()

        # Snapshot completo ANTES de regenerar (deep copy — el objeto vivo
        # se muta in-place, así que necesitamos una copia independiente).
        before_metrics_snapshot = copy.deepcopy(report.metrics_snapshot)
        before_narrative_blocks = copy.deepcopy(report.narrative_blocks)
        before_competition_results = copy.deepcopy(report.competition_results)

        club = MagicMock()
        club.id = 1
        club.name = "Trocha y Ruta"

        db = AsyncMock()
        db.execute = _make_execute_sequence(report, club)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        blocks_use_case = MagicMock()
        blocks_use_case.build_context_from_metrics.return_value = MagicMock()
        draft = MagicMock()
        draft.ai_draft = _canned_text()
        draft.ai_model = "fake-model-v2"
        draft.generated_at = datetime.now(timezone.utc)
        blocks_use_case.run_block = AsyncMock(return_value=draft)

        metrics = MagicMock()

        with patch(
            "app.services.training.reports.compute_monthly_metrics",
            AsyncMock(return_value=metrics),
        ):
            updated_report = await regenerate_block(
                db=db,
                club_id=1,
                year=2026,
                month=6,
                block_key="objetivo",
                blocks_use_case=blocks_use_case,
            )

        # --- El bloque objetivo SÍ cambió (ai_draft/ai_model/ai_generated_at) ---
        objetivo_after = updated_report.narrative_blocks["objetivo"]
        assert objetivo_after["ai_draft"] == _canned_text()
        assert objetivo_after["ai_model"] == "fake-model-v2"
        assert objetivo_after["ai_draft"] != before_narrative_blocks["objetivo"]["ai_draft"]

        # --- metrics_snapshot: intacto, byte-por-byte ---
        assert updated_report.metrics_snapshot == before_metrics_snapshot

        # --- competition_results: intacto, byte-por-byte ---
        assert updated_report.competition_results == before_competition_results

        # --- Las DEMÁS claves de narrative_blocks: intactas, byte-por-byte ---
        untouched_keys = ["plan_entrenamiento", "desarrollo", "competencia"]
        for key in untouched_keys:
            assert updated_report.narrative_blocks[key] == before_narrative_blocks[key], (
                f"El bloque '{key}' cambió al regenerar 'objetivo' — regresión de "
                f"aislamiento entre bloques."
            )

        # --- No aparecieron claves nuevas inesperadas en narrative_blocks ---
        assert set(updated_report.narrative_blocks.keys()) == set(
            before_narrative_blocks.keys()
        )

    @pytest.mark.asyncio
    async def test_regenerar_objetivo_preserva_final_text_editado_por_coach(self):
        """Si el coach ya había editado `final_text` de OTRO bloque
        (difiere de su ai_draft), regenerar un bloque distinto no debe
        tocarlo. Y para el bloque regenerado, si el coach lo había editado
        también debe conservarse el `final_text` editado (comportamiento
        documentado en `regenerate_block`).
        """
        report = _make_report()
        # Simular que el coach ya editó "objetivo" a mano.
        report.narrative_blocks["objetivo"]["final_text"] = (
            "Texto final editado a mano por el coach — distinto del ai_draft viejo."
        )
        before_narrative_blocks = copy.deepcopy(report.narrative_blocks)

        club = MagicMock()
        club.id = 1
        club.name = "Trocha y Ruta"

        db = AsyncMock()
        db.execute = _make_execute_sequence(report, club)
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        blocks_use_case = MagicMock()
        blocks_use_case.build_context_from_metrics.return_value = MagicMock()
        draft = MagicMock()
        draft.ai_draft = _canned_text()
        draft.ai_model = "fake-model-v2"
        draft.generated_at = datetime.now(timezone.utc)
        blocks_use_case.run_block = AsyncMock(return_value=draft)

        metrics = MagicMock()

        with patch(
            "app.services.training.reports.compute_monthly_metrics",
            AsyncMock(return_value=metrics),
        ):
            updated_report = await regenerate_block(
                db=db,
                club_id=1,
                year=2026,
                month=6,
                block_key="objetivo",
                blocks_use_case=blocks_use_case,
            )

        objetivo_after = updated_report.narrative_blocks["objetivo"]
        # El ai_draft se actualiza siempre...
        assert objetivo_after["ai_draft"] == _canned_text()
        # ...pero el final_text editado por el coach se preserva (no se
        # sobreescribe con el nuevo ai_draft).
        assert (
            objetivo_after["final_text"]
            == before_narrative_blocks["objetivo"]["final_text"]
        )

        # El resto de bloques sigue intacto.
        for key in ["plan_entrenamiento", "desarrollo", "competencia"]:
            assert updated_report.narrative_blocks[key] == before_narrative_blocks[key]
