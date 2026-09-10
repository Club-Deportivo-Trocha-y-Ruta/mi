"""Tests para badge_evaluator.py — insignias idempotentes por periodo."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.athlete_badge import BadgeSource, BadgeType
from app.services.training.badge_evaluator import (
    _compute_streak,
    _evaluate_race_badges,
    _is_credible_position,
    _min_credible_field_size,
    _upsert_badge,
    evaluate_and_persist_badges,
)


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def make_session() -> Any:
    """Fake DB session mínima."""
    sess = MagicMock()
    sess.execute = AsyncMock()
    sess.flush = AsyncMock()
    sess.add = MagicMock()
    return sess


def make_scalars_result(items: list) -> Any:
    result = MagicMock()
    result.scalars.return_value = result
    result.all.return_value = items
    result.scalar_one_or_none.return_value = items[0] if items else None
    return result


def make_athlete(id_=1, club_id=10, deleted_at=None) -> Any:
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        first_name="Atleta",
        last_name="Test",
        birth_date=date(2012, 3, 15),
        deleted_at=deleted_at,
    )


def make_session_obj(id_, date_=None, club_id=10) -> Any:
    from app.models.training_session import SessionStatus
    return SimpleNamespace(
        id=id_,
        club_id=club_id,
        scheduled_date=date_ or date(2026, 4, 10 + id_),
        status=SessionStatus.EXECUTED,
        duration_min=90,
        technical_focus="Curvas",
    )


def make_attendance(session_id: int, status_) -> Any:
    return SimpleNamespace(
        session_id=session_id,
        athlete_id=1,
        status=status_,
        rpe_omni=6,
        rubric_effort=4,
        rubric_attitude=4,
        rubric_technique=3,
    )


def is_delete_stmt(stmt: Any) -> bool:
    """Detecta DELETE inicial del re-evaluador (clean slate del periodo)."""
    from sqlalchemy.sql.dml import Delete

    return isinstance(stmt, Delete)


def make_race_competitor(id_=1, athlete_id=1) -> Any:
    return SimpleNamespace(id=id_, athlete_id=athlete_id)


def make_race_event(id_=100, event_date=None) -> Any:
    return SimpleNamespace(id=id_, event_date=event_date or date(2026, 8, 15))


def make_race_result(
    event_id=100,
    category_id=5,
    competitor_id=1,
    position=3,
    race_time_ms=None,
) -> Any:
    from app.models.race_result import ResultStatus

    return SimpleNamespace(
        event_id=event_id,
        category_id=category_id,
        competitor_id=competitor_id,
        position=position,
        race_time_ms=race_time_ms,
        status=ResultStatus.FINISHED,
    )


def make_rows_result(rows: list[tuple]) -> Any:
    """Fake resultado para queries de conteo (SELECT ... GROUP BY) — `.all()` plano."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def make_scalar_none_result() -> Any:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


# ---------------------------------------------------------------------------
# Test: compute_streak
# ---------------------------------------------------------------------------


def test_compute_streak_all_present():
    """Racha = total sesiones si todas presentes."""
    from app.models.training_session import AttendanceStatus

    sessions = [make_session_obj(i) for i in range(1, 5)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]
    streak = _compute_streak(sessions, attendances)
    assert streak == 4


def test_compute_streak_breaks_on_absent():
    """Racha se rompe cuando hay una ausencia."""
    from app.models.training_session import AttendanceStatus

    sessions = [make_session_obj(i) for i in range(1, 6)]
    # última sesión (id=5) es la más reciente → streak desde ahí
    attendances = [
        make_attendance(1, AttendanceStatus.PRESENTE),
        make_attendance(2, AttendanceStatus.AUSENTE),
        make_attendance(3, AttendanceStatus.PRESENTE),
        make_attendance(4, AttendanceStatus.PRESENTE),
        make_attendance(5, AttendanceStatus.PRESENTE),
    ]
    # sessions están ordenadas desc por fecha; la primera en la lista es la más reciente
    # make_session_obj genera fechas 2026-04-11 ... 2026-04-15 para ids 1..5
    # sorted desc: id=5 (15), id=4 (14), id=3 (13), id=2 (12), id=1 (11)
    # Desde el más reciente: 5=PRESENTE, 4=PRESENTE, 3=PRESENTE, 2=AUSENTE → streak=3
    streak = _compute_streak(sessions, attendances)
    assert streak == 3


