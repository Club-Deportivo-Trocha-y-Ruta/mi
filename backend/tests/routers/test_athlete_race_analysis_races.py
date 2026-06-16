"""Tests TDD para el endpoint ``GET /api/athletes/{id}/race-analysis/races``.

Feature 016 — Race Analysis Championship Charts Fix.

Contrato target (aún NO implementado — T018/T019/T020):
    GET /api/athletes/{athlete_id}/race-analysis/races?season=2026
    → RaceParticipationResponse:
        {
          "season": 2026,
          "items": [
            {
              "event_id": <int>,
              "sequence_number": <int>,
              "series_kind": "cup" | "championship",
              "event_date": "YYYY-MM-DD",
              "event_name": "...",
              "location": "...",
              "label": "Válida {roman} — {city}" | "Cto. Dep. — {city}"
            },
            ...
          ]
        }

Reglas del contrato:
    - items = SOLO carreras en las que el atleta compitió (cualquier status
      incluyendo DNF), ordenadas por event_date ASC.
    - Una válida de copa (sequence_number=1) y un campeonato (sequence_number=1)
      con el mismo número de ronda son DOS items distintos con event_id distinto
      (caso SC-004 — colisión de sequence_number).
    - El body NO contiene athlete_id ni competitor_id en ningún nivel.
    - RBAC: admin/coach (del mismo club)/parent-de-este-atleta → 200;
            parent de un atleta DIFERENTE → 403.
    - season fuera de rango → 422.

Estado actual (TDD-rojo):
    El endpoint no existe → todas las solicitudes devuelven 404 Not Found.

Datos: solo ficticios. Reutiliza ``create_distribution_scenario`` de
``tests/fixtures/race_history_fixtures.py``.

IDs del escenario reutilizados de create_distribution_scenario (defaults):
    athlete_id          = 201   ("Juan Ficticio Pérez", DOB 2014-07-10)
    cup_series_id       = 50    (kind='cup')
    championship_series_id = 51  (kind='championship')
    category_id         = 200
    cup_event_id_1      = 501   (sequence_number=1, date 2026-01-31)
    cup_event_id_2      = 502   (sequence_number=2, date 2026-02-28)
    championship_event_id = 503  (sequence_number=1, date 2026-06-12)
"""
from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import AsyncGenerator, Any

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

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_distribution_scenario,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from app.models.race_result import ResultStatus
from app.models.race_series import RaceSeriesKind


# ---------------------------------------------------------------------------
# Engine SQLite in-memory (mismo DDL que distribution tests)
# ---------------------------------------------------------------------------

