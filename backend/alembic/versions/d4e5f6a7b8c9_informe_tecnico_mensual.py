"""informe tecnico mensual: project profile, narrative blocks, session kind

Revision ID: d4e5f6a7b8c9
Revises: c6d7e8f9a0b1
Create Date: 2026-06-03 12:00:00.000000

Capa de datos del refactor "Informe Técnico Mensual" (estilo financiador):

1. Nueva tabla ``club_project_profiles`` (1:1 con ``clubs`` vía UNIQUE en
   ``club_id``). Metadata estática del proyecto del club que encabeza cada
   reporte mensual: nombre del proyecto, entidad ejecutora, responsable,
   propósito, objetivo general, objetivos específicos (JSON lista), y
   localización territorial. FK ``club_id`` -> ``clubs.id`` ON DELETE RESTRICT
   (no se permite borrar un club con perfil de proyecto).

2. ``monthly_reports`` (+3 columnas, todas seguras hacia atrás):
   - ``narrative_blocks`` JSON nullable — bloques estructurados del informe
     (cada bloque {ai_draft, final_text, ai_model, ai_generated_at}). NO se
     migra ``ai_summary`` existente; queda intacto.
   - ``competition_results`` JSON nullable — snapshot de podios del mes.
   - ``status`` Enum(draft, approved) NOT NULL server_default 'draft' — los
     reportes legacy quedan en 'draft'.

3. ``training_sessions`` (+2 columnas):
   - ``session_kind`` Enum(entrenamiento, actividad_conjunta, salida, otro)
     NOT NULL server_default 'entrenamiento' — sesiones legacy quedan como
     'entrenamiento'.
   - ``objectives`` Text nullable.

Patrón enum minúsculas + ``server_default`` + ``batch_alter_table`` para que
funcione tanto en MySQL (ALTER nativo) como en SQLite (recrea tabla). Espejo
exacto de la migración ``e8f9a0b1c2d3`` (race_imports upload delta).

Reversible: ``downgrade`` elimina las 5 columnas, la tabla y los tipos enum
nativos (MySQL). En SQLite los enums son VARCHAR + CHECK y desaparecen con la
columna/tabla.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Valores de enum persistidos (minúsculas, coherentes con values_callable de
# los modelos SessionKind / MonthlyReportStatus).
SESSION_KIND_VALUES = ("entrenamiento", "actividad_conjunta", "salida", "otro")
MONTHLY_REPORT_STATUS_VALUES = ("draft", "approved")


def upgrade() -> None:
    # ── 1. Nueva tabla club_project_profiles (1:1 con clubs) ────────────────
    op.create_table(
        "club_project_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(length=200), nullable=True),
        sa.Column("executing_entity", sa.String(length=200), nullable=True),
        sa.Column("report_responsible", sa.String(length=200), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("general_objective", sa.Text(), nullable=True),
        sa.Column("specific_objectives", sa.JSON(), nullable=True),
        sa.Column("territory_location", sa.String(length=200), nullable=True),
        sa.Column("territory_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["club_id"], ["clubs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("club_id", name="uq_club_project_profile_club"),
    )

    # ── 2. monthly_reports: +narrative_blocks, +competition_results, +status ─
    with op.batch_alter_table("monthly_reports") as batch_op:
        batch_op.add_column(
            sa.Column("narrative_blocks", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("competition_results", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "status",
                sa.Enum(
                    *MONTHLY_REPORT_STATUS_VALUES, name="monthlyreportstatus"
                ),
                nullable=False,
                server_default=sa.text("'draft'"),
            )
        )

    # ── 3. training_sessions: +session_kind, +objectives ────────────────────
    with op.batch_alter_table("training_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "session_kind",
                sa.Enum(*SESSION_KIND_VALUES, name="sessionkind"),
                nullable=False,
                server_default=sa.text("'entrenamiento'"),
            )
        )
        batch_op.add_column(
            sa.Column("objectives", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    with op.batch_alter_table("training_sessions") as batch_op:
        batch_op.drop_column("objectives")
        batch_op.drop_column("session_kind")

    with op.batch_alter_table("monthly_reports") as batch_op:
        batch_op.drop_column("status")
        batch_op.drop_column("competition_results")
        batch_op.drop_column("narrative_blocks")

    op.drop_table("club_project_profiles")

    # Drop de los tipos enum nativos (MySQL). SQLite usa VARCHAR + CHECK que se
    # eliminan junto con la columna/tabla.
    if dialect != "sqlite":
        sa.Enum(name="sessionkind").drop(bind, checkfirst=True)
        sa.Enum(name="monthlyreportstatus").drop(bind, checkfirst=True)