def test_compute_streak_zero_if_last_absent():
    """Racha = 0 si la última sesión fue ausencia."""
    from app.models.training_session import AttendanceStatus

    sessions = [make_session_obj(1), make_session_obj(2)]
    # id=2 es el más reciente (fecha 12), id=1 es el anterior (fecha 11)
    attendances = [
        make_attendance(1, AttendanceStatus.PRESENTE),
        make_attendance(2, AttendanceStatus.AUSENTE),
    ]
    streak = _compute_streak(sessions, attendances)
    assert streak == 0


# ---------------------------------------------------------------------------
# Test: evaluate_and_persist_badges — asistencia
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_badge_attendance_100():
    """attendance_100 se genera con 100% de asistencia."""
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    sessions = [make_session_obj(i) for i in range(1, 4)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            # select Athlete
            return make_scalars_result([athlete])
        elif call_count == 2:
            # select TrainingSession
            return make_scalars_result(sessions)
        elif call_count == 3:
            # select SessionAttendance
            return make_scalars_result(attendances)
        elif call_count == 4:
            # select RaceCompetitor
            return make_scalars_result([])
        else:
            # select existing badge (no existe)
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)

    # Debe haber creado al menos el badge de attendance_100
    badge_types = [b.badge_type for b in badges]
    assert BadgeType.attendance_100 in badge_types


@pytest.mark.asyncio
async def test_badge_attendance_90():
    """attendance_90 se genera con >=90% de asistencia."""
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    # 9 sesiones, 9 presentes = 100% → attendance_100
    # 10 sesiones, 9 presentes = 90% → attendance_90
    sessions = [make_session_obj(i) for i in range(1, 11)]
    # i va 0..9; i < 9 → índices 0..8 PRESENTE, índice 9 AUSENTE → 9/10 = 90%
    attendances = [
        make_attendance(s.id, AttendanceStatus.PRESENTE if i < 9 else AttendanceStatus.AUSENTE)
        for i, s in enumerate(sessions)
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            return make_scalars_result(sessions)
        elif call_count == 3:
            return make_scalars_result(attendances)
        elif call_count == 4:
            # RaceCompetitor
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    badge_types = [b.badge_type for b in badges]
    assert BadgeType.attendance_90 in badge_types
    assert BadgeType.attendance_100 not in badge_types


@pytest.mark.asyncio
async def test_badge_no_badge_below_75():
    """No se genera ningún badge si asistencia < 75%."""
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    sessions = [make_session_obj(i) for i in range(1, 5)]  # 4 sesiones
    # 2 presentes / 4 = 50%
    attendances = [
        make_attendance(1, AttendanceStatus.PRESENTE),
        make_attendance(2, AttendanceStatus.AUSENTE),
        make_attendance(3, AttendanceStatus.AUSENTE),
        make_attendance(4, AttendanceStatus.PRESENTE),
    ]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            return make_scalars_result(sessions)
        elif call_count == 3:
            return make_scalars_result(attendances)
        elif call_count == 4:
            # RaceCompetitor
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    assert badges == []


@pytest.mark.asyncio
async def test_badge_idempotent():
    """Re-evaluar el periodo refleja métricas actuales sin duplicar.

    El evaluador borra los badges del periodo y reinserta. Si las métricas no
    cambiaron, el set final es el mismo; si cambiaron (e.g. asistencia subió
    de 94% a 100%), reemplaza attendance_90 por attendance_100.
    """
    from app.models.athlete_badge import AthleteBadge
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    sessions = [make_session_obj(i) for i in range(1, 4)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]

    # Simular que el badge ya existe
    existing_badge = SimpleNamespace(
        id=99,
        athlete_id=athlete.id,
        badge_type=BadgeType.attendance_100,
        badge_source=BadgeSource.attendance,
        period_year=2026,
        period_month=4,
        earned_at=datetime.now(timezone.utc),
        metadata_json={"attendance_pct": 100.0},
    )

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            return make_scalars_result(sessions)
        elif call_count == 3:
            return make_scalars_result(attendances)
        elif call_count == 4:
            # _upsert_badge check: badge attendance_100 → ya existe
            return make_scalars_result([existing_badge])
        elif call_count == 5:
            # RaceCompetitor — no hay
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    # Badge ya existía → no se crea nuevo
    assert badges == []
    # db.add nunca fue llamado
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Test: atleta sin sesiones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_sessions_no_badges():
    """Sin sesiones en el mes, no se generan badges."""
    db = make_session()
    athlete = make_athlete()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            # Sesiones: vacío
            return make_scalars_result([])
        elif call_count == 3:
            # RaceCompetitor
            return make_scalars_result([])
        else:
            return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    assert badges == []


@pytest.mark.asyncio
async def test_athlete_not_found_returns_empty():
    """Si el atleta no existe, retorna lista vacía."""
    db = make_session()

    async def mock_execute(stmt):
        return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, 999, 2026, 4)
    assert badges == []


