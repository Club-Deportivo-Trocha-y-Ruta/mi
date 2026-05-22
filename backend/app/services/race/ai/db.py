"""Adaptador de sesión async para los nodos del grafo.

Los nodos LangGraph reciben sólo el ``state`` — no AsyncSession. Para
evitar acoplar todos los nodos con FastAPI ``Depends(get_db)``, este
módulo expone un **db_factory** stub-eable:

- Default: usa ``app.database.get_async_session()`` (factory que
  retorna un context manager async).
- Tests: inyectan ``set_db_factory(lambda: FakeAsyncSession())`` antes
  de invocar el grafo.

Razón del patrón: el grafo se compila como singleton al startup
(``compiled_graph``). Inyectar la DB por nodo via partial es más
verboso y fragiliza el test setup. Un factory thread-local es más
simple y suficiente para single-process.
"""

from __future__ import annotations

import contextvars
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Optional

# Tipo del factory: callable que retorna un async-context que da AsyncSession.
SessionContextFactory = Callable[[], Any]

_db_factory_var: contextvars.ContextVar[Optional[SessionContextFactory]] = (
    contextvars.ContextVar("race_ai_db_factory", default=None)
)

# Fallback módulo-global. ContextVar.set() en import-time (main.py) no
# siempre propaga a tasks spawneados por uvicorn cuando el contexto del
# request es derivado del raíz pero ContextVar fue seteado *después* de
# que uvicorn inicializó su event loop. Mantenemos ContextVar para tests
# que necesitan aislamiento por context, y caemos al global cuando el
# contextvar no fue inyectado en ese contexto.
_db_factory_global: Optional[SessionContextFactory] = None


def set_db_factory(factory: Optional[SessionContextFactory]) -> None:
    """Setter del factory (tests + boot de la app).

    Setea tanto el ``ContextVar`` (aislamiento por contexto en tests)
    como el módulo-global (resiliente a tasks spawneados por uvicorn).
    """
    global _db_factory_global
    _db_factory_global = factory
    _db_factory_var.set(factory)


def get_db_factory() -> Optional[SessionContextFactory]:
    factory = _db_factory_var.get()
    if factory is None:
        factory = _db_factory_global
    return factory


@asynccontextmanager
async def get_session() -> AsyncIterator[Any]:
    """Context manager async que entrega la sesión configurada.

    Cada nodo consume la DB así::

        async with get_session() as db:
            ...

    Si no hay factory configurado → ``RuntimeError`` claro.
    """
    factory = get_db_factory()
    if factory is None:
        raise RuntimeError(
            "race AI db_factory no configurado. Llama a set_db_factory() en el "
            "boot de la app o en el setUp del test."
        )
    ctx = factory()
    # Soportamos tanto contexts async (FastAPI default) como factories
    # que retornan directamente una AsyncSession (FakeAsyncSession).
    if hasattr(ctx, "__aenter__"):
        async with ctx as session:
            yield session
    else:
        yield ctx


__all__ = ["set_db_factory", "get_db_factory", "get_session"]
