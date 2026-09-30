"""Migración ``448f7dfbca14`` — planilla IMDERTY (feature 047, T005/T006).

Dos carriles:

- **Por defecto (SQLite, sin marca).** Corre ``upgrade()``/``downgrade()`` del
  archivo sobre un SQLite síncrono con el esquema mínimo previo (``users``,
  ``athletes``, ``clubs``, ``parent_athlete``): cinco tablas + columna, semilla
  = ``len(BARRIOS_YUMBO)``, el truco de único-nulable (varios NULL, un valor
  duplicado rechazado) para ``active_key`` y ``primary_contact_key``, los
  CHECK, paridad migración ↔ modelos (``compare_metadata``) y un downgrade que
  no deja tabla ni columna.
- **``@pytest.mark.mysql``.** El mismo recorrido contra MySQL 8.4 real,
  caminando la cadena Alembic completa en una base hermana
  (``<nombre>_imderty_migrations_test``, creada y borrada aquí) para no pelear
  locks de metadatos con ``mysql_session``. Solo corre con
  ``TEST_DATABASE_URL`` (``mysql+aiomysql://…``, base terminada en ``_test``);
  sin servidor MySQL queda sin correr y debe reportarse así::

      TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
          python -m pytest -m mysql -q tests/imderty/test_migration_imderty.py

Datos ficticios: solo ids numéricos y correos ``@example.test``; ningún dato
de un menor real.
"""
from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError, OperationalError

from app.services.imderty.barrios_seed import BARRIOS_YUMBO

BACKEND_DIR = Path(__file__).resolve().parents[2]
REVISION = "448f7dfbca14"
DOWN_REVISION = "be4595de1ad2"
MIGRATION_PATH = (
    BACKEND_DIR / "alembic" / "versions" / f"{REVISION}_imderty_attendance_sheet.py"
)

NEW_TABLES = (
    "imderty_barrios",
    "athlete_imderty_profiles",
    "athlete_sensitive_authorizations",
    "athlete_sensitive_data",
    "club_imderty_settings",
)
NEW_COLUMN = ("parent_athlete", "primary_contact_key")


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_imderty", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Shared assertions (both dialects)
# ---------------------------------------------------------------------------


def _seed_minimal_rows(conn: Connection) -> None:
    """Two users, two athletes, one club, two guardian links — ids only."""
    conn.execute(
        text(
            "INSERT INTO users (id, email) VALUES "
            "(9001, 'acudiente.a@example.test'), (9002, 'acudiente.b@example.test')"
        )
    )
    conn.execute(text("INSERT INTO clubs (id, name) VALUES (9101, 'Club Ficticio')"))
    conn.execute(text("INSERT INTO athletes (id) VALUES (9201), (9202)"))
    conn.execute(
        text(
            "INSERT INTO parent_athlete (id, parent_id, athlete_id, relationship) "
            "VALUES (9301, 9001, 9201, 'mother'), (9302, 9002, 9201, 'father'), "
            "(9303, 9001, 9202, 'mother')"
        )
    )


def _assert_upgraded_schema(conn: Connection) -> None:
    insp = inspect(conn)
    tables = set(insp.get_table_names())
    assert set(NEW_TABLES) <= tables
    assert NEW_COLUMN[1] in {c["name"] for c in insp.get_columns(NEW_COLUMN[0])}
    assert (
        conn.execute(text("SELECT COUNT(*) FROM imderty_barrios")).scalar_one()
        == len(BARRIOS_YUMBO)
    )
    seeded = {
        (r[0], r[1])
        for r in conn.execute(text("SELECT name, zone FROM imderty_barrios"))
    }
    assert seeded == set(BARRIOS_YUMBO)
    assert conn.execute(
        text("SELECT COUNT(*) FROM imderty_barrios WHERE is_active = 1")
    ).scalar_one() == len(BARRIOS_YUMBO)


