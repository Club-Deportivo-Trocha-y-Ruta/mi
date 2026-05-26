"""Invariantes v2 — Task #24 (QA paralelo a Task #23 fastapi-architect).

Cubre los contratos críticos que la implementación v2 debe respetar:

1. ``athlete_age`` se inyecta correctamente en ``initial_state`` y llega
   al nodo ``analyst_agent`` sin caer al fallback silencioso (=12).
2. El nodo ``analyst_agent._resolve_age`` debe loggear ``WARNING`` cuando
   ``state["athlete_age"]`` falta o está fuera de rango — la regresión
   silenciosa (loggear NADA y devolver 12) está PROHIBIDA.
3. El nodo ``load_race_data`` enriquece cada ``full_season_results`` con
   ``gap_to_winner_ms`` y ``gap_pct`` reales (no ``None``) cuando hay
   tiempo de ganador conocido en el mismo ``event_id``.
4. **Privacidad CRÍTICA**: el endpoint ``GET /insights/{id}`` jamás debe
   exponer ``competitor_id`` de TERCEROS (otros menores TyR) en el JSON
   de respuesta — ni en el snapshot tipado, ni anidado en
   ``metrics_snapshot`` legacy, ni en ningún nivel del payload.
5. Defensa en profundidad: aunque un snapshot legacy persistido siga
   conteniendo ``competitor_id`` en disco, la capa de presentación
   (router) debe limpiarlo antes de serializar.
6. Guardrails ``athlete_age`` kwarg — ``Guardrails(athlete_age=N)`` rechaza
   outputs que contradicen la edad real ("tiene 12 años" cuando age=14).
   PENDIENTE en Task #23; tests marcados xfail.

Estrategia
----------
- Mocks aislados (FakeAsyncSession + FakeAnalystAgent) para no tocar DB
  real ni Gemini.
- Para los tests de Guardrails dependientes de Task #23, usamos
  ``pytest.mark.xfail(strict=False)`` con razón explícita; cuando
  fastapi-architect entregue la kwarg, los tests pasarán automáticamente
  sin que el módulo tenga que editarse.
- Los tests de privacidad usan ``assert_no_keys_recursively`` (copiado
  del módulo de privacidad de ``test_athlete_race_analysis_privacy.py``)
  para barrer recursivamente el JSON y fallar con el path JSONPath del
  hallazgo.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator

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

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.club import ClubRole
from app.models.user import UserRole
from app.services.ai.guardrails import Guardrails
from app.services.race.ai.nodes import load_race_data as load_race_data_mod
from app.services.race.ai.nodes.analyst_agent import _resolve_age, analyst_agent

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_insight,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_user_to_club,
)
from tests.services.race.ai.conftest import (
    FakeAnalystAgent,
    make_analysis_output,
    make_zero_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FORBIDDEN_FOREIGN_KEYS = {
    "competitor_id",
    "athlete_id",
    "generated_by_user_id",
    "requested_by_user_id",
    "agent_run_id",
}


def _assert_no_keys_recursively(
    payload: Any,
    forbidden: set[str],
    path: str = "$",
) -> None:
    """Falla si alguna key prohibida aparece a cualquier nivel del payload.

    Usado para validar la defensa de privacidad: ``competitor_id`` de
    terceros no debe filtrarse ni en el JSON top-level ni anidado en
    ``metrics_snapshot``/``podium_gap``/etc.
    """
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in forbidden:
                raise AssertionError(
                    f"Key prohibida '{k}' detectada en {path}.{k}. "
                    f"Privacidad violada: terceros menores expuestos. "
                    f"value={v!r}"
                )
            _assert_no_keys_recursively(v, forbidden, path=f"{path}.{k}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _assert_no_keys_recursively(item, forbidden, path=f"{path}[{i}]")


# ---------------------------------------------------------------------------
# Bloque 1 — athlete_age en initial_state
# ---------------------------------------------------------------------------


class _RecordingAge:
    """Agente que captura la edad propagada al construir AnalysisInput.

    Lee ``input_.age`` (definido en :class:`AnalysisInput`) para verificar
    que ``_resolve_age`` propagó el valor correcto desde el state.
    """

    def __init__(self) -> None:
        self.captured_ages: list[int] = []

    async def invoke(self, input_: Any):
        self.captured_ages.append(input_.age)
        return make_analysis_output(), make_zero_metrics("race_analyst_v1")


@pytest.mark.asyncio
async def test_athlete_age_in_initial_state_flows_to_analyst_input():
    """Si state["athlete_age"]=14, el nodo analyst_agent v1 construye un
    AnalysisInput con age=14 (no el fallback 12)."""
    agent = _RecordingAge()
    state = {
        "athlete_id": 1,
        "season": 2026,
        "athlete_age": 14,
        "ltad_group": "juvenil",
        "anonymized_data": {"pseudonym": "AzulZorro"},
        "metrics": {"progression": []},
        "podium_context": {},
        "principles": [],
        "memory": [],
        "_analyst_agent": agent,
    }

    await analyst_agent(state)

    assert agent.captured_ages == [14], (
        "Regresión Fix 1: la edad en el state (14) no llegó al "
        f"AnalysisInput. captured={agent.captured_ages!r}"
    )


# ---------------------------------------------------------------------------
# Bloque 2 — no silent fallback for missing athlete_age
# ---------------------------------------------------------------------------


def test_resolve_age_logs_warning_when_missing(caplog):
    """Si state no trae athlete_age, _resolve_age devuelve 12 pero
    DEBE loggear un WARNING — el silencio es la regresión que motivó Fix 1.

    Por qué: en la regresión original el grafo recibía el atleta sin edad,
    asumía 12 sin avisar al equipo, y el LLM emitía recomendaciones para
    bambino sobre un juvenil. Hoy el warning permite detectarlo en
    Langfuse/Render logs.
    """
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.services.race.ai.nodes.analyst_agent"):
        result = _resolve_age({})

    assert result == 12  # fallback explícito
    # Confirmar que se loggeó algo informativo sobre la ausencia.
    matching = [
        r for r in caplog.records
        if "athlete_age" in r.getMessage()
        and "fallback" in r.getMessage().lower()
    ]
    assert matching, (
        "No se loggeó WARNING sobre athlete_age ausente. La regresión "
        "silenciosa está prohibida. Records observados: "
        f"{[r.getMessage() for r in caplog.records]!r}"
    )


def test_resolve_age_logs_warning_when_out_of_range(caplog):
    """Si athlete_age viene fuera de [6, 20], se aplica fallback con warning."""
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.services.race.ai.nodes.analyst_agent"):
        assert _resolve_age({"athlete_age": 50}) == 12
        assert _resolve_age({"athlete_age": 3}) == 12

    age_warnings = [
        r for r in caplog.records
        if "athlete_age" in r.getMessage()
    ]
    assert len(age_warnings) >= 2, (
        "Se esperaba un warning por cada llamada con edad fuera de rango. "
        f"Observados: {len(age_warnings)} warnings."
    )


def test_resolve_age_returns_value_silently_when_valid(caplog):
    """Cuando state trae edad válida (6..20), NO debe loggear warning."""
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.services.race.ai.nodes.analyst_agent"):
        assert _resolve_age({"athlete_age": 14}) == 14

    age_warnings = [
        r for r in caplog.records if "athlete_age" in r.getMessage()
    ]
    assert age_warnings == [], (
        "athlete_age=14 es válido; no debería generar warning. "
        f"Observados: {[r.getMessage() for r in age_warnings]!r}"
    )


# ---------------------------------------------------------------------------
# Bloque 3 — gap_to_winner_ms y gap_pct calculados en load_race_data
# ---------------------------------------------------------------------------


class _FakeRaceResult:
    """Replica mínimo del ORM RaceResult para tests de load_race_data."""

    def __init__(
        self,
        *,
        id: int,
        event_id: int,
        category_id: int = 7,
        competitor_id: int = 22,
        athlete_id: int | None = 1,
        position: int | None = 1,
        race_time_ms: int | None = 2_000,
        sequence_number: int | None = 1,
        status_value: str = "finished",
    ):
        self.id = id
        self.event_id = event_id
        self.category_id = category_id
        self.competitor_id = competitor_id
        self.athlete_id = athlete_id
        self.position = position
        self.race_time_ms = race_time_ms
        self.points_awarded = 20
        self.sequence_number = sequence_number
        self.status = SimpleNamespace(value=status_value)


@pytest.mark.asyncio
async def test_gap_to_winner_calculated_when_winner_present(
    monkeypatch, configure_db_factory, fake_session
):
    """Dado P1 con time=2000ms y atleta con time=2500ms en el mismo evento,
    el ``full_season_results`` del atleta expone:

        gap_to_winner_ms = 500
        gap_pct          = 25.0

    No debe quedar como ``None``. Esto valida que el atleta NO recibe
    silenciosamente "sin datos de gap" cuando los datos del ganador sí
    están disponibles.
    """
    configure_db_factory(fake_session)

    # Atleta analizado (posición 5, 2500 ms).
    athlete_result = _FakeRaceResult(
        id=1, event_id=100, competitor_id=22, athlete_id=1,
        position=5, race_time_ms=2500, sequence_number=1,
    )
    # Ganador de la categoría/evento (position=1, 2000 ms). Mismo event_id.
    winner_result = _FakeRaceResult(
        id=99, event_id=100, competitor_id=999, athlete_id=None,
        position=1, race_time_ms=2000, sequence_number=1,
    )

    async def _fake_fetch_results_for_athlete(db, aid, season, valida_nums=None):
        return [athlete_result]

    async def _fake_fetch_all_results_for_season(db, cat_id, season):
        return [winner_result, athlete_result]

    async def _fake_fetch_podium(db, cat, evt):
        return {"category_id": cat, "event_id": evt, "podium": [], "finishers_count": 2}

    monkeypatch.setattr(
        load_race_data_mod, "fetch_results_for_athlete",
        _fake_fetch_results_for_athlete,
    )
    monkeypatch.setattr(
        load_race_data_mod, "fetch_all_results_for_season",
        _fake_fetch_all_results_for_season,
    )
    monkeypatch.setattr(
        load_race_data_mod, "fetch_podium_context", _fake_fetch_podium,
    )

    state = {"athlete_id": 1, "season": 2026}
    update = await load_race_data_mod.load_race_data(state)

    full_season = update.get("full_season_results", [])
    assert full_season, "full_season_results no debe ir vacío con resultado finished."
    athlete_record = full_season[0]
    assert athlete_record["gap_to_winner_ms"] == 500, (
        f"Esperado 500ms gap (2500 - 2000). Recibido "
        f"{athlete_record['gap_to_winner_ms']!r}."
    )
    assert athlete_record["gap_pct"] == 25.0, (
        f"Esperado 25.0% (500/2000*100). Recibido {athlete_record['gap_pct']!r}."
    )


@pytest.mark.asyncio
async def test_gap_is_none_when_winner_unavailable(
    monkeypatch, configure_db_factory, fake_session, caplog
):
    """Si no hay P1 en la categoría/evento, ``gap_to_winner_ms`` queda None
    y se loggea un WARNING — defensa contra silencio frente a datos faltantes.
    """
    configure_db_factory(fake_session)

    athlete_result = _FakeRaceResult(
        id=1, event_id=200, competitor_id=22, athlete_id=1,
        position=5, race_time_ms=2500, sequence_number=2,
    )

    async def _fake_fetch_results_for_athlete(db, aid, season, valida_nums=None):
        return [athlete_result]

    async def _fake_fetch_all_results_for_season(db, cat_id, season):
        # Solo el atleta — no hay ganador (position=1) en el set.
        return [athlete_result]

    async def _fake_fetch_podium(db, cat, evt):
        return {}

    monkeypatch.setattr(
        load_race_data_mod, "fetch_results_for_athlete",
        _fake_fetch_results_for_athlete,
    )
    monkeypatch.setattr(
        load_race_data_mod, "fetch_all_results_for_season",
        _fake_fetch_all_results_for_season,
    )
    monkeypatch.setattr(
        load_race_data_mod, "fetch_podium_context", _fake_fetch_podium,
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.services.race.ai.nodes.load_race_data"):
        update = await load_race_data_mod.load_race_data({"athlete_id": 1, "season": 2026})

    record = update["full_season_results"][0]
    assert record["gap_to_winner_ms"] is None
    assert record["gap_pct"] is None
    assert any("sin ganador" in r.getMessage() for r in caplog.records), (
        "Se esperaba un warning sobre la ausencia de ganador. "
        f"Records: {[r.getMessage() for r in caplog.records]!r}"
    )


# ---------------------------------------------------------------------------
# Bloque 4 — Privacidad: response nunca expone competitor_id de terceros
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


async def _seed_insight_with_legacy_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    snapshot_payload: dict[str, Any],
) -> int:
    """Siembra el escenario mínimo: club + coach + parent + atleta + insight
    activo aprobado cuyo ``metrics_snapshot_json`` contiene la payload pasada.

    Devuelve el ``insight_id`` para que el test lo use en el GET.
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, code="club1")
        await create_user(s, user_id=10, role=UserRole.coach)
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)
        await create_user(s, user_id=11, role=UserRole.parent)
        await link_user_to_club(
            s, user_id=11, club_id=1, role_in_club=ClubRole.parent,
        )
        await create_user(s, user_id=144, role=UserRole.athlete, can_login=False)
        await create_athlete(
            s, athlete_id=144, club_id=1, user_id=144,
            first_name="Juan Ficticio", last_name="TestAthlete",
        )

        # Vinculamos al padre con el atleta para el escenario parent.
        from app.models.athlete import ParentAthlete, FamilyRelationship
        s.add(
            ParentAthlete(
                parent_id=11,
                athlete_id=144,
                relationship_type=FamilyRelationship.padre,
            )
        )

        await create_race_series(s, series_id=1, season_year=2026)
        await create_race_category(s, category_id=100, code="INF_B")
        await create_race_event(
            s, event_id=1, series_id=1, sequence_number=1, name="V1",
            event_date=date(2026, 1, 31),
        )
        # Competitor del atleta para satisfacer FKs si aparecen.
        await create_race_competitor(
            s, competitor_id=2222, normalized_name="athlete",
            display_name="Athlete Real Ficticio", athlete_id=144,
        )
        await create_race_result(
            s, event_id=1, category_id=100, competitor_id=2222, athlete_id=144,
            position=3, race_time_ms=1_810_000, bib_number=3,
        )

        insight = await create_insight(
            s, athlete_id=144, season=2026, valida_num=1,
            coach_approved=True, is_active=1, use_case="race_progression",
            metrics_snapshot_json=snapshot_payload,
        )
        await s.commit()
        return int(insight.id)