# ---------------------------------------------------------------------------
# Test: credibilidad de las insignias de posición — DOS criterios distintos
# a propósito (ver docstrings en badge_evaluator.py):
#   - first_podium (posición ≤3): `_is_credible_position` — percentil/mitad
#     delantera de la parrilla real. La etiqueta "Primer podio" no promete
#     un tamaño, así que un 2º/3º de 6 sigue siendo un podio real.
#   - top10 (posición ≤10): `_min_credible_field_size` — la parrilla misma
#     debe ser absolutamente grande (≥15), porque la etiqueta "Top 10" SÍ
#     promete un tamaño. Una posición relativamente buena (p. ej. 2º de 6)
#     NO alcanza — ese es justo el defecto reportado por el entrenador
#     ("Top 10" impreso sobre una carrera de 6 corredores).
# ---------------------------------------------------------------------------


def test_is_credible_position_calibrated_with_real_field_sizes():
    """`_is_credible_position` (solo first_podium) validado contra el patrón
    real de parrillas del club (5-13 corredoras por categoría/válida en una
    temporada 2026 completa, ver mensaje del entrenador): posiciones en la
    mitad trasera de una parrilla chica NO son creíbles; posiciones en la
    mitad delantera SÍ lo son aunque la parrilla sea chica.
    """
    # Mitad trasera (posición > mitad de la parrilla) → no creíble.
    assert _is_credible_position(4, 7) is False
    assert _is_credible_position(4, 6) is False
    assert _is_credible_position(4, 5) is False
    assert _is_credible_position(11, 13) is False
    # Caso reportado por el entrenador: P5 de una parrilla de 7 recibió
    # "Top 10" indebidamente — 2 rivales detrás no sostiene ni el podio.
    assert _is_credible_position(5, 7) is False

    # Mitad delantera → creíble, incluso en parrilla chica (p. ej. 2º de 6
    # en un campeonato es un resultado real, no un artefacto de parrilla).
    assert _is_credible_position(3, 6) is True
    assert _is_credible_position(2, 6) is True

    # Piso absoluto (`_MIN_ABSOLUTE_FIELD_SIZE`=4): parrillas degeneradas de
    # 2-3 corredores nunca son creíbles, aunque la posición sea "mitad
    # delantera" en términos relativos. Ejemplo explícito del entrenador:
    # "podio de 3 en parrilla de 3 no dice nada".
    assert _is_credible_position(1, 3) is False
    assert _is_credible_position(1, 2) is False
    assert _is_credible_position(3, 3) is False

    # Boundary exacto en el piso absoluto (4 corredores, posición 2 = mitad).
    assert _is_credible_position(2, 4) is True
    assert _is_credible_position(3, 4) is False


