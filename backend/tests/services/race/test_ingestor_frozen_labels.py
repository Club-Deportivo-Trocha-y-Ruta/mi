"""T026 — columnas congeladas de categoría en ``race_results`` (feature 044, US2).

Contrato: ``specs/044-race-history-backfill/contracts/category-mapping.md``
(secciones "Ingestor" y "Tests") y ``research.md`` R-04.

TDD: al escribir este archivo, ``app/models/race_result.py`` ya tiene las
tres columnas (``category_label_raw``, ``category_age_min_raw``,
``category_age_max_raw``) y la migración ``8efe1618cb83`` ya existe con su
backfill — pero ``RaceIngestor.ingest_event`` todavía NO las escribe al
insertar (T029, agente fastapi-architect, pendiente). Los tests 1-3 deben
fallar hoy por eso — las columnas quedan en ``NULL`` — no por un error de
este archivo.

Cobertura (calco de la petición T026):
1. ``test_ingest_writes_frozen_columns_from_catalogue_at_insert_time`` —
   insertar vía el ingestor puebla las tres columnas con los valores del
   catálogo vigente en ese momento.
2. ``test_frozen_columns_survive_catalogue_edit`` — editar la fila del
   catálogo (label + age_min) DESPUÉS del insert no cambia lo ya congelado.
3. ``test_frozen_columns_survive_revision_update`` — una revisión que
   actualiza un ``RaceResult`` existente (``compute_diff`` + ``commit_revision``,
   acción ``update``) tampoco las toca: ``_apply_update`` sólo escribe los 5
   campos de ``revision._DIFF_FIELDS`` (``position``, ``status``,
   ``race_time_ms``, ``laps_behind``, ``points_awarded``), ninguno de los
   cuales es una columna congelada. Nota para el reporte: el docstring de
   ``RaceResult`` dice que la revisión "inserta filas nuevas, no las edita" —
   eso sólo es cierto para acción ``create``; una acción ``update`` sí muta la
   fila existente in-place (revision.py ``_apply_update``). El resultado que
   importa (columnas congeladas intactas) se sostiene de todos modos, por una
   razón distinta a la que dice el docstring.
4. ``TestMigrationBackfillIdempotent`` — el SQL de backfill de la migración
   ``8efe1618cb83`` puebla filas preexistentes con ``category_label_raw IS
   NULL`` desde el catálogo, y no pisa una fila que ya tiene el valor escrito
   (idempotencia vía el propio ``WHERE ... IS NULL`` del backfill).

Privacidad: nombres ficticios ("Ana Ficticia", "Leo Ficticio").
"""
from __future__ import annotations

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.race_category import RaceCategory
from app.models.race_event import SurfaceCondition
from app.models.race_import import RaceImport, RaceImportStatus
from app.models.race_result import RaceResult
from app.schemas.race import EventMeta
from app.services.race import revision as revision_svc
from app.services.race.ingestor import RaceIngestor
from app.services.race.pdf_parser import ResultsRow

from tests.fixtures.race_history_fixtures import create_race_category, create_user
from tests.helpers.audit_tables import AUDIT_TABLES

#: ``race_result_revisions`` se crea aparte con DDL crudo (ver ``engine``) —
#: no entra en ``Base.metadata.create_all(tables=...)``.
_TABLES_NEEDED = [
    "users",
    "race_series",
    "race_events",
    "race_categories",
    "race_competitors",
    "race_results",
    "race_imports",
    *AUDIT_TABLES,
]


