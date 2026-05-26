"""Tests del router ``/api/race-analysis/imports/*`` (F-UP3).

Estrategia: stub mínimo del service layer + DB SQLite in-memory para los
endpoints `/dry-run`, `/commit`, `/` y un stub-storage in-memory para los PDFs.

Cubre los códigos HTTP del contrato (upload-design.md §4):
- 200 happy path parse / dry-run / commit / list
- 400 magic bytes / archivo vacío / formato no soportado
- 401 sin auth (anon)
- 403 rol parent
- 403 ownership cross-coach (parse_id de otro coach)
- 404 parse_id inexistente / ya committed
- 409 sha duplicado (committed previo con mismo sha)
- 413 archivo > RACE_MAX_PDF_MB
- 422 PDF/CSV inválido o parser sin resultados
- 422 resolved_matches incompletos
- list paginado + filter status
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.dependencies import get_db, require_role
from app.main import app
from app.models import Base
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Fixture: SQLite + dependency overrides (coach/admin/parent/anon)
# ---------------------------------------------------------------------------


def _make_user(role: UserRole, user_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncEngine:
    """SQLite async in-memory con solo las tablas necesarias para race_imports.

    Usa StaticPool para que todas las conexiones compartan la misma instancia
    en memoria (de lo contrario cada conexión nueva ve DB vacío).
    """
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Crear subgrafo (evita LONGTEXT incompatible)
    from app.models.user import User as _U  # noqa: F401
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
            "race_series",
            "race_events",
            "race_imports",
            "race_categories",
            "race_competitors",
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
async def seed_test_data(db_session_factory):
    """Inserta usuarios + series base usados por todos los tests."""
    async with db_session_factory() as session:
        # Coach con id 10 (owner default), coach con id 20 (cross-coach)
        coach1 = User(
            id=10, email="coach10@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        coach2 = User(
            id=20, email="coach20@test.com", hashed_password="x",
            first_name="Coach", last_name="Twenty",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        admin = User(
            id=1, email="admin@test.com", hashed_password="x",
            first_name="Admin", last_name="User",
            role=UserRole.admin, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        series = RaceSeries(
            id=1, name="Copa Valle de Ciclomontañismo", season_year=2026,
            organizer="Liga Vallecaucana", points_scheme_code="copa_valle_2026",
        )
        session.add_all([coach1, coach2, admin, series])
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
    # Vaciar envs SFTP para forzar fallback
    monkeypatch.setattr(settings, "hostinger_sftp_host", "")
    monkeypatch.setattr(settings, "hostinger_sftp_user", "")
    monkeypatch.setattr(settings, "hostinger_sftp_pass", "")
    monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "")
    monkeypatch.setattr(settings, "hostinger_public_base_url", "")
    yield fake_base


@pytest.fixture
def stub_parsers(monkeypatch):
    """Stub de pdf_parser / csv_parser para evitar dependencia de PDFs reales."""
    from app.routers import race_imports as router_mod

    async def fake_parse_results(path, ext):  # noqa: ARG001
        # Devolver 2 filas para que n_rows_resultados > 0
        from app.services.race.pdf_parser import ResultsRow
        return {
            "TET_CP": [
                ResultsRow(
                    position=1, bib="550", name="Sebastian Yule Mendoza",
                    city="Yumbo", club="Club Trocha y Ruta",
                    time_raw="0:03:38", points=40,
                ),
                ResultsRow(
                    position=2, bib="551", name="Otro Tetero",
                    city="Cali", club="Club X",
                    time_raw="0:04:00", points=36,
                ),
            ],
        }

    async def fake_parse_general(path):  # noqa: ARG001
        return {}

    monkeypatch.setattr(
        router_mod, "_parse_results_with_timeout", fake_parse_results
    )
    monkeypatch.setattr(
        router_mod, "_parse_general_with_timeout", fake_parse_general
    )


@pytest.fixture
def stub_parsers_empty(monkeypatch):
    """Stub que retorna 0 filas — usado para test 422 'parser sin resultados'."""
    from app.routers import race_imports as router_mod

    async def fake_empty(path, ext):  # noqa: ARG001
        return {}

    async def fake_general_empty(path):  # noqa: ARG001
        return {}

    monkeypatch.setattr(
        router_mod, "_parse_results_with_timeout", fake_empty
    )
    monkeypatch.setattr(
        router_mod, "_parse_general_with_timeout", fake_general_empty
    )


@pytest.fixture
def stub_ingestor(monkeypatch):
    """Stub de RaceIngestor.ingest_event — evita interacción con la fake DB
    desde el ingestor real (tiene queries que SQLite no soporta vía Select).

    Simula el contrato del ingestor real para los efectos secundarios mínimos:
    si NO es dry_run y hay pdf_results_sha256, promueve el RaceImport pending
    a committed (como hace el ingestor real). En dry_run no toca BD.
    """
    from sqlalchemy import select
    from app.models.race_import import RaceImport, RaceImportStatus
    from app.schemas.race import IngestReport
    from app.services.race import ingestor as ingestor_mod

    state = {"calls": []}

    async def fake_ingest(self, meta, results_by_category, **kwargs):
        state["calls"].append(
            {
                "valida_num": meta.valida_num,
                "dry_run": kwargs.get("dry_run", False),
                "match_decisions": kwargs.get("match_decisions") or {},
                "sha": kwargs.get("pdf_results_sha256"),
            }
        )
        dry_run = kwargs.get("dry_run", False)
        sha = kwargs.get("pdf_results_sha256")
        # Simular promoción pending→committed cuando es commit real
        if not dry_run and sha:
            result = await self.db.execute(
                select(RaceImport).where(
                    RaceImport.sha256 == sha,
                    RaceImport.status == RaceImportStatus.pending,
                )
            )
            pending = result.scalar_one_or_none()
            if pending is not None:
                pending.status = RaceImportStatus.committed
                pending.stats_json = {
                    "results_inserted": 2,
                    "tyr_count": 1,
                }
                await self.db.flush()
        return IngestReport(
            event_id=100,
            series_id=1,
            competitors_created=5,
            competitors_updated=0,
            results_inserted=2,
            results_skipped=0,
            tyr_count=1,
            warnings=[],
        )

    monkeypatch.setattr(
        ingestor_mod.RaceIngestor, "ingest_event", fake_ingest
    )
    return state


@pytest_asyncio.fixture
async def coach_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente HTTP autenticado como coach id=10."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    # Override require_role para devolver coach10
    from app.routers import race_imports as router_mod

    # require_role devuelve callables, los overrideamos por la callable retornada
    # haciendo monkey-patch del dependency creator directamente desde el módulo.
    # Mejor: override get_current_user + require_role retorna current_user.
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def coach2_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente coach id=20 — usado para tests de ownership cross-coach."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=20
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente admin id=1."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.admin, user_id=1
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def parent_client(
    sqlite_engine, db_session_factory, seed_test_data, override_storage
):
    """Cliente parent id=5 — debe ser bloqueado."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    from app.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.parent, user_id=5
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def anon_client(sqlite_engine, db_session_factory, override_storage):
    """Cliente sin auth — NO override de get_current_user."""
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_PDF_HEADER = b"%PDF-1.4\n"
_CSV_HEADER = b"POS,BIB,NAME,CLUB,TIME,POINTS\n1,550,Sebas,Club,03:38,40\n"


