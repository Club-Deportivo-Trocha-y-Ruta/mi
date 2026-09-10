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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BudgetExceededError(RuntimeError):
    """El presupuesto de IA de los últimos 30 días fue excedido. Router → 503."""

    def __init__(self, current_usd: float, budget_usd: float) -> None:
        super().__init__(
            f"race_ai_budget_exceeded (gastado=${current_usd:.4f}, "
            f"limite=${budget_usd:.2f})"
        )
        self.current_usd = current_usd
        self.budget_usd = budget_usd

    @property
    def user_message(self) -> str:
        """Copia única del rechazo por presupuesto (contrato §8).

        Los cuatro sitios que traducen este error a un 503 usaban su propia
        f-string; pasada la regla de tres (Constitución I) viven todos de
        esta propiedad. El texto nombra el período (ventana móvil de 30 días,
        no "mensual") y aclara que los análisis en curso terminan, como pide
        FR-029. Conserva la palabra inicial "Presupuesto" y los dos montos
        para no romper las aserciones existentes.
        """
        return (
            f"Presupuesto de IA del club agotado para los últimos 30 días: "
            f"${self.current_usd:.4f} de ${self.budget_usd:.4f} USD. "
            "Los análisis en curso terminan normalmente; los nuevos se "
            "habilitan cuando el gasto salga de la ventana de 30 días o "
            "cuando el administrador aumente el presupuesto."
        )


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
# Gasto por entrenador (FR-029, contrato scope-ai-imports §7.1)
# ---------------------------------------------------------------------------


#: Etiqueta del cubo sin atribución: insights cuyo run ya no existe o que
#: nacieron sin ``generated_by_user_id``.
UNATTRIBUTED_LABEL = "Sin atribuir"


@dataclass(frozen=True)
class UserSpend:
    """Una fila de gasto de IA atribuido a un miembro del staff.

    Dataclass plana a propósito: un módulo de servicios no importa
    ``app.schemas``. El router la traduce a ``AIUsageByCoach``.

    Privacidad (Ley 1581): ``display_name`` es SIEMPRE staff adulto
    (entrenador o administrador). Ningún menor aparece en esta superficie.
    """

    user_id: Optional[int]  # None = cubo sin atribuir
    display_name: str
    cost_usd_total: float
    run_count: int


# Misma ventana y misma extracción JSON que ``_QUERY_SUM_COST_30D``; si esa
# extracción migra a una columna ``cost_usd`` dedicada, los tres lugares se
# mueven juntos (ver la nota de arriba).
#
# ``COALESCE(ar.requested_by_user_id, i.generated_by_user_id)``: la clave de
# atribución es quien lanzó el run, pero ``athlete_ai_insights.agent_run_id``
# es nullable, así que un JOIN interno perdería filas en silencio y rompería
# la invariante de reconciliación con ``_sum_cost_last_30d``.
_QUERY_SPEND_BY_USER = """
SELECT COALESCE(ar.requested_by_user_id, i.generated_by_user_id) AS uid,
       COUNT(*)                                                  AS run_count,
       COALESCE(SUM(JSON_EXTRACT(i.metrics_snapshot_json,
                                 '$.aggregate.cost_usd_total')), 0) AS cost
  FROM athlete_ai_insights i
  LEFT JOIN agent_runs ar ON ar.id = i.agent_run_id
 WHERE i.generated_at >= :cutoff
 GROUP BY uid
 ORDER BY cost DESC
"""

_QUERY_RESOLVE_NAMES = """
SELECT id, first_name, last_name FROM users WHERE id IN :ids
"""


def _row_get(row: object, name: str, idx: int) -> object:
    """Lee una columna por nombre, con respaldo posicional para fakes."""
    mapping = getattr(row, "_mapping", None)
    if mapping is not None and name in mapping:
        return mapping[name]
    if hasattr(row, name):
        return getattr(row, name)
    try:
        return row[idx]  # type: ignore[index]
    except Exception:  # noqa: BLE001
        return None


async def spend_by_user_last_30d(
    db: AsyncSession, *, days: int = 30
) -> list["UserSpend"]:
    """Gasto de IA de la ventana móvil, agrupado por quien lanzó el análisis.

    Dos queries fijas — la agregación y una resolución de nombres por lote —
    nunca N+1 (§10). El cubo sin atribuir se etiqueta ``"Sin atribuir"``.

    Invariante de reconciliación (FR-029, US6 AC4): la suma de
    ``cost_usd_total`` de las filas devueltas iguala ``_sum_cost_last_30d``
    dentro de ``1e-6`` para ``days=30``.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(text(_QUERY_SPEND_BY_USER), {"cutoff": cutoff})
    rows = result.fetchall() if hasattr(result, "fetchall") else []

    buckets: list[tuple[Optional[int], int, float]] = []
    for row in rows:
        raw_uid = _row_get(row, "uid", 0)
        try:
            uid = int(raw_uid) if raw_uid is not None else None
        except (TypeError, ValueError):
            uid = None
        try:
            run_count = int(_row_get(row, "run_count", 1) or 0)
        except (TypeError, ValueError):
            run_count = 0
        try:
            cost = float(_row_get(row, "cost", 2) or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        buckets.append((uid, run_count, cost))

    names = await _resolve_staff_names(db, {uid for uid, _, _ in buckets if uid is not None})

    return [
        UserSpend(
            user_id=uid,
            display_name=(
                UNATTRIBUTED_LABEL if uid is None else names.get(uid, "Usuario no disponible")
            ),
            cost_usd_total=cost,
            run_count=run_count,
        )
        for uid, run_count, cost in buckets
    ]


async def _resolve_staff_names(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    """``{user_id: "Nombre Apellido"}`` en una sola query por lote (§4.1).

    Un id que no resuelve NO entra al diccionario: quien llama pone
    ``"Usuario no disponible"``, nunca ``user#7`` (FR-013).
    """
    if not ids:
        return {}
    stmt = text(_QUERY_RESOLVE_NAMES).bindparams(bindparam("ids", expanding=True))
    result = await db.execute(stmt, {"ids": sorted(ids)})
    rows = result.fetchall() if hasattr(result, "fetchall") else []
    names: dict[int, str] = {}
    for row in rows:
        raw_id = _row_get(row, "id", 0)
        if raw_id is None:
            continue
        first = _row_get(row, "first_name", 1)
        last = _row_get(row, "last_name", 2)
        full = " ".join(str(p).strip() for p in (first, last) if p).strip()
        if full:
            names[int(raw_id)] = full
    return names


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
    "UNATTRIBUTED_LABEL",
    "BudgetExceededError",
    "UserSpend",
    "check_budget",
    "spend_by_user_last_30d",
]
