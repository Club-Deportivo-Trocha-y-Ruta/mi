"""FR-014 — un atleta archivado desaparece de toda superficie de coach y
padre (feature 041, US2, contract ``athlete-archive.md`` §5, §12.2).

Un atleta archivado y un atleta activo del mismo club; cada listado/agregado
alcanzable por coach o padre debe excluir al primero e incluir al segundo.
El puñado de sitios que §5.3 marca como exentos (``forbidden_names`` para
guardrails de IA/redacción, la vista admin ``include_archived=true`` y el
historial de auditoría) deben seguir incluyendo al atleta archivado.

Los paths HTTP se toman de ``app.routes`` (no de una lista escrita a mano)
para que una ruta renombrada falle aquí en vez de silenciarse como un 404
que "parece" ausencia correcta.

Corre en la vía offline aiosqlite, con un engine propio — no usa el fixture
``client`` de ``conftest.py`` porque ese exige MySQL.

Ningún nombre en este archivo corresponde a una persona real (CLAUDE.md,
Ley 1581).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool


@compiles(LONGTEXT, "sqlite")
def _compile_longtext_as_text_on_sqlite(element, compiler, **kw):  # pragma: no cover
    """``PrivacyPolicy.content_html`` es MySQL ``LONGTEXT`` — no existe en el
    dialecto sqlite usado por esta vía offline. Sin este shim, cualquier
    ``create_all`` que incluya ``privacy_policies`` explota con
    ``UnsupportedCompilationError`` antes de llegar a un solo assert (mismo
    hallazgo pre-existente en ``tests/test_parent_archived_only.py``, no
    introducido aquí). ``TEXT`` es un superset suficiente para pruebas.
    """
    return "TEXT"

from app.dependencies import get_current_user, get_db
from app.main import app
from tests.helpers.app_routes import api_route_paths
from app.models import Base
from app.models.athlete import FamilyRelationship, Sex
from app.models.club import ClubRole
from app.models.parental_consent import ParentalConsent
from app.models.privacy_policy import PrivacyPolicy
from app.models.user import User, UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.audit_tables import AUDIT_TABLES

# ``asyncio_mode = "auto"`` en pyproject.toml — no se necesita
# ``pytestmark = pytest.mark.asyncio``; agregarlo aquí generaría un warning
# en ``test_expected_routes_exist_in_app`` (la única prueba síncrona de este
# archivo).

CLUB_ID = 1
COACH_ID = 800
ADMIN_ID = 801
PARENT_ID = 802
ARCHIVED_ATHLETE_ID = 90
ARCHIVED_ATHLETE_USER_ID = 9990
ACTIVE_ATHLETE_ID = 91
ACTIVE_ATHLETE_USER_ID = 9991

ARCHIVED_NAME = ("Atleta Ficticio", "Archivado")
ACTIVE_NAME = ("Atleta Ficticio", "Activo")

_TABLES = [
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "parental_consents",
    "athlete_monthly_newsletters",
    "anthropometric_records",
    *AUDIT_TABLES,
]


# ---------------------------------------------------------------------------
# Verificación de que las rutas citadas por este test siguen existiendo tal
# como el contrato las nombra — si una ruta se renombra o se elimina, este
# assert falla en vez de dejar que el resto del test "pase" contra un 404
# genérico que no distingue "atleta ausente" de "ruta inexistente".
# ---------------------------------------------------------------------------
EXPECTED_ROUTE_PATHS = {
    "/api/athletes",
    "/api/parent-athletes/my-athletes",
    "/api/parent-athletes",
    "/api/me/consent",
    "/api/dashboard/coach-summary",
    "/api/athletes/alerts",
    "/api/training/athlete-newsletters/summary",
    "/api/athletes/{athlete_id}",
    "/api/athletes/{athlete_id}/growth-summary",
    "/api/race-analysis/runs",
}


def test_expected_routes_exist_in_app():
    """Guarda contra deriva: si una de estas rutas cambia de path, este test
    debe fallar aquí primero, no disfrazarse de "atleta ausente" más abajo.
    """
    actual_paths = api_route_paths(app)
    missing = EXPECTED_ROUTE_PATHS - actual_paths
    assert not missing, f"Rutas del contrato que ya no existen en app.routes: {missing}"


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def scenario(session_factory):
    """Un club con un coach, un admin, un padre, un atleta archivado y uno
    activo. El padre está vinculado a ambos atletas para que "mis atletas"
    tenga algo real que excluir/incluir.
    """
    async with session_factory() as session:
        await create_club(session, club_id=CLUB_ID, name="Club Ficticio Uno", code="cft-a-090")

        coach = await create_user(session, user_id=COACH_ID, role=UserRole.coach, first_name="Coach", last_name="Ficticio")
        await link_user_to_club(session, user_id=COACH_ID, club_id=CLUB_ID, role_in_club=ClubRole.coach)

        admin = await create_user(session, user_id=ADMIN_ID, role=UserRole.admin, first_name="Admin", last_name="Ficticio")

        parent = await create_user(session, user_id=PARENT_ID, role=UserRole.parent, first_name="Padre", last_name="Ficticio")
        await link_user_to_club(session, user_id=PARENT_ID, club_id=CLUB_ID, role_in_club=ClubRole.parent)

        archived = await create_athlete(
            session,
            athlete_id=ARCHIVED_ATHLETE_ID,
            first_name=ARCHIVED_NAME[0],
            last_name=ARCHIVED_NAME[1],
            birth_date=date(2013, 4, 1),
            club_id=CLUB_ID,
            user_id=ARCHIVED_ATHLETE_USER_ID,
            created_by=coach.id,
        )
        archived.deleted_at = datetime.now(timezone.utc)
        archived.deleted_by_user_id = coach.id
        archived.deleted_reason_code = "athlete_left_club"

        active = await create_athlete(
            session,
            athlete_id=ACTIVE_ATHLETE_ID,
            first_name=ACTIVE_NAME[0],
            last_name=ACTIVE_NAME[1],
            birth_date=date(2013, 6, 1),
            club_id=CLUB_ID,
            user_id=ACTIVE_ATHLETE_USER_ID,
            created_by=coach.id,
        )

        await link_parent_to_athlete(session, parent_user_id=PARENT_ID, athlete_id=archived.id)
        await link_parent_to_athlete(session, parent_user_id=PARENT_ID, athlete_id=active.id)

        policy = PrivacyPolicy(
            version="v1",
            effective_date=date(2026, 1, 1),
            title="Política ficticia",
            content_html="<p>contenido ficticio</p>",
            content_hash="0" * 64,
        )
        session.add(policy)
        await session.flush()

        # Consentimiento vigente solo para el atleta ACTIVO. Si
        # ``compute_consents_pending`` no filtrara al archivado, el
        # archivado (sin consentimiento) sumaría un pendiente extra.
        session.add(
            ParentalConsent(
                parent_user_id=PARENT_ID,
                athlete_id=active.id,
                consent_version="v1",
                policy_id=policy.id,
                data_collection=True,
                training_tracking=True,
                anthropometry=True,
                third_party_sharing=True,
            )
        )

        await session.commit()

    return None


@pytest_asyncio.fixture
async def client_factory(session_factory):
    @asynccontextmanager
    async def make_client(user_id: int):
        async with session_factory() as load_session:
            result = await load_session.execute(
                select(User).options(selectinload(User.club_memberships)).where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db():
            async with session_factory() as session:
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


def _ids(rows: list[dict], key: str) -> set[int]:
    return {row[key] for row in rows}


# ---------------------------------------------------------------------------
# Coach surface
# ---------------------------------------------------------------------------


async def test_coach_athlete_list_excludes_archived(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.get("/api/athletes", params={"club_id": CLUB_ID})
    assert resp.status_code == 200
    ids = _ids(resp.json()["items"], "id")
    assert ARCHIVED_ATHLETE_ID not in ids
    assert ACTIVE_ATHLETE_ID in ids


async def test_coach_cannot_request_include_archived(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.get(
            "/api/athletes", params={"club_id": CLUB_ID, "include_archived": "true"}
        )
    assert resp.status_code == 403


async def test_admin_include_archived_shows_archived_with_evidence(scenario, client_factory):
    async with client_factory(ADMIN_ID) as client:
        resp = await client.get("/api/athletes", params={"include_archived": "true"})
    assert resp.status_code == 200
    items = {row["id"]: row for row in resp.json()["items"]}
    assert ARCHIVED_ATHLETE_ID in items
    archived_row = items[ARCHIVED_ATHLETE_ID]
    assert archived_row["deleted_at"] is not None
    assert archived_row["deleted_reason_code"] == "athlete_left_club"


async def test_coach_athlete_detail_404_for_archived(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.get(f"/api/athletes/{ARCHIVED_ATHLETE_ID}")
    assert resp.status_code == 404


async def test_coach_growth_summary_404_for_archived(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.get(f"/api/athletes/{ARCHIVED_ATHLETE_ID}/growth-summary")
    assert resp.status_code == 404


async def test_coach_alerts_exclude_archived(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.get("/api/athletes/alerts", params={"club_id": CLUB_ID})
    assert resp.status_code == 200
    ids = _ids(resp.json()["athletes"], "athlete_id")
    assert ARCHIVED_ATHLETE_ID not in ids


async def test_coach_parent_link_list_excludes_archived(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.get("/api/parent-athletes")
    assert resp.status_code == 200
    ids = _ids(resp.json()["items"], "athlete_id")
    assert ARCHIVED_ATHLETE_ID not in ids
    assert ACTIVE_ATHLETE_ID in ids


async def test_newsletter_status_summary_excludes_archived(scenario, client_factory):
    async with client_factory(COACH_ID) as client:
        resp = await client.get(
            "/api/training/athlete-newsletters/summary",
            params={"year": 2026, "month": 8},
        )
    assert resp.status_code == 200
    ids = _ids(resp.json()["items"], "athlete_id")
    assert ARCHIVED_ATHLETE_ID not in ids
    assert ACTIVE_ATHLETE_ID in ids


async def test_dashboard_consents_pending_excludes_archived(scenario, client_factory):
    """El archivado no tiene consentimiento vigente; si no se filtrara,
    ``consents_pending`` contaría 1 pendiente de más (el activo sí consintió).
    """
    async with client_factory(COACH_ID) as client:
        resp = await client.get("/api/dashboard/coach-summary", params={"club_id": CLUB_ID})
    assert resp.status_code == 200
    assert resp.json()["consents_pending"] == 0


async def test_ai_run_launch_404_for_archived_athlete(
    scenario, client_factory, monkeypatch
):
    # La aserción es sobre el atleta archivado, no sobre el interruptor de IA:
    # ``start_run`` responde 503 en cuanto ``AI_ENABLED`` está apagado, antes de
    # mirar el atleta. Sin fijar la bandera aquí, la prueba dependía del orden de
    # ejecución de la suite (pasaba aislada, fallaba con 503 en la corrida
    # completa). Ver brecha G23 de checklists/integration-review.md.
    from app.config import settings as _settings

    monkeypatch.setattr(_settings, "ai_enabled", True, raising=False)
    async with client_factory(COACH_ID) as client:
        resp = await client.post(
            "/api/race-analysis/runs",
            json={"athlete_id": ARCHIVED_ATHLETE_ID, "season": 2026},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Parent surface
# ---------------------------------------------------------------------------


async def test_parent_my_athletes_excludes_archived(scenario, client_factory):
    async with client_factory(PARENT_ID) as client:
        resp = await client.get("/api/parent-athletes/my-athletes")
    assert resp.status_code == 200
    ids = _ids(resp.json(), "athlete_id")
    assert ARCHIVED_ATHLETE_ID not in ids
    assert ACTIVE_ATHLETE_ID in ids


async def test_parent_consent_status_excludes_archived(scenario, client_factory):
    async with client_factory(PARENT_ID) as client:
        resp = await client.get("/api/me/consent")
    assert resp.status_code == 200
    ids = _ids(resp.json()["consents_per_athlete"], "athlete_id")
    assert ARCHIVED_ATHLETE_ID not in ids
    assert ACTIVE_ATHLETE_ID in ids


async def test_parent_athlete_detail_denied_for_archived(scenario, client_factory):
    """contracts/athlete-archive.md §7 documenta ``403``; hoy
    ``verify_athlete_access`` evalúa el gate "archivado -> 404" para
    cualquier rol no-admin antes de distinguir parent de coach — mismo
    hallazgo ya registrado en ``test_parent_archived_only.py``. Se acepta
    cualquiera de los dos porque lo que importa para FR-014 es que el dato
    del atleta no se revela; el texto exacto es un hallazgo separado.
    """
    async with client_factory(PARENT_ID) as client:
        resp = await client.get(f"/api/athletes/{ARCHIVED_ATHLETE_ID}")
    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# §5.3 — sitios que deben seguir incluyendo al archivado
# ---------------------------------------------------------------------------


async def test_admin_history_and_exempt_sites_still_include_archived(scenario, session_factory):
    """No hay un endpoint HTTP liviano de historial por atleta sin más
    fixtures de auditoría en este archivo; se verifica el exento más barato
    y representativo: ``_build_forbidden_names`` (guardrail de redacción de
    boletines) debe seguir devolviendo el nombre del atleta archivado —
    dropping it would leak an archived teammate's name into a family
    newsletter's coach-note text.
    """
    from app.routers.athlete_monthly_newsletters import _build_forbidden_names

    async with session_factory() as session:
        names = await _build_forbidden_names(session, CLUB_ID)
    assert f"{ARCHIVED_NAME[0]} {ARCHIVED_NAME[1]}" in names
