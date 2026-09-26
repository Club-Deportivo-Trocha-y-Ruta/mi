"""Tests de ``app.services.race.import_staging.stage_extracted_results``
(feature 044, US5 amended 2026-09-26 — contracts/staged-import.md § Tests).

Reemplaza el archivo previo (T056/T131): ``stage_extracted_results`` no
parsea nada — recibe un ``ParsedResults`` ya extraído — así que estos tests
llaman el servicio DIRECTAMENTE con documentos sintéticos
(``tests/helpers/staging.py::stage_for_test``), sin PDF/WeasyPrint ni HTTP.

``stage_results_file`` (el flujo legado detrás de ``POST /parse``, aún vivo
para no romper el wizard de temporada corriente) sigue teniendo su propia
cobertura en los tests de router — este archivo es ahora exclusivamente de
``stage_extracted_results``.

Privacidad: todos los nombres son sintéticos (``FakeNameGenerator``); ningún
archivo real de la Federación se usa ni se genera aquí.
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
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_import_staged_document import RaceImportStagedDocument
from app.models.race_series import RaceSeries, RaceSeriesKind
from app.models.user import User, UserRole
from app.services.race.import_staging import _STAGE_PUBLIC_META_KEYS
from app.services.race.staged_document import (
    ParsedCategory,
    ParsedResults,
    document_from_json,
)
from app.services.request_context import AuditContext
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.staging import (
    DEFAULT_TEST_PROFILE,
    default_test_document,
    default_test_header,
    stage_for_test,
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
            "race_import_staged_documents",
            "race_categories",
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


# ---------------------------------------------------------------------------
# Staging básico
# ---------------------------------------------------------------------------


class TestStageCreatesPendingImport:
    @pytest.mark.asyncio
    async def test_stage_creates_pending_import_with_document_row(
        self, db_session_factory, override_storage, actor_user
    ):
        async with db_session_factory() as db:
            result = await stage_for_test(db, actor=actor_user)
            await db.commit()

            assert result.status == "pending"
            assert result.n_rows == 3
            assert result.n_categories == 1
            assert result.already_committed is False
            assert result.is_revision is False

            imp = (
                await db.execute(
                    select(RaceImport).where(RaceImport.id == result.import_id)
                )
            ).scalar_one()
            assert imp.status == RaceImportStatus.pending
            assert imp.kind == RaceImportKind.resultados
            assert imp.imported_by_user_id == actor_user.id
            assert imp.parse_meta_json["n_rows_resultados"] == 3
            assert imp.parse_meta_json["n_rows_general"] == 0
            assert imp.parse_meta_json["categories"][0]["rows"] == 3

            doc_row = (
                await db.execute(
                    select(RaceImportStagedDocument).where(
                        RaceImportStagedDocument.import_id == result.import_id
                    )
                )
            ).scalar_one()
            document = document_from_json(doc_row.document_json)
            assert len(document.categories) == 1
            assert len(document.categories[0].rows) == 3
            assert doc_row.profile_id == DEFAULT_TEST_PROFILE.profile_id

    @pytest.mark.asyncio
    async def test_conditions_are_all_null_and_kind_is_resultados(
        self, db_session_factory, override_storage, actor_user
    ):
        async with db_session_factory() as db:
            result = await stage_for_test(db, actor=actor_user)
            await db.commit()
            imp = (
                await db.execute(
                    select(RaceImport).where(RaceImport.id == result.import_id)
                )
            ).scalar_one()
            conditions = imp.parse_meta_json["conditions"]
            assert conditions == {
                "climate": None,
                "temperature_c": None,
                "surface_condition": None,
                "altitude_msnm": None,
                "weather_notes": None,
            }
            assert imp.kind == RaceImportKind.resultados
            assert imp.parse_meta_json["n_rows_general"] == 0

    @pytest.mark.asyncio
    async def test_public_meta_keys_match_contract(
        self, db_session_factory, override_storage, actor_user
    ):
        async with db_session_factory() as db:
            result = await stage_for_test(db, actor=actor_user)
            await db.commit()
            imp = (
                await db.execute(
                    select(RaceImport).where(RaceImport.id == result.import_id)
                )
            ).scalar_one()
            expected = set(_STAGE_PUBLIC_META_KEYS) | {
                "results_ext",
                "results_storage_path",
                "parse_uuid",
                "source",
                "profile_id",
            }
            assert set(imp.parse_meta_json.keys()) == expected

    @pytest.mark.asyncio
    async def test_audit_row_carries_via_results_skill(
        self, db_session_factory, override_storage, actor_user
    ):
        from app.models.audit_log import AuditLog

        async with db_session_factory() as db:
            result = await stage_for_test(db, actor=actor_user)
            await db.commit()
            audit_row = (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.entity_id == result.import_id,
                        AuditLog.entity_type == "race_import",
                    )
                )
            ).scalar_one()
            assert (audit_row.meta_json or {}).get("via") == "results_skill"

    @pytest.mark.asyncio
    async def test_imported_at_comes_from_database_clock(
        self, db_session_factory, override_storage, actor_user, monkeypatch
    ):
        """``imported_at`` viene de ``func.now()`` (reloj de la BD), no del
        reloj Python del proceso — congelamos este último y comprobamos que
        difiere."""
        frozen = datetime(2000, 1, 1, tzinfo=timezone.utc)

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return frozen if tz is None else frozen.astimezone(tz)

        import app.models.race_import as race_import_module

        monkeypatch.setattr(race_import_module, "datetime", _FrozenDatetime)

        async with db_session_factory() as db:
            result = await stage_for_test(db, actor=actor_user)
            await db.commit()
            imp = (
                await db.execute(
                    select(RaceImport).where(RaceImport.id == result.import_id)
                )
            ).scalar_one()
            assert imp.imported_at is not None
            assert imp.imported_at.replace(tzinfo=timezone.utc) != frozen


# ---------------------------------------------------------------------------
# Documento vacío
# ---------------------------------------------------------------------------


class TestEmptyDocumentRefused:
    @pytest.mark.asyncio
    async def test_empty_document_raises_422_empty_document(
        self, db_session_factory, override_storage, actor_user
    ):
        from fastapi import HTTPException

        empty_doc = ParsedResults(categories=[], unreadable_rows=[])
        async with db_session_factory() as db:
            with pytest.raises(HTTPException) as exc_info:
                await stage_for_test(db, document=empty_doc, actor=actor_user)
            assert exc_info.value.status_code == 422
            assert exc_info.value.detail["code"] == "empty_document"

            # Nada quedó creado.
            rows = (await db.execute(select(RaceImport))).scalars().all()
            assert rows == []

    @pytest.mark.asyncio
    async def test_category_with_zero_rows_is_also_empty(
        self, db_session_factory, override_storage, actor_user
    ):
        from fastapi import HTTPException

        doc = ParsedResults(
            categories=[ParsedCategory(header_raw="SIN FILAS", code=None, rows=[])],
            unreadable_rows=[],
        )
        async with db_session_factory() as db:
            with pytest.raises(HTTPException) as exc_info:
                await stage_for_test(db, document=doc, actor=actor_user)
            assert exc_info.value.status_code == 422
            assert exc_info.value.detail["code"] == "empty_document"


# ---------------------------------------------------------------------------
# Dedupe (FR-027) — pending y committed
# ---------------------------------------------------------------------------


class TestDedupe:
    @pytest.mark.asyncio
    async def test_restaging_identical_pending_file_returns_same_import(
        self, db_session_factory, override_storage, actor_user
    ):
        doc = default_test_document()
        header = default_test_header(valida_num=5)
        file_bytes = b"contenido-identico-para-dedupe"

        async with db_session_factory() as db:
            first = await stage_for_test(
                db, doc, header, actor_user, file_bytes=file_bytes
            )
            await db.commit()

        async with db_session_factory() as db:
            before = (await db.execute(select(RaceImport))).scalars().all()
            second = await stage_for_test(
                db, doc, header, actor_user, file_bytes=file_bytes
            )
            await db.commit()
            after = (await db.execute(select(RaceImport))).scalars().all()

        assert second.import_id == first.import_id
        assert second.status == "pending"
        assert len(after) == len(before), (
            "re-stagear un archivo idéntico aún pending no debe crear una "
            "segunda fila race_imports (FR-027)"
        )

    @pytest.mark.asyncio
    async def test_restaging_identical_committed_file_returns_already_committed(
        self, db_session_factory, override_storage, actor_user
    ):
        doc = default_test_document()
        header = default_test_header(valida_num=6)
        file_bytes = b"contenido-ya-commiteado"

        async with db_session_factory() as db:
            staged = await stage_for_test(
                db, doc, header, actor_user, file_bytes=file_bytes
            )
            await db.commit()

        async with db_session_factory() as db:
            imp = (
                await db.execute(
                    select(RaceImport).where(RaceImport.id == staged.import_id)
                )
            ).scalar_one()
            imp.status = RaceImportStatus.committed
            await db.commit()

        async with db_session_factory() as db:
            before = (await db.execute(select(RaceImport))).scalars().all()
            result = await stage_for_test(
                db, doc, header, actor_user, file_bytes=file_bytes
            )
            await db.commit()
            after = (await db.execute(select(RaceImport))).scalars().all()

        assert result.status == "already_committed"
        assert result.already_committed is True
        assert result.import_id == staged.import_id
        assert len(after) == len(before)


# ---------------------------------------------------------------------------
# Fallos — upload y transacción no dejan huérfanos
# ---------------------------------------------------------------------------


class TestFailureLeavesNoOrphan:
    @pytest.mark.asyncio
    async def test_upload_failure_leaves_no_import(
        self, db_session_factory, override_storage, actor_user, monkeypatch
    ):
        from app.services.training import storage_sftp

        async def _boom(*args, **kwargs):
            raise OSError("disco lleno (simulado)")

        monkeypatch.setattr(storage_sftp, "upload_bytes", _boom)

        async with db_session_factory() as db:
            with pytest.raises(OSError):
                await stage_for_test(db, actor=actor_user)
            rows = (await db.execute(select(RaceImport))).scalars().all()
            assert rows == []
            docs = (
                await db.execute(select(RaceImportStagedDocument))
            ).scalars().all()
            assert docs == []

    @pytest.mark.asyncio
    async def test_transaction_failure_deletes_uploaded_object_and_leaves_no_rows(
        self, db_session_factory, override_storage, actor_user, monkeypatch
    ):
        from app.services.race import staged_document as staged_document_module
        from app.services.training import storage_sftp

        deleted_paths: list[str] = []
        real_delete = storage_sftp.delete_object

        async def _tracking_delete(storage_path: str) -> None:
            deleted_paths.append(storage_path)
            await real_delete(storage_path)

        async def _boom_save(*args, **kwargs):
            raise RuntimeError("fallo simulado en el insert del documento")

        monkeypatch.setattr(storage_sftp, "delete_object", _tracking_delete)
        monkeypatch.setattr(staged_document_module, "save", _boom_save)

        async with db_session_factory() as db:
            with pytest.raises(RuntimeError):
                await stage_for_test(db, actor=actor_user)
            rows = (await db.execute(select(RaceImport))).scalars().all()
            assert rows == []
            docs = (
                await db.execute(select(RaceImportStagedDocument))
            ).scalars().all()
            assert docs == []

        assert len(deleted_paths) == 1


# ---------------------------------------------------------------------------
# Revisión — un import committed previo de la misma (serie, válida)
# ---------------------------------------------------------------------------


class TestRevisionDetection:
    @pytest.mark.asyncio
    async def test_different_reading_of_committed_valida_is_flagged_revision(
        self, db_session_factory, override_storage, actor_user
    ):
        from app.models.race_event import RaceEvent

        header = default_test_header(season=2026, valida_num=7)

        async with db_session_factory() as db:
            series = RaceSeries(
                name=header.series_name,
                season_year=header.season,
                organizer="Liga Vallecaucana de Ciclismo",
                points_scheme_code="copa_valle_2026",
                kind=RaceSeriesKind.cup,
            )
            db.add(series)
            await db.flush()
            event = RaceEvent(
                series_id=series.id,
                sequence_number=header.valida_num,
                name=header.event_name,
                event_date=header.event_date,
                location=header.location,
                created_by_user_id=actor_user.id,
            )
            db.add(event)
            await db.flush()
            prior_import = RaceImport(
                filename="prev.pdf",
                sha256="a" * 64,
                series_id=series.id,
                status=RaceImportStatus.committed,
                stats_json={},
                imported_by_user_id=actor_user.id,
                event_id=event.id,
                committed_at=datetime.now(timezone.utc),
                committed_by_user_id=actor_user.id,
            )
            db.add(prior_import)
            await db.commit()

            result = await stage_for_test(
                db,
                default_test_document(),
                header,
                actor_user,
                file_bytes=b"un-archivo-diferente-de-la-misma-valida",
            )
            await db.commit()

        assert result.is_revision is True
        assert result.parent_import_id == prior_import.id
