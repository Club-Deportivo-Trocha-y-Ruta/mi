"""add strava sync tables (feature 025)

Revision ID: a4b5c6d7e8f9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-10 00:00:00.000000

NOTE: task T008 specified revision id ``f1a2b3c4d5e6``, but that id was
already in use by ``f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py``
(down_revision of ``a7b8c9d0e1f2``) — reusing it caused an Alembic
``CycleDetected`` error. Using ``a4b5c6d7e8f9`` instead (verified unused
against every existing ``revision =`` in ``alembic/versions/``).

Spec 025 — strava-activity-sync.

Creates ``strava_connections`` (one row per athlete<->Strava-account
authorization, at most one ACTIVE connection per athlete) and
``strava_activities`` (one row per Strava activity of a connected athlete,
idempotency anchor ``UNIQUE(strava_activity_id)``). Consent is by-action:
authorizing the Strava OAuth connection IS the affirmative consent, so
``strava_connections.consent_id`` is nullable and no separate
``parental_consents`` scope is required — the audit trail lives in
``authorized_by_user_id`` + ``connected_at``.

Privacy by schema (Ley 1581, minors — see data-model.md §2 "Explicitly
ABSENT columns"): ``strava_activities`` intentionally has NO location/map
columns (``start_latlng``, ``end_latlng``, ``map_polyline``, ``description``,
photos, segment data). Tokens on ``strava_connections`` are stored as
Fernet-encrypted ``VARBINARY(512)`` (MySQL dialect type), never plaintext.

Downgrade drops both new tables and the named ENUM types (MySQL/PostgreSQL;
no-op-safe on SQLite, which renders ENUM as VARCHAR).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import VARBINARY

# revision identifiers, used by Alembic.
revision = "a4b5c6d7e8f9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. strava_connections
    # -------------------------------------------------------------------------
    op.create_table(
        "strava_connections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("strava_athlete_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active", "disconnected", "broken", name="stravaconnectionstatus"
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("access_token_enc", VARBINARY(512), nullable=False),
        sa.Column("refresh_token_enc", VARBINARY(512), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(), nullable=False),
        sa.Column("scope_granted", sa.String(length=100), nullable=False),
        sa.Column("authorized_by_user_id", sa.Integer(), nullable=False),
        sa.Column("consent_id", sa.Integer(), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["athlete_id"], ["athletes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["authorized_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["consent_id"], ["parental_consents.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strava_connections_athlete_id",
        "strava_connections",
        ["athlete_id"],
        unique=True,
    )
    op.create_index(
        "ix_strava_connections_strava_athlete_id",
        "strava_connections",
        ["strava_athlete_id"],
        unique=True,
    )
    op.create_index(
        "ix_strava_connections_status", "strava_connections", ["status"]
    )

    # -------------------------------------------------------------------------
    # 2. strava_activities
    # -------------------------------------------------------------------------
    op.create_table(
        "strava_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("strava_activity_id", sa.BigInteger(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column(
            "name", sa.String(length=255), nullable=False, server_default=""
        ),
        sa.Column("sport_type", sa.String(length=50), nullable=False),
        sa.Column("start_date_utc", sa.DateTime(), nullable=False),
        sa.Column("start_date_local", sa.DateTime(), nullable=False),
        sa.Column("elapsed_time_s", sa.Integer(), nullable=False),
        sa.Column("moving_time_s", sa.Integer(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("total_elevation_gain_m", sa.Float(), nullable=True),
        sa.Column("average_heartrate", sa.Float(), nullable=True),
        sa.Column("max_heartrate", sa.Float(), nullable=True),
        sa.Column(
            "is_trainer", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "upstream_state",
            sa.Enum("present", "removed_upstream", name="stravaupstreamstate"),
            nullable=False,
            server_default="present",
        ),
        sa.Column(
            "ingest_source",
            sa.Enum("webhook", "reconcile", name="stravaingestsource"),
            nullable=False,
        ),
        sa.Column(
            "summary_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("training_session_id", sa.Integer(), nullable=True),
        sa.Column("linked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("linked_at", sa.DateTime(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["athlete_id"], ["athletes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["strava_connections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["training_session_id"],
            ["training_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["linked_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "strava_activity_id", name="uq_strava_activities_strava_activity_id"
        ),
    )
    op.create_index(
        "ix_strava_activities_athlete_id", "strava_activities", ["athlete_id"]
    )
    op.create_index(
        "ix_strava_activities_start_date_utc",
        "strava_activities",
        ["start_date_utc"],
    )
    # Sirve tanto la vista de revisión del coach (training_session_id IS NULL
    # ORDER BY start_date_utc DESC) como el detalle de sesión
    # (GET /training-sessions/{id}/activities) — data-model.md §5.
    op.create_index(
        "ix_strava_activities_session_start",
        "strava_activities",
        ["training_session_id", "start_date_utc"],
    )


def downgrade() -> None:
    # ``drop_table`` removes each table's own indexes as part of the DROP.
    # (Dropping the composite index first fails on MySQL when it is the index
    # backing the ``training_session_id`` FK — "needed in a foreign key
    # constraint".) Order: strava_activities first (it FKs strava_connections).
    op.drop_table("strava_activities")
    op.drop_table("strava_connections")

    # Drop named ENUM types (MySQL/PostgreSQL no-op-safe on SQLite).
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        for enum_name in (
            "stravaingestsource",
            "stravaupstreamstate",
            "stravaconnectionstatus",
        ):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
