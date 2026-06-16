"""Tests TDD para el endpoint ``GET /evolution`` con ``series_kind`` y ``label``.

Feature 016 — Race Analysis Championship Charts Fix.

Contrato target (post-fix):
    GET /api/athletes/{athlete_id}/race-analysis/evolution
        ?season=<year>&metric=podium_gap_ms

Cada ``EvolutionPoint`` en ``series[]`` debe incluir:
    - ``series_kind``: "cup" | "championship"
    - ``label``: cadena no vacía construida por ``build_race_label``

Estado pre-fix (DEBEN FALLAR):
    El schema ``EvolutionPoint`` actual NO tiene los campos ``series_kind``
    ni ``label`` — tiene ``extra="forbid"`` y solo expone:
    ``valida_num``, ``event_id``, ``event_date``, ``value``, ``unit``.
    Por eso los asserts T023 que verifican la presencia de esos campos
    en el JSON de respuesta FALLARÁN en el código actual.

Caso de colisión crítico (el bug que este feature corrige):
    - Copa Válida I: ``event_id=501``, ``series_id=50`` (kind='cup'),
      ``sequence_number=1``, ``event_date=2026-01-31``.
    - Campeonato Dep.: ``event_id=503``, ``series_id=51`` (kind='championship'),
      ``sequence_number=1``, ``event_date=2026-06-12``.
    Ambos tienen ``sequence_number=1`` → antes del fix el frontend no podía
    distinguirlos. Post-fix: ``series_kind`` + ``label`` los hacen distintos.

Datos: solo ficticios (nunca reales).
Atleta "Juan Ficticio Pérez", DOB 2014-07-10, ``athlete_id=201``.
"""
from __future__ import annotations

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

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import Base
from app.models.club import ClubRole
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_club,
    create_distribution_scenario,
    create_user,
    link_user_to_club,
)


# ---------------------------------------------------------------------------
# Engine SQLite in-memory (mirrors test_athlete_race_analysis_distribution.py)
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
# Seed: escenario copa + campeonato (reutiliza create_distribution_scenario)
#
# IDs resultantes:
#   club_id=1, coach user_id=10
#   athlete_id=201  ("Juan Ficticio Pérez", DOB 2014-07-10)
#   cup_series_id=50   (kind='cup')
#   championship_series_id=51  (kind='championship')
#   category_id=200
#   cup_event_id_1=501  (seq=1, date=2026-01-31)  ← Copa Válida I
#   cup_event_id_2=502  (seq=2, date=2026-02-28)  ← Copa Válida II
#   championship_event_id=503  (seq=1, date=2026-06-12)  ← Cto. Dep.
#
# El caso crítico de colisión:
#   cup_event_id_1 y championship_event_id AMBOS tienen sequence_number=1
#   pero pertenecen a series distintas (kind distinto). El fix debe
#   diferenciarlos por series_kind.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def evolution_seeded(session_factory) -> async_sessionmaker[AsyncSession]:
    """Seed base: club + coach + escenario copa/campeonato con atleta ficticio."""
    async with session_factory() as s:
        await create_club(s, club_id=1, code="tyr_evo_fict")
        await create_user(s, user_id=10, role=UserRole.coach, email="coach_evo@test.com")
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)

        # Usuario para el atleta ficticio (can_login=False como atleta menor)
        await create_user(
            s,
            user_id=1201,
            role=UserRole.athlete,
            email="juanficticioevo@test.com",
            first_name="Juan Ficticio",
            last_name="Pérez",
            can_login=False,
        )

        # Reutilizamos create_distribution_scenario sin modificación:
        # produce copa (2 rondas, seq=1 y seq=2) + campeonato (seq=1) para
        # el mismo athlete_id=201 en season=2026.
        await create_distribution_scenario(
            s,
            athlete_id=201,
            coach_user_id=10,
            season=2026,
            cup_series_id=50,
            championship_series_id=51,
            category_id=200,
            cup_event_id_1=501,
            cup_event_id_2=502,
            championship_event_id=503,
        )
        await s.commit()
    return session_factory


# ---------------------------------------------------------------------------
# Helper: usuario coach para dependency override
# ---------------------------------------------------------------------------


def _coach_user(user_id: int = 10, club_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="Coach",
        email="coach_evo@test.com",
        role=UserRole.coach,
        can_login=True,
        is_active=True,
        club_memberships=[
            SimpleNamespace(
                club_id=club_id,
                role_in_club=ClubRole.coach,
            )
        ],
    )


