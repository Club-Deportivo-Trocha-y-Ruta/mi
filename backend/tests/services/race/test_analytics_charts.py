"""Tests del servicio ``app/services/race/analytics_charts.py`` (BE-3).

Cobertura:

- ``build_evolution``: low confidence con n<3, orden por valida_num,
  cálculo de podium_gap.
- ``build_distribution``: pseudonimización determinística, low confidence
  con n<5 (sin curve, tabla con points pseudonimizados), is_self del
  atleta, z-score y percentil, display_name por rol, rango real de curva.

Estrategia: SQLite async in-memory con StaticPool. Cada test siembra
un escenario mínimo (1 atleta + 1 categoría + N race_results) y verifica
el payload del servicio.
"""
from __future__ import annotations

from datetime import date
from typing import Any, AsyncGenerator, Optional

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.models.user import UserRole
from app.schemas.athlete_race_analysis import (
    AnalysisConfidence,
    EvolutionMetric,
)
from app.services.race.analytics_charts import (
    _build_pseudonym,
    build_distribution,
    build_evolution,
    list_athlete_races,
)
from app.services.race.race_labels import build_race_label

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
)


# ---------------------------------------------------------------------------
# Engine + factory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "athletes",
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_results",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Sesión + seed mínimo: club + coach + atleta + serie + categoría."""
    async with session_factory() as s:
        await create_club(s, club_id=1)
        await create_user(s, user_id=10, role=UserRole.coach)
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(s, athlete_id=144, club_id=1, user_id=144)
        await create_race_series(
            s, series_id=1, season_year=2026
        )
        await create_race_category(s, category_id=100, code="INF_B")
        await s.commit()
        yield s


# ---------------------------------------------------------------------------
# Helpers de escenario
# ---------------------------------------------------------------------------


async def _seed_athlete_in_event(
    session: AsyncSession,
    *,
    event_id: int,
    sequence_number: int,
    event_date: date,
    name: str,
    athlete_position: int,
    athlete_time_ms: int,
    winner_time_ms: int,
    other_runners: int = 3,
    series_id: int = 1,
    category_id: int = 100,
    athlete_id: int = 144,
) -> None:
    """Crea event + ganador + N runners + el atleta. La categoría tiene
    1 + other_runners + 1 corredores en total."""
    await create_race_event(
        session,
        event_id=event_id,
        series_id=series_id,
        sequence_number=sequence_number,
        name=name,
        event_date=event_date,
    )
    # Ganador
    winner_cid = event_id * 1000 + 1
    await create_race_competitor(
        session,
        competitor_id=winner_cid,
        normalized_name=f"winner ev{event_id}",
        display_name=f"Winner {event_id}",
    )
    await create_race_result(
        session,
        event_id=event_id,
        category_id=category_id,
        competitor_id=winner_cid,
        position=1,
        race_time_ms=winner_time_ms,
        bib_number=1,
        points_awarded=40,
    )
    # Atleta target
    athlete_cid = event_id * 1000 + 2
    await create_race_competitor(
        session,
        competitor_id=athlete_cid,
        normalized_name=f"athlete ev{event_id}",
        display_name=f"Athlete {event_id}",
        athlete_id=athlete_id,
    )
    await create_race_result(
        session,
        event_id=event_id,
        category_id=category_id,
        competitor_id=athlete_cid,
        athlete_id=athlete_id,
        position=athlete_position,
        race_time_ms=athlete_time_ms,
        bib_number=athlete_position,
        points_awarded=40 - 4 * (athlete_position - 1),
    )
    # Otros runners (suficientes para alcanzar el sample size deseado)
    for i in range(other_runners):
        cid = event_id * 1000 + 100 + i
        await create_race_competitor(
            session,
            competitor_id=cid,
            normalized_name=f"runner{i} ev{event_id}",
            display_name=f"Runner{i} {event_id}",
        )
        await create_race_result(
            session,
            event_id=event_id,
            category_id=category_id,
            competitor_id=cid,
            position=athlete_position + i + 1,
            race_time_ms=athlete_time_ms + (i + 1) * 1_000,
            bib_number=athlete_position + i + 1,
            points_awarded=10,
        )


