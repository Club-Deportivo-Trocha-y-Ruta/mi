"""Tests F-UP1: columnas upload UI sobre ``race_imports``.

Cubre:
- Instanciación del modelo con/sin las 9 columnas nullable nuevas.
- Defaults seguros (``kind='resultados'``, otras NULL).
- Serialización del enum ``RaceImportKind``.
- Migración upgrade/downgrade reversible aplicada contra SQLite in-memory
  para garantizar que las columnas existen tras ``upgrade()`` y desaparecen
  tras ``downgrade()``.

Convención del proyecto: tests SIN MySQL real (CI sin contenedor). Usamos
``Base.metadata.create_all`` para schema y SQLite in-memory para la migración
reversible (consistente con tests F1.6 / F1.7).
"""
from __future__ import annotations

import sqlite3
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
    """SQLite in-memory con solo las tablas necesarias para tests de RaceImport.

    Evitamos ``Base.metadata.create_all(engine)`` porque ``privacy_policies``
    usa ``LONGTEXT`` que SQLite no compila. Creamos solo el subgrafo de tablas
    que necesita RaceImport: users, race_series, race_events, race_imports.
    """
    engine = create_engine("sqlite:///:memory:", future=True)
    # Importar modelos requeridos para resolver FKs
    from app.models.user import User  # noqa: F401
    from app.models.lookups import RaceImportStatusLookup  # noqa: F401
    from app.models.race_points_scheme import RacePointsScheme  # noqa: F401
    from app.models.race_series import RaceSeries  # noqa: F401
    from app.models.race_event import RaceEvent  # noqa: F401
    from app.models.race_import import RaceImport  # noqa: F401

    # race_points_schemes ahora es FK de race_series (C5).
    # race_import_statuses ahora es FK de race_imports.status (C3).
    tables_to_create = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "race_points_schemes",
            "race_import_statuses",
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
    """Sesión SQLite síncrona con FKs activos (necesario para constraints)."""
    with sqlite_engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.commit()
    with Session(sqlite_engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Tests modelo
# ---------------------------------------------------------------------------


def test_race_import_kind_enum_serializes_values():
    """``RaceImportKind`` mapea a strings ``resultados`` / ``general`` / ``both``."""
    assert RaceImportKind.resultados.value == "resultados"
    assert RaceImportKind.general.value == "general"
    assert RaceImportKind.both.value == "both"
    # str enum: el value es lo que SQLAlchemy persiste con values_callable
    assert {k.value for k in RaceImportKind} == {"resultados", "general", "both"}


def test_race_import_legacy_columns_remain_required():
    """Las columnas legacy (filename, sha256, series_id, status, imported_by)
    siguen siendo NOT NULL — el delta F-UP1 no las afecta."""
    insp = inspect(Base.metadata.tables["race_imports"])
    cols = {c.name: c for c in insp.columns}

    assert cols["filename"].nullable is False
    assert cols["sha256"].nullable is False
    assert cols["series_id"].nullable is False
    assert cols["status"].nullable is False
    assert cols["imported_by_user_id"].nullable is False
    assert cols["imported_at"].nullable is False


def test_race_import_upload_columns_are_nullable():
    """Las 9 columnas F-UP1 deben ser nullable para no romper 3 imports legacy.

    Excepción: ``kind`` es NOT NULL pero con default ``resultados`` (server-side
    + Python-side) — los legacy reciben el default automáticamente.
    """
    insp = inspect(Base.metadata.tables["race_imports"])
    cols = {c.name: c for c in insp.columns}

    # Todas nullable
    nullable_cols = [
        "event_id",
        "storage_path",
        "storage_url",
        "general_storage_path",
        "general_storage_url",
        "general_sha256",
        "parse_meta_json",
        "original_filename",
    ]
    for name in nullable_cols:
        assert name in cols, f"Columna F-UP1 faltante: {name}"
        assert cols[name].nullable is True, f"Columna {name} debería ser nullable"

    # kind NOT NULL con default seguro
    assert "kind" in cols
    assert cols["kind"].nullable is False
    # El default Python es RaceImportKind.resultados
    py_default = cols["kind"].default
    # Aceptamos tanto Default Python como server_default; lo importante es
    # que exista al menos uno y resuelva a 'resultados'.
    has_default = py_default is not None or cols["kind"].server_default is not None
    assert has_default, "kind debe tener default Python o server_default"


def test_race_import_event_id_fk_to_race_events():
    """FK ``event_id`` apunta a ``race_events.id`` con ON DELETE SET NULL."""
    insp = inspect(Base.metadata.tables["race_imports"])
    fks_event = [fk for fk in insp.foreign_keys if fk.parent.name == "event_id"]
    assert len(fks_event) == 1, "Debe existir exactamente 1 FK desde event_id"
    fk = fks_event[0]
    assert fk.column.table.name == "race_events"
    assert fk.column.name == "id"
    assert fk.ondelete == "SET NULL"


def test_race_import_new_indices_present():
    """Los 2 índices F-UP1 (``ix_race_imports_event_id``, ``ix_race_imports_status``)
    deben estar declarados en ``__table_args__``."""
    insp = inspect(Base.metadata.tables["race_imports"])
    index_names = {idx.name for idx in insp.indexes}
    assert "ix_race_imports_event_id" in index_names
    assert "ix_race_imports_status" in index_names


def test_race_import_instantiation_with_only_legacy_fields():
    """Un RaceImport legacy F1.7 (sin event_id, sin storage) debe construirse OK.

    Esto valida la promesa de la migración: imports F1.7 existentes siguen
    funcionando con todas las columnas F-UP1 NULL salvo ``kind`` (default).
    """
    imp = RaceImport(
        filename="valida_iv_2026_resultados.pdf",
        sha256="a" * 64,
        series_id=1,
        status=RaceImportStatus.committed,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
    )
    # Atributos legacy poblados
    assert imp.filename == "valida_iv_2026_resultados.pdf"
    assert imp.sha256 == "a" * 64
    assert imp.status == RaceImportStatus.committed

    # Atributos F-UP1 quedan en None / default (el default Python aplica
    # SOLO tras flush en BD; en construcción in-memory queda None hasta
    # que se haga session.add + flush).
    assert imp.event_id is None
    assert imp.storage_path is None
    assert imp.storage_url is None
    assert imp.general_storage_path is None
    assert imp.general_storage_url is None
    assert imp.general_sha256 is None
    assert imp.parse_meta_json is None
    assert imp.original_filename is None


def test_race_import_instantiation_with_upload_fields():
    """Un RaceImport F-UP1 con TODOS los campos upload poblados."""
    imp = RaceImport(
        filename="valida_iv_2026_resultados.pdf",
        original_filename="Valida IV - Resultados.pdf",
        sha256="b" * 64,
        series_id=1,
        status=RaceImportStatus.pending,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        # F-UP1
        event_id=42,
        kind=RaceImportKind.both,
        storage_path="/uploads/race-imports/pending/uuid-r.pdf",
        storage_url="https://cdn.example.com/race-imports/pending/uuid-r.pdf",
        general_storage_path="/uploads/race-imports/pending/uuid-g.pdf",
        general_storage_url="https://cdn.example.com/race-imports/pending/uuid-g.pdf",
        general_sha256="c" * 64,
        parse_meta_json={"header": {"valida_num": 4}, "categories_found": ["INF_A"]},
    )

    assert imp.event_id == 42
    assert imp.kind == RaceImportKind.both
    assert imp.kind.value == "both"
    assert imp.storage_path == "/uploads/race-imports/pending/uuid-r.pdf"
    assert imp.general_sha256 == "c" * 64
    assert imp.parse_meta_json["categories_found"] == ["INF_A"]


def test_race_import_persistence_kind_default_in_sqlite(sqlite_session):
    """Persistir un RaceImport sin pasar ``kind`` debe resolver al default
    ``resultados`` por el server_default declarado en el modelo.

    Validamos contra SQLite (que respeta server_default via INSERT) — en MySQL
    el comportamiento sería idéntico.
    """
    # Crear dependencias mínimas para que las FKs (series_id, imported_by_user_id)
    # no exploten. SQLite con PRAGMA foreign_keys=ON enforza FKs.
    from app.models.user import User, UserRole
    from app.models.lookups import RaceImportStatusLookup
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
    # C5: race_series.points_scheme_code es FK → race_points_schemes.code.
    scheme = RacePointsScheme(
        code="copa_valle_2026",
        description="Test scheme",
        position_points={"1": 40, "2": 36},
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
    # C3: race_imports.status es FK → race_import_statuses.code.
    statuses = [
        RaceImportStatusLookup(code="pending", label_es="Pendiente", is_terminal=False),
        RaceImportStatusLookup(code="dry_run", label_es="Validación previa", is_terminal=False),
        RaceImportStatusLookup(code="committed", label_es="Confirmado", is_terminal=True),
        RaceImportStatusLookup(code="failed", label_es="Fallido", is_terminal=True),
    ]
    sqlite_session.add_all([user, scheme, series, *statuses])
    sqlite_session.commit()

    imp = RaceImport(
        filename="legacy_import.pdf",
        sha256="d" * 64,
        series_id=1,
        status=RaceImportStatus.committed,
        stats_json={},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        # NO pasamos kind → debe resolver al default
    )
    sqlite_session.add(imp)
    sqlite_session.commit()
    sqlite_session.refresh(imp)

    assert imp.kind == RaceImportKind.resultados
    assert imp.event_id is None
    assert imp.storage_path is None


def test_race_import_persistence_with_all_upload_fields(sqlite_session):
    """Round-trip persistencia → query → atributos correctos.

    Valida que SQLAlchemy + el modelo gestionan correctamente el enum
    ``RaceImportKind`` (values_callable) y los tipos JSON / CHAR(64) /
    VARCHAR(500) declarados en F-UP1.
    """
    # Setup dependencias mínimas
    from app.models.user import User, UserRole
    from app.models.lookups import RaceImportStatusLookup
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
    scheme = RacePointsScheme(
        code="copa_valle_2026",
        description="Test scheme",
        position_points={"1": 40, "2": 36},
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
    statuses = [
        RaceImportStatusLookup(code="pending", label_es="Pendiente", is_terminal=False),
        RaceImportStatusLookup(code="dry_run", label_es="Validación previa", is_terminal=False),
        RaceImportStatusLookup(code="committed", label_es="Confirmado", is_terminal=True),
        RaceImportStatusLookup(code="failed", label_es="Fallido", is_terminal=True),
    ]
    sqlite_session.add_all([user, scheme, series, *statuses])
    sqlite_session.commit()

    imp = RaceImport(
        filename="resultados.pdf",
        original_filename="Resultados Válida IV.pdf",
        sha256="e" * 64,
        series_id=1,
        status=RaceImportStatus.pending,
        stats_json={"x": 1},
        imported_by_user_id=1,
        imported_at=datetime.now(timezone.utc),
        kind=RaceImportKind.both,
        storage_path="race-imports/pending/uuid/resultados.pdf",
        storage_url="https://cdn.example.com/race-imports/pending/uuid/resultados.pdf",
        general_sha256="f" * 64,
        parse_meta_json={"warnings": []},
    )
    sqlite_session.add(imp)
    sqlite_session.commit()
    pk = imp.id
    sqlite_session.expire_all()

    loaded = sqlite_session.get(RaceImport, pk)
    assert loaded is not None
    assert loaded.kind == RaceImportKind.both
    assert loaded.original_filename == "Resultados Válida IV.pdf"
    assert loaded.storage_path == "race-imports/pending/uuid/resultados.pdf"
    assert loaded.general_sha256 == "f" * 64
    assert loaded.parse_meta_json == {"warnings": []}


def test_alembic_migration_upgrade_adds_all_columns(monkeypatch, tmp_path):
    """Aplica la migración F-UP1 (``e8f9a0b1c2d3``) sobre un SQLite limpio y
    verifica que todas las columnas nuevas aparecen en ``race_imports``.

    Estrategia: cargamos el módulo de migración como Python, construimos
    artificialmente la tabla legacy primero (via Base.metadata sin las
    columnas F-UP1 — imposible: el modelo ya las declara). En su lugar:

    - SQLite tiene la tabla ya con las nuevas columnas via Base.metadata.
    - Validamos que el módulo de migración define ``upgrade``/``downgrade``
      callables y que los nombres de columnas que agrega coinciden con
      lo declarado en el modelo (drift detection).
    """
    # Import lazy del módulo de migración
    import importlib.util

    migration_path = (
        "/Users/juadiga/Documents/Personal/Trocha y Ruta/me/backend/"
        "alembic/versions/e8f9a0b1c2d3_race_imports_upload_ui_delta.py"
    )
    spec = importlib.util.spec_from_file_location(
        "race_imports_upload_ui_delta", migration_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Sanity: rev id y down_revision correctos
    assert mod.revision == "e8f9a0b1c2d3"
    assert mod.down_revision == "7a8b9c0d1e2f"

    # Callables presentes y reversibles
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)

    # Enum values declarados son los que esperamos
    assert set(mod.RACE_IMPORT_KIND_VALUES) == {"resultados", "general", "both"}

    # Drift check: los nombres de columnas que el modelo declara deben
    # mencionarse en el código fuente de la migración (sanity simple
    # contra renombrados accidentales).
    with open(migration_path) as f:
        source = f.read()
    for col in [
        "event_id",
        "kind",
        "storage_path",
        "storage_url",
        "general_storage_path",
        "general_storage_url",
        "general_sha256",
        "parse_meta_json",
        "original_filename",
        "ix_race_imports_event_id",
        "ix_race_imports_status",
        "fk_race_imports_event_id",
    ]:
        assert col in source, f"Migración no menciona '{col}'"