def _assert_nullable_unique_active_key(conn: Connection) -> None:
    insert = text(
        "INSERT INTO athlete_sensitive_authorizations "
        "(athlete_id, guardian_user_id, authorized_on, recorded_by_user_id, "
        " recorded_at, withdrawn_at, withdrawn_by_user_id, active_key, "
        " created_at, updated_at) VALUES "
        "(:athlete, 9001, '2026-09-01', 9002, '2026-09-01 10:00:00', "
        " :withdrawn, :withdrawn_by, :key, '2026-09-01 10:00:00', "
        " '2026-09-01 10:00:00')"
    )
    # Two withdrawn rows (NULL key) + one active per athlete: accepted.
    for params in (
        {"athlete": 9201, "withdrawn": "2026-09-02 10:00:00", "withdrawn_by": 9002, "key": None},
        {"athlete": 9201, "withdrawn": "2026-09-03 10:00:00", "withdrawn_by": 9002, "key": None},
        {"athlete": 9201, "withdrawn": None, "withdrawn_by": None, "key": 9201},
        {"athlete": 9202, "withdrawn": None, "withdrawn_by": None, "key": 9202},
    ):
        conn.execute(insert, params)
    # A second active authorization for the same athlete: rejected.
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                insert,
                {"athlete": 9201, "withdrawn": None, "withdrawn_by": None, "key": 9201},
            )


def _assert_nullable_unique_primary_contact(conn: Connection) -> None:
    # All links start NULL (several NULLs coexist); mark one primary each.
    assert conn.execute(
        text("SELECT COUNT(*) FROM parent_athlete WHERE primary_contact_key IS NULL")
    ).scalar_one() == 3
    conn.execute(
        text("UPDATE parent_athlete SET primary_contact_key = 9201 WHERE id = 9301")
    )
    conn.execute(
        text("UPDATE parent_athlete SET primary_contact_key = 9202 WHERE id = 9303")
    )
    # A second primary contact for athlete 9201: rejected.
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            conn.execute(
                text(
                    "UPDATE parent_athlete SET primary_contact_key = 9201 "
                    "WHERE id = 9302"
                )
            )


def _assert_checks(conn: Connection) -> None:
    # SQLite raises IntegrityError for a CHECK violation; MySQL 8.0+ raises
    # OperationalError (error 3819) for the same case — accept either.
    with pytest.raises((IntegrityError, OperationalError)):
        with conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO imderty_barrios "
                    "(name, zone, is_active, created_at, updated_at) VALUES "
                    "('BARRIO FICTICIO', 'ZONA ESTE', 1, "
                    "'2026-09-01 10:00:00', '2026-09-01 10:00:00')"
                )
            )
    barrio_id = conn.execute(text("SELECT MIN(id) FROM imderty_barrios")).scalar_one()
    with pytest.raises((IntegrityError, OperationalError)):
        with conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO athlete_imderty_profiles "
                    "(athlete_id, barrio_id, other_municipality, created_at, "
                    " updated_at) VALUES "
                    "(9201, :b, 1, '2026-09-01 10:00:00', '2026-09-01 10:00:00')"
                ),
                {"b": barrio_id},
            )
    # Either one alone is fine.
    conn.execute(
        text(
            "INSERT INTO athlete_imderty_profiles "
            "(athlete_id, barrio_id, other_municipality, created_at, updated_at) "
            "VALUES (9201, :b, 0, '2026-09-01 10:00:00', '2026-09-01 10:00:00'), "
            "(9202, NULL, 1, '2026-09-01 10:00:00', '2026-09-01 10:00:00')"
        ),
        {"b": barrio_id},
    )


def _assert_downgraded_schema(conn: Connection) -> None:
    insp = inspect(conn)
    tables = set(insp.get_table_names())
    assert not set(NEW_TABLES) & tables
    cols = {c["name"] for c in insp.get_columns(NEW_COLUMN[0])}
    assert NEW_COLUMN[1] not in cols
    uniques = {u["name"] for u in insp.get_unique_constraints("parent_athlete")}
    indexes = {i["name"] for i in insp.get_indexes("parent_athlete")}
    assert "uq_parent_athlete_primary_contact_key" not in uniques | indexes
    # Pre-existing guardian links survive the downgrade.
    assert conn.execute(text("SELECT COUNT(*) FROM parent_athlete")).scalar_one() == 3


# ---------------------------------------------------------------------------
# Default lane — SQLite, minimal pre-revision schema
# ---------------------------------------------------------------------------


