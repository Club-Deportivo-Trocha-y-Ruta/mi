"""Hallazgo H3 (feature 041) — fuga entre clubes en ``GET /admin/ai-usage``.

Contexto: la feature 041 amplió ``/admin/ai-usage`` de admin-only a
``_coach_or_admin`` (RBAC en ``routers/race_analysis.py``), pero
``spend_by_user_last_30d`` (``services/race/ai/budget_guard.py``) no tenía
noción de club — un coach veía el nombre y el gasto de IA del staff de
TODOS los clubes, no sólo del suyo. Este módulo cubre el arreglo:

- ``spend_by_user_last_30d(..., visible_user_ids=...)`` repliega todo ``uid``
  fuera del conjunto en una única fila ``"Otros clubes"`` (T15-T17 abajo).
- El router calcula ese conjunto (``_coach_visible_staff_ids``) a partir de
  ``club_members`` acotado a los clubes donde el requester es coach, y lo
  pasa a través del endpoint (T18).

Arnés: SQLite in-memory real (no un doble de sesión) — la agregación de
``spend_by_user_last_30d`` es SQL crudo con ``JSON_EXTRACT`` y un
``LEFT JOIN``, así que un fake que despache por substrings del SQL
verificaría el fake, no la query. Motor + subconjunto de tablas propios,
igual que ``tests/routers/test_audit_log_api.py``; NO se usa la fixture
``client`` de ``tests/conftest.py`` (intenta hablar con MySQL real, que no
existe en este entorno offline).

Privacidad (Ley 1581): esta superficie sólo expone nombres de staff adulto
(coach/admin) y montos en dólares. El único atleta que aparece en el arnés
es ficticio y sólo existe para satisfacer la FK NOT NULL de
``athlete_ai_insights.athlete_id`` — su nombre no viaja en ninguna
aserción.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import AsyncGenerator, Optional

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.agent_run import AgentRun  # noqa: F401  (registra agent_runs)
from app.models.athlete import Athlete, Sex
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.club import Club, ClubMember, ClubRole
from app.models.user import User, UserRole
from app.services.race.ai.budget_guard import (
    OTHER_CLUBS_LABEL,
    UNATTRIBUTED_LABEL,
    _sum_cost_last_30d,
    spend_by_user_last_30d,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# IDs ficticios del escenario "dos clubes"
# ---------------------------------------------------------------------------

CLUB_MINE_ID = 1
CLUB_OTHER_ID = 2

COACH_A_ID = 10  # coach del club propio — quien hace la petición en H3
COACH_B_ID = 11  # segundo coach del MISMO club — también visible
OTHER_COACH_ID = 20  # coach de OTRO club — debe replegarse, nunca nombrarse
ADMIN_ID = 1

ATHLETE_USER_ID = 90
ATHLETE_ID = 900

COACH_A_NAME = "Ana Ficticia Coach"
COACH_B_NAME = "Beto Ficticio Coach"
OTHER_COACH_NAME = "Otro Club Ficticio Coach"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Motor propio + subconjunto de tablas (patrón de test_audit_log_api.py)
# ---------------------------------------------------------------------------

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "agent_runs",
    "athlete_ai_insights",
)

_next_id = {"run": 0, "insight": 0}


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    _next_id["run"] = 0
    _next_id["insight"] = 0
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed_two_clubs(session: AsyncSession) -> None:
    """Club propio (coach_a + coach_b), club ajeno (other_coach), admin, atleta."""
    session.add_all(
        [
            Club(id=CLUB_MINE_ID, name="Club Ficticio Uno", code="h3-a", is_active=True),
            Club(id=CLUB_OTHER_ID, name="Club Ficticio Dos", code="h3-b", is_active=True),
        ]
    )
    await session.flush()

    for uid, first, last, role in (
        (ADMIN_ID, "Admin", "Ficticio", UserRole.admin),
        (COACH_A_ID, "Ana Ficticia", "Coach", UserRole.coach),
        (COACH_B_ID, "Beto Ficticio", "Coach", UserRole.coach),
        (OTHER_COACH_ID, "Otro Club Ficticio", "Coach", UserRole.coach),
        (ATHLETE_USER_ID, "Atleta", "Ficticio", UserRole.parent),
    ):
        session.add(
            User(
                id=uid,
                email=f"user{uid}@test.local",
                hashed_password="x",
                first_name=first,
                last_name=last,
                role=role,
                is_active=True,
                can_login=(role != UserRole.parent),
                created_at=_utc_now(),
            )
        )
    await session.flush()

    session.add_all(
        [
            ClubMember(
                user_id=COACH_A_ID,
                club_id=CLUB_MINE_ID,
                role_in_club=ClubRole.coach,
                joined_at=_utc_now(),
            ),
            ClubMember(
                user_id=COACH_B_ID,
                club_id=CLUB_MINE_ID,
                role_in_club=ClubRole.coach,
                joined_at=_utc_now(),
            ),
            ClubMember(
                user_id=OTHER_COACH_ID,
                club_id=CLUB_OTHER_ID,
                role_in_club=ClubRole.coach,
                joined_at=_utc_now(),
            ),
        ]
    )
    await session.flush()

    session.add(
        Athlete(
            id=ATHLETE_ID,
            user_id=ATHLETE_USER_ID,
            first_name="Atleta",
            last_name="Ficticio",
            birth_date=date(2013, 6, 20),
            sex=Sex.M,
            club_id=CLUB_MINE_ID,
            created_by=COACH_A_ID,
        )
    )
    await session.flush()
    await session.commit()


_INSERT_RUN = """
INSERT INTO agent_runs (
    id, external_run_id, graph_name, prompt_version, started_at,
    status, requested_by_user_id, checkpoint_thread_id, created_at, updated_at
) VALUES (
    :id, :rid, 'race-analyst', 'race_analyst_v3', :now,
    'completed', :uid, :rid, :now, :now
)
"""


async def _add_run(session: AsyncSession, *, requested_by: Optional[int]) -> int:
    _next_id["run"] += 1
    run_id = _next_id["run"]
    now = _utc_now()
    await session.execute(
        text(_INSERT_RUN),
        {"id": run_id, "rid": f"run-{run_id}", "uid": requested_by, "now": now},
    )
    return run_id


async def _add_insight(
    session: AsyncSession,
    *,
    cost: float,
    generated_by: Optional[int],
    agent_run_id: Optional[int] = None,
) -> None:
    _next_id["insight"] += 1
    session.add(
        AthleteAiInsight(
            id=_next_id["insight"],
            athlete_id=ATHLETE_ID,
            agent_run_id=agent_run_id,
            generated_by_user_id=generated_by,
            season=2026,
            use_case="race_analysis",
            summary_text="Texto sintetico",
            recommendations_json=[],
            metrics_snapshot_json={"aggregate": {"cost_usd_total": cost}},
            principles_cited_json=[],
            model="modelo-ficticio",
            prompt_version="race_analyst_v3",
            generated_at=_utc_now(),
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )
    await session.flush()


def _by_uid(rows) -> dict[Optional[int], object]:
    return {r.user_id: r for r in rows}


# ===========================================================================
# Nivel servicio — ``spend_by_user_last_30d(..., visible_user_ids=...)``
# ===========================================================================


async def test_visible_user_ids_none_preserva_comportamiento_historico(session_factory):
    """``None`` (default admin): sin repliegue, idéntico al comportamiento previo."""
    async with session_factory() as session:
        await _seed_two_clubs(session)
        run_a = await _add_run(session, requested_by=COACH_A_ID)
        run_other = await _add_run(session, requested_by=OTHER_COACH_ID)
        await _add_insight(session, cost=0.20, agent_run_id=run_a, generated_by=COACH_A_ID)
        await _add_insight(
            session, cost=0.05, agent_run_id=run_other, generated_by=OTHER_COACH_ID
        )
        await session.commit()

        rows = await spend_by_user_last_30d(session, visible_user_ids=None)

        assert {r.user_id for r in rows} == {COACH_A_ID, OTHER_COACH_ID}
        assert OTHER_CLUBS_LABEL not in {r.display_name for r in rows}
        por_uid = _by_uid(rows)
        assert por_uid[OTHER_COACH_ID].display_name == OTHER_COACH_NAME


async def test_repliega_staff_fuera_del_conjunto_sin_nombrarlo(session_factory):
    """El corazón de H3: un uid fuera de ``visible_user_ids`` nunca sale con
    su nombre ni como fila propia — cae dentro de "Otros clubes"."""
    async with session_factory() as session:
        await _seed_two_clubs(session)
        run_a = await _add_run(session, requested_by=COACH_A_ID)
        run_b = await _add_run(session, requested_by=COACH_B_ID)
        run_other = await _add_run(session, requested_by=OTHER_COACH_ID)
        await _add_insight(session, cost=0.10, agent_run_id=run_a, generated_by=COACH_A_ID)
        await _add_insight(session, cost=0.15, agent_run_id=run_b, generated_by=COACH_B_ID)
        await _add_insight(
            session, cost=0.40, agent_run_id=run_other, generated_by=OTHER_COACH_ID
        )
        await session.commit()

        rows = await spend_by_user_last_30d(
            session, visible_user_ids={COACH_A_ID, COACH_B_ID}
        )

        por_uid = _by_uid(rows)
        # Los dos coaches visibles conservan nombre + fila propia.
        assert por_uid[COACH_A_ID].display_name == COACH_A_NAME
        assert por_uid[COACH_B_ID].display_name == COACH_B_NAME
        # El coach de otro club NO aparece como fila propia ni con su nombre.
        assert OTHER_COACH_ID not in por_uid
        assert OTHER_COACH_NAME not in {r.display_name for r in rows}
        # En su lugar, una única fila agregada.
        folded = [r for r in rows if r.display_name == OTHER_CLUBS_LABEL]
        assert len(folded) == 1
        assert folded[0].user_id is None
        assert folded[0].run_count == 1
        assert abs(folded[0].cost_usd_total - 0.40) < 1e-6


async def test_repliegue_conserva_reconciliacion_con_el_guard(session_factory):
    """FR-029/US6 AC4: el repliegue SUMA, nunca descarta — la invariante de
    reconciliación (suma de filas == guard) se sostiene también acotado."""
    async with session_factory() as session:
        await _seed_two_clubs(session)
        run_a = await _add_run(session, requested_by=COACH_A_ID)
        run_b = await _add_run(session, requested_by=COACH_B_ID)
        run_other = await _add_run(session, requested_by=OTHER_COACH_ID)
        await _add_insight(session, cost=0.125, agent_run_id=run_a, generated_by=COACH_A_ID)
        await _add_insight(session, cost=0.250, agent_run_id=run_b, generated_by=COACH_B_ID)
        await _add_insight(
            session, cost=0.625, agent_run_id=run_other, generated_by=OTHER_COACH_ID
        )
        # Insight sin run enlazado, atribuido por respaldo a un coach ajeno:
        # también debe replegarse dentro de "Otros clubes".
        await _add_insight(session, cost=0.375, agent_run_id=None, generated_by=OTHER_COACH_ID)
        await session.commit()

        rows = await spend_by_user_last_30d(
            session, visible_user_ids={COACH_A_ID, COACH_B_ID}
        )
        total_guard = await _sum_cost_last_30d(session)

        assert abs(sum(r.cost_usd_total for r in rows) - total_guard) < 1e-6
        assert abs(total_guard - 1.375) < 1e-6
        folded = next(r for r in rows if r.display_name == OTHER_CLUBS_LABEL)
        assert folded.run_count == 2
        assert abs(folded.cost_usd_total - 1.0) < 1e-6


class _FakeResult:
    """Doble mínimo de ``CursorResult`` — sólo ``fetchall()``, filas-tupla."""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeSpendSession:
    """Doble de ``AsyncSession`` que despacha por el texto de la query.

    ``generated_by_user_id`` (``athlete_ai_insights``) y
    ``requested_by_user_id`` (``agent_runs``) son ``NOT NULL`` en el esquema
    real (ver ``test_con_el_esquema_de_hoy_toda_fila_queda_atribuida`` en
    ``tests/services/race/ai/test_spend_by_user.py``) — el cubo "Sin
    atribuir" es hoy inalcanzable insertando filas reales, sea vía ORM o SQL
    crudo (la constraint vive en la tabla, no en el ORM). Para ejercitar la
    interacción "Sin atribuir" + "Otros clubes" sin tocar el esquema, este
    doble entrega directamente las filas YA agregadas que la query
    produciría — sólo se prueba la lógica de repliegue en Python de
    ``spend_by_user_last_30d``, como autoriza la tarea cuando el SQL crudo no
    puede ejercitar un camino sobre sqlite. Filas-tupla a propósito: ejercita
    el respaldo posicional de ``_row_get`` para dobles, no sólo el camino
    ``Row._mapping`` de SQLAlchemy real.
    """

    def __init__(self, spend_rows: list[tuple], name_rows: list[tuple]) -> None:
        self._spend_rows = spend_rows
        self._name_rows = name_rows

    async def execute(self, stmt, params=None):  # noqa: ANN001 — doble de test
        sql = str(stmt)
        if "FROM athlete_ai_insights i" in sql:
            return _FakeResult(self._spend_rows)
        if "FROM users WHERE id IN" in sql:
            return _FakeResult(self._name_rows)
        raise AssertionError(f"consulta inesperada en _FakeSpendSession: {sql}")


async def test_cubo_sin_atribuir_queda_separado_del_repliegue():
    """El cubo "Sin atribuir" (``uid is None``) es una fila propia, distinta
    de "Otros clubes" — no se funden aunque ambos representen "no es mío".

    Usa ``_FakeSpendSession`` (ver docstring de la clase): el esquema real no
    permite producir la fila NULL con inserts reales.
    """
    fake_db = _FakeSpendSession(
        spend_rows=[
            (COACH_A_ID, 1, 0.10),
            (None, 1, 0.05),  # cubo sin atribuir
            (OTHER_COACH_ID, 1, 0.40),  # debe replegarse
        ],
        name_rows=[(COACH_A_ID, "Ana Ficticia", "Coach")],
    )

    rows = await spend_by_user_last_30d(fake_db, visible_user_ids={COACH_A_ID})

    por_label = {r.display_name: r for r in rows}
    assert UNATTRIBUTED_LABEL in por_label
    assert por_label[UNATTRIBUTED_LABEL].user_id is None
    assert por_label[UNATTRIBUTED_LABEL].run_count == 1
    assert abs(por_label[UNATTRIBUTED_LABEL].cost_usd_total - 0.05) < 1e-6
    # "Otros clubes" es una fila DISTINTA — no absorbe ni se deja absorber
    # por el cubo sin atribuir.
    assert OTHER_CLUBS_LABEL in por_label
    assert por_label[OTHER_CLUBS_LABEL].user_id is None
    assert abs(por_label[OTHER_CLUBS_LABEL].cost_usd_total - 0.40) < 1e-6
    assert OTHER_COACH_NAME not in por_label
    assert len(rows) == 3


async def test_sin_gasto_ajeno_no_aparece_fila_otros_clubes(session_factory):
    """Cuando todo el gasto es del propio conjunto visible, no se agrega una
    fila "Otros clubes" vacía — evita ruido en la UI."""
    async with session_factory() as session:
        await _seed_two_clubs(session)
        run_a = await _add_run(session, requested_by=COACH_A_ID)
        await _add_insight(session, cost=0.10, agent_run_id=run_a, generated_by=COACH_A_ID)
        await session.commit()

        rows = await spend_by_user_last_30d(session, visible_user_ids={COACH_A_ID})

        assert OTHER_CLUBS_LABEL not in {r.display_name for r in rows}


# ===========================================================================
# Nivel HTTP — ``GET /api/race-analysis/admin/ai-usage`` (RBAC + wiring)
# ===========================================================================


@pytest_asyncio.fixture
async def client_factory(session_factory: async_sessionmaker[AsyncSession]):
    """Fábrica ``make_client(user_id, role)`` — mismo patrón que
    ``audit_client_factory`` de ``tests/routers/test_audit_log_api.py``: carga
    el ``User`` real con ``club_memberships`` vía ``selectinload`` (igual que
    ``get_current_user`` en producción) y lo monta sobre ``app`` con
    ``ASGITransport`` — nunca la fixture global ``client``.
    """

    @asynccontextmanager
    async def make_client(user_id: int):
        async with session_factory() as load_session:
            result = await load_session.execute(
                select(User)
                .options(selectinload(User.club_memberships))
                .where(User.id == user_id)
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


@pytest_asyncio.fixture
async def seeded(session_factory: async_sessionmaker[AsyncSession]):
    """Escenario de dos clubes + un run/insight por coach, listo para HTTP."""
    async with session_factory() as session:
        await _seed_two_clubs(session)
        run_a = await _add_run(session, requested_by=COACH_A_ID)
        run_other = await _add_run(session, requested_by=OTHER_COACH_ID)
        await _add_insight(session, cost=0.30, agent_run_id=run_a, generated_by=COACH_A_ID)
        await _add_insight(
            session, cost=0.70, agent_run_id=run_other, generated_by=OTHER_COACH_ID
        )
        await session.commit()


async def test_coach_ve_su_club_y_repliega_el_ajeno_sin_nombre(
    client_factory, seeded
):
    """H3 end-to-end: coach_a llama al endpoint ampliado por la feature 041 y
    NUNCA ve el nombre ni el gasto individual del coach de otro club."""
    async with client_factory(COACH_A_ID) as client:
        resp = await client.get("/api/race-analysis/admin/ai-usage", params={"days": 30})

    assert resp.status_code == 200
    body = resp.json()
    by_coach = body["by_coach"]

    names = {row["display_name"] for row in by_coach}
    assert COACH_A_NAME in names
    assert OTHER_COACH_NAME not in names
    # Ni siquiera como substring en el JSON crudo (nombre O costo aislado).
    assert OTHER_COACH_NAME not in resp.text

    folded = next(row for row in by_coach if row["display_name"] == OTHER_CLUBS_LABEL)
    assert folded["user_id"] is None
    assert folded["run_count"] == 1
    assert abs(folded["cost_usd_total"] - 0.70) < 1e-6

    # La invariante de reconciliación se sostiene también en el payload HTTP.
    assert abs(sum(r["cost_usd_total"] for r in by_coach) - body["cost_usd_total"]) < 1e-6


async def test_admin_ve_a_todo_el_staff_sin_repliegue(client_factory, seeded):
    """El admin conserva el comportamiento histórico: sin repliegue, todos
    los nombres visibles."""
    async with client_factory(ADMIN_ID) as client:
        resp = await client.get("/api/race-analysis/admin/ai-usage", params={"days": 30})

    assert resp.status_code == 200
    by_coach = resp.json()["by_coach"]
    names = {row["display_name"] for row in by_coach}

    assert COACH_A_NAME in names
    assert OTHER_COACH_NAME in names
    assert OTHER_CLUBS_LABEL not in names
