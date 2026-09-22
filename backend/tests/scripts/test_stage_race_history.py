"""Tests de ``scripts/stage_race_history.py`` (feature 044, US5, T063).

Cubre exactamente lo que pide ``contracts/historical-load.md`` §"Script":
- Se niega a leer un manifiesto o un archivo referenciado que resuelva
  DENTRO del repositorio.
- Se niega a stagear un ``general_file`` explícito o un archivo cuyo
  nombre sugiere el acumulado GENERAL de la Liga (FR-024).
- ``--dry`` no stagea nada (cero filas nuevas en ``race_imports``).
- La salida (stdout) nunca contiene un nombre — barrido con regex contra
  los nombres que ``FakeNameGenerator`` generó para el PDF de prueba.

``AsyncSessionLocal`` se parchea al motor aiosqlite del test — el script en
producción apunta a la base real vía ``app.database`` (mismo patrón que
otros scripts del repo).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_category import RaceCategory
from app.models.race_import import RaceImport
from app.models.user import User, UserRole
from scripts import stage_race_history as script
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.results_pdf_builder import FakeNameGenerator, build_results_pdf, sequential_category
from tests.services.race.conftest import _SEED_CATEGORIES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
            "race_imports",
            "race_categories",
            *AUDIT_TABLES,
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session_factory(sqlite_engine):
    factory = async_sessionmaker(sqlite_engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            User(
                id=10, email="coach10@test.com", hashed_password="x",
                first_name="Coach", last_name="Ten",
                role=UserRole.coach, is_active=True, can_login=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        for code, label, sex, age_min, age_max, tier, sort_order in _SEED_CATEGORIES:
            session.add(
                RaceCategory(
                    code=code, label=label, sex=sex, age_min=age_min,
                    age_max=age_max, tier=tier, sort_order=sort_order,
                    is_active=True,
                )
            )
        await session.commit()
    return factory


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
    from app.config import settings
    from app.services.training import storage_sftp

    fake_base = tmp_path / "uploads-test"
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_BASE", fake_base)
    monkeypatch.setattr(storage_sftp, "_LOCAL_FALLBACK_URL_PREFIX", "/static/uploads/test")
    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield fake_base


@pytest.fixture
def patched_session_local(monkeypatch, seeded_session_factory):
    monkeypatch.setattr(script, "AsyncSessionLocal", seeded_session_factory)
    return seeded_session_factory


def _write_manifest(tmp_path: Path, entries: list[dict]) -> Path:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(entries), encoding="utf-8")
    return manifest_path


def _build_pdf_outside_repo(tmp_path: Path, *, name_generator: FakeNameGenerator) -> Path:
    cat = sequential_category("INFANTIL A", 2)
    return build_results_pdf(
        tmp_path / "valida_historica.pdf",
        valida_num=3, location="Palmira", event_date=date(2024, 6, 14),
        categories=[cat], name_generator=name_generator,
    )


# ---------------------------------------------------------------------------
# Rutas dentro del repo — refuse
# ---------------------------------------------------------------------------


class TestRefusesInRepoPaths:
    def test_manifest_inside_repo_is_refused(self):
        with pytest.raises(script.ManifestError, match="repositorio"):
            script._load_manifest(Path(__file__))

    def test_file_inside_repo_is_refused(self, tmp_path):
        in_repo_file = Path(__file__).parent / "test_stage_race_history.py"
        manifest = _write_manifest(tmp_path, [
            {
                "season": 2024, "valida_num": 3, "event_date": "2024-06-14",
                "location": "Palmira", "event_name": "VALIDA III PALMIRA",
                "file": str(in_repo_file),
            }
        ])
        entries = script._load_manifest(manifest)
        with pytest.raises(script.ManifestError, match="repositorio"):
            script._assert_outside_repo(Path(entries[0]["file"]), what="test")


# ---------------------------------------------------------------------------
# FR-024 — GENERAL nunca se acepta
# ---------------------------------------------------------------------------


class TestRefusesGeneralFiles:
    def test_general_file_key_is_rejected(self):
        entry = {
            "season": 2024, "valida_num": 3, "event_date": "2024-06-14",
            "location": "Palmira", "event_name": "VALIDA III PALMIRA",
            "file": "/tmp/fuera/valida_3.pdf",
            "general_file": "/tmp/fuera/general.pdf",
        }
        with pytest.raises(script.ManifestError, match="general_file"):
            script._validate_entry(entry, 1)

    @pytest.mark.asyncio
    async def test_general_like_filename_is_rejected(
        self, patched_session_local, override_storage, tmp_path
    ):
        outside = tmp_path / "outside"
        outside.mkdir()
        pdf_path = _build_pdf_outside_repo(outside, name_generator=FakeNameGenerator())
        general_named = pdf_path.with_name("copa_valle_2024_general.pdf")
        pdf_path.rename(general_named)

        entry = {
            "season": 2024, "valida_num": 3, "event_date": "2024-06-14",
            "location": "Palmira", "event_name": "VALIDA III PALMIRA",
            "file": str(general_named),
        }
        async with script.AsyncSessionLocal() as db:
            actor = await script._load_actor(db, 10)
        outcome = await script._stage_entry(1, entry, actor=actor, dry=False)
        assert outcome.ok is False
        assert outcome.code == "rejected"


# ---------------------------------------------------------------------------
# --dry: no stagea nada
# ---------------------------------------------------------------------------


class TestDryRunStagesNothing:
    @pytest.mark.asyncio
    async def test_dry_run_creates_no_race_import(
        self, patched_session_local, override_storage, tmp_path
    ):
        outside = tmp_path / "outside"
        outside.mkdir()
        pdf_path = _build_pdf_outside_repo(outside, name_generator=FakeNameGenerator())
        manifest = _write_manifest(tmp_path, [
            {
                "season": 2024, "valida_num": 3, "event_date": "2024-06-14",
                "location": "Palmira", "event_name": "VALIDA III PALMIRA",
                "file": str(pdf_path),
            }
        ])

        exit_code = await script._run(manifest, user_id=10, dry=True)
        assert exit_code == 0

        async with patched_session_local() as db:
            n_imports = len((await db.execute(select(RaceImport))).scalars().all())
        assert n_imports == 0


# ---------------------------------------------------------------------------
# Salida sin nombres + staging real
# ---------------------------------------------------------------------------


class TestFullRunStagesAndReportsNoNames:
    @pytest.mark.asyncio
    async def test_full_run_stages_and_output_has_no_names(
        self, patched_session_local, override_storage, tmp_path, capsys
    ):
        outside = tmp_path / "outside"
        outside.mkdir()
        name_gen = FakeNameGenerator()
        pdf_path = _build_pdf_outside_repo(outside, name_generator=name_gen)
        manifest = _write_manifest(tmp_path, [
            {
                "season": 2024, "valida_num": 3, "event_date": "2024-06-14",
                "location": "Palmira", "event_name": "VALIDA III PALMIRA",
                "file": str(pdf_path),
            }
        ])

        exit_code = await script._run(manifest, user_id=10, dry=False)
        assert exit_code == 0

        async with patched_session_local() as db:
            imports = (await db.execute(select(RaceImport))).scalars().all()
        assert len(imports) == 1
        assert imports[0].status.value == "pending"

        captured = capsys.readouterr()
        for generated_name in name_gen.generated:
            assert generated_name not in captured.out

        # Re-correr el mismo manifiesto (mismo archivo, aún pending) no debe
        # crear un segundo import (FR-027) — se reporta already_staged.
        exit_code_2 = await script._run(manifest, user_id=10, dry=False)
        assert exit_code_2 == 0
        async with patched_session_local() as db:
            imports_after = (await db.execute(select(RaceImport))).scalars().all()
        assert len(imports_after) == 1
