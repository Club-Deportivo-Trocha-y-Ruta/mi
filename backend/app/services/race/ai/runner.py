"""Orquestador de ejecución del grafo race-analyst (F5.7 backpressure).

Responsabilidades:
- **Semáforo** módulo-global con ``MAX_CONCURRENT_RUNS=10`` (workflow §5.8).
  Si el semáforo está lleno y un caller intenta acquire sin bloqueo →
  :class:`RunBackpressureError` → router traduce a 429.
- **Registry in-memory** de runs activos: ``run_id → asyncio.Task`` para
  cancellation futura (no implementada en MVP, pero el hook está).
- **Lanzamiento** del grafo en background sin bloquear el handler HTTP:
  el router crea la fila ``agent_runs``, llama ``submit_run`` y devuelve
  inmediatamente.
- **Reanudación post-HITL**: ``resume_run`` usa ``Command(resume=...)``
  contra el grafo compilado vía ``ainvoke`` con thread_id estable
  (el ``external_run_id`` como ``thread_id``).

Decisiones:
- Singleton del semáforo y registry → simple para single-process. Si
  evolucionamos a multi-worker (gunicorn -w 4), migrar a un store
  externo (Redis SETNX) — TODO documentado.
- El semáforo se libera cuando la task background termina (success,
  exception o cancelación). Idempotente con ``finally``.
- El grafo se obtiene vía ``get_compiled_graph()`` (singleton lazy).
  Tests inyectan un fake mediante ``set_graph_factory()``.

Privacidad:
- ``run_id`` se loggea (es UUID, no PII). athlete_id NO se loggea — el
  test sentinela cubre el path HTTP, los logs son auditoría server-side
  y respetan el principio "menos exposición posible".
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes y errores
# ---------------------------------------------------------------------------

MAX_CONCURRENT_RUNS = 10
"""Tope global de runs en ejecución simultánea. Si se excede → 429."""


class RunBackpressureError(RuntimeError):
    """No hay slots libres para iniciar un nuevo run."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_RUNS) -> None:
        super().__init__(
            f"max_concurrent_runs_reached (cap={max_concurrent})"
        )
        self.max_concurrent = max_concurrent


# ---------------------------------------------------------------------------
# Semáforo + registry
# ---------------------------------------------------------------------------

# Semáforo módulo-global. Usamos BoundedSemaphore para detectar release()
# spurio (defensive — no debería pasar, pero detecta bugs futuros).
_semaphore = asyncio.BoundedSemaphore(MAX_CONCURRENT_RUNS)

# run_id → Task. Permite tracking + futura cancelación.
_active_runs: dict[str, asyncio.Task] = {}
_registry_lock = asyncio.Lock()


def get_active_run_count() -> int:
    """Cuenta de runs activos (útil para healthcheck / admin metrics)."""
    return len(_active_runs)


def has_capacity() -> bool:
    """True si hay al menos un slot libre. Lectura no atómica — para
    decisiones precisas usar :func:`submit_run` que sí es atómico."""
    return len(_active_runs) < MAX_CONCURRENT_RUNS


# ---------------------------------------------------------------------------
# Inyección de grafo (testability)
# ---------------------------------------------------------------------------

GraphFactory = Callable[[], Awaitable[Any]]

_graph_factory: Optional[GraphFactory] = None


def set_graph_factory(factory: Optional[GraphFactory]) -> None:
    """Override del factory del grafo (tests).

    Cuando ``None``, se usa :func:`get_compiled_graph` del módulo
    ``app.services.race.ai.graph`` (singleton lazy con AsyncSqliteSaver).
    """
    global _graph_factory
    _graph_factory = factory


async def _get_graph() -> Any:
    if _graph_factory is not None:
        return await _graph_factory()
    from app.services.race.ai.graph import get_compiled_graph

    return await get_compiled_graph()


# ---------------------------------------------------------------------------
# Submit + resume
# ---------------------------------------------------------------------------