# ---------------------------------------------------------------------------
# build_evolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_evolution_returns_low_confidence_when_n_less_than_3(session):
    """Si hay <3 puntos válidos → confidence=low."""
    # Solo 2 eventos.
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=2,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
    )
    await _seed_athlete_in_event(
        session,
        event_id=2,
        sequence_number=2,
        event_date=date(2026, 2, 28),
        name="V2",
        athlete_position=3,
        athlete_time_ms=1_820_000,
        winner_time_ms=1_800_000,
    )
    await session.commit()

    result = await build_evolution(
        session,
        athlete_id=144,
        season=2026,
        metric=EvolutionMetric.PODIUM_GAP_MS,
    )
    assert result.confidence == AnalysisConfidence.low
    assert len(result.series) == 2


@pytest.mark.asyncio
async def test_build_evolution_orders_by_valida_num(session):
    """La serie debe venir ordenada por ``valida_num ASC`` (sequence_number)."""
    # Crear eventos fuera de orden: V3 antes que V1 en el seed.
    await _seed_athlete_in_event(
        session,
        event_id=3,
        sequence_number=3,
        event_date=date(2026, 4, 19),
        name="V3",
        athlete_position=2,
        athlete_time_ms=1_805_000,
        winner_time_ms=1_800_000,
    )
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
    )
    await _seed_athlete_in_event(
        session,
        event_id=2,
        sequence_number=2,
        event_date=date(2026, 2, 28),
        name="V2",
        athlete_position=2,
        athlete_time_ms=1_807_000,
        winner_time_ms=1_800_000,
    )
    await session.commit()

    result = await build_evolution(
        session,
        athlete_id=144,
        season=2026,
        metric=EvolutionMetric.RANKING,
    )
    valida_nums = [p.valida_num for p in result.series]
    assert valida_nums == sorted(valida_nums)
    assert valida_nums == [1, 2, 3]


@pytest.mark.asyncio
async def test_build_evolution_podium_gap_metric_calculates_diff_to_winner(session):
    """podium_gap_ms = athlete_time - winner_time (P1 propio → gap=0)."""
    # Atleta P2, gap esperado = 10_000 ms.
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=2,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
    )
    await session.commit()

    result = await build_evolution(
        session,
        athlete_id=144,
        season=2026,
        metric=EvolutionMetric.PODIUM_GAP_MS,
    )
    assert len(result.series) == 1
    point = result.series[0]
    assert point.value == 10_000.0
    assert point.unit == "ms"


