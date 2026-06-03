"""Tests capa de datos — refactor "Informe Técnico Mensual".

Cubre la migración ``d4e5f6a7b8c9`` y los modelos asociados:

- Nueva tabla ``club_project_profiles`` (1:1 con ``clubs``): UNIQUE en
  ``club_id``, FK ON DELETE RESTRICT, columnas JSON/Text/String nullable.
- ``monthly_reports`` +3 columnas: ``narrative_blocks`` (JSON),
  ``competition_results`` (JSON), ``status`` (Enum draft/approved, NOT NULL
  server_default 'draft').
- ``training_sessions`` +2 columnas: ``session_kind`` (Enum, NOT NULL
  server_default 'entrenamiento'), ``objectives`` (Text nullable).
- Enums Python ``SessionKind`` y ``MonthlyReportStatus`` con values_callable.
- Migración upgrade/downgrade reversible aplicada contra SQLite in-memory.

Convención del proyecto: tests SIN MySQL real. Schema vía
``Base.metadata.create_all`` y migración reversible sobre SQLite in-memory,
consistente con ``test_race_import_upload_columns.py`` (F-UP1).
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, time, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.models import Base
from app.models.club_project_profile import ClubProjectProfile
from app.models.training_session import (
    MonthlyReport,
    MonthlyReportStatus,
    SessionKind,
    TrainingSession,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "d4e5f6a7b8c9_informe_tecnico_mensual.py"
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_session_kind_enum_serializes_values():
    assert SessionKind.ENTRENAMIENTO.value == "entrenamiento"
    assert SessionKind.ACTIVIDAD_CONJUNTA.value == "actividad_conjunta"
    assert SessionKind.SALIDA.value == "salida"
    assert SessionKind.OTRO.value == "otro"


def test_monthly_report_status_enum_serializes_values():
    assert MonthlyReportStatus.DRAFT.value == "draft"
    assert MonthlyReportStatus.APPROVED.value == "approved"


# ---------------------------------------------------------------------------
# Fixtures SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine():
    """SQLite in-memory con solo el subgrafo de tablas necesario.

    Evitamos ``create_all(engine)`` completo (otras tablas usan LONGTEXT que
    SQLite no compila). Creamos users, clubs, athletes y las tablas tocadas
    por el refactor.
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    from app.models.user import User  # noqa: F401
    from app.models.club import Club  # noqa: F401
    from app.models.athlete import Athlete  # noqa: F401

    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "athletes",
            "club_project_profiles",
            "training_sessions",
            "session_attendance",
            "monthly_reports",
        )
    ]
    Base.metadata.create_all(engine, tables=tables)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Schema (create_all)
# ---------------------------------------------------------------------------


def test_club_project_profiles_schema(sqlite_engine):
    insp = inspect(sqlite_engine)
    cols = {c["name"] for c in insp.get_columns("club_project_profiles")}
    assert {
        "id",
        "club_id",
        "project_name",
        "executing_entity",
        "report_responsible",
        "purpose",
        "general_objective",
        "specific_objectives",
        "territory_location",
        "territory_description",
        "created_at",
        "updated_at",
    } <= cols

    uniques = insp.get_unique_constraints("club_project_profiles")
    assert any(u["column_names"] == ["club_id"] for u in uniques)

    fks = insp.get_foreign_keys("club_project_profiles")
    assert any(
        fk["referred_table"] == "clubs"
        and fk["constrained_columns"] == ["club_id"]
        and fk["options"].get("ondelete") == "RESTRICT"
        for fk in fks
    )


def test_monthly_reports_new_columns_present(sqlite_engine):
    cols = {c["name"] for c in inspect(sqlite_engine).get_columns("monthly_reports")}
    assert {"narrative_blocks", "competition_results", "status"} <= cols


def test_training_sessions_new_columns_present(sqlite_engine):
    cols = {
        c["name"]
        for c in inspect(sqlite_engine).get_columns("training_sessions")
    }
    assert {"session_kind", "objectives"} <= cols


# ---------------------------------------------------------------------------
# Defaults persistidos
# ---------------------------------------------------------------------------


def test_monthly_report_status_defaults_to_draft(sqlite_engine):
    # SQLite no fuerza FKs por defecto: insertamos sin filas padre para aislar
    # la validación del server_default de ``status``.
    with sqlite_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO monthly_reports "
                "(id, club_id, year, month, generated_by_user_id, generated_at) "
                "VALUES (1, 1, 2026, 6, 1, '2026-06-03')"
            )
        )
        conn.commit()
        row = conn.execute(
            text("SELECT status FROM monthly_reports WHERE id = 1")
        ).fetchone()
    assert row[0] == "draft"


