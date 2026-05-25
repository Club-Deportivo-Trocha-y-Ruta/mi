"""Tests F-UP-REV1: columnas de revisión sobre ``race_imports``.

Cubre el delta de la migración ``f9a0b1c2d3e4`` (down_revision = ``e8f9a0b1c2d3``):

- Instanciación del modelo con ``parent_import_id`` y ``revision_reason``.
- Property derivada ``is_revision`` (True ⇔ parent_import_id NO None).
- Self-referential FK persiste correctamente en SQLite y la relación ``parent``
  carga el padre cuando está set.
- Drift detection de la migración: el módulo debe declarar todas las columnas
  + el índice + la FK con los nombres canónicos.
- Round-trip serialización JSON-friendly (parent_import_id + revision_reason
  ambos quedan accesibles tras ``session.refresh``).
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models import Base
from app.models.race_import import (
    RaceImport,
    RaceImportKind,
    RaceImportStatus,
)


# ---------------------------------------------------------------------------
# Fixtures SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine():
    """SQLite in-memory con solo las tablas necesarias para RaceImport revision.

    Reusa la misma estrategia que ``test_race_import_upload_columns.py``:
    crear solo el subgrafo de tablas (users, race_series, race_events,
    race_imports) para evitar dependencias LONGTEXT incompatibles con SQLite.
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    from app.models.user import User  # noqa: F401
    from app.models.race_points_scheme import RacePointsScheme  # noqa: F401
    from app.models.race_series import RaceSeries  # noqa: F401
    from app.models.race_event import RaceEvent  # noqa: F401
    from app.models.race_import import RaceImport  # noqa: F401

    # race_points_schemes es ahora destino de FK desde race_series (C5).
    tables_to_create = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "race_points_schemes",
            "race_series",
            "race_events",
            "race_imports",
        )
    ]
    Base.metadata.create_all(engine, tables=tables_to_create)
    yield engine
    engine.dispose()


@pytest.fixture
def sqlite_session(sqlite_engine) -> Session:
    """Sesión SQLite síncrona con FKs activos."""
    with sqlite_engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.commit()
    with Session(sqlite_engine) as session:
        yield session


def _make_dependencies(session: Session) -> None:
    """Crea user + points scheme + series base requeridos por RaceImport FKs."""
    from app.models.user import User, UserRole
    from app.models.race_points_scheme import RacePointsScheme
    from app.models.race_series import RaceSeries

    user = User(
        id=1,
        email="test@test.com",
        hashed_password="x",
        first_name="Test",
        last_name="User",
        role=UserRole.admin,
        is_active=True,
        can_login=True,
        created_at=datetime.now(timezone.utc),
    )
    # C5: race_series.points_scheme_code es FK → race_points_schemes.code,
    # así que el scheme debe existir antes que la serie.
    scheme = RacePointsScheme(
        code="copa_valle_2026",
        description="Test scheme",
        position_points={"1": 40, "2": 36, "3": 33},
        attendance_points=10,
        dnf_points=0,
        dsq_points=0,
        dns_points=0,
        is_official=True,
    )
    series = RaceSeries(
        id=1,
        name="Test Series",
        season_year=2026,
        organizer="Test Org",
        points_scheme_code="copa_valle_2026",
    )
    session.add_all([user, scheme, series])
    session.commit()


# ---------------------------------------------------------------------------
# Tests modelo: schema delta
# ---------------------------------------------------------------------------


def test_race_import_revision_columns_declared_nullable():
    """``parent_import_id`` y ``revision_reason`` deben ser nullable.

    Razón: imports F-UP base (post-migración e8f9a0b1c2d3) quedan con ambos
    NULL — no son revisión. Sólo los imports que detectaron `(series, valida)`
    committed previo reciben parent_import_id.
    """
    insp = inspect(Base.metadata.tables["race_imports"])
    cols = {c.name: c for c in insp.columns}

    assert "parent_import_id" in cols, "Columna parent_import_id faltante"
    assert cols["parent_import_id"].nullable is True

    assert "revision_reason" in cols, "Columna revision_reason faltante"
    assert cols["revision_reason"].nullable is True
    # max_length=300 para evitar abuso (validación adicional en Pydantic).
    assert cols["revision_reason"].type.length == 300


