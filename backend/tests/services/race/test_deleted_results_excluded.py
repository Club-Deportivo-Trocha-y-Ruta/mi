"""T171 — sweep de lectura tras un soft-delete de revisión (amendment
2026-09-26, contracts/revision-via-skill.md §"Reads exclude removed
results").

Comitea una revisión que elimina un ``RaceResult`` (via
``revision.commit_revision``) y confirma que la fila desaparece de:

- ``history.build_history_points`` (histórico cross-temporada);
- ``field_metrics.compute_field_metrics`` / ``compute_category_metrics``
  (tamaño de campo, mediana, percentil) — incluso cuando el caller le pasa
  la fila soft-deleted sin filtrar primero (defensa en profundidad: cada
  consumidor filtra por su cuenta, no solo el query que lo alimenta);
- ``standings.get_event_standings``;
- ``results_read.get_event_results`` — vista coach (sin restricción) y
  vista familia (``allowed_athlete_ids``).

No repite la cobertura de ``race/queries.py`` (contexto del analista),
season panorama ni las vistas de familia de resultados propias del router
de temporada — esos consumidores comparten el mismo filtro SQL
``deleted_at IS NULL`` ya probado exhaustivamente en sus propios test
files; este sweep se concentra en los módulos citados explícitamente por
el contrato que no tenían ninguna prueba tocando un ``RaceResult``
producido por una revisión.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.athlete import Sex as AthleteSex
from app.models.club import Club
from app.models.race_category import RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from app.services.race import history, standings
from app.services.race.field_metrics import compute_category_metrics
from app.services.race.results_read import get_event_results
from app.services.race.revision import (
    DiffRow,
    DiffReport,
    DiffSummary,
    RevisionContext,
    commit_revision,
)
from app.services.race.staged_document import ResultsRow  # noqa: F401 (typing parity)

SEASON = 2026


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    from app.models.athlete import Athlete  # noqa: F401
    from app.models.club import ClubMember  # noqa: F401
    from app.models.race_course_category_setup import (  # noqa: F401
        RaceCourseCategorySetup,
    )
    from app.models.race_course_variant import RaceCourseVariant  # noqa: F401
    from app.models.race_identity_candidate import RaceIdentityCandidate  # noqa: F401

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
            "clubs",
            "club_members",
            "athletes",
            "race_series",
            "race_events",
            "race_imports",
            "race_categories",
            "race_competitors",
            "race_competitor_signatures",
            "race_identity_candidates",
            "race_results",
            "race_course_variants",
            "race_course_category_setups",
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        from sqlalchemy import text as _text

        await conn.execute(
            _text(
                "CREATE TABLE race_result_revisions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "result_id INTEGER REFERENCES race_results(id), "
                "action VARCHAR(20) NOT NULL, "
                "changed_by_user_id INTEGER NOT NULL REFERENCES users(id), "
                "changed_at DATETIME NOT NULL, "
                "diff_json JSON NOT NULL, "
                "reason VARCHAR(300)"
                ")"
            )
        )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def seeded(db_session_factory):
    """Evento committed con DOS resultados en INF_A: uno de un atleta del
    club (competitor_id=1, athlete_id=1 — el que la revisión eliminará) y
    uno de un tercero (competitor_id=2) que permanece."""
    async with db_session_factory() as db:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="One", role=UserRole.coach,
            is_active=True, can_login=True, created_at=datetime.now(timezone.utc),
        )
        athlete_user = User(
            id=20, email="athlete@test.com", hashed_password="x",
            first_name="Athlete", last_name="One", role=UserRole.athlete,
            is_active=True, can_login=False, created_at=datetime.now(timezone.utc),
        )
        club = Club(id=1, name="Club Trocha y Ruta", code="TYR")
        db.add_all([coach, athlete_user, club])
        await db.flush()

        from app.models.athlete import Athlete

        athlete = Athlete(
            id=1, user_id=20, first_name="Atleta", last_name="Uno",
            birth_date=date(SEASON - 11, 1, 1), sex=AthleteSex.M,
            club_id=1, created_by=10,
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
        category = RaceCategory(
            id=1, code="INF_A", label="Infantil A", sex=CompetitorSex.M,
            age_min=10, age_max=11, tier="menores", sort_order=1, is_active=True,
        )
        parent_import = RaceImport(
            id=900, filename="parent.pdf", original_filename="parent.pdf",
            sha256="p" * 64, series_id=1, event_id=1,
            status=RaceImportStatus.committed, stats_json={},
            imported_by_user_id=10, imported_at=datetime.now(timezone.utc),
            kind=RaceImportKind.resultados,
        )
        comp_athlete = RaceCompetitor(
            id=1, normalized_name="atleta uno", display_name="Atleta Uno",
            club_text="Club Trocha y Ruta", city_text="Cali", sex=CompetitorSex.M,
            athlete_id=1,
        )
        comp_third = RaceCompetitor(
            id=2, normalized_name="tercero externo", display_name="Tercero Externo",
            club_text="Club Rival", city_text="Cali", sex=CompetitorSex.M,
            athlete_id=None,
        )
        db.add_all([athlete, series, event, category, parent_import, comp_athlete, comp_third])
        await db.flush()
        db.add_all([
            RaceCompetitorSignature(
                competitor_id=1, normalized_name="atleta uno",
                club_norm="club trocha y ruta", city_norm="cali",
                discriminator="", first_season=SEASON, last_season=SEASON,
            ),
            RaceCompetitorSignature(
                competitor_id=2, normalized_name="tercero externo",
                club_norm="club rival", city_norm="cali",
                discriminator="", first_season=SEASON, last_season=SEASON,
            ),
        ])
        db.add_all([
            RaceResult(
                id=1, event_id=1, category_id=1, competitor_id=1, athlete_id=1,
                bib_number=101, position=1, status=ResultStatus.FINISHED,
                race_time_ms=18 * 60_000, points_awarded=50, created_by_user_id=10,
            ),
            RaceResult(
                id=2, event_id=1, category_id=1, competitor_id=2, athlete_id=None,
                bib_number=102, position=2, status=ResultStatus.FINISHED,
                race_time_ms=19 * 60_000, points_awarded=45, created_by_user_id=10,
            ),
        ])
        await db.commit()
    yield


async def _commit_delete_revision(db_session_factory) -> None:
    """Aplica, vía ``commit_revision``, un diff que elimina el RaceResult
    id=1 (el atleta del club) — igual que haría el router en una revisión
    real cuyo documento nuevo no trae a ese competidor."""
    async with db_session_factory() as db:
        revision_ctx = RevisionContext(
            parent_event_id=1, parent_import_id=900,
            parent_committed_at=datetime.now(timezone.utc),
            parent_committed_by_user_id=10, n_results_persisted=2,
        )
        diff = DiffReport(
            summary=DiffSummary(n_create=0, n_update=0, n_delete=1, n_unchanged=1),
            rows=[
                DiffRow(
                    action="delete",
                    competitor_normalized_name="atleta uno",
                    competitor_display_name="Atleta Uno",
                    category_code="INF_A",
                    result_id=1,
                    before={"result_id": 1},
                ),
            ],
        )
        parse_import = RaceImport(
            id=901, filename="revision.pdf", original_filename="revision.pdf",
            sha256="r" * 64, series_id=1,
            status=RaceImportStatus.pending, stats_json={},
            imported_by_user_id=10, imported_at=datetime.now(timezone.utc),
            kind=RaceImportKind.resultados,
        )
        db.add(parse_import)
        await db.flush()
        await commit_revision(
            db, parse_import, revision_ctx, diff, "result_removed", 10
        )
        await db.commit()


class TestDeletedResultsExcludedFromReads:
    @pytest.mark.asyncio
    async def test_field_metrics_excludes_soft_deleted_row(
        self, seeded, db_session_factory
    ):
        await _commit_delete_revision(db_session_factory)
        async with db_session_factory() as db:
            # A propósito NO filtramos deleted_at aquí — el punto es probar
            # que compute_field_metrics filtra por su cuenta.
            rows = (
                await db.execute(select(RaceResult).where(RaceResult.event_id == 1))
            ).scalars().all()
            assert len(rows) == 2  # el soft-deleted sigue en la tabla.

            sets = compute_category_metrics(rows, event_id=1, category_id=1)
        # compute_category_metrics indexa por result_id — el resultado
        # soft-deleted (id=1) nunca produce un MetricSet, aunque se le haya
        # pasado sin filtrar.
        assert 1 not in sets
        assert 2 in sets
        assert sets[2]["field_size"] == 1  # el eliminado no cuenta en el campo.

    @pytest.mark.asyncio
    async def test_event_standings_excludes_soft_deleted_row(
        self, seeded, db_session_factory
    ):
        await _commit_delete_revision(db_session_factory)
        async with db_session_factory() as db:
            result = await standings.get_event_standings(db, race_event_id=1)
        assert result is not None
        all_rows = [row for cat in result.categories for row in cat.rows]
        competitor_ids_present = {row.competitor_id for row in all_rows}
        # El competidor eliminado (id=1) no debe quedar en ninguna posición.
        assert competitor_ids_present == {2}
        assert len(all_rows) == 1

    @pytest.mark.asyncio
    async def test_get_event_results_excludes_soft_deleted_row_coach_and_family(
        self, seeded, db_session_factory
    ):
        await _commit_delete_revision(db_session_factory)
        async with db_session_factory() as db:
            coach_view = await get_event_results(db, race_event_id=1)
            family_view = await get_event_results(
                db, race_event_id=1, allowed_athlete_ids={1}
            )
        assert coach_view is not None
        coach_rows = [row for cat in coach_view.categories for row in cat.rows]
        assert len(coach_rows) == 1

        assert family_view is not None
        family_rows = [row for cat in family_view.categories for row in cat.rows]
        # El único atleta permitido para esta familia es justo el eliminado.
        assert family_rows == []

    @pytest.mark.asyncio
    async def test_history_excludes_soft_deleted_row_for_the_athlete(
        self, seeded, db_session_factory
    ):
        await _commit_delete_revision(db_session_factory)
        async with db_session_factory() as db:
            results = (
                await db.execute(select(RaceResult).where(RaceResult.event_id == 1))
            ).scalars().all()
            events = (await db.execute(select(RaceEvent))).scalars().all()
            series = (await db.execute(select(RaceSeries))).scalars().all()
            categories = (await db.execute(select(RaceCategory))).scalars().all()

        points = history.build_history_points(
            list(results), list(events), list(series), list(categories), athlete_id=1
        )
        assert points == []
