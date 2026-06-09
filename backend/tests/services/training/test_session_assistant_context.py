"""Tests para session_assistant_context.py (feature 006).

Cubre (tasks.md T027):
  - build_aggregate_context produce age_mix correcto desde birth_dates
  - days_to_next_race y priority son correctos vs COPA_VALLE_2026
  - El dict retornado NO contiene nombres ni IDs de atletas
  - COPA_VALLE_2026 constante cubre las 8 válidas documentadas en CLAUDE.md
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.training.session_assistant_context import (
    COPA_VALLE_2026,
    _age_group,
    _race_proximity,
    _season_phase,
    build_aggregate_context,
)


# ---------------------------------------------------------------------------
# Tests de _age_group
# ---------------------------------------------------------------------------


def test_age_group_under_13():
    assert _age_group(10.5) == "10-12"
    assert _age_group(12.9) == "10-12"


def test_age_group_13_to_15():
    assert _age_group(13.0) == "13-15"
    assert _age_group(14.5) == "13-15"
    assert _age_group(15.9) == "13-15"


def test_age_group_16_plus():
    assert _age_group(16.0) == "16+"
    assert _age_group(18.5) == "16+"


# ---------------------------------------------------------------------------
# Tests de _race_proximity
# ---------------------------------------------------------------------------


def test_race_proximity_before_first_valid():
    """Antes de la primera válida: retorna días hasta Válida I."""
    days, priority = _race_proximity(date(2026, 1, 1))
    assert days == 30  # 31 ene - 1 ene = 30 días
    assert priority == "A"


def test_race_proximity_on_race_day():
    """El mismo día de la válida: days=0."""
    days, priority = _race_proximity(date(2026, 1, 31))
    assert days == 0
    assert priority == "A"


def test_race_proximity_after_valid_iv_before_cd():
    """Entre Válida IV (17 may) y CD (12 jun): apunta a CD."""
    days, priority = _race_proximity(date(2026, 5, 18))
    expected_days = (date(2026, 6, 12) - date(2026, 5, 18)).days
    assert days == expected_days
    assert priority == "A"


def test_race_proximity_valid_iii_is_c():
    """Válida III (19 abr) tiene prioridad C."""
    days, priority = _race_proximity(date(2026, 4, 19))
    assert days == 0
    assert priority == "C"


def test_race_proximity_valid_v_is_b():
    """Válida V (1 ago) tiene prioridad B."""
    days, priority = _race_proximity(date(2026, 8, 1))
    assert days == 0
    assert priority == "B"


def test_race_proximity_after_last_valid():
    """Después de la última válida: retorna (None, None)."""
    days, priority = _race_proximity(date(2026, 10, 19))
    assert days is None
    assert priority is None


def test_copa_valle_2026_has_8_entries():
    """El calendario tiene exactamente 8 válidas como en CLAUDE.md."""
    assert len(COPA_VALLE_2026) == 8


def test_copa_valle_2026_dates_are_sorted():
    """Las fechas del calendario están en orden ascendente."""
    dates = [d for d, _ in COPA_VALLE_2026]
    assert dates == sorted(dates)


def test_copa_valle_2026_priorities():
    """Las prioridades del calendario coinciden con CLAUDE.md."""
    expected = ["A", "A", "C", "A", "A", "B", "A", "B"]
    actual = [p for _, p in COPA_VALLE_2026]
    assert actual == expected


# ---------------------------------------------------------------------------
# Tests de _season_phase
# ---------------------------------------------------------------------------


def test_season_phase_pre_temporada():
    phase = _season_phase(date(2025, 12, 15))
    assert "pre-temporada" in phase.lower()


def test_season_phase_tapering_before_a_race():
    # 5 días antes de Válida IV (17 mayo = prioridad A)
    phase = _season_phase(date(2026, 5, 12))
    assert "tapering" in phase.lower() or "pre-competencia" in phase.lower()


def test_season_phase_post_temporada():
    phase = _season_phase(date(2026, 11, 1))
    assert "post-temporada" in phase.lower()


# ---------------------------------------------------------------------------
# Tests de build_aggregate_context (con DB fake)
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _FakeDB:
    """Fake AsyncSession que devuelve birth_dates configurables."""

    def __init__(self, birth_dates=None):
        self._birth_dates = birth_dates or []

    async def execute(self, stmt, *args, **kwargs):
        return _FakeResult(self._birth_dates)


@pytest.mark.asyncio
async def test_build_context_empty_athletes():
    """Sin atletas seleccionados: age_mix vacío, total_athletes=0."""
    db = _FakeDB(birth_dates=[])
    ctx = await build_aggregate_context(db, club_id=1, selected_athlete_ids=[])

    assert ctx["total_athletes"] == 0
    assert ctx["age_mix"] == {}
    assert "today" in ctx
    assert "season_phase" in ctx
    assert "days_to_next_race" in ctx
    assert "next_race_priority" in ctx


@pytest.mark.asyncio
async def test_build_context_correct_age_mix():
    """age_mix refleja correctamente los grupos de edad."""
    # 2 atletas de 11 años, 3 atletas de 14 años
    today = date(2026, 6, 8)
    birth_dates = [
        date(2015, 1, 1),  # ~11 años → 10-12
        date(2014, 6, 1),  # ~12 años → 10-12
        date(2012, 3, 1),  # ~14 años → 13-15
        date(2011, 9, 1),  # ~14 años → 13-15
        date(2011, 1, 1),  # ~15 años → 13-15
    ]
    db = _FakeDB(birth_dates=birth_dates)
    ctx = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=[1, 2, 3, 4, 5], today=today
    )

    assert ctx["total_athletes"] == 5
    assert ctx["age_mix"].get("10-12", 0) == 2
    assert ctx["age_mix"].get("13-15", 0) == 3
    assert ctx["age_mix"].get("16+", 0) == 0


@pytest.mark.asyncio
async def test_build_context_days_to_next_race():
    """days_to_next_race se calcula correctamente."""
    # Antes de Válida V (1 ago 2026)
    today = date(2026, 7, 20)
    db = _FakeDB()
    ctx = await build_aggregate_context(db, club_id=1, selected_athlete_ids=[], today=today)

    expected = (date(2026, 8, 1) - today).days
    assert ctx["days_to_next_race"] == expected
    assert ctx["next_race_priority"] == "B"


@pytest.mark.asyncio
async def test_build_context_no_names_in_dict():
    """El dict retornado NO contiene nombres ni IDs de atletas."""
    birth_dates = [date(2012, 1, 1), date(2013, 6, 15)]
    db = _FakeDB(birth_dates=birth_dates)
    ctx = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=[10, 11], today=date(2026, 6, 8)
    )

    # Verificar que no hay IDs ni nombres en el dict
    all_values = list(ctx.values())

    # No debe haber listas de IDs numéricos
    for v in all_values:
        if isinstance(v, list):
            for item in v:
                assert not isinstance(item, int), (
                    f"Se encontró un int en la lista del contexto: {item}. "
                    "Los IDs de atletas no deben aparecer en el contexto."
                )

    # Las claves del dict deben ser solo las permitidas
    allowed_keys = {"today", "age_mix", "total_athletes", "season_phase",
                    "days_to_next_race", "next_race_priority"}
    assert set(ctx.keys()) == allowed_keys, (
        f"Claves inesperadas en el contexto: {set(ctx.keys()) - allowed_keys}"
    )


@pytest.mark.asyncio
async def test_build_context_no_athlete_ids_passed_to_result():
    """Los IDs de atletas no se incluyen en ninguna clave del dict retornado."""
    # Usar IDs grandes que no sean substrings de years/days en el contexto.
    # 99001+ no aparecerá en "2026-06-08" ni en counts de 1-5 atletas.
    athlete_ids = [99001, 99002, 99003]
    birth_dates = [date(2012, 1, 1), date(2013, 6, 15), date(2014, 3, 20)]
    db = _FakeDB(birth_dates=birth_dates)
    ctx = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=athlete_ids, today=date(2026, 6, 8)
    )

    ctx_str = str(ctx)
    for aid in athlete_ids:
        # Los IDs específicos no deben aparecer como strings en el contexto
        assert str(aid) not in ctx_str, (
            f"ID de atleta {aid} encontrado en el contexto — violación de privacidad."
        )


@pytest.mark.asyncio
async def test_build_context_mixed_age_groups():
    """Grupo mixto (10-12 y 13-15) refleja correctamente."""
    today = date(2026, 6, 8)
    birth_dates = [
        date(2015, 1, 1),  # ~11 años → 10-12
        date(2012, 3, 1),  # ~14 años → 13-15
        date(2008, 5, 1),  # ~18 años → 16+
    ]
    db = _FakeDB(birth_dates=birth_dates)
    ctx = await build_aggregate_context(
        db, club_id=1, selected_athlete_ids=[1, 2, 3], today=today
    )

    assert ctx["total_athletes"] == 3
    assert ctx["age_mix"]["10-12"] == 1
    assert ctx["age_mix"]["13-15"] == 1
    assert ctx["age_mix"]["16+"] == 1
