"""Tests capa de datos — bitácora de etapa (feature 038, T102).

Cubre la migración ``6b998c214e5a`` y los modelos asociados:

- ``athlete_monthly_newsletters`` +7 columnas: ``content_version``
  (SMALLINT NOT NULL DEFAULT 1), ``stage_log_json`` / ``stage_overrides`` /
  ``hidden_blocks`` (JSON NULL), ``coach_note`` (VARCHAR(600) NULL),
  ``read_at`` (DATETIME NULL), ``read_by_user_id`` (FK users.id ON DELETE
  SET NULL).
- Nueva tabla ``newsletter_delivery_events``: FK a
  ``athlete_monthly_newsletters`` (ON DELETE CASCADE) y a ``users`` (ON
  DELETE SET NULL), enum ``event_type`` con ``values_callable``,
  ``provider_event_id`` UNIQUE NULL, índice compuesto
  ``(newsletter_id, event_type)``.
- Migración upgrade/downgrade reversible aplicada contra SQLite in-memory
  (``batch_alter_table`` para el ALTER con FK — SQLite no soporta
  ``ALTER TABLE ADD CONSTRAINT`` fuera de batch mode).

Convención del proyecto: tests SIN MySQL real. Schema vía
``Base.metadata.create_all`` y migración reversible sobre SQLite in-memory,
consistente con ``test_monthly_report_refactor_columns.py`` (d4e5f6a7b8c9).
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.models import Base
from app.models.newsletter_delivery_event import (
    DeliveryEventType,
    NewsletterDeliveryEvent,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "6b998c214e5a_newsletter_stage_log.py"
)


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


def test_delivery_event_type_enum_values():
    values = {e.value for e in DeliveryEventType}
    assert values == {"sent", "delivered", "opened", "clicked", "bounced", "web_read"}


def test_delivery_event_type_is_str_enum():
    assert isinstance(DeliveryEventType.sent, str)


# ---------------------------------------------------------------------------
# Fixtures SQLite (subgrafo de tablas)
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    from app.models.user import User  # noqa: F401
    from app.models.club import Club, ClubMember  # noqa: F401
    from app.models.athlete import Athlete  # noqa: F401
    from app.models.athlete_newsletter import AthleteMonthlyNewsletter  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "athlete_monthly_newsletters",
            "newsletter_delivery_events",
        )
    ]
    Base.metadata.create_all(engine, tables=tables)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Schema (create_all)
# ---------------------------------------------------------------------------


def test_athlete_monthly_newsletters_new_columns_present(sqlite_engine):
    cols = {
        c["name"]
        for c in inspect(sqlite_engine).get_columns("athlete_monthly_newsletters")
    }
    assert {
        "stage_log_json",
        "stage_overrides",
        "hidden_blocks",
        "coach_note",
        "read_at",
        "read_by_user_id",
    } <= cols
    # content_version (feature 038 v1/v2 switch) fue retirado por la
    # migración 8b5ac1f24f61 tras la eliminación del pipeline legacy.
    assert "content_version" not in cols


def test_athlete_monthly_newsletters_read_by_user_id_fk(sqlite_engine):
    fks = inspect(sqlite_engine).get_foreign_keys("athlete_monthly_newsletters")
    assert any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["read_by_user_id"]
        and fk["options"].get("ondelete") == "SET NULL"
        for fk in fks
    )


def test_newsletter_delivery_events_schema(sqlite_engine):
    insp = inspect(sqlite_engine)
    cols = {c["name"] for c in insp.get_columns("newsletter_delivery_events")}
    assert {
        "id",
        "newsletter_id",
        "parent_user_id",
        "event_type",
        "provider_message_id",
        "provider_event_id",
        "occurred_at",
        "created_at",
    } <= cols

    fks = insp.get_foreign_keys("newsletter_delivery_events")
    assert any(
        fk["referred_table"] == "athlete_monthly_newsletters"
        and fk["constrained_columns"] == ["newsletter_id"]
        and fk["options"].get("ondelete") == "CASCADE"
        for fk in fks
    )
    assert any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["parent_user_id"]
        and fk["options"].get("ondelete") == "SET NULL"
        for fk in fks
    )

    uniques = insp.get_unique_constraints("newsletter_delivery_events")
    assert any(u["column_names"] == ["provider_event_id"] for u in uniques)

    indexes = insp.get_indexes("newsletter_delivery_events")
    assert any(
        idx["column_names"] == ["newsletter_id", "event_type"] for idx in indexes
    )


# ---------------------------------------------------------------------------
# Modelo ORM
# ---------------------------------------------------------------------------


def test_newsletter_delivery_event_instantiation():
    now = datetime.now(timezone.utc)
    event = NewsletterDeliveryEvent(
        newsletter_id=1,
        parent_user_id=2,
        event_type=DeliveryEventType.sent,
        provider_message_id="resend-msg-abc",
        provider_event_id=None,
        occurred_at=now,
    )
    assert event.event_type == DeliveryEventType.sent
    assert event.provider_message_id == "resend-msg-abc"
    assert event.parent_user_id == 2


def test_newsletter_delivery_event_web_read_has_no_provider_ids():
    """web_read (lectura del padre) no viene de Resend — sin provider ids."""
    now = datetime.now(timezone.utc)
    event = NewsletterDeliveryEvent(
        newsletter_id=1,
        parent_user_id=2,
        event_type=DeliveryEventType.web_read,
        occurred_at=now,
    )
    assert event.provider_message_id is None
    assert event.provider_event_id is None


# ---------------------------------------------------------------------------
# Migración reversible (SQLite in-memory)
# ---------------------------------------------------------------------------


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_newsletter_stage_log", MIGRATION_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_metadata():
    mod = _load_migration()
    assert mod.revision == "6b998c214e5a"
    assert mod.down_revision == "f7a8b9c0d1e3"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert set(mod.DELIVERY_EVENT_TYPE_VALUES) == {
        "sent",
        "delivered",
        "opened",
        "clicked",
        "bounced",
        "web_read",
    }


def test_migration_upgrade_downgrade_reversible():
    """Aplica upgrade() y downgrade() reales sobre SQLite legacy.

    ``athlete_monthly_newsletters`` legacy (pre-038, solo columnas base) y
    ``users`` mínima. ``batch_alter_table`` (dentro de la migración) hace el
    ALTER + FK compatible con SQLite.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _load_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE athlete_monthly_newsletters (id INTEGER PRIMARY KEY, "
                "athlete_id INTEGER, year INTEGER, month INTEGER, status VARCHAR(20))"
            )
        )
        conn.commit()

        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
        conn.commit()

        insp = inspect(conn)
        assert "newsletter_delivery_events" in insp.get_table_names()
        nl_cols = {c["name"] for c in insp.get_columns("athlete_monthly_newsletters")}
        assert {
            "content_version",
            "stage_log_json",
            "stage_overrides",
            "hidden_blocks",
            "coach_note",
            "read_at",
            "read_by_user_id",
        } <= nl_cols

        with Operations.context(ctx):
            mod.downgrade()
        conn.commit()

        insp = inspect(conn)
        assert "newsletter_delivery_events" not in insp.get_table_names()
        nl_cols = {c["name"] for c in insp.get_columns("athlete_monthly_newsletters")}
        assert not (
            {
                "content_version",
                "stage_log_json",
                "stage_overrides",
                "hidden_blocks",
                "coach_note",
                "read_at",
                "read_by_user_id",
            }
            & nl_cols
        )
    engine.dispose()
