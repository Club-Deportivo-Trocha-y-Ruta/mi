"""Migración ``7c3e9a1f5b24``: categorías propias de la temporada 2023.

Se ejercita ``upgrade``/``downgrade`` sobre un SQLite en memoria con la tabla
mínima (sin tocar ninguna base real). El carril ``-m mysql`` valida el dialecto
MySQL aparte.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_PATH = (
    Path(__file__).parent.parent
    / "alembic" / "versions" / "7c3e9a1f5b24_categorias_copa_valle_2023.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mig_cat_2023", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _engine() -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE race_categories (id INTEGER PRIMARY KEY, code VARCHAR(30) UNIQUE NOT NULL,"
            " label VARCHAR(80), sex VARCHAR(10), age_min INT, age_max INT, tier VARCHAR(10),"
            " sort_order INT, is_active BOOLEAN, created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(sa.text(
            "INSERT INTO race_categories (code,label,sex,tier,sort_order,is_active) "
            "VALUES ('PRE_A','Preinfantil A','M','menores',20,1)"
        ))
    return engine


def _run(engine: sa.Engine, fn) -> None:
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            fn()


def _rows(engine: sa.Engine) -> dict[str, tuple]:
    with engine.connect() as conn:
        return {
            r[0]: tuple(r[1:])
            for r in conn.execute(sa.text(
                "SELECT code, sex, age_min, age_max, tier, is_active FROM race_categories"
            ))
        }


def test_cadena_y_revision() -> None:
    mod = _load()
    assert mod.revision == "7c3e9a1f5b24" and mod.down_revision == "448f7dfbca14"


def test_upgrade_inserta_diez_filas_inactivas_y_downgrade_las_borra() -> None:
    mod, engine = _load(), _engine()
    _run(engine, mod.upgrade)
    rows = _rows(engine)
    nuevos = {c: v for c, v in rows.items() if c.endswith("_2023")}
    assert len(nuevos) == 10
    assert all(v[4] == 0 for v in nuevos.values())  # is_active = false
    assert nuevos["PRE_A_MIX_2023"] == ("MIXED", 6, 7, "menores", 0)
    assert nuevos["PRE_B_MIX_2023"] == ("MIXED", 7, 8, "menores", 0)
    assert nuevos["NOV_F_2023"][0] == "F" and nuevos["NOV_2023"][0] == "M"
    assert nuevos["MAS_A1_2023"][3] == "master" and nuevos["SPORT_B_2023"][3] == "adulto"
    assert rows["PRE_A"] == ("M", None, None, "menores", 1)  # lo existente no se toca

    _run(engine, mod.downgrade)
    assert set(_rows(engine)) == {"PRE_A"}


def test_upgrade_es_idempotente() -> None:
    mod, engine = _load(), _engine()
    _run(engine, mod.upgrade)
    _run(engine, mod.upgrade)
    assert len([c for c in _rows(engine) if c.endswith("_2023")]) == 10


def test_seed_y_migracion_declaran_las_mismas_filas() -> None:
    from scripts.seed_race_categories import CATEGORIES

    mod = _load()
    seed = {
        c[0]: (c[1], c[2].value, c[3], c[4], c[5].value, c[6], c[7])
        for c in CATEGORIES if c[0].endswith("_2023")
    }
    mig = {r[0]: (r[1], r[2], r[3], r[4], r[5], r[6], False) for r in mod._CATEGORIES}
    assert seed == mig
