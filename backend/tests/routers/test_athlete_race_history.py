"""Tests TDD para ``GET /api/athletes/{athlete_id}/race-analysis/history``.

Feature 044, US6 (T069) — contrato
``specs/044-race-history-backfill/contracts/history-progression-api.md``.

Cubre: RBAC vía ``verify_athlete_access`` (sin cambios: admin/coach/padre
propio → 200; otro coach / otro padre → 403), presupuesto de ≤3 SELECT
(decisión del propietario 2026-09-22: se retiró ``avg_speed_kmh`` del
historial, así que el cargador ya no consulta setups de recorrido — el
presupuesto bajó de 4 a 3), ausencia de cualquier campo de tercero en la
respuesta, y el filtro ``series_kind``.

Datos: 100% ficticios. Atleta "Juan Ficticio Pérez", ``athlete_id=300``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
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
from app.config import settings
from app.models.athlete import Athlete
from app.models.club import ClubRole
from app.models.privacy_policy import PrivacyPolicy
from app.models.race_result import RaceResult
from app.models.race_series import RaceSeriesKind
from app.models.user import UserRole

from tests.fixtures.race_history_fixtures import (
    create_athlete,
    create_club,
    create_race_category,
    create_race_competitor,
    create_race_event,
    create_race_result,
    create_race_series,
    create_user,
    link_parent_to_athlete,
    link_user_to_club,
)
from tests.helpers.query_counting import count_selects

_ATHLETE_ID = 300
_CATEGORY_ID = 100
_CUP_SERIES_ID = 1
_CHAMP_SERIES_ID = 2
_EVENT_V1 = 1001  # campo de 4 (<5)
_EVENT_V2 = 1002  # campo de 5 (=5)
_EVENT_CHAMP = 1003


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
    "race_course_variants",
    "race_course_category_setups",
    "privacy_policies",
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
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def history_seeded(session_factory) -> async_sessionmaker[AsyncSession]:
    async with session_factory() as s:
        await create_club(s, club_id=1, code="tyr_hist")
        await create_club(s, club_id=2, code="otro_club_hist")

        await create_user(s, user_id=10, role=UserRole.coach, email="coach_hist@test.com")
        await link_user_to_club(s, user_id=10, club_id=1, role_in_club=ClubRole.coach)

        await create_user(s, user_id=11, role=UserRole.coach, email="otro_coach_hist@test.com")
        await link_user_to_club(s, user_id=11, club_id=2, role_in_club=ClubRole.coach)

        await create_user(
            s, user_id=1301, role=UserRole.athlete, email="atleta_hist@test.com",
            first_name="Juan Ficticio", last_name="Pérez", can_login=False,
        )
        await create_athlete(s, athlete_id=_ATHLETE_ID, club_id=1, user_id=1301, created_by=10)

        await create_user(s, user_id=20, role=UserRole.parent, email="padre_hist@test.com")
        await link_parent_to_athlete(s, parent_user_id=20, athlete_id=_ATHLETE_ID)

        await create_user(s, user_id=21, role=UserRole.parent, email="otro_padre_hist@test.com")

        await create_race_series(s, series_id=_CUP_SERIES_ID, season_year=2024, kind=RaceSeriesKind.cup)
        await create_race_series(
            s, series_id=_CHAMP_SERIES_ID, season_year=2024, name="Cto. Departamental",
            kind=RaceSeriesKind.championship,
        )
        await create_race_category(s, category_id=_CATEGORY_ID, code="INF_A", label="Infantil A")

        await create_race_event(s, event_id=_EVENT_V1, series_id=_CUP_SERIES_ID, sequence_number=1, event_date=date(2024, 2, 1))
        await create_race_event(s, event_id=_EVENT_V2, series_id=_CUP_SERIES_ID, sequence_number=2, event_date=date(2024, 3, 1))
        await create_race_event(s, event_id=_EVENT_CHAMP, series_id=_CHAMP_SERIES_ID, sequence_number=1, event_date=date(2024, 6, 1))

        await create_race_competitor(s, competitor_id=1, normalized_name="atleta propio", athlete_id=_ATHLETE_ID)
        for cid in (2, 3, 4, 5):
            await create_race_competitor(s, competitor_id=cid, normalized_name=f"tercero {cid}")

        # V1: campo de 4 (atleta incluido), atleta 2º.
        await create_race_result(s, event_id=_EVENT_V1, category_id=_CATEGORY_ID, competitor_id=1, athlete_id=_ATHLETE_ID, position=2, race_time_ms=3_100_000, points_awarded=18)
        for comp_id, pos, t in [(2, 1, 3_000_000), (3, 3, 3_200_000), (4, 4, 3_300_000)]:
            await create_race_result(s, event_id=_EVENT_V1, category_id=_CATEGORY_ID, competitor_id=comp_id, position=pos, race_time_ms=t)

        # V2: campo de 5, atleta gana.
        await create_race_result(s, event_id=_EVENT_V2, category_id=_CATEGORY_ID, competitor_id=1, athlete_id=_ATHLETE_ID, position=1, race_time_ms=2_900_000, points_awarded=25)
        for comp_id, pos, t in [(2, 2, 3_000_000), (3, 3, 3_100_000), (4, 4, 3_200_000), (5, 5, 3_300_000)]:
            await create_race_result(s, event_id=_EVENT_V2, category_id=_CATEGORY_ID, competitor_id=comp_id, position=pos, race_time_ms=t)

        # Campeonato: solo el atleta (para el filtro series_kind).
        await create_race_result(s, event_id=_EVENT_CHAMP, category_id=_CATEGORY_ID, competitor_id=1, athlete_id=_ATHLETE_ID, position=1, race_time_ms=2_800_000, points_awarded=30)

        await s.commit()
    return session_factory


def _user(user_id: int, role: UserRole, *, club_id: int | None = None, club_role: ClubRole = ClubRole.coach) -> SimpleNamespace:
    memberships = [] if club_id is None else [SimpleNamespace(club_id=club_id, role_in_club=club_role)]
    return SimpleNamespace(
        id=user_id,
        first_name="Test",
        last_name="User",
        role=role,
        can_login=True,
        is_active=True,
        club_memberships=memberships,
    )


@pytest_asyncio.fixture
async def client_factory(history_seeded):
    """Devuelve una fábrica ``make_client(user)`` con DB seeded compartida."""

    def _override_db():
        async def _inner():
            async with history_seeded() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        return _inner

    async def _make_client(user: SimpleNamespace) -> AsyncClient:
        app.dependency_overrides[get_db] = _override_db()
        app.dependency_overrides[get_current_user] = lambda: user
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    yield _make_client
    app.dependency_overrides.clear()


_URL = f"/api/athletes/{_ATHLETE_ID}/race-analysis/history"


async def _set_registration(factory: async_sessionmaker[AsyncSession], when: datetime) -> None:
    """Fija ``athletes.created_at`` (fecha de registro, R-09) del atleta sembrado."""
    async with factory() as s:
        athlete = await s.get(Athlete, _ATHLETE_ID)
        athlete.created_at = when
        await s.commit()


@pytest.mark.asyncio
async def test_coach_gets_200_with_full_series(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["points"]) == 2  # solo cup por default — el campeonato queda fuera
    assert {p["event_id"] for p in body["points"]} == {_EVENT_V1, _EVENT_V2}


@pytest.mark.asyncio
async def test_admin_gets_200(client_factory):
    async with await client_factory(_user(99, UserRole.admin)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_own_parent_gets_200(client_factory, history_seeded):
    # Registro anterior a toda la serie → nada que retener aunque la compuerta
    # de familia esté cerrada (ver sección US7 más abajo).
    await _set_registration(history_seeded, datetime(2023, 12, 1))
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 200
    assert len(resp.json()["points"]) == 2


@pytest.mark.asyncio
async def test_other_parent_gets_403(client_factory):
    async with await client_factory(_user(21, UserRole.parent)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_other_coach_gets_403(client_factory):
    async with await client_factory(_user(11, UserRole.coach, club_id=2)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_series_kind_filter_all_includes_championship(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "all"})
    assert resp.status_code == 200
    assert len(resp.json()["points"]) == 3


@pytest.mark.asyncio
async def test_series_kind_filter_championship_only(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "championship"})
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    assert points[0]["event_id"] == _EVENT_CHAMP
    assert points[0]["series_kind"] == "championship"


@pytest.mark.asyncio
async def test_response_has_no_third_party_field(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    body = resp.json()
    raw = resp.text
    # Ningún competitor_id, ni de terceros ni propio — la serie está indexada
    # por athlete_id (data-model invariante 4/5, contrato línea 5).
    assert "competitor_id" not in raw
    assert "athlete_id" not in raw
    for point in body["points"]:
        assert set(point.keys()) <= {
            "event_id", "event_date", "season", "label", "series_id",
            "series_name", "series_kind", "category_code", "category_label",
            "category_changed", "previous_category_label",
            "category_change_kind", "status",
            "position", "field_size", "timed_finishers", "percentile",
            "gap_to_median_pct", "gap_to_winner_pct", "gap_to_podium_pct",
            "points_awarded",
        }


@pytest.mark.asyncio
async def test_field_thresholds_shape_percentile_and_gap(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    points = {p["event_id"]: p for p in resp.json()["points"]}
    v1, v2 = points[_EVENT_V1], points[_EVENT_V2]
    assert v1["field_size"] == 4
    assert v1["percentile"] is None
    assert v1["gap_to_median_pct"] is None
    assert v2["field_size"] == 5
    assert v2["percentile"] is not None
    assert v2["gap_to_median_pct"] is not None


@pytest.mark.asyncio
async def test_caveats_are_always_present_and_fixed(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    caveats = resp.json()["caveats"]
    assert caveats == [
        "different_courses",
        "weather_surface",
        "small_fields",
        "non_finishers_excluded",
        "three_rider_categories",
    ]


@pytest.mark.asyncio
async def test_seasons_completion_present(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get(_URL)
    seasons = resp.json()["seasons"]
    assert seasons == [{"season": 2024, "started": 2, "finished": 2}]


@pytest.mark.asyncio
async def test_statement_count_at_most_three(client_factory, engine):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        async with count_selects(engine) as counter:
            resp = await ac.get(_URL)
    assert resp.status_code == 200
    # +1 por la query de ``verify_athlete_access`` (carga del Athlete),
    # que no forma parte del presupuesto de 3 del cargador de historia.
    assert counter[0] <= 4


@pytest.mark.asyncio
async def test_unknown_athlete_returns_404(client_factory):
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        resp = await ac.get("/api/athletes/999999/race-analysis/history")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# US7 (T078) — compuerta de familia sobre resultados previos al registro
# (FR-040/041, R-09, data-model §10 invariante 6, contrato "Parent filter").
# Registro del atleta: 2024-02-15 → V1 (2024-02-01) es previa, V2
# (2024-03-01) y el campeonato (2024-06-01) son posteriores.
# ---------------------------------------------------------------------------

_REGISTERED = datetime(2024, 2, 15, 12, 0)
_POLICY_LIVE = "hist-live"
_POLICY_FUTURE = "hist-future"
_POLICY_DEPRECATED = "hist-old"


@pytest_asyncio.fixture
async def gated(history_seeded) -> async_sessionmaker[AsyncSession]:
    await _set_registration(history_seeded, _REGISTERED)
    async with history_seeded() as s:
        today = date.today()
        for pid, version, effective, deprecated in (
            (1, _POLICY_LIVE, today - timedelta(days=30), None),
            (2, _POLICY_FUTURE, today + timedelta(days=30), None),
            (3, _POLICY_DEPRECATED, today - timedelta(days=90), today - timedelta(days=30)),
        ):
            s.add(
                PrivacyPolicy(
                    id=pid, version=version, effective_date=effective, deprecated_at=deprecated,
                    title="Política ficticia", content_html="<p>Ficticia</p>",
                    content_hash="0" * 64,
                )
            )
        await s.commit()
    return history_seeded


def _gate(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    monkeypatch.setattr(settings, "race_history_family_policy_version", version)


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["", _POLICY_FUTURE, _POLICY_DEPRECATED, "hist-no-existe"])
async def test_parent_gate_closed_hides_pre_registration_results(
    client_factory, gated, monkeypatch, version
):
    _gate(monkeypatch, version)
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert [p["event_id"] for p in body["points"]] == [_EVENT_V2]
    assert all(p["event_date"] >= _REGISTERED.date().isoformat() for p in body["points"])
    # ``seasons`` recalculado sobre lo que queda, no sobre la serie completa.
    assert body["seasons"] == [{"season": 2024, "started": 1, "finished": 1}]


@pytest.mark.asyncio
async def test_parent_gate_closed_applies_to_all_series_kinds(client_factory, gated, monkeypatch):
    _gate(monkeypatch, "")
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "all"})
    body = resp.json()
    assert [p["event_id"] for p in body["points"]] == [_EVENT_V2, _EVENT_CHAMP]
    assert body["seasons"] == [{"season": 2024, "started": 2, "finished": 2}]


@pytest.mark.asyncio
async def test_parent_gate_open_returns_everything(client_factory, gated, monkeypatch):
    _gate(monkeypatch, _POLICY_LIVE)
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        resp = await ac.get(_URL)
    body = resp.json()
    assert [p["event_id"] for p in body["points"]] == [_EVENT_V1, _EVENT_V2]
    assert body["seasons"] == [{"season": 2024, "started": 2, "finished": 2}]


@pytest.mark.asyncio
@pytest.mark.parametrize("role,user_id,club_id", [(UserRole.coach, 10, 1), (UserRole.admin, 99, None)])
async def test_staff_never_filtered_with_gate_closed(
    client_factory, gated, monkeypatch, role, user_id, club_id
):
    _gate(monkeypatch, "")
    async with await client_factory(_user(user_id, role, club_id=club_id)) as ac:
        resp = await ac.get(_URL)
    body = resp.json()
    assert [p["event_id"] for p in body["points"]] == [_EVENT_V1, _EVENT_V2]
    assert body["seasons"] == [{"season": 2024, "started": 2, "finished": 2}]


@pytest.mark.asyncio
async def test_parent_gate_closed_leaks_no_hint_of_withheld_rows(client_factory, gated, monkeypatch):
    """Invariante 6: ni cuenta, ni flag, ni caveat, ni temporada vacía.

    Se compara la respuesta filtrada con la de un atleta cuyo historial es
    todo posterior al registro (mismo atleta, registro movido a 2024-02-20
    y V1 ya retirada por borrado lógico → misma vista "natural").
    Además V1 se mueve a otra categoría: el primer punto visible NO debe
    delatar el cambio frente a un punto oculto.
    """
    async with gated() as s:
        v1_own = (
            await s.execute(
                RaceResult.__table__.select().where(
                    RaceResult.event_id == _EVENT_V1, RaceResult.athlete_id == _ATHLETE_ID
                )
            )
        ).first()
        await create_race_category(s, category_id=_CATEGORY_ID + 1, code="PINF", label="Preinfantil")
        row = await s.get(RaceResult, v1_own.id)
        row.category_id = _CATEGORY_ID + 1
        await s.commit()

    _gate(monkeypatch, "")
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        coach_body = (await ac.get(_URL)).json()
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        gated_resp = await ac.get(_URL)
    gated_body = gated_resp.json()

    # Control: el coach sí ve el cambio de categoría en V2.
    coach_v2 = next(p for p in coach_body["points"] if p["event_id"] == _EVENT_V2)
    assert coach_v2["category_changed"] is True

    # Vista "natural": sin resultados previos al registro en absoluto. Se
    # compara padre contra padre (feature 045: la variante de familia omite
    # ``gap_to_winner_pct``/``gap_to_podium_pct``, así que un cuerpo de coach
    # ya no es comparable byte a byte).
    async with gated() as s:
        row = await s.get(RaceResult, v1_own.id)
        row.deleted_at = datetime(2026, 1, 1)
        await s.commit()
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        natural_body = (await ac.get(_URL)).json()

    assert set(gated_body) == set(natural_body) == {"points", "seasons", "caveats"}
    assert gated_body == natural_body
    assert gated_body["caveats"] == coach_body["caveats"]
    gated_v2 = gated_body["points"][0]
    assert gated_v2["category_changed"] is False
    assert gated_v2["previous_category_label"] is None
    assert gated_v2["category_change_kind"] is None
    # Métricas de campo del punto restante intactas frente a la vista del coach
    # (solo las que la familia puede ver — ver ``TestFamilyPayloadOmitsCoachOnlyGaps``).
    for key in ("position", "field_size", "timed_finishers", "percentile", "gap_to_median_pct"):
        assert gated_v2[key] == coach_v2[key]
    raw = gated_resp.text.lower()
    for hint in ("withheld", "hidden", "omit", "retenid", "pre_registration", "total"):
        assert hint not in raw


@pytest.mark.asyncio
async def test_parent_gate_closed_all_pre_registration_yields_plain_empty(client_factory, history_seeded, monkeypatch):
    # Registro por defecto = ahora → todo es previo; la respuesta debe ser
    # idéntica a la de un atleta sin resultados (ninguna temporada fantasma).
    _gate(monkeypatch, "")
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 200
    assert resp.json() == {
        "points": [],
        "seasons": [],
        "caveats": [
            "different_courses", "weather_surface", "small_fields",
            "non_finishers_excluded", "three_rider_categories",
        ],
    }


@pytest.mark.asyncio
async def test_other_parent_still_403_with_gate_open(client_factory, gated, monkeypatch):
    _gate(monkeypatch, _POLICY_LIVE)
    async with await client_factory(_user(21, UserRole.parent)) as ac:
        resp = await ac.get(_URL)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_parent_statement_budget(client_factory, gated, engine, monkeypatch):
    """Compuerta vacía: 0 queries extra; con versión: exactamente +1 (la
    resolución de la política vía ``services/privacy.py``). El cargador
    sigue en ≤ 3 en ambos casos."""
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        _gate(monkeypatch, "")
        async with count_selects(engine) as closed_empty:
            assert (await ac.get(_URL)).status_code == 200
        _gate(monkeypatch, _POLICY_LIVE)
        async with count_selects(engine) as with_version:
            assert (await ac.get(_URL)).status_code == 200
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        async with count_selects(engine) as coach:
            assert (await ac.get(_URL)).status_code == 200
    assert with_version[0] == closed_empty[0] + 1
    assert coach[0] <= 4
    # verify_athlete_access para un padre: carga del atleta + vínculo.
    assert closed_empty[0] <= 5


# ---------------------------------------------------------------------------
# T013 (feature 045, data-model §2) — variante de familia del historial.
# La brecha vs. 1.ª posición y vs. podio son SOLO de coach: en la respuesta
# de un padre las claves están AUSENTES (excluidas, no en null).
# Seed: V1 (P1=3.000.000, P3=3.200.000, atleta 3.100.000, 2.º);
#       V2 (P1=atleta 2.900.000, P3=3.100.000); campeonato sin P3.
# ---------------------------------------------------------------------------

_COACH_ONLY_KEYS = ("gap_to_winner_pct", "gap_to_podium_pct")
_FAMILY_KEYS = (
    "position", "field_size", "timed_finishers", "percentile", "gap_to_median_pct",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,user_id,club_id", [(UserRole.coach, 10, 1), (UserRole.admin, 99, None)])
async def test_staff_points_carry_winner_and_podium_gaps(client_factory, role, user_id, club_id):
    async with await client_factory(_user(user_id, role, club_id=club_id)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "all"})
    assert resp.status_code == 200
    points = {p["event_id"]: p for p in resp.json()["points"]}
    assert set(points) == {_EVENT_V1, _EVENT_V2, _EVENT_CHAMP}
    for point in points.values():
        for key in _COACH_ONLY_KEYS:
            assert key in point
    assert points[_EVENT_V1]["gap_to_winner_pct"] == 3.3  # (3.1 − 3.0) ÷ 3.0
    assert points[_EVENT_V1]["gap_to_podium_pct"] == -3.1  # (3.1 − 3.2) ÷ 3.2
    assert points[_EVENT_V2]["gap_to_winner_pct"] == 0.0
    assert points[_EVENT_V2]["gap_to_podium_pct"] == -6.5  # (2.9 − 3.1) ÷ 3.1
    # Sin tiempo oficial de P3 el coach ve el campo (con null), no ausente.
    assert points[_EVENT_CHAMP]["gap_to_podium_pct"] is None


@pytest.mark.asyncio
async def test_parent_points_omit_winner_and_podium_gaps(client_factory, history_seeded):
    await _set_registration(history_seeded, datetime(2023, 12, 1))
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "all"})
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert {p["event_id"] for p in points} == {_EVENT_V1, _EVENT_V2, _EVENT_CHAMP}
    for point in points:
        for key in _COACH_ONLY_KEYS:
            assert key not in point  # excluida, no nulled
        for key in _FAMILY_KEYS:
            assert key in point


@pytest.mark.asyncio
async def test_parent_payload_never_mentions_winner_or_podium_fields(client_factory, history_seeded):
    """Ni siquiera como texto: la respuesta cruda no lleva rastro alguno."""
    await _set_registration(history_seeded, datetime(2023, 12, 1))
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "all"})
    raw = resp.text
    for fragment in ("gap_to_winner", "gap_to_podium", "gap_pct", "gap_to_p1", "gap_to_p3"):
        assert fragment not in raw


@pytest.mark.asyncio
async def test_parent_keeps_the_family_metrics_with_the_same_values_as_the_coach(
    client_factory, history_seeded
):
    await _set_registration(history_seeded, datetime(2023, 12, 1))
    async with await client_factory(_user(10, UserRole.coach, club_id=1)) as ac:
        coach_points = {p["event_id"]: p for p in (await ac.get(_URL)).json()["points"]}
    async with await client_factory(_user(20, UserRole.parent)) as ac:
        parent_points = {p["event_id"]: p for p in (await ac.get(_URL)).json()["points"]}
    assert set(parent_points) == set(coach_points)
    for event_id, parent_point in parent_points.items():
        # Mismo punto menos las claves de coach: un solo motor, dos audiencias.
        expected = {k: v for k, v in coach_points[event_id].items() if k not in _COACH_ONLY_KEYS}
        assert parent_point == expected


@pytest.mark.asyncio
async def test_other_parent_is_denied_and_receives_no_points(client_factory):
    async with await client_factory(_user(21, UserRole.parent)) as ac:
        resp = await ac.get(_URL, params={"series_kind": "all"})
    assert resp.status_code == 403
    assert "points" not in resp.json()
    assert "gap_to_" not in resp.text