def _coach_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=10, first_name="Coach", last_name="Test",
        email="coach@test.com", role=UserRole.coach,
        can_login=True, is_active=True,
        club_memberships=[SimpleNamespace(club_id=1, role_in_club=ClubRole.coach)],
    )


def _parent_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=11, first_name="Padre", last_name="Ficticio",
        email="padre@test.com", role=UserRole.parent,
        can_login=True, is_active=True,
        club_memberships=[SimpleNamespace(club_id=1, role_in_club=ClubRole.parent)],
    )


@pytest_asyncio.fixture
async def client_factory(session_factory):
    """Factory que devuelve un AsyncClient autenticado como rol indicado."""

    def _make(user_builder):
        async def _override_db():
            async with session_factory() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = user_builder

        async def _client_ctx():
            transport = ASGITransport(app=app)
            return AsyncClient(transport=transport, base_url="http://test")

        return _client_ctx

    yield _make
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_insight_detail_never_contains_foreign_competitor_id_for_coach(
    session_factory, client_factory,
):
    """CRÍTICO PRIVACIDAD: el JSON del GET /insights/{id} no debe exponer
    ``competitor_id`` de OTROS atletas (terceros menores TyR), aunque el
    snapshot persistido los contenga (legacy pre-fix de Task #23)."""
    # Snapshot simula el caso real: podium_gap viejo con competitor_id
    # de varios corredores TyR (incluyendo al atleta consultado).
    legacy_snapshot = {
        "aggregate": {
            "is_first_in_season": False,
            "season_validas_count": 3,
        },
        "podium_gap": [
            # El atleta consultado (id 2222) podría aparecer; PRINCIPALMENTE
            # nos importa que NO se expongan los competitor_id ajenos.
            {"competitor_id": 2222, "valida_num": 1, "position": 3,
             "gap_to_p1_ms": 10000},
            {"competitor_id": 5555, "valida_num": 1, "position": 4,
             "gap_to_p1_ms": 12000},
            {"competitor_id": 6666, "valida_num": 1, "position": 5,
             "gap_to_p1_ms": 13000},
        ],
        "progression": [
            {"valida_num": 1, "position": 3, "race_time_ms": 1810000},
        ],
    }
    insight_id = await _seed_insight_with_legacy_snapshot(
        session_factory, snapshot_payload=legacy_snapshot,
    )

    client_ctx = client_factory(_coach_user)
    ac = await client_ctx()
    async with ac as client:
        resp = await client.get(
            f"/api/athletes/144/race-analysis/insights/{insight_id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_no_keys_recursively(body, _FORBIDDEN_FOREIGN_KEYS)


@pytest.mark.asyncio
async def test_insight_detail_never_contains_foreign_competitor_id_for_parent(
    session_factory, client_factory,
):
    """Mismo invariante para el rol parent (rol más restringido)."""
    legacy_snapshot = {
        "aggregate": {"is_first_in_season": False, "season_validas_count": 3},
        "podium_gap": [
            {"competitor_id": 2222, "valida_num": 1, "position": 3,
             "gap_to_p1_ms": 10000},
            {"competitor_id": 5555, "valida_num": 1, "position": 4,
             "gap_to_p1_ms": 12000},
        ],
    }
    insight_id = await _seed_insight_with_legacy_snapshot(
        session_factory, snapshot_payload=legacy_snapshot,
    )

    client_ctx = client_factory(_parent_user)
    ac = await client_ctx()
    async with ac as client:
        resp = await client.get(
            f"/api/athletes/144/race-analysis/insights/{insight_id}",
            headers={"Authorization": "Bearer fake"},
        )
    # El parent puede ver el insight (activo+aprobado en seed).
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_no_keys_recursively(body, _FORBIDDEN_FOREIGN_KEYS)


# ---------------------------------------------------------------------------
# Bloque 5 — Defensa router contra snapshots legacy "sucios"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_scrub_handles_legacy_snapshots_with_dirty_dict(
    session_factory, client_factory,
):
    """Snapshot legacy raw (sin `schema_version`) con competitor_id anidados
    de terceros — el router scrubs vía ``_scrub_pii_keys`` aunque persista
    sucio en DB.

    Esta es la defensa CRÍTICA en profundidad: si un coach lanzó análisis
    pre-fix de privacidad y los snapshots en MySQL conservan competitor_id,
    el GET nunca debe re-emitir esa info. La función vive en
    ``app.routers.athlete_race_analysis._scrub_pii_keys`` y es invocada por
    ``_maybe_metrics_snapshot``.
    """
    legacy_dirty_snapshot = {
        # Sin schema_version → cae a dict raw (no tipado).
        "podium_gap": [
            {"competitor_id": 5555, "position": 4, "gap_to_p1_ms": 11000},
            {"competitor_id": 7777, "position": 5, "gap_to_p1_ms": 13000},
        ],
        "extras": {
            "comparados_con": {
                "competitor_id": 9999,  # anidado profundo
                "diff_ms": 4000,
            }
        },
    }
    insight_id = await _seed_insight_with_legacy_snapshot(
        session_factory, snapshot_payload=legacy_dirty_snapshot,
    )

    client_ctx = client_factory(_coach_user)
    ac = await client_ctx()
    async with ac as client:
        resp = await client.get(
            f"/api/athletes/144/race-analysis/insights/{insight_id}",
            headers={"Authorization": "Bearer fake"},
        )
    assert resp.status_code == 200, resp.text
    _assert_no_keys_recursively(resp.json(), _FORBIDDEN_FOREIGN_KEYS)