def test_training_session_kind_defaults_to_entrenamiento(sqlite_engine):
    with sqlite_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO training_sessions "
                "(id, club_id, created_by_user_id, status, scheduled_date, "
                "scheduled_start_time, duration_min, location, technical_focus, "
                "created_at, updated_at) "
                "VALUES (1, 1, 1, 'planned', '2026-06-03', '08:00:00', 60, "
                "'Pista', 'Curvas', '2026-06-03', '2026-06-03')"
            )
        )
        conn.commit()
        row = conn.execute(
            text("SELECT session_kind FROM training_sessions WHERE id = 1")
        ).fetchone()
    assert row[0] == "entrenamiento"


# ---------------------------------------------------------------------------
# Modelos ORM
# ---------------------------------------------------------------------------


def test_club_project_profile_instantiation():
    profile = ClubProjectProfile(
        club_id=1,
        project_name="Escuela de ciclismo juvenil",
        executing_entity="Club Deportivo",
        report_responsible="Coordinacion tecnica",
        purpose="Formacion deportiva",
        general_objective="Desarrollar habilidades tecnicas",
        specific_objectives=["Obj 1", "Obj 2"],
        territory_location="Valle del Cauca",
        territory_description="Zona andina",
    )
    assert profile.specific_objectives == ["Obj 1", "Obj 2"]
    assert profile.project_name == "Escuela de ciclismo juvenil"


def test_monthly_report_narrative_blocks_default_none():
    report = MonthlyReport(
        club_id=1, year=2026, month=6, generated_by_user_id=1
    )
    assert report.narrative_blocks is None
    assert report.competition_results is None


def test_training_session_objectives_optional():
    session = TrainingSession(
        club_id=1,
        created_by_user_id=1,
        scheduled_date=datetime(2026, 6, 3).date(),
        scheduled_start_time=time(8, 0),
        duration_min=60,
        location="Pista",
        technical_focus="Curvas",
    )
    assert session.objectives is None


# ---------------------------------------------------------------------------
# Migración reversible (SQLite in-memory)
# ---------------------------------------------------------------------------


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_informe_tecnico_mensual", MIGRATION_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_metadata():
    mod = _load_migration()
    assert mod.revision == "d4e5f6a7b8c9"
    assert mod.down_revision == "c6d7e8f9a0b1"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert set(mod.SESSION_KIND_VALUES) == {
        "entrenamiento",
        "actividad_conjunta",
        "salida",
        "otro",
    }
    assert set(mod.MONTHLY_REPORT_STATUS_VALUES) == {"draft", "approved"}


def test_migration_upgrade_downgrade_reversible():
    """Aplica upgrade() y downgrade() reales sobre SQLite legacy."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _load_migration()
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        # Tablas legacy pre-refactor (sin las columnas nuevas).
        conn.execute(text("CREATE TABLE clubs (id INTEGER PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE monthly_reports (id INTEGER PRIMARY KEY, "
                "club_id INTEGER, year INTEGER, month INTEGER, ai_summary TEXT, "
                "metrics_snapshot JSON, generated_by_user_id INTEGER, "
                "generated_at DATETIME, coach_observations TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE training_sessions (id INTEGER PRIMARY KEY, "
                "club_id INTEGER, created_by_user_id INTEGER, status VARCHAR(20), "
                "scheduled_date DATE, scheduled_start_time TIME, duration_min INTEGER, "
                "location VARCHAR(200), technical_focus VARCHAR(200), description TEXT, "
                "route_text TEXT, strava_url VARCHAR(500), route_file_path VARCHAR(500), "
                "coach_notes TEXT, created_at DATETIME, updated_at DATETIME, "
                "executed_at DATETIME)"
            )
        )
        conn.commit()

        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
        conn.commit()

        insp = inspect(conn)
        assert "club_project_profiles" in insp.get_table_names()
        mr = {c["name"] for c in insp.get_columns("monthly_reports")}
        ts = {c["name"] for c in insp.get_columns("training_sessions")}
        assert {"narrative_blocks", "competition_results", "status"} <= mr
        assert {"session_kind", "objectives"} <= ts

        with Operations.context(ctx):
            mod.downgrade()
        conn.commit()

        insp = inspect(conn)
        assert "club_project_profiles" not in insp.get_table_names()
        mr = {c["name"] for c in insp.get_columns("monthly_reports")}
        ts = {c["name"] for c in insp.get_columns("training_sessions")}
        assert not ({"narrative_blocks", "competition_results", "status"} & mr)
        assert not ({"session_kind", "objectives"} & ts)
    engine.dispose()
