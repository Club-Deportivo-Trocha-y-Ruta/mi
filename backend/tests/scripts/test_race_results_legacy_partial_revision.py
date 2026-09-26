"""G14 sign-off scenario (amendment 2026-09-26, tasks.md T176): "one legacy
partial commit completed through a revision on the local stack, with a
builder file".

End to end, on the local stack (no HTTP upload — the CLI is the only entry
point per FR-044):

1. A válida was committed through the OLD upload flow with one category
   left out (``pending_categories``, R-27) — simulated directly as a
   ``RaceImport`` committed row with no staged document (legacy), exactly
   the shape ``test_race_imports_legacy.py`` (T134) already proves triggers
   ``409 restage_required`` on any of the old resume routes.
2. The operator re-stages the whole válida with the skill/CLI
   (``scripts/race_results.py mask`` → ``apply`` → ``stage --target
   local``), from a REAL synthetic PDF built with
   ``tests/helpers/results_pdf_builder.py`` — never a real official file.
   The new document carries both the already-committed category (same
   rows, unchanged) and the category that was missing.
3. The CLI reports the staged import as a revision (exit 0, "revisión de
   la importación #<parent>").
4. The coach reviews and commits in the local app (dry-run + commit
   through the real router, in-process): the missing category's rows come
   out ``create``, the already-committed category's rows come out
   ``unchanged`` (the reading matches) — exactly the contract's §"Legacy
   partial commits (R-27)" promise.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.race_category import RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_competitor_signature import RaceCompetitorSignature
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.results_pdf_builder import CategorySpec, RowSpec, build_results_pdf

import scripts.race_results as cli

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "race_series",
    "race_events",
    "race_imports",
    "race_import_staged_documents",
    "race_categories",
    "race_results",
    "race_competitors",
    "race_competitor_signatures",
    "race_identity_candidates",
    *AUDIT_TABLES,
)

_VALIDA_NUM = 6
_SERIES_NAME = "Copa Valle CLI Legacy Test"
_PARENT_EVENT_ID = 1
_PARENT_IMPORT_ID = 900


@pytest.fixture
def sqlite_engine(tmp_path) -> AsyncEngine:
    import asyncio

    from app.models.club import Club, ClubMember  # noqa: F401
    from app.models.race_identity_candidate import RaceIdentityCandidate  # noqa: F401

    db_path = tmp_path / "race_results_legacy_revision.sqlite3"
    tables = [Base.metadata.tables[t] for t in _TABLES]

    async def _create() -> None:
        setup_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
        async with setup_engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
            # ``race_result_revisions.id`` es BigInteger en el modelo real —
            # SQLite solo activa el alias rowid/autoincrement con el token
            # EXACTO "INTEGER PRIMARY KEY" (mismo workaround que
            # tests/services/race/test_ingestor_frozen_labels.py, T026, y
            # tests/routers/test_race_imports_revision.py, T170).
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
        await setup_engine.dispose()

    asyncio.run(_create())
    return create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, poolclass=NullPool)


@pytest.fixture
def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def local_target(sqlite_engine, monkeypatch):
    """Igual patrón que ``test_race_results_cli.py``: el CLI (``--target
    local``, default) debe leer/escribir sobre este mismo aiosqlite."""
    import app.database as database_module
    from app.config import settings

    factory = async_sessionmaker(sqlite_engine, expire_on_commit=False)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(database_module, "engine", sqlite_engine)
    monkeypatch.setattr(settings, "app_env", "development", raising=False)
    monkeypatch.setattr(settings, "mysql_host", "localhost", raising=False)
    monkeypatch.setattr(settings, "mysql_db", "trocha_ruta_test_cli_legacy", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_host", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_user", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "", raising=False)


@pytest.fixture(autouse=True)
def local_storage(monkeypatch, tmp_path):
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-cli-legacy-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/media/local")


async def _seed_legacy_partial_commit(db_session_factory) -> None:
    """Válida VI: committed por el flujo viejo con INFANTIL A adentro y
    JUVENIL A afuera (``pending_categories`` — sin documento stageado, el
    caso legacy que ``test_race_imports_legacy.py`` ya cubre para los
    endpoints de resume)."""
    async with db_session_factory() as db:
        coach = User(
            id=10, email="coach@test.com", hashed_password="x",
            first_name="Coach", last_name="Legacy", role=UserRole.coach,
            is_active=True, can_login=True, created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name=_SERIES_NAME, season_year=2026,
            kind=RaceSeriesKind.cup, level=RaceSeriesLevel.departmental,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        event = RaceEvent(
            id=_PARENT_EVENT_ID, series_id=1, sequence_number=_VALIDA_NUM,
            name=f"Valida {_VALIDA_NUM} legacy", event_date=date(2026, 4, 1),
            location="Cali", created_by_user_id=10, status=RaceEventStatus.COMPLETED,
        )
        cat_inf_a = RaceCategory(
            id=1, code="INF_A", label="Infantil A", sex=CompetitorSex.M,
            age_min=10, age_max=11, tier="menores", sort_order=1, is_active=True,
        )
        cat_juv_a = RaceCategory(
            id=2, code="PJUV_A", label="Prejuvenil A", sex=CompetitorSex.M,
            age_min=15, age_max=16, tier="menores", sort_order=2, is_active=True,
        )
        legacy_import = RaceImport(
            id=_PARENT_IMPORT_ID, filename="legacy_v6.pdf", original_filename="legacy_v6.pdf",
            sha256="l" * 64, series_id=1, event_id=_PARENT_EVENT_ID,
            status=RaceImportStatus.committed, stats_json={"results_inserted": 1},
            imported_by_user_id=10, imported_at=datetime.now(timezone.utc),
            kind=RaceImportKind.resultados,
            # El meta legacy quedaba con esta categoría anotada como
            # pendiente — sin documento stageado (no staged_document row).
            parse_meta_json={"pending_categories": ["PREJUVENIL A"]},
        )
        competitor = RaceCompetitor(
            id=1, normalized_name="andres felipe rios", display_name="Andres Felipe Rios",
            club_text="Club Ejemplo", city_text="Cali", sex=CompetitorSex.M,
            athlete_id=None,
        )
        db.add_all([coach, series, event, cat_inf_a, cat_juv_a, legacy_import, competitor])
        await db.flush()
        db.add(
            RaceCompetitorSignature(
                competitor_id=1, normalized_name="andres felipe rios",
                club_norm="club ejemplo", city_norm="cali",
                discriminator="", first_season=2026, last_season=2026,
            )
        )
        db.add(
            RaceResult(
                id=1, event_id=_PARENT_EVENT_ID, category_id=1, competitor_id=1,
                athlete_id=None, bib_number=101, position=1,
                status=ResultStatus.FINISHED, race_time_ms=18 * 60_000,
                points_awarded=50, created_by_user_id=10,
                imported_from_id=_PARENT_IMPORT_ID,
            )
        )
        await db.commit()


def _build_full_pdf(tmp_path: Path) -> Path:
    """PDF sintético con las DOS categorías: INFANTIL A repite la MISMA fila
    ya committed (nombre/dorsal/tiempo idénticos → sale `unchanged`) y
    JUVENIL A trae la categoría que faltaba (sale `create`)."""
    out = tmp_path / "valida_vi_completa.pdf"
    inf_a = CategorySpec(
        header="INFANTIL A",
        rows=[
            RowSpec(
                position=1, bib="101", name="Andres Felipe Rios",
                city="Cali", club="Club Ejemplo",
                time_raw="0:18:00", points=50,
            ),
        ],
    )
    juv_a = CategorySpec(
        header="PREJUVENIL A",
        rows=[
            RowSpec(
                position=1, bib="201", name="Camila Andrea Torres",
                city="Cali", club="Club Ejemplo",
                time_raw="0:35:00", points=50,
            ),
        ],
    )
    build_results_pdf(
        out,
        valida_num=_VALIDA_NUM,
        location="Cali",
        event_date=date(2026, 4, 1),
        categories=[inf_a, juv_a],
        layout="historical",
    )
    return out


def _write_manifest(tmp_path: Path) -> Path:
    import json

    path = tmp_path / "legacy-revision-manifest.json"
    path.write_text(
        json.dumps(
            {
                "series_name": _SERIES_NAME,
                "series_kind": "cup",
                "series_level": "departmental",
                "season": 2026,
                "valida_num": _VALIDA_NUM,
                "event_name": f"Válida {_VALIDA_NUM} completa",
                "event_date": "2026-04-01",
                "location": "Cali",
            }
        ),
        encoding="utf-8",
    )
    return path


def _find_run_dir(tmp_path: Path, capsys) -> Path:
    out = capsys.readouterr()
    for line in out.out.splitlines():
        if line.startswith("run: "):
            return Path(line.split("run: ", 1)[1])
    raise AssertionError(f"no se encontró 'run: ' en stdout:\n{out.out}")


def _make_coach() -> SimpleNamespace:
    return SimpleNamespace(
        id=10, first_name="Coach", last_name="Legacy",
        email="coach@test.com", role=UserRole.coach,
        can_login=True, is_active=True, club_memberships=[],
    )


def test_legacy_partial_commit_completed_through_a_revision(
    tmp_path, capsys, db_session_factory
):
    """No es ``async def``: ``cli.main`` corre su propio ``asyncio.run()``
    internamente (igual que el proceso real) — un test ``async def`` ya
    tendría un loop activo (pytest-asyncio) y ``asyncio.run()`` anidado
    revienta. La parte async (revisar/comitear vía httpx) se aísla en
    ``_review_and_commit`` y se corre con su propio ``asyncio.run()``,
    igual patrón que ``test_race_results_cli.py``."""
    import asyncio

    asyncio.run(_seed_legacy_partial_commit(db_session_factory))

    # 1. El CLI stagea la válida completa como REVISIÓN de la carga legacy.
    pdf_path = _build_full_pdf(tmp_path)
    manifest_path = _write_manifest(tmp_path)

    assert cli.main(["mask", "--file", str(pdf_path)]) == 0
    run_dir = _find_run_dir(tmp_path, capsys)
    assert cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"]) == 0
    capsys.readouterr()

    exit_code = cli.main(
        ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "10"]
    )
    out = capsys.readouterr()
    assert exit_code == 0, out.err
    assert f"revisión de la importación #{_PARENT_IMPORT_ID}" in out.out
    assert "import_id:" in out.out
    revision_import_id = int(
        next(
            line.split("import_id: ", 1)[1]
            for line in out.out.splitlines()
            if line.startswith("import_id:")
        )
    )

    # 2. El coach revisa (dry-run) y comitea en la app local — router real,
    #    in-process, sin HTTP real hacia afuera. Loop propio (ver docstring
    #    de la función): cmd_stage arriba ya cerró el suyo.
    asyncio.run(_review_and_commit(db_session_factory, revision_import_id))

    # 3. La categoría que faltaba ya tiene su resultado; la que ya estaba
    #    committed sigue exactamente igual (unchanged, no se duplicó).
    asyncio.run(_assert_final_state(db_session_factory, revision_import_id))


async def _review_and_commit(db_session_factory, revision_import_id: int) -> None:
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
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            dry = await client.post(
                f"/api/race-analysis/imports/{revision_import_id}/dry-run"
            )
            assert dry.status_code == 200, dry.text
            dry_body = dry.json()
            assert dry_body["is_revision"] is True
            assert dry_body["parent_event_id"] == _PARENT_EVENT_ID
            assert dry_body["diff_summary"]["n_create"] == 1  # JUVENIL A
            assert dry_body["diff_summary"]["n_unchanged"] == 1  # INFANTIL A
            assert dry_body["diff_summary"]["n_update"] == 0
            assert dry_body["diff_summary"]["n_delete"] == 0

            commit = await client.post(
                f"/api/race-analysis/imports/{revision_import_id}/commit",
                json={"resolved_matches": [], "revision_reason": "result_added"},
            )
            assert commit.status_code == 200, commit.text
            commit_body = commit.json()
            assert commit_body["race_event_id"] == _PARENT_EVENT_ID
            assert commit_body["n_results_inserted"] == 1
    finally:
        app.dependency_overrides.clear()


async def _assert_final_state(db_session_factory, revision_import_id: int) -> None:
    async with db_session_factory() as db:
        results = (
            await db.execute(
                select(RaceResult).where(RaceResult.event_id == _PARENT_EVENT_ID)
            )
        ).scalars().all()
        assert len(results) == 2
        juv_result = next(r for r in results if r.category_id == 2)
        assert juv_result.bib_number == 201
        inf_result = next(r for r in results if r.category_id == 1)
        assert inf_result.id == 1  # el mismo RaceResult de siempre, no un duplicado.

        revision_imp = await db.get(RaceImport, revision_import_id)
        assert revision_imp.status == RaceImportStatus.committed
        assert revision_imp.parent_import_id == _PARENT_IMPORT_ID
