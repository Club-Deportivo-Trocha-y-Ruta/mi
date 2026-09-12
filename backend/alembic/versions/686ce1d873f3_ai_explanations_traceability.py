"""ai_explanations traceability — nine nullable columns (feature 042)

Revision ID: 686ce1d873f3
Revises: 45cd705c6b54
Create Date: 2026-09-12 00:00:00.000000

Adds the nine additive, nullable traceability columns to
``athlete_ai_explanations`` per ``specs/042-traceable-growth-ai/data-model.md``
§1 (LD-6): ``schema_version``, ``structured_json``, ``critic_verdict``,
``prompt_version``, ``tokens_in``, ``tokens_out``, ``cost_usd``,
``latency_ms``, ``langfuse_trace_id``.

No ``server_default`` on any of them — every pre-existing row (feature 033
free-prose rows) simply keeps all nine as NULL, which is itself the
row-format discriminator: ``schema_version IS NULL`` means "free prose"
(surfaced by the API as ``"v1"``), ``schema_version = "v2"`` means
"structured, this feature". No new index — nothing queries on these nine
columns yet (data-model.md §1, mirroring ``45cd705c6b54``'s identical call
for its own additive columns).

Backfill: none. This is a pure additive schema change; the existing
``text``/``model``/``provider``/... columns and the unique constraint
``uq_ai_expl_athlete_record_usecase`` are untouched.

Rollback: ``downgrade()`` drops the nine columns in reverse order. No data
is recoverable after a downgrade (there is none to lose — the columns are
new and NULL-only until this feature's pipeline starts writing "v2" rows).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "686ce1d873f3"
down_revision: Union[str, None] = "45cd705c6b54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("athlete_ai_explanations") as batch_op:
        batch_op.add_column(
            sa.Column("schema_version", sa.String(length=8), nullable=True)
        )
        batch_op.add_column(sa.Column("structured_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("critic_verdict", sa.String(length=16), nullable=True)
        )
        batch_op.add_column(
            sa.Column("prompt_version", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(sa.Column("tokens_in", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("tokens_out", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True)
        )
        batch_op.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("langfuse_trace_id", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("athlete_ai_explanations") as batch_op:
        batch_op.drop_column("langfuse_trace_id")
        batch_op.drop_column("latency_ms")
        batch_op.drop_column("cost_usd")
        batch_op.drop_column("tokens_out")
        batch_op.drop_column("tokens_in")
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("critic_verdict")
        batch_op.drop_column("structured_json")
        batch_op.drop_column("schema_version")