@pytest.mark.asyncio
async def test_build_evolution_winner_point_has_gap_pct_zero(session):
    """El propio ganador (P1, tiempo == tiempo mínimo de la categoría) debe
    exponer ``gap_pct == 0.0`` explícito, no ``None`` (feature 039, B-2)."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=1,
        athlete_time_ms=1_800_000,
        winner_time_ms=1_800_000,
    )
    await session.commit()

    result = await build_evolution(
        session,
        athlete_id=144,
        season=2026,
        metric=EvolutionMetric.RANKING,
    )
    assert len(result.series) == 1
    point = result.series[0]
    assert point.position == 1
    assert point.gap_pct == 0.0


@pytest.mark.asyncio
async def test_build_evolution_field_size_counts_finished_without_time(session):
    """F-8: ``field_size`` cuenta TODOS los FINISHED del (evento, categoría)
    aunque no tengan ``race_time_ms`` (mismo criterio que
    ``field_metrics.compute_field_metrics``); el percentil por TIEMPO sigue
    exigiendo ≥5 finishers CON tiempo registrado y se oculta si no los hay,
    aunque ``field_size`` ya sea 5."""
    await create_race_event(
        session,
        event_id=1,
        series_id=1,
        sequence_number=1,
        name="V1",
        event_date=date(2026, 1, 31),
    )
    winner_cid, athlete_cid, filler1_cid, filler2_cid, no_time_cid = (
        1001,
        1002,
        1003,
        1004,
        1005,
    )
    for cid, label in (
        (winner_cid, "winner"),
        (athlete_cid, "athlete"),
        (filler1_cid, "filler1"),
        (filler2_cid, "filler2"),
        (no_time_cid, "no-time"),
    ):
        await create_race_competitor(
            session,
            competitor_id=cid,
            normalized_name=f"{label} ev1",
            display_name=f"{label.title()} 1",
            athlete_id=144 if cid == athlete_cid else None,
        )
    await create_race_result(
        session,
        event_id=1,
        category_id=100,
        competitor_id=winner_cid,
        position=1,
        race_time_ms=1_800_000,
        bib_number=1,
    )
    await create_race_result(
        session,
        event_id=1,
        category_id=100,
        competitor_id=athlete_cid,
        athlete_id=144,
        position=2,
        race_time_ms=1_815_000,
        bib_number=2,
    )
    await create_race_result(
        session,
        event_id=1,
        category_id=100,
        competitor_id=filler1_cid,
        position=3,
        race_time_ms=1_820_000,
        bib_number=3,
    )
    await create_race_result(
        session,
        event_id=1,
        category_id=100,
        competitor_id=filler2_cid,
        position=4,
        race_time_ms=1_825_000,
        bib_number=4,
    )
    # FINISHED sin tiempo registrado (rider "a N vueltas", registrado por
    # laps_behind en vez de tiempo exacto — el único caso real donde
    # ck_race_results_time_consistent_with_status permite status=finished
    # con race_time_ms NULL). Debe contar en field_size (5 finishers en
    # total) pero no en la muestra del percentil por tiempo (que se queda
    # en 4 con tiempo, bajo el umbral).
    session.add(
        RaceResult(
            event_id=1,
            category_id=100,
            competitor_id=no_time_cid,
            position=5,
            status="finished",
            race_time_ms=None,
            laps_behind=2,
            bib_number=5,
            points_awarded=0,
            created_by_user_id=10,
        )
    )
    await session.commit()

    ranking_result = await build_evolution(
        session, athlete_id=144, season=2026, metric=EvolutionMetric.RANKING
    )
    point = ranking_result.series[0]
    assert point.field_size == 5
    # Percentil posicional (research D3): n=5, position=2 → 100*(1-1/4)=75.0.
    assert point.percentile == pytest.approx(75.0, abs=0.05)

    percentile_result = await build_evolution(
        session, athlete_id=144, season=2026, metric=EvolutionMetric.PERCENTILE
    )
    pct_point = percentile_result.series[0]
    # Solo 4 finishers CON tiempo (<5) → el percentil por TIEMPO se oculta,
    # aunque field_size ya sea 5.
    assert pct_point.field_size == 5
    assert pct_point.value is None


# ---------------------------------------------------------------------------
# build_distribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_distribution_pseudonymizes_competitors(session):
    """Cada DistributionPoint sin include_display_name solo expone ``pseudonym``
    y ``display_name=None`` — competitor_id nunca viaja al cliente."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=4,  # total = 6 corredores (≥5 para activar curve)
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, event_id=1
    )
    assert result.sample_size == 6
    assert len(result.points) == 6
    for point in result.points:
        # Pseudónimo bien formado: "C0000".."C9999".
        assert point.pseudonym.startswith("C")
        assert len(point.pseudonym) == 5
        # Sin include_display_name → display_name=None (default).
        assert point.display_name is None
        # competitor_id no viaja nunca: no está en el schema.
        dumped = point.model_dump()
        assert "competitor_id" not in dumped


