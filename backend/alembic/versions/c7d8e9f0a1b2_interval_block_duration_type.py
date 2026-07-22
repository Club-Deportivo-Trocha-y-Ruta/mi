"""interval block duration usability — duration_type + nullable duration_s (feature 034)

Revision ID: c7d8e9f0a1b2
Revises: b5c6d7e8f9a0
Create Date: 2026-07-22 00:00:00.000000

Spec 034 — interval-duration-usability.

Adds an explicit per-block duration-type discriminator so a block can be
"open" (no planned duration — the athlete ends it by pressing the device's
lap button) instead of always requiring a fixed number of seconds.

DDL (both `interval_structure_blocks` and `interval_template_blocks`):
    1. ADD COLUMN duration_type ENUM('fixed','open_lap') NOT NULL
       DEFAULT 'fixed'
       — existing rows migrate to 'fixed' via server_default, no data
       rewrite needed.
    2. ALTER COLUMN duration_s to nullable (was NOT NULL). Meaning for
       'fixed' rows is unchanged; NULL is now valid and means "open_lap,
       no planned duration".

New named ENUM type created by this migration: `intervaldurationtype`.
Its value list mirrors the Python enum `.value` strings exactly (the model
uses `values_callable`), so the DB stores the value strings ('fixed' /
'open_lap'), not the Python member names.

Invariants (service-layer + Pydantic, matching feature 026's enforcement
style — no DB CHECK constraint added here):
    - duration_type = 'fixed'     => duration_s IS NOT NULL AND > 0
    - duration_type = 'open_lap'  => duration_s IS NULL
    - duration_type = 'open_lap'  => block_type IN ('warmup', 'cooldown')
    - duration_type = 'open_lap'  => repeat_group IS NULL

DOWNGRADE IS DESTRUCTIVE for any 'open_lap' rows created after this
migration: restoring `duration_s` to NOT NULL is impossible while an
open_lap row (duration_s IS NULL) exists, so downgrade() first DELETES
every row with duration_type='open_lap' from both tables, then restores
NOT NULL on duration_s, then drops the duration_type column and the
`intervaldurationtype` ENUM type. This is an accepted, documented data-loss
step (per data-model.md) — coordinate with release-manager before running
downgrade() in an environment that may already contain open_lap blocks.

MySQL/SQLite portability:
    - ENUM type only in MySQL; SQLite renders as VARCHAR (no native ENUM).
    - `duration_s` nullability change uses `existing_type=sa.Integer()` on
      `alter_column`, matching the pattern used elsewhere in this repo for
      altering column nullability.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# revision identifiers
#
# NOTE: the design docs for feature 034 specify revision id "c6d7e8f9a0b1",
# but that id is already used by an existing, unrelated migration
# (c6d7e8f9a0b1_drop_sent_at_from_monthly_reports.py, down_revision
# "a1b2c3d4e5fa", itself the down_revision of d4e5f6a7b8c9). Reusing it here
# would create a duplicate-revision cycle in the Alembic graph. This
# migration uses "c7d8e9f0a1b2" instead, keeping down_revision =
# "b5c6d7e8f9a0" (verified current single head via `alembic heads`) exactly
# as specified.
# ---------------------------------------------------------------------------
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Enum value list — mirrors the Python enum .value strings exactly
# ---------------------------------------------------------------------------
_DURATION_TYPE_VALUES = ["fixed", "open_lap"]
_DURATION_TYPE_ENUM_NAME = "intervaldurationtype"

_BLOCK_TABLES = ("interval_structure_blocks", "interval_template_blocks")


def upgrade() -> None:
    for table_name in _BLOCK_TABLES:
        # 1. Add duration_type — existing rows default to 'fixed'.
        op.add_column(
            table_name,
            sa.Column(
                "duration_type",
                sa.Enum(*_DURATION_TYPE_VALUES, name=_DURATION_TYPE_ENUM_NAME),
                nullable=False,
                server_default="fixed",
            ),
        )

        # 2. duration_s becomes nullable (NULL only valid for open_lap rows).
        op.alter_column(
            table_name,
            "duration_s",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    conn = op.get_bind()

    for table_name in _BLOCK_TABLES:
        # DESTRUCTIVE — see module docstring. Delete open_lap rows first so
        # restoring duration_s NOT NULL below does not fail on NULLs.
        conn.execute(
            sa.text(
                f"DELETE FROM {table_name} WHERE duration_type = 'open_lap'"
            )
        )

        # Restore duration_s NOT NULL (safe now — no NULLs remain).
        op.alter_column(
            table_name,
            "duration_s",
            existing_type=sa.Integer(),
            nullable=False,
        )

        op.drop_column(table_name, "duration_type")

    # Drop the named ENUM type (MySQL/MariaDB only; SQLite has no native ENUM).
    if conn.dialect.name not in ("sqlite",):
        sa.Enum(name=_DURATION_TYPE_ENUM_NAME).drop(conn, checkfirst=True)
