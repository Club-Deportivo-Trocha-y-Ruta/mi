"""T012 — cobertura MySQL real de los modelos de perfil de circuito
(feature 043: ``race_course_variants`` / ``race_course_category_setups`` /
``race_events.terrain_type``).

Por qué esto necesita MySQL real y no basta con la vía offline (aiosqlite):

- ``RaceCourseVariant.geometry`` es una columna ``JSON`` con hasta cientos de
  puntos ``[lat, lon, ele]``; el dialecto MySQL puede normalizar la
  representación numérica de ida y vuelta (p. ej. un float que aterriza como
  entero) de un modo que sqlite no reproduce.
- El ``ondelete="RESTRICT"`` de ``race_course_category_setups.variant_id`` es
  una restricción de motor: sqlite sin ``PRAGMA foreign_keys`` no la aplica.
- ``race_events.terrain_type`` es un ``ENUM`` nativo de MySQL
  (``terraintype``); sqlite lo trata como texto libre y no valida los
  cinco valores.

Sin ``TEST_DATABASE_URL`` (mysql+aiomysql://…, nombre de base terminado en
``_test``) este módulo entero se salta solo, vía la fixture ``mysql_session``
de ``tests/conftest.py`` — igual que ``tests/test_ai_explanation_columns_mysql.py``
y ``tests/test_retention.py`` T20/T21. Correr con::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        pytest -m mysql -q tests/mysql/test_race_course_models.py

Privacidad (Ley 1581): club/entrenador/serie/categoría/válida son enteramente
ficticios (mismo patrón de ids sintéticos que el resto de la suite mysql, p.
ej. ``tests/test_ai_explanation_columns_mysql.py``); la geometría GPX es una
secuencia de números sintéticos generada en este archivo, nunca coordenadas
reales de una válida ni de la grabación de un coach.

Rango de ids dedicado (943_000+, feature 043) para no colisionar con otra
fila de ``users``/``race_series``/``race_categories``/``race_events`` de otro
módulo marcado ``mysql`` — la sesión ``mysql_session`` es de alcance de
sesión de pytest y NO se revierte entre módulos dentro de una misma corrida
``-m mysql`` (sólo ``mysql_engine`` limpia todas las tablas, al final de toda
la corrida). Ver también ``tests/services/race/test_mysql_dialect.py``
(rango 501/601/701/801/90101+) y ``tests/test_ai_explanation_columns_mysql.py``
(rango 961_000+).
"""
from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_course_category_setup import RaceCourseCategorySetup
from app.models.race_course_variant import RaceCourseVariant
from app.models.race_event import RaceEvent, RaceEventStatus, TerrainType
from app.models.user import UserRole
from tests.fixtures.race_history_fixtures import (
    create_race_category,
    create_race_event,
    create_race_series,
    create_user,
)

pytestmark = pytest.mark.mysql

_COACH_ID = 943_001
_SERIES_ID = 943_000
_CATEGORY_ID = 943_000
_CATEGORY_CODE = "INF_B_943_COURSE"

# Un evento/variante/setup por test, cada uno en su propio sub-rango, para que
# los cuatro tests de este módulo (que comparten la sesión de mysql_session
# de alcance de módulo/sesión) nunca choquen entre sí.
_EVENT_GEOMETRY = 943_101
_EVENT_SETUP = 943_102
_EVENT_RESTRICT = 943_103
_EVENT_TERRAIN_BASE = 943_200


