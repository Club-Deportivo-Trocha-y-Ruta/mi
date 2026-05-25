"""ondelete explicit and soft delete athletes users

Revision ID: bb2231fb9f99
Revises: 8c1d2e3f4a5b
Create Date: 2026-05-24 23:55:28.466017

Cambios introducidos por el bloque C1 (db: ondelete + soft-delete):

1. `athletes.deleted_at` y `users.deleted_at` — columnas NULL con índice
   para habilitar soft-delete. Los endpoints DELETE marcan estos campos
   en vez de borrar la fila físicamente.
2. FKs con ondelete explícito (RESTRICT donde la referencia es esencial,
   SET NULL donde la auditoría sobrevive al borrado):
   - athletes.user_id / club_id / created_by → RESTRICT
   - parent_athlete.parent_id / athlete_id → RESTRICT
   - club_members.club_id / user_id → RESTRICT
   - anthropometric_records.athlete_id → RESTRICT
   - anthropometric_records.evaluated_by → SET NULL (nullable)
   - parent_invites.athlete_id → RESTRICT
   - parent_invites.used_by / parent_user_id / created_by → SET NULL
   - parental_consents.parent_user_id / athlete_id → RESTRICT
   - privacy_policies.created_by → SET NULL
   - athlete_ai_explanations.generated_by_user_id → SET NULL (nullable)
   - users.created_by → SET NULL (self-FK)

Nota: las tablas `agent_run_events` y `anonymization_mappings`, y las
columnas extras de `agent_runs` (input_json, langfuse_trace_id, cost_usd,
etc.), existen físicamente en DB pero NO están mapeadas en los modelos
SQLAlchemy a propósito (ver app/models/agent_run.py). Esta migración no
las toca. El downgrade tampoco las restaura.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "bb2231fb9f99"
down_revision: Union[str, None] = "8c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drop_fk_if_exists(table: str, fk_name: str) -> None:
    """Drop a FK constraint by name if it exists (MySQL-specific)."""
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :tname
              AND CONSTRAINT_NAME = :cname
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            """
        ),
        {"tname": table, "cname": fk_name},
    )
    if res.scalar() > 0:
        op.drop_constraint(fk_name, table, type_="foreignkey")


def _find_fk_name(table: str, column: str) -> str | None:
    """Find the FK constraint name for a given (table, column) pair."""
    bind = op.get_bind()
    res = bind.execute(
        sa.text(
            """
            SELECT kcu.CONSTRAINT_NAME
            FROM information_schema.KEY_COLUMN_USAGE kcu
            JOIN information_schema.TABLE_CONSTRAINTS tc
              ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
             AND tc.TABLE_NAME = kcu.TABLE_NAME
            WHERE kcu.TABLE_SCHEMA = DATABASE()
              AND kcu.TABLE_NAME = :tname
              AND kcu.COLUMN_NAME = :cname
              AND tc.CONSTRAINT_TYPE = 'FOREIGN KEY'
            LIMIT 1
            """
        ),
        {"tname": table, "cname": column},
    )
    row = res.fetchone()
    return row[0] if row else None


def _replace_fk(
    table: str,
    column: str,
    ref_table: str,
    ref_column: str = "id",
    ondelete: str | None = None,
) -> None:
    """Drop existing FK on (table, column) and recreate with ondelete."""
    existing = _find_fk_name(table, column)
    if existing:
        op.drop_constraint(existing, table, type_="foreignkey")
    op.create_foreign_key(
        None,
        table,
        ref_table,
        [column],
        [ref_column],
        ondelete=ondelete,
    )


