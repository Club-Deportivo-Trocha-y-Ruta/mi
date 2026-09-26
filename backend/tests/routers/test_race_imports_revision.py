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

    from app.models.club import Club, ClubMember  # noqa: F401
    from app.models.race_competitor_signature import (  # noqa: F401
        RaceCompetitorSignature,
    )
    from app.models.race_identity_candidate import (  # noqa: F401
        RaceIdentityCandidate,
    )

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "race_series",
            "race_events",
            "race_imports",
            "race_import_staged_documents",
            "race_categories",
            "race_competitors",
            "race_competitor_signatures",
            "race_identity_candidates",
            "race_results",
            *AUDIT_TABLES,
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        # ``race_result_revisions.id`` es BigInteger en el modelo real —
        # SQLite solo activa el alias rowid/autoincrement con el token EXACTO
        # "INTEGER PRIMARY KEY" (mismo workaround documentado en
        # tests/services/race/test_ingestor_frozen_labels.py, T026): un DDL
        # crudo aparte, solo para este engine desechable — nunca se muta
        # ``Base.metadata`` compartido.
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


# ---------------------------------------------------------------------------
# T170 — endpoints /dry-run y /commit en la rama de revisión
# (contracts/revision-via-skill.md §"Dry-run, revision branch" / "Commit,
# revision branch"). A diferencia de las clases anteriores (que solo
# ejercitan detect_revision / stage_extracted_results), estos tests montan
# la app real vía httpx.AsyncClient — mismo patrón que
# ``tests/routers/test_race_imports_staged_rows.py``.
# ---------------------------------------------------------------------------

from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.race_category import RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeriesKind, RaceSeriesLevel
from app.services.race.import_staging import StageHeader, stage_extracted_results
from app.services.race.staged_document import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
    StagedProfileMeta,
)
from app.services.request_context import AuditContext

_IMPORTS_URL = "/api/race-analysis/imports"
_REVISION_VALIDA = 7