def test_min_credible_field_size_top10_threshold():
    """`_min_credible_field_size` (solo top10): parrilla ≥15 para N=10 — muy
    por encima de cualquier parrilla real del club (5-13, incluido el
    Campeonato Nacional)."""
    assert _min_credible_field_size(10) == 15
    for real_field_size in (5, 6, 7, 13):
        assert real_field_size < _min_credible_field_size(10)


@pytest.mark.asyncio
async def test_badge_top10_boundary_field_size():
    """top10 exige parrilla absoluta ≥15 (posición 8, dentro de rango) —
    parrilla 15 otorga, 14 no."""
    competitor = make_race_competitor()
    event = make_race_event()
    result = make_race_result(event_id=100, category_id=5, position=8)

    async def run_with_field_size(field_size: int) -> list[dict]:
        db = make_session()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_scalars_result([competitor])
            elif call_count == 2:
                return make_scalars_result([event])
            elif call_count == 3:
                return make_scalars_result([result])
            elif call_count == 4:
                return make_rows_result([(100, 5, field_size)])
            raise AssertionError(f"Llamada inesperada #{call_count}")

        db.execute = mock_execute
        return await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)

    granted = await run_with_field_size(15)
    assert {b["badge_type"] for b in granted} == {BadgeType.top10}

    denied = await run_with_field_size(14)
    assert denied == []


@pytest.mark.asyncio
async def test_badge_top10_not_granted_for_great_relative_position_in_small_field():
    """El defecto original reportado por el entrenador: un P2 de 6 (resultado
    real, percentil excelente) NO debe imprimir "Top 10" — la etiqueta
    promete un tamaño de parrilla que 6 corredores no sostiene. Sí debe
    otorgar first_podium (criterio distinto)."""
    competitor = make_race_competitor()
    event = make_race_event()
    result = make_race_result(event_id=100, category_id=5, position=2)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            return make_rows_result([(100, 5, 6)])
        elif call_count == 5:
            # Historial de podio previo: ninguno.
            return make_scalars_result([])
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    badge_types = {b["badge_type"] for b in badges}
    assert BadgeType.top10 not in badge_types
    assert BadgeType.first_podium in badge_types


@pytest.mark.asyncio
async def test_badge_podium_boundary_field_size():
    """first_podium exige parrilla creíble por percentil (posición 3: parrilla
    ≥6 otorga, 5 no) — independiente del umbral absoluto de top10."""
    competitor = make_race_competitor()
    event = make_race_event()
    result = make_race_result(event_id=100, category_id=5, position=3)

    async def run_with_field_size(field_size: int, expect_history_query: bool) -> list[dict]:
        db = make_session()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_scalars_result([competitor])
            elif call_count == 2:
                return make_scalars_result([event])
            elif call_count == 3:
                return make_scalars_result([result])
            elif call_count == 4:
                return make_rows_result([(100, 5, field_size)])
            elif call_count == 5 and expect_history_query:
                return make_scalars_result([])  # sin podio previo
            raise AssertionError(f"Llamada inesperada #{call_count}")

        db.execute = mock_execute
        return await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)

    # Parrilla 6 (< 15): first_podium creíble, top10 NO (umbral absoluto).
    granted = await run_with_field_size(6, expect_history_query=True)
    assert {b["badge_type"] for b in granted} == {BadgeType.first_podium}
    podium_meta = next(b for b in granted if b["badge_type"] == BadgeType.first_podium)["metadata_json"]
    assert podium_meta["field_size"] == 6

    denied = await run_with_field_size(5, expect_history_query=False)
    assert denied == []


