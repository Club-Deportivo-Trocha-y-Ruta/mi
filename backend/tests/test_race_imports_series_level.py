"""Tests backend spec 023 — National Championship Level (T015).

Cubre ``_get_or_create_series``/``stage_extracted_results`` con
``series_level``:

  (1) Crear una serie NUEVA de campeonato con ``series_level=national`` ->
      ``series.level == national`` y ``organizer is None`` (NO se aplica el
      default "Liga Vallecaucana de Ciclismo" — decisión D5 del plan 023 /
      research R5).
  (2) Crear una serie NUEVA de copa (``series_level`` por defecto,
      departmental) -> ``organizer == "Liga Vallecaucana de Ciclismo"`` sin
      cambios (byte-identical al comportamiento pre-023).
  (3) ``series_level`` inválido -> ``ValueError`` en el helper
      ``_get_or_create_series`` (llamada directa).

Amendment 2026-09-26 (contracts/staged-import.md): ``POST /parse`` se retiró
— (1) y (2) staguean directamente vía ``stage_extracted_results`` (helper
``_stage`` de este módulo), sin HTTP ni parser real; la validación de
``series_level`` sobre input externo (manifest JSON) vive ahora en
``scripts/race_results.py``, cubierta en
``tests/scripts/test_race_results_cli.py``.

Estrategia: SQLite async in-memory + StaticPool.

Privacidad invariante: no se usan datos ficticios de menores; race_series /
race_imports son metadata pública de federación.
"""
from __future__ import annotations

from datetime import datetime, timezone

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

