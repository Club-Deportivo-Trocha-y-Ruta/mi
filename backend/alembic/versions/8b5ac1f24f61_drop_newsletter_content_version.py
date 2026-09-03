"""drop newsletter content_version (retire legacy v1 pipeline)

Revision ID: 8b5ac1f24f61
Revises: d0e1f2a3b4c5
Create Date: 2026-09-03 00:00:00.000000

Retires the legacy v1 newsletter pipeline (three-textarea narrative, the
``athlete_monthly_newsletter.html`` email/PDF templates, the
``athlete_monthly_newsletter_v1`` prompt and its use case). Every newsletter
is now the "bitácora de etapa" (StageLog v2, feature 038) — there is no more
``content_version`` switch.

Coach decision (2026-09-03): no final newsletter has ever been sent to a
family from a ``content_version = 1`` row on this deployment (only drafts /
one ``approved`` row exist locally) — safe to delete those rows outright
rather than migrate them, per the coach's explicit instruction.

1. Deletes every ``athlete_monthly_newsletters`` row with
   ``content_version = 1`` (raw SQL — this is a data decision specific to
   the environments this migration has actually run against so far, not a
   general reversible schema change; see downgrade() note below). Any
   ``newsletter_delivery_events`` for those rows cascade-delete via the
   existing ``ON DELETE CASCADE`` FK.
2. Drops ``content_version`` (SMALLINT NOT NULL DEFAULT 1) and
   ``coach_narrative_overrides`` (JSON NULL, the v1 Fortalezas/Área/Hito
   override) from ``athlete_monthly_newsletters`` — both were v1-only.

Compatibility: SQLite (offline test lane) via ``batch_alter_table``, same
pattern as ``6b998c214e5a``.

Downgrade: re-adds both columns with their original defaults/nullability.
The deleted ``content_version = 1`` rows are NOT restored — this migration
is intentionally NOT data-reversible; downgrade only restores the schema
shape so a rollback doesn't break the ORM mapping.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# revision identifiers
# ---------------------------------------------------------------------------
revision: str = "8b5ac1f24f61"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Drop legacy (v1) rows — coach-confirmed: nothing final was ever
    # sent from content_version=1 (2026-09-03 decision). ─────────────────
    op.execute(
        sa.text(
            "DELETE FROM athlete_monthly_newsletters WHERE content_version = 1"
        )
    )

    # ── 2. Drop v1-only columns ────────────────────────────────────────
    with op.batch_alter_table("athlete_monthly_newsletters") as batch_op:
        batch_op.drop_column("coach_narrative_overrides")
        batch_op.drop_column("content_version")


def downgrade() -> None:
    with op.batch_alter_table("athlete_monthly_newsletters") as batch_op:
        batch_op.add_column(
            sa.Column(
                "content_version",
                sa.SmallInteger(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch_op.add_column(
            sa.Column("coach_narrative_overrides", sa.JSON(), nullable=True)
        )
