"""add_calendar_module

Revision ID: b59ded290a0c
Revises: b2c3d4e5f6a7
Create Date: 2026-05-10 00:00:00.000000

Crea las tablas calendar_events, event_audiences y event_attendances para
el módulo de calendario. Añade la FK opcional calendar_event_id a
training_sessions y realiza backfill de los registros existentes.

Backfill:
- Por cada training_session existente se crea un calendar_event con los
  campos de fecha/hora mapeados, y se enlaza via calendar_event_id.
- La audiencia se infiere desde session_attendance (athlete_list) o
  se registra como all_club si no hay asistencias.

Downgrade:
- Elimina FK y columna calendar_event_id de training_sessions.
- Elimina las tres tablas en orden inverso.
- NO restaura datos.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "b59ded290a0c"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # 1. Crear tabla calendar_events
    # -----------------------------------------------------------------------
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("club_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "training_session",
                "competition",
                "club_event",
                "personal_training",
                "group_training",
                "rest_day",
                name="eventtype",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled",
                "confirmed",
                "cancelled",
                "completed",
                name="eventstatus",
            ),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "timezone",
            sa.String(50),
            nullable=False,
            server_default="America/Bogota",
        ),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.Column("color_hex", sa.String(7), nullable=True),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("end_at >= start_at", name="ck_calendar_event_range"),
        sa.ForeignKeyConstraint(
            ["club_id"], ["clubs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_calendar_club_start",
        "calendar_events",
        ["club_id", "start_at"],
    )

    # -----------------------------------------------------------------------
    # 2. Crear tabla event_audiences
    # -----------------------------------------------------------------------
    op.create_table(
        "event_audiences",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "audience_type",
            sa.Enum(
                "all_club",
                "category",
                "athlete_list",
                "individual",
                name="audiencetype",
            ),
            nullable=False,
        ),
        sa.Column("audience_value", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"], ["calendar_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audience_event", "event_audiences", ["event_id"])

    # -----------------------------------------------------------------------
    # 3. Crear tabla event_attendances
    # -----------------------------------------------------------------------
    op.create_table(
        "event_attendances",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("athlete_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "rsvp_status",
            sa.Enum(
                "pending",
                "accepted",
                "declined",
                "tentative",
                name="rsvpstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("rsvp_at", sa.DateTime(), nullable=True),
        sa.Column("rsvp_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "actual_status",
            sa.Enum(
                "unknown",
                "attended",
                "no_show",
                "excused",
                name="actualattendancestatus",
            ),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"], ["calendar_events.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"], ["athletes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["rsvp_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "athlete_id", name="uq_event_attendance"),
    )

    # -----------------------------------------------------------------------
    # 4. Añadir columna calendar_event_id a training_sessions
    # -----------------------------------------------------------------------
    op.add_column(
        "training_sessions",
        sa.Column("calendar_event_id", sa.BigInteger(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_ts_calendar_event",
        "training_sessions",
        ["calendar_event_id"],
    )
    op.create_foreign_key(
        "fk_ts_calendar_event",
        "training_sessions",
        "calendar_events",
        ["calendar_event_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -----------------------------------------------------------------------
    # 5. Backfill: crear calendar_events para cada training_session existente
    # En modo offline (sql=True), op.get_bind() retorna None y se omite.
    # -----------------------------------------------------------------------
    if context.is_offline_mode():
        # Modo offline (sql=True) — no hay conexión real para el backfill.
        # Al aplicar en producción con MySQL real, el backfill corre automáticamente.
        return

    conn = op.get_bind()

    # Obtener todos los training_sessions existentes
    sessions = conn.execute(
        sa.text(
            """
            SELECT id, club_id, created_by_user_id, status,
                   scheduled_date, scheduled_start_time, duration_min,
                   location, technical_focus, description,
                   created_at, updated_at
            FROM training_sessions
            WHERE calendar_event_id IS NULL
            """
        )
    ).fetchall()

    for session in sessions:
        (
            ts_id,
            club_id,
            created_by_user_id,
            ts_status,
            scheduled_date,
            scheduled_start_time,
            duration_min,
            location,
            technical_focus,
            description,
            created_at,
            updated_at,
        ) = session

        # Mapear status de training_session a EventStatus
        if ts_status == "executed":
            event_status = "completed"
        elif ts_status == "cancelled":
            event_status = "cancelled"
        else:
            event_status = "scheduled"

        # Calcular start_at y end_at
        # scheduled_start_time puede venir como timedelta (MySQL) o time
        import datetime as dt_module

        if isinstance(scheduled_start_time, dt_module.timedelta):
            total_seconds = int(scheduled_start_time.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            start_time = dt_module.time(hours % 24, minutes, seconds)
        else:
            start_time = scheduled_start_time

        if isinstance(scheduled_date, str):
            scheduled_date = dt_module.date.fromisoformat(scheduled_date)

        start_at = dt_module.datetime.combine(scheduled_date, start_time)
        end_at = start_at + dt_module.timedelta(minutes=int(duration_min))

        # Insertar en calendar_events
        result = conn.execute(
            sa.text(
                """
                INSERT INTO calendar_events
                    (club_id, event_type, status, title, description,
                     location, start_at, end_at, all_day, timezone,
                     event_data, created_by_user_id, created_at, updated_at)
                VALUES
                    (:club_id, 'training_session', :status, :title, :description,
                     :location, :start_at, :end_at, 0, 'America/Bogota',
                     :event_data, :created_by_user_id, :created_at, :updated_at)
                """
            ),
            {
                "club_id": club_id,
                "status": event_status,
                "title": technical_focus,
                "description": description,
                "location": location,
                "start_at": start_at,
                "end_at": end_at,
                "event_data": f'{{"training_session_id": {ts_id}}}',
                "created_by_user_id": created_by_user_id,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        new_event_id = result.lastrowid

        # Actualizar training_session con el nuevo calendar_event_id
        conn.execute(
            sa.text(
                "UPDATE training_sessions SET calendar_event_id = :event_id WHERE id = :ts_id"
            ),
            {"event_id": new_event_id, "ts_id": ts_id},
        )

        # Derivar audiencia desde session_attendance
        attendance_rows = conn.execute(
            sa.text(
                "SELECT athlete_id FROM session_attendance WHERE session_id = :ts_id"
            ),
            {"ts_id": ts_id},
        ).fetchall()

        if attendance_rows:
            athlete_ids = [row[0] for row in attendance_rows]
            ids_json = "[" + ", ".join(str(aid) for aid in athlete_ids) + "]"
            audience_value = f'{{"athlete_ids": {ids_json}}}'
            audience_type = "athlete_list"
        else:
            audience_value = "{}"
            audience_type = "all_club"

        conn.execute(
            sa.text(
                """
                INSERT INTO event_audiences (event_id, audience_type, audience_value)
                VALUES (:event_id, :audience_type, :audience_value)
                """
            ),
            {
                "event_id": new_event_id,
                "audience_type": audience_type,
                "audience_value": audience_value,
            },
        )


def downgrade() -> None:
    # Eliminar FK y constraint unique antes de la columna
    op.drop_constraint("fk_ts_calendar_event", "training_sessions", type_="foreignkey")
    op.drop_constraint("uq_ts_calendar_event", "training_sessions", type_="unique")
    op.drop_column("training_sessions", "calendar_event_id")

    # Eliminar tablas en orden inverso (respetando FK)
    op.drop_table("event_attendances")
    op.drop_table("event_audiences")
    op.drop_index("idx_calendar_club_start", table_name="calendar_events")
    op.drop_table("calendar_events")

    # Eliminar tipos Enum (solo necesario en PostgreSQL; en MySQL se eliminan con la tabla)
    # Para compatibilidad futura con Postgres se dejan comentados:
    # op.execute("DROP TYPE IF EXISTS eventtype")
    # op.execute("DROP TYPE IF EXISTS eventstatus")
    # op.execute("DROP TYPE IF EXISTS audiencetype")
    # op.execute("DROP TYPE IF EXISTS rsvpstatus")
    # op.execute("DROP TYPE IF EXISTS actualattendancestatus")
