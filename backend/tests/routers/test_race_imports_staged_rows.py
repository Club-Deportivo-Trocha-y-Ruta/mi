"""Tests del router — las rutas de revisión leen el documento stageado, sin
volver a tocar storage (feature 044, amendment 2026-09-26, T133 —
contracts/staged-import.md § "API deltas").

Cada carga en este archivo se stagea con
``tests/helpers/staging.py::stage_for_test`` (sin HTTP, sin PDF) y
``storage_sftp.download_to_tempfile`` queda monkeypatcheado para LANZAR —
si cualquier ruta bajo prueba intentara descargar el archivo original, el
test fallaría con esa excepción en vez de con el aserto real. Esto es la
prueba directa de FR-048/FR-049 ("el servidor nunca vuelve a leer el
archivo almacenado").

Privacidad: nombres/ciudades/clubes sintéticos (``FakeNameGenerator`` vía
``tests/helpers/staging.py``); ningún archivo real de la Federación.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.race_category import RaceCategory
from app.models.race_competitor import CompetitorSex
from app.models.race_import_staged_document import RaceImportStagedDocument
from app.models.user import User, UserRole
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.staging import (
    default_test_document,
    default_test_header,
    stage_for_test,
)

_IMPORTS_URL = "/api/race-analysis/imports"


def _make_user(role: UserRole, user_id: int, club_ids: tuple[int, ...] = (1,)) -> SimpleNamespace:
    from app.models.club import ClubRole as _ClubRole

    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"{role.value}{user_id}@test.local",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=cid, role_in_club=_ClubRole.coach) for cid in club_ids
        ],
    )


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
            "race_competitor_signatures",
            "race_identity_candidates",
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
            id=10, email="coach10@test.com", hashed_password="x",
            first_name="Coach", last_name="Ten",
            role=UserRole.coach, is_active=True, can_login=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        session.add(
            RaceCategory(
                code="INF_A", label="Infantil A", sex=CompetitorSex.M,
                age_min=10, age_max=11, tier="menores", sort_order=1, is_active=True,
            )
        )
        await session.commit()
    return user


@pytest.fixture
def override_storage(monkeypatch, tmp_path):
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
def storage_download_forbidden(monkeypatch):
    """FR-048/FR-049: ninguna ruta de revisión debe volver a descargar el
    archivo original. Si algo lo intenta, este stub lo delata de inmediato."""
    from app.services.training import storage_sftp

    async def _forbidden(*args, **kwargs):
        raise AssertionError(
            "download_to_tempfile llamado — una ruta de revisión volvió a "
            "leer el archivo almacenado (FR-048/FR-049 violado)"
        )

    monkeypatch.setattr(storage_sftp, "download_to_tempfile", _forbidden)


@pytest_asyncio.fixture
async def coach_client(sqlite_engine, db_session_factory, actor_user, override_storage, storage_download_forbidden):
    async def _override_db():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _make_user(UserRole.coach, 10, (1,))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _stage_pending(db_session_factory, actor_user, *, valida_num: int = 4) -> int:
    async with db_session_factory() as db:
        result = await stage_for_test(db, actor=actor_user, header=default_test_header(valida_num=valida_num))
        await db.commit()
        return result.import_id


async def _document_exists(db_session_factory, import_id: int) -> bool:
    async with db_session_factory() as db:
        row = (
            await db.execute(
                select(RaceImportStagedDocument).where(
                    RaceImportStagedDocument.import_id == import_id
                )
            )
        ).scalar_one_or_none()
        return row is not None


# ---------------------------------------------------------------------------
# dry-run / corrections / acknowledge / commit / commit-pending: todas leen
# el documento stageado, nunca storage.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_succeeds_from_the_staged_document(coach_client, db_session_factory, actor_user):
    import_id = await _stage_pending(db_session_factory, actor_user)

    r = await coach_client.post(f"{_IMPORTS_URL}/{import_id}/dry-run")

    assert r.status_code == 200, r.text
    assert r.json()["counts"]["total"] == 0  # sin atletas TyR en el club


@pytest.mark.asyncio
async def test_corrections_succeed_from_the_staged_document(coach_client, db_session_factory, actor_user):
    import_id = await _stage_pending(db_session_factory, actor_user)

    r = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/corrections",
        json={
            "op": "remove",
            "category_header": "INFANTIL A",
            "ordinal": 1,
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["category_header"] == "INFANTIL A"


@pytest.mark.asyncio
async def test_acknowledge_succeeds_from_the_staged_document(coach_client, db_session_factory, actor_user):
    """Rompemos la completitud primero (falta la posición 1) para que haya
    algo que reconocer."""
    doc = default_test_document(n_rows=3)
    doc.categories[0].rows = [
        row for row in doc.categories[0].rows if row.position != 1
    ]
    async with db_session_factory() as db:
        staged = await stage_for_test(db, doc, actor=actor_user)
        await db.commit()

    r = await coach_client.post(
        f"{_IMPORTS_URL}/{staged.import_id}/acknowledge",
        json={"category_header": "INFANTIL A", "reason": "source_missing_ordinal"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["completeness"]["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_commit_succeeds_from_the_staged_document_and_deletes_it(
    coach_client, db_session_factory, actor_user
):
    import_id = await _stage_pending(db_session_factory, actor_user)

    r = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/commit", json={"resolved_matches": []}
    )

    assert r.status_code == 200, r.text
    assert r.json()["n_results_inserted"] == 3
    assert r.json()["pending_categories"] == []
    assert not await _document_exists(db_session_factory, import_id)


@pytest.mark.asyncio
async def test_partial_commit_keeps_the_document_and_commit_pending_deletes_it(
    coach_client, db_session_factory, actor_user
):
    """Una categoría con un hueco en la numeración (research R-05) queda
    ``pending_categories`` en el primer commit — el documento se conserva.
    Reconocerla (motivo del catálogo cerrado) la hace elegible: el
    ``commit-pending`` siguiente la ingesta y borra el documento."""
    doc = default_test_document(n_rows=3)
    doc.categories[0].rows[1].position = 3  # 1, 3, 3 — hueco en el puesto 2
    async with db_session_factory() as db:
        staged = await stage_for_test(db, doc, actor=actor_user)
        await db.commit()
    import_id = staged.import_id

    first = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/commit", json={"resolved_matches": []}
    )
    assert first.status_code == 200, first.text
    assert first.json()["pending_categories"] == ["INFANTIL A"]
    assert first.json()["n_results_inserted"] == 0
    assert await _document_exists(db_session_factory, import_id), (
        "un commit parcial debe conservar el documento — commit-pending "
        "todavía lo necesita"
    )

    ack = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/acknowledge",
        json={"category_header": "INFANTIL A", "reason": "source_missing_ordinal"},
    )
    assert ack.status_code == 200, ack.text
    assert ack.json()["completeness"]["status"] == "acknowledged"

    pending = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/commit-pending", json={"resolved_matches": []}
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()["pending_categories"] == []
    assert pending.json()["n_results_inserted"] == 3
    assert not await _document_exists(db_session_factory, import_id), (
        "commit-pending que termina lo pendiente debe borrar el documento"
    )


@pytest.mark.asyncio
async def test_discard_deletes_the_staged_document(coach_client, db_session_factory, actor_user):
    import_id = await _stage_pending(db_session_factory, actor_user)

    r = await coach_client.post(f"{_IMPORTS_URL}/{import_id}/discard")

    assert r.status_code == 200, r.text
    assert not await _document_exists(db_session_factory, import_id)


@pytest.mark.asyncio
async def test_commit_pending_completion_deletes_the_document(
    coach_client, db_session_factory, actor_user
):
    """Dos categorías sanas: el primer commit las ingesta todas de una — no
    hay nada parcial que probar de ``commit-pending`` aquí más que su
    disponibilidad; se cubre en integración con la corrección real en
    ``test_race_imports_integrity.py``. Este test solo confirma que, tras un
    commit que NO deja nada pendiente, el documento ya no existe."""
    import_id = await _stage_pending(db_session_factory, actor_user)
    r = await coach_client.post(
        f"{_IMPORTS_URL}/{import_id}/commit", json={"resolved_matches": []}
    )
    assert r.status_code == 200, r.text
    assert r.json()["pending_categories"] == []
    assert not await _document_exists(db_session_factory, import_id)
