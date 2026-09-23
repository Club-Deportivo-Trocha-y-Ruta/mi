"""Tests para race_insight_dispatcher.py.

Decisión cerrada (2026-09-23, reestructura Competencias): aprobar un
insight de carrera NUNCA envía email a padres — todas las prioridades
(A, B, C, CD, UNKNOWN) se publican solo in-app. Esta suite reemplaza la
anterior (Sprint 3, "resumen embebido" por email) que quedó obsoleta
junto con el código que testeaba: helpers de extracto/URL del email,
render del template HTML y el flujo de envío (todo eliminado del
dispatcher).

Cubre:
- Todas las prioridades (A/B/C/CD/UNKNOWN) resuelven ``SENT_IN_APP``,
  nunca email — incluye el caso campeonato (``is_championship=True``).
- ``NotificationChannel.EMAIL`` / ``NotificationDecision.SENT_EMAIL`` ya
  no existen (regresión dura contra que el código de correo reaparezca).
- Guards que siguen sin notificar nada: ``coach_approved=False``,
  ``is_active != 1``, ``valida_num=0`` (agregado de temporada),
  ``event_id`` nulo, atleta archivado, sin padres con email.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.race_event import RaceEventPriority
from app.services.notification.race_event_tier import RaceTier
from app.services.notification.race_insight_dispatcher import (
    NotificationChannel,
    NotificationDecision,
    dispatch_insight_notification,
)

# ---------------------------------------------------------------------------
# Fixtures compartidas (sin nombres reales — placeholders genéricos)
# ---------------------------------------------------------------------------

PARENT = SimpleNamespace(id=20, email="padre@test.com", first_name="Padre", last_name="Acudiente")
ATHLETE = SimpleNamespace(first_name="Deportista", last_name="Prueba", deleted_at=None)


def _make_event(*, priority=None, is_championship=False, series_level=None):
    return SimpleNamespace(
        id=7,
        event_date=date(2026, 5, 17),
        location="Cali",
        sequence_number=4,
        is_championship=is_championship,
        priority=priority,
        series=SimpleNamespace(season_year=2026, level=series_level),
    )


def _make_fresh_insight(*, event, athlete, insight_id=99):
    return SimpleNamespace(
        id=insight_id,
        athlete_id=42,
        valida_num=4,
        season=2026,
        summary_text="La deportista completó la válida en buen orden.",
        prompt_version="race_analyst_v3",
        event=event,
        event_id=event.id if event else None,
        athlete=athlete,
    )


def _base_insight(*, insight_id=99, event_id=7, **overrides):
    base = dict(
        id=insight_id,
        athlete_id=42,
        coach_approved=True,
        is_active=1,
        valida_num=4,
        event_id=event_id,
        season=2026,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_db(*, fresh_insight, parents):
    """DB mock con 2 llamadas a execute: load_insight_with_relations, load_parents."""
    call_count = {"n": 0}

    async def _fake_execute(_stmt):
        call_count["n"] += 1
        n = call_count["n"]
        res = MagicMock()
        if n == 1:
            res.scalar_one_or_none.return_value = fresh_insight
        elif n == 2:
            res.scalars.return_value.all.return_value = parents
        else:
            res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = []
        return res

    db = MagicMock()
    db.execute = _fake_execute
    return db


# ---------------------------------------------------------------------------
# Regresión dura: el código de envío de correo fue eliminado
# ---------------------------------------------------------------------------


def test_email_channel_and_decision_were_removed():
    """El canal EMAIL y las decisiones ligadas a envío de correo ya no existen."""
    assert not hasattr(NotificationChannel, "EMAIL")
    assert not hasattr(NotificationDecision, "SENT_EMAIL")
    assert not hasattr(NotificationDecision, "SKIPPED_TIER")


# ---------------------------------------------------------------------------
# Ninguna prioridad dispara email — todas terminan en SENT_IN_APP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "priority,is_championship,expected_tier",
    [
        (RaceEventPriority.A, False, RaceTier.A),
        (RaceEventPriority.B, False, RaceTier.B),
        (RaceEventPriority.C, False, RaceTier.C),
        (RaceEventPriority.CD, False, RaceTier.CD),
        (None, False, RaceTier.UNKNOWN),
        (None, True, RaceTier.CD),  # campeonato vía is_championship, sin priority
    ],
    ids=["tier-a", "tier-b", "tier-c", "tier-cd", "tier-unknown", "championship-flag"],
)
async def test_dispatch_never_sends_email_for_any_tier(priority, is_championship, expected_tier):
    """2026-09-23: aprobar nunca envía correo, sin importar el tier de la válida."""
    event = _make_event(priority=priority, is_championship=is_championship)
    fresh = _make_fresh_insight(event=event, athlete=ATHLETE)
    db = _make_db(fresh_insight=fresh, parents=[PARENT])
    insight = _base_insight()

    result = await dispatch_insight_notification(insight, db)

    assert result.decision == NotificationDecision.SENT_IN_APP
    assert result.tier == expected_tier
    assert result.channels == [NotificationChannel.IN_APP]
    assert result.in_app_emitted == 1


@pytest.mark.asyncio
async def test_dispatch_championship_national_and_departmental_both_in_app():
    """Regresión: campeonato nacional o departamental, ambos solo in-app.

    La distinción de etiqueta ("Campeonato Nacional" vs "Departamental")
    vivía en el email eliminado; el dispatcher ya no construye etiquetas.
    """
    from app.models.race_series import RaceSeriesLevel

    for level in (RaceSeriesLevel.national, RaceSeriesLevel.departmental):
        event = _make_event(is_championship=True, series_level=level)
        fresh = _make_fresh_insight(event=event, athlete=ATHLETE, insight_id=200)
        db = _make_db(fresh_insight=fresh, parents=[PARENT])
        insight = _base_insight(insight_id=200)

        result = await dispatch_insight_notification(insight, db)

        assert result.decision == NotificationDecision.SENT_IN_APP
        assert result.tier == RaceTier.CD
        assert result.channels == [NotificationChannel.IN_APP]


@pytest.mark.asyncio
async def test_dispatch_emits_one_in_app_event_per_parent():
    """Con 2 padres/acudientes, se emiten 2 eventos in-app (0 emails)."""
    parent_2 = SimpleNamespace(id=21, email="otro@test.com", first_name="Otro", last_name="Acudiente")
    event = _make_event(priority=RaceEventPriority.A)
    fresh = _make_fresh_insight(event=event, athlete=ATHLETE)
    db = _make_db(fresh_insight=fresh, parents=[PARENT, parent_2])
    insight = _base_insight()

    result = await dispatch_insight_notification(insight, db)

    assert result.decision == NotificationDecision.SENT_IN_APP
    assert result.in_app_emitted == 2


# ---------------------------------------------------------------------------
# Guards que ya no llegan a notificar (comportamiento sin cambios)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_skips_when_not_approved():
    insight = SimpleNamespace(id=1, coach_approved=False)
    result = await dispatch_insight_notification(insight, MagicMock())
    assert result.decision == NotificationDecision.SKIPPED_NOT_APPROVED


@pytest.mark.asyncio
async def test_dispatch_skips_when_inactive():
    insight = SimpleNamespace(id=1, coach_approved=True, is_active=0)
    result = await dispatch_insight_notification(insight, MagicMock())
    assert result.decision == NotificationDecision.SKIPPED_INACTIVE


@pytest.mark.asyncio
async def test_dispatch_skips_season_aggregate():
    insight = SimpleNamespace(id=1, coach_approved=True, is_active=1, valida_num=0)
    result = await dispatch_insight_notification(insight, MagicMock())
    assert result.decision == NotificationDecision.SKIPPED_AGGREGATE


@pytest.mark.asyncio
async def test_dispatch_skips_when_no_event_id():
    insight = SimpleNamespace(
        id=1, coach_approved=True, is_active=1, valida_num=4, event_id=None
    )
    result = await dispatch_insight_notification(insight, MagicMock())
    assert result.decision == NotificationDecision.SKIPPED_NO_EVENT


@pytest.mark.asyncio
async def test_dispatch_skips_when_athlete_archived():
    event = _make_event(priority=RaceEventPriority.A)
    archived_athlete = SimpleNamespace(
        first_name="Deportista", last_name="Prueba", deleted_at=date(2026, 6, 1)
    )
    fresh = _make_fresh_insight(event=event, athlete=archived_athlete)
    db = _make_db(fresh_insight=fresh, parents=[PARENT])
    insight = _base_insight()

    result = await dispatch_insight_notification(insight, db)

    assert result.decision == NotificationDecision.SKIPPED_ARCHIVED_ATHLETE


@pytest.mark.asyncio
async def test_dispatch_skips_when_no_parents_with_email():
    event = _make_event(priority=RaceEventPriority.A)
    fresh = _make_fresh_insight(event=event, athlete=ATHLETE)
    db = _make_db(fresh_insight=fresh, parents=[])
    insight = _base_insight()

    result = await dispatch_insight_notification(insight, db)

    assert result.decision == NotificationDecision.SKIPPED_NO_PARENTS