def _synthetic_geometry(
    n: int, *, with_elevation: bool = True
) -> list[list[float | None]]:
    """``n`` ternas ``[lat, lon, ele]`` puramente sintéticas.

    Los valores no corresponden a ninguna coordenada real (ni del Valle del
    Cauca ni de ningún otro lugar) — son una progresión aritmética arbitraria
    elegida solo para tener números variados y verificables ida y vuelta.
    """
    points: list[list[float | None]] = []
    for i in range(n):
        lat = round(1.0 + i * 0.0011, 6)
        lon = round(2.0 + i * 0.0013, 6)
        ele = round(100.0 + (i % 40) * 2.25, 2) if with_elevation else None
        points.append([lat, lon, ele])
    return points


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def scenario(mysql_session: AsyncSession) -> dict[str, int]:
    """Un entrenador + una serie + una categoría, sembrados una sola vez.

    ``scope="module"`` porque ``mysql_session`` (tests/conftest.py) es de
    alcance de sesión de pytest: crear la misma serie/categoría más de una
    vez en este módulo chocaría contra la PK/unique. Cada test siembra su
    propia válida (``race_events``) en vez de compartirla.
    """
    await create_user(
        mysql_session,
        user_id=_COACH_ID,
        role=UserRole.coach,
        first_name="Entrenador",
        last_name="Prueba043",
    )
    await create_race_series(
        mysql_session,
        series_id=_SERIES_ID,
        season_year=2026,
        name="Serie Prueba Perfil de Circuito",
    )
    await create_race_category(
        mysql_session,
        category_id=_CATEGORY_ID,
        code=_CATEGORY_CODE,
        label="Infantil B Prueba Circuito",
    )
    await mysql_session.commit()
    return {
        "coach_id": _COACH_ID,
        "series_id": _SERIES_ID,
        "category_id": _CATEGORY_ID,
    }


