"""race agentic module tables (insights, runs, events, anonymization)

Revision ID: 7a8b9c0d1e2f
Revises: 64c263edd07f
Create Date: 2026-05-20 12:00:00.000000

Tablas para el modulo agentico LangGraph de analisis de resultados de carrera
(Fase race-results v2 — design.md §3.1-3.5):

1. `agent_runs`             — ejecuciones del grafo (input, status, output, costo)
2. `agent_run_events`       — stream de eventos por run (node_start/end, HITL,
                              explain, token, error, done) para SSE/polling
3. `athlete_ai_insights`    — insights publicables aprobados por el coach
                              (use cases: progression, podium_gap, projection,
                              season_summary)
4. `anonymization_mappings` — pseudonim <-> id real (para enviar solo pseudonims
                              al LLM y guardar la traza de des-anonimizacion)

Notas de implementacion:
- Orden de creacion: agent_runs -> agent_run_events / athlete_ai_insights /
  anonymization_mappings (FKs apuntan a agent_runs).
- Enums Python se declaran inline con `sa.Enum(..., name='...')` para que MySQL
  cree el tipo nativo y SQLite (tests) caiga a VARCHAR + CHECK.
- `created_at` / `updated_at` usan `server_default=CURRENT_TIMESTAMP` y
  `ON UPDATE CURRENT_TIMESTAMP` (en MySQL via `onupdate=sa.text(...)`) para que
  la insercion funcione antes de que existan los modelos SQLAlchemy de F1.
- Timestamps `started_at`, `generated_at` son NOT NULL y se setean desde la app.
- Polling de eventos: `ix_run_events_run_seq (run_id, seq)` soporta
  `WHERE run_id=? AND seq>? ORDER BY seq` usado por el endpoint
  `GET /agent-runs/{external_run_id}/events?since=N`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7a8b9c0d1e2f"
down_revision: Union[str, None] = "64c263edd07f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Enums (definidos a nivel modulo para reuso en upgrade/downgrade)
# ---------------------------------------------------------------------------
AGENT_RUN_STATUS_VALUES = (
    "running",
    "awaiting_hitl",
    "completed",
    "rejected",
    "failed",
    "cancelled",
)

AGENT_RUN_EVENT_TYPE_VALUES = (
    "node_start",
    "node_end",
    "hitl_request",
    "hitl_response",
    "explain",
    "token",
    "error",
    "done",
)

INSIGHT_CONFIDENCE_VALUES = ("low", "medium", "high")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Server-side timestamp defaults: solo MySQL soporta ON UPDATE CURRENT_TIMESTAMP
    # de forma nativa. En SQLite (tests) basta con CURRENT_TIMESTAMP en el insert;
    # los modelos SQLAlchemy (F1) cubriran el `onupdate` desde Python.
    created_default = sa.text("CURRENT_TIMESTAMP")
    updated_default = sa.text("CURRENT_TIMESTAMP")
    updated_onupdate = sa.text("CURRENT_TIMESTAMP") if dialect == "mysql" else None

    # -----------------------------------------------------------------------
    # 1) agent_runs
    # -----------------------------------------------------------------------
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("external_run_id", sa.String(length=64), nullable=False),
        sa.Column("graph_name", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*AGENT_RUN_STATUS_VALUES, name="agentrunstatus"),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("final_output_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("langfuse_trace_id", sa.String(length=128), nullable=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
        sa.Column("checkpoint_thread_id", sa.String(length=64), nullable=False),
        sa.Column(
            "explain_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("cost_usd", sa.Numeric(8, 5), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=created_default,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=updated_default,
            onupdate=updated_onupdate,
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_agent_runs_requested_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_run_id", name="uq_agent_runs_external_run_id"
        ),
    )
    op.create_index(
        "ix_agent_runs_user_started",
        "agent_runs",
        ["requested_by_user_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_runs_status",
        "agent_runs",
        ["status"],
        unique=False,
    )

    # -----------------------------------------------------------------------
    # 2) agent_run_events
    # -----------------------------------------------------------------------
    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(*AGENT_RUN_EVENT_TYPE_VALUES, name="agentruneventtype"),
            nullable=False,
        ),
        sa.Column("node_name", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=created_default,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_agent_run_events_run_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("seq >= 1", name="ck_agent_run_events_seq_positive"),
        sa.PrimaryKeyConstraint("id"),
        # TODO(F1): si la app no garantiza monotonicidad de `seq` por run,
        # considerar añadir UNIQUE(run_id, seq) para forzar la invariante.
    )
    op.create_index(
        "ix_run_events_run_seq",
        "agent_run_events",
        ["run_id", "seq"],
        unique=False,
    )
    op.create_index(
        "ix_run_events_type",
        "agent_run_events",
        ["event_type"],
        unique=False,
    )

    # -----------------------------------------------------------------------
    # 3) athlete_ai_insights
    # -----------------------------------------------------------------------
    op.create_table(
        "athlete_ai_insights",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("competitor_id", sa.Integer(), nullable=True),
        sa.Column("season", sa.SmallInteger(), nullable=False),
        sa.Column("valida_num", sa.SmallInteger(), nullable=True),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("use_case", sa.String(length=32), nullable=False),
        sa.Column("agent_run_id", sa.BigInteger(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("recommendations_json", sa.JSON(), nullable=False),
        sa.Column("metrics_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("principles_cited_json", sa.JSON(), nullable=False),
        sa.Column(
            "confidence",
            sa.Enum(*INSIGHT_CONFIDENCE_VALUES, name="insightconfidence"),
            nullable=False,
            server_default=sa.text("'medium'"),
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column(
            "coach_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "coach_edits_count",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("generated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=created_default,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=updated_default,
            onupdate=updated_onupdate,
        ),
        sa.CheckConstraint(
            "coach_edits_count >= 0",
            name="ck_insights_coach_edits_count_nonneg",
        ),
        sa.CheckConstraint(
            "valida_num IS NULL OR valida_num >= 1",
            name="ck_insights_valida_num_positive",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name="fk_insights_athlete_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["race_competitors.id"],
            name="fk_insights_competitor_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["race_events.id"],
            name="fk_insights_event_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_insights_agent_run_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"],
            ["users.id"],
            name="fk_insights_generated_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_insights_athlete_season",
        "athlete_ai_insights",
        ["athlete_id", "season", "valida_num"],
        unique=False,
    )
    op.create_index(
        "ix_insights_event",
        "athlete_ai_insights",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_insights_use_case",
        "athlete_ai_insights",
        ["use_case", "generated_at"],
        unique=False,
    )

    # -----------------------------------------------------------------------
    # 4) anonymization_mappings
    # -----------------------------------------------------------------------
    op.create_table(
        "anonymization_mappings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("pseudonym", sa.String(length=64), nullable=False),
        sa.Column("real_competitor_id", sa.Integer(), nullable=False),
        sa.Column("real_athlete_id", sa.Integer(), nullable=True),
        sa.Column("salt_used", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=created_default,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_anon_run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["real_competitor_id"],
            ["race_competitors.id"],
            name="fk_anon_real_competitor_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["real_athlete_id"],
            ["athletes.id"],
            name="fk_anon_real_athlete_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "pseudonym", name="uq_anon_run_pseudonym"
        ),
    )
    op.create_index(
        "ix_anon_run_athlete",
        "anonymization_mappings",
        ["run_id", "real_athlete_id"],
        unique=False,
    )


def downgrade() -> None:
    # Orden inverso a la creacion. drop_table elimina indices y FKs en cascada.
    # 4 -> 3 -> 2 -> 1 (agent_runs queda al final porque las otras 3 la
    # referencian via FK).
    op.drop_index("ix_anon_run_athlete", table_name="anonymization_mappings")
    op.drop_table("anonymization_mappings")

    op.drop_index("ix_insights_use_case", table_name="athlete_ai_insights")
    op.drop_index("ix_insights_event", table_name="athlete_ai_insights")
    op.drop_index("ix_insights_athlete_season", table_name="athlete_ai_insights")
    op.drop_table("athlete_ai_insights")

    op.drop_index("ix_run_events_type", table_name="agent_run_events")
    op.drop_index("ix_run_events_run_seq", table_name="agent_run_events")
    op.drop_table("agent_run_events")

    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_started", table_name="agent_runs")
    op.drop_table("agent_runs")

    # Drop de tipos enum en MySQL (en SQLite no aplica — son VARCHAR + CHECK).
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        sa.Enum(name="insightconfidence").drop(bind, checkfirst=True)
        sa.Enum(name="agentruneventtype").drop(bind, checkfirst=True)
        sa.Enum(name="agentrunstatus").drop(bind, checkfirst=True)
