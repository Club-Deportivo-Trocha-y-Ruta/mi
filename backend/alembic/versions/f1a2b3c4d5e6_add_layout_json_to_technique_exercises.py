"""add layout_json to technique_exercises (feature 019 Phase A)

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-06-30 00:00:00.000000

Phase A of feature 019 (Gymkhana Circuit Diagrams).

Schema change:
  ADD COLUMN layout_json JSON NULL on technique_exercises.
  Additive, nullable, no default — safe on a live table (no lock on MySQL 8.4
  for nullable column adds without defaults).

Idempotent data step:
  For each gymkhana exercise whose GymkhanaLayout has been transcribed from the
  ASCII croquis, UPDATE technique_exercises SET layout_json = <value> WHERE
  slug = <key> AND layout_json IS NULL.

  Source map: app.data.technique_catalog.GYMKHANA_LAYOUT_BACKFILL
  13 slugs covered (see that module for the full list and fidelity notes).

Downgrade:
  DROP COLUMN layout_json.  layout_ascii / layout_alt are untouched throughout.
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# ---------------------------------------------------------------------------
# revision identifiers
# ---------------------------------------------------------------------------
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Add the nullable JSON column ─────────────────────────────────────
    op.add_column(
        "technique_exercises",
        sa.Column("layout_json", sa.JSON(), nullable=True),
    )

    # ── 2. Idempotent backfill ───────────────────────────────────────────────
    # Import the pre-computed backfill map from the data module.
    # The import is deferred to upgrade() so that the migration file itself
    # never executes side-effects at module import time (Alembic convention).
    from app.data.technique_catalog import GYMKHANA_LAYOUT_BACKFILL  # noqa: PLC0415

    bind = op.get_bind()

    for slug, layout in GYMKHANA_LAYOUT_BACKFILL.items():
        # Only update rows where layout_json IS NULL (idempotent — re-running
        # the migration after a partial failure leaves already-filled rows intact).
        bind.execute(
            text(
                "UPDATE technique_exercises"
                " SET layout_json = :layout_json"
                " WHERE slug = :slug AND layout_json IS NULL"
            ),
            {
                # Serialise to a JSON string so both MySQL (native JSON column)
                # and SQLite (text-stored JSON, used in tests) accept it
                # uniformly via the text() path.
                "layout_json": json.dumps(layout),
                "slug": slug,
            },
        )


def downgrade() -> None:
    # Drop the column.  layout_ascii / layout_alt are intentionally untouched
    # so the ASCII fallback path (FR-010) continues to work after a rollback.
    op.drop_column("technique_exercises", "layout_json")