@pytest.mark.asyncio
async def test_badge_podium_position_4_never_credible_regardless_of_field():
    """Posición 4 nunca otorga first_podium (podio real es 1-3), sin importar
    cuán grande sea la parrilla — el corte por posición es anterior al
    filtro de credibilidad. Con parrilla enorme (50 ≥15), sí otorga top10
    (criterio absoluto distinto, y posición 4 ≤10)."""
    competitor = make_race_competitor()
    event = make_race_event()
    result = make_race_result(event_id=100, category_id=5, position=4)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            return make_rows_result([(100, 5, 50)])
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    assert {b["badge_type"] for b in badges} == {BadgeType.top10}


@pytest.mark.asyncio
async def test_badge_podium_p2_of_6_granted_real_championship_case():
    """Caso real (Campeonato Departamental): posición 2 de una parrilla de 6
    otorga first_podium (y NO top10 — ver test de la etiqueta absurda)."""
    competitor = make_race_competitor()
    event = make_race_event()
    result = make_race_result(event_id=100, category_id=5, position=2)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            return make_rows_result([(100, 5, 6)])
        elif call_count == 5:
            return make_scalars_result([])  # sin podio previo
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    assert {b["badge_type"] for b in badges} == {BadgeType.first_podium}


@pytest.mark.asyncio
async def test_badge_podium_p3_of_3_not_credible_per_coach_example():
    """Ejemplo explícito del entrenador: "podio de 3 en parrilla de 3 no dice
    nada" — bajo el piso absoluto de `_MIN_ABSOLUTE_FIELD_SIZE`, no se
    otorga."""
    competitor = make_race_competitor()
    event = make_race_event()
    result = make_race_result(event_id=100, category_id=5, position=3)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            return make_rows_result([(100, 5, 3)])
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    assert badges == []


@pytest.mark.asyncio
async def test_badge_previous_podium_must_be_credible_to_block_new_one():
    """`had_previous_podium` recalibrado: un podio pasado que NO habría sido
    creíble (P3 de una parrilla de 3) no bloquea el primer podio real de
    verdad. Mes evaluado: P2/6 (creíble). Historial: P3/3 pasado (no
    creíble, evento distinto) — first_podium SÍ se otorga este mes, como si
    no hubiera habido podio previo."""
    competitor = make_race_competitor()
    event = make_race_event(id_=100)
    result = make_race_result(event_id=100, category_id=5, position=2)
    prev_candidate = make_race_result(event_id=50, category_id=9, position=3)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            # Parrilla del mes evaluado: 6, creíble para podio.
            return make_rows_result([(100, 5, 6)])
        elif call_count == 5:
            # Candidatos a podio previo: un P3 de una parrilla de 3 (evento 50).
            return make_scalars_result([prev_candidate])
        elif call_count == 6:
            # Parrilla histórica del evento 50: 3 — no creíble.
            return make_rows_result([(50, 9, 3)])
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    assert BadgeType.first_podium in {b["badge_type"] for b in badges}


@pytest.mark.asyncio
async def test_badge_previous_credible_podium_blocks_new_one():
    """Contraparte: si el podio previo SÍ era creíble, bloquea correctamente
    el nuevo first_podium (comportamiento "primer podio" preexistente,
    ahora recalibrado con credibilidad en vez de solo `position <= 3`)."""
    competitor = make_race_competitor()
    event = make_race_event(id_=100)
    result = make_race_result(event_id=100, category_id=5, position=2)
    prev_candidate = make_race_result(event_id=50, category_id=9, position=3)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            return make_rows_result([(100, 5, 6)])
        elif call_count == 5:
            return make_scalars_result([prev_candidate])
        elif call_count == 6:
            # Parrilla histórica del evento 50: 6 — creíble (3*2=6<=6).
            return make_rows_result([(50, 9, 6)])
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    assert BadgeType.first_podium not in {b["badge_type"] for b in badges}


