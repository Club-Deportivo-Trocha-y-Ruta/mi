"""Tests de ``app.services.race.import_staging.stage_results_file`` (feature
044, US5, T056 — contracts/historical-load.md §"Staging service").

Llama el servicio DIRECTAMENTE (sin pasar por FastAPI) — es exactamente lo
que hará ``backend/scripts/stage_race_history.py`` (T063) y lo que prueba
que la extracción de T059 no cambió el comportamiento de ``POST /parse``
(los tests de router en ``tests/routers/test_race_imports*.py`` siguen en
verde con el mismo aserto HTTP; este archivo es la comparación golden a
nivel de servicio que T059 pidió como red de seguridad).

Requiere WeasyPrint (vía ``tests/helpers/results_pdf_builder.py``) — en este
Mac hace falta anteponer ``DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`` al
comando de pytest.

Privacidad: todos los nombres son sintéticos (``FakeNameGenerator``); ningún
PDF real de la Federación se usa ni se genera aquí.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

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
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_series import RaceSeries, RaceSeriesKind
from app.models.user import User, UserRole
from app.services.race.import_staging import stage_results_file
from app.services.request_context import AuditContext
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.results_pdf_builder import (
    CategorySpec,
    FakeNameGenerator,
    build_results_pdf,
    sequential_category,
)


# ---------------------------------------------------------------------------
# Fixtures: sqlite en memoria + storage local fallback
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
async def db_session_factory(sqlite_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(sqlite_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def actor_user(db_session_factory) -> User:
    async with db_session_factory() as session:
        user = User(
            id=10,
            email="coach10@test.com",
            hashed_password="x",
            first_name="Coach",
            last_name="Ten",
            role=UserRole.coach,
            is_active=True,
            can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()
    return user


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
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


def _ctx(actor: User) -> AuditContext:
    return AuditContext.for_user(actor, request_id="test-req-import-staging")


def _build_pdf(tmp_path: Path, *, valida_num: int, location: str,
               event_date: date, categories: list[CategorySpec]) -> bytes:
    path = build_results_pdf(
        tmp_path / "sintetico.pdf",
        valida_num=valida_num,
        location=location,
        event_date=event_date,
        categories=categories,
        name_generator=FakeNameGenerator(),
    )
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Golden comparison — archivo 2026 (temporada corriente)
# ---------------------------------------------------------------------------


class TestGoldenComparison2026:
    """El servicio extraído produce el mismo ``RaceImport`` + respuesta que
    ``POST /parse`` producía antes de T059 (mismo escenario que
    ``tests/routers/test_race_imports.py::TestParseEndpoint``, a nivel de
    servicio)."""

    @pytest.mark.asyncio
    async def test_stage_creates_pending_import_matching_inputs(
        self, db_session_factory, override_storage, actor_user, tmp_path
    ):
        category = sequential_category("INFANTIL A", 3)
        for i, row in enumerate(category.rows, start=1):
            row.bib = str(700 + i)
        pdf_bytes = _build_pdf(
            tmp_path,
            valida_num=4,
            location="Cali",
            event_date=date(2026, 5, 17),
            categories=[category],
        )

        async with db_session_factory() as db:
            response = await stage_results_file(
                db,
                file_bytes=pdf_bytes,
                original_filename="valida_iv_resultados.pdf",
                results_ext="pdf",
                series_name="Copa Valle de Ciclomontañismo",
                season=2026,
                valida_num=4,
                event_name="VALIDA IV CALI",
                event_date=date(2026, 5, 17),
                location="Cali",
                actor=actor_user,
                ctx=_ctx(actor_user),
            )
            await db.commit()

            # Sin desacuerdo header/inputs (mismo valida_num/fecha/sede que
            # el PDF trae impresos): sin warning header_mismatch.
            assert response.warnings == []
            assert response.header.season == 2026
            assert response.header.valida_num == 4
            assert response.n_rows_resultados == 3
            assert len(response.categories) == 1
            assert response.categories[0].code == "INF_A"
            assert response.categories[0].completeness.status == "ok"

            imp = (
                await db.execute(
                    select(RaceImport).where(RaceImport.id == response.parse_id)
                )
            ).scalar_one()
            assert imp.status == RaceImportStatus.pending
            assert imp.sha256 == response.sha256
            assert imp.kind == RaceImportKind.resultados
            assert imp.imported_by_user_id == actor_user.id
            assert imp.parse_meta_json["header"]["season"] == 2026
            assert imp.parse_meta_json["header"]["valida_num"] == 4
            assert imp.parse_meta_json["header"]["location"] == "Cali"
            # rows es un CONTEO en el meta cacheado, nunca la lista con nombres
            # (data-model.md §7).
            assert imp.parse_meta_json["categories"][0]["rows"] == 3

            series = (
                await db.execute(
                    select(RaceSeries).where(RaceSeries.id == imp.series_id)
                )
            ).scalar_one()
            assert series.season_year == 2026
            assert series.kind == RaceSeriesKind.cup

    @pytest.mark.asyncio
    async def test_zero_rows_raises_422(
        self, db_session_factory, override_storage, actor_user, tmp_path
    ):
        from fastapi import HTTPException

        pdf_bytes = _build_pdf(
            tmp_path, valida_num=4, location="Cali",
            event_date=date(2026, 5, 17), categories=[],
        )
        async with db_session_factory() as db:
            with pytest.raises(HTTPException) as exc_info:
                await stage_results_file(
                    db,
                    file_bytes=pdf_bytes,
                    original_filename="vacio.pdf",
                    results_ext="pdf",
                    series_name="Copa Valle de Ciclomontañismo",
                    season=2026,
                    valida_num=4,
                    event_name="VALIDA IV CALI",
                    event_date=date(2026, 5, 17),
                    location="Cali",
                    actor=actor_user,
                    ctx=_ctx(actor_user),
                )
            assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# Carga histórica — inputs explícitos, nunca inferidos (FR-025)
# ---------------------------------------------------------------------------


class TestHistoricalStagingExplicitInputs:
    @pytest.mark.asyncio
    async def test_historical_file_uses_inputs_verbatim(
        self, db_session_factory, override_storage, actor_user, tmp_path
    ):
        """El PDF trae impreso un header (VALIDA III, otra fecha/sede) —
        igual que un acta histórica real. Los inputs del manifiesto ganan:
        el header impreso solo pre-rellena el formulario, nunca decide."""
        category = sequential_category("ELITE HOMBRES", 2)
        for i, row in enumerate(category.rows, start=1):
            row.bib = str(900 + i)

        # El PDF "dice" ser la válida III de Palmira, 2025-06-14 — un header
        # deliberadamente distinto del que declara el manifiesto histórico.
        pdf_bytes = _build_pdf(
            tmp_path,
            valida_num=3,
            location="Palmira",
            event_date=date(2025, 6, 14),
            categories=[category],
        )

        async with db_session_factory() as db:
            response = await stage_results_file(
                db,
                file_bytes=pdf_bytes,
                original_filename="copa_valle_2024_valida_7.pdf",
                results_ext="pdf",
                series_name="Copa Valle de Ciclomontañismo",
                season=2024,
                valida_num=7,
                event_name="VALIDA VII BUGA",
                event_date=date(2024, 11, 2),
                location="Buga",
                actor=actor_user,
                ctx=_ctx(actor_user),
            )
            await db.commit()

            # Los inputs ganan — nunca lo impreso.
            assert response.header.season == 2024
            assert response.header.valida_num == 7
            assert response.header.event_name == "VALIDA VII BUGA"

            imp = (
                await db.execute(
                    select(RaceImport).where(RaceImport.id == response.parse_id)
                )
            ).scalar_one()
            assert imp.parse_meta_json["header"]["season"] == 2024
            assert imp.parse_meta_json["header"]["valida_num"] == 7
            assert imp.parse_meta_json["header"]["event_date"] == "2024-11-02"
            assert imp.parse_meta_json["header"]["location"] == "Buga"

            series = (
                await db.execute(
                    select(RaceSeries).where(RaceSeries.id == imp.series_id)
                )
            ).scalar_one()
            assert series.season_year == 2024

    @pytest.mark.asyncio
    async def test_header_mismatch_warning_when_printed_header_disagrees(
        self, db_session_factory, override_storage, actor_user, tmp_path
    ):
        category = sequential_category("MASTER A", 2)
        pdf_bytes = _build_pdf(
            tmp_path,
            valida_num=3,
            location="Palmira",
            event_date=date(2025, 6, 14),
            categories=[category],
        )

        async with db_session_factory() as db:
            response = await stage_results_file(
                db,
                file_bytes=pdf_bytes,
                original_filename="copa_valle_2024_valida_7.pdf",
                results_ext="pdf",
                series_name="Copa Valle de Ciclomontañismo",
                season=2024,
                valida_num=7,
                event_name="VALIDA VII BUGA",
                event_date=date(2024, 11, 2),
                location="Buga",
                actor=actor_user,
                ctx=_ctx(actor_user),
            )
            await db.commit()

        codes = {w.code for w in response.warnings}
        assert "header_mismatch" in codes
        mismatch = next(w for w in response.warnings if w.code == "header_mismatch")
        assert set(mismatch.context["fields"]) == {
            "valida_num", "location", "event_date",
        }

    @pytest.mark.asyncio
    async def test_no_header_mismatch_when_inputs_match_printed_header(
        self, db_session_factory, override_storage, actor_user, tmp_path
    ):
        category = sequential_category("MASTER B1", 2)
        pdf_bytes = _build_pdf(
            tmp_path,
            valida_num=2,
            location="Tulua",
            event_date=date(2025, 3, 9),
            categories=[category],
        )

        async with db_session_factory() as db:
            response = await stage_results_file(
                db,
                file_bytes=pdf_bytes,
                original_filename="copa_valle_2025_valida_2.pdf",
                results_ext="pdf",
                series_name="Copa Valle de Ciclomontañismo",
                season=2025,
                valida_num=2,
                event_name="VALIDA II TULUA",
                event_date=date(2025, 3, 9),
                location="Tulua",
                actor=actor_user,
                ctx=_ctx(actor_user),
            )
            await db.commit()

        assert response.warnings == []


# ---------------------------------------------------------------------------
# FR-027 — re-stage de un archivo idéntico, aún pending: no crea nada
# ---------------------------------------------------------------------------


class TestRestageIdenticalFileCreatesNothing:
    @pytest.mark.asyncio
    async def test_restaging_identical_pending_file_returns_same_import(
        self, db_session_factory, override_storage, actor_user, tmp_path
    ):
        category = sequential_category("JUNIOR", 2)
        pdf_bytes = _build_pdf(
            tmp_path, valida_num=5, location="Cartago",
            event_date=date(2026, 7, 12), categories=[category],
        )
        kwargs = dict(
            file_bytes=pdf_bytes,
            original_filename="valida_5.pdf",
            results_ext="pdf",
            series_name="Copa Valle de Ciclomontañismo",
            season=2026,
            valida_num=5,
            event_name="VALIDA V CARTAGO",
            event_date=date(2026, 7, 12),
            location="Cartago",
            actor=actor_user,
            ctx=_ctx(actor_user),
        )

        async with db_session_factory() as db:
            first = await stage_results_file(db, **kwargs)
            await db.commit()

        async with db_session_factory() as db:
            before_count = (
                await db.execute(select(RaceImport))
            ).scalars().all()
            second = await stage_results_file(db, **kwargs)
            await db.commit()
            after_count = (
                await db.execute(select(RaceImport))
            ).scalars().all()

        assert second.parse_id == first.parse_id
        assert second.sha256 == first.sha256
        assert len(after_count) == len(before_count), (
            "re-stagear un archivo idéntico aún pending no debe crear una "
            "segunda fila race_imports (FR-027)"
        )