_PRE_SCHEMA = (
    "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL)",
    "CREATE TABLE clubs (id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL)",
    "CREATE TABLE athletes (id INTEGER PRIMARY KEY)",
    "CREATE TABLE parent_athlete ("
    " id INTEGER PRIMARY KEY,"
    " parent_id INTEGER NOT NULL REFERENCES users (id),"
    " athlete_id INTEGER NOT NULL REFERENCES athletes (id),"
    " relationship VARCHAR(6) NOT NULL,"
    " CONSTRAINT uq_parent_athlete UNIQUE (parent_id, athlete_id))",
    "CREATE INDEX ix_parent_athlete_athlete_id ON parent_athlete (athlete_id)",
)


def _run(mod, conn: Connection, fn: str) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        getattr(mod, fn)()


@pytest.fixture
def sqlite_conn() -> Iterator[Connection]:
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        for ddl in _PRE_SCHEMA:
            conn.exec_driver_sql(ddl)
        yield conn
    engine.dispose()


def test_revision_parent_is_the_046_head() -> None:
    mod = _load_migration()
    assert mod.revision == REVISION
    assert mod.down_revision == DOWN_REVISION
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    rev = ScriptDirectory.from_config(cfg).get_revision(REVISION)
    assert rev is not None and rev.down_revision == DOWN_REVISION


def test_frozen_seed_matches_the_seed_module_today() -> None:
    """The migration copies the list literally; it must match at write time."""
    mod = _load_migration()
    assert tuple(mod.BARRIOS) == tuple(BARRIOS_YUMBO)
    assert {zone for _name, zone in BARRIOS_YUMBO} <= set(mod.ZONES)


def test_migration_enums_match_the_models() -> None:
    from app.models.imderty import (
        IMDERTY_ZONES,
        ImdertyDisability,
        ImdertyDocumentType,
        ImdertyEthnicity,
        ImdertyGrade,
        ImdertyYesNo,
    )

    mod = _load_migration()
    assert tuple(mod.ZONES) == IMDERTY_ZONES
    for values, enum_cls in (
        (mod.DOCUMENT_TYPES, ImdertyDocumentType),
        (mod.GRADES, ImdertyGrade),
        (mod.ETHNICITIES, ImdertyEthnicity),
        (mod.DISABILITIES, ImdertyDisability),
        (mod.YES_NO, ImdertyYesNo),
    ):
        assert tuple(values) == tuple(m.value for m in enum_cls)


def test_no_orientation_field_in_the_migration() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("orientation", "orientacion", "orientación", "sexual"):
        assert forbidden not in source


def test_sqlite_upgrade_constraints_downgrade_upgrade(sqlite_conn: Connection) -> None:
    mod = _load_migration()
    conn = sqlite_conn
    _seed_minimal_rows(conn)

    _run(mod, conn, "upgrade")
    _assert_upgraded_schema(conn)
    _assert_nullable_unique_active_key(conn)
    _assert_nullable_unique_primary_contact(conn)
    _assert_checks(conn)

    _run(mod, conn, "downgrade")
    _assert_downgraded_schema(conn)

    # Re-upgrade is clean (no leftover index/constraint names).
    _run(mod, conn, "upgrade")
    _assert_upgraded_schema(conn)


