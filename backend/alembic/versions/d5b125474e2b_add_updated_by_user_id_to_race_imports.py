"""add updated_by_user_id to race_imports

Revision ID: d5b125474e2b
Revises: 686ce1d873f3
Create Date: 2026-09-14 10:49:52.782620

Corrige un hueco de la migración `45cd705c6b54` (multi-coach governance):
esa migración agregó ``updated_by_user_id`` a 7 tablas (users, athletes,
session_attendance, calendar_events, monthly_reports, anthropometric_records,
club_project_profiles) pero omitió ``race_imports``, aunque el modelo
``RaceImport`` hereda ``ActorTimestampMixin`` (que declara esa columna junto
a ``updated_at``, la cual sí se agregó — ver B6 en esa misma migración). El
lane de tests por defecto usa aiosqlite offline (crea tablas desde los
modelos ORM, sin pasar por Alembic), así que este drift nunca se detectó ahí
— solo rompe contra MySQL real, cualquier `select(RaceImport)` falla con
"Unknown column 'race_imports.updated_by_user_id'".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5b125474e2b'
down_revision: Union[str, None] = '686ce1d873f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("race_imports") as batch_op:
        batch_op.add_column(
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_race_imports_updated_by_user_id",
            "users",
            ["updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("race_imports") as batch_op:
        batch_op.drop_constraint(
            "fk_race_imports_updated_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("updated_by_user_id")
