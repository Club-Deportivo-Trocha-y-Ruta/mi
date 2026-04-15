"""
Task Dispatcher — abstracción sobre FastAPI BackgroundTasks.

Paso 5 del workflow-notifications.

Diseñado para ser swapeable: BackgroundTasks ahora, ARQ+Redis después
sin tocar NotificationService ni routers.

Interfaz futura ArqDispatcher (NO implementada aquí — ver comentario al final):
  La migración a ARQ solo requiere implementar ArqDispatcher con la misma
  interfaz `dispatch(func, *args, **kwargs)` y reemplazar la dependencia en DI.
  Zero cambios en NotificationService ni en routers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """Despachador de tareas en background.

    Con BackgroundTasks (FastAPI) inyectado: despacha en background.
    Sin BackgroundTasks: ejecuta de forma síncrona/espera (útil en tests).

    Uso en endpoint (con background):
        dispatcher = TaskDispatcher(background_tasks)
        dispatcher.dispatch(my_async_func, arg1, kwarg1=val1)

    Uso en test (sin background):
        dispatcher = TaskDispatcher()
        dispatcher.dispatch(my_async_func, ...)  # espera resultado
    """

    def __init__(self, background_tasks=None) -> None:
        """
        Args:
            background_tasks: Instancia de fastapi.BackgroundTasks inyectada
                              desde el endpoint. None para ejecución directa.
        """
        self._bg = background_tasks

    def dispatch(self, func: Callable, /, *args: Any, **kwargs: Any) -> None:
        """Encola la función para ejecución en background (o la ejecuta directamente).

        Args:
            func: Callable (sync o async) a ejecutar.
            *args: Argumentos posicionales para func.
            **kwargs: Argumentos keyword para func.
        """
        if self._bg is not None:
            # FastAPI BackgroundTasks maneja tanto sync como async callables
            self._bg.add_task(func, *args, **kwargs)
            logger.debug("Tarea encolada en BackgroundTasks | func=%s", func.__name__)
        else:
            # Ejecución directa — para tests y contextos sin HTTP request
            logger.debug("Tarea ejecutada directamente | func=%s", func.__name__)
            if asyncio.iscoroutinefunction(func):
                # Intentar ejecutar en el event loop actual si existe
                try:
                    loop = asyncio.get_running_loop()
                    # Si hay un loop corriendo (ej. pytest-asyncio), crear una tarea
                    loop.create_task(func(*args, **kwargs))
                except RuntimeError:
                    # No hay loop en ejecución — ejecutar bloqueante
                    asyncio.run(func(*args, **kwargs))
            else:
                func(*args, **kwargs)


# ---------------------------------------------------------------------------
# Interfaz futura: ArqDispatcher
#
# Cuando se necesite persistencia de tareas y reintentos:
#
#   class ArqDispatcher:
#       def __init__(self, arq_pool: ArqRedis) -> None:
#           self._pool = arq_pool
#
#       def dispatch(self, func: Callable, /, *args, **kwargs) -> None:
#           # arq espera que func esté registrada en WorkerSettings
#           asyncio.create_task(
#               self._pool.enqueue_job(func.__name__, *args, **kwargs)
#           )
#
# Pasos de migración (sin tocar NotificationService ni routers):
#   1. pip install arq redis
#   2. Agregar Redis a docker-compose
#   3. Implementar ArqDispatcher (misma interfaz dispatch())
#   4. Registrar funciones en WorkerSettings
#   5. Actualizar get_task_dispatcher() en dependencies.py para retornar ArqDispatcher
#   6. Zero cambios en NotificationService ni en routers
# ---------------------------------------------------------------------------
