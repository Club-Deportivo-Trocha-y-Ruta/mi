"""Tests del service layer ``app/services/race/competitor_linking.py``.

Estrategia: SQLite async in-memory con StaticPool para compartir la misma
DB entre conexiones. Las tablas se crean con el subgrafo mínimo necesario
(users, clubs, athletes, race_series/event/category/competitor/result).

Cobertura:

Happy path
----------
- ``link_competitor_to_athlete`` enlaza + propaga a race_results activos.
- ``unlink_competitor`` revierte ambos campos a NULL.
- ``list_unlinked_competitors`` retorna solo competitors con athlete_id NULL.
- ``suggest_athletes_for_competitor`` retorna top-N por fuzzy.

Edge cases
----------
- Re-link al mismo athlete_id → idempotente (``already_linked=True``).
- Link a athlete_id distinto del actual → ``CompetitorAlreadyLinkedError``.
- Link a athlete_id inexistente → ``AthleteNotFoundError``.
- Link a competitor inexistente → ``CompetitorNotFoundError``.
- Unlink competitor unlinked → ``was_linked=False``, sin error.
- Soft-deleted results NO se propagan.
- ``list_unlinked_competitors`` con season filter excluye competitors
  que solo tienen results en otras temporadas.
- ``club_filter='trocha'`` filtra por ``is_trocha_y_ruta``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import AsyncGenerator

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
from app.models.athlete import Athlete, Sex
from app.models.club import Club
from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.models.race_competitor_link_audit import (
    LinkAuditAction,
    RaceCompetitorLinkAudit,
)
from app.services.race.competitor_linking import (
    MAX_UNLINKED_COMPETITORS_TO_SCORE,
    AthleteNotFoundError,
    CompetitorAlreadyLinkedError,
    CompetitorNotFoundError,
    link_competitor_to_athlete,
    list_unlinked_competitors,
    suggest_athletes_for_competitor,
    suggest_competitors_for_new_athlete,
    unlink_competitor,
)


# ---------------------------------------------------------------------------
# Engine + factory + seed
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Asegura registro de modelos
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.club import Club as _Cl  # noqa: F401
    from app.models.race_category import RaceCategory as _Cat  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_competitor_link_audit import (  # noqa: F401
        RaceCompetitorLinkAudit as _LA,
    )
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.user import User as _U  # noqa: F401

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
            "race_competitor_link_audit",
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
async def seed_data(session_factory) -> dict:
    """Seed mínimo + retorna IDs útiles para los tests."""
    async with session_factory() as session:
        club = Club(id=1, name="Trocha y Ruta", code="tyr", is_active=True)
        admin = User(
            id=1,
            email="admin@test.com",
            hashed_password="x",
            first_name="Admin",
            last_name="User",
            role=UserRole.admin,
            is_active=True,
            can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        coach = User(
            id=10,
            email="coach@test.com",
            hashed_password="x",
            first_name="Coach",
            last_name="Test",
            role=UserRole.coach,
            is_active=True,
            can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        # Athlete TyR — Juan Diego (caso real del PR)
        athlete = Athlete(
            id=144,
            user_id=10,  # reuse coach user as placeholder
            first_name="Juan Diego",
            last_name="Garcia Bohorquez",
            birth_date=date(2014, 3, 15),
            sex=Sex.M,
            club_id=1,
            created_by=10,
        )
        athlete2 = Athlete(
            id=145,
            user_id=1,  # reuse admin user as placeholder
            first_name="Otro",
            last_name="Atleta",
            birth_date=date(2013, 6, 20),
            sex=Sex.M,
            club_id=1,
            created_by=10,
        )
        # Series + Events + Category
        series_2026 = RaceSeries(
            id=1,
            name="Copa Valle de Ciclomontañismo",
            season_year=2026,
            organizer="Liga",
            points_scheme_code="copa_valle_2026",
        )
        series_2025 = RaceSeries(
            id=2,
            name="Copa Valle de Ciclomontañismo",
            season_year=2025,
            organizer="Liga",
            points_scheme_code="copa_valle_2025",
        )
        event_2026_v1 = RaceEvent(
            id=10,
            series_id=1,
            sequence_number=1,
            name="Sevilla",
            event_date=date(2026, 1, 31),
            location="Sevilla",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_2026_v2 = RaceEvent(
            id=11,
            series_id=1,
            sequence_number=2,
            name="Ginebra",
            event_date=date(2026, 2, 28),
            location="Ginebra",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_2026_v3 = RaceEvent(
            id=12,
            series_id=1,
            sequence_number=3,
            name="La Cumbre",
            event_date=date(2026, 4, 19),
            location="La Cumbre",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_2026_v4 = RaceEvent(
            id=13,
            series_id=1,
            sequence_number=4,
            name="Cali",
            event_date=date(2026, 5, 17),
            location="Cali",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        event_2025_v1 = RaceEvent(
            id=20,
            series_id=2,
            sequence_number=1,
            name="Antigua",
            event_date=date(2025, 2, 1),
            location="Cali",
            is_championship=False,
            status=RaceEventStatus.COMPLETED,
            created_by_user_id=10,
        )
        cat = RaceCategory(
            id=100,
            code="INF_B",
            label="Infantil B",
            sex=CategoryGender.M,
            age_min=11,
            age_max=12,
            tier=CategoryTier.menores,
            sort_order=31,
            is_active=True,
        )
        # Competitor TyR sin linkage (caso real)
        comp_jd = RaceCompetitor(
            id=217,
            normalized_name="juan diego garcia bohorquez",
            display_name="Juan Diego Garcia Bohorquez",
            club_text="Club Trocha y Ruta",
            sex=CompetitorSex.M,
            athlete_id=None,
        )
        # Competitor TyR sin linkage en otra temporada (para filtro season)
        comp_other = RaceCompetitor(
            id=218,
            normalized_name="otro corredor old",
            display_name="Otro Corredor Old",
            club_text="Club Trocha y Ruta",
            sex=CompetitorSex.M,
            athlete_id=None,
        )
        # Competitor NO TyR (para club_filter) — usamos un club explícito
        # que no comparta substring con TyR variants ("club" prefix
        # confunde is_trocha_y_ruta por partial_ratio).
        comp_external = RaceCompetitor(
            id=219,
            normalized_name="externo runner",
            display_name="Externo Runner",
            club_text="Liga Antioquia",
            sex=CompetitorSex.M,
            athlete_id=None,
        )
        # Competitor YA linkado (no debe aparecer en unlinked)
        comp_linked = RaceCompetitor(
            id=220,
            normalized_name="ya linkeado",
            display_name="Ya Linkeado",
            club_text="Club Trocha y Ruta",
            sex=CompetitorSex.M,
            athlete_id=145,
            linked_at=datetime.now(timezone.utc),
            linked_by_user_id=10,
        )

        session.add_all(
            [
                club,
                admin,
                coach,
                athlete,
                athlete2,
                series_2026,
                series_2025,
                event_2026_v1,
                event_2026_v2,
                event_2026_v3,
                event_2026_v4,
                event_2025_v1,
                cat,
                comp_jd,
                comp_other,
                comp_external,
                comp_linked,
            ]
        )
        await session.commit()

        # 4 race_results 2026 para comp_jd (caso real, 4 válidas distintas)
        results = []
        for i, event_id in enumerate([10, 11, 12, 13]):
            r = RaceResult(
                event_id=event_id,
                category_id=100,
                competitor_id=217,
                athlete_id=None,  # estado pre-link
                bib_number=str(100 + i),
                position=i + 1,
                status=ResultStatus.FINISHED,
                race_time_ms=1800000 + i * 1000,
                points_awarded=40 - i * 5,
                created_by_user_id=10,
            )
            results.append(r)
        # 1 soft-deleted en evento 2025: NO se debe propagar al hacer link
        # de comp_jd (lo dejamos en 2025 para garantizar UNIQUE no choque
        # con los 4 active de 2026).
        soft = RaceResult(
            event_id=20,
            category_id=100,
            competitor_id=217,
            athlete_id=None,
            bib_number="200",
            position=5,
            status=ResultStatus.DSQ,
            race_time_ms=None,
            laps_behind=None,
            points_awarded=0,
            deleted_at=datetime.now(timezone.utc),
            created_by_user_id=10,
        )
        results.append(soft)
        # comp_other tiene results SOLO en 2025
        r_old = RaceResult(
            event_id=20,
            category_id=100,
            competitor_id=218,
            athlete_id=None,
            bib_number="300",
            position=1,
            status=ResultStatus.FINISHED,
            race_time_ms=1900000,
            points_awarded=40,
            created_by_user_id=10,
        )
        results.append(r_old)
        # comp_linked también tiene 1 result en 2026 (sanidad)
        r_linked = RaceResult(
            event_id=10,
            category_id=100,
            competitor_id=220,
            athlete_id=145,
            bib_number="400",
            position=2,
            status=ResultStatus.FINISHED,
            race_time_ms=1850000,
            points_awarded=36,
            created_by_user_id=10,
        )
        results.append(r_linked)
        session.add_all(results)
        await session.commit()

    return {
        "athlete_id": 144,
        "athlete2_id": 145,
        "coach_id": 10,
        "admin_id": 1,
        "comp_jd_id": 217,
        "comp_other_id": 218,
        "comp_external_id": 219,
        "comp_linked_id": 220,
        "event_2026_v1_id": 10,
        "event_2025_v1_id": 20,
    }


@pytest_asyncio.fixture
async def session(session_factory, seed_data) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


# ---------------------------------------------------------------------------
# link_competitor_to_athlete — happy path + edges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_propagates_to_active_results(session, seed_data):
    """Link debe setear athlete_id en los 4 race_results activos (no el soft-deleted)."""
    result = await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    assert result.competitor_id == seed_data["comp_jd_id"]
    assert result.athlete_id == seed_data["athlete_id"]
    assert result.results_propagated == 4
    assert result.already_linked is False
    assert result.linked_by_user_id == seed_data["coach_id"]
    assert isinstance(result.linked_at, datetime)

    # Verifica en DB: 4 active con athlete_id seteado, 1 soft con NULL.
    from sqlalchemy import select

    rows = (
        await session.execute(
            select(RaceResult).where(RaceResult.competitor_id == seed_data["comp_jd_id"])
        )
    ).scalars().all()
    assert len(rows) == 5
    active = [r for r in rows if r.deleted_at is None]
    soft = [r for r in rows if r.deleted_at is not None]
    assert len(active) == 4
    assert len(soft) == 1
    assert all(r.athlete_id == seed_data["athlete_id"] for r in active)
    assert soft[0].athlete_id is None


@pytest.mark.asyncio
async def test_link_competitor_persists_audit_fields(session, seed_data):
    """``linked_at`` y ``linked_by_user_id`` deben persistir en DB."""
    from sqlalchemy import select

    await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    comp = (
        await session.execute(
            select(RaceCompetitor).where(RaceCompetitor.id == seed_data["comp_jd_id"])
        )
    ).scalar_one()
    assert comp.athlete_id == seed_data["athlete_id"]
    assert comp.linked_by_user_id == seed_data["coach_id"]
    assert comp.linked_at is not None


@pytest.mark.asyncio
async def test_link_idempotent_same_athlete_returns_already_linked(session, seed_data):
    """Re-link al MISMO athlete_id → already_linked=True, sin escritura nueva."""
    # Primer link
    r1 = await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()
    original_linked_at = r1.linked_at

    # Re-link
    r2 = await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    assert r2.already_linked is True
    # results_propagated debe ser 0 — ya están sincronizados
    assert r2.results_propagated == 0
    # audit timestamp preservado (SQLite descarta tzinfo en roundtrip;
    # comparamos solo los componentes naive — el dato persistido es el
    # mismo, la zona se rehidrata en lectura).
    assert r2.linked_at.replace(tzinfo=None) == original_linked_at.replace(
        tzinfo=None
    )


@pytest.mark.asyncio
async def test_link_to_different_athlete_raises_conflict(session, seed_data):
    """Link a athlete distinto del actual → CompetitorAlreadyLinkedError."""
    # Primer link
    await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    # Intentar linkar a otro
    with pytest.raises(CompetitorAlreadyLinkedError) as exc_info:
        await link_competitor_to_athlete(
            session,
            competitor_id=seed_data["comp_jd_id"],
            athlete_id=seed_data["athlete2_id"],
            user_id=seed_data["coach_id"],
        )
    assert exc_info.value.current_athlete_id == seed_data["athlete_id"]
    assert exc_info.value.requested_athlete_id == seed_data["athlete2_id"]


@pytest.mark.asyncio
async def test_link_to_nonexistent_athlete_raises(session, seed_data):
    with pytest.raises(AthleteNotFoundError):
        await link_competitor_to_athlete(
            session,
            competitor_id=seed_data["comp_jd_id"],
            athlete_id=99_999,
            user_id=seed_data["coach_id"],
        )


@pytest.mark.asyncio
async def test_link_nonexistent_competitor_raises(session, seed_data):
    with pytest.raises(CompetitorNotFoundError):
        await link_competitor_to_athlete(
            session,
            competitor_id=99_999,
            athlete_id=seed_data["athlete_id"],
            user_id=seed_data["coach_id"],
        )


@pytest.mark.asyncio
async def test_link_skips_soft_deleted_results(session, seed_data):
    """Confirmación explícita: race_results.deleted_at NOT NULL no se actualiza."""
    from sqlalchemy import select

    await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    soft = (
        await session.execute(
            select(RaceResult)
            .where(
                RaceResult.competitor_id == seed_data["comp_jd_id"],
                RaceResult.deleted_at.is_not(None),
            )
        )
    ).scalars().all()
    assert len(soft) == 1
    assert soft[0].athlete_id is None


# ---------------------------------------------------------------------------
# unlink_competitor — happy + idempotente
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_reverts_competitor_and_results(session, seed_data):
    """Unlink debe setear NULL en competitor y en race_results activos."""
    # Setup: linkar primero
    await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    # Unlink
    result = await unlink_competitor(
        session,
        competitor_id=seed_data["comp_jd_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    assert result.was_linked is True
    assert result.results_propagated == 4

    # DB check
    from sqlalchemy import select

    comp = (
        await session.execute(
            select(RaceCompetitor).where(RaceCompetitor.id == seed_data["comp_jd_id"])
        )
    ).scalar_one()
    assert comp.athlete_id is None
    assert comp.linked_at is None
    assert comp.linked_by_user_id is None

    active = (
        await session.execute(
            select(RaceResult)
            .where(
                RaceResult.competitor_id == seed_data["comp_jd_id"],
                RaceResult.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    assert all(r.athlete_id is None for r in active)


@pytest.mark.asyncio
async def test_unlink_unlinked_competitor_is_idempotent(session, seed_data):
    """Unlink un competitor ya en NULL → was_linked=False, sin error."""
    result = await unlink_competitor(
        session,
        competitor_id=seed_data["comp_jd_id"],  # nunca linkado
        user_id=seed_data["coach_id"],
    )
    await session.commit()
    assert result.was_linked is False
    assert result.results_propagated == 0


@pytest.mark.asyncio
async def test_unlink_nonexistent_competitor_raises(session, seed_data):
    with pytest.raises(CompetitorNotFoundError):
        await unlink_competitor(
            session,
            competitor_id=99_999,
            user_id=seed_data["coach_id"],
        )


# ---------------------------------------------------------------------------
# list_unlinked_competitors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_unlinked_excludes_linked_competitor(session, seed_data):
    """``comp_linked`` (id=220, athlete_id=145) NO debe aparecer."""
    rows, total = await list_unlinked_competitors(
        session, include_suggestions=False
    )
    ids = [r.id for r in rows]
    assert seed_data["comp_linked_id"] not in ids
    # comp_jd, comp_other, comp_external → 3 unlinked
    assert total == 3
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_list_unlinked_with_club_filter_trocha(session, seed_data):
    """``club_filter='trocha'`` excluye comp_external (club='Club Otro')."""
    rows, _total = await list_unlinked_competitors(
        session, club_filter="trocha", include_suggestions=False
    )
    ids = [r.id for r in rows]
    assert seed_data["comp_external_id"] not in ids
    assert seed_data["comp_jd_id"] in ids
    assert seed_data["comp_other_id"] in ids


@pytest.mark.asyncio
async def test_list_unlinked_season_filter_2026(session, seed_data):
    """``season=2026`` excluye comp_other (que solo tiene results en 2025)."""
    rows, _total = await list_unlinked_competitors(
        session, season=2026, include_suggestions=False
    )
    ids = [r.id for r in rows]
    assert seed_data["comp_jd_id"] in ids
    assert seed_data["comp_other_id"] not in ids


@pytest.mark.asyncio
async def test_list_unlinked_includes_results_count_and_seasons(session, seed_data):
    """``results_count`` y ``seasons`` deben venir poblados."""
    rows, _total = await list_unlinked_competitors(
        session, include_suggestions=False
    )
    jd = next(r for r in rows if r.id == seed_data["comp_jd_id"])
    # 4 active (no cuenta soft-deleted)
    assert jd.results_count == 4
    assert jd.seasons == [2026]


@pytest.mark.asyncio
async def test_list_unlinked_with_suggestions(session, seed_data):
    """Las sugerencias top-N por competitor deben venir con score ∈ [0, 1]."""
    rows, _total = await list_unlinked_competitors(
        session,
        include_suggestions=True,
        suggestions_limit=3,
        suggestions_threshold=70.0,
    )
    jd = next(r for r in rows if r.id == seed_data["comp_jd_id"])
    # El display_name normalizado matchea exactamente a Juan Diego (id=144)
    assert len(jd.suggestions) >= 1
    top = jd.suggestions[0]
    assert top.athlete_id == seed_data["athlete_id"]
    assert 0.0 <= top.score <= 1.0
    assert top.score >= 0.9  # match cercano a 1.0


@pytest.mark.asyncio
async def test_list_unlinked_pagination(session, seed_data):
    """``offset`` y ``limit`` recortan la página."""
    rows_all, total = await list_unlinked_competitors(
        session, include_suggestions=False
    )
    assert total == 3
    rows_page1, _ = await list_unlinked_competitors(
        session, include_suggestions=False, limit=2, offset=0
    )
    rows_page2, _ = await list_unlinked_competitors(
        session, include_suggestions=False, limit=2, offset=2
    )
    assert len(rows_page1) == 2
    assert len(rows_page2) == 1
    assert {r.id for r in rows_page1 + rows_page2} == {r.id for r in rows_all}


# ---------------------------------------------------------------------------
# suggest_athletes_for_competitor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_athletes_returns_top_for_jd(session, seed_data):
    """El competitor 'Juan Diego Garcia Bohorquez' debe sugerir el athlete 144."""
    suggestions = await suggest_athletes_for_competitor(
        session, competitor_id=seed_data["comp_jd_id"], limit=5
    )
    assert len(suggestions) >= 1
    top = suggestions[0]
    assert top.athlete_id == seed_data["athlete_id"]
    assert top.score >= 0.9


@pytest.mark.asyncio
async def test_suggest_athletes_respects_limit(session, seed_data):
    """``limit=1`` retorna como máximo 1 sugerencia."""
    suggestions = await suggest_athletes_for_competitor(
        session, competitor_id=seed_data["comp_jd_id"], limit=1
    )
    assert len(suggestions) <= 1


@pytest.mark.asyncio
async def test_suggest_athletes_for_nonexistent_competitor_raises(session, seed_data):
    with pytest.raises(CompetitorNotFoundError):
        await suggest_athletes_for_competitor(
            session, competitor_id=99_999, limit=5
        )


@pytest.mark.asyncio
async def test_suggest_athletes_excludes_dissimilar(session, seed_data):
    """``comp_external`` (Externo Runner) no debe matchear con Juan Diego/Otro."""
    suggestions = await suggest_athletes_for_competitor(
        session,
        competitor_id=seed_data["comp_external_id"],
        limit=5,
        threshold=90.0,  # exigente
    )
    assert suggestions == []


# ---------------------------------------------------------------------------
# suggest_competitors_for_new_athlete (Option B — sugerencias INVERSAS)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_happy(session, seed_data):
    """Query 'Juan Diego' + 'Garcia Bohorquez' → top match es comp_jd con score alto."""
    suggestions = await suggest_competitors_for_new_athlete(
        session,
        first_name="Juan Diego",
        last_name="Garcia Bohorquez",
    )
    assert len(suggestions) >= 1
    top = suggestions[0]
    assert top.competitor_id == seed_data["comp_jd_id"]
    assert 0.0 <= top.score <= 1.0
    assert top.score >= 0.9
    # Incluye contexto: 4 results activos en 2026 para comp_jd
    assert top.results_count == 4
    assert top.seasons == [2026]
    # Debe haber un reason humano (no vacío)
    assert top.reason


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_respects_limit(session, seed_data):
    """``limit=2`` retorna como máximo 2 sugerencias."""
    suggestions = await suggest_competitors_for_new_athlete(
        session,
        first_name="Juan Diego",
        last_name="Garcia Bohorquez",
        limit=2,
        threshold=0.0,  # acepta todo
    )
    assert len(suggestions) <= 2


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_club_boost_breaks_tie(
    session_factory,
):
    """Boost +5 cuando club matchea: dos candidatos similares, gana el del mismo club."""
    # Construimos un seed mínimo: dos competitors con nombre IDÉNTICO post-
    # normalización pero clubes distintos. El boost por club debe elegir
    # al del club coincidente.
    async with session_factory() as session:
        club = Club(id=1, name="Trocha y Ruta", code="tyr", is_active=True)
        session.add(club)
        await session.commit()
        # Dos competitors con el mismo nombre ⇒ mismo score base. Pero UNIQUE
        # constraint sobre normalized_name nos obliga a usar nombres ligeramente
        # distintos. Usamos un orden alterno de tokens — fuzz.token_set_ratio
        # ignora el orden, así que el base_score es idéntico.
        c_tyr = RaceCompetitor(
            id=300,
            normalized_name="pedro perez",
            display_name="Pedro Perez",
            club_text="Club Trocha y Ruta",
            sex=CompetitorSex.M,
            athlete_id=None,
        )
        c_other = RaceCompetitor(
            id=301,
            normalized_name="perez pedro",
            display_name="Perez Pedro",
            club_text="Liga Antioquia",
            sex=CompetitorSex.M,
            athlete_id=None,
        )
        session.add_all([c_tyr, c_other])
        await session.commit()

    async with session_factory() as s:
        suggestions = await suggest_competitors_for_new_athlete(
            s,
            first_name="Pedro",
            last_name="Perez",
            club="Trocha y Ruta",
            limit=5,
        )
    assert len(suggestions) == 2
    # El primer slot debe ser el del club TyR (boost ganador)
    assert suggestions[0].competitor_id == 300
    assert suggestions[1].competitor_id == 301
    # El reason del ganador debe reflejar el club
    assert "same club" in suggestions[0].reason


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_no_unlinked_returns_empty(
    session_factory,
):
    """0 competitors con athlete_id IS NULL → lista vacía."""
    # Seed vacío: no agregamos competitors.
    async with session_factory() as session:
        club = Club(id=1, name="Trocha y Ruta", code="tyr", is_active=True)
        session.add(club)
        await session.commit()
    async with session_factory() as s:
        suggestions = await suggest_competitors_for_new_athlete(
            s,
            first_name="Juan",
            last_name="Garcia",
        )
    assert suggestions == []


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_high_threshold_filters(session, seed_data):
    """Threshold=95 excluye matches débiles (fuzzy <95)."""
    # Query "Pedro Perez" no matchea con ningún competitor del seed
    # (comp_jd es 'Juan Diego', comp_other es 'Otro Corredor', etc.).
    suggestions = await suggest_competitors_for_new_athlete(
        session,
        first_name="Pedro",
        last_name="Perez",
        threshold=95.0,
    )
    assert suggestions == []


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_handles_accents(session, seed_data):
    """Caracteres con tildes y ñ: la normalización maneja ambos lados."""
    # comp_jd display_name = "Juan Diego Garcia Bohorquez"
    # Query con acentos: "Juán Diego" + "García Bohórquez" debe matchear
    suggestions = await suggest_competitors_for_new_athlete(
        session,
        first_name="Juán Diego",
        last_name="García Bohórquez",
        threshold=70.0,
    )
    assert len(suggestions) >= 1
    top = suggestions[0]
    assert top.competitor_id == seed_data["comp_jd_id"]
    assert top.score >= 0.9


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_excludes_already_linked(
    session, seed_data
):
    """``comp_linked`` (id=220, athlete_id NOT NULL) NO debe aparecer aunque
    el nombre matchee exactamente."""
    suggestions = await suggest_competitors_for_new_athlete(
        session,
        first_name="Ya",
        last_name="Linkeado",
        threshold=70.0,
    )
    ids = [s.competitor_id for s in suggestions]
    assert seed_data["comp_linked_id"] not in ids


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_empty_inputs_returns_empty(
    session, seed_data
):
    """Whitespace-only nombre → lista vacía sin tocar DB (defensa)."""
    suggestions = await suggest_competitors_for_new_athlete(
        session,
        first_name="   ",
        last_name="  ",
    )
    assert suggestions == []


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_score_normalized_to_unit_interval(
    session, seed_data
):
    """Score expuesto al frontend debe estar en [0, 1]."""
    suggestions = await suggest_competitors_for_new_athlete(
        session,
        first_name="Juan Diego",
        last_name="Garcia Bohorquez",
        threshold=0.0,
    )
    for s in suggestions:
        assert 0.0 <= s.score <= 1.0


@pytest.mark.asyncio
async def test_suggest_competitors_by_name_results_count_excludes_soft_deleted(
    session, seed_data
):
    """``results_count`` cuenta solo race_results con deleted_at IS NULL.
    El seed tiene 4 active + 1 soft-deleted para comp_jd → count=4."""
    suggestions = await suggest_competitors_for_new_athlete(
        session,
        first_name="Juan Diego",
        last_name="Garcia Bohorquez",
        threshold=70.0,
    )
    top = next(s for s in suggestions if s.competitor_id == seed_data["comp_jd_id"])
    assert top.results_count == 4


# ---------------------------------------------------------------------------
# R3-A1: race condition (atomic UPDATE)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_race_condition_second_writer_gets_409(
    session_factory, seed_data, monkeypatch
):
    """Si dos escritores concurrentes intentan linkar el mismo competitor a
    athletes DISTINTOS, el segundo debe recibir ``CompetitorAlreadyLinkedError``
    (mapeado a 409 en el router) — no last-writer-wins.

    Estrategia de simulación: parchamos ``_load_competitor`` para retornar
    un competitor con ``athlete_id=None`` (estado pre-carrera) aunque la
    DB ya tenga ``athlete_id=144`` (committed por el primer writer). El
    pre-check del service ve None → falla por el camino del UPDATE atómico.
    El UPDATE en DB usa WHERE ``athlete_id IS NULL`` → rowcount=0 →
    refresh → detecta conflict → 409.
    """
    # Writer 1 commitea.
    async with session_factory() as s1:
        await link_competitor_to_athlete(
            s1,
            competitor_id=seed_data["comp_jd_id"],
            athlete_id=seed_data["athlete_id"],
            user_id=seed_data["coach_id"],
        )
        await s1.commit()

    # Writer 2: monkeypatch _load_competitor para devolver un objeto fake
    # con athlete_id=None (la "stale view" pre-carrera).
    from app.services.race import competitor_linking as cl_module

    original_load_competitor = cl_module._load_competitor
    call_count = {"n": 0}

    async def fake_load_competitor(db, competitor_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Primera llamada: devolvemos un competitor "stale" con
            # athlete_id=None para forzar el camino del UPDATE atómico.
            from sqlalchemy import select

            comp = (
                await db.execute(
                    select(RaceCompetitor).where(
                        RaceCompetitor.id == competitor_id
                    )
                )
            ).scalar_one()
            # NO mutamos el objeto trackeado por la sesión (causaría
            # autoflush parásito). Creamos un proxy sólo-lectura.
            from types import SimpleNamespace

            return SimpleNamespace(
                id=comp.id,
                athlete_id=None,
                linked_at=None,
                linked_by_user_id=None,
            )
        return await original_load_competitor(db, competitor_id)

    monkeypatch.setattr(cl_module, "_load_competitor", fake_load_competitor)

    async with session_factory() as s2:
        with pytest.raises(CompetitorAlreadyLinkedError) as exc_info:
            await link_competitor_to_athlete(
                s2,
                competitor_id=seed_data["comp_jd_id"],
                athlete_id=seed_data["athlete2_id"],  # athlete distinto
                user_id=seed_data["coach_id"],
            )
        assert exc_info.value.current_athlete_id == seed_data["athlete_id"]
        assert exc_info.value.requested_athlete_id == seed_data["athlete2_id"]


@pytest.mark.asyncio
async def test_link_race_condition_second_writer_same_athlete_degrades_to_idempotent(
    session_factory, seed_data, monkeypatch
):
    """Si dos escritores concurrentes piden el MISMO athlete, el segundo
    debe degradar a idempotente (``already_linked=True``) — no 409.

    Misma técnica de monkeypatch que el test anterior: forzamos el camino
    del UPDATE atómico para que el refresh post-rowcount=0 detecte el
    state actual y devuelva ``already_linked=True``.
    """
    # Writer 1 commitea
    async with session_factory() as s1:
        await link_competitor_to_athlete(
            s1,
            competitor_id=seed_data["comp_jd_id"],
            athlete_id=seed_data["athlete_id"],
            user_id=seed_data["coach_id"],
        )
        await s1.commit()

    from app.services.race import competitor_linking as cl_module

    original_load_competitor = cl_module._load_competitor
    call_count = {"n": 0}

    async def fake_load_competitor(db, competitor_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            from types import SimpleNamespace

            return SimpleNamespace(
                id=competitor_id,
                athlete_id=None,
                linked_at=None,
                linked_by_user_id=None,
            )
        return await original_load_competitor(db, competitor_id)

    monkeypatch.setattr(cl_module, "_load_competitor", fake_load_competitor)

    async with session_factory() as s2:
        result = await link_competitor_to_athlete(
            s2,
            competitor_id=seed_data["comp_jd_id"],
            athlete_id=seed_data["athlete_id"],  # MISMO athlete
            user_id=seed_data["coach_id"],
        )
        assert result.already_linked is True
        assert result.athlete_id == seed_data["athlete_id"]


# ---------------------------------------------------------------------------
# R3-M1: audit trail persistente (race_competitor_link_audit)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_creates_audit_row(session, seed_data):
    """Link exitoso debe persistir una fila en ``race_competitor_link_audit``.

    Campos esperados: ``action='link'``, ``previous_athlete_id=None``,
    ``new_athlete_id=athlete_id``, ``results_propagated`` matchea LinkResult,
    ``user_id`` es el actor.
    """
    from sqlalchemy import select

    await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    rows = (
        await session.execute(
            select(RaceCompetitorLinkAudit).where(
                RaceCompetitorLinkAudit.competitor_id == seed_data["comp_jd_id"]
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    a = rows[0]
    assert a.action == LinkAuditAction.link
    assert a.previous_athlete_id is None
    assert a.new_athlete_id == seed_data["athlete_id"]
    assert a.results_propagated == 4  # 4 active results en seed
    assert a.user_id == seed_data["coach_id"]
    assert isinstance(a.created_at, datetime)


@pytest.mark.asyncio
async def test_unlink_creates_audit_row_with_previous_athlete(
    session, seed_data
):
    """Unlink debe persistir audit ``action='unlink'`` con
    ``previous_athlete_id`` igual al athlete que estaba enlazado.

    Esto es el corazón del fix R3-M1: cuando ``race_competitors.linked_by_user_id``
    se borra (NULL), la fila de audit preserva la traza histórica.
    """
    from sqlalchemy import select

    # Setup: linkar primero (esto crea 1 fila de audit action=link)
    await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    # Unlink
    await unlink_competitor(
        session,
        competitor_id=seed_data["comp_jd_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    rows = (
        await session.execute(
            select(RaceCompetitorLinkAudit)
            .where(
                RaceCompetitorLinkAudit.competitor_id == seed_data["comp_jd_id"]
            )
            .order_by(RaceCompetitorLinkAudit.id)
        )
    ).scalars().all()
    assert len(rows) == 2
    link_row, unlink_row = rows[0], rows[1]
    assert link_row.action == LinkAuditAction.link
    assert unlink_row.action == LinkAuditAction.unlink
    # CRÍTICO: el audit preserva quién era el athlete enlazado.
    assert unlink_row.previous_athlete_id == seed_data["athlete_id"]
    assert unlink_row.new_athlete_id is None
    assert unlink_row.results_propagated == 4
    assert unlink_row.user_id == seed_data["coach_id"]


@pytest.mark.asyncio
async def test_link_idempotent_does_not_create_duplicate_audit(
    session, seed_data
):
    """Re-link al MISMO athlete (idempotente) NO debe crear audit duplicado.

    El audit registra TRANSICIONES, no llamadas. Sin esta regla cualquier
    cliente que reintente la operación inflaría la tabla con duplicados.
    """
    from sqlalchemy import select

    # Primer link → crea audit row 1
    await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    # Re-link idempotente → NO debe crear audit row 2
    await link_competitor_to_athlete(
        session,
        competitor_id=seed_data["comp_jd_id"],
        athlete_id=seed_data["athlete_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()

    count = (
        await session.execute(
            select(RaceCompetitorLinkAudit).where(
                RaceCompetitorLinkAudit.competitor_id == seed_data["comp_jd_id"]
            )
        )
    ).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_unlink_noop_does_not_create_audit(session, seed_data):
    """Unlink sobre un competitor que NO estaba enlazado (``was_linked=False``)
    NO debe crear audit row — no hubo transición real."""
    from sqlalchemy import select

    # comp_jd nunca fue linkado en este test
    result = await unlink_competitor(
        session,
        competitor_id=seed_data["comp_jd_id"],
        user_id=seed_data["coach_id"],
    )
    await session.commit()
    assert result.was_linked is False

    rows = (
        await session.execute(
            select(RaceCompetitorLinkAudit).where(
                RaceCompetitorLinkAudit.competitor_id == seed_data["comp_jd_id"]
            )
        )
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# R3-M3: cap defensivo en suggest_competitors_for_new_athlete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggestions_caps_at_max_unlinked(
    session_factory, caplog, monkeypatch
):
    """Si hay más de ``MAX_UNLINKED_COMPETITORS_TO_SCORE`` competitors huérfanos,
    el servicio sólo procesa hasta el cap y emite un warning sin nombres.

    Reducimos el cap para hacer el test rápido y verificamos:

    - No se devuelven más sugerencias de las que el cap permite scorear.
    - Se emite log warning con la palabra clave ``cap_hit`` (sin nombres).
    """
    import logging

    # Reducir el cap dramáticamente para test (10 en vez de 1000)
    monkeypatch.setattr(
        "app.services.race.competitor_linking.MAX_UNLINKED_COMPETITORS_TO_SCORE",
        10,
    )

    async with session_factory() as session:
        club = Club(id=1, name="Trocha y Ruta", code="tyr", is_active=True)
        session.add(club)
        await session.commit()
        # Insertamos 15 competitors huérfanos con nombres únicos pero
        # similares a la query para que TODOS scoreen alto.
        comps = []
        for i in range(15):
            comps.append(
                RaceCompetitor(
                    id=1000 + i,
                    normalized_name=f"pedro perez {i}",
                    display_name=f"Pedro Perez {i}",
                    club_text="X",
                    sex=CompetitorSex.M,
                    athlete_id=None,
                )
            )
        session.add_all(comps)
        await session.commit()

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.services.race.competitor_linking"):
        async with session_factory() as s:
            suggestions = await suggest_competitors_for_new_athlete(
                s,
                first_name="Pedro",
                last_name="Perez",
                threshold=0.0,
                limit=100,
            )

    # El servicio sólo scoreó 10 — devuelve a lo más 10 sugerencias.
    assert len(suggestions) <= 10
    # Log warning emitido con la marca ``cap_hit`` y sin nombres
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("cap_hit" in r.getMessage() for r in warning_records)
    # Privacidad: el log no debe contener nombres en bruto
    for r in warning_records:
        msg = r.getMessage().lower()
        assert "pedro" not in msg
        assert "perez" not in msg


@pytest.mark.asyncio
async def test_max_unlinked_cap_constant_is_reasonable():
    """Sanidad: el cap default está en un rango razonable (no 1, no 1M).

    Si alguien cambia el cap inadvertidamente, este test sirve de canary.
    """
    assert 100 <= MAX_UNLINKED_COMPETITORS_TO_SCORE <= 100_000
