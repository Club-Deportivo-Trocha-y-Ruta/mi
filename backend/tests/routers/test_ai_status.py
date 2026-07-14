"""Tests para `GET /api/ai/status` (feature 033 — hint pre-lanzamiento).

Cobertura (contracts/ai-identity.md §4, tasks.md T005):
- Happy path: ok/warning/exhausted derivados de sumas de costo de 30d
  sembradas (misma fuente que `check_budget()`/`admin_ai_usage()`).
- RBAC: parent → 403; admin/coach → 200 (mismo patrón `_coach_or_admin`
  que `race_analysis.py:115`, ahora replicado en `app/routers/ai.py`).
- Property test (carga normativa para SC-004): `budget_status ==
  "exhausted"` si y solo si un lanzamiento real subsecuente devolvería
  503 vía `check_budget()`. Mantiene el hint y el bloqueo duro sin
  divergir nunca. Usamos un barrido determinista de pares (costo,
  presupuesto) en vez de `hypothesis` full property-based — mismo
  criterio que `test_race_analysis_privacy.py` documenta (test async,
  determinismo + velocidad).
- Privacidad: el payload no lleva identificadores de atletas.
"""

from __future__ import annotations

import pytest

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.user import UserRole
from app.routers import ai as ai_router_mod
from app.services.race.ai.budget_guard import BudgetExceededError, check_budget
from tests.routers.conftest import FakeSession, make_user

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures locales — `app.routers.ai._coach_or_admin` es un objeto
# `Depends()` DISTINTO del homónimo en `race_analysis.py`; los fixtures
# compartidos en `tests/routers/conftest.py` solo overridean ese último,
# así que para este endpoint basta (y es más simple) con overridear
# `get_current_user` y dejar que el `require_role` real haga el 403.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_db() -> FakeSession:
    return FakeSession()


@pytest.fixture
def _client_as(client, fake_db):
    def _make(role: UserRole, user_id: int = 1):
        async def _override_db():
            yield fake_db

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: make_user(role, user_id=user_id)
        return client

    yield _make
    app.dependency_overrides.clear()


def _seed_cost(fake_db: FakeSession, cost_usd: float) -> None:
    """Siembra un único insight cuyo costo agregado suma `cost_usd`."""
    fake_db.seed_insight(cost_total=cost_usd, latency_total=20_000)


# ---------------------------------------------------------------------------
# Happy path — ok / warning / exhausted
# ---------------------------------------------------------------------------


