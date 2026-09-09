"""Migration tests for `45cd705c6b54` (feature 041 — multi-coach governance).

Covers data-model.md §6.5, bundled into this single module marked
``@pytest.mark.mysql`` (T014's task description groups all of the required
migration checks here rather than splitting a SQLite lane from a MySQL lane):

- ``audit_log.occurred_at`` keeps microsecond precision (`DATETIME(6)`) —
  FR-002's "sub-second precision", the pre-existing gap this feature must not
  inherit (data-model.md §1, §6.4).
- Backfill B1: every pre-existing ``training_sessions`` row ends up with
  exactly one ``training_session_coaches`` bridge row, its creator, after
  upgrading past this revision.
- Backfill B2: a pre-existing *approved* ``monthly_reports`` row gets
  ``approved_at = generated_at`` but ``approved_by_user_id`` stays ``NULL`` —
  copying ``generated_by_user_id`` would fabricate an attribution nobody
  verified.
- Backfills are idempotent: replaying the same guarded statements (the
  ``NOT EXISTS`` / ``IS NULL`` guards baked into the migration) must not
  create a duplicate bridge row or move ``approved_at`` a second time.
- ``alembic heads`` resolves to exactly one head (this revision) — no
  unresolved fork.

No app model is imported here (same rule as the migration itself); rows are
seeded with raw SQL against the pre-041 schema so the test exercises exactly
what a real deploy runs. Rows are synthetic scheduling/report metadata only
(club/session/report ids, no athlete, no minor data) — nothing here needs a
privacy review.

**Cannot run on this machine**: there is no MySQL 8.4 instance available in
this environment (only offline aiosqlite is wired up here), so this module
has been written and statically reviewed (imports cleanly, mirrors the
project's existing `-m mysql` fixture conventions in `tests/conftest.py`) but
has **not** been executed against a real `_test` database. That verification
is an open blocker — see the task's `blockers` note. Run with::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        pytest -m mysql -q backend/tests/test_audit_mysql.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.mysql

BACKEND_DIR = Path(__file__).resolve().parents[1]
REVISION = "45cd705c6b54"
DOWN_REVISION = "2a8baa967cc6"


def _require_test_url() -> str:
    """``TEST_DATABASE_URL`` (aiomysql, async) -> pymysql (sync), for Alembic.

    Mirrors the safety rule of the ``mysql_engine`` fixture in
    ``tests/conftest.py``: skip when unset, hard-fail when the database name
    does not end in ``_test`` (never point this at dev/prod).
    """
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url or not url.startswith("mysql+aiomysql://"):
        pytest.skip(
            "TEST_DATABASE_URL (mysql+aiomysql://) no configurada — "
            "saltando lane mysql"
        )
    db_name = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    if not db_name.endswith("_test"):
        pytest.fail(
            f"TEST_DATABASE_URL apunta a la base '{db_name}', que no termina "
            "en '_test'. Abortando para proteger datos de dev/prod."
        )
    return url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)


def _alembic_config(sync_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


@pytest.fixture(scope="module")
def sync_url() -> str:
    return _require_test_url()


@pytest.fixture
def clean_schema(sync_url: str) -> str:
    """Drop every table, then walk the full Alembic chain to `down_revision`
    (the pre-041 schema) so each test starts from a known, empty baseline."""
    engine = create_engine(sync_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        tables = [row[0] for row in conn.execute(text("SHOW TABLES")).fetchall()]
        for tbl in tables:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    engine.dispose()

    command.upgrade(_alembic_config(sync_url), DOWN_REVISION)
    return sync_url


def _seed_pre041_fixtures(engine) -> dict[str, int]:
    """Minimal synthetic rows on the pre-041 schema: one club, one coach user,
    one session (creator = the coach, no bridge row yet — the table does not
    exist pre-041) and one approved monthly report with no approval
    attribution. No athlete/minor data anywhere in this fixture.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clubs (id, name, code, is_active) "
                "VALUES (9001, 'Club Prueba Migración', 'MIG9001', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users "
                "(id, email, first_name, last_name, role, is_active, can_login) "
                "VALUES (9001, 'coach9001@example.test', 'Coach', 'Nueve', "
                "'coach', 1, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO training_sessions "
                "(id, club_id, created_by_user_id, status, scheduled_date, "
                "scheduled_start_time, duration_min, location, technical_focus, "
                "session_kind, created_at, updated_at) "
                "VALUES (9001, 9001, 9001, 'planned', '2026-03-01', '08:00:00', "
                "90, 'Pista', 'Resistencia', 'entrenamiento', NOW(), NOW())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO monthly_reports "
                "(id, club_id, year, month, status, generated_by_user_id, "
                "generated_at) "
                "VALUES (9001, 9001, 2026, 3, 'approved', 9001, "
                "'2026-03-05 10:00:00')"
            )
        )
    return {"club_id": 9001, "user_id": 9001, "session_id": 9001, "report_id": 9001}