# ---------------------------------------------------------------------------
# Upgrade / Downgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) Soft-delete columns
    # ------------------------------------------------------------------
    op.add_column("athletes", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_athletes_deleted_at", "athletes", ["deleted_at"], unique=False
    )

    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_users_deleted_at", "users", ["deleted_at"], unique=False
    )

    # ------------------------------------------------------------------
    # 2) Nullable columns que pasan a SET NULL
    # ------------------------------------------------------------------
    op.alter_column(
        "anthropometric_records",
        "evaluated_by",
        existing_type=mysql.INTEGER(),
        nullable=True,
    )
    op.alter_column(
        "athlete_ai_explanations",
        "generated_by_user_id",
        existing_type=mysql.INTEGER(),
        nullable=True,
    )
    op.alter_column(
        "parent_invites",
        "created_by",
        existing_type=mysql.INTEGER(),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # 3) FKs explícitas con ondelete
    # ------------------------------------------------------------------
    # athletes
    _replace_fk("athletes", "user_id", "users", ondelete="RESTRICT")
    _replace_fk("athletes", "club_id", "clubs", ondelete="RESTRICT")
    _replace_fk("athletes", "created_by", "users", ondelete="RESTRICT")

    # parent_athlete
    _replace_fk("parent_athlete", "parent_id", "users", ondelete="RESTRICT")
    _replace_fk("parent_athlete", "athlete_id", "athletes", ondelete="RESTRICT")

    # club_members
    _replace_fk("club_members", "club_id", "clubs", ondelete="RESTRICT")
    _replace_fk("club_members", "user_id", "users", ondelete="RESTRICT")

    # anthropometric_records
    _replace_fk(
        "anthropometric_records", "athlete_id", "athletes", ondelete="RESTRICT"
    )
    _replace_fk(
        "anthropometric_records", "evaluated_by", "users", ondelete="SET NULL"
    )

    # parent_invites
    _replace_fk("parent_invites", "athlete_id", "athletes", ondelete="RESTRICT")
    _replace_fk("parent_invites", "used_by", "users", ondelete="SET NULL")
    _replace_fk("parent_invites", "parent_user_id", "users", ondelete="SET NULL")
    _replace_fk("parent_invites", "created_by", "users", ondelete="SET NULL")

    # parental_consents
    _replace_fk(
        "parental_consents", "parent_user_id", "users", ondelete="RESTRICT"
    )
    _replace_fk(
        "parental_consents", "athlete_id", "athletes", ondelete="RESTRICT"
    )

    # privacy_policies
    _replace_fk("privacy_policies", "created_by", "users", ondelete="SET NULL")

    # athlete_ai_explanations
    _replace_fk(
        "athlete_ai_explanations",
        "generated_by_user_id",
        "users",
        ondelete="SET NULL",
    )

    # users (self-FK created_by)
    _replace_fk("users", "created_by", "users", ondelete="SET NULL")


def downgrade() -> None:
    # FKs vuelven a su forma sin ondelete explícito (default RESTRICT en MySQL).
    _replace_fk("users", "created_by", "users")
    _replace_fk("athlete_ai_explanations", "generated_by_user_id", "users")
    _replace_fk("privacy_policies", "created_by", "users")
    _replace_fk("parental_consents", "athlete_id", "athletes")
    _replace_fk("parental_consents", "parent_user_id", "users")
    _replace_fk("parent_invites", "created_by", "users")
    _replace_fk("parent_invites", "parent_user_id", "users")
    _replace_fk("parent_invites", "used_by", "users")
    _replace_fk("parent_invites", "athlete_id", "athletes")
    _replace_fk("anthropometric_records", "evaluated_by", "users")
    _replace_fk("anthropometric_records", "athlete_id", "athletes")
    _replace_fk("club_members", "user_id", "users")
    _replace_fk("club_members", "club_id", "clubs")
    _replace_fk("parent_athlete", "athlete_id", "athletes")
    _replace_fk("parent_athlete", "parent_id", "users")
    _replace_fk("athletes", "created_by", "users")
    _replace_fk("athletes", "club_id", "clubs")
    _replace_fk("athletes", "user_id", "users")

    # Restaurar nullable=False en columnas
    op.alter_column(
        "parent_invites",
        "created_by",
        existing_type=mysql.INTEGER(),
        nullable=False,
    )
    op.alter_column(
        "athlete_ai_explanations",
        "generated_by_user_id",
        existing_type=mysql.INTEGER(),
        nullable=False,
    )
    op.alter_column(
        "anthropometric_records",
        "evaluated_by",
        existing_type=mysql.INTEGER(),
        nullable=False,
    )

    # Drop soft-delete columns
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_at")

    op.drop_index("ix_athletes_deleted_at", table_name="athletes")
    op.drop_column("athletes", "deleted_at")
