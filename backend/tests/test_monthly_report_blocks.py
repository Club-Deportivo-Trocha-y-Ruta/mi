"""Tests — Feature 022, T007 (US1).

Cubre:
1. Happy path: ``plan_entrenamiento`` es una clave de bloque auto-generable
   por IA — ``MonthlyReportBlocksUseCase.run_block`` produce un borrador
   dedicado (título/prompt propios de "Plan de entrenamiento", NO el
   fallback genérico que usa la clave cruda como título).
2. Happy path (nivel router): ``regenerate_report_block`` con
   ``block_key="plan_entrenamiento"`` sobre un reporte existente responde
   200 y persiste el bloque en ``narrative_blocks``.
3. Negativo: ``block_key`` desconocido/inválido es rechazado (422) tanto en
   el servicio (``regenerate_block`` -> ValueError) como en el router.

Nota: este test se escribe ANTES de T009 (que añade ``plan_entrenamiento``
a ``_BLOCK_MAX_WORDS/_TITLES/_PROMPTS`` en
``app/services/ai/use_cases/monthly_report_blocks.py``). Se espera que la
aserción de título dedicado en el test 1 FALLE hasta que T009 se implemente
— hoy la clave cae al fallback genérico (título = clave cruda).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.training_session import ALLOWED_BLOCK_KEYS
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.use_cases.monthly_report import MonthlyReportContext
from app.services.ai.use_cases.monthly_report_blocks import MonthlyReportBlocksUseCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**overrides) -> MonthlyReportContext:
    defaults = dict(
        club_name="Trocha y Ruta",
        period_year=2026,
        period_month=6,
        total_sessions_planned=8,
        total_sessions_executed=7,
        total_sessions_cancelled=1,
        attendance_stats=[],
        attendance_summary="7 atletas con asistencia promedio 82% (rango 60-100%).",
        focos_técnicos=["Frenado progresivo", "Cadencia en subida"],
        avg_rpe=6.0,
        avg_rubric_effort=3.9,
        avg_rubric_attitude=4.2,
        avg_rubric_technique=3.6,
        coach_observations=None,
        forbidden_names=frozenset(),
    )
    defaults.update(overrides)
    return MonthlyReportContext(**defaults)


def _canned_plan_text() -> str:
    return (
        "El plan de entrenamiento del mes priorizó bloques de fuerza general "
        "y técnica de frenado, alineados con el mesociclo vigente. Se mantuvo "
        "la relación entrenamiento-competencia definida para el grupo de alto "
        "rendimiento, con ajustes puntuales por clima y disponibilidad de pista. "
        "El foco principal estuvo en consolidar la cadencia de pedaleo en subida "
        "y la lectura de terreno técnico, reforzando hábitos de calentamiento y "
        "movilidad articular antes de cada sesión planificada del mesociclo. "
        "Se ajustaron cargas progresivamente según la respuesta observada del grupo."
    )


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
    r.metrics_snapshot = {}
    r.narrative_blocks = {}
    r.competition_results = []
    r.coach_observations = None
    r.generated_by_user_id = 1
    r.generated_at = datetime.now(timezone.utc)
    r.athlete_names = {}
    return r


# ---------------------------------------------------------------------------
# 1. plan_entrenamiento es una clave permitida
# ---------------------------------------------------------------------------


class TestPlanEntrenamientoIsAllowedKey:
    def test_plan_entrenamiento_esta_en_allowed_block_keys(self):
        assert "plan_entrenamiento" in ALLOWED_BLOCK_KEYS


# ---------------------------------------------------------------------------
# 2. Happy path — MonthlyReportBlocksUseCase.run_block genera un borrador
#    DEDICADO (no el fallback genérico) para plan_entrenamiento.
# ---------------------------------------------------------------------------


class TestPlanEntrenamientoAutoGeneration:
    @pytest.mark.asyncio
    async def test_run_block_produce_borrador_sin_error(self):
        """El bloque se genera sin lanzar excepción y sin error interno."""
        fake = FakeLLMProvider(canned=_canned_plan_text())
        uc = MonthlyReportBlocksUseCase(fake, PromptRegistry())
        ctx = _ctx()

        draft = await uc.run_block(ctx, "plan_entrenamiento")

        assert draft.block_key == "plan_entrenamiento"
        assert draft.error is None
        assert draft.ai_draft is not None
        assert draft.ai_draft.strip() != ""

    @pytest.mark.asyncio
    async def test_run_block_usa_titulo_y_prompt_dedicados_no_el_fallback_generico(self):
        """El prompt renderizado debe usar el título legible 'Plan de entrenamiento',
        NO el fallback genérico (clave cruda 'plan_entrenamiento' como título).

        Este es el comportamiento que T009 debe cablear en
        `_BLOCK_TITLES`/`_BLOCK_PROMPTS`/`_BLOCK_MAX_WORDS`. Se espera que esta
        aserción FALLE hasta que T009 se implemente.
        """
        fake = FakeLLMProvider(canned=_canned_plan_text())
        uc = MonthlyReportBlocksUseCase(fake, PromptRegistry())
        ctx = _ctx()

        await uc.run_block(ctx, "plan_entrenamiento")

        assert fake.last_request is not None
        rendered = fake.last_request.messages[-1].content

        # Título legible esperado — NO el fallback genérico que usa la clave
        # cruda como título ("Genera el bloque **plan_entrenamiento**").
        assert "Genera el bloque **Plan de entrenamiento**" in rendered
        # El prompt genérico de fallback ("Redacta el bloque 'plan_entrenamiento'.")
        # NO debe estar presente — debe usarse una instrucción dedicada.
        assert "Redacta el bloque 'plan_entrenamiento'." not in rendered


# ---------------------------------------------------------------------------
# 3. Happy path — router regenerate_report_block persiste el bloque
# ---------------------------------------------------------------------------


class TestRegenerateReportBlockRouterHappyPath:
    @pytest.mark.asyncio
    async def test_regenerar_plan_entrenamiento_sobre_reporte_existente(self):
        from app.models.user import UserRole
        from app.routers.monthly_reports import regenerate_report_block

        report = _make_report()
        coach = _make_user(1)
        coach.role = UserRole.coach

        club = MagicMock()
        club.id = 1
        club.name = "Trocha y Ruta"

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

        db = AsyncMock()
        db.execute = mock_execute
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        blocks_use_case = MagicMock()
        blocks_use_case.build_context_from_metrics.return_value = _ctx()
        draft = MagicMock()
        draft.ai_draft = _canned_plan_text()
        draft.ai_model = "fake-model"
        draft.generated_at = datetime.now(timezone.utc)
        blocks_use_case.run_block = AsyncMock(return_value=draft)

        metrics = MagicMock()

        with patch(
            "app.routers.monthly_reports.user_club_role",
            AsyncMock(return_value=MagicMock()),
        ), patch(
            "app.services.training.reports.compute_monthly_metrics",
            AsyncMock(return_value=metrics),
        ):
            out = await regenerate_report_block(
                club_id=1,
                year=2026,
                month=6,
                block_key="plan_entrenamiento",
                db=db,
                current_user=coach,
                blocks_use_case=blocks_use_case,
            )

        blocks_use_case.run_block.assert_awaited_once()
        called_block_key = blocks_use_case.run_block.await_args.args[1]
        assert called_block_key == "plan_entrenamiento"
        assert "plan_entrenamiento" in report.narrative_blocks
        assert (
            report.narrative_blocks["plan_entrenamiento"]["ai_draft"]
            == _canned_plan_text()
        )
        assert out is not None


# ---------------------------------------------------------------------------
# 4. Negativo — block_key desconocido/inválido es rechazado (422)
# ---------------------------------------------------------------------------


class TestRegenerateUnknownBlockKeyRejected:
    @pytest.mark.asyncio
    async def test_servicio_rechaza_clave_desconocida(self):
        """regenerate_block lanza ValueError para una clave fuera de ALLOWED_BLOCK_KEYS."""
        from app.services.training.reports import regenerate_block

        db = AsyncMock()
        blocks_use_case = MagicMock()

        with pytest.raises(ValueError, match="no permitida"):
            await regenerate_block(
                db=db,
                club_id=1,
                year=2026,
                month=6,
                block_key="bloque_inexistente",
                blocks_use_case=blocks_use_case,
            )

    @pytest.mark.asyncio
    async def test_router_responde_422_para_clave_invalida(self):
        """El router traduce la clave inválida a 422 (contrato:
        specs/022-align-monthly-report-format/contracts/monthly-report-api.md
        — "block_key domain now includes plan_entrenamiento (422 on unknown
        key, unchanged mechanism)").
        """
        from app.models.user import UserRole
        from app.routers.monthly_reports import regenerate_report_block

        coach = _make_user(1)
        coach.role = UserRole.coach

        db = AsyncMock()
        blocks_use_case = MagicMock()

        with patch(
            "app.routers.monthly_reports.user_club_role",
            AsyncMock(return_value=MagicMock()),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await regenerate_report_block(
                    club_id=1,
                    year=2026,
                    month=6,
                    block_key="bloque_inexistente",
                    db=db,
                    current_user=coach,
                    blocks_use_case=blocks_use_case,
                )

        assert exc_info.value.status_code == 422
