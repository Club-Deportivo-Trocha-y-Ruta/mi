"""newsletter stage log (feature 038, T102)

Revision ID: 6b998c214e5a
Revises: f7a8b9c0d1e3
Create Date: 2026-09-02 12:00:00.000000

Feature 038 (Bitácora de etapa — family newsletter redesign). Capa de datos
para el contenido v2 (StageLog) de ``athlete_monthly_newsletters`` y el
tracking de entrega/lectura por familia.

1. ``athlete_monthly_newsletters`` (+7 columnas, todas seguras hacia atrás):
   - ``content_version`` SMALLINT NOT NULL DEFAULT 1 — 1 = boletín legacy
     (plantillas v1), 2 = bitácora (StageLog v2). Filas existentes quedan en
     1 (AC-7.1: "Convertir a bitácora" es una acción explícita del coach,
     nunca automática).
   - ``stage_log_json`` JSON NULL — ``StageLog.model_dump()`` (vista coach,
     incluye ``block_states``/``grounding_violations``); NULL para filas v1.
     Se re-deriva en cada PATCH que toque overrides/hidden/coach_note.
   - ``stage_overrides`` JSON NULL — ``{block: value}`` edición manual del
     coach por bloque narrativo (ver ``data-model.md`` §3).
   - ``hidden_blocks`` JSON NULL — subconjunto de bloques opcionales que el
     coach decidió ocultar (``analyst_reading``, ``photos``, ``badges``,
     ``coach_note``).
   - ``coach_note`` VARCHAR(600) NULL — "Nota del entrenador", ≤ 60 palabras,
     redactada (nombres prohibidos del club) antes de persistir — igual que
     el resto de texto libre del coach en este módulo (ver
     ``_redact_names`` en ``app/services/ai/use_cases/monthly_report.py``).
   - ``read_at`` / ``read_by_user_id`` — primera lectura web de un padre
     (``POST /api/parents/.../newsletters/{id}/read``, idempotente).
     ``read_by_user_id`` usa ``ON DELETE SET NULL`` (mismo patrón que
     ``generated_by_user_id``/``approved_by_user_id`` en la tabla: no se
     bloquea el borrado de un usuario por haber leído un boletín).

2. Nueva tabla ``newsletter_delivery_events`` — una fila por evento de
   entrega/lectura (``sent``, ``delivered``, ``opened``, ``clicked``,
   ``bounced``, ``web_read``). ``newsletter_id`` con ``ON DELETE CASCADE``
   (el historial de entrega no tiene sentido sin el boletín); ``parent_user_id``
   con ``ON DELETE SET NULL`` (igual criterio que ``read_by_user_id`` arriba).
   ``provider_event_id`` UNIQUE NULL — id `svix-id` del webhook de Resend,
   usado como llave de idempotencia (feature 038 P3, T401). Índice compuesto
   ``(newsletter_id, event_type)`` para el panel de entrega del studio.

   Privacidad (Ley 1581): esta tabla NUNCA almacena emails, nombres, IPs ni
   user-agents — solo ids + timestamps + tipo de evento.

Enum ``DeliveryEventType`` con ``values_callable`` (minúsculas), mismo patrón
que ``NewsletterStatus``/``LinkAuditAction``/``SessionKind`` en este proyecto.

Compatibilidad SQLite (tests, offline lane): los tests corren sobre
``Base.metadata.create_all`` — NO ejecutan esta migración. Para que sea
además reproducible localmente con SQLite (sin MySQL), el ALTER de
``athlete_monthly_newsletters`` usa ``batch_alter_table`` (agrega columna +
FK en un solo paso "copy-and-move", requerido por SQLite para constraints —
ver ``d4e5f6a7b8c9``). La tabla nueva usa ``create_table`` con FKs inline,
soportado nativamente por ambos dialectos.

Reversible: ``downgrade()`` dropea la tabla nueva, su enum nativo (MySQL) y
las 7 columnas agregadas. Ningún dato previo a esta migración existe en
ellas (todo NULL/default) — no hay pérdida de datos funcionales al revertir.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b998c214e5a"
down_revision: Union[str, None] = "f7a8b9c0d1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Valores de enum persistidos (minúsculas, coherentes con values_callable de
# DeliveryEventType en app/models/newsletter_delivery_event.py).
DELIVERY_EVENT_TYPE_VALUES = (
    "sent",
    "delivered",
    "opened",
    "clicked",
    "bounced",
    "web_read",
)


def upgrade() -> None:
    # ── 1. athlete_monthly_newsletters: +7 columnas (contenido bitácora) ────
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
            sa.Column("stage_log_json", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stage_overrides", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("hidden_blocks", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("coach_note", sa.String(length=600), nullable=True)
        )
        batch_op.add_column(
            sa.Column("read_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("read_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_athlete_monthly_newsletters_read_by_user_id",
            "users",
            ["read_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ── 2. Nueva tabla newsletter_delivery_events ────────────────────────────
    op.create_table(
        "newsletter_delivery_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("newsletter_id", sa.Integer(), nullable=False),
        sa.Column("parent_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum(*DELIVERY_EVENT_TYPE_VALUES, name="newsletterdeliveryeventtype"),
            nullable=False,
        ),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("provider_event_id", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["newsletter_id"],
            ["athlete_monthly_newsletters.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_event_id", name="uq_newsletter_delivery_events_provider_event_id"
        ),
    )
    op.create_index(
        "ix_newsletter_delivery_events_provider_message_id",
        "newsletter_delivery_events",
        ["provider_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_newsletter_delivery_events_newsletter_event_type",
        "newsletter_delivery_events",
        ["newsletter_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index(
        "ix_newsletter_delivery_events_newsletter_event_type",
        table_name="newsletter_delivery_events",
    )
    op.drop_index(
        "ix_newsletter_delivery_events_provider_message_id",
        table_name="newsletter_delivery_events",
    )
    op.drop_table("newsletter_delivery_events")

    with op.batch_alter_table("athlete_monthly_newsletters") as batch_op:
        batch_op.drop_constraint(
            "fk_athlete_monthly_newsletters_read_by_user_id",
            type_="foreignkey",
        )
        batch_op.drop_column("read_by_user_id")
        batch_op.drop_column("read_at")
        batch_op.drop_column("coach_note")
        batch_op.drop_column("hidden_blocks")
        batch_op.drop_column("stage_overrides")
        batch_op.drop_column("stage_log_json")
        batch_op.drop_column("content_version")

    # Drop del tipo enum nativo (MySQL). SQLite usa VARCHAR + CHECK que
    # desaparece junto con la tabla.
    if dialect != "sqlite":
        sa.Enum(name="newsletterdeliveryeventtype").drop(bind, checkfirst=True)