def test_race_import_parent_fk_self_ref_set_null():
    """FK ``parent_import_id`` apunta a ``race_imports.id`` con ON DELETE SET NULL.

    Razón: si admin hard-deletea un import en sandbox (operación de emergencia
    documentada en runbook), las revisiones descendientes preservan su audit
    trail con parent_import_id=NULL en lugar de cascade-deletear.
    """
    insp = inspect(Base.metadata.tables["race_imports"])
    fks_parent = [
        fk for fk in insp.foreign_keys if fk.parent.name == "parent_import_id"
    ]
    assert len(fks_parent) == 1, (
        "Debe existir exactamente 1 FK desde parent_import_id"
    )
    fk = fks_parent[0]
    assert fk.column.table.name == "race_imports", "FK self-ref a race_imports"
    assert fk.column.name == "id"
    assert fk.ondelete == "SET NULL"


def test_race_import_parent_index_present():
    """Índice ``ix_race_imports_parent_id`` debe estar declarado.

    Necesario para queries de "listar revisiones descendientes" (futuro F2)
    sin full-table scan.
    """
    insp = inspect(Base.metadata.tables["race_imports"])
    index_names = {idx.name for idx in insp.indexes}
    assert "ix_race_imports_parent_id" in index_names


# ---------------------------------------------------------------------------
# Tests modelo: instanciación + property
# ---------------------------------------------------------------------------


def test_race_import_is_revision_property_false_for_default():
    """``is_revision`` = False cuando ``parent_import_id`` NO está set."""
    imp = RaceImport(
        filename="r.pdf",
        sha256="a" * 64,
        series_id=1,
        status=RaceImportStatus.pending,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
    )
    assert imp.parent_import_id is None
    assert imp.is_revision is False


def test_race_import_is_revision_property_true_when_parent_set():
    """``is_revision`` = True cuando ``parent_import_id`` está set."""
    imp = RaceImport(
        filename="r.pdf",
        sha256="b" * 64,
        series_id=1,
        status=RaceImportStatus.pending,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        parent_import_id=42,
        revision_reason="Federación corrigió posiciones tras reclamo oficial",
    )
    assert imp.parent_import_id == 42
    assert imp.revision_reason == "Federación corrigió posiciones tras reclamo oficial"
    assert imp.is_revision is True


def test_race_import_revision_reason_max_length_via_string_type():
    """``revision_reason`` es VARCHAR(300) — capacidad declarada en columna.

    No es responsabilidad del modelo enforzar max_length (eso lo hace Pydantic).
    Esta prueba solo confirma que la columna soporta hasta 300 chars.
    """
    text_300 = "x" * 300
    imp = RaceImport(
        filename="r.pdf",
        sha256="c" * 64,
        series_id=1,
        status=RaceImportStatus.pending,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        parent_import_id=10,
        revision_reason=text_300,
    )
    assert len(imp.revision_reason) == 300


# ---------------------------------------------------------------------------
# Tests persistencia + relación self-ref
# ---------------------------------------------------------------------------


def test_race_import_persistence_with_parent_and_reason(sqlite_session):
    """Round-trip: persistir un parent + revisión hija → relación parent navega
    correctamente al padre y is_revision retorna True."""
    _make_dependencies(sqlite_session)

    # Crear parent (committed previo)
    parent_imp = RaceImport(
        filename="resultados_v1.pdf",
        sha256="p" * 64,
        series_id=1,
        status=RaceImportStatus.committed,
        stats_json={"results_inserted": 200},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        kind=RaceImportKind.resultados,
    )
    sqlite_session.add(parent_imp)
    sqlite_session.commit()
    parent_id = parent_imp.id

    # Crear revisión hija con parent_import_id apuntando al previo
    child_imp = RaceImport(
        filename="resultados_v2.pdf",
        sha256="r" * 64,
        series_id=1,
        status=RaceImportStatus.committed,
        stats_json={"results_inserted": 198, "deletes": 2},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        kind=RaceImportKind.resultados,
        parent_import_id=parent_id,
        revision_reason="Corrección federación tras reclamo posiciones",
    )
    sqlite_session.add(child_imp)
    sqlite_session.commit()
    child_id = child_imp.id

    sqlite_session.expire_all()

    # Cargar revisión y verificar que parent se resuelve via relación
    loaded_child = sqlite_session.get(RaceImport, child_id)
    assert loaded_child is not None
    assert loaded_child.is_revision is True
    assert loaded_child.parent_import_id == parent_id
    assert loaded_child.revision_reason == "Corrección federación tras reclamo posiciones"

    # La relación parent carga al padre correctamente
    assert loaded_child.parent is not None
    assert loaded_child.parent.id == parent_id
    assert loaded_child.parent.is_revision is False
    assert loaded_child.parent.sha256 == "p" * 64


