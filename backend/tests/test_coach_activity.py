"""T082 — pruebas del informe de actividad por entrenador (feature 041, US7).

Contrato: ``specs/041-multi-coach-governance/contracts/coach-activity-report.md``
§9.1. Cubre la regla de conteo de §2 (fan-out por entrenador vs
``COUNT(DISTINCT)`` en el club), la reconciliación SC-008 contra
``compute_monthly_metrics``, las dos familias de anclaje temporal de §3, el
RBAC de §4 (padre → `403`, entrenador de otro club → `403`), el período
vacío, la invariante de privacidad y el conteo constante de consultas.

Vía offline aiosqlite: este módulo levanta su **propio** motor in-memory con
el subconjunto de tablas que necesita (el de ``tests.fixtures.two_coaches``
no incluye ``training_sessions`` ni las tablas de carreras) y sobre él
siembra el escenario compartido con ``seed_two_coaches``. No usa el fixture
``client`` de ``tests/conftest.py``, que apunta a la base real.

Como en ``tests/routers/test_audit_log_api.py``, la fábrica de cliente carga
el ``User`` real con ``club_memberships`` vía ``selectinload`` — igual que
``get_current_user`` en producción — porque ``can_view_audit`` lee esa lista
en memoria y con el doble de ``two_coaches_client_factory``
(``club_memberships=[]``) el RBAC sería un artefacto del override.

Todos los datos son ficticios (CLAUDE.md, Ley 1581). Los deportistas solo
existen como alcance de las sesiones: ningún nombre de menor entra en las
aserciones ni puede salir en la respuesta.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.athlete import Athlete
from app.models.audit_log import AuditAction, AuditActorKind, AuditLog
from app.models.race_competitor_link_audit import (
    LinkAuditAction,
    RaceCompetitorLinkAudit,
)
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_result_revision import (
    RaceResultRevision,
    RaceResultRevisionAction,
)
from app.models.training_session import (
    AttendanceStatus,
    SessionAttendance,
    SessionKind,
    SessionStatus,
    TrainingSession,
    TrainingSessionCoach,
)
from app.models.user import User, UserRole
from app.services.training.metrics import compute_monthly_metrics

from tests.fixtures.race_history_fixtures import create_athlete, create_user
from tests.fixtures.two_coaches import TwoCoachesScenario, seed_two_coaches
from tests.helpers.audit_tables import AUDIT_TABLES
from tests.helpers.query_counting import count_selects

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Período sintético fijo — nunca depende del reloj (§1.1)
# ---------------------------------------------------------------------------

PERIOD_FROM = date(2026, 3, 1)
PERIOD_TO = date(2026, 3, 31)
PERIOD_QS = f"from={PERIOD_FROM.isoformat()}&to={PERIOD_TO.isoformat()}"

# Deportistas ficticios adicionales (el escenario base trae uno).
ATHLETE_2_ID = 942
ATHLETE_3_ID = 943

# Sesiones del mes sembrado.
S_CO_LED = 5001  # ejecutada, dirigida por A y B
S_A_EXEC = 5002  # ejecutada, solo A
S_A_PLAN = 5003  # planificada, solo A
S_B_CANC = 5004  # cancelada, solo B
S_OUT_OF_WINDOW = 5005  # ejecutada por A, pero en abril

_EXTRA_TABLES = (
    "training_sessions",
    "session_attendance",
    "agent_runs",
    "race_imports",
    "race_result_revisions",
    "race_competitor_link_audit",
)

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "parent_athlete",
    "password_reset_tokens",
    *AUDIT_TABLES,
    *_EXTRA_TABLES,
)


def _dt(day: int, hour: int = 9) -> datetime:
    """Marca de tiempo naive UTC dentro del mes sembrado."""
    return datetime(2026, 3, day, hour, 0, 0)


# ---------------------------------------------------------------------------
# Motor y siembra
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def activity_engine() -> AsyncEngine:
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
async def activity_session_factory(
    activity_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(activity_engine, expire_on_commit=False)


def _session(
    session_id: int,
    *,
    status: SessionStatus,
    club_id: int,
    day: date,
    created_by: int,
) -> TrainingSession:
    return TrainingSession(
        id=session_id,
        club_id=club_id,
        created_by_user_id=created_by,
        status=status,
        scheduled_date=day,
        scheduled_start_time=time(16, 0),
        duration_min=90,
        location="Sede ficticia",
        technical_focus="Técnica de descenso",
        session_kind=SessionKind.ENTRENAMIENTO,
        created_at=_dt(1),
        updated_at=_dt(1),
    )


async def _seed_activity(session: AsyncSession, sc: TwoCoachesScenario) -> None:
    """Siembra el mes sintético completo sobre el escenario de dos coaches.

    Cifras esperadas del período (marzo 2026), verificables a mano:

    - Sesiones — club: 1 planificada, 2 ejecutadas, 1 cancelada (total 4).
      Coach A: 3 (1 planificada + 2 ejecutadas), 1 codirigida.
      Coach B: 2 (1 ejecutada + 1 cancelada), 1 codirigida.
    - Asistencias no archivadas: club 5, A 3, B 2 (más 1 archivada de A).
    - Runs de IA: club 3, A 2, B 1.
    - Resultados: importaciones club 2 (A 1, B 1), revisiones club 3
      (A 2, B 1), vínculos club 2 (A 1, B 1).
    - ``audit_log``: club 6 (A 3, B 2 y 1 del administrador).
    """
    a = sc.coach_a_user_id
    b = sc.coach_b_user_id

    await create_athlete(
        session,
        athlete_id=ATHLETE_2_ID,
        first_name="Deportista Ficticio",
        last_name="Dos",
        birth_date=date(2013, 2, 2),
        club_id=sc.club_id,
        user_id=1942,
        created_by=a,
    )
    await create_athlete(
        session,
        athlete_id=ATHLETE_3_ID,
        first_name="Deportista Ficticio",
        last_name="Tres",
        birth_date=date(2012, 4, 4),
        club_id=sc.club_id,
        user_id=1943,
        created_by=a,
    )

    session.add_all(
        [
            _session(
                S_CO_LED,
                status=SessionStatus.EXECUTED,
                club_id=sc.club_id,
                day=date(2026, 3, 3),
                created_by=a,
            ),
            _session(
                S_A_EXEC,
                status=SessionStatus.EXECUTED,
                club_id=sc.club_id,
                day=date(2026, 3, 10),
                created_by=a,
            ),
            _session(
                S_A_PLAN,
                status=SessionStatus.PLANNED,
                club_id=sc.club_id,
                day=date(2026, 3, 17),
                created_by=a,
            ),
            _session(
                S_B_CANC,
                status=SessionStatus.CANCELLED,
                club_id=sc.club_id,
                day=date(2026, 3, 24),
                created_by=b,
            ),
            # Fuera de ventana: ejecutada por A el 5 de abril.
            _session(
                S_OUT_OF_WINDOW,
                status=SessionStatus.EXECUTED,
                club_id=sc.club_id,
                day=date(2026, 4, 5),
                created_by=a,
            ),
        ]
    )
    await session.flush()

    for session_id, coach_id in (
        (S_CO_LED, a),
        (S_CO_LED, b),
        (S_A_EXEC, a),
        (S_A_PLAN, a),
        (S_B_CANC, b),
        (S_OUT_OF_WINDOW, a),
    ):
        session.add(
            TrainingSessionCoach(
                session_id=session_id,
                coach_user_id=coach_id,
                added_by_user_id=a,
                added_at=_dt(1),
            )
        )

    def _attendance(
        session_id: int,
        athlete_id: int,
        recorder: int,
        archived: datetime | None = None,
    ) -> SessionAttendance:
        return SessionAttendance(
            session_id=session_id,
            athlete_id=athlete_id,
            status=AttendanceStatus.PRESENTE,
            rpe_omni=5,
            rubric_effort=4,
            rubric_attitude=4,
            rubric_technique=3,
            created_at=_dt(4),
            updated_at=_dt(4),
            recorded_by_user_id=recorder,
            archived_at=archived,
        )

    session.add_all(
        [
            _attendance(S_CO_LED, sc.athlete_id, a),
            _attendance(S_CO_LED, ATHLETE_2_ID, a),
            _attendance(S_CO_LED, ATHLETE_3_ID, a),
            _attendance(S_A_EXEC, sc.athlete_id, b),
            _attendance(S_A_EXEC, ATHLETE_2_ID, b),
            # Archivada: no cuenta en ningún contador (§3, nota 3).
            _attendance(S_B_CANC, sc.athlete_id, a, archived=_dt(25)),
        ]
    )

    def _run(run_id: int, actor: int, athlete_id: int | None, started: datetime):
        return AgentRun(
            id=run_id,
            external_run_id=f"run-ficticio-{run_id}",
            graph_name="race_analysis",
            prompt_version="race_analyst_v3",
            started_at=started,
            status=AgentRunStatus.completed,
            requested_by_user_id=actor,
            athlete_id=athlete_id,
            checkpoint_thread_id=f"thread-{run_id}",
            created_at=started,
            updated_at=started,
        )

    session.add_all(
        [
            _run(7001, a, sc.athlete_id, _dt(10)),
            _run(7002, a, None, _dt(11)),
            _run(7003, b, sc.athlete_id, _dt(12)),
            # Fuera de ventana.
            _run(7004, a, sc.athlete_id, datetime(2026, 4, 2, 9, 0, 0)),
            # Coach de otro club, sin atleta: fuera del alcance del club 1.
            _run(7005, sc.other_club_coach_user_id, None, _dt(13)),
        ]
    )

    def _import(
        import_id: int,
        *,
        status: RaceImportStatus,
        imported_by: int,
        imported_at: datetime,
        committed_by: int | None = None,
        committed_at: datetime | None = None,
    ) -> RaceImport:
        return RaceImport(
            id=import_id,
            filename=f"resultados-{import_id}.pdf",
            sha256=f"{import_id:064d}",
            series_id=1,
            status=status,
            stats_json={},
            kind=RaceImportKind.resultados,
            imported_by_user_id=imported_by,
            imported_at=imported_at,
            committed_by_user_id=committed_by,
            committed_at=committed_at,
        )

    session.add_all(
        [
            # Commiteada por A en marzo aunque el parseo lo subió B en febrero:
            # se atribuye al que la commiteó y se ancla en committed_at.
            _import(
                8001,
                status=RaceImportStatus.committed,
                imported_by=b,
                imported_at=datetime(2026, 2, 20, 9, 0, 0),
                committed_by=a,
                committed_at=_dt(5),
            ),
            # Fila legado sin committed_by: cae a imported_by/imported_at.
            _import(
                8002,
                status=RaceImportStatus.committed,
                imported_by=b,
                imported_at=_dt(7),
            ),
            # Parseo en curso: no es una operación de resultados.
            _import(
                8003,
                status=RaceImportStatus.dry_run,
                imported_by=a,
                imported_at=_dt(8),
            ),
        ]
    )

    def _revision(rev_id: int, actor: int, changed: datetime) -> RaceResultRevision:
        return RaceResultRevision(
            id=rev_id,
            result_id=None,
            action=RaceResultRevisionAction.update,
            changed_by_user_id=actor,
            changed_at=changed,
            diff_json={},
        )

    session.add_all(
        [
            _revision(9001, a, _dt(15)),
            _revision(9002, a, _dt(16)),
            _revision(9003, b, _dt(17)),
            _revision(9004, a, datetime(2026, 4, 1, 9, 0, 0)),
        ]
    )

    def _link(
        link_id: int, actor: int, action: LinkAuditAction, created: datetime
    ) -> RaceCompetitorLinkAudit:
        return RaceCompetitorLinkAudit(
            id=link_id,
            competitor_id=1,
            action=action,
            results_propagated=0,
            user_id=actor,
            created_at=created,
        )

    session.add_all(
        [
            _link(9101, a, LinkAuditAction.link, _dt(20)),
            _link(9102, b, LinkAuditAction.unlink, _dt(21)),
            # ``relink`` no está en el catálogo del contrato (§3).
            _link(9103, a, LinkAuditAction.relink, _dt(22)),
        ]
    )

    def _audit(
        audit_id: int,
        actor: int,
        action: AuditAction,
        entity_type: str,
        occurred: datetime,
        role: UserRole = UserRole.coach,
    ) -> AuditLog:
        return AuditLog(
            id=audit_id,
            occurred_at=occurred,
            actor_user_id=actor,
            actor_kind=AuditActorKind.user,
            actor_role=role,
            club_id=sc.club_id,
            athlete_id=None,
            entity_type=entity_type,
            entity_id=1,
            action=action,
            changed_fields=[],
            request_id=f"req-{audit_id}",
        )

    session.add_all(
        [
            _audit(9201, a, AuditAction.approve, "monthly_report", _dt(25)),
            _audit(
                9202, a, AuditAction.approve, "athlete_monthly_newsletter", _dt(26)
            ),
            _audit(
                9203, b, AuditAction.approve, "athlete_monthly_newsletter", _dt(26, 10)
            ),
            _audit(9204, b, AuditAction.send, "athlete_monthly_newsletter", _dt(27)),
            _audit(9205, a, AuditAction.export, "training_session", _dt(28)),
            _audit(
                9206,
                sc.admin_user_id,
                AuditAction.create,
                "training_session",
                _dt(29),
                role=UserRole.admin,
            ),
            # Fuera de ventana.
            _audit(
                9207,
                a,
                AuditAction.approve,
                "monthly_report",
                datetime(2026, 4, 2, 9, 0, 0),
            ),
        ]
    )

    await session.commit()


@pytest_asyncio.fixture
async def activity_scenario(
    activity_session_factory: async_sessionmaker[AsyncSession],
) -> TwoCoachesScenario:
    async with activity_session_factory() as session:
        scenario = await seed_two_coaches(session)
        await _seed_activity(session, scenario)
        return scenario


@pytest_asyncio.fixture
async def activity_client_factory(
    activity_session_factory: async_sessionmaker[AsyncSession],
    activity_scenario: TwoCoachesScenario,
):
    """``make_client(user_id)`` con el ``User`` real y sus membresías."""

    @asynccontextmanager
    async def make_client(user_id: int):
        async with activity_session_factory() as load_session:
            result = await load_session.execute(
                select(User)
                .options(selectinload(User.club_memberships))
                .where(User.id == user_id)
            )
            actor = result.scalar_one()

        async def _override_db():
            async with activity_session_factory() as session:
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


def _url(club_id: int, extra: str = "") -> str:
    return f"/api/clubs/{club_id}/coach-activity?{PERIOD_QS}{extra}"


def _by_id(payload: dict) -> dict[int, dict]:
    return {row["coach"]["user_id"]: row for row in payload["coaches"]}


# ---------------------------------------------------------------------------
# 1-2. Camino feliz (§9.1 tests 1 y 2)
# ---------------------------------------------------------------------------


async def test_coach_member_ve_ambos_entrenadores(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        resp = await client.get(_url(sc.club_id))

    assert resp.status_code == 200
    body = resp.json()
    assert body["club_id"] == sc.club_id
    assert body["from"] == PERIOD_FROM.isoformat()
    assert body["to"] == PERIOD_TO.isoformat()
    assert set(_by_id(body)) == {sc.coach_a_user_id, sc.coach_b_user_id}


async def test_admin_ve_el_informe(activity_scenario, activity_client_factory):
    sc = activity_scenario
    async with activity_client_factory(sc.admin_user_id) as client:
        resp = await client.get(_url(sc.club_id))

    assert resp.status_code == 200
    # El administrador no es una fila del informe: sus actos viven en el
    # historial del club (§1.3).
    assert sc.admin_user_id not in _by_id(resp.json())


async def test_orden_estable_por_apellido(activity_scenario, activity_client_factory):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    assert [row["coach"]["user_id"] for row in body["coaches"]] == [
        sc.coach_a_user_id,
        sc.coach_b_user_id,
    ]


# ---------------------------------------------------------------------------
# 3-5. Caminos denegados (§4)
# ---------------------------------------------------------------------------


async def test_padre_recibe_403(activity_scenario, activity_client_factory):
    sc = activity_scenario
    async with activity_client_factory(sc.parent_user_id) as client:
        resp = await client.get(_url(sc.club_id))

    assert resp.status_code == 403
    assert resp.json()["detail"] == (
        "No tienes permisos para ver la actividad de este club."
    )


async def test_deportista_recibe_403(
    activity_scenario, activity_session_factory, activity_client_factory
):
    sc = activity_scenario
    async with activity_session_factory() as session:
        await create_user(
            session,
            user_id=905,
            role=UserRole.athlete,
            first_name="Deportista",
            last_name="Ficticio",
            can_login=False,
        )
        await session.commit()

    async with activity_client_factory(905) as client:
        resp = await client.get(_url(sc.club_id))

    assert resp.status_code == 403


async def test_coach_de_otro_club_recibe_403(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.other_club_coach_user_id) as client:
        resp = await client.get(_url(sc.club_id))

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6-8. 404 y validación del período (§1.5)
# ---------------------------------------------------------------------------


async def test_club_desconocido_es_404(activity_scenario, activity_client_factory):
    sc = activity_scenario
    async with activity_client_factory(sc.admin_user_id) as client:
        resp = await client.get(_url(99999))

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Club no encontrado"


async def test_coach_user_id_no_miembro_es_404(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        resp = await client.get(
            _url(sc.club_id, f"&coach_user_id={sc.other_club_coach_user_id}")
        )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Entrenador no encontrado en este club"


async def test_coach_user_id_recorta_solo_las_filas(
    activity_scenario, activity_client_factory
):
    """``coach_user_id`` recorta ``coaches``; ``club_totals`` no (§1.1)."""
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        full = (await client.get(_url(sc.club_id))).json()
        narrowed = (
            await client.get(_url(sc.club_id, f"&coach_user_id={sc.coach_b_user_id}"))
        ).json()

    assert len(narrowed["coaches"]) == 1
    assert narrowed["coaches"][0]["coach"]["user_id"] == sc.coach_b_user_id
    assert narrowed["club_totals"] == full["club_totals"]


async def test_periodo_invertido_es_422(activity_scenario, activity_client_factory):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{sc.club_id}/coach-activity?from=2026-03-31&to=2026-03-01"
        )

    assert resp.status_code == 422
    assert resp.json()["detail"] == (
        "El periodo debe empezar antes de terminar y no superar 366 días."
    )


async def test_ventana_de_400_dias_es_422(activity_scenario, activity_client_factory):
    sc = activity_scenario
    desde = date(2026, 1, 1)
    hasta = desde + timedelta(days=400)
    async with activity_client_factory(sc.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{sc.club_id}/coach-activity"
            f"?from={desde.isoformat()}&to={hasta.isoformat()}"
        )

    assert resp.status_code == 422


async def test_ventana_de_366_dias_es_valida(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    desde = date(2026, 1, 1)
    hasta = desde + timedelta(days=366)
    async with activity_client_factory(sc.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{sc.club_id}/coach-activity"
            f"?from={desde.isoformat()}&to={hasta.isoformat()}"
        )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 9. Conteo de sesiones codirigidas (§2, §9.1 test 9)
# ---------------------------------------------------------------------------


async def test_sesion_codirigida_cuenta_para_cada_entrenador(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    rows = _by_id(body)
    a = rows[sc.coach_a_user_id]["sessions"]
    b = rows[sc.coach_b_user_id]["sessions"]

    assert a == {
        "planned": 1,
        "executed": 2,
        "cancelled": 0,
        "total": 3,
        "co_led": 1,
    }
    assert b == {
        "planned": 0,
        "executed": 1,
        "cancelled": 1,
        "total": 2,
        "co_led": 1,
    }
    # El club la cuenta una sola vez: 3 + 2 = 5 asignaciones, 4 sesiones.
    assert body["club_totals"]["sessions"]["total"] == 4
    assert a["total"] + b["total"] > body["club_totals"]["sessions"]["total"]
    # Invariantes del contrato: los tres estados suman el total y las
    # codirigidas son un subconjunto, no un cuarto estado.
    for counters in (a, b):
        assert (
            counters["planned"] + counters["executed"] + counters["cancelled"]
            == counters["total"]
        )
        assert counters["co_led"] <= counters["total"]


# ---------------------------------------------------------------------------
# 10. Reconciliación SC-008 (§9.1 test 10)
# ---------------------------------------------------------------------------


async def test_reconciliacion_con_el_informe_mensual(
    activity_scenario, activity_session_factory, activity_client_factory
):
    """El total del club coincide con ``compute_monthly_metrics`` y con el
    número de sesiones **distintas** de los baldes por entrenador — nunca con
    la suma ingenua."""
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    async with activity_session_factory() as session:
        metrics = await compute_monthly_metrics(session, sc.club_id, 2026, 3)

    sessions = body["club_totals"]["sessions"]
    assert sessions["planned"] == metrics.total_sessions_planned
    assert sessions["executed"] == metrics.total_sessions_executed
    assert sessions["cancelled"] == metrics.total_sessions_cancelled

    # Unión de ids por entrenador, reconstruida desde la siembra: el contrato
    # exige comparar contra el conjunto, no contra la suma.
    per_coach_session_ids = {S_CO_LED, S_A_EXEC, S_A_PLAN} | {S_CO_LED, S_B_CANC}
    assert sessions["total"] == len(per_coach_session_ids)

    naive_sum = sum(row["sessions"]["total"] for row in body["coaches"])
    assert naive_sum >= sessions["total"]
    assert naive_sum - sessions["total"] == 1  # la única asignación extra


# ---------------------------------------------------------------------------
# 11-12. Membresía de coaches[] (§1.3)
# ---------------------------------------------------------------------------


async def test_entrenador_sin_actividad_aparece_en_ceros(
    activity_scenario, activity_session_factory, activity_client_factory
):
    sc = activity_scenario
    async with activity_session_factory() as session:
        from app.models.club import ClubMember, ClubRole

        await create_user(
            session,
            user_id=906,
            role=UserRole.coach,
            first_name="Coach",
            last_name="Ficticio Z",
        )
        session.add(
            ClubMember(user_id=906, club_id=sc.club_id, role_in_club=ClubRole.coach)
        )
        await session.commit()

    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    row = _by_id(body)[906]
    assert row["sessions"]["total"] == 0
    assert row["attendance_entries_recorded"] == 0
    assert row["ai_runs_launched"] == 0
    assert row["results_operations"]["total"] == 0
    assert row["audit_entries_count"] == 0


async def test_entrenador_desactivado_con_actividad_sigue_apareciendo(
    activity_scenario, activity_session_factory, activity_client_factory
):
    """FR-013: quien trabajó ese mes no desaparece del período al darlo de
    baja; la fila llega con ``is_active: false`` y el nombre resuelto."""
    sc = activity_scenario
    async with activity_session_factory() as session:
        await session.execute(
            update(User).where(User.id == sc.coach_b_user_id).values(is_active=False)
        )
        await session.commit()

    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    row = _by_id(body)[sc.coach_b_user_id]
    assert row["coach"]["is_active"] is False
    assert row["coach"]["display_name"] == "Coach Ficticio B"
    assert row["sessions"]["total"] == 2


# ---------------------------------------------------------------------------
# 13-14. Deportista archivado y asistencias archivadas (§1.4, §3 nota 3)
# ---------------------------------------------------------------------------


async def test_atleta_archivado_no_altera_los_conteos(
    activity_scenario, activity_session_factory, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        antes = (await client.get(_url(sc.club_id))).json()

    async with activity_session_factory() as session:
        await session.execute(
            update(Athlete)
            .where(Athlete.id == sc.athlete_id)
            .values(deleted_at=_dt(30))
        )
        await session.commit()

    async with activity_client_factory(sc.coach_a_user_id) as client:
        despues = (await client.get(_url(sc.club_id))).json()

    assert despues["club_totals"] == antes["club_totals"]
    assert despues["coaches"] == antes["coaches"]


async def test_asistencias_archivadas_quedan_fuera(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    rows = _by_id(body)
    # A registró 4 filas, una de ellas archivada: solo cuentan 3.
    assert rows[sc.coach_a_user_id]["attendance_entries_recorded"] == 3
    assert rows[sc.coach_b_user_id]["attendance_entries_recorded"] == 2
    assert body["club_totals"]["attendance_entries_recorded"] == 5


# ---------------------------------------------------------------------------
# 15. Invariante de privacidad (§5, §9.1 test 15)
# ---------------------------------------------------------------------------


async def test_respuesta_no_expone_dato_alguno_de_un_menor(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        resp = await client.get(_url(sc.club_id))

    raw = resp.text
    body = resp.json()

    for prohibido in (
        "Mariana",
        "Restrepo",
        "Deportista Ficticio",
        "2013-06-20",
        "athlete_id",
        "birth_date",
        "first_name",
        "last_name",
    ):
        assert prohibido not in raw

    assert set(body) == {
        "club_id",
        "from",
        "to",
        "computed_at",
        "club_totals",
        "coaches",
    }
    assert set(body["club_totals"]) == {
        "sessions",
        "attendance_entries_recorded",
        "ai_runs_launched",
        "results_operations",
        "documents",
        "audit_entries_count",
    }
    assert set(body["club_totals"]["sessions"]) == {
        "planned",
        "executed",
        "cancelled",
        "total",
    }
    for row in body["coaches"]:
        assert set(row) == {
            "coach",
            "sessions",
            "attendance_entries_recorded",
            "ai_runs_launched",
            "results_operations",
            "documents",
            "audit_entries_count",
        }
        assert set(row["coach"]) == {"user_id", "display_name", "role", "is_active"}
        assert set(row["sessions"]) == {
            "planned",
            "executed",
            "cancelled",
            "total",
            "co_led",
        }
        assert set(row["results_operations"]) == {
            "imports",
            "revisions",
            "competitor_links",
            "total",
        }
        assert set(row["documents"]) == {
            "reports_approved",
            "newsletters_approved",
            "newsletters_sent",
            "exports",
        }
    # Ningún valor de texto libre: solo nombres de personal y enteros.
    assert all(
        isinstance(v, int)
        for row in body["coaches"]
        for k, v in row.items()
        if k not in ("coach", "sessions", "results_operations", "documents")
    )
    json.loads(raw)  # el payload es JSON válido y completo


# ---------------------------------------------------------------------------
# 16. Sin N+1 (§5, §9.1 test 16)
# ---------------------------------------------------------------------------


async def test_numero_de_consultas_no_crece_con_los_entrenadores(
    activity_scenario, activity_engine, activity_session_factory
):
    """El conteo de SELECT es idéntico con 2 y con 5 entrenadores."""
    from app.models.club import ClubMember, ClubRole
    from app.services.coach_activity import compute_coach_activity

    sc = activity_scenario

    async with activity_session_factory() as session:
        async with count_selects(activity_engine) as counter:
            await compute_coach_activity(
                session,
                club_id=sc.club_id,
                period_from=PERIOD_FROM,
                period_to=PERIOD_TO,
            )
        con_dos = counter[0]

    async with activity_session_factory() as session:
        for extra in (911, 912, 913):
            await create_user(
                session,
                user_id=extra,
                role=UserRole.coach,
                first_name="Coach",
                last_name=f"Ficticio {extra}",
            )
            session.add(
                ClubMember(
                    user_id=extra, club_id=sc.club_id, role_in_club=ClubRole.coach
                )
            )
        await session.commit()

    async with activity_session_factory() as session:
        async with count_selects(activity_engine) as counter:
            result = await compute_coach_activity(
                session,
                club_id=sc.club_id,
                period_from=PERIOD_FROM,
                period_to=PERIOD_TO,
            )
        con_cinco = counter[0]

    assert len(result.coaches) == 5
    assert con_dos == con_cinco


# ---------------------------------------------------------------------------
# 17-18. Importaciones de resultados (§1.4, §3 nota 2)
# ---------------------------------------------------------------------------


async def test_import_legado_cae_a_imported_by_y_solo_cuentan_committed(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    rows = _by_id(body)
    # 8001: commiteada por A en marzo (parseada por B en febrero).
    assert rows[sc.coach_a_user_id]["results_operations"]["imports"] == 1
    # 8002: legado sin committed_by → B, anclada en imported_at.
    assert rows[sc.coach_b_user_id]["results_operations"]["imports"] == 1
    # 8003 (dry_run) no aparece por ningún lado.
    assert body["club_totals"]["results_operations"]["imports"] == 2


async def test_resultados_revisiones_y_vinculos(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    rows = _by_id(body)
    assert rows[sc.coach_a_user_id]["results_operations"] == {
        "imports": 1,
        "revisions": 2,
        "competitor_links": 1,
        "total": 4,
    }
    assert rows[sc.coach_b_user_id]["results_operations"] == {
        "imports": 1,
        "revisions": 1,
        "competitor_links": 1,
        "total": 3,
    }
    assert body["club_totals"]["results_operations"] == {
        "imports": 2,
        "revisions": 3,
        "competitor_links": 2,
        "total": 7,
    }


# ---------------------------------------------------------------------------
# Runs de IA, documentos y volumen de historial (§3)
# ---------------------------------------------------------------------------


async def test_runs_de_ia_por_entrenador_y_club(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    rows = _by_id(body)
    assert rows[sc.coach_a_user_id]["ai_runs_launched"] == 2
    assert rows[sc.coach_b_user_id]["ai_runs_launched"] == 1
    # El run del coach de otro club (sin atleta) no entra al alcance.
    assert body["club_totals"]["ai_runs_launched"] == 3


async def test_documentos_y_conteo_de_historial(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        body = (await client.get(_url(sc.club_id))).json()

    rows = _by_id(body)
    assert rows[sc.coach_a_user_id]["documents"] == {
        "reports_approved": 1,
        "newsletters_approved": 1,
        "newsletters_sent": 0,
        "exports": 1,
    }
    assert rows[sc.coach_b_user_id]["documents"] == {
        "reports_approved": 0,
        "newsletters_approved": 1,
        "newsletters_sent": 1,
        "exports": 0,
    }
    assert body["club_totals"]["documents"] == {
        "reports_approved": 1,
        "newsletters_approved": 2,
        "newsletters_sent": 1,
        "exports": 1,
    }
    # El total del club incluye la fila del administrador; la suma de las
    # filas por entrenador (3 + 2) no tiene por qué igualarlo.
    assert rows[sc.coach_a_user_id]["audit_entries_count"] == 3
    assert rows[sc.coach_b_user_id]["audit_entries_count"] == 2
    assert body["club_totals"]["audit_entries_count"] == 6


# ---------------------------------------------------------------------------
# Período vacío (§1.4)
# ---------------------------------------------------------------------------


async def test_periodo_sin_actividad_devuelve_ceros_y_la_plantilla_de_coaches(
    activity_scenario, activity_client_factory
):
    sc = activity_scenario
    async with activity_client_factory(sc.coach_a_user_id) as client:
        resp = await client.get(
            f"/api/clubs/{sc.club_id}/coach-activity"
            "?from=2025-01-01&to=2025-01-31"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["club_totals"] == {
        "sessions": {"planned": 0, "executed": 0, "cancelled": 0, "total": 0},
        "attendance_entries_recorded": 0,
        "ai_runs_launched": 0,
        "results_operations": {
            "imports": 0,
            "revisions": 0,
            "competitor_links": 0,
            "total": 0,
        },
        "documents": {
            "reports_approved": 0,
            "newsletters_approved": 0,
            "newsletters_sent": 0,
            "exports": 0,
        },
        "audit_entries_count": 0,
    }
    assert set(_by_id(body)) == {sc.coach_a_user_id, sc.coach_b_user_id}