# ---------------------------------------------------------------------------
# Fixtures — SQLite async in-memory (mismo patrón que
# tests/routers/test_event_revision_diff.py)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES_NEEDED]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        # ``race_result_revisions.id`` es ``BigInteger`` en el modelo real.
        # SQLite sólo activa el alias rowid/autoincrement para el token exacto
        # ``INTEGER PRIMARY KEY`` — un ``BIGINT PRIMARY KEY`` (misma afinidad,
        # pero no el alias) se queda sin default y el INSERT falla con
        # ``NOT NULL constraint failed`` porque ``commit_revision()`` nunca
        # pasa ``id=`` explícito (confía en la DB). Este DDL crudo, SOLO para
        # este engine desechable de este archivo, evita tocar
        # ``Base.metadata`` compartido (mutarlo in-place afectaría a
        # cualquier otro test que importe el mismo modelo en el mismo proceso
        # de pytest). Ningún test existente invoca ``commit_revision()`` hoy —
        # ver hallazgo en el reporte de T026.
        await conn.execute(
            text(
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
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _meta(valida_num: int = 4, season: int = 2026) -> EventMeta:
    return EventMeta(
        season=season,
        valida_num=valida_num,
        name=f"Valida {valida_num}",
        event_date=date(season, 5, 17),
        location="Cali",
        climate=None,
        temperature_c=Decimal("25.0"),
        surface_condition=SurfaceCondition.seca,
    )


def _row(
    pos: int, bib: str, name: str, club: str, time_raw: str, points: int
) -> ResultsRow:
    return ResultsRow(
        position=pos, bib=bib, name=name, city="Yumbo", club=club,
        time_raw=time_raw, points=points,
    )


# ---------------------------------------------------------------------------
# 1-2. Insert congela; edición posterior del catálogo no lo cambia
# ---------------------------------------------------------------------------


class TestFrozenColumnsAtInsert:
    @pytest.mark.asyncio
    async def test_ingest_writes_frozen_columns_from_catalogue_at_insert_time(
        self, session_factory
    ):
        from app.models.user import UserRole

        async with session_factory() as db:
            await create_user(db, user_id=10, role=UserRole.coach)
            category = await create_race_category(
                db,
                category_id=100,
                code="INF_B",
                label="Infantil B",
                age_min=11,
                age_max=12,
            )
            await db.commit()

            ingestor = RaceIngestor(db)
            await ingestor.ingest_event(
                meta=_meta(),
                results_by_category={
                    "INF_B": [
                        _row(1, "501", "Ana Ficticia", "Club Trocha y Ruta", "0:20:00", 40),
                    ]
                },
                ingested_by_user_id=10,
            )

            result = (
                await db.execute(select(RaceResult).where(RaceResult.category_id == category.id))
            ).scalar_one()

            assert result.category_label_raw == category.label
            assert result.category_age_min_raw == 11
            assert result.category_age_max_raw == 12

    @pytest.mark.asyncio
    async def test_frozen_columns_survive_catalogue_edit(self, session_factory):
        async with session_factory() as db:
            from app.models.user import UserRole

            await create_user(db, user_id=10, role=UserRole.coach)
            category = await create_race_category(
                db,
                category_id=100,
                code="INF_B",
                label="Infantil B",
                age_min=11,
                age_max=12,
            )
            await db.commit()

            ingestor = RaceIngestor(db)
            await ingestor.ingest_event(
                meta=_meta(),
                results_by_category={
                    "INF_B": [
                        _row(1, "501", "Ana Ficticia", "Club Trocha y Ruta", "0:20:00", 40),
                    ]
                },
                ingested_by_user_id=10,
            )

            result = (
                await db.execute(select(RaceResult).where(RaceResult.category_id == category.id))
            ).scalar_one()
            frozen_label = result.category_label_raw
            frozen_age_min = result.category_age_min_raw
            frozen_age_max = result.category_age_max_raw
            assert frozen_label is not None, (
                "Precondición: el insert debe haber congelado un label — si "
                "esto falla, T029 aún no escribe las columnas (esperado hoy)."
            )

            # Editar el catálogo DESPUÉS del insert — como haría el coach vía
            # un futuro admin de categorías, o el seed re-corriendo con datos
            # corregidos.
            cat_row = (
                await db.execute(select(RaceCategory).where(RaceCategory.id == category.id))
            ).scalar_one()
            cat_row.label = "Infantil B (renombrada)"
            cat_row.age_min = 99
            cat_row.age_max = 100
            await db.flush()

            reloaded = (
                await db.execute(select(RaceResult).where(RaceResult.id == result.id))
            ).scalar_one()
            assert reloaded.category_label_raw == frozen_label
            assert reloaded.category_age_min_raw == frozen_age_min
            assert reloaded.category_age_max_raw == frozen_age_max
            # Y explícitamente divergen del catálogo editado — no es una
            # columna calculada al vuelo.
            assert reloaded.category_label_raw != cat_row.label
            assert reloaded.category_age_min_raw != cat_row.age_min


# ---------------------------------------------------------------------------
# 3. Una revisión (update in-place) tampoco las toca
# ---------------------------------------------------------------------------


class TestFrozenColumnsSurviveRevision:
    @pytest.mark.asyncio
    async def test_frozen_columns_survive_revision_update(self, session_factory):
        from app.models.user import UserRole

        async with session_factory() as db:
            await create_user(db, user_id=10, role=UserRole.coach)
            category = await create_race_category(
                db,
                category_id=100,
                code="INF_B",
                label="Infantil B",
                age_min=11,
                age_max=12,
            )
            await db.commit()

            # --- Primer commit: crea el RaceResult original -----------------
            ingestor = RaceIngestor(db)
            first_sha = "a" * 64
            await ingestor.ingest_event(
                meta=_meta(),
                results_by_category={
                    "INF_B": [
                        _row(1, "501", "Ana Ficticia", "Club Trocha y Ruta", "0:20:00", 40),
                    ]
                },
                pdf_results_sha256=first_sha,
                ingested_by_user_id=10,
            )

            original = (
                await db.execute(select(RaceResult).where(RaceResult.category_id == category.id))
            ).scalar_one()
            frozen_label = original.category_label_raw
            frozen_age_min = original.category_age_min_raw
            frozen_age_max = original.category_age_max_raw
            assert frozen_label is not None, (
                "Precondición: el insert debe congelar un label antes de "
                "poder probar que la revisión no lo toca."
            )

            # --- Detectar revisión sobre la misma válida ---------------------
            ctx = await revision_svc.detect_revision(
                db,
                series_name="Copa Valle de Ciclomontañismo",
                season=2026,
                valida_num=4,
            )
            assert ctx is not None, "Debe detectar el import committed previo."

            # --- PDF "nuevo" con el MISMO corredor pero tiempo distinto ------
            # (misma normalized_name + categoría → acción "update", NO "create").
            new_parsed = {
                "INF_B": [
                    _row(1, "501", "Ana Ficticia", "Club Trocha y Ruta", "0:21:00", 38),
                ]
            }
            diff = await revision_svc.compute_diff(db, new_parsed, ctx.parent_event_id)
            assert diff.summary.n_update == 1, (
                "El diff debe clasificar el cambio de tiempo como update, no "
                "create/delete — si no, el resto del test no prueba lo que dice."
            )

            from app.models.race_event import RaceEvent

            event_series_id = (
                await db.execute(
                    select(RaceEvent.series_id).where(RaceEvent.id == ctx.parent_event_id)
                )
            ).scalar_one()

            parse_import = RaceImport(
                filename="valida_4_resultados_v2.pdf",
                sha256="b" * 64,
                series_id=event_series_id,
                status=RaceImportStatus.pending,
                stats_json={},
                imported_by_user_id=10,
            )
            db.add(parse_import)
            await db.flush()

            await revision_svc.commit_revision(
                db,
                parse_import=parse_import,
                revision_context=ctx,
                diff_report=diff,
                revision_reason=None,
                changed_by_user_id=10,
            )
            await db.commit()

            reloaded = (
                await db.execute(select(RaceResult).where(RaceResult.id == original.id))
            ).scalar_one()
            # El campo SÍ cambió (prueba que la revisión de verdad se aplicó)…
            assert reloaded.race_time_ms != original.race_time_ms or reloaded.points_awarded != 40
            # …pero las columnas congeladas NO.
            assert reloaded.category_label_raw == frozen_label
            assert reloaded.category_age_min_raw == frozen_age_min
            assert reloaded.category_age_max_raw == frozen_age_max


# ---------------------------------------------------------------------------
# 4. Migración 8efe1618cb83 — backfill de filas preexistentes, idempotente
# ---------------------------------------------------------------------------


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "8efe1618cb83_race_history_backfill.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "mig_race_history_backfill", _MIGRATION_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _create_minimal_schema(conn) -> None:
    conn.execute(
        text(
            "CREATE TABLE race_categories ("
            "id INTEGER PRIMARY KEY, label VARCHAR(100), age_min SMALLINT, age_max SMALLINT"
            ")"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE race_results ("
            "id INTEGER PRIMARY KEY, category_id INTEGER, "
            "category_label_raw VARCHAR(100), category_age_min_raw SMALLINT, "
            "category_age_max_raw SMALLINT"
            ")"
        )
    )


class TestMigrationBackfillIdempotent:
    def test_backfill_fills_preexisting_null_rows(self):
        mod = _load_migration_module()
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            _create_minimal_schema(conn)
            conn.execute(
                text(
                    "INSERT INTO race_categories (id, label, age_min, age_max) "
                    "VALUES (1, 'Infantil B', 11, 12)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO race_results (id, category_id, category_label_raw, "
                    "category_age_min_raw, category_age_max_raw) "
                    "VALUES (1, 1, NULL, NULL, NULL)"
                )
            )
            conn.execute(text(mod.BACKFILL_FROZEN_CATEGORY_SQL))

            row = conn.execute(
                text(
                    "SELECT category_label_raw, category_age_min_raw, category_age_max_raw "
                    "FROM race_results WHERE id = 1"
                )
            ).one()
            assert row[0] == "Infantil B"
            assert row[1] == 11
            assert row[2] == 12
        engine.dispose()

    def test_backfill_never_overwrites_an_already_frozen_row(self):
        """El WHERE ... IS NULL del backfill hace que un re-run sea inocuo —
        crítico porque el ingestor (T029) empezará a escribir estas columnas
        en el INSERT, y un ``alembic upgrade`` posterior (o un re-run
        defensivo) nunca debe pisar lo que el ingestor ya congeló."""
        mod = _load_migration_module()
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            _create_minimal_schema(conn)
            conn.execute(
                text(
                    "INSERT INTO race_categories (id, label, age_min, age_max) "
                    "VALUES (1, 'Infantil B (2026)', 9, 10)"
                )
            )
            # Fila que un ingest post-044 ya congeló con el header IMPRESO
            # (deliberadamente distinto del label actual del catálogo).
            conn.execute(
                text(
                    "INSERT INTO race_results (id, category_id, category_label_raw, "
                    "category_age_min_raw, category_age_max_raw) "
                    "VALUES (2, 1, 'INFANTIL B', 11, 12)"
                )
            )
            conn.execute(text(mod.BACKFILL_FROZEN_CATEGORY_SQL))

            row = conn.execute(
                text(
                    "SELECT category_label_raw, category_age_min_raw, category_age_max_raw "
                    "FROM race_results WHERE id = 2"
                )
            ).one()
            assert row[0] == "INFANTIL B"
            assert row[1] == 11
            assert row[2] == 12
        engine.dispose()
