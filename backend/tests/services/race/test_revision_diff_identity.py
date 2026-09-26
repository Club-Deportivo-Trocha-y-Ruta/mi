"""T169 — diff identity-aware de ``revision.compute_diff`` (amendment
2026-09-26, contracts/revision-via-skill.md §"Identity-aware diff").

Cubre:

- dos competidores homónimos ya separados (misma terna, discriminadores por
  colisión de dorsal) se diffean por separado, nunca fusionados;
- una corrección de apellido resuelve por el fallback fuzzy y queda marcada
  ``fuzzy_matched=True``;
- el candidato fuzzy de un competidor vinculado a un atleta del club NUNCA
  se auto-matchea — la fila queda ``create``;
- un competidor que cambia de categoría sale como ``delete`` en la vieja más
  ``create`` en la nueva.

Privacidad: nombres/ciudades/clubes sintéticos (``FakeNameGenerator``), nunca
datos reales de menores.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

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
from app.models.race_category import RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from app.services.race.identity_resolver import bib_discriminator
from app.services.race.revision import compute_diff
from app.services.race.staged_document import ResultsRow

SEASON = 2026


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_competitor_signatures",
            "race_identity_candidates",
            "race_results",
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def base_seed(db_session_factory):
    """Coach + serie + evento padre (categoría INF_A, sex=M, 10-11 años)."""
    async with db_session_factory() as db:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="One",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=SEASON,
            kind=RaceSeriesKind.cup, level=RaceSeriesLevel.departmental,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        event = RaceEvent(
            id=1, series_id=1, sequence_number=4, name="Valida IV",
            event_date=date(SEASON, 5, 17), location="Cali",
            created_by_user_id=10, status=RaceEventStatus.COMPLETED,
        )
        cat_inf_a = RaceCategory(
            id=1, code="INF_A", label="Infantil A", sex=CompetitorSex.M,
            age_min=10, age_max=11, tier="menores", sort_order=1, is_active=True,
        )
        cat_juv_a = RaceCategory(
            id=2, code="JUV_A", label="Juvenil A", sex=CompetitorSex.M,
            age_min=15, age_max=16, tier="juvenil", sort_order=2, is_active=True,
        )
        db.add_all([coach, series, event, cat_inf_a, cat_juv_a])
        await db.commit()
    yield


def _row(
    *, position, bib, name, city="Cali", club="Club Trocha y Ruta",
    time_raw="0:20:00", points=50,
) -> ResultsRow:
    return ResultsRow(
        position=position, bib=bib, name=name, city=city, club=club,
        time_raw=time_raw, points=points,
    )


# ---------------------------------------------------------------------------
# Caso 1 — homónimos ya separados por colisión de dorsal, diffean aparte.
# ---------------------------------------------------------------------------


class TestHomonymsAlreadySplit:
    @pytest_asyncio.fixture
    async def seeded(self, base_seed, db_session_factory):
        """Dos competidores "Andres Felipe Mora" (misma terna exacta),
        separados en el import ORIGINAL por colisión de dorsal (101 / 102) —
        cada uno con su propia firma y su propio RaceResult en INF_A."""
        async with db_session_factory() as db:
            comp_a = RaceCompetitor(
                id=201, normalized_name="andres felipe mora", display_name="Andres Felipe Mora",
                club_text="Club Trocha y Ruta", city_text="Cali", sex=CompetitorSex.M,
                athlete_id=None,
            )
            comp_b = RaceCompetitor(
                id=202, normalized_name="andres felipe mora", display_name="Andres Felipe Mora",
                club_text="Club Trocha y Ruta", city_text="Cali", sex=CompetitorSex.M,
                athlete_id=None,
            )
            db.add_all([comp_a, comp_b])
            await db.flush()
            disc_a = bib_discriminator("101", SEASON)
            disc_b = bib_discriminator("102", SEASON)
            db.add_all([
                RaceCompetitorSignature(
                    competitor_id=201, normalized_name="andres felipe mora",
                    club_norm="club trocha y ruta", city_norm="cali",
                    discriminator=disc_a, first_season=SEASON, last_season=SEASON,
                ),
                RaceCompetitorSignature(
                    competitor_id=202, normalized_name="andres felipe mora",
                    club_norm="club trocha y ruta", city_norm="cali",
                    discriminator=disc_b, first_season=SEASON, last_season=SEASON,
                ),
            ])
            db.add_all([
                RaceResult(
                    event_id=1, category_id=1, competitor_id=201, athlete_id=None,
                    bib_number=101, position=1, status=ResultStatus.FINISHED,
                    race_time_ms=20 * 60_000, points_awarded=50, created_by_user_id=10,
                ),
                RaceResult(
                    event_id=1, category_id=1, competitor_id=202, athlete_id=None,
                    bib_number=102, position=2, status=ResultStatus.FINISHED,
                    race_time_ms=21 * 60_000, points_awarded=45, created_by_user_id=10,
                ),
            ])
            await db.commit()
        yield

    @pytest.mark.asyncio
    async def test_two_homonyms_in_one_category_diff_separately(
        self, seeded, db_session_factory
    ):
        """La revisión repite los mismos dos dorsales/tiempos corregidos — cada
        homónimo debe mapear a SU competidor persistido, nunca fusionarse ni
        duplicarse."""
        parsed = {
            "INF_A": [
                _row(position=1, bib="101", name="Andres Felipe Mora", time_raw="0:19:50"),
                _row(position=2, bib="102", name="Andres Felipe Mora", time_raw="0:21:00"),
            ]
        }
        async with db_session_factory() as db:
            report = await compute_diff(db, parsed, parent_event_id=1, season=SEASON)

        assert report.summary.n_delete == 0
        assert report.summary.n_create == 0
        assert report.summary.n_update == 2
        result_ids = {row.result_id for row in report.rows if row.action == "update"}
        # Dos RaceResult DISTINTOS actualizados — nunca la misma fila dos veces.
        assert len(result_ids) == 2
        # Cada fila corrigió el tiempo del competidor correcto (no se
        # cruzaron entre sí): dorsal 101 -> 19:50, dorsal 102 -> 21:00.
        after_times_by_result = {row.result_id: row.after["race_time_ms"] for row in report.rows}
        assert set(after_times_by_result.values()) == {
            19 * 60_000 + 50_000,
            21 * 60_000,
        }


# ---------------------------------------------------------------------------
# Caso 2 — corrección de apellido: fuzzy fallback.
# ---------------------------------------------------------------------------


class TestFuzzyFallback:
    @pytest_asyncio.fixture
    async def seeded(self, base_seed, db_session_factory):
        async with db_session_factory() as db:
            comp = RaceCompetitor(
                id=301, normalized_name="maria jose mejia", display_name="Maria Jose Mejia",
                club_text="Club Trocha y Ruta", city_text="Cali", sex=CompetitorSex.F,
                athlete_id=None,
            )
            db.add(comp)
            await db.flush()
            db.add(
                RaceCompetitorSignature(
                    competitor_id=301, normalized_name="maria jose mejia",
                    club_norm="club trocha y ruta", city_norm="cali",
                    discriminator="", first_season=SEASON, last_season=SEASON,
                )
            )
            db.add(
                RaceResult(
                    event_id=1, category_id=1, competitor_id=301, athlete_id=None,
                    bib_number=201, position=3, status=ResultStatus.FINISHED,
                    race_time_ms=22 * 60_000, points_awarded=40, created_by_user_id=10,
                )
            )
            await db.commit()
        yield

    @pytest.mark.asyncio
    async def test_surname_typo_correction_resolves_via_fuzzy(
        self, seeded, db_session_factory
    ):
        """"Jose" -> "Jse" (letra faltante, typo de digitación) no matchea
        firma exacta (nombre normalizado distinto, partial_ratio 93.3 >= 92)
        — el fallback fuzzy lo resuelve como update del MISMO RaceResult,
        marcado `fuzzy_matched=True`."""
        parsed = {
            "INF_A": [
                _row(position=3, bib="201", name="Maria Jse Mejia", time_raw="0:22:10"),
            ]
        }
        async with db_session_factory() as db:
            report = await compute_diff(db, parsed, parent_event_id=1, season=SEASON)

        assert report.summary.n_create == 0
        assert report.summary.n_update == 1
        row = report.rows[0]
        assert row.action == "update"
        assert row.result_id is not None
        assert row.fuzzy_matched is True


# ---------------------------------------------------------------------------
# Caso 3 — el candidato fuzzy es un atleta del club: nunca se auto-matchea.
# ---------------------------------------------------------------------------


class TestFuzzyNeverMatchesClubAthlete:
    @pytest_asyncio.fixture
    async def seeded(self, base_seed, db_session_factory):
        async with db_session_factory() as db:
            comp = RaceCompetitor(
                id=401, normalized_name="carlos andres gomez", display_name="Carlos Andres Gomez",
                club_text="Club Trocha y Ruta", city_text="Cali", sex=CompetitorSex.M,
                athlete_id=999,  # vinculado a un atleta del club — NUNCA auto-match.
            )
            db.add(comp)
            await db.flush()
            db.add(
                RaceCompetitorSignature(
                    competitor_id=401, normalized_name="carlos andres gomez",
                    club_norm="club trocha y ruta", city_norm="cali",
                    discriminator="", first_season=SEASON, last_season=SEASON,
                )
            )
            db.add(
                RaceResult(
                    event_id=1, category_id=1, competitor_id=401, athlete_id=999,
                    bib_number=301, position=1, status=ResultStatus.FINISHED,
                    race_time_ms=18 * 60_000, points_awarded=50, created_by_user_id=10,
                )
            )
            await db.commit()
        yield

    @pytest.mark.asyncio
    async def test_fuzzy_candidate_on_club_athlete_stays_create(
        self, seeded, db_session_factory
    ):
        """Un nombre parecido (typo) al atleta del club nunca se auto-matchea
        contra su fila — queda `create` para que el candado de identidad la
        levante (feature 045), no un update silencioso sobre un atleta TyR."""
        parsed = {
            "INF_A": [
                _row(position=1, bib="301", name="Carlos Andres Gomz", time_raw="0:18:05"),
            ]
        }
        async with db_session_factory() as db:
            report = await compute_diff(db, parsed, parent_event_id=1, season=SEASON)

        assert report.summary.n_update == 0
        assert report.summary.n_create == 1
        create_row = next(r for r in report.rows if r.action == "create")
        assert create_row.competitor_display_name == "Carlos Andres Gomz"
        # La fila persistida del atleta del club sigue intacta -> delete,
        # porque el nombre nuevo no la reclamó (comportamiento esperado: el
        # candado de identidad decide, no un match silencioso).
        assert report.summary.n_delete == 1


# ---------------------------------------------------------------------------
# Caso 4 — cambio de categoría: delete + create.
# ---------------------------------------------------------------------------


class TestCategoryMove:
    @pytest_asyncio.fixture
    async def seeded(self, base_seed, db_session_factory):
        async with db_session_factory() as db:
            comp = RaceCompetitor(
                id=501, normalized_name="valentina rios ortiz", display_name="Valentina Rios Ortiz",
                club_text="Club Trocha y Ruta", city_text="Cali", sex=CompetitorSex.M,
                athlete_id=None,
            )
            db.add(comp)
            await db.flush()
            db.add(
                RaceCompetitorSignature(
                    competitor_id=501, normalized_name="valentina rios ortiz",
                    club_norm="club trocha y ruta", city_norm="cali",
                    discriminator="", first_season=SEASON, last_season=SEASON,
                )
            )
            db.add(
                RaceResult(
                    event_id=1, category_id=1, competitor_id=501, athlete_id=None,
                    bib_number=401, position=5, status=ResultStatus.FINISHED,
                    race_time_ms=25 * 60_000, points_awarded=30, created_by_user_id=10,
                )
            )
            await db.commit()
        yield

    @pytest.mark.asyncio
    async def test_category_move_yields_delete_plus_create(
        self, seeded, db_session_factory
    ):
        """La revisión trae a esta misma persona corriendo JUV_A en vez de
        INF_A — sale como delete (INF_A) + create (JUV_A), nunca un update
        cross-categoría."""
        parsed = {
            "JUV_A": [
                _row(position=2, bib="401", name="Valentina Rios Ortiz", time_raw="0:19:00"),
            ]
        }
        async with db_session_factory() as db:
            report = await compute_diff(db, parsed, parent_event_id=1, season=SEASON)

        assert report.summary.n_update == 0
        actions = {row.action for row in report.rows}
        assert actions == {"delete", "create"}
        delete_row = next(r for r in report.rows if r.action == "delete")
        create_row = next(r for r in report.rows if r.action == "create")
        assert delete_row.category_code == "INF_A"
        assert create_row.category_code == "JUV_A"


# ---------------------------------------------------------------------------
# Caso 5 — filas `unchanged` se cuentan pero se omiten de `rows`.
# ---------------------------------------------------------------------------


class TestUnchangedOmitted:
    @pytest_asyncio.fixture
    async def seeded(self, base_seed, db_session_factory):
        async with db_session_factory() as db:
            comp = RaceCompetitor(
                id=601, normalized_name="daniela castro leon", display_name="Daniela Castro Leon",
                club_text="Club Trocha y Ruta", city_text="Cali", sex=CompetitorSex.F,
                athlete_id=None,
            )
            db.add(comp)
            await db.flush()
            db.add(
                RaceCompetitorSignature(
                    competitor_id=601, normalized_name="daniela castro leon",
                    club_norm="club trocha y ruta", city_norm="cali",
                    discriminator="", first_season=SEASON, last_season=SEASON,
                )
            )
            db.add(
                RaceResult(
                    event_id=1, category_id=1, competitor_id=601, athlete_id=None,
                    bib_number=501, position=1, status=ResultStatus.FINISHED,
                    race_time_ms=15 * 60_000, points_awarded=50, created_by_user_id=10,
                )
            )
            await db.commit()
        yield

    @pytest.mark.asyncio
    async def test_unchanged_row_counted_but_omitted(self, seeded, db_session_factory):
        parsed = {
            "INF_A": [
                _row(position=1, bib="501", name="Daniela Castro Leon", time_raw="0:15:00"),
            ]
        }
        async with db_session_factory() as db:
            report = await compute_diff(db, parsed, parent_event_id=1, season=SEASON)

        assert report.summary.n_unchanged == 1
        assert report.rows == []