class TestBudgetStatusHappyPath:
    async def test_ok_cuando_gasto_bajo(self, _client_as, fake_db, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 20.0)
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        _seed_cost(fake_db, 5.0)  # remaining = round((1 - 5/20)*100) = 75%

        resp = await _client_as(UserRole.coach).get("/api/ai/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["budget_status"] == "ok"
        assert body["budget_remaining_pct"] == 75
        assert body["concurrency_available"] is True
        assert body["est_wait_seconds"] == 20  # 20_000ms → 20s

    async def test_warning_cuando_gasto_alto(self, _client_as, fake_db, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 20.0)
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        _seed_cost(fake_db, 17.0)  # remaining = round((1 - 17/20)*100) = 15%

        resp = await _client_as(UserRole.coach).get("/api/ai/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["budget_status"] == "warning"
        assert body["budget_remaining_pct"] == 15

    async def test_exhausted_cuando_gasto_iguala_presupuesto(
        self, _client_as, fake_db, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 20.0)
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        _seed_cost(fake_db, 20.0)  # remaining = 0 → exhausted (edge >=)

        resp = await _client_as(UserRole.admin).get("/api/ai/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["budget_status"] == "exhausted"
        assert body["budget_remaining_pct"] == 0

    async def test_exhausted_cuando_gasto_excede_presupuesto(
        self, _client_as, fake_db, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 20.0)
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        _seed_cost(fake_db, 45.0)  # gasto > presupuesto: pct clamped a 0, no negativo

        resp = await _client_as(UserRole.admin).get("/api/ai/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["budget_status"] == "exhausted"
        assert body["budget_remaining_pct"] == 0

    async def test_concurrency_available_false_no_afecta_budget_status(
        self, _client_as, fake_db, monkeypatch
    ):
        """Backpressure es transitorio — nunca cambia budget_status."""
        from app.config import settings

        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 20.0)
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: False)
        _seed_cost(fake_db, 1.0)

        resp = await _client_as(UserRole.coach).get("/api/ai/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["budget_status"] == "ok"
        assert body["concurrency_available"] is False


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class TestRBAC:
    async def test_parent_403(self, _client_as, monkeypatch):
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        resp = await _client_as(UserRole.parent, user_id=5).get("/api/ai/status")
        assert resp.status_code == 403

    async def test_coach_200(self, _client_as, monkeypatch):
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        resp = await _client_as(UserRole.coach, user_id=10).get("/api/ai/status")
        assert resp.status_code == 200

    async def test_admin_200(self, _client_as, monkeypatch):
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        resp = await _client_as(UserRole.admin, user_id=1).get("/api/ai/status")
        assert resp.status_code == 200

    async def test_sin_auth_401_o_403(self, client):
        # Sin override — HTTPBearer real exige token.
        resp = await client.get("/api/ai/status")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Property test — budget_status=="exhausted" <=> check_budget() raise
# ---------------------------------------------------------------------------


# Barrido determinista de pares (costo_gastado, presupuesto), cubriendo:
# muy por debajo, justo debajo (warning), exactamente igual (edge >=),
# ligeramente arriba, y muy por encima del presupuesto.
_COST_BUDGET_PAIRS = [
    (0.0, 20.0),
    (1.0, 20.0),
    (4.0, 20.0),
    (16.0, 20.0),
    (16.01, 20.0),
    (19.99, 20.0),
    (20.0, 20.0),
    (20.01, 20.0),
    (25.5, 20.0),
    (100.0, 20.0),
    (0.0, 5.0),
    (4.99, 5.0),
    (5.0, 5.0),
    (5.01, 5.0),
    (2.5, 1.0),
    (0.0, 1.0),
]


class TestBudgetStatusMatchesRealEnforcement:
    @pytest.mark.parametrize("cost_usd, budget_usd", _COST_BUDGET_PAIRS)
    async def test_exhausted_iff_launch_would_503(
        self, _client_as, fake_db, monkeypatch, cost_usd, budget_usd
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", budget_usd)
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        _seed_cost(fake_db, cost_usd)

        resp = await _client_as(UserRole.coach).get("/api/ai/status")
        assert resp.status_code == 200
        reported_exhausted = resp.json()["budget_status"] == "exhausted"

        # "Un lanzamiento real subsecuente" = lo que hace el router real
        # de `race_analysis.py` antes de arrancar un run: `check_budget()`
        # contra la MISMA fuente de gasto (una sesión fake independiente
        # con el mismo costo sembrado, para no compartir estado de query
        # log con la sesión que atendió la request HTTP).
        launch_session = FakeSession()
        launch_session.seed_insight(cost_total=cost_usd, latency_total=1)
        would_503 = False
        try:
            await check_budget(launch_session, max_cost_usd_30d=budget_usd)
        except BudgetExceededError:
            would_503 = True

        assert reported_exhausted == would_503, (
            f"cost={cost_usd} budget={budget_usd}: "
            f"status endpoint dice exhausted={reported_exhausted} pero "
            f"check_budget() real {'SÍ' if would_503 else 'NO'} bloquearía"
        )


# ---------------------------------------------------------------------------
# Privacidad — ningún identificador de atleta en el payload
# ---------------------------------------------------------------------------


class TestNoAthleteIdentifiers:
    async def test_payload_no_expone_identificadores(self, _client_as, fake_db, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 20.0)
        monkeypatch.setattr(ai_router_mod, "has_capacity", lambda: True)
        fake_db.seed_insight(athlete_id=42, cost_total=1.0, latency_total=5_000)

        resp = await _client_as(UserRole.coach).get("/api/ai/status")
        assert resp.status_code == 200
        body = resp.json()

        # Contrato exacto — exactamente estos 4 campos, nada de
        # athlete_id / nombres / ningún otro campo agregado a mano.
        assert set(body.keys()) == {
            "budget_status",
            "budget_remaining_pct",
            "concurrency_available",
            "est_wait_seconds",
        }
        serialized = str(body)
        assert "42" not in serialized  # el athlete_id sembrado no debe fugarse