def test_sqlite_migration_matches_the_models(sqlite_conn: Connection) -> None:
    """``compare_metadata`` on the new objects must report no drift."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.models import Base

    _run(_load_migration(), sqlite_conn, "upgrade")

    def include_object(obj, name, type_, reflected, compare_to):
        table = obj if type_ == "table" else getattr(obj, "table", None)
        table_name = getattr(table, "name", None)
        if type_ == "table":
            return name in NEW_TABLES or name == "parent_athlete"
        if table_name in NEW_TABLES:
            return True
        if table_name == "parent_athlete":
            return name in (
                "primary_contact_key",
                "uq_parent_athlete_primary_contact_key",
            )
        return False

    ctx = MigrationContext.configure(
        sqlite_conn,
        opts={"include_object": include_object, "compare_type": True},
    )
    diff = compare_metadata(ctx, Base.metadata)
    assert diff == []


# ---------------------------------------------------------------------------
# mysql lane — full Alembic chain on a real MySQL 8.4
# ---------------------------------------------------------------------------


def _require_mysql_url() -> URL:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url.startswith("mysql+aiomysql://"):
        pytest.skip(
            "TEST_DATABASE_URL (mysql+aiomysql://) no configurada — "
            "saltando lane mysql"
        )
    db_name = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    if not db_name.endswith("_test"):
        pytest.fail(
            f"TEST_DATABASE_URL apunta a la base '{db_name}', que no termina "
            "en '_test'. Abortando para proteger datos de dev/prod."
        )
    return make_url(url).set(
        drivername="mysql+pymysql",
        database=f"{db_name.removesuffix('_test')}_imderty_migrations_test",
    )


def _alembic_config(sync_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["sqlalchemy.url"] = sync_url  # read by alembic/env.py
    return cfg


@pytest.fixture(scope="module")
def mysql_sync_url() -> Iterator[str]:
    url = _require_mysql_url()
    server = create_engine(url.set(database="information_schema"), future=True)
    with server.begin() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{url.database}`"))
        conn.execute(text(f"CREATE DATABASE `{url.database}`"))
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with server.begin() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS `{url.database}`"))
        server.dispose()


def _mysql_seed_minimal_rows(conn: Connection) -> None:
    """The real ``users``/``athletes``/``clubs`` have many NOT NULL columns, so
    rows are inserted with FK checks off and only the columns the assertions
    touch; ``parent_athlete.relationship`` uses a valid enum name."""
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    conn.execute(text("SET SESSION sql_mode = ''"))
    conn.execute(
        text(
            "INSERT INTO users (id, email) VALUES "
            "(9001, 'acudiente.a@example.test'), (9002, 'acudiente.b@example.test')"
        )
    )
    conn.execute(text("INSERT INTO clubs (id, name) VALUES (9101, 'Club Ficticio')"))
    # ``user_id`` is UNIQUE — with strict mode off, an omitted value implicitly
    # defaults to 0 for every row, so the second insert collides. Give each
    # athlete its own (fictitious, unused) user id instead.
    conn.execute(
        text(
            "INSERT INTO athletes (id, user_id) VALUES (9201, 9911), (9202, 9912)"
        )
    )
    relationship = conn.execute(
        text(
            "SELECT SUBSTRING_INDEX(SUBSTRING_INDEX(COLUMN_TYPE, '''', 2), '''', -1) "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'parent_athlete' AND COLUMN_NAME = 'relationship'"
        )
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO parent_athlete (id, parent_id, athlete_id, relationship) "
            "VALUES (9301, 9001, 9201, :r), (9302, 9002, 9201, :r), "
            "(9303, 9001, 9202, :r)"
        ),
        {"r": relationship},
    )
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


@pytest.mark.mysql
def test_mysql_upgrade_constraints_downgrade_upgrade(mysql_sync_url: str) -> None:
    cfg = _alembic_config(mysql_sync_url)
    engine = create_engine(mysql_sync_url, future=True)
    try:
        command.upgrade(cfg, DOWN_REVISION)
        with engine.begin() as conn:
            _mysql_seed_minimal_rows(conn)

        command.upgrade(cfg, REVISION)
        with engine.connect() as conn:
            with conn.begin():
                _assert_upgraded_schema(conn)
                # Native ENUM with the stored values, diacritics included.
                col_type = conn.execute(
                    text(
                        "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() "
                        "AND TABLE_NAME = 'athlete_sensitive_data' "
                        "AND COLUMN_NAME = 'ethnicity'"
                    )
                ).scalar_one()
                assert "'INDÍGENA'" in col_type
                assert "'NO SABE NO RESPONDE'" in col_type
                _assert_nullable_unique_active_key(conn)
                _assert_nullable_unique_primary_contact(conn)
                _assert_checks(conn)

        command.downgrade(cfg, DOWN_REVISION)
        with engine.begin() as conn:
            _assert_downgraded_schema(conn)

        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            _assert_upgraded_schema(conn)
            current = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == ScriptDirectory.from_config(cfg).get_current_head()
    finally:
        engine.dispose()
