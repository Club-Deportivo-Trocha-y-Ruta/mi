"""growth source on anthropometry (feature 040 — growth module redesign)

Revision ID: 2a8baa967cc6
Revises: 8b5ac1f24f61
Create Date: 2026-09-04 10:34:03.972659

Additive column: ``anthropometric_records.growth_source`` records which
population reference (``WHO`` or ``CDC``) the stored ``*_z_score`` /
``*_percentile`` / ``nutritional_status`` values on that row were computed
against. Reuses the ``GrowthSource`` enum already backing
``growth_reference_lms.source`` (same enum name ``growthsource`` — MySQL
enums are inline per-column so this only affects SQLAlchemy's own type
bookkeeping, not a shared DB type).

Nullable, no default, no data backfill here: existing rows stay ``NULL``
("legacy row / referencia anterior" per the UI contract) until the
idempotent recompute script (``app/scripts/backfill_anthropometry.py``,
feature 040 T023) sets them to ``WHO``. New rows get ``growth_source='WHO'``
once the router is switched (T022) — unrelated to this migration.

Risk: single nullable ``ADD COLUMN`` on ``anthropometric_records``. MySQL
8.0+ performs this as an in-place/instant DDL operation (no full table
rewrite, brief metadata lock) since the column is nullable, has no default
and is appended at the end — safe outside a maintenance window, but still
coordinate with `release-manager` before running in Hostinger prod per repo
policy for prod DDL.

Downgrade: drops the column. No data is destroyed beyond the (recoverable,
recomputed-from-raw-values) ``growth_source`` tag itself — raw measurement
columns are never touched by this migration.

``batch_alter_table`` used for parity with the other recent migrations
(offline/SQLite-based migration unit tests use the same pattern); MySQL
executes the plain ``ALTER TABLE`` under the hood.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a8baa967cc6'
down_revision: Union[str, None] = '8b5ac1f24f61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("anthropometric_records") as batch_op:
        batch_op.add_column(
            sa.Column(
                "growth_source",
                sa.Enum("WHO", "CDC", name="growthsource"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("anthropometric_records") as batch_op:
        batch_op.drop_column("growth_source")
