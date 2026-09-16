"""Tests de la migración ``c2314ccd7927`` (hotfix "identidad de válida",
2026-09-16, ver ``~/.claude/plans/multicopa-identidad-valida.md``) —
específicamente el backfill de ``athlete_ai_insights.event_id`` para filas
legadas (punto 3 del docstring de la migración).

Complementa a ``tests/models/test_athlete_ai_insight_scope_key.py``, que
cubre ``compute_insight_scope_key`` y el listener ORM pero NO ejecuta la
migración en sí. Este módulo corre ``upgrade()`` de verdad (vía
``Operations.context``, mismo patrón que
``tests/models/test_newsletter_stage_log_migration.py``) contra un esquema
SQLite mínimo — no ``Base.metadata`` completo, porque la cadena alembic
completa no compila en SQLite (``LONGTEXT`` de una migración no
relacionada, ``d1e2f3a4b5c6``).

Escenario (ids sintéticos):

- **Ambiguo** — temporada 2026, dos series (Copa Valle + Copa Let's Go)
  con su propia válida ``sequence_number=4``. Un insight legado
  ``season=2026, valida_num=4, event_id=NULL`` NO debe resolverse — no hay
  forma segura de saber a cuál copa pertenecía.
- **Sin ambigüedad** — temporada 2025, una sola serie con
  ``sequence_number=2``. Un insight legado
  ``season=2025, valida_num=2, event_id=NULL`` SÍ debe resolverse al único
  evento posible.
- **Agregado de temporada** — ``valida_num=0`` nunca se toca (no tiene un
  evento único que resolver).
- Idempotencia: correr el backfill dos veces no cambia el resultado.
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
    / "c2314ccd7927_multicopa_insight_scope_key_event_.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_multicopa_hotfix", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_metadata():
    mod = _load_migration()
    assert mod.revision == "c2314ccd7927"
    assert mod.down_revision == "2c0097aa48b8"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


# ---------------------------------------------------------------------------
# Esquema SQLite mínimo (no Base.metadata — ver docstring del módulo)
# ---------------------------------------------------------------------------


def _create_minimal_schema(conn) -> None:
    conn.execute(text("CREATE TABLE race_series (id INTEGER PRIMARY KEY, season_year INTEGER, name VARCHAR(150))"))
    conn.execute(
        text(
            "CREATE TABLE race_events (id INTEGER PRIMARY KEY, series_id INTEGER, sequence_number INTEGER)"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE athlete_ai_insights ("
            "id INTEGER PRIMARY KEY, athlete_id INTEGER, season INTEGER, "
            "valida_num INTEGER, event_id INTEGER, is_active INTEGER, "
            "coach_edits_count INTEGER DEFAULT 0"
            ")"
        )
    )


def _run_upgrade(mod, conn) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        mod.upgrade()


def _row(conn, insight_id: int):
    return conn.execute(
        text(
            "SELECT event_id, insight_scope_key FROM athlete_ai_insights WHERE id = :id"
        ),
        {"id": insight_id},
    ).one()


@pytest.fixture
def seeded_engine():
    """Semilla el escenario ambiguo + sin-ambigüedad + agregado de temporada.

    IDs de insight: 1 = ambiguo (2026, V4), 2 = sin ambigüedad (2025, V2),
    3 = agregado de temporada (valida_num=0).
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.connect() as conn:
        _create_minimal_schema(conn)

        # --- Temporada 2026: DOS copas con su propia Válida 4 (ambiguo) ---
        conn.execute(text("INSERT INTO race_series (id, season_year, name) VALUES (1, 2026, 'Copa Valle de Ciclomontanismo')"))
        conn.execute(text("INSERT INTO race_series (id, season_year, name) VALUES (2, 2026, \"Copa Let's Go Interdepartamental XCO\")"))
        conn.execute(text("INSERT INTO race_events (id, series_id, sequence_number) VALUES (43, 1, 4)"))  # Copa Valle V4
        conn.execute(text("INSERT INTO race_events (id, series_id, sequence_number) VALUES (99, 2, 4)"))  # Copa Let's Go V4

        # --- Temporada 2025: UNA sola copa, Válida 2 (sin ambigüedad) ---
        conn.execute(text("INSERT INTO race_series (id, season_year, name) VALUES (3, 2025, 'Copa Única 2025')"))
        conn.execute(text("INSERT INTO race_events (id, series_id, sequence_number) VALUES (77, 3, 2)"))

        # --- Insights legados (pre-hotfix): event_id NULL ---
        conn.execute(
            text(
                "INSERT INTO athlete_ai_insights (id, athlete_id, season, valida_num, event_id, is_active, coach_edits_count) "
                "VALUES (1, 200, 2026, 4, NULL, 1, 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO athlete_ai_insights (id, athlete_id, season, valida_num, event_id, is_active, coach_edits_count) "
                "VALUES (2, 201, 2025, 2, NULL, 1, 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO athlete_ai_insights (id, athlete_id, season, valida_num, event_id, is_active, coach_edits_count) "
                "VALUES (3, 202, 2026, 0, NULL, 1, 0)"
            )
        )
        conn.commit()
    yield engine
    engine.dispose()


def test_ambiguous_legacy_row_is_not_backfilled(seeded_engine):
    """Dos copas comparten sequence_number=4 en 2026 — event_id se deja
    NULL y la clave cae al formato legado ``valida:{season}:{n}``."""
    mod = _load_migration()
    with seeded_engine.connect() as conn:
        _run_upgrade(mod, conn)
        conn.commit()
        event_id, scope_key = _row(conn, 1)
        assert event_id is None
        assert scope_key == "valida:2026:4"


def test_unambiguous_legacy_row_is_backfilled(seeded_engine):
    """Una sola copa con sequence_number=2 en 2025 — event_id se resuelve
    a esa válida y la clave pasa a ``event:{id}``."""
    mod = _load_migration()
    with seeded_engine.connect() as conn:
        _run_upgrade(mod, conn)
        conn.commit()
        event_id, scope_key = _row(conn, 2)
        assert event_id == 77
        assert scope_key == "event:77"


def test_season_summary_row_is_never_touched(seeded_engine):
    """``valida_num=0`` no tiene un evento único que resolver — se
    excluye del backfill (event_id sigue NULL) y su clave es la de
    agregado de temporada, sin importar event_id."""
    mod = _load_migration()
    with seeded_engine.connect() as conn:
        _run_upgrade(mod, conn)
        conn.commit()
        event_id, scope_key = _row(conn, 3)
        assert event_id is None
        assert scope_key == "season:2026"


def test_backfill_sql_is_idempotent(seeded_engine):
    """Correr el backfill de event_id dos veces no cambia nada — ya
    cubierto indirectamente por upgrade() corriendo una vez, pero se
    ejercita explícitamente la constante reutilizable de la migración."""
    mod = _load_migration()
    with seeded_engine.connect() as conn:
        _run_upgrade(mod, conn)
        conn.commit()
        before_ambiguous = _row(conn, 1)
        before_unambiguous = _row(conn, 2)

        # Re-ejecutar SOLO el backfill de event_id (ya con insight_scope_key
        # NOT NULL en la tabla real, pero la columna event_id no cambia de
        # forma — un segundo pase debe ser un no-op).
        conn.execute(text(mod.BACKFILL_LEGACY_EVENT_ID_SQL))
        conn.commit()

        after_ambiguous = _row(conn, 1)
        after_unambiguous = _row(conn, 2)
        assert before_ambiguous == after_ambiguous
        assert before_unambiguous == after_unambiguous