_AGENT_RUNS_DDL = """
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

_TABLES = (
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
    "anthropometric_records",
)


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.exec_driver_sql(_AGENT_RUNS_DDL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Seed: escenario distribución reutilizado + parent de este atleta
# ---------------------------------------------------------------------------

# IDs del seed principal (espejo de create_distribution_scenario defaults)
_ATHLETE_ID = 201
_CUP_EVENT_1 = 501   # sequence_number=1, date 2026-01-31, kind='cup'
_CUP_EVENT_2 = 502   # sequence_number=2, date 2026-02-28, kind='cup'
_CHAMP_EVENT = 503   # sequence_number=1, date 2026-06-12, kind='championship'
_COACH_USER_ID = 10
_PARENT_OWN_ID = 20   # padre de este atleta (athlete_id=201)
_PARENT_OTHER_ID = 30  # padre de un atleta DISTINTO (athlete_id=202)
_OTHER_ATHLETE_ID = 202  # atleta sin vínculo con PARENT_OWN_ID

_LOCATION_DEFAULT = "Sevilla"   # default en create_race_event


@pytest_asyncio.fixture
async def races_seeded(session_factory) -> async_sessionmaker[AsyncSession]:
    """Seed completo para los tests T015 y T016.

    Crea:
    - club_id=1, coach (user_id=10).
    - Atleta ficticio (id=201) vía create_distribution_scenario.
    - Parent propio (user_id=20) vinculado al atleta 201.
    - Parent ajeno (user_id=30) vinculado al atleta 202 (distinto).
    - Atleta ficticio 2 (id=202) para el caso 403.
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, code="tyr_races_test")
        await create_user(
            s, user_id=_COACH_USER_ID, role=UserRole.coach,
            email="coach_races@test.com",
        )
        await link_user_to_club(
            s, user_id=_COACH_USER_ID, club_id=1, role_in_club=ClubRole.coach,
        )

        # Usuario del atleta ficticio principal
        await create_user(
            s,
            user_id=_ATHLETE_ID + 1000,  # 1201
            role=UserRole.athlete,
            email="juanficticio201@test.com",
            first_name="Juan Ficticio",
            last_name="Pérez",
            can_login=False,
        )

        # Escenario copa + campeonato (atleta 201)
        await create_distribution_scenario(
            s,
            athlete_id=_ATHLETE_ID,
            coach_user_id=_COACH_USER_ID,
            season=2026,
            cup_series_id=50,
            championship_series_id=51,
            category_id=200,
            cup_event_id_1=_CUP_EVENT_1,
            cup_event_id_2=_CUP_EVENT_2,
            championship_event_id=_CHAMP_EVENT,
        )

        # Parent propio (user_id=20) → vinculado al atleta 201
        await create_user(
            s, user_id=_PARENT_OWN_ID, role=UserRole.parent,
            email="parent_own@test.com",
        )
        await link_parent_to_athlete(
            s, parent_user_id=_PARENT_OWN_ID, athlete_id=_ATHLETE_ID,
        )

        # Atleta ficticio 2 (id=202) — diferente, sin relación con parent 20
        await create_user(
            s, user_id=_OTHER_ATHLETE_ID + 1000,  # 1202
            role=UserRole.athlete,
            email="juanficticio202@test.com",
            first_name="Otro Ficticio",
            last_name="García",
            can_login=False,
        )
        from app.models.athlete import Athlete, Sex
        other_athlete = Athlete(
            id=_OTHER_ATHLETE_ID,
            user_id=_OTHER_ATHLETE_ID + 1000,
            first_name="Otro Ficticio",
            last_name="García",
            birth_date=date(2013, 5, 20),
            sex=Sex.M,
            club_id=1,
            created_by=_COACH_USER_ID,
        )
        s.add(other_athlete)
        await s.flush()

        # Parent ajeno (user_id=30) → vinculado al atleta 202 (NO al 201)
        await create_user(
            s, user_id=_PARENT_OTHER_ID, role=UserRole.parent,
            email="parent_other@test.com",
        )
        await link_parent_to_athlete(
            s, parent_user_id=_PARENT_OTHER_ID, athlete_id=_OTHER_ATHLETE_ID,
        )

        await s.commit()
    return session_factory


# ---------------------------------------------------------------------------
# Helpers: usuarios para overrides de auth
# ---------------------------------------------------------------------------


def _coach_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=_COACH_USER_ID,
        first_name="Entrenador",
        last_name="Ficticio",
        email="coach_races@test.com",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(club_id=1, role_in_club=ClubRole.coach)
        ],
    )


