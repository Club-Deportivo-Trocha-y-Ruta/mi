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
stub_parsers, override_storage) — los duplicamos aquí para evitar acoplamiento.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.dependencies import get_db, get_current_user
from app.main import app
from app.models import Base
from app.models.race_event import RaceEvent, RaceEventStatus
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.services.race.revision import detect_revision


# ---------------------------------------------------------------------------
# Fixtures locales
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
            "race_categories",
            "race_competitors",
            "race_results",
            "race_result_revisions",
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


@pytest.fixture
def stub_parsers(monkeypatch):
    from app.routers import race_imports as router_mod
    from app.services.race.pdf_parser import ResultsRow

    async def fake_results(path, ext):  # noqa: ARG001
        return {
            "TET_CP": [
                ResultsRow(
                    position=1, bib="550", name="Sebastian Yule Mendoza",
                    city="Yumbo", club="Club Trocha y Ruta",
                    time_raw="0:03:38", points=40,
                ),
            ],
        }

    async def fake_general(path):  # noqa: ARG001
        return {}

    monkeypatch.setattr(router_mod, "_parse_results_with_timeout", fake_results)
    monkeypatch.setattr(router_mod, "_parse_general_with_timeout", fake_general)


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, seed_data, override_storage):
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(
        UserRole.coach, user_id=10
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _parse_form(**overrides) -> dict[str, str]:
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


_PDF_HEADER = b"%PDF-1.4\n"


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


class TestParseEndpointRevisionDetection:
    @pytest.mark.asyncio
    async def test_parse_first_upload_returns_will_be_revision_false(
        self, coach_client, stub_parsers
    ):
        """PDF nuevo sin previo committed → will_be_revision=false."""
        files = {"resultados_pdf": ("r.pdf", _PDF_HEADER + b"first content xyz", "application/pdf")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["will_be_revision"] is False
        assert data["parent_event_id"] is None
        assert data["parent_import_id"] is None
        assert data["parent_committed_at"] is None
        assert data["parent_n_results"] is None

    @pytest.mark.asyncio
    async def test_parse_revision_detection_when_committed_exists(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """Si ya existe RaceEvent + committed import para (series, valida),
        un parse con SHA distinto retorna 200 + will_be_revision=true."""
        # Seed: event + import committed para valida 4
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
            event_id = event.id

            committed = RaceImport(
                filename="prev.pdf",
                sha256="cc" * 32,  # SHA distinto al que generaremos
                series_id=1,
                status=RaceImportStatus.committed,
                stats_json={"results_inserted": 100},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
                event_id=event_id,
            )
            session.add(committed)
            await session.commit()
            prev_id = committed.id

        # Parse con SHA distinto (contenido único)
        files = {"resultados_pdf": ("r2.pdf", _PDF_HEADER + b"REVISED CONTENT XYZ 123", "application/pdf")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(valida_num=4), files=files,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["will_be_revision"] is True
        assert data["parent_event_id"] == event_id
        assert data["parent_import_id"] == prev_id
        assert data["parent_committed_at"] is not None
        # 0 results en seed (no creamos RaceResult)
        assert data["parent_n_results"] == 0

    @pytest.mark.asyncio
    async def test_parse_byte_exact_sha_still_returns_409(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """SHA byte-exacto duplicado en committed → 409 (sin cambio F-UP base).

        Política: una revisión REAL exige PDF distinto (al menos 1 byte). Si el
        coach intenta subir el mismo PDF byte-exacto, es un re-upload genuino
        (no aporta info nueva) → seguimos bloqueando.
        """
        # Calcular SHA del payload que vamos a enviar
        payload = _PDF_HEADER + b"identical content for sha test"
        sha = hashlib.sha256(payload).hexdigest()

        # Seed: committed con MISMO sha
        async with db_session_factory() as session:
            committed = RaceImport(
                filename="prev.pdf",
                sha256=sha,
                series_id=1,
                status=RaceImportStatus.committed,
                stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados,
            )
            session.add(committed)
            await session.commit()

        files = {"resultados_pdf": ("r.pdf", payload, "application/pdf")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files,
        )
        assert r.status_code == 409
        assert "commiteado" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_parse_revision_detection_for_different_valida(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """Committed previo en valida=3, ahora parse para valida=5 → no revisión.
        La detección debe matchear EXACTAMENTE el sequence_number."""
        async with db_session_factory() as session:
            event = RaceEvent(
                series_id=1, sequence_number=3,  # otro valida
                name="V3", event_date=datetime.now(timezone.utc).date(),
                location="Sevilla", created_by_user_id=10,
                status=RaceEventStatus.COMPLETED,
            )
            session.add(event)
            await session.commit()
            event_id = event.id

            committed = RaceImport(
                filename="v3.pdf", sha256="v3" * 32, series_id=1,
                status=RaceImportStatus.committed, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados, event_id=event_id,
            )
            session.add(committed)
            await session.commit()

        # Parse para valida=5 (distinta a la commiteada=3)
        files = {"resultados_pdf": ("r5.pdf", _PDF_HEADER + b"valida 5 content", "application/pdf")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(valida_num=5), files=files,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["will_be_revision"] is False
        assert data["parent_event_id"] is None

    @pytest.mark.asyncio
    async def test_parse_revision_ignores_pending_imports(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """Si hay event + pending (no committed), NO se considera revisión.

        Razón: el pending puede ser un wizard abandonado del mismo coach. Hasta
        que no haya committed, todo nuevo parse es "primer commit" lógico.
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
            event_id = event.id

            pending = RaceImport(
                filename="pend.pdf", sha256="pp" * 32, series_id=1,
                status=RaceImportStatus.pending, stats_json={},
                imported_by_user_id=10,
                imported_at=datetime.now(timezone.utc),
                kind=RaceImportKind.resultados, event_id=event_id,
            )
            session.add(pending)
            await session.commit()

        files = {"resultados_pdf": ("r.pdf", _PDF_HEADER + b"new pending content", "application/pdf")}
        r = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["will_be_revision"] is False

    @pytest.mark.asyncio
    async def test_parse_revision_succeeds_concurrent_uploads_gracefully(
        self, coach_client, stub_parsers, db_session_factory
    ):
        """Dos parses consecutivos sobre misma `(series, valida)` cuando ambos
        previo+actual son pending (ninguno committed) NO suben 409. Validamos
        que el segundo simplemente no se considera revisión.
        """
        files1 = {"resultados_pdf": ("r1.pdf", _PDF_HEADER + b"first parse a", "application/pdf")}
        r1 = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files1,
        )
        assert r1.status_code == 200
        assert r1.json()["will_be_revision"] is False

        files2 = {"resultados_pdf": ("r2.pdf", _PDF_HEADER + b"second parse b", "application/pdf")}
        r2 = await coach_client.post(
            "/api/race-analysis/imports/parse",
            data=_parse_form(), files=files2,
        )
        # Aún sin committed previo, el 2do parse tampoco es revisión.
        assert r2.status_code == 200
        assert r2.json()["will_be_revision"] is False