@pytest.mark.asyncio
async def test_build_distribution_low_confidence_when_n_less_than_5(session):
    """sample_size < 5 → curve vacía y confidence=low; points pseudonimizados
    siguen viniendo poblados para que el cliente pueda renderizar tabla."""
    # Total runners = 4 (1 ganador + atleta + 2 más) → debajo del umbral.
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=2,  # 1 winner + 1 athlete + 2 = 4 < 5
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, event_id=1
    )
    assert result.sample_size == 4
    # Points pseudonimizados siempre presentes — la tabla los necesita.
    assert len(result.points) == 4
    assert all(p.pseudonym.startswith("C") for p in result.points)
    # Curva normal no se ajusta con n<5 (sería engañosa con muestra chica).
    assert result.curve == []
    assert result.confidence == AnalysisConfidence.low


@pytest.mark.asyncio
async def test_build_distribution_self_marker_correctly_flagged(session):
    """El point del atleta consultante debe tener ``is_self=True``."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=4,
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, event_id=1
    )
    self_points = [p for p in result.points if p.is_self]
    assert len(self_points) == 1
    # El tiempo del self point debe coincidir con athlete_time_ms del seed.
    assert self_points[0].time_ms == 1_810_000


@pytest.mark.asyncio
async def test_build_distribution_athlete_z_score_and_percentile(session):
    """Verifica z-score y percentile contra distribución conocida."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=4,
        athlete_time_ms=1_815_000,
        winner_time_ms=1_800_000,
        other_runners=4,
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, event_id=1
    )
    # mean y stddev calculados sobre 6 puntos (winner..athlete..runners)
    assert result.mean_ms is not None
    assert result.stddev_ms is not None
    assert result.stddev_ms > 0
    # z-score: athlete está por encima del mean (peor tiempo) → z > 0 si el
    # tiempo está por encima del mean. Sanity check basado en datos:
    # times = [1800k, 1815k, 1816k, 1817k, 1818k] aprox.
    # El sentido exacto del signo depende de la posición del atleta.
    assert result.athlete_z_score is not None
    # Percentile en [0..100]
    assert result.athlete_percentile is not None
    assert 0.0 <= result.athlete_percentile <= 100.0
    # Pseudónimo determinístico — el helper privado lo arma así.
    self_point = next(p for p in result.points if p.is_self)
    # El competitor_id del atleta seed-eado es event_id * 1000 + 2 = 1002.
    expected_pseudo = _build_pseudonym(1002)
    assert self_point.pseudonym == expected_pseudo


# ---------------------------------------------------------------------------
# Nuevos tests: display_name por rol, rango real de curva
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_distribution_with_include_display_name_populates_field(session):
    """Con include_display_name=True cada point expone display_name no vacío."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=4,  # total 6 ≥ 5
    )
    await session.commit()

    result = await build_distribution(
        session,
        athlete_id=144,
        season=2026,
        event_id=1,
        include_display_name=True,
    )
    assert result.sample_size == 6
    # Todos los puntos deben tener display_name poblado (seed los define).
    for point in result.points:
        assert point.display_name is not None
        assert len(point.display_name) > 0


@pytest.mark.asyncio
async def test_build_distribution_without_include_display_name_is_none(session):
    """Con include_display_name=False (default) todos los display_name son None."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=4,
    )
    await session.commit()

    result = await build_distribution(
        session,
        athlete_id=144,
        season=2026,
        event_id=1,
        include_display_name=False,
    )
    for point in result.points:
        assert point.display_name is None