# ---------------------------------------------------------------------------
# Bloque 6 — Guardrails kwarg athlete_age (Task #23 PENDIENTE)
# ---------------------------------------------------------------------------


def test_guardrails_age_mismatch_rejects_when_output_lies_about_age():
    """Output con 'la deportista tiene 12 años' debe ser rechazado cuando
    ``Guardrails(athlete_age=14)`` — defensa contra alucinaciones del LLM
    sobre edad.

    Verificado el kwarg ``athlete_age`` ya está implementado (Task #23
    cerrado). Si esto vuelve a romperse, el LLM podría afirmar cualquier
    edad sin que el guardrail lo detecte.
    """
    g = Guardrails(use_case="race_analyst_v2", athlete_age=14)
    bad_output = (
        "## Qué pasó en esta válida\n"
        "La deportista tiene 12 años y participó con buen ritmo.\n\n"
        "## Recorrido hasta acá\nProgreso constante.\n\n"
        "## Hacia dónde va\nReforzar fuerza.\n"
    )
    report = g.scrub_with_report(bad_output)
    assert report.rejected is True, (
        f"Se esperaba rejected=True. Violations: {report.violations!r}"
    )
    assert any(v.startswith("age_mismatch") for v in report.violations), (
        f"Se esperaba violation 'age_mismatch'. Observadas: "
        f"{report.violations!r}"
    )


