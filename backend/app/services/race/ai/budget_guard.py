"""Budget guard runtime para race-analyst (Fase 8A).

Responsabilidad
---------------
Antes de iniciar un nuevo run (en ``POST /api/race-analysis/runs``),
chequea que el gasto acumulado de IA en los últimos 30 días no supere
el presupuesto configurado (``settings.race_ai_budget_usd_30d``,
default $20).

Diseño
------
- **Fuente de verdad**: misma query que el endpoint admin ``/ai-usage``
  (extracción de ``cost_usd_total`` desde ``metrics_snapshot_json``).
  Esto garantiza que el guard y el panel de admin SIEMPRE coincidan.
- **Bloqueo "hard"**: si excede, raise :class:`BudgetExceededError` y
  el router lo traduce a ``503 Service Unavailable`` con mensaje claro.
- **Runs en curso completan**: el guard sólo bloquea NUEVOS runs. Los
  runs ya pasados el chequeo (incluyendo HITL resume) terminan
  normalmente — racional: cancelar a mitad camino desperdicia el costo
  ya incurrido y deja al coach sin output.
- **Best-effort en errores**: si la query falla (DB caída, schema
  diferente), el guard LOGUEA y deja pasar. Nunca bloqueamos runs por
  errores de telemetría — la spec del proyecto prioriza disponibilidad
  sobre auditoría perfecta.
- **Notificación una sola vez** por ventana: usamos un *cooldown*
  módulo-global de 1h para no spammear al coach si llegan 50 requests
  cuando el budget ya se excedió. Multi-worker (gunicorn -w 4) podría
  generar hasta N notificaciones; aceptable para MVP.

Notas operativas
----------------
- Cambiar el threshold: setear ``RACE_AI_BUDGET_USD_30D`` en Render.
  El validator de Settings recarga al próximo restart.
- Reset manual del cooldown: no expuesto (esperar 1h o reiniciar
  servicio). Documentado en runbook-ops.md §3.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BudgetExceededError(RuntimeError):
    """El presupuesto mensual de IA fue excedido. Router → 503."""

    def __init__(self, current_usd: float, budget_usd: float) -> None:
        super().__init__(
            f"race_ai_budget_exceeded (gastado=${current_usd:.4f}, "
            f"limite=${budget_usd:.2f})"
        )
        self.current_usd = current_usd
        self.budget_usd = budget_usd


# ---------------------------------------------------------------------------
# Cooldown de notificación (módulo-global)
# ---------------------------------------------------------------------------

_notification_cooldown_secs = 3600  # 1h
_last_notification_at: Optional[datetime] = None
_cooldown_lock = asyncio.Lock()


async def _should_notify() -> bool:
    """True si pasaron >= cooldown segundos desde la última notificación."""
    global _last_notification_at
    async with _cooldown_lock:
        now = datetime.now(timezone.utc)
        if (
            _last_notification_at is None
            or (now - _last_notification_at).total_seconds() >= _notification_cooldown_secs
        ):
            _last_notification_at = now
            return True
        return False


async def _reset_cooldown_for_tests() -> None:
    """Reset SOLO para tests — no exportado."""
    global _last_notification_at
    async with _cooldown_lock:
        _last_notification_at = None


# ---------------------------------------------------------------------------
# Query helper
# ---------------------------------------------------------------------------


# Misma extracción que el endpoint admin /ai-usage (router race_analysis.py).
# Si en el futuro se migra a columna dedicada ``athlete_ai_insights.cost_usd``,
# actualizar AMBOS lugares juntos para mantener consistencia.
_QUERY_SUM_COST_30D = """
SELECT
  COALESCE(
    SUM(JSON_EXTRACT(metrics_snapshot_json, '$.aggregate.cost_usd_total')),
    0
  ) AS total
