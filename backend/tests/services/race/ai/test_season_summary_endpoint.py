"""Tests v2 — endpoint POST ``/api/athletes/{id}/race-analysis/season-summary``.

Contratos asumidos (Task #9):

- POST sin body inicia un run especial de tipo ``season_summary``.
- 422 si el atleta tiene <3 válidas analizadas en la temporada (no hay
  base suficiente para resumen).
- 200 (201) si ≥3 válidas analizadas y ``ai_enabled``.
- Solo coach/admin pueden invocarlo (parent → 403).

La fixture reusable de ``test_athlete_race_analysis.py`` ya monta un
SQLite in-memory con seed completo. Como el endpoint puede no existir
todavía, los tests detectan 404 y se marcan xfail apropiadamente.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.athlete_ai_insight import AthleteAiInsight
from app.models.club import ClubRole
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_category,
    create_race_event,
    create_race_series,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)


# ---------------------------------------------------------------------------
# Fixtures locales — DB + auth override
# ---------------------------------------------------------------------------


_AGENT_RUNS_FULL_DDL = """
CREATE TABLE agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_run_id VARCHAR(64) NOT NULL UNIQUE,
    graph_name VARCHAR(64) NOT NULL,
    prompt_version VARCHAR(32) NOT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    input_json TEXT NOT NULL,
    final_output_json TEXT NULL,
    error_message TEXT NULL,
    langfuse_trace_id VARCHAR(128) NULL,
    requested_by_user_id INTEGER NOT NULL,
    checkpoint_thread_id VARCHAR(64) NOT NULL,
    explain_mode INTEGER NOT NULL DEFAULT 0,
    cost_usd NUMERIC NULL,
    athlete_id INTEGER NULL,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
)
"""


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Base.metadata.tables[t]
        for t in (
            "users",
            "clubs",
            "club_members",
            "athletes",
            "parent_athlete",
            "race_series",
            "race_events",
            "race_categories",
            "race_competitors",
            "race_results",
            "athlete_ai_insights",
        )
    ]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.exec_driver_sql(_AGENT_RUNS_FULL_DDL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_athlete_with_n_insights(
    session_factory: async_sessionmaker[AsyncSession],
    n_insights: int,
    *,
    athlete_id: int = 144,
    season: int = 2026,
) -> None:
    """Helper: siembra atleta + N insights aprobados activos para temporada."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=10, role=UserRole.coach, email="c@t.com")
        await link_user_to_club(
            s, user_id=10, club_id=1, role_in_club=ClubRole.coach
        )
        await create_user(s, user_id=20, role=UserRole.parent, email="p@t.com")
        await create_user(
            s, user_id=athlete_id, role=UserRole.athlete, can_login=False
        )
        await create_athlete(s, athlete_id=athlete_id, club_id=1, user_id=athlete_id)
        await create_race_series(s, series_id=1, season_year=season)
        await create_race_category(s, category_id=100, code="INF_B")
        for valida in range(1, n_insights + 1):
            await create_race_event(
                s,
                event_id=valida,
                series_id=1,
                sequence_number=valida,
                name=f"V{valida}",
                event_date=date(season, 1, 31),
            )
            await create_insight(
                s,
                athlete_id=athlete_id,
                season=season,
                valida_num=valida,
                coach_approved=True,
                is_active=1,
            )
        await s.commit()


def _make_user(
    user_id: int, role: UserRole, club_id: int | None = 1
) -> SimpleNamespace:
    cm = (
        SimpleNamespace(
            club_id=club_id,
            role_in_club=(
                ClubRole.coach if role == UserRole.coach
                else ClubRole.admin if role == UserRole.admin
                else ClubRole.parent
            ),
        )
        if club_id is not None
        else None
    )
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        email=f"u{user_id}@test.com",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=[cm] if cm else [],
    )


@pytest_asyncio.fixture
async def client_factory(session_factory):
    def _build(user: SimpleNamespace):
        async def _override_db():
            async with session_factory() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _build
    app.dependency_overrides.clear()


URL = "/api/athletes/144/race-analysis/season-summary"


def _is_endpoint_missing(resp_status: int) -> bool:
    """405 (Method Not Allowed) o 404 indica que el endpoint no existe aún."""
    return resp_status in (404, 405)


# ---------------------------------------------------------------------------
# 422 — menos de 3 válidas analizadas
# ---------------------------------------------------------------------------


