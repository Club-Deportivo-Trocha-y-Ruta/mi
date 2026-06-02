"""Tests para los modelos AthleteMonthlyNewsletter y AthleteBadge.

Cubre: enums, constraints Pydantic, factory helpers, from_orm_model,
separación email_blocks / pdf_only_blocks, privacidad sent_to.
No requiere base de datos real.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.athlete_badge import BadgeSource, BadgeType
from app.models.athlete_newsletter import NewsletterStatus
from app.schemas.athlete_newsletter import (
    AiNarrativeOut,
    AthleteNewsletterBatchCreate,
    AthleteNewsletterCreate,
    AthleteNewsletterPatch,
    AthleteNewsletterRead,
    NarrativeOverride,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_nl_obj(
    *,
    id_: int = 1,
    athlete_id: int = 5,
    year: int = 2026,
    month: int = 4,
    status: NewsletterStatus = NewsletterStatus.draft,
    metrics_snapshot: dict | None = None,
    ai_narrative: dict | None = None,
    coach_narrative_overrides: dict | None = None,
    badges_earned: list | None = None,
    sent_to: list | None = None,
    error_message: str | None = None,
) -> Any:
    """Construye un objeto tipo ORM para AthleteMonthlyNewsletter."""
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=id_,
        athlete_id=athlete_id,
        year=year,
        month=month,
        status=status,
        metrics_snapshot=metrics_snapshot,
        ai_narrative=ai_narrative,
        coach_narrative_overrides=coach_narrative_overrides,
        badges_earned=badges_earned,
        pdf_storage_url=None,
        pdf_generated_at=None,
        pdf_sha256=None,
        generated_by_user_id=None,
        approved_by_user_id=None,
        approved_at=None,
        sent_at=None,
        sent_to=sent_to,
        error_message=error_message,
        created_at=now,
        updated_at=now,
    )


def _valid_ai_narrative() -> dict:
    return {
        "strengths": "El atleta mostró gran compromiso en todas las sesiones del mes.",
        "area_to_develop": "Se recomienda mejorar la técnica de frenado en descensos.",
        "milestone": "Completó la primera sesión de XCO con ruta completa sin asistencia.",
        "model": "gemini-2.5-flash",
        "prompt_version": "athlete_monthly_newsletter_v1",
        "confidence": "medium",
    }


def _valid_snapshot() -> dict:
    return {
        "email_blocks": {
            "attendance": {"sessions_present": 8, "sessions_total": 10, "attendance_pct": 80.0},
            "technical": {"focos_tecnicos": ["Frenado", "Curvas"], "avg_rpe": 6.2},
        },
        "pdf_only_blocks": {
            "anthropometry": {"records": [{"height_cm": 152.0, "weight_kg": 45.0}]},
            "charts_context": {},
        },
    }


# ---------------------------------------------------------------------------
# NewsletterStatus enum
# ---------------------------------------------------------------------------


class TestNewsletterStatus:
    def test_all_values_defined(self):
        values = {s.value for s in NewsletterStatus}
        # PR5 (D3): 'outdated' añadido — boletín enviado que quedó
        # desactualizado por una re-ingesta (no se reenvía).
        assert values == {"draft", "approved", "sent", "failed", "outdated"}

    def test_is_str_enum(self):
        assert isinstance(NewsletterStatus.draft, str)

    def test_workflow_transitions(self):
        draft = NewsletterStatus.draft
        approved = NewsletterStatus.approved
        sent = NewsletterStatus.sent
        failed = NewsletterStatus.failed
        # Verificar que el flujo esperado draft→approved→sent es posible
        assert draft != approved
        assert approved != sent
        assert failed != sent


# ---------------------------------------------------------------------------
# BadgeType y BadgeSource enums
# ---------------------------------------------------------------------------


class TestBadgeEnums:
    def test_badge_type_all_values(self):
        types = {b.value for b in BadgeType}
        assert "attendance_100" in types
        assert "attendance_90" in types
        assert "attendance_75" in types
        assert "first_podium" in types
        assert "mtp" in types
        assert "top10" in types

    def test_badge_source_values(self):
        sources = {s.value for s in BadgeSource}
        assert sources == {"attendance", "race"}

    def test_badge_type_is_str(self):
        assert isinstance(BadgeType.attendance_100, str)

    def test_badge_source_is_str(self):
        assert isinstance(BadgeSource.attendance, str)


# ---------------------------------------------------------------------------
# AthleteNewsletterCreate schema
# ---------------------------------------------------------------------------


class TestAthleteNewsletterCreate:
    def test_valid_past_month(self):
        s = AthleteNewsletterCreate(year=2026, month=3)
        assert s.year == 2026
        assert s.month == 3

    def test_force_default_false(self):
        s = AthleteNewsletterCreate(year=2026, month=3)
        assert s.force is False

    def test_force_true_allowed(self):
        s = AthleteNewsletterCreate(year=2026, month=3, force=True)
        assert s.force is True

    def test_year_below_2020_invalid(self):
        with pytest.raises(ValidationError):
            AthleteNewsletterCreate(year=2019, month=3)

    def test_year_above_2100_invalid(self):
        with pytest.raises(ValidationError):
            AthleteNewsletterCreate(year=2101, month=3)

    def test_month_0_invalid(self):
        with pytest.raises(ValidationError):
            AthleteNewsletterCreate(year=2026, month=0)

    def test_month_13_invalid(self):
        with pytest.raises(ValidationError):
            AthleteNewsletterCreate(year=2026, month=13)

    def test_month_boundary_valid(self):
        s1 = AthleteNewsletterCreate(year=2026, month=1)
        s12 = AthleteNewsletterCreate(year=2026, month=12)
        assert s1.month == 1
        assert s12.month == 12


# ---------------------------------------------------------------------------
# NarrativeOverride schema
# ---------------------------------------------------------------------------


class TestNarrativeOverride:
    def test_all_none_by_default(self):
        n = NarrativeOverride()
        assert n.strengths is None
        assert n.area_to_develop is None
        assert n.milestone is None

    def test_partial_override(self):
        n = NarrativeOverride(strengths="Buen trabajo en curvas.")
        assert n.strengths == "Buen trabajo en curvas."
        assert n.area_to_develop is None

    def test_max_length_enforced(self):
        with pytest.raises(ValidationError):
            NarrativeOverride(strengths="x" * 501)

    def test_max_length_boundary(self):
        n = NarrativeOverride(strengths="x" * 500)
        assert len(n.strengths) == 500


# ---------------------------------------------------------------------------
# AthleteNewsletterPatch schema
# ---------------------------------------------------------------------------


class TestAthleteNewsletterPatch:
    def test_valid_patch(self):
        p = AthleteNewsletterPatch(
            coach_narrative_overrides=NarrativeOverride(
                strengths="Gran energía en los entrenamientos."
            )
        )
        assert p.coach_narrative_overrides.strengths == "Gran energía en los entrenamientos."

    def test_coach_narrative_overrides_required(self):
        with pytest.raises(ValidationError):
            AthleteNewsletterPatch()


# ---------------------------------------------------------------------------
# AthleteNewsletterBatchCreate schema
# ---------------------------------------------------------------------------


class TestAthleteNewsletterBatchCreate:
    def test_valid(self):
        b = AthleteNewsletterBatchCreate(year=2026, month=3)
        assert b.force is False

    def test_force_true(self):
        b = AthleteNewsletterBatchCreate(year=2026, month=3, force=True)
        assert b.force is True

    def test_invalid_month(self):
        with pytest.raises(ValidationError):
            AthleteNewsletterBatchCreate(year=2026, month=0)


# ---------------------------------------------------------------------------
# AthleteNewsletterRead.from_orm_model — separación email_blocks / pdf_only_blocks
# ---------------------------------------------------------------------------


class TestAthleteNewsletterRead:
    def test_email_blocks_extracted(self):
        """from_orm_model solo expone email_blocks, nunca pdf_only_blocks."""
        obj = _make_nl_obj(metrics_snapshot=_valid_snapshot())
        read = AthleteNewsletterRead.from_orm_model(obj)

        assert read.email_blocks is not None
        assert "attendance" in read.email_blocks
        assert "technical" in read.email_blocks
        # pdf_only_blocks NO debe aparecer en el schema de respuesta
        assert not hasattr(read, "pdf_only_blocks")
        assert "pdf_only_blocks" not in read.model_fields_set

    def test_pdf_only_blocks_never_in_response(self):
        """anthropometry NUNCA debe llegar al response JSON."""
        obj = _make_nl_obj(metrics_snapshot=_valid_snapshot())
        read = AthleteNewsletterRead.from_orm_model(obj)
        data = read.model_dump()

        assert "pdf_only_blocks" not in data
        assert "anthropometry" not in data

    def test_sent_to_never_serialized(self):
        """sent_to es PII — nunca debe aparecer en el response schema."""
        obj = _make_nl_obj(sent_to=["padre@example.com"])
        read = AthleteNewsletterRead.from_orm_model(obj)
        data = read.model_dump()

        assert "sent_to" not in data

    def test_ai_narrative_parsed(self):
        """ai_narrative se parsea a AiNarrativeOut si existe."""
        obj = _make_nl_obj(ai_narrative=_valid_ai_narrative())
        read = AthleteNewsletterRead.from_orm_model(obj)

        assert read.ai_narrative is not None
        assert isinstance(read.ai_narrative, AiNarrativeOut)
        assert read.ai_narrative.confidence == "medium"

    def test_ai_narrative_none_if_absent(self):
        obj = _make_nl_obj(ai_narrative=None)
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.ai_narrative is None

    def test_ai_narrative_none_if_invalid(self):
        """ai_narrative malformado → None silencioso (no crash)."""
        obj = _make_nl_obj(ai_narrative={"bad": "data"})
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.ai_narrative is None

    def test_coach_overrides_parsed(self):
        overrides = {"strengths": "Buen sprint final.", "area_to_develop": None, "milestone": None}
        obj = _make_nl_obj(coach_narrative_overrides=overrides)
        read = AthleteNewsletterRead.from_orm_model(obj)

        assert read.coach_narrative_overrides is not None
        assert read.coach_narrative_overrides.strengths == "Buen sprint final."

    def test_no_metrics_snapshot(self):
        """metrics_snapshot=None devuelve email_blocks=None sin crashear."""
        obj = _make_nl_obj(metrics_snapshot=None)
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.email_blocks is None

    def test_status_draft(self):
        obj = _make_nl_obj(status=NewsletterStatus.draft)
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.status == NewsletterStatus.draft

    def test_status_approved(self):
        obj = _make_nl_obj(status=NewsletterStatus.approved)
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.status == NewsletterStatus.approved

    def test_error_message_preserved(self):
        obj = _make_nl_obj(error_message="Timeout IA: no respondió en 45s.")
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.error_message == "Timeout IA: no respondió en 45s."

    def test_badges_earned_in_response(self):
        badges = [{"badge_type": "attendance_100", "period_year": 2026, "period_month": 4}]
        obj = _make_nl_obj(badges_earned=badges)
        read = AthleteNewsletterRead.from_orm_model(obj)
        assert read.badges_earned == badges


# ---------------------------------------------------------------------------
# AiNarrativeOut schema
# ---------------------------------------------------------------------------


class TestAiNarrativeOut:
    def test_valid(self):
        a = AiNarrativeOut(**_valid_ai_narrative())
        assert a.confidence in {"low", "medium", "high"}

    def test_missing_strengths_invalid(self):
        data = _valid_ai_narrative()
        del data["strengths"]
        with pytest.raises(ValidationError):
            AiNarrativeOut(**data)

    def test_all_confidence_levels(self):
        for conf in ("low", "medium", "high"):
            data = _valid_ai_narrative()
            data["confidence"] = conf
            a = AiNarrativeOut(**data)
            assert a.confidence == conf
