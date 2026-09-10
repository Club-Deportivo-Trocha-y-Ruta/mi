"""T082 — guarda de regresión FR-031 / SC-009 (feature 041).

Contrato: ``specs/041-multi-coach-governance/contracts/coach-activity-report.md``
§9.2. El informe de actividad por entrenador **añade** una superficie; no
puede tocar el Informe Técnico Mensual del club. Esta prueba fija, para un
mes sintético fijo:

1. la instantánea completa de ``compute_monthly_metrics``
   (``app/services/training/metrics.py``), campo por campo, contra literales
   calculados a mano a partir de la siembra — no contra un valor grabado de
   una corrida anterior, para que la aserción siga siendo independiente de
   la implementación; y
2. los encabezados de sección de ``build_report_document_context``
   (``app/services/training/reports.py``), en su orden aprobado.

La siembra ejerce a propósito las tres columnas que esta feature agregó a
las tablas del informe — ``training_session_coaches`` (una sesión con dos
entrenadores), ``session_attendance.recorded_by_user_id`` y
``session_attendance.archived_at`` —, porque el riesgo real de FR-031 es
justamente que alguna de ellas se cuele en el cálculo mensual. El informe
mensual **no** filtra por ``archived_at``: la fila archivada sigue contando
aquí, y esa asimetría respecto del informe por entrenador (que sí la
excluye, §3 nota 3) es deliberada y queda fijada abajo.

Vía offline aiosqlite con subconjunto de tablas; no usa el fixture
``client`` de ``tests/conftest.py``. Datos ficticios (CLAUDE.md, Ley 1581):
los deportistas solo aparecen como ``athlete_id``.
"""
from __future__ import annotations

from datetime import date, datetime, time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.training_session import (
    AttendanceStatus,
    MonthlyReport,
    MonthlyReportStatus,
    SessionAttendance,
    SessionKind,
    SessionStatus,
    TrainingSession,
    TrainingSessionCoach,
)
from app.models.user import UserRole
from app.services.training.metrics import compute_monthly_metrics
from app.services.training.reports import build_report_document_context

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_user,
)
from tests.helpers.audit_tables import AUDIT_TABLES

pytestmark = pytest.mark.asyncio

CLUB_ID = 1
YEAR = 2026
MONTH = 4

COACH_A_ID = 901
COACH_B_ID = 902
ATHLETE_1_ID = 941
ATHLETE_2_ID = 942
ATHLETE_3_ID = 943

FOCO_DESCENSO = "Técnica de descenso"
FOCO_RESISTENCIA = "Resistencia aeróbica"

#: Orden aprobado de las secciones narrativas del Informe Técnico Mensual
#: (formato institucional, feature 022). Congelado aquí a propósito: si
#: alguien agrega, quita o renombra una sección, esta prueba lo detiene.
SECCIONES_APROBADAS = [
    ("objetivo", "Objetivo"),
    ("plan_entrenamiento", "Plan de entrenamiento"),
    ("desarrollo", "Desarrollo de actividades"),
    ("competencia", "Participación en competencia"),
    ("resultados", "Resultados obtenidos"),
    ("conclusiones", "Conclusiones"),
]

_TABLES = (
    "users",
    "clubs",
    "club_members",
    "athletes",
    "training_sessions",
    "session_attendance",
    *AUDIT_TABLES,
)


