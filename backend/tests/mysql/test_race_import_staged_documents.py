"""Migración ``c9d0e1f2a3b4`` — ``race_import_staged_documents`` (amendment
2026-09-26, T111, data-model.md §11.1).

Comprueba, contra MySQL 8.4 real:

- la tabla exactamente como en data-model.md §11.1: ``import_id INT PK, FK
  → race_imports.id ON DELETE CASCADE``, ``schema_version SMALLINT NOT
  NULL``, ``profile_id VARCHAR(64) NOT NULL``, ``profile_sha256 CHAR(64)
  NOT NULL``, ``engine_version VARCHAR(16) NOT NULL``, ``document_json JSON
  NOT NULL``, ``created_at DATETIME NOT NULL``;
- que borrar el import se lleva su documento (``ON DELETE CASCADE``);
- un round-trip JSON de un documento sintético de 300 filas;
- ``upgrade`` → ``downgrade`` → ``upgrade``, limpio.

Camina la cadena de Alembic en su propia base hermana
(``<name>_migrations_test``), igual que ``tests/test_audit_mysql.py`` —
nunca en la base de ``TEST_DATABASE_URL`` que comparte ``mysql_session``.
Sin ``TEST_DATABASE_URL`` (mysql+aiomysql://…, base terminada en
``_test``) el módulo entero se salta solo. Correr con::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        pytest -m mysql -q tests/mysql/test_race_import_staged_documents.py

Privacidad: el documento de 300 filas es enteramente sintético
(``tests.helpers.results_pdf_builder.FakeNameGenerator``) — ninguna fila
proviene de un acta real.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.services.race.staged_document import document_to_json
from tests.helpers.results_pdf_builder import FakeNameGenerator
from tests.services.race.test_staged_document import _sample_document as _small_document

pytestmark = pytest.mark.mysql

BACKEND_DIR = Path(__file__).resolve().parents[2]
REVISION = "c9d0e1f2a3b4"
DOWN_REVISION = "be4595de1ad2"


def _require_test_url() -> URL:
    """Igual a ``tests/conftest.py::mysql_engine``: salta sin
    ``TEST_DATABASE_URL``; falla duro si la base no termina en ``_test``."""
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url or not url.startswith("mysql+aiomysql://"):
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
        database=f"{db_name.removesuffix('_test')}_migrations_test",
    )


def _alembic_config(sync_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["sqlalchemy.url"] = sync_url
    return cfg


@pytest.fixture(scope="module")
def sync_url() -> Iterator[str]:
    url = _require_test_url()
    server = create_engine(url.set(database="information_schema"), future=True)
    with server.begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{url.database}`"))
    yield url.render_as_string(hide_password=False)
    with server.begin() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{url.database}`"))
    server.dispose()


@pytest.fixture
def clean_schema(sync_url: str) -> str:
    """Vacía la base y sube hasta ``DOWN_REVISION`` (el head previo a esta
    migración) — punto de partida conocido para cada test."""
    engine = create_engine(sync_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        tables = [row[0] for row in conn.execute(text("SHOW TABLES")).fetchall()]
        for tbl in tables:
            conn.execute(text(f"DROP TABLE IF EXISTS `{tbl}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    engine.dispose()

    command.upgrade(_alembic_config(sync_url), DOWN_REVISION)
    return sync_url


def _seed_minimal_import(engine) -> int:
    """Un coach + una serie + un import ``pending`` — lo mínimo que exige
    la FK de ``race_import_staged_documents``."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users "
                "(id, email, first_name, last_name, role, is_active, can_login, "
                "created_at) "
                "VALUES (8001, 'coach8001@example.test', 'Entrenador', 'Prueba', "
                "'coach', 1, 1, NOW())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO race_series "
                "(id, name, season_year, points_scheme_code, kind, level, "
                "created_at, updated_at) "
                "VALUES (8001, 'Serie Prueba T111', 2026, 'uci_xco', 'cup', "
                "'departmental', NOW(), NOW())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO race_imports "
                "(id, filename, sha256, series_id, status, stats_json, "
                "imported_by_user_id, imported_at, kind) "
                "VALUES (8001, 'acta.pdf', :sha, 8001, 'pending', '{}', 8001, "
                "NOW(), 'resultados')"
            ),
            {"sha": "c" * 64},
        )
    return 8001


