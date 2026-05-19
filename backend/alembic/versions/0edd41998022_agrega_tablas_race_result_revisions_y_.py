"""agrega tablas race_result_revisions y race_imports

Revision ID: 0edd41998022
Revises: 04536432643f
Create Date: 2026-05-15 22:20:54.215752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0edd41998022"
down_revision: Union[str, None] = "04536432643f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "race_imports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "dry_run",
                "committed",
                "failed",
                name="raceimportstatus",
            ),
            nullable=False,
        ),
        sa.Column("stats_json", sa.JSON(), nullable=False),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column("imported_by_user_id", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["imported_by_user_id"],
            ["users.id"],
            name="fk_race_imports_imported_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["race_series.id"],
            name="fk_race_imports_series_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_race_imports_imported_at",
        "race_imports",
        ["imported_at"],
        unique=False,
    )
    op.create_index(
        "ix_race_imports_sha256", "race_imports", ["sha256"], unique=False
    )
    op.create_index(
        "ix_race_imports_status_sha256",
        "race_imports",
        ["status", "sha256"],
        unique=False,
    )
    op.create_table(
        "race_result_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("result_id", sa.Integer(), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "create", "update", "delete", name="raceresultrevisionaction"
            ),
            nullable=False,
        ),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("diff_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            name="fk_race_result_revisions_changed_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_id"],
            ["race_results.id"],
            name="fk_race_result_revisions_result_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_race_result_revisions_changed_at",
        "race_result_revisions",
        ["changed_at"],
        unique=False,
    )
    op.create_index(
        "ix_race_result_revisions_changed_by",
        "race_result_revisions",
        ["changed_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_race_result_revisions_result_id",
        "race_result_revisions",
        ["result_id"],
        unique=False,
    )

    # Materializa el FK lógico race_results.imported_from_id -> race_imports.id
    # (la columna se creó en B3.3 sin FK física porque race_imports aún no existía).
    op.create_foreign_key(
        "fk_race_results_imported_from_id",
        "race_results",
        "race_imports",
        ["imported_from_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Quitar la FK añadida en upgrade antes de dropear race_imports.
    op.drop_constraint(
        "fk_race_results_imported_from_id",
        "race_results",
        type_="foreignkey",
    )
    # Orden inverso a la creación; drop_table dropea índices y FKs en cascada.
    op.drop_table("race_result_revisions")
    op.drop_table("race_imports")