@pytest.mark.asyncio
async def test_badge_position_withheld_reproduces_reported_incident():
    """Reproduce el incidente reportado por el entrenador: posición 5 de una
    parrilla real de 7 corredoras recibió la insignia "Top 10". Ni top10
    (parrilla 7 << 15) ni first_podium (posición 5 > 3) deben otorgarse."""
    competitor = make_race_competitor()
    event = make_race_event()
    result = make_race_result(event_id=100, category_id=5, position=5)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            # Parrilla real reportada para ese incidente: 7 corredoras.
            return make_rows_result([(100, 5, 7)])
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    assert badges == []


@pytest.mark.asyncio
async def test_badge_position_withheld_when_field_size_missing_entirely():
    """Si la query de conteo no devuelve fila para esa (evento, categoría)
    (parrilla desconocida en el sentido estricto), se trata como 0 → se
    retiene la insignia (posición 1 también falla el umbral absoluto de
    top10 de todas formas)."""
    competitor = make_race_competitor()
    event = make_race_event()
    result = make_race_result(event_id=100, category_id=5, position=1)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            # Ninguna fila para (100, 5): parrilla desconocida.
            return make_rows_result([])
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    assert badges == []


@pytest.mark.asyncio
async def test_badge_mtp_unaffected_by_field_size():
    """MTP (insignia no posicional) se otorga sin importar el tamaño de
    parrilla — ninguno de los dos umbrales de credibilidad aplica a MTP."""
    competitor = make_race_competitor()
    event = make_race_event()
    # Posición 15: fuera de rango de top10 y first_podium.
    result = make_race_result(event_id=100, category_id=5, position=15, race_time_ms=500_000)
    prev_result = make_race_result(event_id=50, category_id=5, position=12, race_time_ms=600_000)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            # Parrilla diminuta e irrelevante para MTP.
            return make_rows_result([(100, 5, 3)])
        elif call_count == 5:
            # Historial previo para comparar MTP
            return make_scalars_result([prev_result])
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badges = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    badge_types = {b["badge_type"] for b in badges}
    assert badge_types == {BadgeType.mtp}


