"""Migration ``be4595de1ad2`` — ``skinfold_measurements`` + FUPRECOL enum
values on ``growth_reference_lms`` (feature 046, T012).

Why real MySQL: on SQLite both ``growth_reference_lms`` enum columns are
VARCHAR without CHECK, so the part of the migration that can break a deploy
(``MODIFY COLUMN ... ENUM(...)`` up and down, with FUPRECOL rows present) only
runs on MySQL. The walk is::

    upgrade head -> seed FUPRECOL (vendored CSV) -> 3 indicators x 2 sexes x
    9 bands = 54 rows, enum values present -> downgrade one revision -> FUPRECOL
    rows gone, enums shrunk, table dropped, non-FUPRECOL rows untouched ->
    upgrade head again

**Deferred lane.** Marked ``@pytest.mark.mysql``: it only runs with
``TEST_DATABASE_URL`` (``mysql+aiomysql://…``, database name ending in
``_test``) and is skipped otherwise — sessions without a MySQL server leave it
unrun and must say so. Like ``tests/test_audit_mysql.py`` it walks the Alembic
chain in a sibling database (``<name>_skinfolds_migrations_test``, created and
dropped here) so it never fights the session-scoped ``mysql_session`` for
metadata locks; the MySQL user needs ``CREATE``/``DROP`` database privileges.
Fixtures are population reference constants only (no athlete, no minor data).
Run with::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        python -m pytest -m mysql -q tests/test_migration_skinfolds.py
"""
from __future__ import annotations

import csv
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import URL, make_url

pytestmark = pytest.mark.mysql

BACKEND_DIR = Path(__file__).resolve().parents[1]
DOWN_REVISION = "a76c264449a5"
FUPRECOL_CSV = BACKEND_DIR / "app" / "data" / "fuprecol_lms" / "fuprecol_skinfolds.csv"

SKINFOLD_INDICATORS = {
    "triceps_skinfold_for_age",
    "subscapular_skinfold_for_age",
    "triceps_subscapular_sum_for_age",
}
BAND_MIDPOINTS = {114, 126, 138, 150, 162, 174, 186, 198, 210}
EXPECTED_ROWS = len(SKINFOLD_INDICATORS) * 2 * len(BAND_MIDPOINTS)  # 54

SOURCE_TYPE_NEW = "enum('who','cdc','fuprecol')"
SOURCE_TYPE_OLD = "enum('who','cdc')"
INDICATOR_TYPE_NEW = (
    "enum('height_for_age','weight_for_age','bmi_for_age',"
    "'triceps_skinfold_for_age','subscapular_skinfold_for_age',"
    "'triceps_subscapular_sum_for_age')"
)
INDICATOR_TYPE_OLD = "enum('height_for_age','weight_for_age','bmi_for_age')"

_UPSERT = text(
    """
    INSERT INTO growth_reference_lms (source, indicator, sex, age_months, L, M, S)
    VALUES ('FUPRECOL', :indicator, :sex, :age_months, :L, :M, :S)
    ON DUPLICATE KEY UPDATE L = VALUES(L), M = VALUES(M), S = VALUES(S)
    """
)


def _require_test_url() -> URL:
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
        database=f"{db_name.removesuffix('_test')}_skinfolds_migrations_test",
    )


def _alembic_config(sync_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["sqlalchemy.url"] = sync_url  # read by alembic/env.py
    return cfg


@pytest.fixture(scope="module")
def sync_url() -> Iterator[str]:
    url = _require_test_url()
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


def _fuprecol_rows() -> list[dict[str, object]]:
    """Generic ``indicator,sex,age_months,L,M,S`` parse of the vendored CSV —
    the same shape the FUPRECOL entry of ``app/seed_growth_data.py`` loads."""
    with FUPRECOL_CSV.open(newline="", encoding="utf-8") as fh:
        return [
            {
                "indicator": row["indicator"].strip(),
                "sex": row["sex"].strip(),
                "age_months": float(row["age_months"]),
                "L": float(row["L"]),
                "M": float(row["M"]),
                "S": float(row["S"]),
            }
            for row in csv.DictReader(fh)
        ]


def _seed_fuprecol(conn: Connection) -> None:
    conn.execute(_UPSERT, _fuprecol_rows())


def _column_type(conn: Connection, table: str, column: str) -> str:
    return conn.execute(
        text(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    ).scalar_one().lower()


def _has_table(conn: Connection, table: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
            ),
            {"t": table},
        ).scalar_one()
    )