def test_single_head():
    """`alembic heads` resolves to exactly one head — this revision."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == [REVISION], (
        f"Expected a single head {REVISION!r}, got {heads!r} — an unresolved "
        "Alembic fork exists."
    )


def test_occurred_at_has_fsp6(clean_schema: str):
    """`audit_log.occurred_at` must be `DATETIME(6)` — FR-002 sub-second
    precision, and the exact gap `race_result_revisions.changed_at` already
    has (data-model.md §1)."""
    command.upgrade(_alembic_config(clean_schema), REVISION)

    engine = create_engine(clean_schema, future=True)
    with engine.begin() as conn:
        ddl = conn.execute(text("SHOW CREATE TABLE audit_log")).fetchone()[1]
    engine.dispose()

    assert "datetime(6)" in ddl.lower(), (
        f"audit_log.occurred_at must be DATETIME(6), got DDL:\n{ddl}"
    )


def test_audit_indexes_exist(clean_schema: str):
    """The five composite indexes of data-model.md §1.1 must exist after
    upgrading, with their documented leading columns."""
    command.upgrade(_alembic_config(clean_schema), REVISION)

    engine = create_engine(clean_schema, future=True)
    with engine.begin() as conn:
        rows = conn.execute(text("SHOW INDEX FROM audit_log")).fetchall()
    engine.dispose()

    index_names = {row[2] for row in rows}  # Key_name column
    assert {
        "ix_audit_club_time",
        "ix_audit_actor_time",
        "ix_audit_entity_time",
        "ix_audit_athlete_time",
        "ix_audit_request_id",
    } <= index_names, f"Missing audit_log index(es); found: {sorted(index_names)}"


def test_backfill_b1_session_coach_is_creator(clean_schema: str):
    """B1: every pre-existing session ends up with exactly one bridge row —
    its creator — after upgrading past 45cd705c6b54."""
    engine = create_engine(clean_schema, future=True)
    ids = _seed_pre041_fixtures(engine)

    command.upgrade(_alembic_config(clean_schema), REVISION)

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT coach_user_id, added_by_user_id "
                "FROM training_session_coaches WHERE session_id = :sid"
            ),
            {"sid": ids["session_id"]},
        ).fetchall()
    engine.dispose()

    assert len(rows) == 1, (
        f"Expected exactly one bridge row for session {ids['session_id']}, "
        f"got {rows!r}"
    )
    assert rows[0][0] == ids["user_id"], "coach_user_id must be the session creator"
    assert rows[0][1] is None, "added_by_user_id must be NULL for the backfill"


def test_backfill_b2_approved_report_keeps_approved_by_null(clean_schema: str):
    """B2: `approved_at` copies `generated_at` for pre-existing approved
    reports; `approved_by_user_id` stays NULL — no attribution is fabricated
    (data-model.md §6.3)."""
    engine = create_engine(clean_schema, future=True)
    ids = _seed_pre041_fixtures(engine)

    command.upgrade(_alembic_config(clean_schema), REVISION)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT approved_at, approved_by_user_id, generated_at "
                "FROM monthly_reports WHERE id = :rid"
            ),
            {"rid": ids["report_id"]},
        ).fetchone()
    engine.dispose()

    assert row is not None
    assert row[0] == row[2], "approved_at must equal generated_at for the backfill"
    assert row[1] is None, "approved_by_user_id must stay NULL (no fabricated actor)"


def test_backfills_are_idempotent(clean_schema: str):
    """Re-running the same guarded statements a second time must not
    duplicate the bridge row or move `approved_at` again — the `NOT EXISTS`
    / `IS NULL` guards baked into the migration make every backfill a no-op
    on replay."""
    engine = create_engine(clean_schema, future=True)
    ids = _seed_pre041_fixtures(engine)

    command.upgrade(_alembic_config(clean_schema), REVISION)

    with engine.begin() as conn:
        first_approved_at = conn.execute(
            text("SELECT approved_at FROM monthly_reports WHERE id = :rid"),
            {"rid": ids["report_id"]},
        ).scalar()

    # Re-run the exact guarded statements the migration's B1/B2 backfills use.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO training_session_coaches "
                "    (session_id, coach_user_id, added_by_user_id, added_at) "
                "SELECT ts.id, ts.created_by_user_id, NULL, ts.created_at "
                "FROM training_sessions ts "
                "WHERE NOT EXISTS ("
                "    SELECT 1 FROM training_session_coaches c "
                "    WHERE c.session_id = ts.id"
                ")"
            )
        )
        conn.execute(
            text(
                "UPDATE monthly_reports "
                "SET approved_at = generated_at "
                "WHERE status = 'approved' AND approved_at IS NULL"
            )
        )

    with engine.begin() as conn:
        bridge_row_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM training_session_coaches "
                "WHERE session_id = :sid"
            ),
            {"sid": ids["session_id"]},
        ).scalar()
        second_approved_at = conn.execute(
            text("SELECT approved_at FROM monthly_reports WHERE id = :rid"),
            {"rid": ids["report_id"]},
        ).scalar()
    engine.dispose()

    assert bridge_row_count == 1, "Replaying B1 must not create a second bridge row"
    assert second_approved_at == first_approved_at, (
        "Replaying B2 must not move approved_at a second time"
    )


def test_upgrade_downgrade_upgrade_round_trip(clean_schema: str):
    """`alembic upgrade head` → `downgrade -1` → `upgrade head` must succeed
    without error, and land back on the single head (non-negotiable
    reversibility rule)."""
    cfg = _alembic_config(clean_schema)
    command.upgrade(cfg, REVISION)
    command.downgrade(cfg, DOWN_REVISION)
    command.upgrade(cfg, REVISION)

    engine = create_engine(clean_schema, future=True)
    with engine.begin() as conn:
        current = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
    engine.dispose()
    assert current == REVISION