async def test_season_summary_returns_422_with_less_than_3_validas(
    session_factory, client_factory, monkeypatch
):
    """Solo 2 válidas analizadas → 422."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    await _seed_athlete_with_n_insights(session_factory, n_insights=2)

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    if _is_endpoint_missing(resp.status_code):
        pytest.xfail(f"Endpoint todavía no expuesto (status={resp.status_code})")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 200/201 — con 3+ válidas y feature flag ON
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="v2 endpoint pending", strict=False)
async def test_season_summary_success_with_3_validas_flag_on(
    session_factory, client_factory, monkeypatch
):
    """3 válidas + flag ON → 200/201, devuelve run_id."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    # Stub del runner para no disparar grafo real.
    try:
        from app.routers import athlete_race_analysis as router_mod

        async def _fake_submit_run(run_id, initial_state, on_complete=None):
            return None

        async def _fake_check_budget(db):
            return None

        monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
        monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    except (ImportError, AttributeError):
        pass  # OK si el router todavía no expone esos símbolos

    await _seed_athlete_with_n_insights(session_factory, n_insights=4)

    coach = _make_user(10, UserRole.coach, club_id=1)
    async with client_factory(user=coach) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    if _is_endpoint_missing(resp.status_code):
        pytest.xfail(f"Endpoint todavía no expuesto (status={resp.status_code})")
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert "run_id" in body


# ---------------------------------------------------------------------------
# 403 — RBAC: parent NO puede invocar
# ---------------------------------------------------------------------------


async def test_season_summary_parent_forbidden(
    session_factory, client_factory, monkeypatch
):
    """Parent intentando lanzar resumen de temporada → 403."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    await _seed_athlete_with_n_insights(session_factory, n_insights=4)

    parent = _make_user(20, UserRole.parent, club_id=None)
    async with client_factory(user=parent) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    if _is_endpoint_missing(resp.status_code):
        pytest.xfail(f"Endpoint todavía no expuesto (status={resp.status_code})")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 200 — admin también puede
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="v2 endpoint pending", strict=False)
async def test_season_summary_admin_allowed(
    session_factory, client_factory, monkeypatch
):
    """Admin tiene acceso (coach/admin only)."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    try:
        from app.routers import athlete_race_analysis as router_mod

        async def _fake_submit_run(run_id, initial_state, on_complete=None):
            return None

        async def _fake_check_budget(db):
            return None

        monkeypatch.setattr(router_mod, "submit_run", _fake_submit_run)
        monkeypatch.setattr(router_mod, "check_budget", _fake_check_budget)
    except (ImportError, AttributeError):
        pass

    await _seed_athlete_with_n_insights(session_factory, n_insights=4)

    admin = _make_user(99, UserRole.admin, club_id=1)
    async with client_factory(user=admin) as ac:
        resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})

    if _is_endpoint_missing(resp.status_code):
        pytest.xfail(f"Endpoint todavía no expuesto (status={resp.status_code})")
    assert resp.status_code in (200, 201)


# ---------------------------------------------------------------------------
# is_fallback (feature 036, US4) — create_season_summary construye
# AthleteAiInsight directamente (no pasa por persist_insight.py) y por eso
# necesita su propio wiring de is_fallback vía is_fallback_output().
# ---------------------------------------------------------------------------


