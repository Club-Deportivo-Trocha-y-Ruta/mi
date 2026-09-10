"""Trazas Langfuse de las llamadas LLM del pipeline race — SOLO desarrollo local.

Observador opcional (``LANGFUSE_ENABLED``, prohibido en producción por
validator de ``Settings``) para ver tokens por llamada en un Langfuse
self-hosted. No es fuente de verdad de costos: eso sigue siendo
``agents/pricing.py`` + ``metrics_snapshot_json`` + el budget guard.

- ``langfuse`` se importa lazy: con el flag apagado nunca se carga.
- Tracing nunca rompe una corrida: cualquier fallo degrada a "sin callbacks".
- Privacidad: el ``mask`` del cliente reemplaza SIEMPRE input/output/metadata
  por ``"[redacted]"`` (los prompts, aun seudonimizados, llevan
  cuasi-identificadores de menores); solo salen modelo, uso y estructura. Los
  mensajes de error se reducen al tipo de excepción (``str(GraphInterrupt)``
  incluye el payload HITL) y solo se exportan spans del SDK de Langfuse: el
  cliente instala el TracerProvider global y spans OTel de terceros (p. ej.
  ``gen_ai.*`` del servidor MCP de claude-cli) no pasan por el mask.
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from functools import cache
from typing import Any, Iterator, Optional, Sequence

from app.config import settings

logger = logging.getLogger(__name__)

REDACTED = "[redacted]"

_client: Any = None
_warned_missing_keys = False


def _mask(*, data: Any, **kwargs: Any) -> Any:
    return None if data is None else REDACTED


def _create_client(**overrides: Any) -> Any:
    from langfuse import Langfuse
    from langfuse.span_filter import is_langfuse_span

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        environment=settings.app_env,
        mask=_mask,
        should_export_span=is_langfuse_span,
        **overrides,
    )


def _get_client() -> Any:
    global _client, _warned_missing_keys
    if not settings.langfuse_enabled:
        return None
    if _client is not None:
        return _client
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        if not _warned_missing_keys:
            logger.warning(
                "langfuse: LANGFUSE_ENABLED=true sin LANGFUSE_PUBLIC_KEY/"
                "LANGFUSE_SECRET_KEY — trazas deshabilitadas"
            )
            _warned_missing_keys = True
        return None
    try:
        _client = _create_client()
    except Exception:  # noqa: BLE001 — tracing nunca rompe la app.
        logger.exception("langfuse: no se pudo crear el cliente — trazas deshabilitadas")
        return None
    return _client


@cache
def _handler_class() -> type:
    from langfuse.langchain import CallbackHandler

    class _RaceCallbackHandler(CallbackHandler):
        def _get_error_level_and_status_message(self, error: BaseException) -> Any:
            level, _ = super()._get_error_level_and_status_message(error)
            return level, type(error).__name__

    return _RaceCallbackHandler


def get_callbacks(*, trace_id: Optional[str] = None) -> list[Any]:
    """Callbacks LangChain para una corrida; ``[]`` si tracing está apagado o falla."""
    if _get_client() is None:
        return []
    try:
        handler = _handler_class()(
            public_key=settings.langfuse_public_key,
            trace_context={"trace_id": trace_id} if trace_id else None,
        )
    except Exception:  # noqa: BLE001 — tracing nunca rompe la corrida.
        logger.exception("langfuse: no se pudo crear el CallbackHandler — corrida sin trazas")
        return []
    return [handler]


def trace_id_for(seed: str) -> Optional[str]:
    """Trace id determinístico (32 hex) para ``seed``; ``None`` si tracing está apagado."""
    if _get_client() is None:
        return None
    from langfuse import Langfuse

    return Langfuse.create_trace_id(seed=seed)


def anonymous_session_id(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@contextmanager
def llm_tracing(
    *,
    trace_name: str,
    session_id: str,
    tags: Sequence[str] = (),
    trace_seed: Optional[str] = None,
) -> Iterator[dict[str, Any]]:
    """Scope de una traza: entrega el fragmento de ``RunnableConfig`` a pasar.

    Entrega ``{}`` con tracing apagado. Los atributos de traza se propagan por
    contexto (no por ``metadata``) porque Langfuse solo los lee de metadata
    cuando la raíz es una cadena — chat y juez invocan el LLM directo.
    ``trace_seed`` fija el trace id (start + resume HITL comparten traza).
    """
    if _get_client() is None:
        yield {}
        return
    from langfuse import Langfuse, propagate_attributes

    trace_id = Langfuse.create_trace_id(seed=trace_seed)
    callbacks = get_callbacks(trace_id=trace_id)
    if not callbacks:
        yield {}
        return
    logger.info(
        "langfuse_trace name=%s session=%s trace_id=%s", trace_name, session_id, trace_id
    )
    with propagate_attributes(trace_name=trace_name, session_id=session_id, tags=list(tags)):
        yield {"callbacks": callbacks}


def shutdown() -> None:
    """Flush + cierre del cliente, solo si llegó a crearse."""
    global _client
    if _client is None:
        return
    try:
        _client.shutdown()
    except Exception:  # noqa: BLE001
        logger.exception("langfuse: shutdown falló")
    _client = None
