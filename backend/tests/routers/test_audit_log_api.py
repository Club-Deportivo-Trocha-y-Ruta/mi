"""T034 — pruebas del API de lectura del historial de auditoría (feature 041).

Ver ``specs/041-multi-coach-governance/contracts/audit-log-api.md`` §13
(T1-T4, T6, T8, T12-T14, T16 de la tabla de pruebas requeridas). Cubre:

- camino feliz con nombres de actor resueltos (club y panel de atleta),
- cada filtro documentado en §2.1/§3,
- paginación (`limit`/`offset`/`total`),
- 403 para un padre,
- 403 para un coach de otro club,
- un atleta archivado (`deleted_at` seteado) que sigue devolviéndose a coach
  y admin,
- ausencia de datos personales de un menor en la respuesta serializada,
- conteo de queries SQL <= 2 por request (Principle IV / contrato §11).

Corre en la vía offline aiosqlite — reutiliza el escenario compartido
``tests.fixtures.two_coaches`` (registrado como plugin en
``tests/conftest.py``: club único con ``coach_a``/``coach_b``, un coach de
otro club, un admin, un padre y un atleta ficticio) en vez de construir
usuarios/club desde cero.

``two_coaches_client_factory`` (el de la fixture compartida) monta el actor
con ``club_memberships=[]`` — suficiente para los tests que no dependen de
RBAC basado en membresía, pero ``can_view_audit``/``verify_athlete_access``
sí leen esa lista en memoria (``app/services/permissions.py:73``,
``app/dependencies.py:115-120``). Este módulo define su propia fábrica de
cliente que carga el ``User`` real con ``club_memberships`` vía
``selectinload`` — igual que ``get_current_user`` en producción
(``app/dependencies.py:63``) — para que las pruebas de RBAC sean reales y no
un artefacto del override.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.athlete import Athlete
from app.models.audit_log import AuditAction, AuditActorKind
from app.models.user import User
from app.services.audit import AuditEntityType, AuditReasonCode
from app.services.request_context import request_id_scope
from app.services.audit import record_audit

from tests.fixtures.two_coaches import TwoCoachesScenario
from tests.helpers.query_counting import count_selects


# ---------------------------------------------------------------------------
# Fábrica de cliente HTTP con club_memberships reales (no vacíos)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def audit_client_factory(
    two_coaches_session_factory: async_sessionmaker[AsyncSession],
    two_coaches_scenario: TwoCoachesScenario,
):
    """Fábrica ``make_client(user_id)`` que carga el ``User`` real (con
    ``club_memberships`` vía ``selectinload``, igual que
    ``app/dependencies.py::get_current_user``) y lo monta detrás de
    ``get_current_user``/``get_db``.
    """

    @asynccontextmanager
    async def make_client(user_id: int):
        async with two_coaches_session_factory() as load_session:
            result = await load_session.execute(
                select(User)
                .options(selectinload(User.club_memberships))
                .where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db():
            async with two_coaches_session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: actor
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return make_client


# ---------------------------------------------------------------------------
# Siembra de filas de audit_log sobre el escenario de dos coaches
# ---------------------------------------------------------------------------


async def _load_user(session: AsyncSession, user_id: int) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one()


async def _seed_audit_rows(
    session_factory: async_sessionmaker[AsyncSession],
    scenario: TwoCoachesScenario,
) -> dict:
    """Siembra un puñado de filas realistas y devuelve los ids clave usados
    por las pruebas de filtro/paginación/PII.
    """
    async with session_factory() as session:
        coach_a = await _load_user(session, scenario.coach_a_user_id)
        coach_b = await _load_user(session, scenario.coach_b_user_id)

        # 1) coach_a cancela una sesión de entrenamiento (club, con reason_code)
        with request_id_scope() as rid_cancel:
            await record_audit(
                session,
                action=AuditAction.cancel,
                entity_type=AuditEntityType.training_session,
                entity_id=318,
                actor=coach_a,
                club_id=scenario.club_id,
                athlete_id=None,
                changed_fields=["status"],
                diff={"status": ("programada", "cancelada")},
                meta={"event_date": "2026-03-15"},
                reason_code=AuditReasonCode.cancel_weather,
            )

        # 2) coach_a exporta el PDF de crecimiento del atleta (club + athlete)
        await record_audit(
            session,
            action=AuditAction.export,
            entity_type=AuditEntityType.athlete,
            entity_id=scenario.athlete_id,
            actor=coach_a,
            club_id=scenario.club_id,
            athlete_id=scenario.athlete_id,
            meta={"document_kind": "growth_pdf"},
        )

        # 3) coach_b actualiza datos del atleta (club + athlete, otro actor)
        await record_audit(
            session,
            action=AuditAction.update,
            entity_type=AuditEntityType.athlete,
            entity_id=scenario.athlete_id,
            actor=coach_b,
            club_id=scenario.club_id,
            athlete_id=scenario.athlete_id,
            changed_fields=["club_join_date"],
            diff={"club_join_date": ("2024-01-10", "2024-02-01")},
        )

        # 4) fila de actor automatizado (webhook) — sin actor humano
        await record_audit(
            session,
            action=AuditAction.create,
            entity_type=AuditEntityType.training_session,
            entity_id=319,
            actor=None,
            actor_kind=AuditActorKind.webhook,
            club_id=scenario.club_id,
            athlete_id=None,
        )

        await session.commit()

        return {
            "cancel_request_id": rid_cancel,
        }


async def _archive_athlete(
    session_factory: async_sessionmaker[AsyncSession],
    scenario: TwoCoachesScenario,
) -> None:
    """Archiva (soft-delete) el atleta ficticio y registra la fila de
    auditoría correspondiente — simula el escenario de Edge Case
    spec.md:176 ("un atleta archivado sigue siendo consultable")."""
    async with session_factory() as session:
        coach_a = await _load_user(session, scenario.coach_a_user_id)
        athlete = await session.get(Athlete, scenario.athlete_id)
        athlete.deleted_at = datetime.now(timezone.utc)
        athlete.deleted_by_user_id = coach_a.id
        await record_audit(
            session,
            action=AuditAction.archive,
            entity_type=AuditEntityType.athlete,
            entity_id=scenario.athlete_id,
            actor=coach_a,
            club_id=scenario.club_id,
            athlete_id=scenario.athlete_id,
            reason_code=AuditReasonCode.athlete_family_request,
        )
        await session.commit()


# ---------------------------------------------------------------------------
# T1/T2/T3 — camino feliz, nombres de actor resueltos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_club_audit_log_happy_path_resolves_actor_names(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(f"/api/clubs/{scenario.club_id}/audit-log")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    assert len(body["items"]) == 4

    # Orden: más reciente primero por (occurred_at, id) — la fila 4 (webhook)
    # es la última insertada, debe salir primero.
    occurred_ats = [item["occurred_at"] for item in body["items"]]
    assert occurred_ats == sorted(occurred_ats, reverse=True)

    for item in body["items"]:
        assert item["sentence_es"], "sentence_es no debe estar vacío"
        assert item["actor_display_name"], "actor_display_name no debe estar vacío"
        assert len(item["request_id"]) == 32

    # La fila de coach_a (export) trae su nombre real resuelto por el JOIN.
    export_row = next(i for i in body["items"] if i["action"] == "export")
    assert export_row["actor_display_name"] == "Coach Ficticio A"

    # La fila del webhook no tiene actor humano.
    webhook_row = next(i for i in body["items"] if i["actor_kind"] == "webhook")
    assert webhook_row["actor_user_id"] is None
    assert webhook_row["actor_role"] is None
    assert webhook_row["actor_display_name"] == "Servicio externo"


@pytest.mark.asyncio
async def test_club_audit_log_admin_sees_any_club(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.admin_user_id) as client:
        resp = await client.get(f"/api/clubs/{scenario.club_id}/audit-log")

    assert resp.status_code == 200
    assert resp.json()["total"] == 4


@pytest.mark.asyncio
async def test_athlete_audit_log_happy_path(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(f"/api/athletes/{scenario.athlete_id}/audit-log")

    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 15  # default distinto del endpoint de club (25)
    assert body["total"] == 2  # export + update, no la sesión ni el webhook
    for item in body["items"]:
        assert item["athlete_id"] == scenario.athlete_id
        assert item["actor_display_name"] in {"Coach Ficticio A", "Coach Ficticio B"}


# ---------------------------------------------------------------------------
# T4/T6 — 403 padre y coach de otro club
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_club_audit_log_forbids_parent(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.parent_user_id) as client:
        resp = await client.get(f"/api/clubs/{scenario.club_id}/audit-log")

    assert resp.status_code == 403
    assert "items" not in resp.json()


@pytest.mark.asyncio
async def test_athlete_audit_log_forbids_parent_of_own_child(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    """Regresión de §4.3: el padre está vinculado al atleta, pero el
    historial no es un endpoint "parent-facing" — debe seguir dando 403, no
    el 200 que ``verify_athlete_access`` por sí solo dejaría pasar."""
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.parent_user_id) as client:
        resp = await client.get(f"/api/athletes/{scenario.athlete_id}/audit-log")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_club_audit_log_forbids_coach_of_other_club(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.other_club_coach_user_id) as client:
        resp = await client.get(f"/api/clubs/{scenario.club_id}/audit-log")

    assert resp.status_code == 403
    assert resp.json()["detail"] == "No tienes permisos para ver el historial de este club."


@pytest.mark.asyncio
async def test_club_audit_log_forbids_parent_with_generic_message(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    """§4.4: padre y deportista reciben el texto genérico en ambos endpoints;
    el texto "de este club" queda para el coach sin membresía."""
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.parent_user_id) as client:
        resp = await client.get(f"/api/clubs/{scenario.club_id}/audit-log")

    assert resp.status_code == 403
    assert resp.json()["detail"] == "No tienes permisos para esta acción"


@pytest.mark.asyncio
async def test_athlete_audit_log_forbids_coach_of_other_club(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.other_club_coach_user_id) as client:
        resp = await client.get(f"/api/athletes/{scenario.athlete_id}/audit-log")

    assert resp.status_code == 403
    assert resp.json()["detail"] == "No tienes acceso a este atleta"


# ---------------------------------------------------------------------------
# T16 — atleta archivado sigue visible a coach y admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_athlete_audit_log_still_visible_after_archive(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)
    await _archive_athlete(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(f"/api/athletes/{scenario.athlete_id}/audit-log")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3  # export + update + archive
    actions = {item["action"] for item in body["items"]}
    assert "archive" in actions

    async with audit_client_factory(scenario.admin_user_id) as client:
        resp = await client.get(f"/api/athletes/{scenario.athlete_id}/audit-log")
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


# ---------------------------------------------------------------------------
# T12 — cada filtro documentado en §2.1/§3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_actor_user_id(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"actor_user_id": scenario.coach_b_user_id},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["actor_user_id"] == scenario.coach_b_user_id


@pytest.mark.asyncio
async def test_filter_entity_type(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"entity_type": "training_session"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # cancel + create(webhook)
    assert all(item["entity_type"] == "training_session" for item in body["items"])


@pytest.mark.asyncio
async def test_filter_action(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"action": "export"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "export"


@pytest.mark.asyncio
async def test_filter_athlete_id(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"athlete_id": scenario.athlete_id},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # export + update
    assert all(item["athlete_id"] == scenario.athlete_id for item in body["items"])


@pytest.mark.asyncio
async def test_filter_request_id(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    ids = await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"request_id": ids["cancel_request_id"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["request_id"] == ids["cancel_request_id"]


@pytest.mark.asyncio
async def test_filter_from_to_date_inclusive(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)
    today = datetime.now(timezone.utc).date()

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"from": today.isoformat(), "to": today.isoformat()},
        )
    assert resp.status_code == 200
    assert resp.json()["total"] == 4  # todas las filas ocurrieron "hoy"

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"from": "1999-01-01", "to": "1999-01-02"},
        )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_invalid_date_range_returns_422(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"from": "2026-03-31", "to": "2026-03-01"},
        )

    assert resp.status_code == 422
    assert (
        resp.json()["detail"]
        == "El rango de fechas es inválido: 'from' debe ser anterior o igual a 'to'."
    )


# ---------------------------------------------------------------------------
# T13 — paginación
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pagination_disjoint_pages_and_stable_total(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        page0 = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"limit": 1, "offset": 0},
        )
        page1 = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"limit": 1, "offset": 1},
        )

    assert page0.status_code == page1.status_code == 200
    body0, body1 = page0.json(), page1.json()
    assert body0["total"] == body1["total"] == 4
    assert len(body0["items"]) == len(body1["items"]) == 1
    assert body0["items"][0]["id"] != body1["items"][0]["id"]


@pytest.mark.asyncio
async def test_pagination_offset_beyond_total_returns_empty_with_real_total(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log",
            params={"limit": 25, "offset": 100},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 4


@pytest.mark.asyncio
async def test_pagination_limit_over_ceiling_returns_422(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{scenario.club_id}/audit-log", params={"limit": 51}
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# T8 — ausencia de datos personales de un menor en la respuesta
# ---------------------------------------------------------------------------

_FORBIDDEN_PII_STRINGS = (
    "Mariana Ficticia",  # ATHLETE_FIRST_NAME
    "Restrepo",  # ATHLETE_LAST_NAME
    "2013-06-20",  # ATHLETE_BIRTH_DATE.isoformat()
)
_FORBIDDEN_PII_KEYS = (
    "first_name",
    "last_name",
    "birth_date",
    "sex",
    "email",
    "individual_feedback",
    "coach_note",
)


@pytest.mark.asyncio
async def test_no_pii_of_the_minor_in_club_and_athlete_responses(
    two_coaches_session_factory, two_coaches_scenario, audit_client_factory
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        club_resp = await client.get(f"/api/clubs/{scenario.club_id}/audit-log")
        athlete_resp = await client.get(f"/api/athletes/{scenario.athlete_id}/audit-log")

    for resp in (club_resp, athlete_resp):
        assert resp.status_code == 200
        raw = resp.text
        for forbidden in _FORBIDDEN_PII_STRINGS:
            assert forbidden not in raw, f"PII filtrada en la respuesta: {forbidden!r}"

        def _scan(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    assert key not in _FORBIDDEN_PII_KEYS, f"clave prohibida: {key!r}"
                    _scan(value)
            elif isinstance(node, list):
                for item in node:
                    _scan(item)

        _scan(resp.json())

        # El único nombre propio permitido es el del actor adulto.
        for item in resp.json()["items"]:
            assert item["actor_display_name"] in {
                "Coach Ficticio A",
                "Coach Ficticio B",
                "Servicio externo",
            }


# ---------------------------------------------------------------------------
# T14 — conteo de queries SQL <= 2 por request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_club_audit_log_query_count_is_at_most_two(
    two_coaches_engine,
    two_coaches_session_factory,
    two_coaches_scenario,
    audit_client_factory,
):
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        async with count_selects(two_coaches_engine) as counter:
            resp = await client.get(f"/api/clubs/{scenario.club_id}/audit-log")

    assert resp.status_code == 200
    assert counter[0] == 2, f"esperaba exactamente 2 SELECT, se ejecutaron {counter[0]}"


@pytest.mark.asyncio
async def test_athlete_audit_log_query_count_is_at_most_three(
    two_coaches_engine,
    two_coaches_session_factory,
    two_coaches_scenario,
    audit_client_factory,
):
    """El endpoint de atleta paga una consulta adicional respecto al de
    club: ``verify_athlete_access`` primero carga el ``Athlete``
    (``app/dependencies.py:103``) y luego el router ejecuta las mismas dos
    consultas del presupuesto (§11) — 3 en total, no 2."""
    scenario = two_coaches_scenario
    await _seed_audit_rows(two_coaches_session_factory, scenario)

    async with audit_client_factory(scenario.coach_a_user_id) as client:
        async with count_selects(two_coaches_engine) as counter:
            resp = await client.get(f"/api/athletes/{scenario.athlete_id}/audit-log")

    assert resp.status_code == 200
    assert counter[0] == 3, f"esperaba exactamente 3 SELECT, se ejecutaron {counter[0]}"
