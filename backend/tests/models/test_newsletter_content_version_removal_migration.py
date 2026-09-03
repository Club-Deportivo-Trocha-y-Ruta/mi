"""Tests para la migración ``8b5ac1f24f61`` (retiro del pipeline legacy v1).

Cubre, en aislamiento (SQLite in-memory, sin depender de ``Base.metadata``):
  - Metadatos de la revisión (``revision``/``down_revision``).
  - ``upgrade()`` borra las filas ``content_version = 1`` y deja intactas
    las ``content_version = 2``.
  - ``upgrade()`` dropea ``content_version`` y ``coach_narrative_overrides``.
  - ``downgrade()`` restaura ambas columnas con su forma original (no
    restaura las filas borradas — documentado como no-reversible en datos).

Mismo patrón que ``test_newsletter_stage_log_migration.py``
(``test_migration_upgrade_downgrade_reversible``): carga el módulo de la
migración por ruta de archivo y lo ejecuta contra una tabla SQLite mínima
armada a mano (no requiere MySQL real).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "8b5ac1f24f61_drop_newsletter_content_version.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_drop_newsletter_content_version", MIGRATION_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_metadata():
    mod = _load_migration()
    assert mod.revision == "8b5ac1f24f61"
    assert mod.down_revision == "d0e1f2a3b4c5"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_upgrade_deletes_v1_rows_keeps_v2_and_drops_columns():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _load_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE athlete_monthly_newsletters ("
                "id INTEGER PRIMARY KEY, athlete_id INTEGER, year INTEGER, "
                "month INTEGER, status VARCHAR(20), content_version INTEGER "
                "NOT NULL DEFAULT 1, coach_narrative_overrides TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO athlete_monthly_newsletters "
                "(id, athlete_id, year, month, status, content_version) "
                "VALUES (1, 5, 2026, 4, 'draft', 1), "
                "(2, 5, 2026, 5, 'approved', 1), "
                "(3, 6, 2026, 6, 'sent', 2)"
            )
        )
        conn.commit()

        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
        conn.commit()

        insp = inspect(conn)
        remaining_cols = {
            c["name"] for c in insp.get_columns("athlete_monthly_newsletters")
        }
        assert "content_version" not in remaining_cols
        assert "coach_narrative_overrides" not in remaining_cols

        remaining_ids = {
            row[0]
            for row in conn.execute(
                text("SELECT id FROM athlete_monthly_newsletters")
            ).fetchall()
        }
        assert remaining_ids == {3}, "solo debe sobrevivir la fila content_version=2"

        with Operations.context(ctx):
            mod.downgrade()
        conn.commit()

        insp = inspect(conn)
        restored_cols = {
            c["name"] for c in insp.get_columns("athlete_monthly_newsletters")
        }
        assert "content_version" in restored_cols
        assert "coach_narrative_overrides" in restored_cols

        # downgrade() restaura la forma de la columna, no las filas borradas.
        remaining_ids_after_downgrade = {
            row[0]
            for row in conn.execute(
                text("SELECT id FROM athlete_monthly_newsletters")
            ).fetchall()
        }
        assert remaining_ids_after_downgrade == {3}
    engine.dispose()
