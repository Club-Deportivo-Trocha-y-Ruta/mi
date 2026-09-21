"""Migración ``a7c3e5d91f20`` — discriminador de firmas (feature 044,
decisión del dueño 2026-09-21 "separar por categoría").

Corre ``upgrade()``/``downgrade()`` del archivo de la revisión sobre un sqlite
síncrono con el esquema mínimo previo (la tabla tal como la deja
``8efe1618cb83``), vía ``Operations.context`` — mismo patrón que
``test_athlete_ai_insight_scope_key_migration.py``. Cubre: una sola cabeza
con ``down_revision`` correcto; tras upgrade conviven dos firmas de la misma
terna con discriminador distinto y la cuaterna repetida colisiona; el
downgrade vuelve al UNIQUE de la terna y se niega (sin nombrar a nadie) si
dos firmas comparten terna.
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
    / "a7c3e5d91f20_race_signature_discriminator.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_signature_discriminator", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(mod, conn, fn: str) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        getattr(mod, fn)()


def _pre_schema(conn) -> None:
    conn.execute(
        text(
            "CREATE TABLE race_competitor_signatures ("
            "id INTEGER PRIMARY KEY, competitor_id INTEGER NOT NULL, "
            "normalized_name VARCHAR(160) NOT NULL, "
            "club_norm VARCHAR(150) NOT NULL DEFAULT '', "
            "city_norm VARCHAR(100) NOT NULL DEFAULT '', "
            "first_season SMALLINT NOT NULL, last_season SMALLINT NOT NULL, "
            "source_candidate_id INTEGER, created_at DATETIME, "
            "CONSTRAINT uq_race_competitor_signatures_triple "
            "UNIQUE (normalized_name, club_norm, city_norm))"
        )
    )


def _insert(conn, sig_id: int, competitor_id: int, disc: str | None = None) -> None:
    if disc is None:
        conn.execute(
            text(
                "INSERT INTO race_competitor_signatures "
                "(id, competitor_id, normalized_name, club_norm, city_norm, first_season, last_season) "
                "VALUES (:i, :c, 'mateo ficticio igual', 'club andino', 'cali', 2025, 2025)"
            ),
            {"i": sig_id, "c": competitor_id},
        )
    else:
        conn.execute(
            text(
                "INSERT INTO race_competitor_signatures "
                "(id, competitor_id, normalized_name, club_norm, city_norm, discriminator, "
                "first_season, last_season) "
                "VALUES (:i, :c, 'mateo ficticio igual', 'club andino', 'cali', :d, 2025, 2025)"
            ),
            {"i": sig_id, "c": competitor_id, "d": disc},
        )


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    with eng.connect() as conn:
        _pre_schema(conn)
        _insert(conn, 1, 10)
        conn.commit()
    yield eng
    eng.dispose()


def test_migration_metadata():
    mod = _load_migration()
    assert mod.revision == "a7c3e5d91f20"
    assert mod.down_revision == "8efe1618cb83"


def test_upgrade_allows_same_triple_with_distinct_discriminator(engine):
    mod = _load_migration()
    with engine.connect() as conn:
        _run(mod, conn, "upgrade")
        conn.commit()
        assert conn.execute(
            text("SELECT discriminator FROM race_competitor_signatures WHERE id = 1")
        ).scalar_one() == ""
        _insert(conn, 2, 11, "M:9-10@2025")
        conn.commit()
        with pytest.raises(IntegrityError):
            _insert(conn, 3, 11, "M:9-10@2025")
        conn.rollback()


def test_downgrade_restores_the_triple_unique(engine):
    mod = _load_migration()
    with engine.connect() as conn:
        _run(mod, conn, "upgrade")
        _run(mod, conn, "downgrade")
        conn.commit()
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(race_competitor_signatures)"))]
        assert "discriminator" not in cols
        with pytest.raises(IntegrityError):
            _insert(conn, 2, 11)
        conn.rollback()


def test_downgrade_refuses_when_a_triple_has_two_signatures(engine):
    mod = _load_migration()
    with engine.connect() as conn:
        _run(mod, conn, "upgrade")
        _insert(conn, 2, 11, "M:9-10@2025")
        conn.commit()
        with pytest.raises(RuntimeError) as exc:
            _run(mod, conn, "downgrade")
        assert "1 terna(s)" in str(exc.value)
        assert "mateo" not in str(exc.value).lower()
