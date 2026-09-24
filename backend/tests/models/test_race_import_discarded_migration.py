"""Migración ``a76c264449a5`` — ``race_imports.status`` gana ``discarded``
(feature 045, US3, T024 — data-model §5).

Mismo patrón que ``test_race_result_finished_without_time_migration.py``: corre
``upgrade()``/``downgrade()`` del archivo sobre un sqlite síncrono. En SQLite la
columna es VARCHAR sin CHECK (el modelo declara el ``Enum`` sin
``create_constraint``), así que el ``MODIFY COLUMN`` del ENUM nativo es solo de
MySQL y aquí se prueba lo que es de todos los dialectos: una sola cabeza sobre
``b4e8d2f61a93``, el downgrade mapea ``discarded`` → ``failed`` sin tocar las
demás filas, y el modelo y la migración declaran el mismo valor. El ``ALTER``
real lo cubre ``tests/mysql/test_race_import_discarded_migration_mysql.py``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "a76c264449a5_race_import_discarded.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_race_import_discarded", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(mod, conn, fn: str) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        getattr(mod, fn)()


@pytest.fixture
def conn():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(
            text("CREATE TABLE race_imports (id INTEGER PRIMARY KEY, status VARCHAR(9) NOT NULL)")
        )
        yield connection
    engine.dispose()


def _statuses(conn) -> dict[int, str]:
    return {r[0]: r[1] for r in conn.execute(text("SELECT id, status FROM race_imports"))}


def test_single_head_on_previous_revision():
    mod = _load_migration()
    assert mod.down_revision == "b4e8d2f61a93"
    children = [
        p.name
        for p in MIGRATION_PATH.parent.glob("*.py")
        if f'down_revision: Union[str, None] = "{mod.revision}"' in p.read_text()
    ]
    # Única sucesora conocida: be4595de1ad2 (feature 046, pliegues cutáneos).
    assert children in ([], ["be4595de1ad2_skinfold_measurements_and_fuprecol_lms.py"])


def test_upgrade_is_a_no_op_on_sqlite(conn):
    conn.execute(text("INSERT INTO race_imports VALUES (1, 'pending'), (2, 'committed')"))
    _run(_load_migration(), conn, "upgrade")
    assert _statuses(conn) == {1: "pending", 2: "committed"}


def test_downgrade_maps_discarded_to_failed_and_keeps_the_rest(conn):
    conn.execute(
        text(
            "INSERT INTO race_imports VALUES "
            "(1, 'pending'), (2, 'discarded'), (3, 'committed'), (4, 'discarded'), (5, 'failed')"
        )
    )
    _run(_load_migration(), conn, "downgrade")
    assert _statuses(conn) == {
        1: "pending",
        2: "failed",
        3: "committed",
        4: "failed",
        5: "failed",
    }


def test_model_enum_gains_discarded_stored_as_its_value():
    """El modelo (lo que crea el esquema en la lane sqlite) declara el mismo
    valor que agrega la migración, con ``values_callable`` como los demás enums."""
    from app.models.race_import import RaceImport, RaceImportStatus

    mod = _load_migration()
    assert RaceImportStatus.discarded.value == "discarded"
    enum_type = RaceImport.__table__.c.status.type
    assert list(enum_type.enums) == list(mod.STATUS_VALUES_WITH_DISCARDED)
    assert "discarded" not in mod.STATUS_VALUES_WITHOUT_DISCARDED