def test_race_import_persistence_first_import_has_no_parent(sqlite_session):
    """Un import "primero" (no revisión) persiste con parent_import_id=NULL."""
    _make_dependencies(sqlite_session)

    imp = RaceImport(
        filename="first.pdf",
        sha256="f" * 64,
        series_id=1,
        status=RaceImportStatus.committed,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        kind=RaceImportKind.resultados,
        # No pasamos parent_import_id ni revision_reason
    )
    sqlite_session.add(imp)
    sqlite_session.commit()

    sqlite_session.expire_all()
    loaded = sqlite_session.get(RaceImport, imp.id)
    assert loaded.parent_import_id is None
    assert loaded.revision_reason is None
    assert loaded.is_revision is False
    assert loaded.parent is None


def test_race_import_serializable_json_friendly(sqlite_session):
    """Schema friendly: campos parent_import_id + revision_reason son tipos JSON-serializables
    (int y str). Verifica que un round-trip preserva los tipos para uso en Pydantic v2.
    """
    import json

    _make_dependencies(sqlite_session)

    parent_imp = RaceImport(
        filename="p.pdf",
        sha256="p" * 64,
        series_id=1,
        status=RaceImportStatus.committed,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
    )
    sqlite_session.add(parent_imp)
    sqlite_session.commit()

    child_imp = RaceImport(
        filename="c.pdf",
        sha256="c" * 64,
        series_id=1,
        status=RaceImportStatus.committed,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        parent_import_id=parent_imp.id,
        revision_reason="Test reason JSON-serializable",
    )
    sqlite_session.add(child_imp)
    sqlite_session.commit()

    # Verificar serialización a dict pseudo-JSON (lo que haría model_dump en Pydantic v2)
    payload = {
        "id": child_imp.id,
        "parent_import_id": child_imp.parent_import_id,
        "revision_reason": child_imp.revision_reason,
        "is_revision": child_imp.is_revision,
    }
    serialized = json.dumps(payload)
    rehydrated = json.loads(serialized)
    assert rehydrated["parent_import_id"] == parent_imp.id
    assert rehydrated["revision_reason"] == "Test reason JSON-serializable"
    assert rehydrated["is_revision"] is True


# ---------------------------------------------------------------------------
# Tests migración Alembic
# ---------------------------------------------------------------------------


def test_alembic_revision_migration_has_correct_lineage():
    """Migración ``f9a0b1c2d3e4`` debe declarar down_revision=e8f9a0b1c2d3.

    Garantiza que la cadena F-UP base → F-UP-REV1 es lineal y reversible.
    """
    migration_path = (
        "/Users/juadiga/Documents/Personal/Trocha y Ruta/me/backend/"
        "alembic/versions/f9a0b1c2d3e4_race_imports_revision_delta.py"
    )
    spec = importlib.util.spec_from_file_location(
        "race_imports_revision_delta", migration_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "f9a0b1c2d3e4"
    assert mod.down_revision == "e8f9a0b1c2d3"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_alembic_revision_migration_mentions_all_changes():
    """Drift detection: el source de la migración debe mencionar todos los
    nombres canónicos (columnas, índice, FK)."""
    migration_path = (
        "/Users/juadiga/Documents/Personal/Trocha y Ruta/me/backend/"
        "alembic/versions/f9a0b1c2d3e4_race_imports_revision_delta.py"
    )
    with open(migration_path) as f:
        source = f.read()

    for needle in [
        "parent_import_id",
        "revision_reason",
        "ix_race_imports_parent_id",
        "fk_race_imports_parent_id",
        "SET NULL",
        "race_imports",
    ]:
        assert needle in source, f"Migración no menciona '{needle}'"
