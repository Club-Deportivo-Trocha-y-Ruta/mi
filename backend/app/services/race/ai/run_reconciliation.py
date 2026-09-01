"""Reconciliación de runs huérfanos del pipeline agéntico (specs/036, US3/T016).

Contexto
========
``services/race/ai/runner.py`` mantiene el registro de runs activos **en
memoria** del proceso (``_active_runs: dict[run_id, asyncio.Task]``). Render
free tier redeploya el backend en cada push a ``main`` (y además apaga la
instancia por inactividad): el proceso Python muere y ese registro
desaparece con él. Cualquier fila de ``agent_runs`` que haya quedado en
``running`` o ``awaiting_hitl`` en ese momento queda huérfana para siempre
— nadie va a completarla — y el cliente (``useRaceRun.ts``) sigue haciendo
polling contra un run que ya no existe.

Este módulo se invoca una sola vez al arrancar la app (``main.py::lifespan``,
antes de aceptar tráfico) y cierra esas filas con ``status='failed'`` y un
``error_message`` honesto en español.

Por qué un umbral de edad y no "todo lo que esté running al boot"
===================================================================
En un proceso single-worker (documentado así en ``runner.py``), cualquier
fila ``running``/``awaiting_hitl`` en el momento del boot pertenece, por
construcción, a un proceso anterior — el registro en memoria de ESTE
proceso arranca vacío. En teoría no haría falta umbral. Se usa uno de
todos modos como defensa en profundidad, para no competir nunca con un run
legítimo si en el futuro esto corre en más de un worker, o si el arranque
se dispara más de una vez dentro del mismo proceso (tests). El default es
generoso: ≥2x la duración máxima esperada del pipeline. Un lanzamiento de
hasta 4 válidas (tope actual, ver ``routers/athlete_race_analysis.py``)
con los nodos ``analyst``/``critic`` agotando sus 3 reintentos cada uno
(``services/race/ai/retry.py``, timeout de ``ai_timeout_seconds`` por
intento) puede tomar, en el peor caso, del orden de 12-15 minutos — de ahí
el default de 30 minutos (``settings.race_ai_orphan_run_threshold_minutes``).

Por qué el mismo umbral también cierra ``awaiting_hitl``
=========================================================
El checkpoint de LangGraph (``./data/langgraph_state.sqlite``) vive en el
filesystem efímero de Render free tier (specs/036/research.md R2): no
sobrevive un deploy. Una decisión HITL pendiente en el momento del reinicio
queda irrecuperable sin importar cuánto tiempo llevara esperando al
coach — por eso no se le da un margen de gracia distinto al de ``running``,
y por eso su mensaje de error es explícito sobre la causa (no es un simple
timeout: la espera en sí se perdió).

Convención de acceso a DB
=========================
Igual que el resto de ``services/race/ai/`` (nodos del grafo), se usa
``db.get_session()`` en vez de ``Depends(get_db)`` porque este código corre
fuera del ciclo request/response de FastAPI (arranque de la app). El
``db_factory`` ya está configurado en ese momento — ``main.py`` lo hace a
nivel de módulo (``set_db_factory(AsyncSessionLocal)``), antes de que
``lifespan`` se ejecute.

SQL crudo contra ``agent_runs`` porque el modelo ORM
(``app.models.agent_run.AgentRun``) sólo mapea un subconjunto de columnas
—no incluye ``error_message``— por diseño documentado en ese mismo módulo.

Nunca bloquea ni tumba el arranque
==================================
Cualquier fallo (DB caída, tabla inexistente en un entorno a medio migrar,
lo que sea) se loguea y se traga: esta reconciliación es limpieza
best-effort, no un requisito para servir tráfico.

Privacidad: no se lee ni se loguea nada específico de un atleta o menor —
sólo el conteo de filas afectadas.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

ORPHAN_RUNNING_ERROR_MESSAGE = (
    "Este análisis se interrumpió porque el servidor se reinició antes de "
    "terminar. Por favor, inicia el análisis nuevamente."
)
"""``error_message`` para runs huérfanos que estaban en ``running``."""

ORPHAN_AWAITING_HITL_ERROR_MESSAGE = (
    "Este análisis quedó esperando tu revisión cuando el servidor se "
    "reinició, y esa espera no se pudo conservar: en este plan de hosting, "
    "el progreso guardado no sobrevive a un reinicio. Por favor, inicia el "
    "análisis nuevamente para revisarlo de nuevo."
)
"""``error_message`` para runs huérfanos que estaban en ``awaiting_hitl``.

Distinto del anterior a propósito (R2 en specs/036/research.md): no es un
timeout cualquiera, es una pérdida honesta y explicada de una decisión
pendiente del coach.
"""

_ORPHAN_RECONCILE_SQL = text(
    """
    UPDATE agent_runs
    SET status = 'failed',
        error_message = CASE
            WHEN status = 'awaiting_hitl' THEN :em_hitl
            ELSE :em_running
        END,
        finished_at = :fa
    WHERE status IN ('running', 'awaiting_hitl')
      AND started_at < :cutoff
    """
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def reconcile_orphan_runs(
    threshold_minutes: int | None = None,
    *,
    now: datetime | None = None,
) -> int:
    """Marca ``failed`` los runs ``running``/``awaiting_hitl`` huérfanos.

    Punto de entrada usado por ``main.py::lifespan``. Abre y cierra su
    propia sesión (vía ``services.race.ai.db.get_session()``) y **nunca
    lanza**: cualquier excepción se loguea y la función retorna ``0``.

    Args:
        threshold_minutes: edad mínima (minutos, por ``started_at``) para
            considerar una fila huérfana. ``None`` → usa
            ``settings.race_ai_orphan_run_threshold_minutes``.
        now: override de "ahora" para tests. ``None`` → UTC real.

    Returns:
        Número de filas reconciliadas. ``0`` también en caso de error (no
        hay forma de distinguir "no había huérfanos" de "falló la query"
        desde el valor de retorno — el log sí distingue, vía
        ``logger.exception`` en el segundo caso).
    """
    from app.config import settings
    from app.services.race.ai.db import get_session

    threshold = (
        threshold_minutes
        if threshold_minutes is not None
        else settings.race_ai_orphan_run_threshold_minutes
    )
    moment = now or _utcnow()
    cutoff = moment - timedelta(minutes=threshold)

    try:
        async with get_session() as db:
            result = await db.execute(
                _ORPHAN_RECONCILE_SQL,
                {
                    "em_running": ORPHAN_RUNNING_ERROR_MESSAGE,
                    "em_hitl": ORPHAN_AWAITING_HITL_ERROR_MESSAGE,
                    "fa": moment,
                    "cutoff": cutoff,
                },
            )
            count = int(result.rowcount or 0)
            await db.commit()
    except Exception:  # noqa: BLE001 — best-effort, nunca debe tumbar el arranque.
        logger.exception("race_orphan_run_reconciliation_failed")
        return 0

    if count:
        logger.warning(
            "race_orphan_runs_reconciled count=%d threshold_minutes=%d",
            count,
            threshold,
        )
    return count


__all__ = [
    "ORPHAN_RUNNING_ERROR_MESSAGE",
    "ORPHAN_AWAITING_HITL_ERROR_MESSAGE",
    "reconcile_orphan_runs",
]