# ---------------------------------------------------------------------------
# Fixture de cliente con auth override
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coach_client(evolution_seeded):
    """AsyncClient con auth=coach y DB SQLite seeded (escenario evolution)."""

    def _override_db():
        async def _inner():
            async with evolution_seeded() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        return _inner

    app.dependency_overrides[get_db] = _override_db()
    app.dependency_overrides[get_current_user] = lambda: _coach_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T023-A — Todo punto de la serie lleva series_kind y label no vacío
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_each_point_has_series_kind_and_label(coach_client):
    """T023-A: GET /evolution → cada EvolutionPoint tiene series_kind ∈
    {'cup','championship'} y label no vacío.

    Pre-fix (estado actual): EvolutionPoint NO incluye series_kind ni label
    (extra='forbid' los rechazaría en la serialización). Los asserts que
    comprueban la presencia de esos campos DEBEN FALLAR ahora — ese es el
    estado TDD-red esperado.

    Contrato target (post-fix):
    - HTTP 200.
    - series[] no vacío (el atleta ficticio compitió en 3 eventos).
    - Cada punto tiene "series_kind" ∈ {"cup", "championship"}.
    - Cada punto tiene "label" que es una cadena no vacía.
    """
    resp = await coach_client.get(
        "/api/athletes/201/race-analysis/evolution",
        params={"season": 2026, "metric": "podium_gap_ms"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200, (
        f"Esperaba 200 pero recibí {resp.status_code}. Body: {resp.text[:400]}"
    )
    body = resp.json()
    series = body.get("series", [])
    assert len(series) >= 1, (
        "series[] debe tener al menos 1 punto (el atleta compitió en 3 eventos)"
    )

    valid_kinds = {"cup", "championship"}
    for i, point in enumerate(series):
        # --- Aserción principal que DEBE FALLAR pre-fix ---
        assert "series_kind" in point, (
            f"Punto [{i}] (event_id={point.get('event_id')}) carece de 'series_kind'. "
            "El schema EvolutionPoint actual no incluye este campo. "
            "Este fallo TDD-red es esperado — implementar en T025/T026."
        )
        assert point["series_kind"] in valid_kinds, (
            f"Punto [{i}] series_kind={point['series_kind']!r} no está en {valid_kinds}"
        )
        assert "label" in point, (
            f"Punto [{i}] (event_id={point.get('event_id')}) carece de 'label'. "
            "El schema EvolutionPoint actual no incluye este campo. "
            "Este fallo TDD-red es esperado — implementar en T025/T026."
        )
        assert isinstance(point["label"], str) and point["label"].strip(), (
            f"Punto [{i}] label debe ser una cadena no vacía. Recibí: {point.get('label')!r}"
        )


# ---------------------------------------------------------------------------
# T023-B — El punto campeonato y la Copa Válida I son DISTINTOS (no colisionan)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_championship_distinct_from_cup_valida_i(coach_client):
    """T023-B: el campeonato (event_id=503) y la Copa Válida I (event_id=501)
    aparecen como entradas DISTINTAS en series[], a pesar de que ambos tienen
    sequence_number=1.

    Assertions:
    1. Hay exactamente un punto con series_kind=='championship'.
    2. El event_id del campeonato (503) difiere del de Copa Válida I (501).
    3. El label del campeonato empieza con "Cto. Dep.".
    4. El label de Copa Válida I empieza con "Válida I".

    Pre-fix: (a) los puntos no tienen series_kind → IndexError/KeyError
    hace fallar el test. (b) incluso si los campos existieran, la query
    actual no selecciona series.kind → los labels serían incorrectos.
    """
    resp = await coach_client.get(
        "/api/athletes/201/race-analysis/evolution",
        params={"season": 2026, "metric": "podium_gap_ms"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200, (
        f"Esperaba 200 pero recibí {resp.status_code}. Body: {resp.text[:400]}"
    )
    body = resp.json()
    series = body.get("series", [])
    assert len(series) >= 2, (
        f"Debe haber al menos 2 puntos en series[]. Recibí: {len(series)}"
    )

    # --- Aserción que DEBE FALLAR pre-fix (series_kind no existe) ---
    championship_points = [p for p in series if p.get("series_kind") == "championship"]
    assert len(championship_points) == 1, (
        f"Debe haber exactamente 1 punto con series_kind=='championship'. "
        f"Encontré: {len(championship_points)}. "
        "Si es 0, el campo series_kind no existe todavía (TDD-red esperado)."
    )

    cup_points = [p for p in series if p.get("series_kind") == "cup"]
    assert len(cup_points) >= 2, (
        f"Debe haber al menos 2 puntos con series_kind=='cup'. "
        f"Encontré: {len(cup_points)}."
    )

    champ_point = championship_points[0]
    # event_id del campeonato es 503 (campeonato de la fixture)
    assert champ_point["event_id"] == 503, (
        f"El punto campeonato debe tener event_id=503. Recibí: {champ_point.get('event_id')}"
    )

    # Copa Válida I: event_id=501
    cup_valida_i_points = [p for p in cup_points if p.get("event_id") == 501]
    assert len(cup_valida_i_points) == 1, (
        f"Debe existir exactamente un punto con event_id=501 (Copa Válida I). "
        f"Encontré: {len(cup_valida_i_points)}"
    )
    cup_valida_i = cup_valida_i_points[0]

    # Los event_ids son distintos (el bug a corregir era la colisión en el frontend
    # porque ambos tenían sequence_number=1; aquí verificamos que el backend los
    # distingue con series_kind).
    assert champ_point["event_id"] != cup_valida_i["event_id"], (
        "El campeonato y la Copa Válida I deben tener event_ids distintos"
    )

    # Labels correcto post-fix
    assert champ_point["label"].startswith("Cto. Dep."), (
        f"Label del campeonato debe empezar con 'Cto. Dep.'. Recibí: {champ_point['label']!r}"
    )
    assert cup_valida_i["label"].startswith("Válida I"), (
        f"Label de Copa Válida I debe empezar con 'Válida I'. Recibí: {cup_valida_i['label']!r}"
    )


# ---------------------------------------------------------------------------
# T023-C — series[] ordenado por event_date ascendente
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evolution_series_ordered_by_event_date(coach_client):
    """T023-C: series[] está ordenado cronológicamente por event_date ascendente.

    El campeonato (2026-06-12) debe aparecer DESPUÉS de las dos rondas de
    copa (2026-01-31 y 2026-02-28), no al principio ni en medio por error
    de orden.

    Este test puede pasar pre-fix (el ORDER BY ya existe en la query actual)
    pero documenta el invariante que la feature debe preservar. Si el fix
    cambia el ORDER BY y rompe el orden, este test lo detecta.

    Nota: como el test también verifica que los puntos existan con los campos
    de fecha, si el endpoint falla antes de serializar (por causa de otro
    assertion error en la fixture), este test también fallará de forma derivada.
    Para aislar el orden puro, hacemos la petición independiente.
    """
    resp = await coach_client.get(
        "/api/athletes/201/race-analysis/evolution",
        params={"season": 2026, "metric": "podium_gap_ms"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code == 200, (
        f"Esperaba 200 pero recibí {resp.status_code}. Body: {resp.text[:400]}"
    )
    body = resp.json()
    series = body.get("series", [])
    assert len(series) >= 2, (
        f"Necesito al menos 2 puntos para verificar el orden. Recibí: {len(series)}"
    )

    # Verificar que event_date esté presente en cada punto
    for i, point in enumerate(series):
        assert "event_date" in point, (
            f"Punto [{i}] carece de 'event_date'"
        )

    # Extraer fechas y verificar orden ascendente
    dates = [p["event_date"] for p in series]
    assert dates == sorted(dates), (
        f"series[] debe estar ordenado por event_date ASC. Recibí: {dates}"
    )

    # Verificar la posición relativa: copa 2026-01-31 → copa 2026-02-28 → cto 2026-06-12
    assert dates[0] <= dates[-1], (
        "El primer punto debe ser anterior o igual al último (orden cronológico)"
    )

    # El campeonato (fecha 2026-06-12) debe ser el último de los 3 puntos
    assert dates[-1] == "2026-06-12", (
        f"El último punto debería ser el campeonato (2026-06-12). Recibí: {dates[-1]}"
    )
    assert dates[0] == "2026-01-31", (
        f"El primer punto debería ser Copa Válida I (2026-01-31). Recibí: {dates[0]}"
    )