@pytest.mark.asyncio
async def test_build_distribution_curve_range_equals_min_max_times(session):
    """La curva se extiende desde min(times) hasta max(times), no ±3σ."""
    await _seed_athlete_in_event(
        session,
        event_id=1,
        sequence_number=1,
        event_date=date(2026, 1, 31),
        name="V1",
        athlete_position=3,
        athlete_time_ms=1_810_000,
        winner_time_ms=1_800_000,
        other_runners=4,  # total 6 ≥ 5, activa curva
    )
    await session.commit()

    result = await build_distribution(
        session, athlete_id=144, season=2026, event_id=1
    )
    # La curva debe estar activa (n=6 ≥ 5).
    assert len(result.curve) == 60

    # x_ms[0] debe coincidir con el tiempo mínimo del sample (winner 1_800_000).
    assert result.curve[0].x_ms == pytest.approx(1_800_000.0, rel=1e-4)
    # x_ms[-1] debe coincidir con el tiempo máximo del sample.
    # Con other_runners=4: tiempos = 1800k, 1810k, 1811k, 1812k, 1813k, 1814k
    # (winner + athlete P3 + runners P4..P7).
    assert result.curve[-1].x_ms == pytest.approx(1_814_000.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Feature 039 — grupos de comparación (T016, TDD-red)
#
# Usa las fixtures reutilizables de ``tests/fixtures/race_groups.py``
# (registradas globalmente vía ``conftest.py::pytest_plugins``):
#
#   - ``race_groups_base_season``: 1 copa (5 válidas) + Cto. Dep. + Cto. Nal.
#   - ``race_groups_two_cups``: agrega una segunda copa cuya Válida I es
#     anterior a la de la copa principal (para el test de orden).
#   - ``race_groups_dnf_championship``: el Cto. Nacional del atleta es DNF.
#
# Ninguno de estos tests debería pasar todavía: ``build_evolution`` no acepta
# ``series_id``, no calcula ``groups``/``selected_group`` y ``EvolutionPoint``/
# ``RaceParticipationOption`` no exponen los campos nuevos — el fallo esperado
# es ``TypeError`` (kwarg desconocido) o ``AttributeError`` (atributo
# inexistente en el schema Pydantic actual).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_evolution_groups_ordered_cups_then_championships(
    race_groups_base_season,
):
    """``response.groups``: la copa primero, luego los campeonatos por fecha
    (Cto. Dep. 2026-06-20 antes que Cto. Nal. 2026-08-22)."""
    scenario = race_groups_base_season
    result = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
    )

    groups = result.groups
    assert [g.series_id for g in groups] == [
        scenario.cup_series_id,
        scenario.departmental_series_id,
        scenario.national_series_id,
    ], f"Orden de groups inesperado: {[g.series_id for g in groups]}"

    cup_group = groups[0]
    assert cup_group.comparison_group == f"cup:{scenario.cup_series_id}"
    assert cup_group.kind == "cup"
    assert cup_group.level == "departmental"
    assert cup_group.label == f"{scenario.cup_series_name} {scenario.season}"
    assert cup_group.n_points == 5

    dep_group = groups[1]
    assert dep_group.comparison_group == (
        f"championship:{scenario.departmental_series_id}"
    )
    assert dep_group.kind == "championship"
    assert dep_group.level == "departmental"
    assert dep_group.label == build_race_label(
        RaceSeriesKind.championship, 1, "Ginebra", level=RaceSeriesLevel.departmental
    )
    assert dep_group.n_points == 1

    nat_group = groups[2]
    assert nat_group.comparison_group == f"championship:{scenario.national_series_id}"
    assert nat_group.kind == "championship"
    assert nat_group.level == "national"
    assert nat_group.label == build_race_label(
        RaceSeriesKind.championship, 1, "Pereira", level=RaceSeriesLevel.national
    )
    assert nat_group.n_points == 1


@pytest.mark.asyncio
async def test_build_evolution_groups_order_two_cups_by_earliest_round_not_series_id(
    race_groups_two_cups,
):
    """Con dos copas, el orden entre ellas es por la fecha de su válida más
    temprana — NO por ``series_id`` (6002 > 6001 rompería si se ordenara así)
    ni por orden de inserción (la copa principal se siembra primero)."""
    scenario = race_groups_two_cups
    result = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
    )

    cup_group_ids = [g.series_id for g in result.groups if g.kind == "cup"]
    # "Liga Departamental" corre desde el 5 de enero; la copa principal desde
    # el 15 de enero → Liga debe ir primero pese a tener series_id mayor.
    assert cup_group_ids == [
        scenario.second_cup_series_id,
        scenario.cup_series_id,
    ], f"Orden de copas inesperado: {cup_group_ids}"