async def _fetch_variant(db: AsyncSession, variant_id: int) -> RaceCourseVariant:
    """SELECT fresco — fuerza a releer de MySQL en vez de devolver el objeto
    Python cacheado en la identity map (``mysql_session`` usa
    ``expire_on_commit=False``)."""
    result = await db.execute(
        select(RaceCourseVariant)
        .where(RaceCourseVariant.id == variant_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _fetch_setup(db: AsyncSession, setup_id: int) -> RaceCourseCategorySetup:
    result = await db.execute(
        select(RaceCourseCategorySetup)
        .where(RaceCourseCategorySetup.id == setup_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _fetch_event(db: AsyncSession, event_id: int) -> RaceEvent:
    result = await db.execute(
        select(RaceEvent)
        .where(RaceEvent.id == event_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# 1. RaceCourseVariant.geometry (JSON, 600 puntos) ida y vuelta
# ---------------------------------------------------------------------------


async def test_variant_geometry_round_trips(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    await create_race_event(
        mysql_session,
        event_id=_EVENT_GEOMETRY,
        series_id=scenario["series_id"],
        sequence_number=101,
        name="Valida Prueba Geometria",
        created_by_user_id=scenario["coach_id"],
    )

    geometry = _synthetic_geometry(600)
    variant_id = _EVENT_GEOMETRY
    mysql_session.add(
        RaceCourseVariant(
            id=variant_id,
            race_event_id=_EVENT_GEOMETRY,
            label="Circuito Prueba Geometria",
            lap_distance_m=4200,
            elevation_gain_m=180,
            has_elevation=True,
            point_count=len(geometry),
            geometry=geometry,
            detection_method="closed_loop",
            recorded_laps=1,
            source_sha256="f" * 64,
            created_by_user_id=scenario["coach_id"],
        )
    )
    await mysql_session.commit()

    row = await _fetch_variant(mysql_session, variant_id)

    # Estructura/longitud: exacta.
    assert row.point_count == 600
    assert isinstance(row.geometry, list)
    assert len(row.geometry) == 600
    for expected_point, actual_point in zip(geometry, row.geometry, strict=True):
        assert len(actual_point) == 3
        # Valores: MySQL JSON puede normalizar int vs float al releer, así
        # que se compara numéricamente (pytest.approx), no por igualdad de
        # tipo.
        assert actual_point == pytest.approx(expected_point)


# ---------------------------------------------------------------------------
# 2. RaceCourseCategorySetup referenciando una variante — ida y vuelta
# ---------------------------------------------------------------------------


async def test_category_setup_round_trips(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    await create_race_event(
        mysql_session,
        event_id=_EVENT_SETUP,
        series_id=scenario["series_id"],
        sequence_number=102,
        name="Valida Prueba Setup",
        created_by_user_id=scenario["coach_id"],
    )

    variant_id = _EVENT_SETUP
    mysql_session.add(
        RaceCourseVariant(
            id=variant_id,
            race_event_id=_EVENT_SETUP,
            label="Circuito Prueba Setup",
            lap_distance_m=3800,
            elevation_gain_m=None,
            has_elevation=False,
            point_count=10,
            geometry=_synthetic_geometry(10, with_elevation=False),
            detection_method="manual",
            recorded_laps=1,
            source_sha256="e" * 64,
            created_by_user_id=scenario["coach_id"],
        )
    )
    await mysql_session.flush()

    setup_id = _EVENT_SETUP
    mysql_session.add(
        RaceCourseCategorySetup(
            id=setup_id,
            race_event_id=_EVENT_SETUP,
            category_id=scenario["category_id"],
            variant_id=variant_id,
            laps=4,
        )
    )
    await mysql_session.commit()

    row = await _fetch_setup(mysql_session, setup_id)

    assert row.laps == 4
    assert row.race_event_id == _EVENT_SETUP
    assert row.category_id == scenario["category_id"]
    assert row.variant_id == variant_id


# ---------------------------------------------------------------------------
# 3. ondelete=RESTRICT: no se puede borrar una variante referenciada
# ---------------------------------------------------------------------------


async def test_variant_delete_restricted_while_setup_references_it(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    await create_race_event(
        mysql_session,
        event_id=_EVENT_RESTRICT,
        series_id=scenario["series_id"],
        sequence_number=103,
        name="Valida Prueba Restrict",
        created_by_user_id=scenario["coach_id"],
    )

    variant_id = _EVENT_RESTRICT
    mysql_session.add(
        RaceCourseVariant(
            id=variant_id,
            race_event_id=_EVENT_RESTRICT,
            label="Circuito Prueba Restrict",
            lap_distance_m=4000,
            elevation_gain_m=100,
            has_elevation=True,
            point_count=5,
            geometry=_synthetic_geometry(5),
            detection_method="single",
            recorded_laps=1,
            source_sha256="d" * 64,
            created_by_user_id=scenario["coach_id"],
        )
    )
    await mysql_session.flush()

    mysql_session.add(
        RaceCourseCategorySetup(
            id=_EVENT_RESTRICT,
            race_event_id=_EVENT_RESTRICT,
            category_id=scenario["category_id"],
            variant_id=variant_id,
            laps=3,
        )
    )
    await mysql_session.commit()

    variant = await mysql_session.get(RaceCourseVariant, variant_id)
    assert variant is not None
    await mysql_session.delete(variant)
    with pytest.raises(IntegrityError):
        await mysql_session.flush()

    # La sesión queda en estado "pending rollback" tras el error del motor;
    # se revierte explícitamente porque ``mysql_session`` es de alcance de
    # sesión y la comparte todo el resto de la corrida ``-m mysql``.
    await mysql_session.rollback()

    # La variante sigue existiendo — el RESTRICT bloqueó el DELETE.
    still_there = await mysql_session.get(RaceCourseVariant, variant_id)
    assert still_there is not None


# ---------------------------------------------------------------------------
# 4. race_events.terrain_type acepta los cinco valores del ENUM nativo
# ---------------------------------------------------------------------------


async def test_race_event_terrain_type_accepts_all_enum_values(
    mysql_session: AsyncSession, scenario: dict[str, int]
) -> None:
    terrain_values = list(TerrainType)
    assert len(terrain_values) == 5

    event_ids_by_terrain: dict[TerrainType, int] = {}
    for offset, terrain in enumerate(terrain_values, start=1):
        event_id = _EVENT_TERRAIN_BASE + offset
        event_ids_by_terrain[terrain] = event_id
        mysql_session.add(
            RaceEvent(
                id=event_id,
                series_id=scenario["series_id"],
                sequence_number=200 + offset,
                name=f"Valida Prueba Terreno {terrain.value}",
                event_date=date(2026, 6, offset),
                location="Sede Prueba Circuito",
                is_championship=False,
                status=RaceEventStatus.SCHEDULED,
                created_by_user_id=scenario["coach_id"],
                terrain_type=terrain,
            )
        )
    await mysql_session.commit()

    for terrain, event_id in event_ids_by_terrain.items():
        row = await _fetch_event(mysql_session, event_id)
        assert row.terrain_type == terrain
        assert row.terrain_type.value == terrain.value
