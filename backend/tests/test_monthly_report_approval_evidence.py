"""T071 — evidencia de aprobación del Informe Técnico Mensual sobrevive a la
regeneración (FR-010, US5 AS4, contracts/concurrency-and-approvals.md §5).

Defecto original (§5.1): ``update_report_blocks`` solo movía ``status`` a
``approved`` sin dejar ningún rastro de quién aprobó ni cuándo, y
``generate_monthly_report(force_regenerate=True)`` sobreescribía
``generated_by_user_id`` sin conservar la evidencia de una aprobación previa
— aprobar como coach A y luego regenerar como coach B borraba toda huella de
que A lo había aprobado. Después de esta tarea, el coach debe poder ver
"generado por B" **y** "previamente aprobado por A el <fecha>" a la vez,
con ambas acciones en el historial de auditoría.

Vía offline: motor sqlite in-memory propio con un subconjunto explícito de
tablas (patrón de ``tests/routers/test_audit_log_api.py`` /
``tests/test_session_coaches.py``, reutilizando ``tests/helpers/audit_tables.py``
y el escenario compartido ``tests.fixtures.two_coaches``). NO usa la fixture
``client`` de ``tests/conftest.py`` (requiere MySQL real, no disponible aquí).

Cobertura (numeración de
``specs/041-multi-coach-governance/contracts/concurrency-and-approvals.md``
§14, líneas 569-585):

- Test 14: regenerar tras aprobar preserva la evidencia de A (regresión).
- Test 15: regenerar un reporte YA en borrador no vacía un
  ``previous_approved_*`` preexistente.
- Test 16: aprobar → regenerar → aprobar → regenerar dos veces siempre deja
  la aprobación superada MÁS RECIENTE, nunca la primera.
- Test 17: aprobar escribe ``approved_by_user_id``/``approved_at``/
  ``updated_by_user_id`` (hoy no hay atribución alguna).
- Test 18: la regeneración audita ``update`` + ``unapprove`` bajo un mismo
  ``request_id``, y ningún ``diff_json`` sale de ``VALUE_ALLOWLIST``.
- Test 19: ``previous_approved_*`` está ausente de la proyección para padres
  de ``MonthlyReportRead`` (nivel HTTP, con ``app.dependency_overrides``).

Test 20 (DOCX/PDF byte-idéntico, SC-009) vive en
``backend/tests/test_monthly_report_unchanged.py`` (T082) — no se duplica
aquí; ver la nota FR-031 al final de este módulo.

Ningún dato corresponde a una persona real (club, coaches, padre y atleta son
los ficticios de ``tests.fixtures.two_coaches`` — Ley 1581).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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
from app.models.audit_log import AuditLog
from app.models.training_session import MonthlyReport, MonthlyReportStatus
from app.models.user import User
from app.services.audit import AuditEntityType, VALUE_ALLOWLIST
from app.services.request_context import request_id_scope
from app.services.training.reports import generate_monthly_report, update_report_blocks

from tests.fixtures.two_coaches import _TABLES as _TWO_COACHES_TABLES
from tests.fixtures.two_coaches import TwoCoachesScenario, seed_two_coaches

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Motor con el subconjunto de tablas que este módulo necesita
#
# `generate_monthly_report` llama a `compute_monthly_metrics` (necesita
# `training_sessions`/`session_attendance` — vacías está bien, solo deben
# existir para que el SELECT no reviente) y a `build_competition_results`,
# que degrada limpio a `[]` ante cualquier excepción de BD (incluida "no such
# table" en sqlite) — por eso las tablas `race_*` NO hacen falta aquí.
#
# `dict.fromkeys(...)` deduplica: `_TWO_COACHES_TABLES` ya incluye
# `AUDIT_TABLES` completo, así que no se puede repetir un nombre literal (ver
# la trampa documentada en `tests/helpers/audit_tables.py`).
# ---------------------------------------------------------------------------

_TABLES = tuple(
    dict.fromkeys((*_TWO_COACHES_TABLES, "training_sessions", "session_attendance", "monthly_reports"))
)

# Período cerrado: el mes calendario anterior al de hoy, calculado en
# ejecución (nunca hardcodeado — `_validate_period` rechaza el mes en curso y
# cualquier mes futuro).
_TODAY = date.today()
if _TODAY.month == 1:
    YEAR, MONTH = _TODAY.year - 1, 12
else:
    YEAR, MONTH = _TODAY.year, _TODAY.month - 1


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
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def scenario(
    session_factory: async_sessionmaker[AsyncSession],
) -> TwoCoachesScenario:
    async with session_factory() as session:
        yield await seed_two_coaches(session)


@pytest_asyncio.fixture
async def client_factory(session_factory: async_sessionmaker[AsyncSession], scenario: TwoCoachesScenario):
    """Fábrica ``make_client(user_id)`` — mismo patrón que
    ``tests/test_session_coaches.py::client_factory``, para el único test que
    necesita el router real (proyección de padres, test 19)."""

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
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.clear()

    return make_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_user(session: AsyncSession, user_id: int) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one()


async def _load_report(session: AsyncSession, club_id: int, year: int, month: int) -> MonthlyReport:
    result = await session.execute(
        select(MonthlyReport).where(
            MonthlyReport.club_id == club_id,
            MonthlyReport.year == year,
            MonthlyReport.month == month,
        )
    )
    return result.scalar_one()


async def _audit_rows_for(session: AsyncSession, entity_id: int) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.entity_type == AuditEntityType.monthly_report.value,
            AuditLog.entity_id == entity_id,
        )
        .order_by(AuditLog.id.asc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Test 17 — aprobar escribe approved_by_user_id / approved_at / updated_by_user_id
# ---------------------------------------------------------------------------


class TestApprovalWritesAttribution:
    async def test_aprobar_persiste_approved_by_approved_at_y_updated_by(
        self, scenario: TwoCoachesScenario
    ) -> None:
        session = scenario.session
        coach_a = await _load_user(session, scenario.coach_a_user_id)

        with request_id_scope():
            await generate_monthly_report(
                db=session,
                club_id=scenario.club_id,
                year=YEAR,
                month=MONTH,
                generator_user=coach_a,
                force_regenerate=False,
            )

        before = datetime.now(timezone.utc)
        with request_id_scope():
            report = await update_report_blocks(
                db=session,
                club_id=scenario.club_id,
                year=YEAR,
                month=MONTH,
                blocks={},
                new_status=MonthlyReportStatus.APPROVED,
                editor_user=coach_a,
            )
        after = datetime.now(timezone.utc)

        assert report.status == MonthlyReportStatus.APPROVED
        assert report.approved_by_user_id == coach_a.id
        assert report.approved_at is not None
        assert before <= report.approved_at <= after
        assert report.updated_by_user_id == coach_a.id
        assert report.updated_at is not None


# ---------------------------------------------------------------------------
# Test 14 — regresión: regenerar tras aprobar preserva la evidencia de A
# ---------------------------------------------------------------------------


class TestRegeneratePreservesApprovalEvidence:
    async def test_regenerar_tras_aprobar_preserva_evidencia_de_a_como_generador_b(
        self, scenario: TwoCoachesScenario
    ) -> None:
        """Test 14 del contrato (regresión — falla contra el código previo a
        esta tarea; ver la verificación manual descrita en el reporte de
        entrega). Aprobar como coach A y luego regenerar con
        ``force_regenerate=true`` como coach B no debe borrar el rastro de
        que A ya lo había aprobado."""
        session = scenario.session
        coach_a = await _load_user(session, scenario.coach_a_user_id)
        coach_b = await _load_user(session, scenario.coach_b_user_id)

        with request_id_scope():
            await generate_monthly_report(
                db=session,
                club_id=scenario.club_id,
                year=YEAR,
                month=MONTH,
                generator_user=coach_a,
                force_regenerate=False,
            )
        with request_id_scope():
            await update_report_blocks(
                db=session,
                club_id=scenario.club_id,
                year=YEAR,
                month=MONTH,
                blocks={},
                new_status=MonthlyReportStatus.APPROVED,
                editor_user=coach_a,
            )

        approved_report = await _load_report(session, scenario.club_id, YEAR, MONTH)
        approved_at_a = approved_report.approved_at
        assert approved_report.approved_by_user_id == coach_a.id  # sanity: A sí aprobó
        assert approved_at_a is not None

        with request_id_scope():
            regenerated = await generate_monthly_report(
                db=session,
                club_id=scenario.club_id,
                year=YEAR,
                month=MONTH,
                generator_user=coach_b,
                force_regenerate=True,
            )

        assert regenerated.generated_by_user_id == coach_b.id
        assert regenerated.status == MonthlyReportStatus.DRAFT
        assert regenerated.approved_by_user_id is None
        assert regenerated.approved_at is None
        assert regenerated.previous_approved_by_user_id == coach_a.id
        assert regenerated.previous_approved_at == approved_at_a
        assert regenerated.updated_by_user_id == coach_b.id

    async def test_regenerar_un_borrador_no_vacia_un_previous_approved_preexistente(
        self, scenario: TwoCoachesScenario
    ) -> None:
        """Test 15 del contrato: una vez que `previous_approved_*` guarda la
        evidencia de A, regenerar de nuevo (ahora el reporte YA está en
        borrador, `approved_by_user_id` ya es None) no debe vaciarlo."""
        session = scenario.session
        coach_a = await _load_user(session, scenario.coach_a_user_id)
        coach_b = await _load_user(session, scenario.coach_b_user_id)

        with request_id_scope():
            await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_a, force_regenerate=False,
            )
        with request_id_scope():
            await update_report_blocks(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                blocks={}, new_status=MonthlyReportStatus.APPROVED, editor_user=coach_a,
            )
        with request_id_scope():
            first_regen = await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_b, force_regenerate=True,
            )
        assert first_regen.previous_approved_by_user_id == coach_a.id
        previous_approved_at_snapshot = first_regen.previous_approved_at

        # Reporte YA en borrador (approved_by_user_id is None) — regenerar de
        # nuevo no debe tocar previous_approved_*.
        assert first_regen.approved_by_user_id is None
        with request_id_scope():
            second_regen = await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_b, force_regenerate=True,
            )

        assert second_regen.previous_approved_by_user_id == coach_a.id
        assert second_regen.previous_approved_at == previous_approved_at_snapshot

    async def test_previous_approved_guarda_siempre_la_aprobacion_superada_mas_reciente(
        self, scenario: TwoCoachesScenario
    ) -> None:
        """Test 16 del contrato: aprobar → regenerar → aprobar → regenerar
        dos veces. `previous_approved_*` debe terminar apuntando a la
        SEGUNDA aprobación superada (coach B), nunca a la primera (coach A)."""
        session = scenario.session
        coach_a = await _load_user(session, scenario.coach_a_user_id)
        coach_b = await _load_user(session, scenario.coach_b_user_id)

        with request_id_scope():
            await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_a, force_regenerate=False,
            )
        with request_id_scope():
            await update_report_blocks(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                blocks={}, new_status=MonthlyReportStatus.APPROVED, editor_user=coach_a,
            )
        with request_id_scope():
            await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_b, force_regenerate=True,
            )
        # Ahora aprueba B (segunda aprobación, distinta de la de A).
        with request_id_scope():
            second_approval = await update_report_blocks(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                blocks={}, new_status=MonthlyReportStatus.APPROVED, editor_user=coach_b,
            )
        approved_at_b = second_approval.approved_at
        assert second_approval.approved_by_user_id == coach_b.id
        assert approved_at_b != None  # noqa: E711 — comparación explícita, no `is`

        with request_id_scope():
            final_regen = await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_a, force_regenerate=True,
            )

        assert final_regen.previous_approved_by_user_id == coach_b.id
        assert final_regen.previous_approved_at == approved_at_b
        assert final_regen.previous_approved_by_user_id != coach_a.id


# ---------------------------------------------------------------------------
# Test 18 — auditoría: update + unapprove comparten request_id; VALUE_ALLOWLIST
# ---------------------------------------------------------------------------


class TestRegenerateAudit:
    async def test_regenerar_audita_update_y_unapprove_bajo_un_mismo_request_id(
        self, scenario: TwoCoachesScenario
    ) -> None:
        session = scenario.session
        coach_a = await _load_user(session, scenario.coach_a_user_id)
        coach_b = await _load_user(session, scenario.coach_b_user_id)

        with request_id_scope():
            report = await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_a, force_regenerate=False,
            )
        with request_id_scope():
            await update_report_blocks(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                blocks={}, new_status=MonthlyReportStatus.APPROVED, editor_user=coach_a,
            )

        with request_id_scope() as regen_request_id:
            await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_b, force_regenerate=True,
            )

        all_rows = await _audit_rows_for(session, report.id)
        regen_rows = [r for r in all_rows if r.request_id == regen_request_id]

        assert {r.action.value if hasattr(r.action, "value") else r.action for r in regen_rows} == {
            "update",
            "unapprove",
        }
        assert len(regen_rows) == 2

        allowed = VALUE_ALLOWLIST[AuditEntityType.monthly_report]
        for row in all_rows:
            if not row.diff_json:
                continue
            offending = set(row.diff_json.keys()) - allowed
            assert not offending, (
                f"diff_json de la fila action={row.action} incluye claves fuera de "
                f"VALUE_ALLOWLIST['monthly_report']: {offending}"
            )

    async def test_aprobar_sin_regenerar_no_emite_unapprove(
        self, scenario: TwoCoachesScenario
    ) -> None:
        """Control negativo: solo el camino de `force_regenerate=true` sobre
        un reporte ya aprobado debe emitir `unapprove`. Aprobar de cero no."""
        session = scenario.session
        coach_a = await _load_user(session, scenario.coach_a_user_id)

        with request_id_scope():
            report = await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_a, force_regenerate=False,
            )
        with request_id_scope():
            await update_report_blocks(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                blocks={}, new_status=MonthlyReportStatus.APPROVED, editor_user=coach_a,
            )

        rows = await _audit_rows_for(session, report.id)
        actions = [r.action.value if hasattr(r.action, "value") else r.action for r in rows]
        assert "unapprove" not in actions
        assert "approve" in actions


# ---------------------------------------------------------------------------
# Test 19 — previous_approved_* ausente de la proyección para padres
# ---------------------------------------------------------------------------


class TestParentProjectionStripsSupersededApproval:
    async def test_padre_no_recibe_previous_approved_pero_coach_si(
        self,
        scenario: TwoCoachesScenario,
        client_factory,
    ) -> None:
        session = scenario.session
        coach_a = await _load_user(session, scenario.coach_a_user_id)
        coach_b = await _load_user(session, scenario.coach_b_user_id)

        with request_id_scope():
            await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_a, force_regenerate=False,
            )
        with request_id_scope():
            await update_report_blocks(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                blocks={}, new_status=MonthlyReportStatus.APPROVED, editor_user=coach_a,
            )
        with request_id_scope():
            await generate_monthly_report(
                db=session, club_id=scenario.club_id, year=YEAR, month=MONTH,
                generator_user=coach_b, force_regenerate=True,
            )
        await session.commit()

        path = f"/api/clubs/{scenario.club_id}/monthly-reports/{YEAR}/{MONTH}"

        async with client_factory(scenario.coach_a_user_id) as coach_client:
            coach_resp = await coach_client.get(path)
        assert coach_resp.status_code == 200, coach_resp.text
        coach_body = coach_resp.json()
        assert coach_body["previous_approved_by"] == {
            "user_id": coach_a.id,
            "display_name": coach_a.display_name,
        }
        assert coach_body["previous_approved_at"] is not None
        assert coach_body["generated_by"]["user_id"] == coach_b.id

        async with client_factory(scenario.parent_user_id) as parent_client:
            parent_resp = await parent_client.get(path)
        assert parent_resp.status_code == 200, parent_resp.text
        parent_body = parent_resp.json()
        assert parent_body["previous_approved_by"] is None
        assert parent_body["previous_approved_at"] is None


# ---------------------------------------------------------------------------
# Nota FR-031 (no es un test — documentación de alcance)
# ---------------------------------------------------------------------------
#
# Esta tarea (T071) solo agrega atribución/evidencia de aprobación alrededor
# del reporte mensual: nuevas columnas de auditoría y los campos ActorRef de
# la respuesta. NINGUNA línea de `compute_monthly_metrics`,
# `build_competition_results`, ni de la construcción de `metrics_snapshot`/
# `narrative_blocks`/`competition_results` fue tocada — se verificó con
# `git diff` que los únicos cambios en `reports.py` están dentro del bloque
# `if existing is not None and force_regenerate:` (asignaciones de
# `approved_*`/`previous_approved_*`/`updated_*` y el audit) y dentro de
# `update_report_blocks` (mismo tipo de asignaciones tras aprobar). El guard
# byte-a-byte del DOCX/PDF (SC-009, test 20 del contrato) vive en
# `backend/tests/test_monthly_report_unchanged.py` (T082) y no se duplica
# aquí.