@pytest.mark.asyncio
async def test_build_evolution_series_id_filters_points_and_sets_selected_group(
    race_groups_base_season,
):
    """``series_id=<copa>`` filtra ``series`` a solo esa copa y fija
    ``selected_group``; ``groups`` sigue completo (las 3 series)."""
    scenario = race_groups_base_season
    result = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
        series_id=scenario.cup_series_id,
    )

    assert result.selected_group == f"cup:{scenario.cup_series_id}"
    assert len(result.series) == 5, (
        f"Esperaba solo las 5 válidas de la copa filtrada, recibí "
        f"{len(result.series)}"
    )
    assert all(p.series_id == scenario.cup_series_id for p in result.series)
    assert len(result.groups) == 3, "groups debe seguir completo con el filtro aplicado"


@pytest.mark.asyncio
async def test_build_evolution_unknown_series_id_returns_empty_series_low_confidence(
    race_groups_base_season,
):
    """``series_id`` que no corresponde a ninguna serie del atleta →
    ``series == []``, ``groups`` sigue poblado, ``confidence == low``
    (nunca 404 — contrato ``evolution-api.md``)."""
    scenario = race_groups_base_season
    result = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
        series_id=999999,
    )

    assert result.series == []
    assert len(result.groups) == 3
    assert result.confidence == AnalysisConfidence.low


@pytest.mark.asyncio
async def test_build_evolution_confidence_computed_over_filtered_series(
    race_groups_base_season,
):
    """``confidence`` se recalcula sobre la serie YA filtrada, no sobre la
    temporada completa: 7 puntos (medium) vs. 1 punto del Cto. Dep. (low)."""
    scenario = race_groups_base_season

    full = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
    )
    assert len(full.series) == 7
    assert full.confidence == AnalysisConfidence.medium

    filtered = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
        series_id=scenario.departmental_series_id,
    )
    assert len(filtered.series) == 1
    assert filtered.confidence == AnalysisConfidence.low


@pytest.mark.asyncio
async def test_build_evolution_points_carry_series_and_field_metrics(
    race_groups_base_season,
):
    """Cada ``EvolutionPoint`` lleva ``series_id``/``series_name``/
    ``series_level``/``comparison_group``/``field_size``/``percentile``
    (percentil posicional, research D3 — no el percentil por tiempo)."""
    scenario = race_groups_base_season
    result = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
    )

    cup_point = next(
        p for p in result.series if p.event_id == scenario.cup_event_ids[0]
    )
    assert cup_point.series_id == scenario.cup_series_id
    assert cup_point.series_name == scenario.cup_series_name
    assert cup_point.series_level == "departmental"
    assert cup_point.comparison_group == f"cup:{scenario.cup_series_id}"
    # Pelotón de 4 (winner + atleta P2 + 2 rellenos) →
    # percentil = 100*(1-(2-1)/(4-1)) = 66.7.
    assert cup_point.field_size == 4
    assert cup_point.percentile == pytest.approx(66.7, abs=0.05)

    dep_point = next(
        p for p in result.series if p.event_id == scenario.departmental_event_id
    )
    assert dep_point.series_id == scenario.departmental_series_id
    assert dep_point.series_name == scenario.departmental_series_name
    assert dep_point.series_level == "departmental"
    assert dep_point.comparison_group == f"championship:{scenario.departmental_series_id}"
    # Atleta P4 de 4 → percentil = 100*(1-(4-1)/(4-1)) = 0.0.
    assert dep_point.field_size == 4
    assert dep_point.percentile == pytest.approx(0.0, abs=0.05)