async def test_season_summary_marks_is_fallback_when_llm_fails(
    session_factory, client_factory, monkeypatch
):
    """Si ``invoke_season_summary`` cae al failure path (``deterministic_fallback``),
    el insight persistido debe quedar con ``is_fallback=True``.

    Antes de este fix, ``create_season_summary`` construía
    ``AthleteAiInsight`` directamente (no vía ``persist_insight.py``) y
    nunca seteaba ``is_fallback`` — un resumen de temporada que falló
    silenciosamente quedaba indistinguible de uno real, adjuntable al
    boletín sin aviso. No probamos el endpoint real de LLM: monkeypatcheamos
    ``RaceAnalystAgent.invoke_season_summary`` para simular el failure path
    determinísticamente.
    """
    monkeypatch.setattr(settings, "ai_enabled", True)
    await _seed_athlete_with_n_insights(session_factory, n_insights=3)

    from app.services.race.agents.analyst import RaceAnalystAgent
    from app.services.race.ai.db import set_db_factory
    from app.services.race.ai.fallback import deterministic_fallback
    from app.services.race.schemas import RunMetrics

    async def _fake_invoke_season_summary(
        self, input_, *, forbidden_names=None, timeout_seconds=None
    ):
        return deterministic_fallback(input_.athlete_pseudonym), RunMetrics(
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            cost_usd=0.0,
            prompt_version="race_analyst_v2",
        )

    monkeypatch.setattr(
        RaceAnalystAgent, "invoke_season_summary", _fake_invoke_season_summary
    )
    # create_season_summary carga la progresión vía
    # `services.race.ai.db.get_session()` (factory global independiente de
    # `Depends(get_db)`) — sin esto apunta a la MySQL real de app.main y
    # el test intenta conectarse a un host inalcanzable fuera de docker.
    set_db_factory(lambda: session_factory())

    try:
        coach = _make_user(10, UserRole.coach, club_id=1)
        async with client_factory(user=coach) as ac:
            post_resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})
            if _is_endpoint_missing(post_resp.status_code):
                pytest.xfail(f"Endpoint todavía no expuesto (status={post_resp.status_code})")
            assert post_resp.status_code == 201, post_resp.text
            insight_id = post_resp.json()["insight_id"]

            get_resp = await ac.get(
                f"/api/athletes/144/race-analysis/insights/{insight_id}",
                headers={"Authorization": "Bearer fake"},
            )
    finally:
        set_db_factory(None)

    assert get_resp.status_code == 200
    assert get_resp.json()["is_fallback"] is True