def test_guardrails_age_match_passes_when_output_matches_real_age():
    """Output con 'tiene 14 años' y age=14 NO debe gatillar age_mismatch."""
    g = Guardrails(use_case="race_analyst_v2", athlete_age=14)
    good_output = (
        "## Qué pasó en esta válida\n"
        "La deportista tiene 14 años y compitió en la categoría juvenil.\n\n"
        "## Recorrido hasta acá\nDesempeño constante.\n\n"
        "## Hacia dónde va\nMantener volumen.\n"
    )
    report = g.scrub_with_report(good_output)
    assert not any(v.startswith("age_mismatch") for v in report.violations), (
        f"Falso positivo: age=14 + 'tiene 14 años' no debe gatillar "
        f"age_mismatch. Observadas: {report.violations!r}"
    )


def test_guardrails_age_check_skipped_when_age_none():
    """Si ``athlete_age=None`` (compat con flujos v1) el check no aplica.

    Garantiza retro-compatibilidad: el kwarg nuevo no debe romper a
    callers que no lo pasen.
    """
    g = Guardrails(use_case="race_analyst_v2", athlete_age=None)
    text = (
        "## Qué pasó en esta válida\n"
        "La deportista tiene 5 años y participó.\n\n"  # 5 años absurdo, pero
        # con age=None el check ni se evalúa.
        "## Recorrido hasta acá\nOk.\n\n"
        "## Hacia dónde va\nOk.\n"
    )
    report = g.scrub_with_report(text)
    assert not any(v.startswith("age_mismatch") for v in report.violations)


