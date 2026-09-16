"""Cobertura MySQL real del hotfix "identidad de válida" (2026-09-16, ver
``~/.claude/plans/multicopa-identidad-valida.md``) sobre
``athlete_ai_insights.insight_scope_key`` / ``uq_insights_active_scope``.

Por qué esto necesita MySQL real y no basta con la vía offline (aiosqlite):
el UNIQUE parcial se apoya en que ``NULL`` es DISTINCT dentro de un UNIQUE
constraint — comportamiento de InnoDB (MySQL/MariaDB) que SQLite también
imita, pero la semántica exacta de choque (``ER_DUP_ENTRY`` /
``IntegrityError`` real del motor, no solo la capa Python del ORM) solo se
valida contra el dialecto de producción. `tests/models/test_athlete_ai_insight_scope_key.py`
ya cubre el mismo escenario sobre aiosqlite — este módulo es la confirmación
contra el motor real, igual que ``tests/mysql/test_race_course_models.py``.

Sin ``TEST_DATABASE_URL`` (mysql+aiomysql://…, nombre de base terminado en
``_test``) este módulo entero se salta solo, vía la fixture ``mysql_session``
de ``tests/conftest.py``. Correr con::

    TEST_DATABASE_URL="mysql+aiomysql://root:testroot@127.0.0.1:3306/trocha_ruta_test" \\
        pytest -m mysql -q tests/mysql/test_athlete_ai_insight_scope_key_mysql.py

Privacidad (Ley 1581): club/entrenador/atleta/copas son enteramente
ficticios (mismo patrón sintético que el resto de la suite mysql).

Rango de ids dedicado (970_000+) para no colisionar con otra fila de
``clubs``/``users``/``athletes``/``race_series``/``race_events`` de otro
módulo marcado ``mysql`` — ver rangos ya usados: ``tests/mysql/test_race_course_models.py``
(943_000+), ``tests/test_ai_explanation_columns_mysql.py`` (961_000+).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.user import UserRole
from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_event,
    create_race_series,
    create_user,
)

pytestmark = pytest.mark.mysql

_CLUB_ID = 970_000
_COACH_ID = 970_001
_ATHLETE_USER_ID = 970_002
_ATHLETE_ID = 970_000

_COPA_VALLE_SERIES_ID = 970_010
_LETS_GO_SERIES_ID = 970_011


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _rollback_after_each_test(mysql_session: AsyncSession):
    """Red de seguridad: ``mysql_session`` es de alcance de sesión de pytest
    y la comparte TODO el resto de la corrida ``-m mysql``. Cualquier error
    en este módulo (un FK roto en el seed, un assert fallido a mitad de un
    INSERT sin commit, no solo el ``IntegrityError`` esperado de
    ``test_same_event_id_twice_active_raises_integrity_error_mysql``) deja
    la sesión en estado "pending rollback" — sin este rollback incondicional
    tras CADA test, ese estado se filtra a los módulos ``mysql`` que corren
    después y produce fallos en cascada no relacionados con este archivo.
    Redundante con el rollback explícito ya presente en ese test (queda
    documentado ahí porque sigue siendo el ejemplo canónico del patrón) —
    un segundo rollback sobre una sesión ya limpia es un no-op."""
    yield
    await mysql_session.rollback()


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def scenario(mysql_session: AsyncSession) -> dict[str, int]:
    """Club + entrenador + atleta + 2 copas 2026, sembrados una sola vez.

    ``scope="module"`` porque ``mysql_session`` es de alcance de sesión de
    pytest — sembrar el club/atleta más de una vez en este módulo chocaría
    contra la PK. Cada test crea sus propias válidas/insights en su propio
    sub-rango de ids.
    """
    await create_club(mysql_session, club_id=_CLUB_ID, name="Club Prueba 970", code="tst970")
    await create_user(
        mysql_session, user_id=_COACH_ID, role=UserRole.coach,
        first_name="Entrenador", last_name="Prueba970",
    )
    await create_user(
        mysql_session, user_id=_ATHLETE_USER_ID, role=UserRole.athlete, can_login=False,
    )
    await create_athlete(
        mysql_session, athlete_id=_ATHLETE_ID, club_id=_CLUB_ID, user_id=_ATHLETE_USER_ID,
        first_name="Atleta", last_name="Prueba970", created_by=_COACH_ID,
    )
    await create_race_series(
        mysql_session, series_id=_COPA_VALLE_SERIES_ID, season_year=2026,
        name="Copa Valle Prueba 970",
    )
    await create_race_series(
        mysql_session, series_id=_LETS_GO_SERIES_ID, season_year=2026,
        name="Copa Let's Go Prueba 970",
    )
    await mysql_session.commit()
    return {
        "club_id": _CLUB_ID,
        "coach_id": _COACH_ID,
        "athlete_id": _ATHLETE_ID,
        "copa_valle_series_id": _COPA_VALLE_SERIES_ID,
        "lets_go_series_id": _LETS_GO_SERIES_ID,
    }


@pytest.mark.asyncio
async def test_two_active_insights_same_valida_num_different_event_coexist_mysql(
    mysql_session: AsyncSession, scenario: dict[str, int]
):
    """El fix real contra MySQL: Copa Valle V4 y Copa Let's Go V4 del mismo
    atleta, mismo ``valida_num``, ambas activas — el ``insight_scope_key``
    distinto (``event:<id>`` por evento) evita el choque que producía el
    viejo ``uq_insights_active_terna``."""
    copa_valle_event = await create_race_event(
        mysql_session, event_id=970_100, series_id=scenario["copa_valle_series_id"],
        sequence_number=4, name="Copa Valle V4 Prueba 970",
        created_by_user_id=scenario["coach_id"],
    )
    lets_go_event = await create_race_event(
        mysql_session, event_id=970_101, series_id=scenario["lets_go_series_id"],
        sequence_number=4, name="Copa Let's Go V4 Prueba 970",
        created_by_user_id=scenario["coach_id"],
    )

    copa_valle_insight = await create_insight(
        mysql_session, athlete_id=scenario["athlete_id"], season=2026, valida_num=4,
        event_id=copa_valle_event.id, generated_by_user_id=scenario["coach_id"],
        is_active=1,
    )
    lets_go_insight = await create_insight(
        mysql_session, athlete_id=scenario["athlete_id"], season=2026, valida_num=4,
        event_id=lets_go_event.id, generated_by_user_id=scenario["coach_id"],
        is_active=1,
    )
    await mysql_session.commit()

    assert copa_valle_insight.insight_scope_key == f"event:{copa_valle_event.id}"
    assert lets_go_insight.insight_scope_key == f"event:{lets_go_event.id}"

    rows = await mysql_session.execute(
        select(AthleteAiInsight.is_active).where(
            AthleteAiInsight.id.in_([copa_valle_insight.id, lets_go_insight.id])
        )
    )
    assert list(rows.scalars().all()) == [1, 1]


@pytest.mark.asyncio
async def test_same_event_id_twice_active_raises_integrity_error_mysql(
    mysql_session: AsyncSession, scenario: dict[str, int]
):
    """Dentro de la MISMA válida, dos insights activos siguen chocando —
    el motor real (InnoDB) rechaza el segundo INSERT."""
    event = await create_race_event(
        mysql_session, event_id=970_102, series_id=scenario["copa_valle_series_id"],
        sequence_number=5, name="Copa Valle V5 Prueba 970",
        created_by_user_id=scenario["coach_id"],
    )
    await create_insight(
        mysql_session, athlete_id=scenario["athlete_id"], season=2026, valida_num=5,
        event_id=event.id, generated_by_user_id=scenario["coach_id"], is_active=1,
    )
    await mysql_session.commit()

    # create_insight ya hace flush() internamente — contra MySQL real el
    # INSERT se manda de inmediato en ese flush, así que el choque del
    # UNIQUE lo dispara esa llamada, no un commit() posterior (a diferencia
    # de dejar el pytest.raises solo alrededor del commit, que dejaría la
    # excepción sin capturar y tumbaría la sesión compartida).
    with pytest.raises(IntegrityError):
        await create_insight(
            mysql_session, athlete_id=scenario["athlete_id"], season=2026, valida_num=5,
            event_id=event.id, generated_by_user_id=scenario["coach_id"], is_active=1,
        )

    # La sesión queda en estado "pending rollback" tras el error del motor;
    # se revierte explícitamente porque ``mysql_session`` es de alcance de
    # sesión y la comparte todo el resto de la corrida ``-m mysql``.
    await mysql_session.rollback()