FROM athlete_ai_insights
WHERE generated_at >= :cutoff
"""


async def _sum_cost_last_30d(db: AsyncSession) -> float:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    result = await db.execute(text(_QUERY_SUM_COST_30D), {"cutoff": cutoff})

    # SQLAlchemy 2.x: result.first() devuelve Row o None. Defensive porque
    # FakeSession en tests puede devolver wrappers ligeramente distintos.
    first = getattr(result, "first", lambda: None)()
    if first is None:
        rows = result.fetchall() if hasattr(result, "fetchall") else []
        first = rows[0] if rows else None

    if first is None:
        return 0.0

    if hasattr(first, "_mapping"):
        raw = first._mapping.get("total")
    else:
        raw = getattr(first, "total", None) or first[0]

    try:
        return float(raw or 0.0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Notificación
# ---------------------------------------------------------------------------


async def _notify_overrun(current_usd: float, budget_usd: float) -> None:
    """Best-effort: log + (futuro) email al coach + admin.

    MVP: solo log. El cableado real al NotificationService se hace
    cuando se defina un template ``race_ai_budget_alert`` en el
    registry. Mientras tanto, el log es de nivel ``ERROR`` y queda
    capturado por la observabilidad de Render.

    El cooldown garantiza que esta función se llame a lo sumo 1 vez
    por hora — los logs no se inundan ni se enviarían 100 emails.
    """
    if not await _should_notify():
        logger.debug(
            "budget_guard: notificación suprimida por cooldown "
            "(spent=$%.4f, limit=$%.2f)",
            current_usd,
            budget_usd,
        )
        return

    # Log estructurado — captado por monitoreo de Render + buscable
    # por palabras clave en logs.
    logger.error(
        "race_ai_budget_exceeded: gasto últimos 30d = $%.4f USD, "
        "presupuesto = $%.2f USD. Nuevos runs bloqueados (503) hasta "
        "que el costo caiga o se aumente RACE_AI_BUDGET_USD_30D. "
        "Runs en curso completan normalmente.",
        current_usd,
        budget_usd,
    )

    # Cuando se cablee email real, este es el lugar:
    #
    #   from app.services.notification import NotificationService
    #   from app.schemas.notification import NotificationRequest, ...
    #   await notification_service.send(NotificationRequest(
    #       recipient=NotificationRecipient(email=coach_email, name=...),
    #       template=NotificationTemplate.RACE_AI_BUDGET_ALERT,  # nuevo
    #       context={"current_usd": current_usd, "budget_usd": budget_usd},
    #   ))
    #
    # Implementación diferida porque agregar template Jinja + entrada en
    # registry es scope mayor; el log + alerta en monitoring cubre F8A.


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


async def check_budget(
    db: AsyncSession,
    max_cost_usd_30d: float | None = None,
) -> None:
    """Verifica que el gasto acumulado de IA no haya excedido el presupuesto.

    Args:
        db: Sesión async para query. Debe estar en transacción válida
            (commit no requerido — solo lee).
        max_cost_usd_30d: Override del threshold (útil para tests).
            Si None, usa ``settings.race_ai_budget_usd_30d``.

    Raises:
        BudgetExceededError: si gasto >= threshold. El router traduce
            a 503 Service Unavailable.

    Nunca raise por errores de DB/telemetría:
        Si la query falla, loggea ``WARNING`` y retorna OK. Racional:
        bloquear runs por un error de monitoring es peor que dejar
        pasar uno que excede levemente el budget.
    """
    if max_cost_usd_30d is None:
        from app.config import settings

        max_cost_usd_30d = settings.race_ai_budget_usd_30d

    try:
        current = await _sum_cost_last_30d(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "budget_guard: query falló (%s) — dejando pasar el run",
            type(exc).__name__,
        )
        return

    if current >= max_cost_usd_30d:
        # Notificación best-effort (no bloquea si falla).
        try:
            await _notify_overrun(current, max_cost_usd_30d)
        except Exception:  # noqa: BLE001
            logger.exception("budget_guard: notify_overrun falló (no crítico)")
        raise BudgetExceededError(current, max_cost_usd_30d)


__all__ = [
    "BudgetExceededError",
    "check_budget",
]