def _parent_own_user() -> SimpleNamespace:
    """Parent que SÍ está vinculado al atleta 201."""
    return SimpleNamespace(
        id=_PARENT_OWN_ID,
        first_name="Padre",
        last_name="Ficticio",
        email="parent_own@test.com",
        role=UserRole.parent,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


def _parent_other_user() -> SimpleNamespace:
    """Parent vinculado al atleta 202, NO al 201."""
    return SimpleNamespace(
        id=_PARENT_OTHER_ID,
        first_name="Padre",
        last_name="Ajeno",
        email="parent_other@test.com",
        role=UserRole.parent,
        can_login=True,
        is_active=True,
        club_memberships=[],
    )


# ---------------------------------------------------------------------------
# Fixture de cliente con override de auth
# ---------------------------------------------------------------------------


def _make_client(session_factory_fixture, user_fn):
    """Construye un AsyncClient con DB override + auth override."""

    def _override_db():
        async def _inner():
            async with session_factory_fixture() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise
        return _inner

    app.dependency_overrides[get_db] = _override_db()
    app.dependency_overrides[get_current_user] = user_fn
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Helper: recorre el JSON recursivamente buscando keys prohibidas
# ---------------------------------------------------------------------------


def _assert_no_keys_recursively(payload: Any, forbidden: set[str], path: str = "$") -> None:
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in forbidden:
                raise AssertionError(
                    f"Key prohibida '{k}' encontrada en {path}.{k} — payload={payload!r}"
                )
            _assert_no_keys_recursively(v, forbidden, path=f"{path}.{k}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _assert_no_keys_recursively(item, forbidden, path=f"{path}[{i}]")


# ===========================================================================
# T015 — Contenido del endpoint /races
# ===========================================================================


@pytest.mark.asyncio
async def test_races_coach_returns_200_with_competed_races_ordered_by_date(
    races_seeded,
):
    """T015-1: coach obtiene 200 con items = exactamente las carreras en que
    el atleta ficticio (id=201) compitió, ordenadas por event_date ASC.

    Escenario: atleta compitió en cup_event_1 (2026-01-31),
    cup_event_2 (2026-02-28) y championship_event (2026-06-12).
    → 3 items en orden cronológico.
    """
    async with _make_client(races_seeded, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{_ATHLETE_ID}/race-analysis/races",
            params={"season": 2026},
            headers={"Authorization": "Bearer fake"},
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Esperaba 200 pero recibí {resp.status_code}. Body: {resp.text[:400]}"
    )
    body = resp.json()
    assert body["season"] == 2026
    items = body["items"]
    assert len(items) == 3, (
        f"Esperaba 3 items (2 valid. copa + 1 campeonato). Recibí {len(items)}: {items}"
    )

    # Ordenados por event_date ASC
    dates = [it["event_date"] for it in items]
    assert dates == sorted(dates), (
        f"Los items no están ordenados por event_date. Fechas: {dates}"
    )

    # Fechas esperadas
    assert dates[0] == "2026-01-31"
    assert dates[1] == "2026-02-28"
    assert dates[2] == "2026-06-12"

    # event_ids correctos
    event_ids = [it["event_id"] for it in items]
    assert _CUP_EVENT_1 in event_ids
    assert _CUP_EVENT_2 in event_ids
    assert _CHAMP_EVENT in event_ids


@pytest.mark.asyncio
async def test_races_label_format_cup_vs_championship(races_seeded):
    """T015-1b: las labels siguen el formato del contrato.

    Copa → "Válida {roman} — {city}"
    Campeonato → "Cto. Dep. — {city}"
    """
    async with _make_client(races_seeded, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{_ATHLETE_ID}/race-analysis/races",
            params={"season": 2026},
            headers={"Authorization": "Bearer fake"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text[:300]
    items = resp.json()["items"]

    # Ordenados por fecha; primero los de copa, último el campeonato
    cup_items = [it for it in items if it["series_kind"] == "cup"]
    champ_items = [it for it in items if it["series_kind"] == "championship"]

    assert len(cup_items) == 2
    assert len(champ_items) == 1

    # Copa: labels con "Válida"
    for it in cup_items:
        assert it["label"].startswith("Válida"), (
            f"Label de copa debe comenzar con 'Válida'. Recibí: {it['label']!r}"
        )

    # Campeonato: label con "Cto. Dep."
    champ = champ_items[0]
    assert champ["label"].startswith("Cto. Dep."), (
        f"Label de campeonato debe comenzar con 'Cto. Dep.'. Recibí: {champ['label']!r}"
    )


@pytest.mark.asyncio
async def test_races_non_competed_events_are_absent(races_seeded):
    """T015-2: eventos en los que el atleta NO compitió no aparecen en items.

    Agregamos un evento extra (event_id=600) donde el atleta 201 NO tiene
    race_result. Debe ser invisible en la respuesta.
    """
    # Necesitamos sembrar el evento extra en la misma DB
    async with races_seeded() as s:
        await create_race_event(
            s,
            event_id=600,
            series_id=50,  # cup_series_id
            sequence_number=5,
            name="Evento Sin Atleta",
            event_date=date(2026, 10, 1),
            created_by_user_id=_COACH_USER_ID,
        )
        # 1 corredor ficticio que SÍ compitió en ese evento (pero no el atleta 201)
        await create_race_competitor(
            s, competitor_id=60001,
            normalized_name="corredor ficticio extra",
            display_name="Corredor Ficticio Extra 600",
        )
        await create_race_result(
            s, event_id=600, category_id=200, competitor_id=60001,
            position=1, race_time_ms=1_800_000, bib_number=1,
            created_by_user_id=_COACH_USER_ID,
        )
        await s.commit()

    async with _make_client(races_seeded, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{_ATHLETE_ID}/race-analysis/races",
            params={"season": 2026},
            headers={"Authorization": "Bearer fake"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text[:300]
    items = resp.json()["items"]
    event_ids = [it["event_id"] for it in items]
    assert 600 not in event_ids, (
        "El evento 600 no debe aparecer porque el atleta no compitió en él."
    )
    # Solo los 3 del escenario base
    assert len(items) == 3, (
        f"Esperaba solo los 3 eventos del atleta. Recibí {len(items)}: {event_ids}"
    )


@pytest.mark.asyncio
async def test_races_cup_round1_and_championship_round1_are_two_distinct_items(
    races_seeded,
):
    """T015-3: caso SC-004 — cup sequence_number=1 y championship
    sequence_number=1 son DOS items con event_id distintos.

    El escenario base tiene cup_event_1 (seq=1, kind=cup) y
    championship_event (seq=1, kind=championship). Deben ser 2 items
    distintos, nunca colapsados en uno.
    """
    async with _make_client(races_seeded, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{_ATHLETE_ID}/race-analysis/races",
            params={"season": 2026},
            headers={"Authorization": "Bearer fake"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text[:300]
    items = resp.json()["items"]

    # Ambos eventos con sequence_number=1 deben estar presentes
    seq1_items = [it for it in items if it["sequence_number"] == 1]
    assert len(seq1_items) == 2, (
        f"Esperaba 2 items con sequence_number=1 (copa + campeonato). "
        f"Recibí {len(seq1_items)}: {seq1_items}"
    )
    # Con event_id distintos
    seq1_event_ids = {it["event_id"] for it in seq1_items}
    assert len(seq1_event_ids) == 2, (
        f"Los event_ids de los dos items seq=1 deben ser distintos. "
        f"Recibí: {seq1_event_ids}"
    )
    assert _CUP_EVENT_1 in seq1_event_ids
    assert _CHAMP_EVENT in seq1_event_ids

    # series_kind distintos
    kinds = {it["series_kind"] for it in seq1_items}
    assert "cup" in kinds
    assert "championship" in kinds


@pytest.mark.asyncio
async def test_races_athlete_with_zero_competed_races_returns_200_empty_items(
    session_factory,
):
    """T015-4: atleta que no compitió en ninguna carrera en esa temporada
    → 200 con items=[].

    Usamos un atleta distinto (id=300) sin ningún race_result.
    """
    async with session_factory() as s:
        await create_club(s, club_id=1, code="tyr_empty_test")
        await create_user(
            s, user_id=_COACH_USER_ID, role=UserRole.coach,
            email="coach_empty@test.com",
        )
        await link_user_to_club(
            s, user_id=_COACH_USER_ID, club_id=1, role_in_club=ClubRole.coach,
        )
        await create_user(
            s, user_id=1300, role=UserRole.athlete,
            email="atl300@test.com", can_login=False,
        )
        from app.models.athlete import Athlete, Sex
        empty_athlete = Athlete(
            id=300,
            user_id=1300,
            first_name="Sin Carreras",
            last_name="Ficticio",
            birth_date=date(2015, 1, 1),
            sex=Sex.M,
            club_id=1,
            created_by=_COACH_USER_ID,
        )
        s.add(empty_athlete)
        await s.commit()

    empty_session_factory = session_factory

    def _override_db():
        async def _inner():
            async with empty_session_factory() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise
        return _inner

    app.dependency_overrides[get_db] = _override_db()
    app.dependency_overrides[get_current_user] = _coach_user
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/athletes/300/race-analysis/races",
                params={"season": 2026},
                headers={"Authorization": "Bearer fake"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, (
        f"Esperaba 200 para atleta sin carreras. Recibí {resp.status_code}. "
        f"Body: {resp.text[:300]}"
    )
    body = resp.json()
    assert body["items"] == [], (
        f"Esperaba items=[] para atleta sin carreras. Recibí: {body['items']}"
    )
    assert body["season"] == 2026


# ===========================================================================
# T016 — RBAC, privacidad, validación de parámetros
# ===========================================================================


@pytest.mark.asyncio
async def test_races_rbac_parent_own_athlete_returns_200(races_seeded):
    """T016-1a: parent del propio atleta (id=20 → atleta 201) → 200."""
    async with _make_client(races_seeded, _parent_own_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{_ATHLETE_ID}/race-analysis/races",
            params={"season": 2026},
            headers={"Authorization": "Bearer fake"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200, (
        f"Parent del propio atleta debe recibir 200. "
        f"Recibí {resp.status_code}. Body: {resp.text[:300]}"
    )
    body = resp.json()
    assert "items" in body
    assert body["season"] == 2026


@pytest.mark.asyncio
async def test_races_rbac_parent_different_athlete_returns_403(races_seeded):
    """T016-1b: parent ajeno (id=30, vinculado al atleta 202, NO al 201)
    intenta acceder al atleta 201 → 403.

    Patrón reusado de test_get_insights_as_parent_other_child_returns_403
    en test_athlete_race_analysis.py: usuario parent con id=30 intenta
    acceder al path /athletes/201/... → verify_athlete_access lanza 403.
    """
    async with _make_client(races_seeded, _parent_other_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{_ATHLETE_ID}/race-analysis/races",
            params={"season": 2026},
            headers={"Authorization": "Bearer fake"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 403, (
        f"Parent ajeno debe recibir 403. "
        f"Recibí {resp.status_code}. Body: {resp.text[:300]}"
    )


@pytest.mark.asyncio
async def test_races_privacy_response_body_has_no_athlete_id_or_competitor_id(
    races_seeded,
):
    """T016-2: el body de la respuesta 200 no contiene athlete_id ni
    competitor_id en ningún nivel del JSON.

    El cliente ya conoce athlete_id por la URL; competitor_id es PK interna
    de race_competitors y nunca debe salir al cliente.
    """
    async with _make_client(races_seeded, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{_ATHLETE_ID}/race-analysis/races",
            params={"season": 2026},
            headers={"Authorization": "Bearer fake"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text[:300]

    body = resp.json()
    _assert_no_keys_recursively(body, {"athlete_id", "competitor_id"})

    # Doble check: el texto crudo tampoco debe contenerlos
    raw = resp.text
    assert '"athlete_id"' not in raw, (
        "El texto de la respuesta no debe contener la key 'athlete_id' (privacidad)."
    )
    assert '"competitor_id"' not in raw, (
        "El texto de la respuesta no debe contener la key 'competitor_id' (privacidad)."
    )


@pytest.mark.asyncio
async def test_races_season_out_of_range_returns_422(races_seeded):
    """T016-3: season=1999 (fuera de rango razonable) → 422 Unprocessable Entity.

    El schema del endpoint debe validar que season sea un año dentro de
    los rangos válidos (e.g., ≥ 2020 según convención del proyecto).
    """
    async with _make_client(races_seeded, _coach_user) as ac:
        resp = await ac.get(
            f"/api/athletes/{_ATHLETE_ID}/race-analysis/races",
            params={"season": 1999},
            headers={"Authorization": "Bearer fake"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 422, (
        f"season=1999 debe devolver 422. Recibí {resp.status_code}. "
        f"Body: {resp.text[:300]}"
    )