@pytest_asyncio.fixture
async def report_engine() -> AsyncEngine:
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
async def report_session(report_engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(report_engine, expire_on_commit=False)
    async with factory() as session:
        await _seed_month(session)
        yield session


def _training_session(
    session_id: int,
    *,
    status: SessionStatus,
    day: date,
    focus: str,
    duration: int,
) -> TrainingSession:
    return TrainingSession(
        id=session_id,
        club_id=CLUB_ID,
        created_by_user_id=COACH_A_ID,
        status=status,
        scheduled_date=day,
        scheduled_start_time=time(16, 0),
        duration_min=duration,
        location="Sede ficticia",
        technical_focus=focus,
        session_kind=SessionKind.ENTRENAMIENTO,
        created_at=datetime(YEAR, MONTH, 1, 9, 0, 0),
        updated_at=datetime(YEAR, MONTH, 1, 9, 0, 0),
    )


async def _seed_month(session: AsyncSession) -> None:
    """Mes sintético fijo: abril de 2026, tres sesiones y cuatro asistencias."""
    await create_club(session, club_id=CLUB_ID, name="Club Ficticio Uno", code="cft-041-r")
    await create_user(
        session,
        user_id=COACH_A_ID,
        role=UserRole.coach,
        first_name="Coach",
        last_name="Ficticio A",
    )
    await create_user(
        session,
        user_id=COACH_B_ID,
        role=UserRole.coach,
        first_name="Coach",
        last_name="Ficticio B",
    )
    for athlete_id, user_id, apellido, nacimiento in (
        (ATHLETE_1_ID, 1941, "Uno", date(2013, 6, 20)),
        (ATHLETE_2_ID, 1942, "Dos", date(2013, 2, 2)),
        (ATHLETE_3_ID, 1943, "Tres", date(2012, 4, 4)),
    ):
        await create_athlete(
            session,
            athlete_id=athlete_id,
            first_name="Deportista Ficticio",
            last_name=apellido,
            birth_date=nacimiento,
            club_id=CLUB_ID,
            user_id=user_id,
            created_by=COACH_A_ID,
        )

    session.add_all(
        [
            _training_session(
                6001,
                status=SessionStatus.EXECUTED,
                day=date(YEAR, MONTH, 6),
                focus=FOCO_DESCENSO,
                duration=90,
            ),
            _training_session(
                6002,
                status=SessionStatus.PLANNED,
                day=date(YEAR, MONTH, 13),
                focus=FOCO_RESISTENCIA,
                duration=60,
            ),
            _training_session(
                6003,
                status=SessionStatus.CANCELLED,
                day=date(YEAR, MONTH, 20),
                focus=FOCO_DESCENSO,
                duration=120,
            ),
            # Fuera del mes: no debe entrar en ninguna métrica.
            _training_session(
                6004,
                status=SessionStatus.EXECUTED,
                day=date(YEAR, 5, 4),
                focus=FOCO_DESCENSO,
                duration=90,
            ),
        ]
    )
    await session.flush()

    # Columnas nuevas de la feature 041 en juego: sesión codirigida...
    session.add_all(
        [
            TrainingSessionCoach(
                session_id=6001,
                coach_user_id=COACH_A_ID,
                added_by_user_id=COACH_A_ID,
                added_at=datetime(YEAR, MONTH, 1, 9, 0, 0),
            ),
            TrainingSessionCoach(
                session_id=6001,
                coach_user_id=COACH_B_ID,
                added_by_user_id=COACH_A_ID,
                added_at=datetime(YEAR, MONTH, 1, 9, 0, 0),
            ),
        ]
    )

    def _attendance(
        session_id: int,
        athlete_id: int,
        status: AttendanceStatus,
        recorder: int,
        rpe: int | None = None,
        effort: int | None = None,
        attitude: int | None = None,
        technique: int | None = None,
        archived: datetime | None = None,
    ) -> SessionAttendance:
        return SessionAttendance(
            session_id=session_id,
            athlete_id=athlete_id,
            status=status,
            rpe_omni=rpe,
            rubric_effort=effort,
            rubric_attitude=attitude,
            rubric_technique=technique,
            created_at=datetime(YEAR, MONTH, 6, 18, 0, 0),
            updated_at=datetime(YEAR, MONTH, 6, 18, 0, 0),
            recorded_by_user_id=recorder,
            archived_at=archived,
        )

    session.add_all(
        [
            _attendance(
                6001, ATHLETE_1_ID, AttendanceStatus.PRESENTE, COACH_A_ID,
                rpe=6, effort=4, attitude=5, technique=3,
            ),
            _attendance(
                6001, ATHLETE_2_ID, AttendanceStatus.TARDE, COACH_B_ID,
                rpe=4, effort=3, attitude=3, technique=4,
            ),
            _attendance(6001, ATHLETE_3_ID, AttendanceStatus.AUSENTE, COACH_A_ID),
            # ...y una fila archivada, que el informe mensual SÍ sigue contando.
            _attendance(
                6003,
                ATHLETE_1_ID,
                AttendanceStatus.JUSTIFICADO,
                COACH_A_ID,
                archived=datetime(YEAR, MONTH, 21, 9, 0, 0),
            ),
        ]
    )

    await session.commit()


# ---------------------------------------------------------------------------
# 1. Instantánea de métricas (§9.2)
# ---------------------------------------------------------------------------


async def test_instantanea_de_metricas_del_mes_sintetico(report_session):
    metrics = await compute_monthly_metrics(report_session, CLUB_ID, YEAR, MONTH)
    snapshot = metrics.model_dump(mode="json")

    # ``technical_focus_list`` se arma con un ``set``: su orden no está
    # garantizado y no forma parte del contrato. Se normaliza y se compara
    # aparte; todo lo demás se compara literal.
    assert sorted(snapshot.pop("technical_focus_list")) == sorted(
        [FOCO_DESCENSO, FOCO_RESISTENCIA]
    )

    assert snapshot == {
        "club_id": CLUB_ID,
        "year": YEAR,
        "month": MONTH,
        # 3 sesiones en el mes; la del 4 de mayo queda fuera.
        "total_sessions_planned": 1,
        "total_sessions_executed": 1,
        "total_sessions_cancelled": 1,
        "attendance_by_athlete": {
            # Presente en 6001 y justificado en 6003 → 50 %.
            str(ATHLETE_1_ID): {
                "athlete_id": ATHLETE_1_ID,
                "count_present": 1,
                "count_absent": 0,
                "count_justified": 1,
                "count_late": 0,
                "count_injured": 0,
                "total_sessions": 2,
                "attendance_pct": 50.0,
                "avg_rubric_effort": 4.0,
                "avg_rubric_attitude": 5.0,
                "avg_rubric_technique": 3.0,
            },
            # Tarde cuenta como asistencia efectiva → 100 %.
            str(ATHLETE_2_ID): {
                "athlete_id": ATHLETE_2_ID,
                "count_present": 0,
                "count_absent": 0,
                "count_justified": 0,
                "count_late": 1,
                "count_injured": 0,
                "total_sessions": 1,
                "attendance_pct": 100.0,
                "avg_rubric_effort": 3.0,
                "avg_rubric_attitude": 3.0,
                "avg_rubric_technique": 4.0,
            },
            # Ausente: sin rúbrica, promedios en None.
            str(ATHLETE_3_ID): {
                "athlete_id": ATHLETE_3_ID,
                "count_present": 0,
                "count_absent": 1,
                "count_justified": 0,
                "count_late": 0,
                "count_injured": 0,
                "total_sessions": 1,
                "attendance_pct": 0.0,
                "avg_rubric_effort": None,
                "avg_rubric_attitude": None,
                "avg_rubric_technique": None,
            },
        },
        # Promedios solo sobre presentes/tarde: (6+4)/2, (4+3)/2, (5+3)/2, (3+4)/2.
        "avg_rpe": 5.0,
        "avg_rubric_effort": 3.5,
        "avg_rubric_attitude": 4.0,
        "avg_rubric_technique": 3.5,
        # Planificado = no canceladas (90 + 60); ejecutado = solo 6001.
        "total_minutes_planned": 150,
        "total_minutes_executed": 90,
        # 90 min / 60 / (30 días / 7) = 0,35 h/semana. El cociente en coma
        # flotante cae del lado alto (0,35000000000000003), así que
        # ``round(..., 1)`` da 0,4 y no 0,3: se fija el valor real, no el
        # aritméticamente "esperado".
        "avg_hours_per_week": 0.4,
        "technical_focus_counts": {FOCO_DESCENSO: 2, FOCO_RESISTENCIA: 1},
        "attendance_status_totals": {
            "presente": 1,
            "tarde": 1,
            "justificado": 1,
            "ausente": 1,
            "lesionado": 0,
        },
        "session_detail": [
            {
                "session_date": "2026-04-06",
                "start_time": "16:00:00",
                "technical_focus": FOCO_DESCENSO,
                "location": "Sede ficticia",
                "status": "executed",
                "present_count": 2,
                "attendee_total": 3,
            },
            {
                "session_date": "2026-04-13",
                "start_time": "16:00:00",
                "technical_focus": FOCO_RESISTENCIA,
                "location": "Sede ficticia",
                "status": "planned",
                "present_count": 0,
                "attendee_total": 0,
            },
            {
                "session_date": "2026-04-20",
                "start_time": "16:00:00",
                "technical_focus": FOCO_DESCENSO,
                "location": "Sede ficticia",
                "status": "cancelled",
                "present_count": 0,
                "attendee_total": 1,
            },
        ],
    }


async def test_el_informe_mensual_no_filtra_asistencias_archivadas(report_session):
    """Asimetría deliberada respecto del informe por entrenador (§3 nota 3).

    La fila archivada del 20 de abril sigue sumando en el mensual; si alguien
    "armoniza" ambos cálculos filtrando ``archived_at`` aquí, FR-031 se rompe
    y esta prueba lo señala en el sitio exacto.
    """
    metrics = await compute_monthly_metrics(report_session, CLUB_ID, YEAR, MONTH)

    assert metrics.attendance_status_totals["justificado"] == 1
    assert metrics.attendance_by_athlete[ATHLETE_1_ID].total_sessions == 2


async def test_la_sesion_codirigida_no_se_cuenta_dos_veces_en_el_mensual(
    report_session,
):
    """La sesión 6001 tiene dos entrenadores; el mensual la cuenta una vez.

    Es la contracara de la regla de §2: el fan-out vive solo en el informe
    por entrenador, jamás en el informe del club.
    """
    metrics = await compute_monthly_metrics(report_session, CLUB_ID, YEAR, MONTH)

    assert metrics.total_sessions_executed == 1
    assert len(metrics.session_detail) == 3


# ---------------------------------------------------------------------------
# 2. Encabezados de sección del documento (§9.2)
# ---------------------------------------------------------------------------


async def test_encabezados_de_seccion_del_informe_no_cambian(report_session):
    metrics = await compute_monthly_metrics(report_session, CLUB_ID, YEAR, MONTH)
    report = MonthlyReport(
        club_id=CLUB_ID,
        year=YEAR,
        month=MONTH,
        status=MonthlyReportStatus.DRAFT,
        metrics_snapshot=metrics.model_dump(mode="json"),
        narrative_blocks={
            "objetivo": {"final_text": "Texto ficticio del objetivo."},
        },
        competition_results=[],
        generated_by_user_id=COACH_A_ID,
        generated_at=datetime(YEAR, 5, 1, 9, 0, 0),
    )

    context = build_report_document_context(report, None)

    assert [
        (section["key"], section["title"]) for section in context["sections"]
    ] == SECCIONES_APROBADAS
    assert context["header"]["period_label"] == "Abril 2026"
    assert context["status"] == "draft"
    assert context["is_draft"] is True
    # Las cinco secciones sin texto siguen marcándose como pendientes, con
    # los mismos títulos: el banner de borrador no cambia de contenido.
    assert context["missing_sections"] == [
        title for key, title in SECCIONES_APROBADAS if key != "objetivo"
    ]
    # Las tablas derivadas del snapshot siguen poblándose igual.
    assert len(context["session_detail"]["rows"]) == 3
    assert context["session_detail"]["is_empty"] is False
    assert len(context["attendance_table"]["rows"]) == 3
    assert context["has_competition_results"] is False


async def test_la_firma_del_contexto_del_documento_no_cambia(report_session):
    """El conjunto de claves de nivel superior del contexto es cerrado."""
    report = MonthlyReport(
        club_id=CLUB_ID,
        year=YEAR,
        month=MONTH,
        status=MonthlyReportStatus.APPROVED,
        metrics_snapshot={},
        narrative_blocks={},
        competition_results=[],
        generated_by_user_id=COACH_A_ID,
        generated_at=datetime(YEAR, 5, 1, 9, 0, 0),
    )

    context = build_report_document_context(report, None)

    assert set(context) == {
        "header",
        "status",
        "is_draft",
        "sections",
        "missing_sections",
        "session_detail",
        "attendance_table",
        "competition_results",
        "competition_groups",
        "has_competition_results",
    }
    assert set(context["header"]) == {
        "project_name",
        "executing_entity",
        "report_responsible",
        "period_label",
    }
    assert context["is_draft"] is False
