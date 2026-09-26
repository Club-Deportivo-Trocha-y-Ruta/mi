"""CLI ``scripts/race_results.py`` (amendment 2026-09-26, T143).

``contracts/results-skill-cli.md`` § Tests. Corre enteramente sobre
aiosqlite (``app.database.AsyncSessionLocal``/``engine`` monkeypatchados) y
el storage local de respaldo — nunca toca MySQL ni una red real. Cada PDF
es sintético (``tests/helpers/results_pdf_builder``, ``FakeNameGenerator``)
y vive en ``tmp_path`` (fuera del repositorio).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import scripts.race_results as cli
from app.models import Base
from app.models.race_event import RaceEvent
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries, RaceSeriesKind, RaceSeriesLevel
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.name_sweep import assert_no_fake_names
from tests.helpers.results_pdf_builder import (
    FakeNameGenerator,
    build_results_pdf,
    sequential_category,
)

_TABLES = (
    "users",
    "race_series",
    "race_events",
    "race_imports",
    "race_import_staged_documents",
    "race_categories",
    "race_results",
    "race_competitors",
    "race_competitor_signatures",
    *AUDIT_TABLES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine(tmp_path) -> AsyncEngine:
    """Archivo sqlite en ``tmp_path`` (no ``:memory:`` + ``StaticPool``): el
    CLI abre su propio event loop por subcomando (``asyncio.run`` en
    ``cmd_stage``/``cmd_compare``, igual que el proceso real), y una
    conexión ``:memory:`` compartida entre loops distintos revienta con
    ``MissingGreenlet``. Un archivo permite que cada ``asyncio.run`` abra su
    propia conexión nueva contra los mismos datos."""
    import asyncio

    db_path = tmp_path / "race_results_cli.sqlite3"
    tables = [Base.metadata.tables[t] for t in _TABLES]

    async def _create() -> None:
        setup_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
        async with setup_engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await setup_engine.dispose()

    asyncio.run(_create())

    # ``NullPool``: cada checkout abre una conexión aiosqlite nueva, así
    # que ningún checkout queda atado al event loop que estaba activo
    # cuando se abrió — necesario porque `cmd_stage`/`cmd_compare` corren
    # su propio `asyncio.run()` (igual que el proceso real del CLI),
    # distinto del loop de sesión de pytest-asyncio que usan las demás
    # fixtures de este archivo.
    return create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True, poolclass=NullPool)


@pytest.fixture(autouse=True)
def local_target(sqlite_engine, monkeypatch):
    """Hace que ``resolve_target(None|'local', ...)`` apunte al aiosqlite
    de este test, en vez de a la base real de ``app.database``."""
    import app.database as database_module
    from app.config import settings

    factory = async_sessionmaker(sqlite_engine, expire_on_commit=False)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(database_module, "engine", sqlite_engine)
    monkeypatch.setattr(settings, "app_env", "development", raising=False)
    monkeypatch.setattr(settings, "mysql_host", "localhost", raising=False)
    monkeypatch.setattr(settings, "mysql_db", "trocha_ruta_test_cli", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_host", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_user", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "", raising=False)
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "", raising=False)


@pytest.fixture(autouse=True)
def local_storage(monkeypatch, tmp_path):
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-cli-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/media/local")


async def _make_user(session_factory, *, id_: int, role: UserRole, is_active: bool = True) -> None:
    async with session_factory() as session:
        session.add(
            User(
                id=id_,
                email=f"user{id_}@test.com",
                hashed_password="x",
                first_name="Test",
                last_name=str(id_),
                role=role,
                is_active=is_active,
                can_login=(role != UserRole.athlete),
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


@pytest.fixture
def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def coach_user(db_session_factory) -> None:
    import asyncio

    asyncio.run(_make_user(db_session_factory, id_=10, role=UserRole.coach))


# ---------------------------------------------------------------------------
# Helpers de archivo/manifiesto
# ---------------------------------------------------------------------------


def _build_pdf(tmp_path: Path, *, name: str = "valida", valida_num: int = 3, n_rows: int = 4) -> Path:
    out = tmp_path / f"{name}.pdf"
    build_results_pdf(
        out,
        valida_num=valida_num,
        location="Ciudad Ficticia",
        event_date=date(2026, 3, 1),
        categories=[sequential_category("INFANTIL A", n_rows)],
        name_generator=FakeNameGenerator(),
        layout="historical",
    )
    return out


def _write_manifest(tmp_path: Path, *, valida_num: int = 3, name: str = "manifest") -> Path:
    import json

    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "series_name": "Copa Valle CLI Test",
                "series_kind": "cup",
                "series_level": "departmental",
                "season": 2026,
                "valida_num": valida_num,
                "event_name": f"Válida {valida_num} CLI",
                "event_date": "2026-03-01",
                "location": "Ciudad Ficticia",
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


async def _count(session_factory, model) -> int:
    from sqlalchemy import func

    async with session_factory() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_mask_profile_check_apply_stage(self, tmp_path, capsys, db_session_factory):
        pdf_path = _build_pdf(tmp_path)
        manifest_path = _write_manifest(tmp_path)

        assert cli.main(["mask", "--file", str(pdf_path)]) == 0
        run_dir = _find_run_dir(tmp_path, capsys)
        assert (run_dir / "masked" / "view.txt").exists()
        assert (run_dir / "private" / "source.json").exists()

        assert cli.main(["profile-check", "--profile", "copa-valle-results-pdf"]) == 0
        capsys.readouterr()

        assert (
            cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"]) == 0
        )
        out = capsys.readouterr()
        assert "fuga: 0" in out.out
        assert (run_dir / "private" / "document.json").exists()

        exit_code = cli.main(
            [
                "stage",
                "--run",
                str(run_dir),
                "--manifest",
                str(manifest_path),
                "--user-id",
                "10",
            ]
        )
        out = capsys.readouterr()
        assert exit_code == 0, out.err
        assert "import_id:" in out.out
        assert "/competitions/import?import=" in out.out

    def test_dry_writes_nothing(self, tmp_path, capsys, db_session_factory):
        pdf_path = _build_pdf(tmp_path, name="dry")
        manifest_path = _write_manifest(tmp_path, valida_num=4, name="dry-manifest")

        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        before = _import_count = None

        async def _counts():
            return (
                await _count(db_session_factory, RaceImport),
                await _count(db_session_factory, RaceSeries),
            )

        import asyncio

        before = asyncio.run(_counts())
        exit_code = cli.main(
            [
                "stage",
                "--run",
                str(run_dir),
                "--manifest",
                str(manifest_path),
                "--user-id",
                "10",
                "--dry",
            ]
        )
        after = asyncio.run(_counts())
        assert exit_code == 0
        assert before == after


# ---------------------------------------------------------------------------
# Local guard
# ---------------------------------------------------------------------------


class TestLocalGuard:
    def test_remote_mysql_host_refused(self, tmp_path, capsys, db_session_factory, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "mysql_host", "203.0.113.9", raising=False)
        pdf_path = _build_pdf(tmp_path, name="remote")
        manifest_path = _write_manifest(tmp_path, valida_num=5, name="remote-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        exit_code = cli.main(
            ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "10"]
        )
        assert exit_code == 9

    def test_app_env_production_refused(self, tmp_path, capsys, db_session_factory, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "app_env", "production", raising=False)
        pdf_path = _build_pdf(tmp_path, name="prodenv")
        manifest_path = _write_manifest(tmp_path, valida_num=6, name="prodenv-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        exit_code = cli.main(
            ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "10"]
        )
        assert exit_code == 9


class TestProductionGuard:
    def test_missing_confirm_refused(self, tmp_path, capsys, db_session_factory):
        pdf_path = _build_pdf(tmp_path, name="prod1")
        manifest_path = _write_manifest(tmp_path, valida_num=7, name="prod1-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        exit_code = cli.main(
            [
                "stage",
                "--run",
                str(run_dir),
                "--manifest",
                str(manifest_path),
                "--user-id",
                "10",
                "--target",
                "production",
            ]
        )
        # Sin .env.production real en este checkout, el rechazo llega por
        # archivo ausente — igualmente exit 9 (target_refused), como pide
        # el contrato para todo rechazo de destino salvo el de cabeza de
        # Alembic (exit 11, cubierto en test_target.py con env sintético).
        assert exit_code == 9


# ---------------------------------------------------------------------------
# Actor
# ---------------------------------------------------------------------------


class TestActor:
    @pytest.mark.parametrize(
        "role", [UserRole.parent, UserRole.athlete]
    )
    def test_wrong_role_refused(self, tmp_path, capsys, db_session_factory, role):
        import asyncio

        asyncio.run(_make_user(db_session_factory, id_=20, role=role))
        pdf_path = _build_pdf(tmp_path, name=f"actor-{role.value}")
        manifest_path = _write_manifest(tmp_path, valida_num=8, name=f"actor-{role.value}-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        exit_code = cli.main(
            ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "20"]
        )
        assert exit_code == 10

    def test_inactive_actor_refused(self, tmp_path, capsys, db_session_factory):
        import asyncio

        asyncio.run(_make_user(db_session_factory, id_=21, role=UserRole.coach, is_active=False))
        pdf_path = _build_pdf(tmp_path, name="inactive")
        manifest_path = _write_manifest(tmp_path, valida_num=9, name="inactive-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        exit_code = cli.main(
            ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "21"]
        )
        assert exit_code == 10

    def test_unknown_actor_refused(self, tmp_path, capsys, db_session_factory):
        pdf_path = _build_pdf(tmp_path, name="unknown")
        manifest_path = _write_manifest(tmp_path, valida_num=10, name="unknown-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        exit_code = cli.main(
            ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "999"]
        )
        assert exit_code == 10


# ---------------------------------------------------------------------------
# Duplicados
# ---------------------------------------------------------------------------


class TestDuplicates:
    def test_same_file_staged_twice_gives_one_import(self, tmp_path, capsys, db_session_factory):
        pdf_path = _build_pdf(tmp_path, name="dup")
        manifest_path = _write_manifest(tmp_path, valida_num=11, name="dup-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        args = ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "10"]
        first = cli.main(args)
        out1 = capsys.readouterr().out
        second = cli.main(args)
        out2 = capsys.readouterr().out
        assert first == 0
        assert second == 0

        import_ids = set()
        for out in (out1, out2):
            for line in out.splitlines():
                if line.startswith("import_id: "):
                    import_ids.add(line.split(": ", 1)[1])
        assert len(import_ids) == 1

        import asyncio

        n_imports = asyncio.run(_count(db_session_factory, RaceImport))
        assert n_imports == 1

    def test_committed_same_file_exits_8(self, tmp_path, capsys, db_session_factory):
        import asyncio

        pdf_path = _build_pdf(tmp_path, name="committed")
        manifest_path = _write_manifest(tmp_path, valida_num=12, name="committed-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        args = ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "10"]
        cli.main(args)
        capsys.readouterr()

        async def _mark_committed():
            async with db_session_factory() as session:
                imp = (await session.execute(select(RaceImport))).scalars().first()
                imp.status = RaceImportStatus.committed
                await session.commit()

        asyncio.run(_mark_committed())

        exit_code = cli.main(args)
        assert exit_code == 8


# ---------------------------------------------------------------------------
# Revisión — guarda ON (T147, T150)
# ---------------------------------------------------------------------------


class TestRevisionGuard:
    def test_different_reading_of_committed_valida_stages_a_revision(
        self, tmp_path, capsys, db_session_factory
    ):
        import asyncio

        async def _seed_committed_valida():
            async with db_session_factory() as session:
                series = RaceSeries(
                    name="Copa Valle CLI Test",
                    season_year=2026,
                    kind=RaceSeriesKind.cup,
                    level=RaceSeriesLevel.departmental,
                    points_scheme_code="copa_valle_2026",
                )
                session.add(series)
                await session.flush()
                event = RaceEvent(
                    series_id=series.id,
                    sequence_number=12,
                    name="Válida 12 CLI",
                    event_date=date(2026, 3, 1),
                    location="Ciudad Ficticia",
                    created_by_user_id=10,
                )
                session.add(event)
                await session.flush()
                parent_import = RaceImport(
                    filename="parent.pdf",
                    original_filename="parent.pdf",
                    sha256="0" * 64,
                    series_id=series.id,
                    event_id=event.id,
                    status=RaceImportStatus.committed,
                    stats_json={},
                    imported_by_user_id=10,
                    kind=RaceImportKind.resultados,
                    storage_path="/tmp/parent.pdf",
                    storage_url="/media/parent.pdf",
                    parse_meta_json={},
                )
                session.add(parent_import)
                await session.commit()
                return parent_import.id

        parent_import_id = asyncio.run(_seed_committed_valida())

        pdf_path = _build_pdf(tmp_path, name="revision", valida_num=12)
        manifest_path = _write_manifest(tmp_path, valida_num=12, name="revision-manifest")
        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        capsys.readouterr()

        # T175 (amendment 2026-09-26): la fase de revisiones ya existe
        # (T173/T174) — el guardia `revision_not_available` se apagó. Una
        # lectura distinta de una válida ya commiteada se stagea como
        # revisión (exit 0), lista para dry-run/commit en la app.
        exit_code = cli.main(
            ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "10"]
        )
        out = capsys.readouterr()
        assert exit_code == 0
        assert "status: pending" in out.out
        assert f"revisión de la importación #{parent_import_id}" in out.out
        assert "revision_not_available" not in out.out

        n_imports = asyncio.run(_count(db_session_factory, RaceImport))
        assert n_imports == 2  # el padre sembrado + la revisión recién stageada.


# ---------------------------------------------------------------------------
# Archivos rechazados
# ---------------------------------------------------------------------------


class TestFileRefusals:
    def test_file_inside_repo_refused(self, capsys):
        in_repo_file = Path(__file__).resolve().parents[1] / "fixtures" / "race" / "does-not-matter.pdf"
        exit_code = cli.main(["mask", "--file", str(in_repo_file)])
        assert exit_code == 2

    def test_scanned_pdf_refused(self, tmp_path):
        minimal_pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
        )
        pdf_path = tmp_path / "scanned.pdf"
        pdf_path.write_bytes(minimal_pdf)
        exit_code = cli.main(["mask", "--file", str(pdf_path)])
        assert exit_code == 4


# ---------------------------------------------------------------------------
# Barrido de nombres — stdout/stderr/report.json de cada subcomando
# ---------------------------------------------------------------------------


class TestStdoutSweep:
    def test_no_fake_name_in_any_output(self, tmp_path, capsys, db_session_factory):
        import json as json_module

        gen = FakeNameGenerator()
        pdf_path = tmp_path / "sweep.pdf"
        build_results_pdf(
            pdf_path,
            valida_num=12,
            location="Ciudad Ficticia",
            event_date=date(2026, 3, 1),
            categories=[sequential_category("INFANTIL A", 5)],
            name_generator=gen,
            layout="historical",
        )
        manifest_path = _write_manifest(tmp_path, valida_num=12, name="sweep-manifest")

        cli.main(["mask", "--file", str(pdf_path)])
        run_dir = _find_run_dir(tmp_path, capsys)
        out = capsys.readouterr()
        assert_no_fake_names(out.out, gen)
        assert_no_fake_names((run_dir / "masked" / "view.txt").read_text(encoding="utf-8"), gen)
        assert_no_fake_names((run_dir / "report.json").read_text(encoding="utf-8"), gen)

        cli.main(["apply", "--run", str(run_dir), "--profile", "copa-valle-results-pdf"])
        out = capsys.readouterr()
        assert_no_fake_names(out.out, gen)
        assert_no_fake_names((run_dir / "report.json").read_text(encoding="utf-8"), gen)

        cli.main(
            ["stage", "--run", str(run_dir), "--manifest", str(manifest_path), "--user-id", "10"]
        )
        out = capsys.readouterr()
        assert_no_fake_names(out.out, gen)
        assert_no_fake_names(out.err, gen)
        report_path = run_dir / "report.json"
        if report_path.exists():
            assert_no_fake_names(report_path.read_text(encoding="utf-8"), gen)
        _ = json_module  # placeholder si se necesita inspeccionar el JSON a futuro


class TestApplyReportNeverPrintsHeaderText:
    """B1 (privacy-audit.md §4): a too-broad header rule can turn a rider row into a
    'category header'. Its text must never reach the apply stdout the LLM reads."""

    def test_unrecognised_and_recognised_headers_are_not_printed(self):
        from app.services.race.staged_document import (
            ParsedCategory,
            ParsedResults,
            ResultsRow,
        )

        gen = FakeNameGenerator(seed=7)
        rider = gen.next_name()
        row = ResultsRow(position=1, bib="101", name=gen.next_name(), city="Ciudad Ficticia",
                         club="Club Ficticio Uno", time_raw="1:02:03", points=150)
        document = ParsedResults(categories=[
            ParsedCategory(header_raw=rider, code=None, rows=[row]),
            ParsedCategory(header_raw="PREJUVENIL A DAMAS", code="PJUV_A_F", rows=[row]),
        ])

        text = "\n".join(cli._document_report_lines(document))

        assert rider not in text
        assert "PREJUVENIL A DAMAS" not in text
        assert "⟨no reconocida #1⟩" in text
        assert "code=PJUV_A_F" in text
        assert_no_fake_names(text, gen)