def _fuprecol_count(conn: Connection) -> int:
    return conn.execute(
        text("SELECT COUNT(*) FROM growth_reference_lms WHERE source = 'FUPRECOL'")
    ).scalar_one()


def test_migration_parent_is_the_045_head() -> None:
    """Runs in the mysql lane with the rest; guards the chain wiring."""
    cfg = _alembic_config("sqlite://")
    rev = ScriptDirectory.from_config(cfg).get_revision("be4595de1ad2")
    assert rev is not None and rev.down_revision == DOWN_REVISION


def test_upgrade_seed_downgrade_upgrade_roundtrip(sync_url: str) -> None:
    cfg = _alembic_config(sync_url)
    engine = create_engine(sync_url, future=True)
    try:
        # --- upgrade head --------------------------------------------------
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            assert _has_table(conn, "skinfold_measurements")
            assert _column_type(conn, "growth_reference_lms", "source") == SOURCE_TYPE_NEW
            assert (
                _column_type(conn, "growth_reference_lms", "indicator")
                == INDICATOR_TYPE_NEW
            )
            unique_cols = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT COLUMN_NAME FROM information_schema.STATISTICS "
                        "WHERE TABLE_SCHEMA = DATABASE() "
                        "AND TABLE_NAME = 'skinfold_measurements' "
                        "AND INDEX_NAME = 'uq_skinfold_measurements_record' "
                        "AND NON_UNIQUE = 0"
                    )
                )
            }
            assert unique_cols == {"anthropometric_record_id"}

            # A synthetic non-FUPRECOL row that the downgrade must keep.
            conn.execute(
                text(
                    "INSERT INTO growth_reference_lms "
                    "(source, indicator, sex, age_months, L, M, S) "
                    "VALUES ('WHO', 'bmi_for_age', 'F', 120.0, -1.0, 16.5, 0.12)"
                )
            )

        # --- seed FUPRECOL (twice: the upsert must be idempotent) ----------
        with engine.begin() as conn:
            _seed_fuprecol(conn)
            _seed_fuprecol(conn)
        with engine.begin() as conn:
            assert _fuprecol_count(conn) == EXPECTED_ROWS
            combos = {
                (r[0], r[1], int(r[2]))
                for r in conn.execute(
                    text(
                        "SELECT indicator, sex, age_months FROM growth_reference_lms "
                        "WHERE source = 'FUPRECOL'"
                    )
                )
            }
            assert combos == {
                (ind, sex, band)
                for ind in SKINFOLD_INDICATORS
                for sex in ("M", "F")
                for band in BAND_MIDPOINTS
            }

        # --- downgrade one revision ----------------------------------------
        command.downgrade(cfg, DOWN_REVISION)
        with engine.begin() as conn:
            assert not _has_table(conn, "skinfold_measurements")
            assert _fuprecol_count(conn) == 0
            assert _column_type(conn, "growth_reference_lms", "source") == SOURCE_TYPE_OLD
            assert (
                _column_type(conn, "growth_reference_lms", "indicator")
                == INDICATOR_TYPE_OLD
            )
            assert (
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM growth_reference_lms "
                        "WHERE source = 'WHO' AND indicator = 'bmi_for_age'"
                    )
                ).scalar_one()
                == 1
            )

        # --- upgrade again -------------------------------------------------
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            assert _has_table(conn, "skinfold_measurements")
            assert _column_type(conn, "growth_reference_lms", "source") == SOURCE_TYPE_NEW
            current = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert current == ScriptDirectory.from_config(cfg).get_current_head()
    finally:
        engine.dispose()
