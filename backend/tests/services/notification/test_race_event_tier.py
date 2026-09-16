"""Tests de ``app/services/notification/race_event_tier.py``.

Hotfix "identidad de válida" (2026-09-16, ver
``~/.claude/plans/multicopa-identidad-valida.md``): el tier ya no se deriva
de un dict hardcodeado ``_CALENDAR_TIERS`` (que solo conocía Copa Valle 2026
y colisionaba con cualquier otra copa reutilizando ``sequence_number``) sino
de la columna ``RaceEvent.priority``. Cubre:

- Mapeo directo ``priority`` → ``RaceTier`` (A/B/C/CD).
- ``priority=None`` → ``RaceTier.UNKNOWN`` (fallback conservador, sin email).
- ``is_championship=True`` y ``sequence_number == 99`` siguen forzando
  ``CD`` con prioridad sobre ``priority`` (aunque ``priority`` traiga otro
  valor o esté en ``None`` — el Campeonato nunca depende de esta columna).
- ``should_email_parents`` sigue disparando solo para A/CD.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.race_event import RaceEventPriority
from app.services.notification.race_event_tier import (
    RaceTier,
    get_race_tier,
    should_email_parents,
)


def _event(
    *,
    event_id: int = 1,
    sequence_number: int = 4,
    is_championship: bool = False,
    priority: RaceEventPriority | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=event_id,
        sequence_number=sequence_number,
        is_championship=is_championship,
        priority=priority,
    )


# ---------------------------------------------------------------------------
# Mapeo directo priority -> RaceTier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "priority,expected_tier",
    [
        (RaceEventPriority.A, RaceTier.A),
        (RaceEventPriority.B, RaceTier.B),
        (RaceEventPriority.C, RaceTier.C),
        (RaceEventPriority.CD, RaceTier.CD),
    ],
)
def test_get_race_tier_maps_priority_directly(priority, expected_tier):
    event = _event(priority=priority)
    assert get_race_tier(event) == expected_tier


def test_get_race_tier_none_priority_is_unknown():
    """Sin prioridad asignada (ej. cualquier copa que no sea Copa Valle
    2026, o una válida nueva aún no priorizada por el coach) → UNKNOWN,
    fallback conservador que NO dispara email."""
    event = _event(priority=None)
    assert get_race_tier(event) == RaceTier.UNKNOWN
    assert should_email_parents(RaceTier.UNKNOWN) is False


# ---------------------------------------------------------------------------
# Campeonato: is_championship / sequence_number==99 tienen prioridad sobre
# la columna priority.
# ---------------------------------------------------------------------------


def test_is_championship_forces_cd_regardless_of_priority():
    event = _event(is_championship=True, priority=RaceEventPriority.B)
    assert get_race_tier(event) == RaceTier.CD


def test_is_championship_forces_cd_when_priority_is_none():
    event = _event(is_championship=True, priority=None)
    assert get_race_tier(event) == RaceTier.CD


def test_sequence_number_99_forces_cd_regardless_of_priority():
    event = _event(sequence_number=99, is_championship=False, priority=RaceEventPriority.C)
    assert get_race_tier(event) == RaceTier.CD


def test_sequence_number_99_forces_cd_when_priority_is_none():
    event = _event(sequence_number=99, is_championship=False, priority=None)
    assert get_race_tier(event) == RaceTier.CD


# ---------------------------------------------------------------------------
# should_email_parents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tier,expected",
    [
        (RaceTier.A, True),
        (RaceTier.CD, True),
        (RaceTier.B, False),
        (RaceTier.C, False),
        (RaceTier.UNKNOWN, False),
    ],
)
def test_should_email_parents(tier, expected):
    assert should_email_parents(tier) is expected


# ---------------------------------------------------------------------------
# No hardcoded calendar: dos copas distintas con el mismo sequence_number
# resuelven tier independientemente por su propia columna priority.
# ---------------------------------------------------------------------------


def test_two_cups_same_sequence_number_resolve_independently():
    """El bug real: Copa Valle V4 (priority=A) y Copa Let's Go V4 (priority
    NULL, sin asignar) comparten sequence_number=4 en la misma temporada —
    ya no hay un dict global por (season, sequence_number) que pueda
    confundirlas."""
    copa_valle_v4 = _event(event_id=43, sequence_number=4, priority=RaceEventPriority.A)
    lets_go_v4 = _event(event_id=99, sequence_number=4, priority=None)

    assert get_race_tier(copa_valle_v4) == RaceTier.A
    assert get_race_tier(lets_go_v4) == RaceTier.UNKNOWN
    assert should_email_parents(get_race_tier(lets_go_v4)) is False