# ---------------------------------------------------------------------------
# Bloque 7 — Smoke: prompt v2 cita gap_pct en contexto de tendencia
# ---------------------------------------------------------------------------


def test_analyst_v2_prompt_includes_gap_pct_column_for_trend_threshold():
    """El system prompt v2 debe documentar la columna ``gap_pct`` y el
    threshold de tendencia (≥3pp). Lo verificamos buscando ambos en el
    contenido del template Jinja2 cargado.

    El bloque que documenta gap_pct vive bajo
    ``{% if not is_first_in_season and season_progression|length >= 2 %}``,
    así que el contexto debe tener ≥2 entradas para activarlo.
    """
    from app.services.race.prompts import render_prompt

    # Render mínimo (no necesita LLM real).
    context = {
        "athlete_pseudonym": "AzulZorro",
        "age": 14,
        "ltad_group": "juvenil",
        "valida_num": 2,
        "is_first_in_season": False,
        "season_progression": [
            {"valida_num": 1, "position": 5, "race_time_ms": 2500,
             "gap_to_winner_ms": 500, "gap_pct": 25.0},
            {"valida_num": 2, "position": 3, "race_time_ms": 2300,
             "gap_to_winner_ms": 200, "gap_pct": 9.5},
        ],
        "maturation_status": "Circa-PHV",
        "progression_table": "...",
        "podium_context": "...",
        "principles_block": "",
        "memory_recent_insights": [],
        "explain_mode": False,
    }
    rendered = render_prompt("race_analyst_v2", context, strict=False)
    assert "gap_pct" in rendered, (
        "El prompt v2 debe documentar la columna 'gap_pct' para que el "
        "LLM la pueda citar al declarar tendencias."
    )
    # Threshold de tendencia: el prompt debe declarar la regla explícita.
    assert any(
        marker in rendered for marker in ("3pp", "3 pp", "3 puntos porcentuales")
    ), (
        "El prompt v2 debe declarar el threshold de tendencia (≥3pp en "
        "gap_pct) para que la sección 'Recorrido' sea descriptiva y no "
        "proyectiva."
    )
