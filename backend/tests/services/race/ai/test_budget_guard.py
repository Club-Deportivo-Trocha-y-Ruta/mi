"""Tests para ``app.services.race.ai.budget_guard`` (F8A).

Cobertura mínima exigida (≥5 tests):
- budget bajo límite → no raise
- budget excedido → raise BudgetExceededError
- notificación emitida al exceder
- cooldown suprime notificaciones repetidas
- threshold respeta override (settings vs argumento)
- query SQL es la esperada (mismo shape que /ai-usage)
- DB error → no bloquea (best-effort)
- threshold via settings.race_ai_budget_usd_30d
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from app.services.race.ai.budget_guard import (
    BudgetExceededError,
    _reset_cooldown_for_tests,
    _sum_cost_last_30d,
    check_budget,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fake session mínima para el guard
# ---------------------------------------------------------------------------


class _BudgetRow:
    """Row-like con _mapping (estilo SQLAlchemy 2.x)."""

    def __init__(self, total: float):
        self._mapping = {"total": total}
        self.total = total

    def __getitem__(self, idx: int) -> Any:
        return self.total


class _BudgetResult:
    def __init__(self, total: float | None):
        self._row = _BudgetRow(total) if total is not None else None

    def first(self) -> _BudgetRow | None:
        return self._row

    def fetchall(self) -> list[_BudgetRow]:
        return [self._row] if self._row else []


class FakeBudgetSession:
    """AsyncSession mock que devuelve un total fijo (o lanza excepción)."""

    def __init__(self, total_usd: float | None = 0.0, raises: Exception | None = None):
        self.total = total_usd
        self.raises = raises
        self.queries: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        sql = getattr(stmt, "text", str(stmt))
        self.queries.append((sql, params or {}))
        if self.raises is not None:
            raise self.raises
        return _BudgetResult(self.total)


@pytest_asyncio.fixture(autouse=True)
async def _reset_cooldown():
    """Reset cooldown antes y después de cada test (state módulo-global)."""
    await _reset_cooldown_for_tests()
    yield
    await _reset_cooldown_for_tests()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_bajo_limite_no_raise():
    """Si el gasto está debajo del límite, no debe haber excepción."""
    session = FakeBudgetSession(total_usd=5.0)
    # No raise → método retorna None.
    result = await check_budget(session, max_cost_usd_30d=20.0)
    assert result is None


async def test_excede_limite_raise():
    """Si el gasto >= límite, raise BudgetExceededError con valores correctos."""
    session = FakeBudgetSession(total_usd=25.50)
    with pytest.raises(BudgetExceededError) as exc_info:
        await check_budget(session, max_cost_usd_30d=20.0)
    assert exc_info.value.current_usd == 25.50
    assert exc_info.value.budget_usd == 20.0
    # Mensaje útil para logs / 503 detail.
    assert "25.5" in str(exc_info.value)
    assert "20" in str(exc_info.value)


async def test_exactamente_en_limite_raise():
    """Edge: gasto == límite debe bloquear (cumple ``>=``)."""
    session = FakeBudgetSession(total_usd=20.0)
    with pytest.raises(BudgetExceededError):
        await check_budget(session, max_cost_usd_30d=20.0)


async def test_notificacion_se_dispara_al_exceder(caplog):
    """Al exceder, se loggea ERROR (notificación via logger en MVP)."""
    import logging

    session = FakeBudgetSession(total_usd=100.0)
    with caplog.at_level(logging.ERROR, logger="app.services.race.ai.budget_guard"):
        with pytest.raises(BudgetExceededError):
            await check_budget(session, max_cost_usd_30d=20.0)
    # Debe haber un log ERROR con el dato del exceso.
    overrun_logs = [r for r in caplog.records if "race_ai_budget_exceeded" in r.message]
    assert len(overrun_logs) >= 1
    assert "100" in overrun_logs[0].message


async def test_cooldown_suprime_segunda_notificacion(caplog):
    """Dentro del cooldown (1h), la 2da llamada NO debe re-loggear el ERROR."""
    import logging

    session = FakeBudgetSession(total_usd=100.0)

    with caplog.at_level(logging.ERROR, logger="app.services.race.ai.budget_guard"):
        with pytest.raises(BudgetExceededError):
            await check_budget(session, max_cost_usd_30d=20.0)
        first_count = sum(
            1 for r in caplog.records if "race_ai_budget_exceeded" in r.message
        )

        # Segunda invocación inmediata: aún raise pero NO emite nuevo log error.
        with pytest.raises(BudgetExceededError):
            await check_budget(session, max_cost_usd_30d=20.0)
        second_count = sum(
            1 for r in caplog.records if "race_ai_budget_exceeded" in r.message
        )

    assert first_count == 1
    assert second_count == 1, "Cooldown debe suprimir la 2da notificación"


async def test_threshold_via_settings(monkeypatch):
    """Si no se pasa max_cost_usd_30d, lee desde settings.race_ai_budget_usd_30d."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 5.0)
    session = FakeBudgetSession(total_usd=10.0)
    with pytest.raises(BudgetExceededError) as exc_info:
        await check_budget(session)  # sin override
    assert exc_info.value.budget_usd == 5.0


async def test_threshold_override_argumento_pisa_settings(monkeypatch):
    """El argumento explícito tiene precedencia sobre settings."""
    from app.config import settings

    monkeypatch.setattr(settings, "race_ai_budget_usd_30d", 1.0)
    session = FakeBudgetSession(total_usd=5.0)
    # Override a 100 → no raise aunque settings diga 1.
    await check_budget(session, max_cost_usd_30d=100.0)


async def test_query_sql_es_la_esperada():
    """La query usa la MISMA extracción que el endpoint admin /ai-usage."""
    session = FakeBudgetSession(total_usd=0.0)
    await check_budget(session, max_cost_usd_30d=20.0)
    assert len(session.queries) == 1
    sql, params = session.queries[0]
    # Debe leer desde athlete_ai_insights y extraer cost_usd_total del JSON.
    assert "athlete_ai_insights" in sql
    assert "cost_usd_total" in sql
    assert "metrics_snapshot_json" in sql
    assert "cutoff" in params  # debe filtrar por ventana


async def test_db_error_no_bloquea(caplog):
    """Si la query falla, loggea WARNING y deja pasar (best-effort)."""
    import logging

    session = FakeBudgetSession(raises=RuntimeError("db unreachable"))
    with caplog.at_level(logging.WARNING, logger="app.services.race.ai.budget_guard"):
        # No raise: pasa silenciosamente.
        await check_budget(session, max_cost_usd_30d=20.0)
    warns = [r for r in caplog.records if "query falló" in r.message]
    assert len(warns) >= 1


async def test_helper_sum_cost_retorna_float():
    """``_sum_cost_last_30d`` devuelve float (no None / Decimal opaco)."""
    session = FakeBudgetSession(total_usd=3.14)
    result = await _sum_cost_last_30d(session)
    assert isinstance(result, float)
    assert result == 3.14


async def test_helper_sum_cost_sin_filas_retorna_cero():
    """Si la DB no devuelve filas, retorna 0.0 (no None ni excepción)."""
    session = FakeBudgetSession(total_usd=None)  # FakeResult.first() → None
    result = await _sum_cost_last_30d(session)
    assert result == 0.0
