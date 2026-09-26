"""``app.services.race.staged_document`` (amendment 2026-09-26, T112).

Cubre lo que pide ``tasks.md`` T112:

- un ``save`` -> ``load`` conserva orden de categorías, ``code: null`` para
  un encabezado no reconocido, ``time_raw == ""`` y filas ilegibles;
- ``StagedDocumentMissing`` cuando no hay fila;
- ``delete`` es idempotente;
- ningún registro de log lleva un valor de fila (``caplog`` +
  ``assert_no_fake_names``).

SQLite en memoria con solo las tablas que hacen falta (``users``,
``race_series``, ``race_imports``, ``race_import_staged_documents``) —
mismo patrón que ``tests/test_race_imports_club_scope.py::sqlite_engine``.

Privacidad: los nombres/ciudades/clubes de este archivo vienen de
``tests.helpers.results_pdf_builder.FakeNameGenerator`` — nunca un dato
real.
"""
from __future__ import annotations

import logging
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

from app.models import Base
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_import_staged_document import RaceImportStagedDocument
from app.models.race_series import RaceSeries
from app.models.user import User, UserRole
from app.services.race.staged_document import (
    ParsedCategory,
    ParsedResults,
    ResultsRow,
    StagedDocumentMissing,
    StagedProfileMeta,
    UnreadableRow,
    delete,
    load,
    save,
)
from tests.helpers.name_sweep import assert_no_fake_names
from tests.helpers.results_pdf_builder import FakeNameGenerator


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
            "race_imports",
            "race_import_staged_documents",
        )
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(sqlite_engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(sqlite_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def imp(db: AsyncSession) -> RaceImport:
    """Un ``RaceImport`` ``pending`` mínimo, con su serie y su coach."""
    coach = User(
        id=1,
        email="coach1@example.test",
        first_name="Entrenador",
        last_name="Prueba",
        role=UserRole.coach,
        is_active=True,
        can_login=True,
    )
    series = RaceSeries(
        id=1,
        name="Serie Prueba T112",
        season_year=2026,
        points_scheme_code="uci_xco",
    )
    db.add_all([coach, series])
    await db.flush()

    race_import = RaceImport(
        filename="acta.pdf",
        sha256="a" * 64,
        series_id=series.id,
        status=RaceImportStatus.pending,
        imported_by_user_id=coach.id,
        imported_at=datetime.now(timezone.utc),
    )
    db.add(race_import)
    await db.flush()
    return race_import


def _profile_meta() -> StagedProfileMeta:
    return StagedProfileMeta(
        profile_id="copa-valle-results-pdf",
        profile_sha256="b" * 64,
        engine_version="results_skill@0.1.0",
    )


def _sample_document(gen: FakeNameGenerator) -> ParsedResults:
    """Categorías en un orden deliberado, con los cuatro casos que T112 pide
    cubrir: encabezado desconocido, sin tiempo, y una fila ilegible."""
    row_with_time = ResultsRow(
        position=1,
        bib="101",
        name=gen.next_name(),
        city=gen.next_city(),
        club=gen.next_club(),
        time_raw="0:41:07",
        points=50,
    )
    row_without_time = ResultsRow(
        position=2,
        bib="102",
        name=gen.next_name(),
        city=gen.next_city(),
        club=gen.next_club(),
        time_raw="",
        points=49,
    )
    return ParsedResults(
        categories=[
            ParsedCategory(header_raw="INFANTIL A", code="INF_A", rows=[row_with_time]),
            ParsedCategory(
                header_raw="ENCABEZADO RARO", code=None, rows=[row_without_time]
            ),
        ],
        unreadable_rows=[UnreadableRow(page=3, ordinal=12)],
    )


# ---------------------------------------------------------------------------
# save -> load round trip
# ---------------------------------------------------------------------------


async def test_save_then_load_round_trips_the_document(
    db: AsyncSession, imp: RaceImport
) -> None:
    gen = FakeNameGenerator()
    document = _sample_document(gen)

    await save(db, imp.id, document, _profile_meta())
    await db.commit()

    loaded = await load(db, imp)

    assert [c.header_raw for c in loaded.categories] == [
        "INFANTIL A",
        "ENCABEZADO RARO",
    ]
    assert loaded.categories[0].code == "INF_A"
    assert loaded.categories[1].code is None  # encabezado no reconocido
    assert loaded.categories[0].rows[0].time_raw == "0:41:07"
    assert loaded.categories[1].rows[0].time_raw == ""  # clasificado sin tiempo
    assert loaded.unreadable_rows == [UnreadableRow(page=3, ordinal=12)]

    # Los valores de fila coinciden exactamente con lo generado.
    assert loaded.categories[0].rows[0].name == document.categories[0].rows[0].name
    assert loaded.categories[0].rows[0].club == document.categories[0].rows[0].club


async def test_save_persists_profile_metadata(db: AsyncSession, imp: RaceImport) -> None:
    gen = FakeNameGenerator()
    document = _sample_document(gen)
    meta = _profile_meta()

    await save(db, imp.id, document, meta)
    await db.commit()

    row = await db.get(RaceImportStagedDocument, imp.id)
    assert row is not None
    assert row.profile_id == meta.profile_id
    assert row.profile_sha256 == meta.profile_sha256
    assert row.engine_version == meta.engine_version
    assert row.schema_version == 1


# ---------------------------------------------------------------------------
# StagedDocumentMissing
# ---------------------------------------------------------------------------


async def test_load_raises_staged_document_missing_when_no_row(
    db: AsyncSession, imp: RaceImport
) -> None:
    with pytest.raises(StagedDocumentMissing) as exc_info:
        await load(db, imp)
    assert exc_info.value.import_id == imp.id


# ---------------------------------------------------------------------------
# delete es idempotente
# ---------------------------------------------------------------------------


async def test_delete_is_idempotent(db: AsyncSession, imp: RaceImport) -> None:
    gen = FakeNameGenerator()
    await save(db, imp.id, _sample_document(gen), _profile_meta())
    await db.commit()

    await delete(db, imp.id)
    await db.commit()
    result = await db.execute(
        select(RaceImportStagedDocument).where(
            RaceImportStagedDocument.import_id == imp.id
        )
    )
    assert result.scalar_one_or_none() is None

    # Borrar de nuevo (o un import que nunca tuvo documento) no lanza.
    await delete(db, imp.id)
    await delete(db, 999_999)
    await db.commit()


# ---------------------------------------------------------------------------
# Ningún log lleva un valor de fila
# ---------------------------------------------------------------------------


async def test_no_log_record_carries_a_row_value(
    db: AsyncSession, imp: RaceImport, caplog: pytest.LogCaptureFixture
) -> None:
    gen = FakeNameGenerator()
    document = _sample_document(gen)

    with caplog.at_level(logging.INFO, logger="app.services.race.staged_document"):
        await save(db, imp.id, document, _profile_meta())
        await db.commit()
        await load(db, imp)
        await delete(db, imp.id)
        await db.commit()

    full_log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert_no_fake_names(full_log_text, gen)
