"""multi-coach governance — audit_log, training_session_coaches, attribution columns (feature 041)

Revision ID: 45cd705c6b54
Revises: 2a8baa967cc6
Create Date: 2026-09-09 00:00:00.000000

One revision for the whole feature (data-model.md §6.1-§6.2): splitting the new
``audit_log``/``training_session_coaches`` tables from the attribution columns and
backfills would create an intermediate state where every existing session momentarily
has zero coaches, violating the bridge table's minimum-one invariant (§3).

Adds
----
1. ``audit_log`` — club-wide, append-only, privacy-minimised audit trail (§1-§2). No
   ``updated_at``; the application must never UPDATE/DELETE this table outside
   ``app/services/retention.py``.
2. ``training_session_coaches`` — bridge table for multi-coach sessions (§3), composite
   PK, backfilled so every existing session keeps exactly its creator as coach.
3. Additive, nullable attribution columns (``<verb>_by_user_id`` / timestamp pairs) on
   14 existing tables per §4: ``users``, ``athletes``, ``session_attendance``,
   ``calendar_events``, ``monthly_reports``, ``athlete_monthly_newsletters``,
   ``athlete_ai_insights``, ``session_media``, ``anthropometric_records``,
   ``race_imports``, ``race_series``, ``club_project_profiles``, ``club_members``,
   ``agent_runs``.
4. Three read-path indexes: ``ix_athletes_deleted_at``, ``ix_calendar_events_deleted_at``,
   ``ix_session_attendance_archived_at`` (§6.2 point 4 — every archive/soft-delete
   listing filters on these from this feature onward).
5. Backfills B1, B2, B4, B5, B6, B7 (§6.3, plus the B7 delta from
   ``contracts/scope-ai-imports.md`` §1.3). B3 (``edit_version`` default) is not needed
   as a separate UPDATE — the column is added ``NOT NULL server_default='1'`` directly.
   All backfills are idempotent (``NOT EXISTS`` / ``IS NULL`` guards) and safe to
   re-run.

MySQL 8.4 notes (§6.4)
-----------------------
- ``batch_alter_table`` is used unconditionally for every attribution-column block: on
  SQLite (the default offline test lane) it is the only way to add an FK-bearing
  column; on MySQL it degrades to a plain ``ALTER TABLE``. Every new column here is
  nullable with no ``server_default`` (except ``edit_version``), so MySQL 8.0+ performs
  the ``ADD COLUMN`` in-place/instant — brief metadata lock, no table rewrite. Adding
  the FK constraints is the one part that requires a validating pass; on this dataset
  (~20 athletes, low hundreds of sessions) it is milliseconds, but it is still prod DDL
  on Hostinger — coordinate with `release-manager` for a low-traffic window before
  running against production, per repo policy.
- ``audit_log.occurred_at`` is declared
  ``sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")`` — a bare
  ``sa.DateTime()`` compiles to ``DATETIME`` with ``fsp=0`` on MySQL 8.4 and silently
  truncates the microseconds Python computes (the pre-existing defect in
  ``race_result_revisions.changed_at``); this table must not inherit that gap because
  two coaches can act inside the same second.
- ``changed_fields``, ``diff_json`` and ``meta_json`` (``audit_log``) are never
  indexed — MySQL cannot index a JSON column without a stored generated column, and no
  read path in this feature filters on JSON content.
- No app model is ever imported into this migration (established pattern, e.g.
  ``c4d5e6f7a8b9_seed_race_categories.py``).

Risks
-----
- Table-locking DDL on MySQL for the FK-constraint additions across 14 tables plus 2
  new tables — coordinate a low-traffic window on Hostinger prod (release-manager).
- Backfilled data (B1/B2/B4/B5/B6/B7) is **not** restored on ``downgrade()`` — same
  honest posture as ``8b5ac1f24f61``'s docstring. The schema shape is fully reversible;
  the historical attribution/coach rows it wrote are not recoverable after a downgrade.

Rollback plan: ``alembic downgrade -1`` reverses the schema in the exact inverse order
(drop columns/constraints, then drop the two new tables). Tested against the offline
SQLite lane (upgrade → downgrade → upgrade round trip) and pending verification against
a Hostinger-equivalent MySQL 8.4 ``_test`` database (no MySQL available on this
machine — see T014's blockers).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.sqlite import INTEGER as SQLITE_INTEGER


# revision identifiers, used by Alembic.
revision: str = "45cd705c6b54"
down_revision: Union[str, None] = "2a8baa967cc6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AUDIT_ACTION_VALUES = (
    "create",
    "update",
    "archive",
    "delete",
    "restore",
    "approve",
    "unapprove",
    "send",
    "export",
    "cancel",
    "execute",
    "link",
    "unlink",
    "role_change",
    "activate",
    "deactivate",
    "purge",
)
_AUDIT_ACTOR_KIND_VALUES = ("user", "system", "webhook", "cron")
# Same members/values as UserRole (app/models/user.py) — a separate DB enum
# (name="audit_actor_role") so a future change to users.role's own enum type
# cannot silently affect this snapshot column (data-model.md §1).
_AUDIT_ACTOR_ROLE_VALUES = ("admin", "coach", "parent", "athlete")


def upgrade() -> None:
    # =========================================================================
    # 1) audit_log — new table + five indexes (data-model.md §1-§1.1)
    # =========================================================================
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(SQLITE_INTEGER(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "actor_kind",
            sa.Enum(*_AUDIT_ACTOR_KIND_VALUES, name="audit_actor_kind"),
            nullable=False,
        ),
        sa.Column(
            "actor_role",
            sa.Enum(*_AUDIT_ACTOR_ROLE_VALUES, name="audit_actor_role"),
            nullable=True,
        ),
        sa.Column("club_id", sa.Integer(), nullable=True),
        sa.Column("athlete_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(*_AUDIT_ACTION_VALUES, name="audit_action"),
            nullable=False,
        ),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("diff_json", sa.JSON(), nullable=True),
        sa.Column("reason_code", sa.String(length=40), nullable=True),
        sa.Column("request_id", sa.String(length=32), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_log_actor_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["club_id"],
            ["clubs.id"],
            name="fk_audit_log_club_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athletes.id"],
            name="fk_audit_log_athlete_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_club_time", "audit_log", ["club_id", "occurred_at"], unique=False
    )
    op.create_index(
        "ix_audit_actor_time",
        "audit_log",
        ["actor_user_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_entity_time",
        "audit_log",
        ["entity_type", "entity_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_athlete_time",
        "audit_log",
        ["athlete_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_request_id", "audit_log", ["request_id"], unique=False
    )

    # =========================================================================
    # 2) training_session_coaches — bridge table (data-model.md §3)
    # =========================================================================
    op.create_table(
        "training_session_coaches",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("coach_user_id", sa.Integer(), nullable=False),
        sa.Column("added_by_user_id", sa.Integer(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["training_sessions.id"],
            name="fk_training_session_coaches_session_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["coach_user_id"],
            ["users.id"],
            name="fk_training_session_coaches_coach_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["users.id"],
            name="fk_training_session_coaches_added_by_user_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("session_id", "coach_user_id"),
    )
    op.create_index(
        "ix_tsc_coach_user_id",
        "training_session_coaches",
        ["coach_user_id"],
        unique=False,
    )

    # =========================================================================
    # 3) Attribution columns on 14 existing tables (data-model.md §4)
    # =========================================================================
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_users_updated_by_user_id",
            "users",
            ["updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("athletes") as batch_op:
        batch_op.add_column(
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("deleted_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("deleted_reason_code", sa.String(length=40), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_athletes_updated_by_user_id",
            "users",
            ["updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_athletes_deleted_by_user_id",
            "users",
            ["deleted_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("session_attendance") as batch_op:
        batch_op.add_column(
            sa.Column("recorded_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_session_attendance_recorded_by_user_id",
            "users",
            ["recorded_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_session_attendance_updated_by_user_id",
            "users",
            ["updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.add_column(
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("cancelled_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("cancelled_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "cancellation_reason_code", sa.String(length=40), nullable=True
            )
        )
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("deleted_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_calendar_events_updated_by_user_id",
            "users",
            ["updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_calendar_events_cancelled_by_user_id",
            "users",
            ["cancelled_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_calendar_events_deleted_by_user_id",
            "users",
            ["deleted_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("monthly_reports") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("approved_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("previous_approved_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("previous_approved_at", sa.DateTime(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_monthly_reports_updated_by_user_id",
            "users",
            ["updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_monthly_reports_approved_by_user_id",
            "users",
            ["approved_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_monthly_reports_previous_approved_by_user_id",
            "users",
            ["previous_approved_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("athlete_monthly_newsletters") as batch_op:
        batch_op.add_column(
            sa.Column("coach_note_author_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("coach_note_updated_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("last_edited_by_user_id", sa.Integer(), nullable=True)
        )
        # NOT NULL DEFAULT 1 directly on the ADD — INSTANT-eligible on MySQL
        # 8.0.12+ and avoids the separate B3 backfill (data-model.md §6.3).
        batch_op.add_column(
            sa.Column(
                "edit_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.create_foreign_key(
            "fk_athlete_monthly_newsletters_coach_note_author_id",
            "users",
            ["coach_note_author_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_athlete_monthly_newsletters_last_edited_by_user_id",
            "users",
            ["last_edited_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("athlete_ai_insights") as batch_op:
        batch_op.add_column(
            sa.Column("approved_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("archived_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("coach_answer_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_athlete_ai_insights_approved_by_user_id",
            "users",
            ["approved_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_athlete_ai_insights_archived_by_user_id",
            "users",
            ["archived_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_athlete_ai_insights_coach_answer_by_user_id",
            "users",
            ["coach_answer_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("session_media") as batch_op:
        batch_op.add_column(
            sa.Column("deleted_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_session_media_deleted_by_user_id",
            "users",
            ["deleted_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("anthropometric_records") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_anthropometric_records_updated_by_user_id",
            "users",
            ["updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("race_imports") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("committed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("committed_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_race_imports_committed_by_user_id",
            "users",
            ["committed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("race_series") as batch_op:
        batch_op.add_column(
            sa.Column("created_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_race_series_created_by_user_id",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("club_project_profiles") as batch_op:
        batch_op.add_column(
            sa.Column("created_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_club_project_profiles_created_by_user_id",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_club_project_profiles_updated_by_user_id",
            "users",
            ["updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("club_members") as batch_op:
        batch_op.add_column(
            sa.Column("added_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_club_members_added_by_user_id",
            "users",
            ["added_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(
            sa.Column("decided_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("decided_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_runs_decided_by_user_id",
            "users",
            ["decided_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # =========================================================================
    # 4) Read-path indexes every archive/soft-delete listing filters on (§6.2.4)
    # =========================================================================
    op.create_index(
        "ix_athletes_deleted_at", "athletes", ["deleted_at"], unique=False
    )
    op.create_index(
        "ix_calendar_events_deleted_at",
        "calendar_events",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_session_attendance_archived_at",
        "session_attendance",
        ["archived_at"],
        unique=False,
    )

    # =========================================================================
    # 5) Backfills (idempotent, dialect-aware where the SQL differs) — §6.3
    # =========================================================================
    bind = op.get_bind()
    dialect = bind.dialect.name  # "mysql" | "mariadb" | "sqlite"

    # B1 — session coaches = creator (spec.md:285). Standard SQL, both dialects.
    op.execute(
        sa.text(
            "INSERT INTO training_session_coaches "
            "    (session_id, coach_user_id, added_by_user_id, added_at) "
            "SELECT ts.id, ts.created_by_user_id, NULL, ts.created_at "
            "FROM training_sessions ts "
            "WHERE NOT EXISTS ("
            "    SELECT 1 FROM training_session_coaches c "
            "    WHERE c.session_id = ts.id"
            ")"
        )
    )

    # B2 — approved reports get an approval time; approved_by_user_id deliberately
    # stays NULL (copying generated_by_user_id would fabricate an attribution the
    # system never recorded — data-model.md §6.3).
    op.execute(
        sa.text(
            "UPDATE monthly_reports "
            "SET approved_at = generated_at "
            "WHERE status = 'approved' AND approved_at IS NULL"
        )
    )

    # B4 — users.updated_at.
    op.execute(
        sa.text("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")
    )

    # B5 — anthropometric_records.updated_at.
    op.execute(
        sa.text(
            "UPDATE anthropometric_records "
            "SET updated_at = created_at WHERE updated_at IS NULL"
        )
    )

    # B6 — race_imports timeline.
    op.execute(
        sa.text(
            "UPDATE race_imports SET updated_at = imported_at "
            "WHERE updated_at IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE race_imports SET committed_at = imported_at "
            "WHERE status = 'committed' AND committed_at IS NULL"
        )
    )

    # B7 (contracts/scope-ai-imports.md §1.3) — agent_runs.athlete_id from
    # input_json, for the two insert sites that historically did not set it.
    # FK is ON DELETE SET NULL, so guard against a dangling extracted id.
    if dialect == "sqlite":
        op.execute(
            sa.text(
                "UPDATE agent_runs "
                "SET athlete_id = CAST(json_extract(input_json, '$.athlete_id') AS INTEGER) "
                "WHERE athlete_id IS NULL "
                "AND json_extract(input_json, '$.athlete_id') IS NOT NULL "
                "AND EXISTS ("
                "    SELECT 1 FROM athletes a "
                "    WHERE a.id = CAST(json_extract(input_json, '$.athlete_id') AS INTEGER)"
                ")"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE agent_runs "
                "SET athlete_id = CAST("
                "    JSON_UNQUOTE(JSON_EXTRACT(input_json, '$.athlete_id')) AS UNSIGNED"
                ") "
                "WHERE athlete_id IS NULL "
                "AND JSON_EXTRACT(input_json, '$.athlete_id') IS NOT NULL "
                "AND EXISTS ("
                "    SELECT 1 FROM athletes a "
                "    WHERE a.id = CAST("
                "        JSON_UNQUOTE(JSON_EXTRACT(input_json, '$.athlete_id')) AS UNSIGNED"
                "    )"
                ")"
            )
        )


def downgrade() -> None:
    # Backfilled data is not restored (same honest posture as 8b5ac1f24f61's
    # docstring) — only the schema shape reverses. Exact inverse order of upgrade().
    op.drop_index("ix_session_attendance_archived_at", table_name="session_attendance")
    op.drop_index("ix_calendar_events_deleted_at", table_name="calendar_events")
    op.drop_index("ix_athletes_deleted_at", table_name="athletes")

    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_constraint(
            "fk_agent_runs_decided_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("decided_at")
        batch_op.drop_column("decided_by_user_id")

    with op.batch_alter_table("club_members") as batch_op:
        batch_op.drop_constraint(
            "fk_club_members_added_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("added_by_user_id")

    with op.batch_alter_table("club_project_profiles") as batch_op:
        batch_op.drop_constraint(
            "fk_club_project_profiles_updated_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_club_project_profiles_created_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("updated_by_user_id")
        batch_op.drop_column("created_by_user_id")

    with op.batch_alter_table("race_series") as batch_op:
        batch_op.drop_constraint(
            "fk_race_series_created_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("created_by_user_id")

    with op.batch_alter_table("race_imports") as batch_op:
        batch_op.drop_constraint(
            "fk_race_imports_committed_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("committed_by_user_id")
        batch_op.drop_column("committed_at")
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("anthropometric_records") as batch_op:
        batch_op.drop_constraint(
            "fk_anthropometric_records_updated_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("updated_by_user_id")
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("session_media") as batch_op:
        batch_op.drop_constraint(
            "fk_session_media_deleted_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("deleted_by_user_id")

    with op.batch_alter_table("athlete_ai_insights") as batch_op:
        batch_op.drop_constraint(
            "fk_athlete_ai_insights_coach_answer_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_athlete_ai_insights_archived_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_athlete_ai_insights_approved_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("coach_answer_by_user_id")
        batch_op.drop_column("archived_by_user_id")
        batch_op.drop_column("approved_by_user_id")

    with op.batch_alter_table("athlete_monthly_newsletters") as batch_op:
        batch_op.drop_constraint(
            "fk_athlete_monthly_newsletters_last_edited_by_user_id",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_athlete_monthly_newsletters_coach_note_author_id",
            type_="foreignkey",
        )
        batch_op.drop_column("edit_version")
        batch_op.drop_column("last_edited_by_user_id")
        batch_op.drop_column("coach_note_updated_at")
        batch_op.drop_column("coach_note_author_id")

    with op.batch_alter_table("monthly_reports") as batch_op:
        batch_op.drop_constraint(
            "fk_monthly_reports_previous_approved_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_monthly_reports_approved_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_monthly_reports_updated_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("previous_approved_at")
        batch_op.drop_column("previous_approved_by_user_id")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by_user_id")
        batch_op.drop_column("updated_by_user_id")
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.drop_constraint(
            "fk_calendar_events_deleted_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_calendar_events_cancelled_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_calendar_events_updated_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("deleted_by_user_id")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("cancellation_reason_code")
        batch_op.drop_column("cancelled_at")
        batch_op.drop_column("cancelled_by_user_id")
        batch_op.drop_column("updated_by_user_id")

    with op.batch_alter_table("session_attendance") as batch_op:
        batch_op.drop_constraint(
            "fk_session_attendance_updated_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_session_attendance_recorded_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("archived_at")
        batch_op.drop_column("updated_by_user_id")
        batch_op.drop_column("recorded_by_user_id")

    with op.batch_alter_table("athletes") as batch_op:
        batch_op.drop_constraint(
            "fk_athletes_deleted_by_user_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_athletes_updated_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("deleted_reason_code")
        batch_op.drop_column("deleted_by_user_id")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("updated_by_user_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(
            "fk_users_updated_by_user_id", type_="foreignkey"
        )
        batch_op.drop_column("updated_by_user_id")
        batch_op.drop_column("updated_at")

    # drop_table cascades index + FK drops for both new tables.
    op.drop_table("training_session_coaches")
    op.drop_table("audit_log")