# ---------------------------------------------------------------------------
# Test: earned_at refleja la fecha real del criterio, no la fecha de
# (re)evaluación del boletín.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_badge_earned_at_reflects_last_session_not_now():
    """earned_at de una insignia de asistencia es la fecha de la última
    sesión convocada del periodo, no el instante en que corre el evaluador."""
    from app.models.training_session import AttendanceStatus

    db = make_session()
    athlete = make_athlete()
    # make_session_obj(i) → date(2026, 4, 10+i): fechas 04-11, 04-12, 04-13.
    sessions = [make_session_obj(i) for i in range(1, 4)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        if is_delete_stmt(stmt):
            return MagicMock()
        call_count += 1
        if call_count == 1:
            return make_scalars_result([athlete])
        elif call_count == 2:
            return make_scalars_result(sessions)
        elif call_count == 3:
            return make_scalars_result(attendances)
        elif call_count == 4:
            return make_scalars_result([])  # RaceCompetitor
        return make_scalars_result([])

    db.execute = mock_execute

    badges = await evaluate_and_persist_badges(db, athlete.id, 2026, 4)
    badge = next(b for b in badges if b.badge_type == BadgeType.attendance_100)

    # Última sesión convocada = 2026-04-13 (id=3), no "hoy".
    assert badge.earned_at == datetime(2026, 4, 13, tzinfo=timezone.utc)
    # Cae dentro del periodo evaluado (abril 2026).
    assert badge.earned_at.year == 2026
    assert badge.earned_at.month == 4


@pytest.mark.asyncio
async def test_badge_earned_at_reflects_race_event_date():
    """earned_at de una insignia de carrera es la fecha de la válida que la
    disparó (`event_date`), no el instante en que corre el evaluador.

    Usa una parrilla absolutamente grande (20) para que también otorgue
    top10 y así verificar la fecha en ambos tipos de insignia de posición
    con una sola carrera.
    """
    competitor = make_race_competitor()
    race_date = date(2026, 8, 2)
    event = make_race_event(id_=100, event_date=race_date)
    result = make_race_result(event_id=100, category_id=5, position=2)

    db = make_session()
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_scalars_result([competitor])
        elif call_count == 2:
            return make_scalars_result([event])
        elif call_count == 3:
            return make_scalars_result([result])
        elif call_count == 4:
            return make_rows_result([(100, 5, 20)])
        elif call_count == 5:
            return make_scalars_result([])  # sin podio previo
        raise AssertionError(f"Llamada inesperada #{call_count}")

    db.execute = mock_execute

    badge_datas = await _evaluate_race_badges(db, athlete_id=1, year=2026, month=8)
    # Dentro del periodo evaluado (agosto 2026) y exactamente la fecha de la
    # carrera, no la fecha de evaluación — para ambos tipos de insignia.
    top10_data = next(b for b in badge_datas if b["badge_type"] == BadgeType.top10)
    assert top10_data["earned_date"] == race_date
    podium_data = next(b for b in badge_datas if b["badge_type"] == BadgeType.first_podium)
    assert podium_data["earned_date"] == race_date


@pytest.mark.asyncio
async def test_upsert_badge_falls_back_to_period_end_when_earned_date_missing():
    """Sin `earned_date` recuperable, se usa el último día del periodo
    evaluado (conservador) — nunca `datetime.now()`."""
    db = make_session()

    async def mock_execute(stmt):
        return make_scalars_result([])  # no existe aún

    db.execute = mock_execute

    badge_data = {
        "badge_type": BadgeType.attendance_100,
        "badge_source": BadgeSource.attendance,
        "metadata_json": {},
        # sin "earned_date": simula un caller legado.
    }
    badge = await _upsert_badge(db, badge_data, athlete_id=1, year=2026, month=4)

    assert badge.earned_at == datetime(2026, 4, 30, tzinfo=timezone.utc)  # abril tiene 30 días


@pytest.mark.asyncio
async def test_badge_earned_at_stable_across_reevaluation():
    """Reevaluar el mismo periodo (p. ej. regenerar el boletín) no mueve
    earned_at: es función determinística de los datos del periodo (fecha de
    sesión/carrera), no del reloj — aunque el evaluador borre e reinserte
    (`evaluate_and_persist_badges`) en cada corrida."""
    from app.models.training_session import AttendanceStatus

    athlete = make_athlete()
    sessions = [make_session_obj(i) for i in range(1, 4)]
    attendances = [make_attendance(s.id, AttendanceStatus.PRESENTE) for s in sessions]

    def make_mock_execute():
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            if is_delete_stmt(stmt):
                return MagicMock()
            call_count += 1
            if call_count == 1:
                return make_scalars_result([athlete])
            elif call_count == 2:
                return make_scalars_result(sessions)
            elif call_count == 3:
                return make_scalars_result(attendances)
            elif call_count == 4:
                return make_scalars_result([])  # RaceCompetitor
            return make_scalars_result([])

        return mock_execute

    db1 = make_session()
    db1.execute = make_mock_execute()
    first_run = await evaluate_and_persist_badges(db1, athlete.id, 2026, 4)
    first_earned_at = next(
        b.earned_at for b in first_run if b.badge_type == BadgeType.attendance_100
    )

    # Segunda "regeneración del boletín": mismos datos subyacentes, sesión de
    # DB nueva (delete + reinsert real haría lo mismo con MySQL).
    db2 = make_session()
    db2.execute = make_mock_execute()
    second_run = await evaluate_and_persist_badges(db2, athlete.id, 2026, 4)
    second_earned_at = next(
        b.earned_at for b in second_run if b.badge_type == BadgeType.attendance_100
    )

    assert first_earned_at == second_earned_at
