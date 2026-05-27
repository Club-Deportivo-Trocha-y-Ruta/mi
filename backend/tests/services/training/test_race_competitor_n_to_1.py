"""Tests de regresión: race_competitors permite N filas con mismo athlete_id.

Bug original:
    Antes el código usaba `.scalar_one_or_none()` sobre `select(RaceCompetitor).where(...athlete_id == X)`.
    Como `athlete_id` no tiene UNIQUE constraint en `race_competitors` (la única
    UNIQUE es sobre `normalized_name`), un mismo atleta podía estar referenciado
    desde múltiples competitors (ej: corrió V-I bajo nombre "Juan A. Pérez" y
    V-II bajo "Juan Andrés Pérez", y el coach vinculó ambos competitors al
    mismo `Athlete`). Resultado: `MultipleResultsFound`.

Fix:
    `competitors = comp_result.scalars().all()` + agregación de resultados de
    todos los competitor IDs.

Cobertura:
    - Caso A: `_build_race_block` con N=2 competitors (resultados agregados).
    - Caso B: `_evaluate_race_badges` con N=2 competitors (mejor posición cross-competitor).
    - Caso C: 0 competitors smoke (estructura vacía sin raise).
    - Caso D: 1 competitor smoke (no regresión del happy path 1:1).

Privacidad:
    Fixtures con nombres genéricos ficticios ("Test Athlete", "Variant A/B").
    Nunca se usan datos reales de menores del club.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.models.athlete_badge import BadgeSource, BadgeType
from app.services.training.badge_evaluator import (
    _evaluate_race_badges,
    evaluate_and_persist_badges,
)
from app.services.training.newsletter_builder import _build_race_block


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def make_session() -> Any:
    """Fake DB session mínima — execute es AsyncMock por defecto."""
    sess = MagicMock()
    sess.execute = AsyncMock()
    sess.flush = AsyncMock()
    sess.add = MagicMock()
    return sess


def make_scalars_result(items: list) -> Any:
    """Empaqueta una lista como Result de SQLAlchemy con .scalars().all()."""
    result = MagicMock()
    result.scalars.return_value = result
    result.all.return_value = items
    result.scalar_one_or_none.return_value = items[0] if items else None
    return result


def make_athlete(id_: int = 100, club_id: int = 10) -> Any:
    """Fixture genérica — nombres ficticios, NUNCA un menor real del club."""
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        first_name="Test",
        last_name="Athlete",
        birth_date=date(2012, 1, 1),
    )


def make_competitor(id_: int, athlete_id: int, normalized_name: str) -> Any:
    """RaceCompetitor genérico — `normalized_name` varía por fila (UNIQUE)."""
    return SimpleNamespace(
        id=id_,
        athlete_id=athlete_id,
        normalized_name=normalized_name,
        display_name=normalized_name.title(),
        club_text="Club Ficticio",
    )


def make_race_event(id_: int, event_date_: date) -> Any:
    return SimpleNamespace(
        id=id_,
        event_date=event_date_,
        sequence_number=id_,
        name=f"Valida {id_} Ficticia",
    )


def make_race_result(
    id_: int,
    competitor_id: int,
    event_id: int,
    position: int | None,
    race_time_ms: int | None,
) -> Any:
    from app.models.race_result import ResultStatus

    return SimpleNamespace(
        id=id_,
        competitor_id=competitor_id,
        event_id=event_id,
        athlete_id=None,
        position=position,
        race_time_ms=race_time_ms,
        status=ResultStatus.FINISHED,
        category_id=1,
        points_awarded=10,
    )


def make_progression_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame con shape compatible con `athlete_progression` output.

    Las columnas devueltas por `athlete_progression`:
        valida_num, event_date, category_code, position, race_time_ms,
        points_awarded, gap_to_winner_ms, gap_to_winner_pct.

    Adicionalmente, los tests verifican que el código maneja correctamente
    la deduplicación cuando varios competitors devuelven el mismo evento.
    """
    columns = [
        "valida_num",
        "event_date",
        "category_code",
        "position",
        "race_time_ms",
        "points_awarded",
        "gap_to_winner_ms",
        "gap_to_winner_pct",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


# ===========================================================================
# CASO A — _build_race_block con N=2 competitors
# ===========================================================================


@pytest.mark.asyncio
async def test_build_race_block_n2_competitors_no_raises_and_aggregates():
    """N=2 competitors vinculados al mismo athlete_id: no raise + has_races=True.

    Aserciones del contrato post-fix:
        1. NO se lanza MultipleResultsFound (el código usa .scalars().all()).
        2. has_races == True cuando hay resultados en el mes objetivo.
        3. competitor_id == competitors[0].id (primer competitor por orden de inserción).
        4. results contiene resultados agregados de ambos competitors.
    """
    db = make_session()
    athlete_id = 100

    comp_a = make_competitor(id_=201, athlete_id=athlete_id, normalized_name="variant a")
    comp_b = make_competitor(id_=202, athlete_id=athlete_id, normalized_name="variant b")

    # Athlete progression devuelve un DataFrame distinto por competitor.
    # comp_a corrió Válida 4 (mayo 2026).
    # comp_b corrió Válida 5 (mayo 2026, distinto evento del mes).
    df_a = make_progression_df([
        {
            "valida_num": 4,
            "event_date": "2026-05-10",
            "category_code": "U13M",
            "position": 5,
            "race_time_ms": 1_800_000,
            "points_awarded": 20,
            "gap_to_winner_ms": 60_000,
            "gap_to_winner_pct": 3.4,
        }
    ])
    df_b = make_progression_df([
        {
            "valida_num": 5,
            "event_date": "2026-05-20",
            "category_code": "U13M",
            "position": 7,
            "race_time_ms": 1_900_000,
            "points_awarded": 14,
            "gap_to_winner_ms": 90_000,
            "gap_to_winner_pct": 5.0,
        }
    ])

    # DB.execute solo se llama una vez: select(RaceCompetitor)
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([comp_a, comp_b])
        return make_scalars_result([])

    db.execute = mock_execute

    # Mock athlete_progression devolviendo un DataFrame distinto por competitor.
    progression_calls: list[int] = []

    async def fake_progression(_db, competitor_id):
        progression_calls.append(competitor_id)
        if competitor_id == 201:
            return df_a
        if competitor_id == 202:
            return df_b
        return make_progression_df([])

    with patch(
        "app.services.race.analytics.athlete_progression",
        side_effect=fake_progression,
    ):
        block = await _build_race_block(db, athlete_id=athlete_id, year=2026, month=5)

    # 1. No raise → si llegamos aquí ya pasamos la mitad del test.
    # 2. has_races
    assert block["has_races"] is True, (
        "has_races debe ser True cuando ambos competitors aportan resultados en el mes"
    )
    # 3. competitor_id == primer competitor (orden de inserción)
    assert block["competitor_id"] == 201, (
        "competitor_id debe ser el id del primer competitor vinculado (orden de carga)"
    )
    # 4. Ambos competitors fueron consultados
    assert sorted(progression_calls) == [201, 202], (
        "Se debió llamar a athlete_progression con cada competitor_id vinculado"
    )
    # 5. results agregados de ambos
    assert len(block["results"]) == 2, (
        "results debe contener los 2 resultados (uno por cada competitor) del mes"
    )
    valida_nums = sorted(r["valida_num"] for r in block["results"])
    assert valida_nums == [4, 5]


@pytest.mark.asyncio
async def test_build_race_block_n2_competitors_dedup_same_event():
    """Si los 2 competitors devuelven resultados del MISMO evento, no se duplican.

    Esto cubre el escenario raro pero posible: el atleta corrió un evento
    bajo dos identificadores y por alguna razón ambos quedaron en el pipeline.
    El builder debe deduplicar manteniendo solo una fila por evento.
    """
    db = make_session()
    athlete_id = 100

    comp_a = make_competitor(id_=201, athlete_id=athlete_id, normalized_name="variant a")
    comp_b = make_competitor(id_=202, athlete_id=athlete_id, normalized_name="variant b")

    # Ambos competitors retornan la MISMA válida_num 4 con misma event_date.
    # El código debe deduplicar (queda con la primera).
    shared_row = {
        "valida_num": 4,
        "event_date": "2026-05-10",
        "category_code": "U13M",
        "position": 5,
        "race_time_ms": 1_800_000,
        "points_awarded": 20,
        "gap_to_winner_ms": 60_000,
        "gap_to_winner_pct": 3.4,
    }
    df_a = make_progression_df([shared_row])
    df_b = make_progression_df([{**shared_row, "position": 6, "race_time_ms": 1_810_000}])

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([comp_a, comp_b])
        return make_scalars_result([])

    db.execute = mock_execute

    async def fake_progression(_db, competitor_id):
        return df_a if competitor_id == 201 else df_b

    with patch(
        "app.services.race.analytics.athlete_progression",
        side_effect=fake_progression,
    ):
        block = await _build_race_block(db, athlete_id=athlete_id, year=2026, month=5)

    # El contrato pide deduplicación: una sola fila por evento.
    # (Nota: el bug actual del fix usa drop_duplicates(subset=["event_id"]) pero
    # athlete_progression NO devuelve event_id en sus columnas. Si los tests
    # fallan, es señal del bug del fix — usar "valida_num" en su lugar.)
    assert block["has_races"] is True
    assert len(block["results"]) == 1, (
        "results debe deduplicar por evento (mismo valida_num) cuando varios competitors lo devuelven"
    )


# ===========================================================================
# CASO B — _evaluate_race_badges con N=2 competitors
# ===========================================================================


@pytest.mark.asyncio
async def test_evaluate_race_badges_n2_competitors_no_raises_and_picks_best():
    """N=2 competitors: top10 emitida con la MEJOR posición cross-competitor.

    Setup:
        comp_a → P8 en evento E1 (mayo 2026).
        comp_b → P15 en evento E1 (mayo 2026).
    Esperado:
        Badge top10 con position=8 (mejor de los dos), event_id de comp_a.
        NO MultipleResultsFound.
    """
    db = make_session()
    athlete_id = 100

    comp_a = make_competitor(id_=201, athlete_id=athlete_id, normalized_name="variant a")
    comp_b = make_competitor(id_=202, athlete_id=athlete_id, normalized_name="variant b")

    event_e1 = make_race_event(id_=900, event_date_=date(2026, 5, 10))

    result_a = make_race_result(
        id_=5001, competitor_id=201, event_id=900, position=8, race_time_ms=1_800_000
    )
    result_b = make_race_result(
        id_=5002, competitor_id=202, event_id=900, position=15, race_time_ms=2_100_000
    )

    # Secuencia de queries esperada en _evaluate_race_badges:
    # 1. select(RaceCompetitor) → [comp_a, comp_b]
    # 2. select(RaceEvent) → [event_e1]
    # 3. select(RaceResult) [eventos del mes] → [result_a, result_b]
    # (top10 emitido sin queries adicionales — no hay podio P1/P2/P3, no se entra a MTP)
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([comp_a, comp_b])
        elif call_count == 2:
            return make_scalars_result([event_e1])
        elif call_count == 3:
            return make_scalars_result([result_a, result_b])
        return make_scalars_result([])

    db.execute = mock_execute

    badge_datas = await _evaluate_race_badges(db, athlete_id, 2026, 5)

    badge_types = [b["badge_type"] for b in badge_datas]
    assert BadgeType.top10 in badge_types, (
        "Debe emitirse badge top10 (P8 ≤ 10)"
    )

    top10_badge = next(b for b in badge_datas if b["badge_type"] == BadgeType.top10)
    # Mejor cross-competitor: P8 (de comp_a), no P15.
    assert top10_badge["metadata_json"]["position"] == 8, (
        "top10 debe usar la MEJOR posición entre todos los competitors vinculados"
    )


@pytest.mark.asyncio
async def test_evaluate_race_badges_n2_podium_no_previous():
    """N=2 competitors con P3 en el mes y sin podio previo: first_podium emitido."""
    db = make_session()
    athlete_id = 100

    comp_a = make_competitor(id_=201, athlete_id=athlete_id, normalized_name="variant a")
    comp_b = make_competitor(id_=202, athlete_id=athlete_id, normalized_name="variant b")

    event_e1 = make_race_event(id_=900, event_date_=date(2026, 5, 10))

    # comp_a P3, comp_b P8 → first_podium + top10
    result_a = make_race_result(
        id_=5001, competitor_id=201, event_id=900, position=3, race_time_ms=1_750_000
    )
    result_b = make_race_result(
        id_=5002, competitor_id=202, event_id=900, position=8, race_time_ms=1_900_000
    )

    # Secuencia:
    # 1. RaceCompetitor → [comp_a, comp_b]
    # 2. RaceEvent → [event_e1]
    # 3. RaceResult (mes) → [result_a, result_b]
    # 4. RaceResult prev podium (join RaceEvent < month_start) → [] (no previo)
    # 5. RaceResult prev times (MTP) → [] (sin previo)
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([comp_a, comp_b])
        elif call_count == 2:
            return make_scalars_result([event_e1])
        elif call_count == 3:
            return make_scalars_result([result_a, result_b])
        elif call_count == 4:
            return make_scalars_result([])  # sin podio previo
        elif call_count == 5:
            return make_scalars_result([])  # sin tiempos previos
        return make_scalars_result([])

    db.execute = mock_execute

    badge_datas = await _evaluate_race_badges(db, athlete_id, 2026, 5)
    badge_types = [b["badge_type"] for b in badge_datas]

    assert BadgeType.first_podium in badge_types, (
        "first_podium debe emitirse con P3 cuando no hay podios previos"
    )
    assert BadgeType.top10 in badge_types


# ===========================================================================
# CASO C — 0 competitors smoke
# ===========================================================================


@pytest.mark.asyncio
async def test_build_race_block_zero_competitors_returns_empty():
    """Atleta sin RaceCompetitor: estructura vacía sin raise."""
    db = make_session()

    async def mock_execute(stmt):
        return make_scalars_result([])  # no competitors

    db.execute = mock_execute

    block = await _build_race_block(db, athlete_id=999, year=2026, month=5)

    assert block == {
        "has_races": False,
        "competitor_id": None,
        "results": [],
        "projection": None,
    }


@pytest.mark.asyncio
async def test_evaluate_race_badges_zero_competitors_returns_empty():
    """Atleta sin RaceCompetitor: lista vacía sin raise."""
    db = make_session()

    async def mock_execute(stmt):
        return make_scalars_result([])

    db.execute = mock_execute

    badge_datas = await _evaluate_race_badges(db, 999, 2026, 5)
    assert badge_datas == []


# ===========================================================================
# CASO D — 1 competitor smoke (no regresión)
# ===========================================================================


@pytest.mark.asyncio
async def test_build_race_block_single_competitor_still_works():
    """Happy path clásico 1:1 — debe seguir funcionando tras el fix."""
    db = make_session()
    athlete_id = 100

    comp_only = make_competitor(id_=201, athlete_id=athlete_id, normalized_name="solo competitor")

    df = make_progression_df([
        {
            "valida_num": 4,
            "event_date": "2026-05-10",
            "category_code": "U13M",
            "position": 5,
            "race_time_ms": 1_800_000,
            "points_awarded": 20,
            "gap_to_winner_ms": 60_000,
            "gap_to_winner_pct": 3.4,
        }
    ])

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([comp_only])
        return make_scalars_result([])

    db.execute = mock_execute

    async def fake_progression(_db, competitor_id):
        return df if competitor_id == 201 else make_progression_df([])

    with patch(
        "app.services.race.analytics.athlete_progression",
        side_effect=fake_progression,
    ):
        block = await _build_race_block(db, athlete_id=athlete_id, year=2026, month=5)

    assert block["has_races"] is True
    assert block["competitor_id"] == 201
    assert len(block["results"]) == 1
    assert block["results"][0]["valida_num"] == 4
    assert block["results"][0]["position"] == 5


@pytest.mark.asyncio
async def test_evaluate_race_badges_single_competitor_still_works():
    """Happy path 1:1 para evaluador de badges race."""
    db = make_session()
    athlete_id = 100

    comp_only = make_competitor(id_=201, athlete_id=athlete_id, normalized_name="solo competitor")
    event_e1 = make_race_event(id_=900, event_date_=date(2026, 5, 10))
    result = make_race_result(
        id_=5001, competitor_id=201, event_id=900, position=7, race_time_ms=1_850_000
    )

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([comp_only])
        elif call_count == 2:
            return make_scalars_result([event_e1])
        elif call_count == 3:
            return make_scalars_result([result])
        return make_scalars_result([])

    db.execute = mock_execute

    badge_datas = await _evaluate_race_badges(db, athlete_id, 2026, 5)
    badge_types = [b["badge_type"] for b in badge_datas]

    assert BadgeType.top10 in badge_types
    top10 = next(b for b in badge_datas if b["badge_type"] == BadgeType.top10)
    assert top10["metadata_json"]["position"] == 7