def _parse_form(extra_files=None, **overrides):
    """Construye form payload base + files para multipart upload."""
    form = {
        "series_name": "Copa Valle",
        "season": "2026",
        "valida_num": "4",
        "event_name": "VALIDA IV CALI",
        "event_date": "2026-05-17",
        "location": "CALI",
    }
    form.update({k: str(v) for k, v in overrides.items()})
    return form


def _pdf_file(content_extra: bytes = b"") -> tuple[str, bytes, str]:
    return ("resultados.pdf", _PDF_HEADER + content_extra, "application/pdf")


# ===========================================================================
# Auth / RBAC
# ===========================================================================


class TestAuthRbac:
    @pytest.mark.asyncio
    async def test_anon_get_returns_401_or_403(self, anon_client):
        """Sin auth: el bearer scheme requiere credenciales."""
        r = await anon_client.get("/api/race-analysis/imports/")
        assert r.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_parent_forbidden_on_list(self, parent_client):
        r = await parent_client.get("/api/race-analysis/imports/")
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_parent_forbidden_on_parse(self, parent_client, stub_parsers):
        files = {
            "resultados_pdf": _pdf_file(b"content"),
        }
        r = await parent_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_coach_ok_on_list_empty(self, coach_client):
        r = await coach_client.get("/api/race-analysis/imports/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []


# ===========================================================================
# POST /parse — happy path + validaciones
# ===========================================================================


class TestParseEndpoint:
    @pytest.mark.asyncio
    async def test_parse_happy_path_pdf(self, coach_client, stub_parsers):
        files = {
            "resultados_pdf": _pdf_file(b"dummy results content"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "parse_id" in data
        assert len(data["sha256"]) == 64
        assert data["header"]["valida_num"] == 4
        assert data["n_rows_resultados"] == 2
        assert data["n_rows_general"] is None

    @pytest.mark.asyncio
    async def test_parse_with_general_pdf(self, coach_client, stub_parsers):
        files = {
            "resultados_pdf": _pdf_file(b"results content"),
            "general_pdf": ("general.pdf", _PDF_HEADER + b"general content", "application/pdf"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["n_rows_general"] == 0  # stub_parsers retorna {} para general

    @pytest.mark.asyncio
    async def test_parse_with_csv_results(self, coach_client, stub_parsers):
        files = {
            "resultados_pdf": ("resultados.csv", _CSV_HEADER, "text/csv"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_parse_rejects_pdf_without_magic_bytes(
        self, coach_client, stub_parsers
    ):
        """400: archivo .pdf cuyo contenido no es PDF (sin %PDF-)."""
        files = {
            "resultados_pdf": (
                "fake.pdf", b"<html>not a pdf</html>", "application/pdf"
            ),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 400
        assert "magic bytes" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_parse_rejects_unknown_extension(
        self, coach_client, stub_parsers
    ):
        files = {
            "resultados_pdf": ("file.exe", b"binary", "application/octet-stream"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 400
        assert "no soportado" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_parse_rejects_empty_file(self, coach_client, stub_parsers):
        files = {
            "resultados_pdf": ("resultados.pdf", b"", "application/pdf"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 400
        assert "vacío" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_parse_rejects_oversized_file(
        self, coach_client, stub_parsers, monkeypatch
    ):
        """413: tamaño > RACE_MAX_PDF_MB."""
        # Bajamos el cap a 1 MB para no inflar memoria
        monkeypatch.setattr(settings, "race_max_pdf_mb", 1)
        oversized = _PDF_HEADER + (b"a" * (2 * 1024 * 1024))  # 2 MB
        files = {
            "resultados_pdf": ("resultados.pdf", oversized, "application/pdf"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 413
        assert "límite" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_parse_rejects_when_parser_returns_zero_rows(
        self, coach_client, stub_parsers_empty
    ):
        """422: PDF parseable pero sin filas reconocidas."""
        files = {
            "resultados_pdf": _pdf_file(b"valid pdf bytes"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 422
        assert "ninguna fila" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_parse_409_on_committed_sha_duplicate(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """Pre-seedeamos un RaceImport committed con cierto sha; un parse con
        bytes que tengan el mismo sha debe retornar 409."""
        # Calculamos sha de un payload conocido y lo seedeamos
        import hashlib

        payload = _PDF_HEADER + b"unique content xyz"
        sha = hashlib.sha256(payload).hexdigest()

        async with db_session_factory() as session:
            existing = RaceImport(
                filename="existing.pdf",
                sha256=sha,
                series_id=1,
                status=RaceImportStatus.committed,
                stats_json={"results_inserted": 100},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
            )
            session.add(existing)
            await session.commit()

        files = {
            "resultados_pdf": ("resultados.pdf", payload, "application/pdf"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 409
        assert "commiteado" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_parse_sanitizes_path_traversal_filename(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """El filename ../../etc/passwd.pdf debe ser sanitizado en BD."""
        files = {
            "resultados_pdf": (
                "../../etc/passwd.pdf", _PDF_HEADER + b"content", "application/pdf"
            ),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse", data=_parse_form(), files=files
        )
        assert r.status_code == 200
        parse_id = r.json()["parse_id"]

        async with db_session_factory() as session:
            from sqlalchemy import select as _sel
            imp = (await session.execute(
                _sel(RaceImport).where(RaceImport.id == parse_id)
            )).scalar_one()
            # Sanitizado: no debe contener "/" ni "..\"
            assert "/" not in imp.filename
            assert ".." not in imp.filename
            # Original preservado para UI
            assert imp.original_filename == "../../etc/passwd.pdf"


# ===========================================================================
# POST /{parse_id}/dry-run
# ===========================================================================


class TestDryRunEndpoint:
    @pytest.mark.asyncio
    async def test_dry_run_404_unknown_parse_id(self, coach_client):
        r = await coach_client.post(
            "/api/race-analysis/imports/9999/dry-run"
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_dry_run_404_on_already_committed(
        self, coach_client, db_session_factory
    ):
        """parse_id en estado committed → 404 (no se puede dry-run)."""
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="a" * 64, series_id=1,
                status=RaceImportStatus.committed, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_dry_run_403_cross_coach_ownership(
        self, coach2_client, db_session_factory
    ):
        """coach20 intenta hacer dry-run sobre parse_id de coach10 → 403."""
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="b" * 64, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,  # propiedad de coach10
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                parse_meta_json={"header": {}},
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach2_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_dry_run_admin_bypasses_ownership(
        self, admin_client, db_session_factory
    ):
        """Admin puede dry-run sobre parse de cualquier coach.

        Verificamos que pase el chequeo ownership; el dry-run en sí fallará
        después por falta de PDF en storage (410), lo cual nos confirma que
        ownership pasó OK."""
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="c" * 64, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,  # otro coach
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                parse_meta_json={"header": {}, "results_ext": "pdf"},
                storage_path="/nonexistent/file.pdf",
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await admin_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        # Admin pasa ownership; falla en reload_parsed_from_storage por 410.
        assert r.status_code != 403


# ===========================================================================
# POST /{parse_id}/commit
# ===========================================================================


class TestCommitEndpoint:
    @pytest.mark.asyncio
    async def test_commit_404_unknown_parse_id(self, coach_client):
        r = await coach_client.post(
            "/api/race-analysis/imports/9999/commit",
            json={"resolved_matches": []},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_commit_invalid_body_422(self, coach_client):
        r = await coach_client.post(
            "/api/race-analysis/imports/1/commit",
            json={"resolved_matches": [{"athlete_id": 1}]},  # falta normalized_name
        )
        assert r.status_code == 422


# ===========================================================================
# GET / — list paginado
# ===========================================================================


class TestListEndpoint:
    @pytest.mark.asyncio
    async def test_list_empty(self, coach_client):
        r = await coach_client.get("/api/race-analysis/imports/")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

    @pytest.mark.asyncio
    async def test_list_returns_seeded_imports(
        self, coach_client, db_session_factory
    ):
        async with db_session_factory() as session:
            for i in range(3):
                session.add(
                    RaceImport(
                        filename=f"r{i}.pdf",
                        original_filename=f"Resultados {i}.pdf",
                        sha256=str(i) * 64,
                        series_id=1,
                        status=RaceImportStatus.committed,
                        stats_json={"results_inserted": 200 + i},
                        imported_by_user_id=10,
                        imported_at=datetime.now(timezone.utc),
                        kind=RaceImportKind.both,
                        event_id=None,
                    )
                )
            await session.commit()

        r = await coach_client.get("/api/race-analysis/imports/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["uploaded_by"]["full_name"] == "Coach Ten"
            assert item["kind"] == "both"
            assert item["status"] == "committed"
            assert item["n_results"] in (200, 201, 202)

    @pytest.mark.asyncio
    async def test_list_paginated(self, coach_client, db_session_factory):
        async with db_session_factory() as session:
            for i in range(5):
                session.add(
                    RaceImport(
                        filename=f"r{i}.pdf",
                        sha256=f"{i:x}" * 32,  # 64 hex chars
                        series_id=1,
                        status=RaceImportStatus.committed,
                        stats_json={},
                        imported_by_user_id=10,
                        imported_at=datetime.now(timezone.utc),
                        kind=RaceImportKind.resultados,
                    )
                )
            await session.commit()

        r = await coach_client.get(
            "/api/race-analysis/imports/?limit=2&offset=1"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, coach_client, db_session_factory):
        async with db_session_factory() as session:
            session.add(
                RaceImport(
                    filename="committed.pdf", sha256="a" * 64, series_id=1,
                    status=RaceImportStatus.committed, stats_json={},
                    imported_by_user_id=10,
                    imported_at=datetime.now(timezone.utc),
                    kind=RaceImportKind.resultados,
                )
            )
            session.add(
                RaceImport(
                    filename="pending.pdf", sha256="b" * 64, series_id=1,
                    status=RaceImportStatus.pending, stats_json={},
                    imported_by_user_id=10,
                    imported_at=datetime.now(timezone.utc),
                    kind=RaceImportKind.resultados,
                )
            )
            await session.commit()

        # Filtrar committed
        r = await coach_client.get(
            "/api/race-analysis/imports/?status=committed"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "committed"

        # Filtrar pending
        r = await coach_client.get(
            "/api/race-analysis/imports/?status=pending"
        )
        assert r.status_code == 200
        assert r.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_list_400_on_invalid_status(self, coach_client):
        r = await coach_client.get(
            "/api/race-analysis/imports/?status=invalid_xx"
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_list_query_limit_validation(self, coach_client):
        # limit > 100 inválido
        r = await coach_client.get("/api/race-analysis/imports/?limit=999")
        assert r.status_code == 422
        # offset negativo inválido
        r = await coach_client.get("/api/race-analysis/imports/?offset=-1")
        assert r.status_code == 422


# ===========================================================================
# Helpers y casos adicionales: sanitización + parsing edge cases
# ===========================================================================


class TestParseValidation:
    @pytest.mark.asyncio
    async def test_parse_form_missing_required_fields_422(
        self, coach_client, stub_parsers
    ):
        """Faltan campos del form (valida_num, season, ...) → 422 Pydantic."""
        files = {"resultados_pdf": _pdf_file(b"content")}
        # data sin valida_num
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data={"series_name": "x", "season": "2026", "event_name": "n",
                  "event_date": "2026-05-17", "location": "Cali"},
            files=files,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_parse_valida_num_out_of_range(self, coach_client, stub_parsers):
        """valida_num=100 → 422."""
        files = {"resultados_pdf": _pdf_file(b"content")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(valida_num=100), files=files,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_parse_results_and_general_same_sha_rejected(
        self, coach_client, stub_parsers
    ):
        """Si resultados y general tienen mismo SHA, 400 (cliente confundido)."""
        identical = _PDF_HEADER + b"same content"
        files = {
            "resultados_pdf": ("r.pdf", identical, "application/pdf"),
            "general_pdf": ("g.pdf", identical, "application/pdf"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files,
        )
        assert r.status_code == 400
        assert "mismo" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_parse_general_only_pdf_accepted(
        self, coach_client, stub_parsers
    ):
        """general como .csv → 400 (GENERAL solo PDF, design §1.3)."""
        files = {
            "resultados_pdf": _pdf_file(b"r content"),
            "general_pdf": ("g.csv", _CSV_HEADER, "text/csv"),
        }
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files,
        )
        assert r.status_code == 400
        assert ".pdf" in r.json()["detail"]


class TestCommitValidation:
    @pytest.mark.asyncio
    async def test_commit_404_on_dry_run_status(
        self, coach_client, db_session_factory
    ):
        """status=dry_run no es pending → 404 igual que committed/failed."""
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf", sha256="d" * 64, series_id=1,
                status=RaceImportStatus.dry_run, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_client.post(
            f"/api/race-analysis/imports/{pid}/commit",
            json={"resolved_matches": []},
        )
        assert r.status_code == 404
        assert "pending" in r.json()["detail"].lower()


# ===========================================================================
# Full flow: parse → dry-run → commit (con stub ingestor y storage real local)
# ===========================================================================


class TestFullFlowWithStubIngestor:
    """Pruebas end-to-end del wizard usando el StubIngestor para evitar la
    interacción del ingestor real con SQLite (que rompe en queries Select)."""

    @pytest.mark.asyncio
    async def test_full_flow_parse_dryrun_commit(
        self, coach_client, stub_parsers, stub_ingestor, db_session_factory
    ):
        # 1. Parse
        files = {"resultados_pdf": _pdf_file(b"flow content xyz")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files,
        )
        assert r.status_code == 200, r.text
        parse_id = r.json()["parse_id"]

        # 2. Dry-run (el storage_path debe existir gracias al fallback local)
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/dry-run"
        )
        assert r.status_code == 200, r.text
        dry = r.json()
        assert dry["parse_id"] == parse_id
        # 1 match TyR (Sebastian del stub) → ambiguous
        assert dry["counts"]["ambiguous"] == 1

        # 3. Commit con resolved_matches que cubre el TyR detectado
        from app.services.race.normalizer import normalize_name

        match_norm = normalize_name("Sebastian Yule Mendoza")
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json={
                "resolved_matches": [
                    {"competitor_normalized_name": match_norm, "athlete_id": None}
                ]
            },
        )
        assert r.status_code == 200, r.text
        commit_resp = r.json()
        assert commit_resp["parse_id"] == parse_id
        assert commit_resp["race_event_id"] == 100  # stub ingestor returns event_id=100
        assert commit_resp["n_results_inserted"] == 2

        # 4. Verificar promoción pending → committed en BD
        async with db_session_factory() as session:
            from sqlalchemy import select as _sel
            imp = (await session.execute(
                _sel(RaceImport).where(RaceImport.id == parse_id)
            )).scalar_one()
            assert imp.status == RaceImportStatus.committed
            assert imp.event_id == 100
            # parse_meta limpiado tras commit
            assert imp.parse_meta_json is None
            # storage_path movido a committed/
            assert imp.storage_path and "committed" in imp.storage_path

    @pytest.mark.asyncio
    async def test_commit_missing_resolved_matches_422(
        self, coach_client, stub_parsers, stub_ingestor, db_session_factory
    ):
        """Si el TyR detectado no tiene resolved_match → 422."""
        # Parse para crear el pending
        files = {"resultados_pdf": _pdf_file(b"flow content missing matches")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files,
        )
        assert r.status_code == 200
        parse_id = r.json()["parse_id"]

        # Commit con resolved_matches vacíos
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/commit",
            json={"resolved_matches": []},
        )
        assert r.status_code == 422
        assert "resolved_matches" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_dry_run_410_when_storage_file_missing(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """Si parse persistió un storage_path pero el archivo no existe en disk
        (caso fallback local efímero post-restart), dry-run retorna 410."""
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="x.pdf",
                sha256="f0" * 32,
                series_id=1,
                status=RaceImportStatus.pending,
                stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                parse_meta_json={
                    "header": {
                        "season": 2026,
                        "valida_num": 4,
                        "event_name": "X",
                        "event_date": "2026-05-17",
                        "location": "Cali",
                    },
                    "results_ext": "pdf",
                },
                storage_path="/nonexistent-test-path/r.pdf",
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        assert r.status_code == 410
        assert "storage" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_parse_results_with_timeout_helper_raises_422_on_timeout(
        self, monkeypatch
    ):
        """Test directo del helper: si asyncio.wait_for lanza TimeoutError → 422."""
        from app.routers import race_imports as router_mod
        from app.services.race.pdf_parser import parse_results_pdf

        async def fake_wait_for(coro, timeout):
            # Cancelamos el coroutine creada para no leaks (best-effort)
            try:
                coro.close()
            except Exception:  # noqa: BLE001
                pass
            import asyncio
            raise asyncio.TimeoutError()

        monkeypatch.setattr(router_mod, "wait_for", fake_wait_for)

        with pytest.raises(HTTPException) as exc_info:
            await router_mod._parse_results_with_timeout(Path("/x.pdf"), "pdf")
        assert exc_info.value.status_code == 422
        assert "complejo" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_parse_general_with_timeout_helper_raises_422_on_exception(
        self, monkeypatch
    ):
        """Helper general: cualquier excepción del parser → 422."""
        from app.routers import race_imports as router_mod

        async def fake_wait_for(coro, timeout):
            try:
                coro.close()
            except Exception:  # noqa: BLE001
                pass
            raise ValueError("simulated parse failure")

        monkeypatch.setattr(router_mod, "wait_for", fake_wait_for)

        with pytest.raises(HTTPException) as exc_info:
            await router_mod._parse_general_with_timeout(Path("/x.pdf"))
        assert exc_info.value.status_code == 422
        assert "GENERAL" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_dry_run_sftp_remote_path_does_not_return_410(
        self,
        coach_client,
        stub_parsers,
        stub_ingestor,
        db_session_factory,
        monkeypatch,
    ):
        """Regresión: storage_path remoto SFTP (no existe en disco local) debe
        ser descargado vía download_to_tempfile y NO retornar HTTP 410.

        Simula producción donde ``HOSTINGER_SFTP_*`` está configurado y el
        storage_path es un path absoluto del servidor FTPS que no existe en el
        disco del contenedor Render.
        """
        from app.services.training import storage_sftp
        from app.config import settings

        # Activar modo SFTP (sin conexión real)
        monkeypatch.setattr(settings, "hostinger_sftp_host", "ftps.example.com")
        monkeypatch.setattr(settings, "hostinger_sftp_user", "user")
        monkeypatch.setattr(settings, "hostinger_sftp_pass", "pass")
        monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "/public_html")
        monkeypatch.setattr(
            settings, "hostinger_public_base_url", "https://cdn.example.com"
        )

        # Stub de download_to_tempfile que crea un tmp válido con magic bytes PDF
        import tempfile
        from pathlib import Path

        async def fake_download(storage_path: str, suffix: str = "") -> Path:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(b"%PDF-1.4\nfake pdf content for sftp test")
            tmp.close()
            return Path(tmp.name)

        monkeypatch.setattr(storage_sftp, "download_to_tempfile", fake_download)

        # Crear un RaceImport pending con storage_path "remoto" (no existe localmente)
        remote_path = "/public_html/mi/media/race-imports/pending/abc123/resultados.pdf"
        async with db_session_factory() as session:
            imp = RaceImport(
                filename="resultados.pdf",
                original_filename="RESULTADOS_VALIDA_IV.pdf",
                sha256="e1" * 32,
                series_id=1,
                status=RaceImportStatus.pending,
                stats_json={},
                imported_by_user_id=10,
                imported_at=datetime(2026, 5, 17, tzinfo=timezone.utc),
                kind=RaceImportKind.resultados,
                storage_path=remote_path,
                storage_url="https://cdn.example.com/mi/media/race-imports/pending/abc123/resultados.pdf",
                parse_meta_json={
                    "header": {
                        "season": 2026,
                        "valida_num": 4,
                        "event_name": "VALIDA IV CALI",
                        "event_date": "2026-05-17",
                        "location": "Cali",
                    },
                    "results_ext": "pdf",
                    "parse_uuid": "abc123",
                },
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        # No debe retornar 410 (PDF no encontrado en storage)
        assert r.status_code != 410, (
            f"Regresión: dry-run retornó 410 con storage_path remoto SFTP. "
            f"Detalle: {r.json()}"
        )
        # Con stub_parsers en lugar devuelve 200
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_download_to_tempfile_fallback_local_raises_fnf_on_missing(
        self, monkeypatch
    ):
        """download_to_tempfile en modo local lanza FileNotFoundError si el path
        no existe (equivalente al test de la capa de servicio pero desde router)."""
        from app.services.training import storage_sftp
        from app.config import settings

        # Forzar modo fallback local (sin SFTP)
        monkeypatch.setattr(settings, "hostinger_sftp_host", "")

        with pytest.raises(FileNotFoundError):
            await storage_sftp.download_to_tempfile("/nonexistent/path/r.pdf", suffix=".pdf")

    @pytest.mark.asyncio
    async def test_dry_run_general_sftp_missing_continues_without_general(
        self,
        coach_client,
        stub_parsers,
        stub_ingestor,
        db_session_factory,
        monkeypatch,
    ):
        """Si el GENERAL no está en SFTP, dry-run continúa sin él (no 4xx).

        GENERAL es opcional; su ausencia en storage no debe romper el flow.
        """
        from app.services.training import storage_sftp
        from app.config import settings
        import tempfile
        from pathlib import Path

        monkeypatch.setattr(settings, "hostinger_sftp_host", "ftps.example.com")
        monkeypatch.setattr(settings, "hostinger_sftp_user", "user")
        monkeypatch.setattr(settings, "hostinger_sftp_pass", "pass")
        monkeypatch.setattr(settings, "hostinger_sftp_remote_dir", "/public_html")
        monkeypatch.setattr(
            settings, "hostinger_public_base_url", "https://cdn.example.com"
        )

        remote_results = "/public_html/race-imports/pending/def456/resultados.pdf"
        remote_general = "/public_html/race-imports/pending/def456/general.pdf"

        async def fake_download(storage_path: str, suffix: str = "") -> Path:
            if "general" in storage_path:
                raise FileNotFoundError(storage_path)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(b"%PDF-1.4\nfake results")
            tmp.close()
            return Path(tmp.name)

        monkeypatch.setattr(storage_sftp, "download_to_tempfile", fake_download)

        async with db_session_factory() as session:
            imp = RaceImport(
                filename="resultados.pdf",
                original_filename="RESULTADOS_VALIDA_III.pdf",
                sha256="f2" * 32,
                series_id=1,
                status=RaceImportStatus.pending,
                stats_json={},
                imported_by_user_id=10,
                imported_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
                kind=RaceImportKind.both,
                storage_path=remote_results,
                general_storage_path=remote_general,
                parse_meta_json={
                    "header": {
                        "season": 2026,
                        "valida_num": 3,
                        "event_name": "VALIDA III",
                        "event_date": "2026-04-19",
                        "location": "La Cumbre",
                    },
                    "results_ext": "pdf",
                    "parse_uuid": "def456",
                },
            )
            session.add(imp)
            await session.commit()
            pid = imp.id

        r = await coach_client.post(
            f"/api/race-analysis/imports/{pid}/dry-run"
        )
        assert r.status_code == 200, (
            f"dry-run debe continuar sin GENERAL ausente. Detalle: {r.json()}"
        )

    @pytest.mark.asyncio
    async def test_dry_run_returns_zero_matches_when_no_tyr(
        self, coach_client, monkeypatch, stub_ingestor, db_session_factory
    ):
        """PDF sin atletas TyR (todos clubes externos) → 0 matches."""
        from app.routers import race_imports as router_mod
        from app.services.race.pdf_parser import ResultsRow

        async def fake_no_tyr(path, ext):  # noqa: ARG001
            return {
                "TET_CP": [
                    ResultsRow(
                        position=1, bib="999", name="External Rider",
                        city="Bogotá", club="Club Externo",
                        time_raw="0:05:00", points=30,
                    ),
                ],
            }

        async def fake_g(path):  # noqa: ARG001
            return {}

        monkeypatch.setattr(
            router_mod, "_parse_results_with_timeout", fake_no_tyr
        )
        monkeypatch.setattr(
            router_mod, "_parse_general_with_timeout", fake_g
        )

        # Parse
        files = {"resultados_pdf": _pdf_file(b"no tyr content")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files,
        )
        assert r.status_code == 200
        parse_id = r.json()["parse_id"]

        # Dry-run
        r = await coach_client.post(
            f"/api/race-analysis/imports/{parse_id}/dry-run"
        )
        assert r.status_code == 200
        assert r.json()["counts"]["total"] == 0

    @pytest.mark.asyncio
    async def test_dry_run_unknown_category_returns_422(
        self, coach_client, monkeypatch, db_session_factory
    ):
        """Categoría desconocida en parsed_results → ingestor lanza ValueError
        → dry-run debe devolver HTTP 422 con detail que mencione la categoría.

        Regresión: antes del fix el ingestor propagaba ValueError sin handler
        y FastAPI devolvía HTTP 500 sin body (bug producción 2026-05-26).
        """
        from app.routers import race_imports as router_mod
        from app.services.race import ingestor as ingestor_mod
        from app.services.race.pdf_parser import ResultsRow

        # Stub parser devuelve una categoría inexistente en DB
        _FAKE_CODE = "XYZ_FAKE"

        async def fake_unknown_cat(path, ext):  # noqa: ARG001
            return {
                _FAKE_CODE: [
                    ResultsRow(
                        position=1, bib="001", name="Ciclista Fantasma",
                        city="Cali", club="Club Trocha y Ruta",
                        time_raw="0:04:00", points=40,
                    ),
                ],
            }

        async def fake_g(path):  # noqa: ARG001
            return {}

        monkeypatch.setattr(router_mod, "_parse_results_with_timeout", fake_unknown_cat)
        monkeypatch.setattr(router_mod, "_parse_general_with_timeout", fake_g)

        # El ingestor real lanza ValueError cuando no encuentra la categoría.
        # Lo replicamos con un stub que no toca la DB pero reproduce el error.
        async def fake_ingest_raises(self, meta, results_by_category, **kwargs):
            for code in results_by_category:
                raise ValueError(
                    f"Categoría desconocida en RESULTADOS: code='{code}'"
                )

        monkeypatch.setattr(ingestor_mod.RaceIngestor, "ingest_event", fake_ingest_raises)

        # 1. Parse (necesitamos un parse_id válido en DB)
        files = {"resultados_pdf": _pdf_file(b"unknown cat content")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(),
            files=files,
        )
        assert r.status_code == 200, r.text
        parse_id = r.json()["parse_id"]

        # 2. Dry-run — debe devolver 422, no 500
        r = await coach_client.post(f"/api/race-analysis/imports/{parse_id}/dry-run")
        assert r.status_code == 422, (
            f"Se esperaba 422 por categoría desconocida, se obtuvo {r.status_code}: {r.text}"
        )
        detail = r.json().get("detail", "")
        assert "Categoría desconocida" in detail, (
            f"El detail debe mencionar 'Categoría desconocida', se obtuvo: {detail!r}"
        )
        assert _FAKE_CODE in detail, (
            f"El detail debe incluir el code inválido '{_FAKE_CODE}', se obtuvo: {detail!r}"
        )