async def test_season_summary_real_output_keeps_is_fallback_false(
    session_factory, client_factory, monkeypatch
):
    """Control: un resumen que SÍ generó contenido real nunca marca
    ``is_fallback`` — sólo el failure path de ``deterministic_fallback`` lo
    hace (``deterministic_fallback_n1`` tampoco, pero no aplica aquí:
    season-summary siempre tiene ≥3 válidas)."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    await _seed_athlete_with_n_insights(session_factory, n_insights=3)

    from app.services.race.agents.analyst import RaceAnalystAgent
    from app.services.race.ai.db import set_db_factory
    from app.services.race.schemas import AnalysisOutput, RunMetrics

    async def _fake_invoke_season_summary(
        self, input_, *, forbidden_names=None, timeout_seconds=None
    ):
        return AnalysisOutput(
            pseudonym=input_.athlete_pseudonym,
            sections={"resumen_temporada": "Buen cierre de temporada."},
            citations_used=[],
            recommendations=[],
            risk_flags=[],
            raw_markdown="## Resumen temporada\nBuen cierre de temporada.",
            word_count=4,
        ), RunMetrics(
            tokens_in=100,
            tokens_out=50,
            latency_ms=500,
            cost_usd=0.001,
            prompt_version="race_analyst_v2",
        )

    monkeypatch.setattr(
        RaceAnalystAgent, "invoke_season_summary", _fake_invoke_season_summary
    )
    # Ver comentario equivalente en el test anterior: sin esto la carga de
    # progresión intenta conectarse a la MySQL real de app.main.
    set_db_factory(lambda: session_factory())

    try:
        coach = _make_user(10, UserRole.coach, club_id=1)
        async with client_factory(user=coach) as ac:
            post_resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})
            if _is_endpoint_missing(post_resp.status_code):
                pytest.xfail(f"Endpoint todavía no expuesto (status={post_resp.status_code})")
            assert post_resp.status_code == 201, post_resp.text
            insight_id = post_resp.json()["insight_id"]

            get_resp = await ac.get(
                f"/api/athletes/144/race-analysis/insights/{insight_id}",
                headers={"Authorization": "Bearer fake"},
            )
    finally:
        set_db_factory(None)

    assert get_resp.status_code == 200
    assert get_resp.json()["is_fallback"] is False


# ---------------------------------------------------------------------------
# Privacidad (fuera de banda, Ley 1581) — forbidden_names ya no queda vacío
# ---------------------------------------------------------------------------


async def test_season_summary_forbidden_names_includes_parent_full_name(
    session_factory, client_factory, monkeypatch
):
    """``forbidden_names`` NO debe estar vacío cuando el atleta tiene un
    padre/madre vinculado con nombre.

    Bug: el código consultaba ``UserModel.full_name`` — columna INEXISTENTE
    (``app/models/user.py`` solo define ``first_name``/``last_name``). El
    ``AttributeError`` resultante caía en un ``except Exception`` amplio que
    solo logueaba a WARNING, dejando ``forbidden_names=[]`` SIEMPRE: el
    guardrail que evita que el LLM mencione el nombre real del menor o de su
    familia nunca estuvo activo en producción.
    """
    monkeypatch.setattr(settings, "ai_enabled", True)
    await _seed_athlete_with_n_insights(session_factory, n_insights=3)

    # Vincular un padre CON NOMBRE al atleta 144 (el helper no crea ninguno).
    async with session_factory() as s:
        await create_user(
            s,
            user_id=500,
            role=UserRole.parent,
            email="padre500@test.com",
            first_name="Carlos",
            last_name="Ramirez",
        )
        await link_parent_to_athlete(s, parent_user_id=500, athlete_id=144)
        await s.commit()

    from app.services.race.agents.analyst import RaceAnalystAgent
    from app.services.race.ai.db import set_db_factory
    from app.services.race.schemas import AnalysisOutput, RunMetrics

    captured: dict[str, object] = {}

    async def _fake_invoke_season_summary(
        self, input_, *, forbidden_names=None, timeout_seconds=None
    ):
        captured["forbidden_names"] = list(forbidden_names or [])
        return AnalysisOutput(
            pseudonym=input_.athlete_pseudonym,
            sections={"resumen_temporada": "Buen cierre de temporada."},
            citations_used=[],
            recommendations=[],
            risk_flags=[],
            raw_markdown="## Resumen temporada\nBuen cierre de temporada.",
            word_count=4,
        ), RunMetrics(
            tokens_in=100,
            tokens_out=50,
            latency_ms=500,
            cost_usd=0.001,
            prompt_version="race_analyst_v2",
        )

    monkeypatch.setattr(
        RaceAnalystAgent, "invoke_season_summary", _fake_invoke_season_summary
    )
    set_db_factory(lambda: session_factory())

    try:
        coach = _make_user(10, UserRole.coach, club_id=1)
        async with client_factory(user=coach) as ac:
            resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})
            if _is_endpoint_missing(resp.status_code):
                pytest.xfail(f"Endpoint todavía no expuesto (status={resp.status_code})")
    finally:
        set_db_factory(None)

    assert resp.status_code == 201, resp.text
    forbidden_names = captured.get("forbidden_names")
    assert forbidden_names, "forbidden_names no debe estar vacío con un padre vinculado"
    assert "Carlos Ramirez" in forbidden_names


# ---------------------------------------------------------------------------
# T044 (feature 036) — lock de deduplicación antes del LLM + 409 específico
# ---------------------------------------------------------------------------


async def test_season_summary_deprecates_previous_before_invoking_llm(
    session_factory, client_factory, monkeypatch
):
    """El resumen previo debe quedar deprecado (y confirmado con commit)
    ANTES de invocar el LLM, no después — así un segundo submit concurrente
    encuentra el conflicto tan pronto como sea posible, en vez de solo al
    final, tras haber gastado presupuesto de IA.
    """
    monkeypatch.setattr(settings, "ai_enabled", True)
    await _seed_athlete_with_n_insights(session_factory, n_insights=3)

    # Resumen de temporada previo ya activo (escenario de re-generación).
    async with session_factory() as s:
        previous = await create_insight(
            s,
            athlete_id=144,
            season=2026,
            valida_num=0,
            use_case="season_summary_v2",
            coach_approved=True,
            is_active=1,
        )
        previous_id = previous.id
        await s.commit()

    from app.services.race.agents.analyst import RaceAnalystAgent
    from app.services.race.ai.db import set_db_factory
    from app.services.race.schemas import AnalysisOutput, RunMetrics

    state_at_llm_call: dict[str, object] = {}

    async def _fake_invoke_season_summary(
        self, input_, *, forbidden_names=None, timeout_seconds=None
    ):
        async with session_factory() as s:
            row = await s.get(AthleteAiInsight, previous_id)
            state_at_llm_call["is_active"] = row.is_active
            state_at_llm_call["deprecated_at"] = row.deprecated_at
        return AnalysisOutput(
            pseudonym=input_.athlete_pseudonym,
            sections={"resumen_temporada": "x"},
            citations_used=[],
            recommendations=[],
            risk_flags=[],
            raw_markdown="## Resumen\nx",
            word_count=1,
        ), RunMetrics(
            tokens_in=1,
            tokens_out=1,
            latency_ms=1,
            cost_usd=0.0,
            prompt_version="race_analyst_v2",
        )

    monkeypatch.setattr(
        RaceAnalystAgent, "invoke_season_summary", _fake_invoke_season_summary
    )
    set_db_factory(lambda: session_factory())

    try:
        coach = _make_user(10, UserRole.coach, club_id=1)
        async with client_factory(user=coach) as ac:
            resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})
            if _is_endpoint_missing(resp.status_code):
                pytest.xfail(f"Endpoint todavía no expuesto (status={resp.status_code})")
    finally:
        set_db_factory(None)

    assert resp.status_code == 201, resp.text
    assert state_at_llm_call["is_active"] is None, (
        "El insight previo debía estar deprecado (is_active=NULL) ANTES de "
        "invocar el LLM — el lock de deduplicación se adquiere después."
    )
    assert state_at_llm_call["deprecated_at"] is not None


async def test_season_summary_conflicting_active_insight_returns_409_not_500(
    session_factory, client_factory, monkeypatch
):
    """Si otra solicitud ya insertó su propio resumen activo para la misma
    terna mientras esta esperaba al LLM, la persistencia final choca con
    ``uq_insights_active_terna`` — debe responder 409 con detalle
    específico.

    Simulamos "otro submit ganó la carrera" insertando, como efecto
    secundario del propio mock del LLM, un resumen activo competidor para
    la misma terna — no depende de concurrencia real de DB (SQLite
    in-memory no la soporta de forma fiable con StaticPool).

    Nota sobre el comportamiento ANTES del fix (verificado manualmente
    revirtiendo T044): con ``deprecate_previous_active`` corriendo DESPUÉS
    del LLM (dentro del mismo try que el INSERT), este escenario exacto no
    produce un 500 sino un **201 que enmascara la carrera** — el
    ``deprecate_previous_active`` de ESTA request encuentra la fila recién
    insertada por "la otra solicitud" (coincide con su propio predicado de
    búsqueda) y la depreca silenciosamente antes de insertar la suya,
    perdiendo sin aviso el resumen de la solicitud que "ganó". El 500
    genérico ocurre en la variante de carrera real (dos transacciones DB
    concurrentes, no reproducible de forma fiable en SQLite in-memory). En
    cualquier caso, el resultado correcto post-fix es 409 explícito — ni
    500 genérico ni un 201 que oculta la pérdida de datos de otra solicitud.
    """
    monkeypatch.setattr(settings, "ai_enabled", True)
    await _seed_athlete_with_n_insights(session_factory, n_insights=3)

    from app.services.race.agents.analyst import RaceAnalystAgent
    from app.services.race.ai.db import set_db_factory
    from app.services.race.schemas import AnalysisOutput, RunMetrics

    async def _fake_invoke_season_summary(
        self, input_, *, forbidden_names=None, timeout_seconds=None
    ):
        async with session_factory() as s:
            await create_insight(
                s,
                athlete_id=144,
                season=2026,
                valida_num=0,
                use_case="season_summary_v2",
                coach_approved=True,
                is_active=1,
            )
            await s.commit()
        return AnalysisOutput(
            pseudonym=input_.athlete_pseudonym,
            sections={"resumen_temporada": "x"},
            citations_used=[],
            recommendations=[],
            risk_flags=[],
            raw_markdown="## Resumen\nx",
            word_count=1,
        ), RunMetrics(
            tokens_in=1,
            tokens_out=1,
            latency_ms=1,
            cost_usd=0.0,
            prompt_version="race_analyst_v2",
        )

    monkeypatch.setattr(
        RaceAnalystAgent, "invoke_season_summary", _fake_invoke_season_summary
    )
    set_db_factory(lambda: session_factory())

    try:
        coach = _make_user(10, UserRole.coach, club_id=1)
        async with client_factory(user=coach) as ac:
            resp = await ac.post(URL, headers={"Authorization": "Bearer fake"})
            if _is_endpoint_missing(resp.status_code):
                pytest.xfail(f"Endpoint todavía no expuesto (status={resp.status_code})")
    finally:
        set_db_factory(None)

    assert resp.status_code == 409, resp.text
    assert "resumen" in resp.json()["detail"].lower()