@pytest.mark.asyncio
async def test_build_evolution_championship_point_exposes_position_and_gap_pct(
    race_groups_base_season,
):
    """Un punto de campeonato expone ``position``/``gap_pct`` sin importar
    la métrica solicitada — la tarjeta de campeonato del frontend los
    necesita aunque ``metric`` sea otra cosa (feature 039, F-1 / B-2).

    Cto. Dep.: winner_time_ms=1_900_000, atleta P4 →
    race_time_ms=1_900_000+20_000*4=1_980_000 →
    gap_pct=100*(1_980_000-1_900_000)/1_900_000≈4.2.
    """
    scenario = race_groups_base_season

    for metric in (EvolutionMetric.RANKING, EvolutionMetric.TIME_MS):
        result = await build_evolution(
            scenario.session,
            athlete_id=scenario.athlete_id,
            season=scenario.season,
            metric=metric,
        )
        dep_point = next(
            p for p in result.series if p.event_id == scenario.departmental_event_id
        )
        assert dep_point.position == 4, f"metric={metric}"
        assert dep_point.gap_pct == pytest.approx(4.2, abs=0.05), f"metric={metric}"


@pytest.mark.asyncio
async def test_build_evolution_percentile_is_none_when_not_finished(
    race_groups_dnf_championship,
):
    """DNF propio → ``value`` y ``percentile`` en ``None``; ``field_size``
    solo cuenta a los que sí terminaron (nunca al propio DNF); el grupo del
    campeonato sigue apareciendo en ``groups`` pero con ``n_points == 0``.
    ``position``/``gap_pct`` (feature 039, B-2) también quedan en ``None``
    para el propio DNF."""
    scenario = race_groups_dnf_championship
    result = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
    )

    nat_point = next(
        p for p in result.series if p.event_id == scenario.national_event_id
    )
    assert nat_point.value is None
    assert nat_point.percentile is None
    assert nat_point.position is None
    assert nat_point.gap_pct is None
    # Pelotón FINISHED = winner + 2 rellenos = 3 (el DNF del atleta no cuenta).
    assert nat_point.field_size == 3

    nat_group = next(
        g for g in result.groups if g.series_id == scenario.national_series_id
    )
    assert nat_group.n_points == 0


@pytest.mark.asyncio
async def test_list_athlete_races_items_carry_series_fields(
    race_groups_base_season,
):
    """``RaceParticipationOption`` gana ``series_id``/``series_name``/
    ``series_level`` (contrato ``evolution-api.md`` §races)."""
    scenario = race_groups_base_season
    result = await list_athlete_races(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
    )

    cup_item = next(
        i for i in result.items if i.event_id == scenario.cup_event_ids[0]
    )
    assert cup_item.series_id == scenario.cup_series_id
    assert cup_item.series_name == scenario.cup_series_name
    assert cup_item.series_level == "departmental"

    dep_item = next(
        i for i in result.items if i.event_id == scenario.departmental_event_id
    )
    assert dep_item.series_id == scenario.departmental_series_id
    assert dep_item.series_name == scenario.departmental_series_name
    assert dep_item.series_level == "departmental"

    nat_item = next(
        i for i in result.items if i.event_id == scenario.national_event_id
    )
    assert nat_item.series_id == scenario.national_series_id
    assert nat_item.series_name == scenario.national_series_name
    assert nat_item.series_level == "national"


