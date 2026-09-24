"""Migración ``a76c264449a5`` — el ``MODIFY COLUMN`` del ENUM de
``race_imports.status`` en MySQL real (feature 045, US3, T024).

Por qué MySQL real: en SQLite la columna es VARCHAR y la migración no hace
nada (``tests/models/test_race_import_discarded_migration.py``); lo que hay que
comprobar aquí es que el ``ALTER`` agrega ``discarded`` al final del ENUM
nativo y que el downgrade primero mapea ``discarded`` → ``failed`` y luego
quita el valor.

Se corre sobre una tabla de prueba aparte (``zz_race_imports_045_probe``, la
migración expone ``_TABLE``) para no tocar el ``race_imports`` que otros
módulos de la lane ``mysql`` comparten; se borra al terminar. Sin
``TEST_DATABASE_URL`` (mysql+aiomysql://…, base terminada en ``_test``) el
módulo se salta solo. Correr con::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        pytest -m mysql -q tests/mysql/test_race_import_discarded_migration_mysql.py
"""
from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.mysql

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "a76c264449a5_race_import_discarded.py"
)
_PROBE = "zz_race_imports_045_probe"
_OLD_DDL = "ENUM('pending','dry_run','committed','failed')"
_OLD_TYPE = _OLD_DDL.lower()  # cómo lo informa information_schema.COLUMNS
_NEW_TYPE = "enum('pending','dry_run','committed','failed','discarded')"


def _run(mod, conn: Connection, fn: str) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with Operations.context(MigrationContext.configure(conn)):
        getattr(mod, fn)()


def _column_type(conn: Connection) -> str:
    return conn.execute(
        text(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = 'status'"
        ),
        {"t": _PROBE},
    ).scalar_one()


@pytest.fixture
def conn() -> Iterator[Connection]:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url.startswith("mysql+aiomysql://"):
        pytest.skip("TEST_DATABASE_URL (mysql+aiomysql://) no configurada — saltando lane mysql")
    db_name = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    if not db_name.endswith("_test"):
        pytest.fail(
            f"TEST_DATABASE_URL apunta a la base '{db_name}', que no termina en '_test'. "
            "Abortando para proteger datos de dev/prod."
        )
    engine = create_engine(make_url(url).set(drivername="mysql+pymysql"), future=True)
    with engine.connect() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {_PROBE}"))
        connection.execute(
            text(
                f"CREATE TABLE {_PROBE} (id INT AUTO_INCREMENT PRIMARY KEY, "
                f"status {_OLD_DDL} NOT NULL)"
            )
        )
        try:
            yield connection
        finally:
            connection.execute(text(f"DROP TABLE IF EXISTS {_PROBE}"))
    engine.dispose()


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_race_import_discarded_mysql", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._TABLE = _PROBE  # apunta el ALTER a la tabla de prueba
    return mod


def test_upgrade_appends_discarded_and_keeps_existing_rows(conn: Connection) -> None:
    mod = _load_migration()
    conn.execute(text(f"INSERT INTO {_PROBE} (status) VALUES ('pending'), ('committed')"))
    assert _column_type(conn) == _OLD_TYPE

    _run(mod, conn, "upgrade")

    assert _column_type(conn) == _NEW_TYPE
    conn.execute(text(f"INSERT INTO {_PROBE} (status) VALUES ('discarded')"))
    statuses = [r[0] for r in conn.execute(text(f"SELECT status FROM {_PROBE} ORDER BY id"))]
    assert statuses == ["pending", "committed", "discarded"]


def test_downgrade_maps_discarded_to_failed_then_drops_the_value(conn: Connection) -> None:
    mod = _load_migration()
    _run(mod, conn, "upgrade")
    conn.execute(
        text(f"INSERT INTO {_PROBE} (status) VALUES ('pending'), ('discarded'), ('committed'), ('discarded')")
    )

    _run(mod, conn, "downgrade")

    assert _column_type(conn) == _OLD_TYPE
    statuses = [r[0] for r in conn.execute(text(f"SELECT status FROM {_PROBE} ORDER BY id"))]
    assert statuses == ["pending", "failed", "committed", "failed"]