def _make_coach(user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Coach",
        last_name="Ten",
        email=f"coach{user_id}@test.local",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest_asyncio.fixture
async def revision_parent(seed_data, db_session_factory):
    """Evento padre COMMITTED con una fila persistida en INF_A — la base
    sobre la que las revisiones de este bloque corrigen/agregan/eliminan."""
    async with db_session_factory() as db:
        event = RaceEvent(
            id=1, series_id=1, sequence_number=_REVISION_VALIDA,
            name="Valida VII", event_date=datetime(2026, 6, 1).date(),
            location="Cali", created_by_user_id=10,
            status=RaceEventStatus.COMPLETED,
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
        competitor = RaceCompetitor(
            id=1, normalized_name="andres felipe rios", display_name="Andres Felipe Rios",
            club_text="Club Trocha y Ruta", city_text="Cali", sex=CompetitorSex.M,
            athlete_id=None,
        )
        db.add_all([event, category, parent_import, competitor])
        await db.flush()
        db.add(
            RaceCompetitorSignature(
                competitor_id=1, normalized_name="andres felipe rios",
                club_norm="club trocha y ruta", city_norm="cali",
                discriminator="", first_season=2026, last_season=2026,
            )
        )
        db.add(
            RaceResult(
                id=1, event_id=1, category_id=1, competitor_id=1, athlete_id=None,
                bib_number=101, position=1, status=ResultStatus.FINISHED,
                race_time_ms=20 * 60_000, points_awarded=50, created_by_user_id=10,
            )
        )
        await db.commit()
    yield


async def _stage_revision(
    db_session_factory,
    *,
    rows: list[ResultsRow],
    marker: bytes,
    header_code: str = "INF_A",
    header_raw: str = "INFANTIL A",
) -> int:
    """Staguea una revisión de ``revision_parent`` (misma serie/válida, SHA
    distinto) con filas a medida. Devuelve el ``import_id`` staged."""
    document = ParsedResults(
        categories=[ParsedCategory(header_raw=header_raw, code=header_code, rows=rows)],
        unreadable_rows=[],
    )
    header = StageHeader(
        series_name="Copa Valle de Ciclomontañismo",
        series_kind=RaceSeriesKind.cup,
        series_level=RaceSeriesLevel.departmental,
        season=2026,
        valida_num=_REVISION_VALIDA,
        event_name="VALIDA VII CALI",
        event_date=datetime(2026, 6, 1).date(),
        location="CALI",
    )
    profile = StagedProfileMeta(
        profile_id="test-race-imports-revision-t170",
        profile_sha256="4" * 64,
        engine_version="test-helper",
    )
    async with db_session_factory() as session:
        actor = await session.get(User, 10)
        result = await stage_extracted_results(
            session,
            document=document,
            profile=profile,
            file_bytes=_PDF_HEADER + marker,
            original_filename="revision.pdf",
            results_ext="pdf",
            header=header,
            actor=actor,
            ctx=AuditContext.for_user(actor, request_id="test-t170"),
        )
        await session.commit()
        assert result.is_revision is True
        return result.import_id


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, override_storage):
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_coach()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestRevisionDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_revision_diff_shape(
        self, revision_parent, db_session_factory, coach_client
    ):
        import_id = await _stage_revision(
            db_session_factory,
            marker=b"dry-run-update",
            rows=[
                ResultsRow(
                    position=1, bib="101", name="Andres Felipe Rios",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:19:50", points=50,
                ),
                ResultsRow(
                    position=2, bib="102", name="Nueva Persona Uno",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:21:00", points=45,
                ),
            ],
        )

        r = await coach_client.post(f"{_IMPORTS_URL}/{import_id}/dry-run")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_revision"] is True
        assert body["parent_event_id"] == 1
        assert body["diff_summary"]["n_update"] == 1
        assert body["diff_summary"]["n_create"] == 1
        assert body["diff_summary"]["n_delete"] == 0
        actions = {row["action"] for row in body["diff_rows"]}
        assert actions == {"update", "create"}
        assert all(row["action"] != "unchanged" for row in body["diff_rows"])


class TestRevisionCommit:
    async def _commit(self, coach_client, import_id: int, **body):
        return await coach_client.post(f"{_IMPORTS_URL}/{import_id}/commit", json=body)

    @pytest.mark.asyncio
    async def test_commit_without_reason_returns_422(
        self, revision_parent, db_session_factory, coach_client
    ):
        import_id = await _stage_revision(
            db_session_factory, marker=b"no-reason",
            rows=[
                ResultsRow(
                    position=1, bib="101", name="Andres Felipe Rios",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:19:50", points=50,
                ),
            ],
        )
        r = await self._commit(coach_client, import_id, resolved_matches=[])
        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_commit_applies_update_create_delete_and_writes_revisions(
        self, revision_parent, db_session_factory, coach_client
    ):
        import_id = await _stage_revision(
            db_session_factory,
            marker=b"full-apply",
            rows=[
                ResultsRow(
                    position=1, bib="101", name="Andres Felipe Rios",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:19:50", points=50,
                ),
                ResultsRow(
                    position=2, bib="102", name="Nueva Persona Uno",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:21:00", points=45,
                ),
            ],
        )

        r = await self._commit(
            coach_client, import_id,
            resolved_matches=[],
            revision_reason="official_correction",
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["race_event_id"] == 1
        assert body["n_results_inserted"] == 1  # 1 create
        assert body["pending_categories"] == []

        async with db_session_factory() as db:
            from sqlalchemy import select as _select

            results = (
                await db.execute(
                    _select(RaceResult).where(
                        RaceResult.event_id == 1, RaceResult.deleted_at.is_(None)
                    )
                )
            ).scalars().all()
            assert len(results) == 2  # el update (id=1) + el create nuevo.
            updated = next(r for r in results if r.id == 1)
            assert updated.race_time_ms == 19 * 60_000 + 50_000

            from app.models.race_result_revision import RaceResultRevision

            revisions = (
                await db.execute(_select(RaceResultRevision))
            ).scalars().all()
            actions = {rr.action.value for rr in revisions}
            assert actions == {"update", "create"}

            imp = await db.get(RaceImport, import_id)
            assert imp.status == RaceImportStatus.committed
            assert imp.parent_import_id == 900
            assert imp.revision_reason == "official_correction"

    @pytest.mark.asyncio
    async def test_commit_deletes_a_result_and_writes_delete_revision(
        self, revision_parent, db_session_factory, coach_client
    ):
        """El documento nuevo NO trae al competidor 101 — su fila persistida
        se elimina (soft-delete) con un ``RaceResultRevision`` `delete`."""
        import_id = await _stage_revision(
            db_session_factory,
            marker=b"delete-case",
            rows=[
                ResultsRow(
                    position=1, bib="200", name="Otra Persona Distinta",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:18:00", points=50,
                ),
            ],
        )

        r = await self._commit(
            coach_client, import_id,
            resolved_matches=[],
            revision_reason="result_removed",
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as db:
            deleted = await db.get(RaceResult, 1)
            assert deleted.deleted_at is not None
            # El status oficial NUNCA se toca en un soft-delete de revisión.
            assert deleted.status == ResultStatus.FINISHED

    @pytest.mark.asyncio
    async def test_commit_preserves_existing_athlete_link_on_update(
        self, revision_parent, db_session_factory, coach_client
    ):
        """Un ``athlete_id`` ya asignado por el coach NO se pisa al aplicar
        un update de revisión (contrato: los links de atleta nunca se
        reescriben en una revisión)."""
        async with db_session_factory() as db:
            result_obj = await db.get(RaceResult, 1)
            result_obj.athlete_id = 999
            await db.commit()

        import_id = await _stage_revision(
            db_session_factory,
            marker=b"athlete-link-survives",
            rows=[
                ResultsRow(
                    position=1, bib="101", name="Andres Felipe Rios",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:19:00", points=55,
                ),
            ],
        )
        r = await self._commit(
            coach_client, import_id,
            resolved_matches=[],
            revision_reason="timing_fix",
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as db:
            result_obj = await db.get(RaceResult, 1)
            assert result_obj.athlete_id == 999

    @pytest.mark.asyncio
    async def test_commit_deletes_the_staged_document(
        self, revision_parent, db_session_factory, coach_client
    ):
        import_id = await _stage_revision(
            db_session_factory,
            marker=b"doc-deleted",
            rows=[
                ResultsRow(
                    position=1, bib="101", name="Andres Felipe Rios",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:19:00", points=50,
                ),
            ],
        )
        r = await self._commit(
            coach_client, import_id,
            resolved_matches=[],
            revision_reason="timing_fix",
        )
        assert r.status_code == 200, r.text

        async with db_session_factory() as db:
            from sqlalchemy import select as _select

            from app.models.race_import_staged_document import (
                RaceImportStagedDocument,
            )

            row = (
                await db.execute(
                    _select(RaceImportStagedDocument).where(
                        RaceImportStagedDocument.import_id == import_id
                    )
                )
            ).scalar_one_or_none()
            assert row is None

    @pytest.mark.asyncio
    async def test_commit_invalidates_ai_runs_for_the_event(
        self, revision_parent, db_session_factory, coach_client, monkeypatch
    ):
        calls: list[int] = []

        async def _fake_invalidate(db, event_id):
            calls.append(event_id)

        import app.routers.race_imports as router_module

        monkeypatch.setattr(
            router_module, "invalidate_runs_for_event", _fake_invalidate
        )

        import_id = await _stage_revision(
            db_session_factory,
            marker=b"invalidate-runs",
            rows=[
                ResultsRow(
                    position=1, bib="101", name="Andres Felipe Rios",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:19:00", points=50,
                ),
            ],
        )
        r = await self._commit(
            coach_client, import_id,
            resolved_matches=[],
            revision_reason="timing_fix",
        )
        assert r.status_code == 200, r.text
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_commit_locked_event_returns_409(
        self, revision_parent, db_session_factory, coach_client, monkeypatch
    ):
        from sqlalchemy.exc import OperationalError

        import app.services.race.revision as revision_module

        async def _raise_locked(db, event_id):
            raise OperationalError("locked", None, None)

        monkeypatch.setattr(revision_module, "_acquire_event_lock", _raise_locked)

        import_id = await _stage_revision(
            db_session_factory,
            marker=b"event-locked",
            rows=[
                ResultsRow(
                    position=1, bib="101", name="Andres Felipe Rios",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:19:00", points=50,
                ),
            ],
        )
        r = await self._commit(
            coach_client, import_id,
            resolved_matches=[],
            revision_reason="timing_fix",
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "event_locked"

    @pytest.mark.asyncio
    async def test_commit_blocked_by_identity_gate_for_a_new_name(
        self, revision_parent, db_session_factory, coach_client, monkeypatch
    ):
        """Un nombre nuevo en la revisión que el candado de identidad
        (feature 045) todavía tiene `pending` bloquea el commit igual que en
        un import normal — se verifica que la rama de revisión invoca el
        MISMO `_identity_gate`, no un camino aparte que lo salte."""
        from app.services.race import identity_review as ir

        async def _fake_pending(db, keys):
            return [object()]  # cualquier candidato pending es suficiente.

        monkeypatch.setattr(ir, "pending_candidates_for_import", _fake_pending)

        import_id = await _stage_revision(
            db_session_factory,
            marker=b"identity-gate-new-name",
            rows=[
                ResultsRow(
                    position=1, bib="900", name="Nombre Totalmente Nuevo",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:18:30", points=50,
                ),
            ],
        )
        r = await self._commit(
            coach_client, import_id,
            resolved_matches=[],
            revision_reason="result_added",
        )
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["detail"] == "identity_pending"
        assert body["pending_for_import"] == 1

        # No debe haber aplicado nada — el import sigue pending.
        async with db_session_factory() as db:
            imp = await db.get(RaceImport, import_id)
            assert imp.status == RaceImportStatus.pending

    @pytest.mark.asyncio
    async def test_commit_incomplete_category_returns_409(
        self, revision_parent, db_session_factory, coach_client
    ):
        """Una categoría con un hueco en la numeración (sin reconocer) deja
        toda la revisión incompleta — sin revisión parcial (contrato)."""
        import_id = await _stage_revision(
            db_session_factory,
            marker=b"revision-incomplete",
            rows=[
                ResultsRow(
                    position=1, bib="101", name="Andres Felipe Rios",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:19:00", points=50,
                ),
                ResultsRow(
                    # Hueco: posición 3 sin la 2 — categoría inconsistente.
                    position=3, bib="103", name="Otra Persona Mas",
                    city="Cali", club="Club Trocha y Ruta",
                    time_raw="0:22:00", points=40,
                ),
            ],
        )
        r = await self._commit(
            coach_client, import_id,
            resolved_matches=[],
            revision_reason="position_fix",
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "revision_incomplete"
        assert "INFANTIL A" in r.json()["pending_categories"]

        async with db_session_factory() as db:
            imp = await db.get(RaceImport, import_id)
            assert imp.status == RaceImportStatus.pending