def test_table_matches_data_model(clean_schema: str) -> None:
    command.upgrade(_alembic_config(clean_schema), REVISION)

    engine = create_engine(clean_schema, future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_KEY "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'race_import_staged_documents'"
            )
        ).fetchall()
    engine.dispose()

    columns = {row[0]: (row[1].lower(), row[2], row[3]) for row in rows}
    assert columns == {
        "import_id": ("int", "NO", "PRI"),
        "schema_version": ("smallint", "NO", ""),
        "profile_id": ("varchar(64)", "NO", ""),
        "profile_sha256": ("char(64)", "NO", ""),
        "engine_version": ("varchar(16)", "NO", ""),
        "document_json": ("json", "NO", ""),
        "created_at": ("datetime", "NO", ""),
    }


def test_no_index_beyond_the_primary_key(clean_schema: str) -> None:
    command.upgrade(_alembic_config(clean_schema), REVISION)

    engine = create_engine(clean_schema, future=True)
    with engine.begin() as conn:
        rows = conn.execute(
            text("SHOW INDEX FROM race_import_staged_documents")
        ).fetchall()
    engine.dispose()

    key_names = {row[2] for row in rows}  # Key_name
    assert key_names == {"PRIMARY"}, (
        f"race_import_staged_documents no debe tener índice más allá de la "
        f"PK; encontrado: {sorted(key_names)}"
    )


def test_delete_import_cascades_to_staged_document(clean_schema: str) -> None:
    command.upgrade(_alembic_config(clean_schema), REVISION)

    engine = create_engine(clean_schema, future=True)
    import_id = _seed_minimal_import(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO race_import_staged_documents "
                "(import_id, schema_version, profile_id, profile_sha256, "
                "engine_version, document_json, created_at) "
                "VALUES (:id, 1, 'copa-valle-results-pdf', :sha, "
                "'results_skill@0.1.0', '{}', NOW())"
            ),
            {"id": import_id, "sha": "d" * 64},
        )

    with engine.begin() as conn:
        count_before = conn.execute(
            text(
                "SELECT COUNT(*) FROM race_import_staged_documents "
                "WHERE import_id = :id"
            ),
            {"id": import_id},
        ).scalar()
    assert count_before == 1

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM race_imports WHERE id = :id"), {"id": import_id})

    with engine.begin() as conn:
        count_after = conn.execute(
            text(
                "SELECT COUNT(*) FROM race_import_staged_documents "
                "WHERE import_id = :id"
            ),
            {"id": import_id},
        ).scalar()
    engine.dispose()
    assert count_after == 0, "ON DELETE CASCADE debió borrar el documento con el import"


def test_document_json_round_trips_300_rows(clean_schema: str) -> None:
    command.upgrade(_alembic_config(clean_schema), REVISION)

    engine = create_engine(clean_schema, future=True)
    import_id = _seed_minimal_import(engine)

    gen = FakeNameGenerator()
    document = _small_document(gen)
    # Ensancha a 300 filas sintéticas repitiendo el patrón de la primera
    # categoría con posiciones/dorsales distintos — el punto de este test es
    # el tamaño del payload JSON, no la variedad de casos (ya cubierta por
    # ``tests/services/race/test_staged_document.py``).
    base_row = document.categories[0].rows[0]
    from dataclasses import replace

    document.categories[0].rows = [
        replace(base_row, position=i, bib=str(100 + i), points=max(1, 300 - i))
        for i in range(1, 301)
    ]
    payload = document_to_json(document)
    assert sum(len(c["rows"]) for c in payload["categories"]) >= 300

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO race_import_staged_documents "
                "(import_id, schema_version, profile_id, profile_sha256, "
                "engine_version, document_json, created_at) "
                "VALUES (:id, 1, 'copa-valle-results-pdf', :sha, "
                "'results_skill@0.1.0', :doc, NOW())"
            ),
            {"id": import_id, "sha": "e" * 64, "doc": json.dumps(payload)},
        )

    with engine.begin() as conn:
        stored = conn.execute(
            text(
                "SELECT document_json FROM race_import_staged_documents "
                "WHERE import_id = :id"
            ),
            {"id": import_id},
        ).scalar_one()
    engine.dispose()

    reloaded = json.loads(stored) if isinstance(stored, str) else stored
    assert reloaded == payload


def test_upgrade_downgrade_upgrade_round_trip(clean_schema: str) -> None:
    cfg = _alembic_config(clean_schema)
    command.upgrade(cfg, REVISION)
    command.downgrade(cfg, DOWN_REVISION)
    command.upgrade(cfg, REVISION)

    engine = create_engine(clean_schema, future=True)
    with engine.begin() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        table_exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'race_import_staged_documents'"
            )
        ).scalar()
    engine.dispose()
    assert current == REVISION
    assert table_exists == 1
