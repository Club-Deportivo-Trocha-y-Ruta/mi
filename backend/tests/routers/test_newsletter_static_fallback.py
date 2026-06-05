"""Tests US3 (T026): fallback estático del boletín mensual individual.

Verifica el comportamiento de `_generate_newsletter_for_athlete`:

  - SIN consentimiento IA: la generación NO falla con 409. Se produce un
    borrador con subtítulos/resumen/apoyo estáticos y la valoración del
    entrenador como placeholder neutro.
  - CON consentimiento IA: se invoca el LLM (mock) y los campos IA
    (block_captions/month_highlights) se poblan en ai_narrative.

Estrategia: mocks vía MagicMock/AsyncMock (sin MySQL), patcheando los
servicios internos importados dentro de la función.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.athlete_newsletter import NewsletterStatus
from app.routers.athlete_monthly_newsletters import _generate_newsletter_for_athlete
from app.services.training.newsletter_static_copy import COACH_NARRATIVE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


def _make_athlete(id_: int = 5, club_id: int = 1) -> Any:
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        first_name="Atleta",
        last_name="Prueba",
        birth_date=date(2012, 3, 15),
    )


def _make_user(id_: int = 1) -> Any:
    from app.models.user import UserRole

    return SimpleNamespace(id=id_, role=UserRole.coach)


_SNAPSHOT = {
    "email_blocks": {
        "period": {"year": 2026, "month": 3},
        "attendance": {"sessions_present": 9, "sessions_total": 10, "attendance_pct": 90.0},
        "technical": {"focos_tecnicos": ["Frenado"]},
        "race_results": {"has_races": False, "results": []},
        "badges": {"items": []},
        "support_at_home": {"tips": [{"category": "sueno", "title": "Sueño", "text": "..."}]},
    },
    "pdf_only_blocks": {"anthropometry": {"has_records": False}},
}


def _make_db(existing_newsletter=None, club_athletes=None):
    """DB mock: 1ª execute = lookup newsletter existente; 2ª = atletas del club."""
    club_athletes = club_athletes if club_athletes is not None else [_make_athlete()]

    nl_result = MagicMock()
    nl_result.scalar_one_or_none.return_value = existing_newsletter

    athletes_result = MagicMock()
    athletes_result.scalars.return_value = athletes_result
    athletes_result.all.return_value = club_athletes

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[nl_result, athletes_result])
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


async def _run(*, has_consent: bool, ai_use_case_factory=None):
    db = _make_db()

    captured = {}

    def _capture_add(obj):
        captured["nl"] = obj

    db.add.side_effect = _capture_add

    patches = [
        patch(
            "app.services.privacy.athlete_has_ai_processing_consent",
            new_callable=AsyncMock,
            return_value=has_consent,
        ),
        patch(
            "app.services.training.newsletter_builder.build_newsletter_metrics",
            new_callable=AsyncMock,
            return_value=_SNAPSHOT,
        ),
    ]

    cm = []
    for p in patches:
        cm.append(p.__enter__())

    try:
        if ai_use_case_factory is not None:
            with patch(
                "app.services.ai.use_cases.athlete_monthly_newsletter.AthleteNewsletterUseCase",
                ai_use_case_factory,
            ):
                nl = await _generate_newsletter_for_athlete(
                    db=db,
                    athlete=_make_athlete(),
                    year=2026,
                    month=3,
                    current_user=_make_user(),
                    force=False,
                    llm_provider=MagicMock(),
                    prompt_registry=MagicMock(),
                )
        else:
            nl = await _generate_newsletter_for_athlete(
                db=db,
                athlete=_make_athlete(),
                year=2026,
                month=3,
                current_user=_make_user(),
                force=False,
                llm_provider=MagicMock(),
                prompt_registry=MagicMock(),
            )
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

    return nl


# ---------------------------------------------------------------------------
# SIN consentimiento → fallback estático, NO hard-fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_consent_does_not_hard_fail():
    """Sin consentimiento IA, el boletín se genera como draft (no 409)."""
    nl = await _run(has_consent=False)

    assert nl.status == NewsletterStatus.draft
    assert nl.error_message is None


@pytest.mark.asyncio
async def test_no_consent_static_captions_and_highlights_render():
    nl = await _run(has_consent=False)

    narrative = nl.ai_narrative
    assert narrative is not None
    # Subtítulos estáticos para bloques email-safe + antropometría.
    captions = narrative.get("block_captions") or {}
    assert "attendance" in captions
    assert "technical" in captions
    assert "anthropometry" in captions
    # Resumen del mes presente.
    assert narrative.get("month_highlights")
    # Marca de origen estático.
    assert narrative.get("source") == "static_fallback"


@pytest.mark.asyncio
async def test_no_consent_coach_narrative_is_placeholder():
    """La valoración del entrenador queda como placeholder neutro (sin IA)."""
    nl = await _run(has_consent=False)
    assert nl.ai_narrative.get("strengths") == COACH_NARRATIVE_UNAVAILABLE
    assert nl.ai_narrative.get("area_to_develop") == ""
    assert nl.ai_narrative.get("milestone") == ""


@pytest.mark.asyncio
async def test_no_consent_support_at_home_present_in_snapshot():
    """El bloque de apoyo en casa sigue disponible en el snapshot."""
    nl = await _run(has_consent=False)
    support = nl.metrics_snapshot["email_blocks"]["support_at_home"]
    assert support.get("tips")


# ---------------------------------------------------------------------------
# CON consentimiento → IA poblada (mock del use case)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_consent_ai_fields_populated():
    ai_dump = {
        "strengths": "Gran constancia y compromiso durante todas las sesiones del mes en el club.",
        "area_to_develop": "Seguir afinando la técnica de frenado en descensos con curvas cerradas.",
        "milestone": "Completó el primer recorrido técnico largo sin asistencia del entrenador.",
        "block_captions": {
            "attendance": "La asistencia constante ayuda a consolidar el aprendizaje técnico del mes.",
            "technical": "El trabajo técnico priorizó habilidades concretas sobre la intensidad este mes.",
        },
        "month_highlights": "Un mes con excelente constancia y progreso técnico sobre la bici.",
        "model": "fake",
        "prompt_version": "athlete_monthly_newsletter_v1",
        "confidence": "high",
    }

    fake_result = SimpleNamespace(model_dump=lambda: dict(ai_dump))
    fake_uc = MagicMock()
    fake_uc.run = AsyncMock(return_value=fake_result)
    factory = MagicMock(return_value=fake_uc)

    nl = await _run(has_consent=True, ai_use_case_factory=factory)

    assert nl.status == NewsletterStatus.draft
    assert nl.error_message is None
    narrative = nl.ai_narrative
    assert narrative["confidence"] == "high"
    assert narrative["block_captions"]["attendance"].startswith("La asistencia")
    assert narrative["month_highlights"].startswith("Un mes")


@pytest.mark.asyncio
async def test_with_consent_ai_failure_degrades_to_static():
    """Si la IA falla con consentimiento, degrada a estático y NO bloquea."""
    from app.services.ai.use_cases.athlete_monthly_newsletter import (
        AthleteNewsletterLLMTimeout,
    )

    fake_uc = MagicMock()
    fake_uc.run = AsyncMock(side_effect=AthleteNewsletterLLMTimeout("timeout"))
    factory = MagicMock(return_value=fake_uc)

    nl = await _run(has_consent=True, ai_use_case_factory=factory)

    # Documento válido (draft) con fallback estático y telemetría de error.
    assert nl.status == NewsletterStatus.draft
    assert nl.error_message == "llm_timeout"
    captions = nl.ai_narrative.get("block_captions") or {}
    assert "attendance" in captions
    assert nl.ai_narrative.get("source") == "static_fallback"