# ---------------------------------------------------------------------------
# T042 (039): aserciones adicionales de dos copas para build_evolution.
#
# ``test_build_evolution_groups_order_two_cups_by_earliest_round_not_series_id``
# ya cubre el orden ENTRE las dos copas; lo que falta aquí es el orden
# COMPLETO (copas + campeonatos juntos), ``selected_group is None`` por
# defecto y que filtrar por ``series_id`` de la segunda copa devuelva SOLO
# sus rondas (nunca las 5 válidas de la copa principal ni los campeonatos).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_evolution_two_cups_full_groups_order_and_default_selected_group(
    race_groups_two_cups,
):
    """``groups`` completo: las DOS copas primero (Liga antes que la copa
    principal, por válida más temprana), luego los DOS campeonatos por
    fecha; ``selected_group`` es ``None`` cuando no se pasa ``series_id``."""
    scenario = race_groups_two_cups
    result = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
    )

    assert [g.series_id for g in result.groups] == [
        scenario.second_cup_series_id,
        scenario.cup_series_id,
        scenario.departmental_series_id,
        scenario.national_series_id,
    ], f"Orden de groups inesperado: {[g.series_id for g in result.groups]}"
    assert [g.kind for g in result.groups] == [
        "cup",
        "cup",
        "championship",
        "championship",
    ]
    assert result.selected_group is None


@pytest.mark.asyncio
async def test_build_evolution_series_id_filter_second_cup_returns_only_its_rounds(
    race_groups_two_cups,
):
    """``series_id=<Liga Departamental>`` filtra ``series`` a solo sus 3
    rondas — nunca las 5 válidas de la copa principal ni los campeonatos,
    aunque ``groups`` siga completo."""
    scenario = race_groups_two_cups
    result = await build_evolution(
        scenario.session,
        athlete_id=scenario.athlete_id,
        season=scenario.season,
        metric=EvolutionMetric.RANKING,
        series_id=scenario.second_cup_series_id,
    )

    assert result.selected_group == f"cup:{scenario.second_cup_series_id}"
    assert len(result.series) == 3
    assert all(p.series_id == scenario.second_cup_series_id for p in result.series)
    assert {p.event_id for p in result.series} == set(scenario.second_cup_event_ids)
    assert len(result.groups) == 4, "groups debe seguir completo con el filtro aplicado"


# ---------------------------------------------------------------------------
# F-10 — series_name NULL fallback (defensive; unreachable via schema today,
# race_series.name is NOT NULL, but EvolutionPoint declares min_length=1).
# ---------------------------------------------------------------------------


class _FakeExecResult:
    """Emula el ``Result`` de SQLAlchemy — solo lo que ``build_evolution`` usa."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return self._rows


class _FakeRow:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping


class _FakeDbNullSeriesName:
    """Fake mínimo de ``AsyncSession`` — una sola fila con ``series_name=None``.

    ``build_evolution`` consume SQL crudo (``text()``), así que no hace
    falta una DB real ni el ``FakeAsyncSession`` del ingestor (que solo
    soporta ``select(Model)``) para probar el fallback en aislamiento.
    """

    async def execute(self, _sql: Any, _params: Optional[dict] = None) -> _FakeExecResult:
        row = _FakeRow(
            {
                "event_id": 1,
                "valida_num": 1,
                "event_date": "2026-01-31",
                "status": "finished",
                "position": 1,
                "race_time_ms": 1_800_000,
                "winner_time_ms": 1_800_000,
                "time_max_ms": 1_800_000,
                "cat_size": 1,
                "cat_size_with_time": 1,
                "series_id": 1,
                "series_name": None,
                "series_kind": "cup",
                "series_level": "departmental",
                "location": None,
            }
        )
        return _FakeExecResult([row])


@pytest.mark.asyncio
async def test_build_evolution_series_name_null_falls_back_to_placeholder():
    """F-10: ``series_name`` NULL degrada a un placeholder no vacío.

    ``EvolutionPoint.series_name`` declara ``min_length=1`` — devolver ``""``
    rompería la validación del schema con un 500 en vez de degradar.
    """
    result = await build_evolution(
        _FakeDbNullSeriesName(),  # type: ignore[arg-type]
        athlete_id=1,
        season=2026,
        metric=EvolutionMetric.RANKING,
    )
    assert result.series[0].series_name == "Serie"