async def submit_run(
    run_id: str,
    initial_state: dict[str, Any],
    on_complete: Optional[Callable[[str, Optional[BaseException]], Awaitable[None]]] = None,
) -> asyncio.Task:
    """Lanza el grafo en background con backpressure.

    Args:
        run_id: external_run_id (UUID), usado como ``thread_id`` del
            checkpointer LangGraph para reanudación post-HITL.
        initial_state: estado inicial del grafo (athlete_id, season,
            valida_nums, coach_id, explain_mode, run_id).
        on_complete: callback opcional ``(run_id, exception_or_None)``
            ejecutado al terminar (success, error o cancel). El router
            lo usa para actualizar ``agent_runs.status`` y
            ``finished_at``.

    Returns:
        La task spawned. El caller no necesita await — la task vive
        en el registry.

    Raises:
        RunBackpressureError: si no hay slots libres.
    """
    # Acquire NO bloqueante. Si está lleno → 429.
    acquired = False
    try:
        # asyncio.BoundedSemaphore no tiene try-acquire nativo en 3.13.
        # Workaround: chequeamos contador interno con un lock.
        async with _registry_lock:
            if len(_active_runs) >= MAX_CONCURRENT_RUNS:
                raise RunBackpressureError()
            # Acquire bajo lock — garantiza que el conteo sea exacto.
            await _semaphore.acquire()
            acquired = True

            task = asyncio.create_task(
                _run_graph(run_id, initial_state, on_complete),
                name=f"race-run-{run_id}",
            )
            _active_runs[run_id] = task
            return task
    except BaseException:
        if acquired:
            try:
                _semaphore.release()
            except ValueError:
                # release spurio — no debería pasar; defensive.
                logger.warning("submit_run: release spurio del semáforo")
        raise


async def _run_graph(
    run_id: str,
    initial_state: dict[str, Any],
    on_complete: Optional[Callable[[str, Optional[BaseException]], Awaitable[None]]],
) -> None:
    """Worker async que ejecuta el grafo. Idempotente en cleanup."""
    exc: Optional[BaseException] = None
    try:
        graph = await _get_graph()
        config = {"configurable": {"thread_id": run_id}}
        await graph.ainvoke(initial_state, config=config)
    except BaseException as e:  # noqa: BLE001
        exc = e
        logger.exception("race run %s falló: %s", run_id, type(e).__name__)
    finally:
        async with _registry_lock:
            _active_runs.pop(run_id, None)
            try:
                _semaphore.release()
            except ValueError:
                logger.warning("race run %s: release spurio", run_id)
        if on_complete is not None:
            try:
                await on_complete(run_id, exc)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "race run %s: on_complete callback falló", run_id
                )


async def resume_run(
    run_id: str,
    resume_value: Any,
    on_complete: Optional[Callable[[str, Optional[BaseException]], Awaitable[None]]] = None,
) -> asyncio.Task:
    """Reanuda un run pausado en HITL.

    Args:
        run_id: thread_id del checkpointer (== external_run_id).
        resume_value: dict ``{"decision": "approve"|"reject"|"edit",
            "edits": str | None, "notes": str | None}`` que llega a
            ``interrupt()`` en el nodo ``hitl_gate_review``.
        on_complete: callback al terminar la continuación.

    Returns:
        Task spawned para la continuación.

    Notas:
        - No re-acquire del semáforo: la continuación reutiliza el slot
          conceptualmente (el run sigue activo desde la perspectiva del
          usuario). En la práctica el slot ya se liberó cuando la
          primera invocación retornó (la pausa por interrupt suspende
          la ejecución, no la task per-se). Para simplicidad MVP,
          *reusamos el patrón submit_run* — si la capacidad está
          llena, falla con backpressure y el coach debe reintentar.

    Raises:
        RunBackpressureError: si está lleno.
    """
    # Import lazy para no cargar langgraph al importar este módulo.
    from langgraph.types import Command

    async with _registry_lock:
        if len(_active_runs) >= MAX_CONCURRENT_RUNS:
            raise RunBackpressureError()
        await _semaphore.acquire()
        task = asyncio.create_task(
            _resume_graph(run_id, Command(resume=resume_value), on_complete),
            name=f"race-resume-{run_id}",
        )
        _active_runs[run_id] = task
        return task


async def _resume_graph(
    run_id: str,
    command: Any,
    on_complete: Optional[Callable[[str, Optional[BaseException]], Awaitable[None]]],
) -> None:
    exc: Optional[BaseException] = None
    try:
        graph = await _get_graph()
        config = {"configurable": {"thread_id": run_id}}
        await graph.ainvoke(command, config=config)
    except BaseException as e:  # noqa: BLE001
        exc = e
        logger.exception("race resume %s falló: %s", run_id, type(e).__name__)
    finally:
        async with _registry_lock:
            _active_runs.pop(run_id, None)
            try:
                _semaphore.release()
            except ValueError:
                logger.warning("race resume %s: release spurio", run_id)
        if on_complete is not None:
            try:
                await on_complete(run_id, exc)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "race resume %s: on_complete callback falló", run_id
                )


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


async def _reset_for_tests() -> None:
    """Resetea state global. SOLO usar en tests (no exportado)."""
    global _semaphore
    async with _registry_lock:
        for task in list(_active_runs.values()):
            task.cancel()
        _active_runs.clear()
        _semaphore = asyncio.BoundedSemaphore(MAX_CONCURRENT_RUNS)


__all__ = [
    "MAX_CONCURRENT_RUNS",
    "RunBackpressureError",
    "get_active_run_count",
    "has_capacity",
    "set_graph_factory",
    "submit_run",
    "resume_run",
]
