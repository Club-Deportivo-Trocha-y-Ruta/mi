"""Retry policy para nodos del grafo (F4 §4.5).

Decorador para envolver funciones async de nodos con:

- Reintentos limitados (``max_attempts``).
- Backoff exponencial (``backoff`` es el factor — sleep = backoff ** attempt).
- **Allowlist explícita** de excepciones a reintentar: sólo errores de
  red / I/O. ``ValueError`` u otros ``Exception`` programáticos NO se
  reintentan (regla: bugs deterministas no deben "auto-curarse" por reintento).
- Log warning en cada intento. Después del último, re-raise.

Uso::

    @with_retry(max_attempts=3, backoff=2.0)
    async def my_node(state):
        ...

El error final se debe capturar en el wrapper de grafo (en ``graph.py``)
para popular ``state["errors"]`` y permitir transición a fallback. Este
decorador deliberadamente NO toca el ``state`` — su única responsabilidad
es el reintento.
"""

from __future__ import annotations

import asyncio
import logging
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Excepciones que SI se reintentan (errores transitorios de red / I/O).
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TimeoutError,
    asyncio.TimeoutError,
    httpx.HTTPError,
    OSError,
    ConnectionError,
)


def with_retry(
    max_attempts: int = 3,
    backoff: float = 2.0,
    retryable: tuple[type[BaseException], ...] | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorador de retry con backoff exponencial.

    Args:
        max_attempts: número máximo de intentos (incluyendo el primero).
        backoff: factor exponencial — sleep = ``backoff ** attempt`` seconds.
            Con ``backoff=2``: 2s, 4s, 8s (intentos 0,1,2). Usar
            ``backoff=0`` desactiva sleep (tests).
        retryable: override de la tupla de excepciones a reintentar. Por
            default :data:`RETRYABLE_EXCEPTIONS`.

    Returns:
        Decorador.

    Notas:
        - ``ValueError``, ``TypeError``, ``KeyError`` y demás bugs NUNCA
          se reintentan — re-raise inmediato.
        - Si la función async retorna sin excepción → se devuelve el
          valor en el primer intento exitoso.
    """
    exc_types = retryable or RETRYABLE_EXCEPTIONS

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt = 0
            last_exc: BaseException | None = None
            while attempt < max_attempts:
                try:
                    return await fn(*args, **kwargs)
                except exc_types as exc:
                    last_exc = exc
                    logger.warning(
                        "retry: %s falló intento %d/%d: %s",
                        fn.__name__,
                        attempt + 1,
                        max_attempts,
                        type(exc).__name__,
                    )
                    attempt += 1
                    if attempt >= max_attempts:
                        break
                    if backoff > 0:
                        sleep_s = backoff ** attempt
                        await asyncio.sleep(sleep_s)
                except Exception:
                    # No-retry path: bugs deterministas, programación, etc.
                    raise
            # Agotamos intentos: re-raise el último error
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


__all__ = ["with_retry", "RETRYABLE_EXCEPTIONS"]
