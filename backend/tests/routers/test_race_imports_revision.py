"""Tests F-UP-REV2: detector de revisión + cambio comportamiento /parse.

Cubre:

- ``detect_revision`` retorna ``RevisionContext`` cuando `(series, valida)` ya
  tiene committed previo.
- ``detect_revision`` retorna ``None`` cuando es primer import.
- Endpoint POST /parse:
  - SHA byte-exacto duplicado sigue retornando 409 (sin cambio F-UP).
  - PDF nuevo con misma `(series, valida)` y SHA distinto → 200 con
    `will_be_revision=true` + metadata del parent.
  - PDF de válida nueva sin previo → 200 con `will_be_revision=false`.
  - Series inexistente / no encontrada → 200 + `will_be_revision=false`.
  - Caso defensivo: parse con misma `(series, valida)` pero event sin committed
    (legacy F1.7 con event_id NULL) → `will_be_revision=false`.

Reusa fixtures del test_race_imports.py existente (coach_client, seed_test_data,
override_storage) — los duplicamos aquí para evitar acoplamiento. Amendment
2026-09-26 (contracts/staged-import.md): ``POST /parse`` se retiró — el
staging ahora se hace directamente vía ``stage_extracted_results``
(``_stage`` helper de este módulo), sin HTTP ni parser real.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.models import Base
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.services.race.revision import detect_revision
from tests.helpers.audit_tables import AUDIT_TABLES


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    from app.models.user import User as _U  # noqa: F401
    from app.models.race_series import RaceSeries as _S  # noqa: F401
    from app.models.race_event import RaceEvent as _E  # noqa: F401
    from app.models.race_import import RaceImport as _I  # noqa: F401
    from app.models.race_category import RaceCategory as _C  # noqa: F401
    from app.models.race_competitor import RaceCompetitor as _Comp  # noqa: F401
    from app.models.race_result import RaceResult as _R  # noqa: F401
    from app.models.race_result_revision import (  # noqa: F401
        RaceResultRevision,
    )

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "race_series",
            "race_events",
            "race_imports",
            "race_import_staged_documents",
            "race_categories",
            "race_competitors",
            "race_results",
            "race_result_revisions",
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
async def seed_data(db_session_factory):
    async with db_session_factory() as session:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="One",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        session.add_all([coach, series])
        await session.commit()
    yield


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-rev"
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


_PDF_HEADER = b"%PDF-1.4\n"


async def _stage(
    db_session_factory,
    *,
    marker: bytes = b"content",
    valida_num: int = 4,
    series_name: str = "Copa Valle de Ciclomontañismo",
):
    """Sucesor de ``POST /parse`` (retirado, amendment 2026-09-26) — staguea
    un documento sintético directamente vía ``stage_extracted_results`` y
    devuelve el ``StageResult`` (``is_revision``/``parent_import_id``).
    ``parent_event_id``/``parent_committed_at``/``parent_n_results`` no
    sobreviven a este servicio (solo estaban en la respuesta HTTP de
    ``ImportParseResponse``) — esa metadata sigue probada directamente contra
    ``detect_revision`` en ``TestDetectRevisionUnit``."""
    from datetime import date

    from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
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
        series_kind=RaceSeriesKind.cup,
        series_level=RaceSeriesLevel.departmental,
        season=2026,
        valida_num=valida_num,
        event_name="VALIDA IV CALI",
        event_date=date(2026, 5, 17),
        location="CALI",
    )
    profile = StagedProfileMeta(
        profile_id="test-race-imports-revision",
        profile_sha256="3" * 64,
        engine_version="test-helper",
    )
    async with db_session_factory() as session:
        actor = await session.get(User, 10)
        result = await stage_extracted_results(
            session,
            document=document,
            profile=profile,
            file_bytes=_PDF_HEADER + marker,
            original_filename="resultados.pdf",
            results_ext="pdf",
            header=header,
            actor=actor,
            ctx=AuditContext.for_user(actor, request_id="test-stage-revision"),
        )
        await session.commit()
        return result


# ---------------------------------------------------------------------------
# Tests detect_revision (unidad)
# ---------------------------------------------------------------------------


class TestDetectRevisionUnit:
    @pytest.mark.asyncio
    async def test_detect_returns_none_when_series_missing(self, db_session_factory):
        """Serie con nombre inexistente → None."""
        async with db_session_factory() as session:
            ctx = await detect_revision(
                session,
                series_name="Inexistente",
                season=2026,
                valida_num=4,
            )
            assert ctx is None

    @pytest.mark.asyncio
    async def test_detect_returns_none_when_event_missing(
        self, seed_data, db_session_factory
    ):
        """Serie existe pero no hay event con sequence_number=valida_num → None."""
        async with db_session_factory() as session:
            ctx = await detect_revision(
                session,
                series_name="Copa Valle de Ciclomontañismo",
                season=2026,
                valida_num=4,
            )
            assert ctx is None

    @pytest.mark.asyncio
    async def test_detect_returns_none_when_no_committed_import(
        self, seed_data, db_session_factory
    ):
        """Event existe pero sin RaceImport committed → None (legacy / manual event)."""
        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1,
                sequence_number=4,
                name="Valida IV",
                event_date=datetime.now(timezone.utc).date(),
                location="Cali",
                created_by_user_id=10,
                status=RaceEventStatus.COMPLETED,
            )
            session.add(event)
            await session.commit()

            ctx = await detect_revision(
                session,
                series_name="Copa Valle de Ciclomontañismo",
                season=2026,
                valida_num=4,
            )
            assert ctx is None

    @pytest.mark.asyncio
    async def test_detect_returns_context_when_committed_exists(
        self, seed_data, db_session_factory
    ):
        """Caso happy: event + committed import → RevisionContext con metadata."""
        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1,
                sequence_number=4,
                name="Valida IV",
                event_date=datetime.now(timezone.utc).date(),
                location="Cali",
                created_by_user_id=10,
                status=RaceEventStatus.COMPLETED,
            )
            session.add(event)
            await session.commit()
            event_id = event.id

            committed = RaceImport(
                filename="prev.pdf",
                sha256="prev" * 16,
                series_id=1,
                status=RaceImportStatus.committed,
                stats_json={"results_inserted": 50},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                event_id=event_id,
            )
            session.add(committed)
            await session.commit()
            prev_id = committed.id

            ctx = await detect_revision(
                session,
                series_name="Copa Valle de Ciclomontañismo",
                season=2026,
                valida_num=4,
            )
            assert ctx is not None
            assert ctx.parent_event_id == event_id
            assert ctx.parent_import_id == prev_id
            assert ctx.parent_committed_by_user_id == 10
            assert ctx.n_results_persisted == 0  # sin RaceResult creados aún

    @pytest.mark.asyncio
    async def test_detect_returns_last_committed_when_multiple(
        self, seed_data, db_session_factory
    ):
        """Si hay múltiples committed para mismo event, retorna el más reciente
        (encadenamiento lineal — el "parent" de la próxima revisión es el último).
        """
        from datetime import timedelta

        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1,
                sequence_number=4,
                name="Valida IV",
                event_date=datetime.now(timezone.utc).date(),
                location="Cali",
                created_by_user_id=10,
                status=RaceEventStatus.COMPLETED,
            )
            session.add(event)
            await session.commit()
            event_id = event.id

            base_time = datetime.now(timezone.utc)
            older = RaceImport(
                filename="v1.pdf", sha256="v1" * 32, series_id=1,
                status=RaceImportStatus.committed, stats_json={},
                imported_by_user_id=10,
                imported_at=base_time - timedelta(days=1),
                kind=RaceImportKind.resultados, event_id=event_id,
            )
            newer = RaceImport(
                filename="v2.pdf", sha256="v2" * 32, series_id=1,
                status=RaceImportStatus.committed, stats_json={},
                imported_by_user_id=10,
                imported_at=base_time,
                kind=RaceImportKind.resultados, event_id=event_id,
            )
            session.add_all([older, newer])
            await session.commit()
            newer_id = newer.id

            ctx = await detect_revision(
                session,
                series_name="Copa Valle de Ciclomontañismo",
                season=2026,
                valida_num=4,
            )
            assert ctx is not None
            assert ctx.parent_import_id == newer_id

    @pytest.mark.asyncio
    async def test_detect_ignores_pending_imports(
        self, seed_data, db_session_factory
    ):
        """Solo cuentan los committed: un pending NO dispara detección revisión."""
        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1,
                sequence_number=4,
                name="Valida IV",
                event_date=datetime.now(timezone.utc).date(),
                location="Cali",
                created_by_user_id=10,
                status=RaceEventStatus.COMPLETED,
            )
            session.add(event)
            await session.commit()
            event_id = event.id

            pending = RaceImport(
                filename="pending.pdf", sha256="pe" * 32, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados, event_id=event_id,
            )
            session.add(pending)
            await session.commit()

            ctx = await detect_revision(
                session,
                series_name="Copa Valle de Ciclomontañismo",
                season=2026,
                valida_num=4,
            )
            assert ctx is None


# ---------------------------------------------------------------------------
# Tests endpoint POST /parse extendido (F-UP-REV2)
# ---------------------------------------------------------------------------


class TestStagingRevisionDetection:
    """Sucesor de ``TestParseEndpointRevisionDetection`` (amendment
    2026-09-26): ``POST /parse`` se retiró — ``stage_extracted_results`` se
    llama directamente. Solo expone ``is_revision``/``parent_import_id`` (no
    ``parent_event_id``/``parent_committed_at``/``parent_n_results`` — esos
    siguen probados contra ``detect_revision`` en ``TestDetectRevisionUnit``).
    El caso de dedupe por sha byte-exacto committed vive en
    ``tests/services/race/test_import_staging.py`` (T131)."""

    @pytest.mark.asyncio
    async def test_first_upload_is_not_a_revision(self, seed_data, db_session_factory, override_storage):
        """Documento nuevo sin previo committed → is_revision=false."""
        result = await _stage(db_session_factory, marker=b"first content xyz")
        assert result.is_revision is False
        assert result.parent_import_id is None

    @pytest.mark.asyncio
    async def test_revision_detection_when_committed_exists(
        self, seed_data, db_session_factory, override_storage
    ):
        """Si ya existe RaceEvent + committed import para (series, valida),
        un documento con SHA distinto marca is_revision=true."""
        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1,
                sequence_number=4,
                name="Valida IV Previa",
                event_date=datetime.now(timezone.utc).date(),
                location="Cali",
                created_by_user_id=10,
                status=RaceEventStatus.COMPLETED,
            )
            session.add(event)
            await session.commit()

            committed = RaceImport(
                filename="prev.pdf",
                sha256="cc" * 32,  # SHA distinto al que generaremos
                series_id=1,
                status=RaceImportStatus.committed,
                stats_json={"results_inserted": 100},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                event_id=event.id,
            )
            session.add(committed)
            await session.commit()
            prev_id = committed.id

        result = await _stage(
            db_session_factory,
            marker=b"REVISED CONTENT XYZ 123",
            valida_num=4,
            series_name="Copa Valle de Ciclomontañismo",
        )
        assert result.is_revision is True
        assert result.parent_import_id == prev_id

    @pytest.mark.asyncio
    async def test_revision_detection_for_different_valida(
        self, seed_data, db_session_factory, override_storage
    ):
        """Committed previo en valida=3, ahora un documento para valida=5 →
        no revisión. La detección debe matchear EXACTAMENTE el sequence_number."""
        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1, sequence_number=3,  # otro valida
                name="V3", event_date=datetime.now(timezone.utc).date(),
                location="Sevilla", created_by_user_id=10,
                status=RaceEventStatus.COMPLETED,
            )
            session.add(event)
            await session.commit()

            committed = RaceImport(
                filename="v3.pdf", sha256="v3" * 32, series_id=1,
                status=RaceImportStatus.committed, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados, event_id=event.id,
            )
            session.add(committed)
            await session.commit()

        result = await _stage(db_session_factory, marker=b"valida 5 content", valida_num=5)
        assert result.is_revision is False

    @pytest.mark.asyncio
    async def test_revision_ignores_pending_imports(self, seed_data, db_session_factory, override_storage):
        """Si hay event + pending (no committed), NO se considera revisión.

        Razón: el pending puede ser un wizard abandonado del mismo coach. Hasta
        que no haya committed, todo nuevo staging es "primer commit" lógico.
        """
        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1, sequence_number=4,
                name="V4 Pending", event_date=datetime.now(timezone.utc).date(),
                location="Cali", created_by_user_id=10,
                status=RaceEventStatus.COMPLETED,
            )
            session.add(event)
            await session.commit()

            pending = RaceImport(
                filename="pend.pdf", sha256="pp" * 32, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados, event_id=event.id,
            )
            session.add(pending)
            await session.commit()

        result = await _stage(db_session_factory, marker=b"new pending content")
        assert result.is_revision is False

    @pytest.mark.asyncio
    async def test_revision_succeeds_concurrent_uploads_gracefully(
        self, seed_data, db_session_factory, override_storage
    ):
        """Dos staging consecutivos sobre misma `(series, valida)` cuando
        ambos previo+actual son pending (ninguno committed) no revientan.
        Validamos que el segundo simplemente no se considera revisión."""
        result1 = await _stage(db_session_factory, marker=b"first parse a")
        assert result1.is_revision is False

        result2 = await _stage(db_session_factory, marker=b"second parse b")
        # Aún sin committed previo, el 2do staging tampoco es revisión.
        assert result2.is_revision is False