from app.config import settings
from app.models import Base
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite async in-memory con solo las tablas necesarias para /parse."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    from app.models.user import User as _U  # noqa: F401
    from app.models.club import Club as _Cl, ClubMember as _CM  # noqa: F401
    from app.models.athlete import Athlete as _A  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401

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
            "race_import_staged_documents",
            "race_categories",
            "race_competitors",
            "race_results",
            *AUDIT_TABLES,
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
async def seed_test_data(db_session_factory):
    """Inserta el coach usado por todos los tests (sin serie preexistente —
    cada test crea su propia serie NUEVA vía /parse para poder observar
    `_get_or_create_series` en su rama "crear")."""
    async with db_session_factory() as session:
        coach1 = User(
            id=10, email="coach10@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(coach1)
        await session.commit()
    yield


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
    """Redirige storage_sftp al fallback local en tmp_path."""
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(
        storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/test"
    )
    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield fake_base




# ---------------------------------------------------------------------------
# Helpers de payload
# ---------------------------------------------------------------------------

async def _stage(
    db_session_factory,
    *,
    series_name: str,
    series_kind: RaceSeriesKind = RaceSeriesKind.cup,
    series_level: RaceSeriesLevel = RaceSeriesLevel.departmental,
    marker: bytes = b"contenido",
    actor_id: int = 10,
):
    """Sucesor de ``POST /parse`` (retirado, amendment 2026-09-26) — staguea
    un documento sintético directamente vía ``stage_extracted_results``, sin
    HTTP ni parser real."""
    from datetime import date

    from app.services.race.import_staging import StageHeader, stage_extracted_results
    from app.services.race.staged_document import (
        ParsedCategory,
        ParsedResults,
        ResultsRow,
        StagedProfileMeta,
    )
    from app.services.request_context import AuditContext

    document = ParsedResults(
        categories=[
            ParsedCategory(
                header_raw="TETEROS CON PEDALES",
                code="TET_CP",
                rows=[
                    ResultsRow(
                        position=1, bib="550", name="Sebastian Yule Mendoza",
                        city="Yumbo", club="Club Trocha y Ruta",
                        time_raw="0:03:38", points=40,
                    ),
                ],
            ),
        ],
        unreadable_rows=[],
    )
    header = StageHeader(
        series_name=series_name,
        series_kind=series_kind,
        series_level=series_level,
        season=2026,
        valida_num=1,
        event_name="EVENTO TEST",
        event_date=date(2026, 7, 18),
        location="PEREIRA",
    )
    profile = StagedProfileMeta(
        profile_id="test-race-imports-series-level",
        profile_sha256="6" * 64,
        engine_version="test-helper",
    )
    async with db_session_factory() as session:
        actor = await session.get(User, actor_id)
        result = await stage_extracted_results(
            session,
            document=document,
            profile=profile,
            file_bytes=marker,
            original_filename="resultados.pdf",
            results_ext="pdf",
            header=header,
            actor=actor,
            ctx=AuditContext.for_user(actor, request_id="test-stage-series-level"),
        )
        await session.commit()
        return result


# ===========================================================================
# (1) Campeonato NUEVO con series_level=national -> organizer NULL
# ===========================================================================


class TestSeriesLevelOnNewSeries:
    @pytest.mark.asyncio
    async def test_new_national_championship_series_has_no_valle_organizer(
        self, seed_test_data, override_storage, db_session_factory
    ):
        """FR-006 / D5: campeonato nacional NUEVO -> organizer None, level=national."""
        await _stage(
            db_session_factory,
            series_name="Campeonato Nacional MTB 2026",
            series_kind=RaceSeriesKind.championship,
            series_level=RaceSeriesLevel.national,
            marker=b"contenido nacional",
        )

        async with db_session_factory() as session:
            result = await session.execute(
                select(RaceSeries).where(
                    RaceSeries.name == "Campeonato Nacional MTB 2026",
                    RaceSeries.season_year == 2026,
                )
            )
            series = result.scalar_one()

        assert series.kind == RaceSeriesKind.championship
        assert series.level == RaceSeriesLevel.national
        assert series.organizer is None, (
            "El campeonato nacional NO debe heredar el organizer "
            "'Liga Vallecaucana de Ciclismo' (D5 / FR-006)."
        )

    @pytest.mark.asyncio
    async def test_new_cup_series_keeps_valle_organizer_default_unchanged(
        self, seed_test_data, override_storage, db_session_factory
    ):
        """Regresión: crear una copa NUEVA (sin series_level) mantiene el
        default de organizer byte-identical al comportamiento pre-023.
        """
        await _stage(
            db_session_factory,
            series_name="Copa Valle 023 Regresion",
            marker=b"contenido copa",
        )

        async with db_session_factory() as session:
            result = await session.execute(
                select(RaceSeries).where(
                    RaceSeries.name == "Copa Valle 023 Regresion",
                    RaceSeries.season_year == 2026,
                )
            )
            series = result.scalar_one()

        assert series.kind == RaceSeriesKind.cup
        assert series.level == RaceSeriesLevel.departmental
        assert series.organizer == "Liga Vallecaucana de Ciclismo"


# ===========================================================================
# (3) series_level inválido -> ValueError (helper)
# ===========================================================================
#
# Amendment 2026-09-26 (contracts/staged-import.md): ``POST /parse`` se
# retiró — no hay Form field HTTP que validar. La validación de
# ``series_level`` sobre input externo (manifest JSON) vive ahora en
# ``scripts/race_results.py`` (T146-149, cubierta en
# ``tests/scripts/test_race_results_cli.py``); aquí solo queda la prueba
# directa del helper.


class TestSeriesLevelInvalid:
    @pytest.mark.asyncio
    async def test_get_or_create_series_helper_rejects_invalid_level(
        self, db_session_factory
    ):
        """Llamada directa al helper con un `level` inválido.

        Pre-T020: `_get_or_create_series` no tiene parámetro `level` -> la
        llamada lanza `TypeError` (kwarg inexistente), no `ValueError`, así
        que este `pytest.raises(ValueError)` FALLA por la razón correcta
        (falta implementar T020).
        """
        # Feature 044 (US5, T059): el helper se extrajo a
        # `app.services.race.import_staging` (contracts/historical-load.md
        # §"Staging service"); el router ya no lo re-exporta.
        from app.services.race.import_staging import _get_or_create_series

        async with db_session_factory() as session:
            with pytest.raises(ValueError):
                await _get_or_create_series(
                    session,
                    "Serie Helper Nivel Invalido",
                    2026,
                    RaceSeriesKind.championship,
                    level="galactic",  # type: ignore[arg-type]
                )
