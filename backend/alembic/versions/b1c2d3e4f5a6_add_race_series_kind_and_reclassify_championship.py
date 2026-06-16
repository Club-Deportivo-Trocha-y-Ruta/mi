"""add race_series.kind and reclassify championship series

Revision ID: b1c2d3e4f5a6
Revises: a3b4c5d6e7f8
Create Date: 2026-06-15 00:00:00.000000

Spec 014 — cup-vs-championship-series.

DDL:
    ALTER TABLE race_series ADD COLUMN kind ENUM('cup','championship') NOT NULL
    DEFAULT 'cup'

Data step (T026 — idempotent):
    1. Upsert championship series 'Campeonato Departamental 2026' for season 2026.
    2. Repoint the legacy Departmental event (is_championship=1, sequence_number=99
       under the Copa Valle 2026 series) to the new championship series with
       sequence_number=1. Guarded — safe no-op if the event does not exist (fresh
       DBs / tests).

Both steps are idempotent: re-runs and environments without the legacy data succeed
without error and without duplicating rows.

Downgrade:
    Repoints the event back to Copa Valle (seq 99), removes the empty championship
    series, and drops the kind column.

MySQL/SQLite portability:
    - ENUM type only in MySQL. SQLite uses VARCHAR (Alembic renders as VARCHAR when
      the dialect does not support ENUM natively).
    - Data steps use op.execute() with portable SQL (INSERT … SELECT / UPDATE with
      subquery) or dialect-branched raw SQL for MySQL-specific upsert syntax.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Constants — series name strings used in upgrade + downgrade
# ---------------------------------------------------------------------------
_COPA_VALLE_NAME = "Copa Valle de Ciclomontañismo"
_CD_NAME = "Campeonato Departamental 2026"
_CD_ORGANIZER = "Liga Vallecaucana de Ciclismo"
_CD_SCHEME = "copa_valle_2026"
_CD_SEASON = 2026


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. Add `kind` column to `race_series`
    # -----------------------------------------------------------------------
    op.add_column(
        "race_series",
        sa.Column(
            "kind",
            sa.Enum("cup", "championship", name="raceserieskind"),
            nullable=False,
            server_default="cup",
        ),
    )

    # -----------------------------------------------------------------------
    # 2. Upsert championship series (idempotent via UNIQUE(name, season_year))
    #    Portable: use SELECT then INSERT to avoid dialect-specific upsert syntax.
    # -----------------------------------------------------------------------
    conn = op.get_bind()

    # Check if the championship series already exists
    row = conn.execute(
        sa.text(
            "SELECT id FROM race_series "
            "WHERE name = :name AND season_year = :season"
        ),
        {"name": _CD_NAME, "season": _CD_SEASON},
    ).fetchone()

    if row is None:
        conn.execute(
            sa.text(
                "INSERT INTO race_series "
                "(name, season_year, organizer, points_scheme_code, kind, "
                " created_at, updated_at) "
                "VALUES (:name, :season, :organizer, :scheme, 'championship', "
                "        NOW(), NOW())"
            ),
            {
                "name": _CD_NAME,
                "season": _CD_SEASON,
                "organizer": _CD_ORGANIZER,
                "scheme": _CD_SCHEME,
            },
        )

    # Re-fetch to get the id (whether we just created it or it already existed)
    cd_series_row = conn.execute(
        sa.text(
            "SELECT id FROM race_series "
            "WHERE name = :name AND season_year = :season"
        ),
        {"name": _CD_NAME, "season": _CD_SEASON},
    ).fetchone()
    cd_series_id = cd_series_row[0]  # type: ignore[index]

    # Fetch Copa Valle 2026 series id (may not exist in fresh DBs — guarded)
    copa_row = conn.execute(
        sa.text(
            "SELECT id FROM race_series "
            "WHERE name = :name AND season_year = :season"
        ),
        {"name": _COPA_VALLE_NAME, "season": _CD_SEASON},
    ).fetchone()

    # -----------------------------------------------------------------------
    # 3. Repoint the legacy Departmental event to the championship series
    #    Guard: only if the Copa Valle series exists and has an is_championship=1
    #    event with sequence_number=99 (the legacy sentinel).
    # -----------------------------------------------------------------------
    if copa_row is not None:
        copa_series_id = copa_row[0]  # type: ignore[index]
        conn.execute(
            sa.text(
                "UPDATE race_events "
                "SET series_id = :cd_id, sequence_number = 1 "
                "WHERE series_id = :copa_id "
                "  AND is_championship = 1 "
                "  AND sequence_number = 99"
            ),
            {"cd_id": cd_series_id, "copa_id": copa_series_id},
        )


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Find championship series id
    cd_row = conn.execute(
        sa.text(
            "SELECT id FROM race_series "
            "WHERE name = :name AND season_year = :season"
        ),
        {"name": _CD_NAME, "season": _CD_SEASON},
    ).fetchone()

    if cd_row is not None:
        cd_series_id = cd_row[0]  # type: ignore[index]

        # Find Copa Valle 2026 series id
        copa_row = conn.execute(
            sa.text(
                "SELECT id FROM race_series "
                "WHERE name = :name AND season_year = :season"
            ),
            {"name": _COPA_VALLE_NAME, "season": _CD_SEASON},
        ).fetchone()

        if copa_row is not None:
            copa_series_id = copa_row[0]  # type: ignore[index]
            # Repoint the event back to Copa Valle (legacy sentinel seq=99)
            conn.execute(
                sa.text(
                    "UPDATE race_events "
                    "SET series_id = :copa_id, sequence_number = 99 "
                    "WHERE series_id = :cd_id "
                    "  AND is_championship = 1"
                ),
                {"copa_id": copa_series_id, "cd_id": cd_series_id},
            )

        # Remove championship series if it has no remaining events
        event_count_row = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM race_events WHERE series_id = :cd_id"
            ),
            {"cd_id": cd_series_id},
        ).fetchone()
        if event_count_row is not None and event_count_row[0] == 0:
            conn.execute(
                sa.text("DELETE FROM race_series WHERE id = :cd_id"),
                {"cd_id": cd_series_id},
            )

    # 2. Drop the kind column
    # MySQL requires existing_type + existing_nullable when altering ENUM columns
    op.drop_column("race_series", "kind")
