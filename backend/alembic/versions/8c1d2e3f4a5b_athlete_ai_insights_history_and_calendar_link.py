"""athlete_ai_insights history + calendar -> race_event link (BE-1)

Revision ID: 8c1d2e3f4a5b
Revises: 6e01932b21fb
Create Date: 2026-05-22 10:00:00.000000

Fase BE-1 del workflow "Histórico de análisis IA por atleta + asociación
calendar↔race_event".

Cambios:

1) `agent_runs.athlete_id` (nullable + FK SET NULL):
   - Permite query directo "todos los runs de un atleta" sin tener que
     parsear `input_json` (que sigue siendo la fuente histórica).
   - Backfill desde `input_json->>'athlete_id'` (MySQL via JSON_EXTRACT,
     SQLite via json_extract). Filas sin athlete_id en el payload quedan
     NULL — no rompemos runs históricos de chat libre.
   - Índice compuesto `(athlete_id, started_at DESC)` para listado paginado
     "últimos runs del atleta".

2) `athlete_ai_insights` versionado:
   - Add `deprecated_at` (NULL = activo). Cuando un nuevo insight
     reemplaza a uno anterior (mismo athlete+season+valida), el viejo
     se marca con timestamp y queda como histórico inmutable.
   - Add `superseded_by_insight_id` (FK self ON DELETE SET NULL): traza
     qué insight nuevo reemplaza al actual.
   - Add `is_active` SMALLINT NULL — sentinel para emular UNIQUE parcial
     "solo puede haber UN insight activo por (athlete, season, valida)":
     valor `1` = activo, `NULL` = no activo (deprecado o no aprobado).
     Truco: en SQL estándar (MySQL InnoDB + SQLite) NULL es DISTINCT
     en UNIQUE constraints, así que `(athlete_id, season, valida_num, NULL)`
     no colisiona con otros NULL pero `(athlete_id, season, valida_num, 1)`
     sí colisiona con otro `(..., 1)`. Esto da la semántica de filtro
     parcial sin necesitar PostgreSQL.
   - Backfill: insights que ya estaban `coach_approved=1 AND archived_at IS NULL`
     se marcan como activos (`is_active=1`).
   - Relax del CHECK `ck_insights_valida_num_positive` de `valida_num >= 1`
     a `valida_num >= 0`: el valor `0` se reserva para use_cases agregados
     a nivel temporada (ej. `season_summary`) donde no hay válida específica.
     NULL sigue significando "no aplica" (ej. analítica longitudinal entre
     temporadas, futuro).

3) `calendar_events.race_event_id` (nullable + FK SET NULL):
   - Link explícito calendar→race. Hoy ya existe `race_events.calendar_event_id`
     (FK inversa, migración 04536432643f). Mantener ambos genera redundancia
     potencial pero NO ciclo de FK destructivo (ambas son nullable +
     SET NULL). El servicio en BE-2 debe mantener la coherencia
     bidireccional al crear/actualizar.
   - CHECK `ck_calendar_competition_race_event`: si `event_type='competition'`
     entonces `race_event_id` NO PUEDE ser NULL. Aplica solo a filas nuevas:
     legacy queda NULL — el coach las completa manualmente vía el script
     `backend/scripts/backfill_calendar_race_events.py` (dry-run).
   - NO se hace backfill masivo automático aquí: la decisión de qué evento
     de calendario corresponde a qué race_event requiere juicio del coach
     cuando hay ambigüedad (fechas/ubicaciones aproximadas).

Compatibilidad SQLite (tests):
- Los CHECK + add_column de FK se aplican vía `batch_alter_table` solo donde
  SQLite no soporta ALTER directo.
- Los enums no se tocan en esta migración (no se crean nuevos).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8c1d2e3f4a5b"
down_revision: Union[str, None] = "6e01932b21fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_OLD_VALIDA_CHECK = "ck_insights_valida_num_positive"
_NEW_VALIDA_CHECK = "ck_insights_valida_num_nonneg"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # =======================================================================
    # 1) agent_runs.athlete_id
    # =======================================================================
    if dialect == "sqlite":
        # SQLite no soporta ADD COLUMN con FK + ON DELETE; usar batch.
        with op.batch_alter_table("agent_runs") as batch_op:
            batch_op.add_column(
                sa.Column("athlete_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_agent_runs_athlete_id",
                "athletes",
                ["athlete_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.add_column(
            "agent_runs",
            sa.Column("athlete_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_agent_runs_athlete_id",
            "agent_runs",
            "athletes",
            ["athlete_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Índice compuesto. MySQL acepta DESC en índice (ignora si es B-tree
    # normal); SQLite ignora la palabra DESC silenciosamente. SQLAlchemy
    # no expone DESC en op.create_index, así que pasamos texto raw en MySQL.
    op.create_index(
        "ix_agent_runs_athlete_started",
        "agent_runs",
        ["athlete_id", "started_at"],
        unique=False,
    )

    # Backfill condicional por dialecto.
    if dialect == "mysql":
        op.execute(
            """
            UPDATE agent_runs
            SET athlete_id = CAST(
                JSON_UNQUOTE(JSON_EXTRACT(input_json, '$.athlete_id')) AS UNSIGNED
            )
            WHERE athlete_id IS NULL
              AND JSON_EXTRACT(input_json, '$.athlete_id') IS NOT NULL
            """
        )
    elif dialect == "sqlite":
        op.execute(
            """
            UPDATE agent_runs
            SET athlete_id = CAST(json_extract(input_json, '$.athlete_id') AS INTEGER)
            WHERE athlete_id IS NULL
              AND json_extract(input_json, '$.athlete_id') IS NOT NULL
            """
        )
    # PostgreSQL u otros: skip backfill (no es target).

    # =======================================================================
    # 2) athlete_ai_insights: deprecation + active sentinel + relax valida CHECK
    # =======================================================================
    if dialect == "sqlite":
        # En SQLite los CHECK están embebidos en la tabla; batch_alter_table
        # recrea la tabla aplicando los nuevos constraints.
        with op.batch_alter_table(
            "athlete_ai_insights",
            # Pasamos los CHECK actuales conocidos para que el recreate no
            # los pierda; reemplazamos el de valida_num por la versión relax.
            table_args=(
                sa.CheckConstraint(
                    "coach_edits_count >= 0",
                    name="ck_insights_coach_edits_count_nonneg",
                ),
                sa.CheckConstraint(
                    "valida_num IS NULL OR valida_num >= 0",
                    name=_NEW_VALIDA_CHECK,
                ),
            ),
        ) as batch_op:
            batch_op.add_column(
                sa.Column("deprecated_at", sa.DateTime(), nullable=True)
            )
            batch_op.add_column(
                sa.Column(
                    "superseded_by_insight_id", sa.Integer(), nullable=True
                )
            )
            batch_op.add_column(
                sa.Column("is_active", sa.SmallInteger(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_insights_superseded_by",
                "athlete_ai_insights",
                ["superseded_by_insight_id"],
                ["id"],
                ondelete="SET NULL",
            )
            # NOTE: el batch recrea la tabla con los CHECK indicados arriba.
            # El CHECK viejo `ck_insights_valida_num_positive` queda
            # implícitamente reemplazado (batch_alter_table regenera DDL).
    else:
        # MySQL: ALTER TABLE directo.
        op.add_column(
            "athlete_ai_insights",
            sa.Column("deprecated_at", sa.DateTime(), nullable=True),
        )
        op.add_column(
            "athlete_ai_insights",
            sa.Column("superseded_by_insight_id", sa.Integer(), nullable=True),
        )
        op.add_column(
            "athlete_ai_insights",
            sa.Column("is_active", sa.SmallInteger(), nullable=True),
        )
        op.create_foreign_key(
            "fk_insights_superseded_by",
            "athlete_ai_insights",
            "athlete_ai_insights",
            ["superseded_by_insight_id"],
            ["id"],
            ondelete="SET NULL",
        )
        # Relax CHECK: drop viejo + add nuevo. Usamos `DROP CONSTRAINT`
        # (portable: MySQL 8.0.19+ y MariaDB 10.2+). `DROP CHECK` es
        # MySQL-only y rompe en MariaDB (prod Hostinger corre MariaDB).
        op.execute(
            f"ALTER TABLE athlete_ai_insights DROP CONSTRAINT {_OLD_VALIDA_CHECK}"
        )
        op.create_check_constraint(
            _NEW_VALIDA_CHECK,
            "athlete_ai_insights",
            "valida_num IS NULL OR valida_num >= 0",
        )

    # Backfill: insights ya aprobados y no archivados → activos.
    op.execute(
        """
        UPDATE athlete_ai_insights
        SET is_active = 1
        WHERE coach_approved = 1
          AND archived_at IS NULL
          AND deprecated_at IS NULL
        """
    )

    # UNIQUE parcial emulado: NULL es distinct en MySQL/SQLite, así que
    # múltiples filas con is_active=NULL pueden coexistir, y solo UN
    # is_active=1 puede existir por terna.
    op.create_unique_constraint(
        "uq_insights_active_terna",
        "athlete_ai_insights",
        ["athlete_id", "season", "valida_num", "is_active"],
    )

    op.create_index(
        "ix_insights_deprecated_at",
        "athlete_ai_insights",
        ["deprecated_at"],
        unique=False,
    )

    # =======================================================================
    # 3) calendar_events.race_event_id + CHECK competition implies race_event
    # =======================================================================
    # MySQL rechaza CHECK que referencia una columna usada en FK con
    # ON DELETE SET NULL (error 3823). Por eso la FK se crea con
    # ON DELETE RESTRICT: el coach debe desasociar el calendar_event
    # antes de borrar el race_event. SQLite no impone esa restricción
    # pero mantenemos RESTRICT para consistencia semántica.
    if dialect == "sqlite":
        with op.batch_alter_table(
            "calendar_events",
            table_args=(
                sa.CheckConstraint(
                    "end_at >= start_at",
                    name="ck_calendar_event_range",
                ),
                sa.CheckConstraint(
                    "event_type != 'competition' OR race_event_id IS NOT NULL",
                    name="ck_calendar_competition_race_event",
                ),
            ),
        ) as batch_op:
            batch_op.add_column(
                sa.Column("race_event_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_calendar_events_race_event_id",
                "race_events",
                ["race_event_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    else:
        op.add_column(
            "calendar_events",
            sa.Column("race_event_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_calendar_events_race_event_id",
            "calendar_events",
            "race_events",
            ["race_event_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        # Backfill defensivo: si hay calendar_events con event_type='competition'
        # y race_event_id NULL, intentamos asociarlos por (date, location) con
        # race_events de la temporada vigente. Lo que no matchee queda NULL y
        # el CHECK falla — el operador debe correr el script de backfill manual.
        op.execute(
            """
            UPDATE calendar_events ce
            JOIN race_events re
              ON re.event_date = DATE(ce.start_at)
             AND (
                  LOWER(re.location) = LOWER(IFNULL(ce.location, ''))
               OR LOWER(re.name) LIKE CONCAT('%', LOWER(IFNULL(ce.title, '')), '%')
             )
            SET ce.race_event_id = re.id
            WHERE ce.event_type = 'competition'
              AND ce.race_event_id IS NULL
            """
        )
        op.create_check_constraint(
            "ck_calendar_competition_race_event",
            "calendar_events",
            "event_type != 'competition' OR race_event_id IS NOT NULL",
        )

    op.create_index(
        "ix_calendar_events_race_event_id",
        "calendar_events",
        ["race_event_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # =======================================================================
    # 3') calendar_events.race_event_id
    # =======================================================================
    op.drop_index(
        "ix_calendar_events_race_event_id", table_name="calendar_events"
    )
    if dialect == "sqlite":
        with op.batch_alter_table(
            "calendar_events",
            table_args=(
                sa.CheckConstraint(
                    "end_at >= start_at",
                    name="ck_calendar_event_range",
                ),
            ),
        ) as batch_op:
            batch_op.drop_constraint(
                "fk_calendar_events_race_event_id", type_="foreignkey"
            )
            batch_op.drop_column("race_event_id")
    else:
        op.drop_constraint(
            "ck_calendar_competition_race_event",
            "calendar_events",
            type_="check",
        )
        op.drop_constraint(
            "fk_calendar_events_race_event_id",
            "calendar_events",
            type_="foreignkey",
        )
        op.drop_column("calendar_events", "race_event_id")

    # =======================================================================
    # 2') athlete_ai_insights: revert deprecation + sentinel + valida CHECK
    # =======================================================================
    op.drop_index(
        "ix_insights_deprecated_at", table_name="athlete_ai_insights"
    )
    op.drop_constraint(
        "uq_insights_active_terna", "athlete_ai_insights", type_="unique"
    )

    if dialect == "sqlite":
        with op.batch_alter_table(
            "athlete_ai_insights",
            table_args=(
                sa.CheckConstraint(
                    "coach_edits_count >= 0",
                    name="ck_insights_coach_edits_count_nonneg",
                ),
                sa.CheckConstraint(
                    "valida_num IS NULL OR valida_num >= 1",
                    name=_OLD_VALIDA_CHECK,
                ),
            ),
        ) as batch_op:
            batch_op.drop_constraint(
                "fk_insights_superseded_by", type_="foreignkey"
            )
            batch_op.drop_column("is_active")
            batch_op.drop_column("superseded_by_insight_id")
            batch_op.drop_column("deprecated_at")
    else:
        op.execute(
            f"ALTER TABLE athlete_ai_insights DROP CONSTRAINT {_NEW_VALIDA_CHECK}"
        )
        op.create_check_constraint(
            _OLD_VALIDA_CHECK,
            "athlete_ai_insights",
            "valida_num IS NULL OR valida_num >= 1",
        )
        op.drop_constraint(
            "fk_insights_superseded_by",
            "athlete_ai_insights",
            type_="foreignkey",
        )
        op.drop_column("athlete_ai_insights", "is_active")
        op.drop_column("athlete_ai_insights", "superseded_by_insight_id")
        op.drop_column("athlete_ai_insights", "deprecated_at")

    # =======================================================================
    # 1') agent_runs.athlete_id
    # =======================================================================
    op.drop_index("ix_agent_runs_athlete_started", table_name="agent_runs")
    if dialect == "sqlite":
        with op.batch_alter_table("agent_runs") as batch_op:
            batch_op.drop_constraint(
                "fk_agent_runs_athlete_id", type_="foreignkey"
            )
            batch_op.drop_column("athlete_id")
    else:
        op.drop_constraint(
            "fk_agent_runs_athlete_id", "agent_runs", type_="foreignkey"
        )
        op.drop_column("agent_runs", "athlete_id")
