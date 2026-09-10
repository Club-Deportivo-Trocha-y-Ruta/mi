"""G15 (feature 041) — comportamiento real de las compuertas de archivado
añadidas en los sitios que la compuerta estática ``test_archive_scope_gate.py``
marcaba en rojo.

``test_archive_scope_gate.py`` es análisis estático: comprueba que la consulta
*lleve* el filtro. Este módulo comprueba que el filtro *haga* lo que debe en
las dos superficies de familia más sensibles del lote:

- ``routers/consent.py::_active_athlete_or_404`` — una familia no puede
  renovar ni revocar consentimiento para un atleta archivado (FR-014).
- ``services/permissions.py::can_view_activity`` / ``can_link_activity`` — el
  coach pierde el acceso a las actividades de Strava de un atleta archivado,
  el admin lo conserva (regla C3 del contrato ``athlete-archive.md`` §5.1).

Vía offline (aiosqlite in-memory) reutilizando el escenario compartido
``tests.fixtures.two_coaches``; no toca el fixture ``client`` ni MySQL.

Ningún nombre corresponde a una persona real (CLAUDE.md, Ley 1581).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.athlete import Athlete
from app.models.user import User
from app.routers.consent import _active_athlete_or_404
from app.services.permissions import can_link_activity, can_view_activity

from tests.fixtures.two_coaches import TwoCoachesScenario

pytestmark = pytest.mark.asyncio


async def _archive(session: AsyncSession, athlete_id: int) -> None:
    """Marca el atleta como archivado (equivalente mínimo de
    ``athlete_scope.archive_athlete``, sin el rastro de auditoría)."""
    athlete = await session.get(Athlete, athlete_id)
    assert athlete is not None
    athlete.deleted_at = datetime.now(timezone.utc)
    await session.commit()


async def _load_user(session: AsyncSession, user_id: int) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    return user


# ---------------------------------------------------------------------------
# consent.py — renovar / revocar consentimiento
# ---------------------------------------------------------------------------


async def test_consent_gate_devuelve_atleta_activo(
    two_coaches_scenario: TwoCoachesScenario,
) -> None:
    session = two_coaches_scenario.session
    athlete = await _active_athlete_or_404(session, two_coaches_scenario.athlete_id)
    assert athlete.id == two_coaches_scenario.athlete_id


async def test_consent_gate_404_para_atleta_archivado(
    two_coaches_scenario: TwoCoachesScenario,
) -> None:
    """Una familia nunca debe poder renovar consentimiento de un archivado."""
    session = two_coaches_scenario.session
    await _archive(session, two_coaches_scenario.athlete_id)

    with pytest.raises(HTTPException) as exc:
        await _active_athlete_or_404(session, two_coaches_scenario.athlete_id)

    assert exc.value.status_code == 404


async def test_consent_gate_404_para_atleta_inexistente(
    two_coaches_scenario: TwoCoachesScenario,
) -> None:
    with pytest.raises(HTTPException) as exc:
        await _active_athlete_or_404(two_coaches_scenario.session, 99_999)

    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# permissions.py — actividades de Strava
# ---------------------------------------------------------------------------


async def test_coach_pierde_acceso_a_actividades_de_atleta_archivado(
    two_coaches_scenario: TwoCoachesScenario,
) -> None:
    session = two_coaches_scenario.session
    coach = await _load_user(session, two_coaches_scenario.coach_a_user_id)

    assert await can_view_activity(coach, two_coaches_scenario.athlete_id, session)

    await _archive(session, two_coaches_scenario.athlete_id)

    assert not await can_view_activity(coach, two_coaches_scenario.athlete_id, session)


async def test_admin_conserva_acceso_a_actividades_de_atleta_archivado(
    two_coaches_scenario: TwoCoachesScenario,
) -> None:
    """Regla C3 del contrato: coach y padre reciben 404, el admin ve el archivo."""
    session = two_coaches_scenario.session
    admin = await _load_user(session, two_coaches_scenario.admin_user_id)

    await _archive(session, two_coaches_scenario.athlete_id)

    assert await can_view_activity(admin, two_coaches_scenario.athlete_id, session)


async def test_coach_no_puede_vincular_actividad_de_atleta_archivado(
    two_coaches_scenario: TwoCoachesScenario,
) -> None:
    session = two_coaches_scenario.session
    coach = await _load_user(session, two_coaches_scenario.coach_a_user_id)
    activity = SimpleNamespace(athlete_id=two_coaches_scenario.athlete_id)

    assert await can_link_activity(coach, activity, session)  # type: ignore[arg-type]

    await _archive(session, two_coaches_scenario.athlete_id)

    assert not await can_link_activity(coach, activity, session)  # type: ignore[arg-type]


async def test_padre_no_ve_actividades_de_atleta_archivado(
    two_coaches_scenario: TwoCoachesScenario,
) -> None:
    """El camino de padre pasa por ``parent_athlete_ids`` (choke point C1)."""
    session = two_coaches_scenario.session
    parent = await _load_user(session, two_coaches_scenario.parent_user_id)

    assert await can_view_activity(parent, two_coaches_scenario.athlete_id, session)

    await _archive(session, two_coaches_scenario.athlete_id)

    assert not await can_view_activity(parent, two_coaches_scenario.athlete_id, session)
