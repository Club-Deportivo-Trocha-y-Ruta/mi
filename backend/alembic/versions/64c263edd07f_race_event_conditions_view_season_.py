"""race events conditions + view season_standings + minus_laps status + tier

Revision ID: 64c263edd07f
Revises: d7f1a2b3c4e5
Create Date: 2026-05-19 10:00:00.000000

Delta del Paso 2 (Fase 1.7 — módulo Resultados Copa Valle):

1. `race_events`: agrega campos de condiciones del día (clima, temperatura,
   superficie, altitud, notas) y trazabilidad de PDFs originales
   (pdf_results_filename, pdf_general_filename). Todos NULL — backward compatible.

2. `race_categories`: agrega columna `tier` (enum menores/juvenil/adulto/master)
   NULL para soportar filtros analíticos sin enumerar codes uno a uno.

3. `race_results.status`: agrega valor `minus_laps` al enum (manteniendo `dns`
   heredado del schema previo). Patrón observado en V-IV — workflow §2.2.

4. `race_results`: agrega índice `ix_race_results_category_points` para acelerar
   queries de standings (ORDER BY points_awarded DESC por categoría).

5. Crea VIEW `season_standings` (design.md §3.5) — agregación de puntos por
   (season, category, competitor).

Notas de implementación:
- ALTER ENUM se ejecuta solo en MySQL (en SQLite los enums son `VARCHAR` + CHECK).
- La VIEW se crea con CREATE OR REPLACE en MySQL; en SQLite se usa CREATE VIEW
  (no soporta OR REPLACE) tras DROP IF EXISTS.
- Downgrade revierte todo, incluida la VIEW.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "64c263edd07f"
down_revision: Union[str, None] = "d7f1a2b3c4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# View — season_standings (design.md §3.5)
# ---------------------------------------------------------------------------
# Agrega puntos por (season_year, category_id, competitor_id). Une race_results
# con race_events → race_series para tener la temporada disponible.
# Excluye soft-deletes (deleted_at IS NULL).
SEASON_STANDINGS_VIEW_SQL = """
CREATE VIEW season_standings AS
SELECT
    s.season_year AS season,
    r.category_id AS category_id,
    r.competitor_id AS competitor_id,
    SUM(r.points_awarded) AS total_points,
    COUNT(*) AS races_run,
    SUM(CASE WHEN r.position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS podiums,
    SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) AS wins
FROM race_results r
JOIN race_events e ON e.id = r.event_id
JOIN race_series s ON s.id = e.series_id
WHERE r.deleted_at IS NULL
GROUP BY s.season_year, r.category_id, r.competitor_id
"""


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ---- 1. race_events: campos clima + trazabilidad PDF ------------------
    with op.batch_alter_table("race_events") as batch_op:
        batch_op.add_column(sa.Column("climate", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("temperature_c", sa.Numeric(4, 1), nullable=True))
        batch_op.add_column(
            sa.Column(
                "surface_condition",
                sa.Enum(
                    "seca",
                    "humeda",
                    "barro",
                    "lluvia",
                    "mixta",
                    name="racesurfacecondition",
                ),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("altitude_msnm", sa.SmallInteger(), nullable=True))
        batch_op.add_column(sa.Column("weather_notes", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("pdf_results_filename", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("pdf_general_filename", sa.String(length=255), nullable=True)
        )

    # ---- 2. race_categories: agrega columna tier --------------------------
    with op.batch_alter_table("race_categories") as batch_op:
        batch_op.add_column(
            sa.Column(
                "tier",
                sa.Enum(
                    "menores",
                    "juvenil",
                    "adulto",
                    "master",
                    name="racecategorytier",
                ),
                nullable=True,
            )
        )

    # ---- 3. race_results.status: agrega valor 'minus_laps' ---------------
    # En MySQL: ALTER de la columna con el nuevo conjunto de valores enum.
    # En SQLite: el enum se materializa como VARCHAR + CHECK constraint —
    # batch_alter_table re-crea la tabla; aquí se hace por seguridad.
    if dialect == "mysql":
        op.execute(
            "ALTER TABLE race_results "
            "MODIFY COLUMN status ENUM('finished','dnf','dns','dsq','minus_laps') NOT NULL"
        )
    else:
        # SQLite (tests): recrear la columna con el nuevo enum.
        with op.batch_alter_table("race_results") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=sa.Enum("finished", "dnf", "dns", "dsq", name="raceresultstatus"),
                type_=sa.Enum(
                    "finished",
                    "dnf",
                    "dns",
                    "dsq",
                    "minus_laps",
                    name="raceresultstatus",
                ),
                existing_nullable=False,
            )

    # ---- 4. Índice extra sobre (category_id, points_awarded DESC) ---------
    # Para queries del tipo "top scorers categoría X" — design.md §3.4.
    # MySQL acepta ORDER en CREATE INDEX pero SQLAlchemy lo abstrae;
    # el índice plano sirve y MySQL puede usar reverse scan.
    op.create_index(
        "ix_race_results_category_points",
        "race_results",
        ["category_id", "points_awarded"],
        unique=False,
    )

    # ---- 5. VIEW season_standings ----------------------------------------
    op.execute("DROP VIEW IF EXISTS season_standings")
    op.execute(SEASON_STANDINGS_VIEW_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ---- 5'. drop view ----------------------------------------------------
    op.execute("DROP VIEW IF EXISTS season_standings")

    # ---- 4'. drop index --------------------------------------------------
    op.drop_index("ix_race_results_category_points", table_name="race_results")

    # ---- 3'. revierte minus_laps del enum --------------------------------
    if dialect == "mysql":
        op.execute(
            "ALTER TABLE race_results "
            "MODIFY COLUMN status ENUM('finished','dnf','dns','dsq') NOT NULL"
        )
    else:
        with op.batch_alter_table("race_results") as batch_op:
            batch_op.alter_column(
                "status",
                existing_type=sa.Enum(
                    "finished",
                    "dnf",
                    "dns",
                    "dsq",
                    "minus_laps",
                    name="raceresultstatus",
                ),
                type_=sa.Enum("finished", "dnf", "dns", "dsq", name="raceresultstatus"),
                existing_nullable=False,
            )

    # ---- 2'. drop tier column + enum -------------------------------------
    with op.batch_alter_table("race_categories") as batch_op:
        batch_op.drop_column("tier")
    if dialect != "sqlite":
        sa.Enum(name="racecategorytier").drop(op.get_bind(), checkfirst=True)

    # ---- 1'. drop columnas clima + pdf ------------------------------------
    with op.batch_alter_table("race_events") as batch_op:
        batch_op.drop_column("pdf_general_filename")
        batch_op.drop_column("pdf_results_filename")
        batch_op.drop_column("weather_notes")
        batch_op.drop_column("altitude_msnm")
        batch_op.drop_column("surface_condition")
        batch_op.drop_column("temperature_c")
        batch_op.drop_column("climate")
    if dialect != "sqlite":
        sa.Enum(name="racesurfacecondition").drop(op.get_bind(), checkfirst=True)
