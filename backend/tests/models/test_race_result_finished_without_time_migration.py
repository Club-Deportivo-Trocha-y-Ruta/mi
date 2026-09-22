"""Migración ``b4e8d2f61a93`` — clasificado sin tiempo (feature 044, T024b).

Mismo patrón que ``test_race_signature_discriminator_migration.py``: corre
``upgrade()``/``downgrade()`` del archivo sobre un sqlite síncrono con el
esquema mínimo previo. Cubre: una sola cabeza; tras upgrade un ``finished``
sin tiempo ni vueltas entra y un ``dnf`` con tiempo sigue rechazado; el
downgrade se niega (solo con un conteo) mientras exista una fila así y
restituye el CHECK viejo cuando no.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "b4e8d2f61a93_race_result_finished_without_time.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_finished_without_time", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(mod, conn, fn: str) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        getattr(mod, fn)()


def _pre_schema(conn, mod) -> None:
    conn.execute(
        text(
            "CREATE TABLE race_results ("
            "id INTEGER PRIMARY KEY, status VARCHAR(20) NOT NULL, "
            "race_time_ms INTEGER, laps_behind SMALLINT, "
            f"CONSTRAINT {mod._CK} CHECK ({mod.OLD_RULE}))"
        )
    )


def _insert(conn, rid: int, status: str, time_ms: int | None, laps: int | None) -> None:
    conn.execute(
        text(
            "INSERT INTO race_results (id, status, race_time_ms, laps_behind) "
            "VALUES (:i, :s, :t, :l)"
        ),
        {"i": rid, "s": status, "t": time_ms, "l": laps},
    )


@pytest.fixture
def conn():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def test_single_head_on_previous_revision():
    mod = _load_migration()
    assert mod.down_revision == "a7c3e5d91f20"
    versions = MIGRATION_PATH.parent
    children = [
        p.name
        for p in versions.glob("*.py")
        if f'down_revision: Union[str, None] = "{mod.revision}"' in p.read_text()
    ]
    assert children == []


def test_old_rule_rejects_finished_without_time(conn):
    mod = _load_migration()
    _pre_schema(conn, mod)
    with pytest.raises(IntegrityError):
        _insert(conn, 1, "finished", None, None)


def test_upgrade_allows_finished_without_time_and_keeps_other_half(conn):
    mod = _load_migration()
    _pre_schema(conn, mod)
    _run(mod, conn, "upgrade")

    _insert(conn, 1, "finished", None, None)
    _insert(conn, 2, "finished", 3_600_000, None)
    _insert(conn, 3, "minus_laps", None, 1)
    with pytest.raises(IntegrityError):
        _insert(conn, 4, "dnf", 3_600_000, None)


def test_downgrade_refuses_with_finished_without_time_rows(conn):
    mod = _load_migration()
    _pre_schema(conn, mod)
    _run(mod, conn, "upgrade")
    _insert(conn, 1, "finished", None, None)

    with pytest.raises(RuntimeError) as excinfo:
        _run(mod, conn, "downgrade")
    assert "1 resultado(s)" in str(excinfo.value)


def test_downgrade_restores_old_rule(conn):
    mod = _load_migration()
    _pre_schema(conn, mod)
    _run(mod, conn, "upgrade")
    _run(mod, conn, "downgrade")

    with pytest.raises(IntegrityError):
        _insert(conn, 1, "finished", None, None)


def test_model_check_matches_migration_rule():
    """El modelo (lo que usa ``create_all`` en la lane sqlite) y la migración
    (lo que corre en MySQL) declaran la misma regla."""
    from app.models.race_result import RaceResult

    mod = _load_migration()
    (ck,) = [
        c for c in RaceResult.__table__.constraints if getattr(c, "name", None) == mod._CK
    ]
    assert " ".join(str(ck.sqltext).split()) == " ".join(mod.NEW_RULE.split())
