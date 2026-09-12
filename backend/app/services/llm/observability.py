"""Trazas Langfuse de las llamadas LLM — SOLO desarrollo local.

Compartido por los dos stacks de IA del monorepo (``app/services/ai/`` y
``app/services/race/``, feature 042 T011 — antes vivía únicamente en
``app/services/race/observability.py``, que ahora es un shim de
compatibilidad hacia este módulo).

Observador opcional (``LANGFUSE_ENABLED``, prohibido en producción por
validator de ``Settings``) para ver tokens por llamada en un Langfuse
self-hosted. No es fuente de verdad de costos: eso sigue siendo
``llm/pricing.py`` + ``metrics_snapshot_json`` + el budget guard de race.

- ``langfuse`` se importa lazy: con el flag apagado nunca se carga.
- Tracing nunca rompe una corrida: cualquier fallo degrada a "sin callbacks".
- Privacidad: el ``mask`` del cliente (``observability_metadata.build_mask``)
  reemplaza SIEMPRE input/output por ``"[redacted]"`` (los prompts, aun
  seudonimizados, llevan cuasi-identificadores de menores); metadata solo
  escapa del redact-always cuando viene envuelta en
  ``StructuralMetadata`` (``LANGFUSE_STRUCTURAL_METADATA=true``, prohibido en
  producción) — ver ``observability_metadata.py`` para el allow-list cerrado
  y su razonamiento. Los mensajes de error se reducen al tipo de excepción
  (``str(GraphInterrupt)`` incluye el payload HITL) y solo se exportan spans
  del SDK de Langfuse: el cliente instala el TracerProvider global y spans
  OTel de terceros (p. ej. ``gen_ai.*`` del servidor MCP de claude-cli) no
  pasan por el mask.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import contextmanager
from functools import cache
from typing import Any, Iterator, Optional, Sequence

from app.config import settings
from app.services.llm.observability_metadata import build_mask

logger = logging.getLogger(__name__)

REDACTED = "[redacted]"

# Dominio de separación de ``keyed_session_id`` — distinto del anonimizador
# de pseudónimos de atletas (``race/ai/anonymizer.py``, salt propio) y del
# ``anonymous_session_id`` sin clave de este mismo módulo, para que la
# filtración de una derivación no debilite a la otra
# (``contracts/trace-metadata-allowlist.md`` §4).
_KEYED_SESSION_ID_DOMAIN = b"042-langfuse-session"

_client: Any = None
_warned_missing_keys = False
_warned_construction_failed = False

# Mask por defecto del cliente Langfuse: redact-always sobre el sentinela
# actual, expuesto también como fábrica (``build_mask``) para que
# ``observability_metadata.py`` sea el único lugar que decide qué
# sobrevive al mask (ver su docstring).
_mask = build_mask(REDACTED)


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
    global _client, _warned_missing_keys, _warned_construction_failed
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
        # FR-021: "como máximo UNA advertencia por proceso". Sin este flag la
        # rama se dispara en cada llamada — y una sola corrida de
        # ``llm_tracing`` ya invoca ``_get_client`` dos veces (directo y vía
        # ``get_callbacks``), así que un Langfuse local caído inundaba el log
        # con un stacktrace por llamada LLM. Mismo criterio que
        # ``_warned_missing_keys``, la rama hermana de arriba.
        if not _warned_construction_failed:
            logger.exception(
                "langfuse: no se pudo crear el cliente — trazas deshabilitadas"
            )
            _warned_construction_failed = True
        return None
    return _client


@cache
def _handler_class() -> type:
    from langfuse.langchain import CallbackHandler

    class _TracingCallbackHandler(CallbackHandler):
        def _get_error_level_and_status_message(self, error: BaseException) -> Any:
            level, _ = super()._get_error_level_and_status_message(error)
            return level, type(error).__name__

    return _TracingCallbackHandler


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
    """SHA-256 plano truncado — ENUMERABLE por fuerza bruta sobre un espacio de
    preimagen pequeño (~20 atletas × unos cientos de registros, bajo 10.000
    hashes). Se conserva sin cambios por compatibilidad; ``keyed_session_id``
    es el reemplazo correcto para cualquier caller nuevo (feature 042, FR-024).
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def keyed_session_id(raw: str) -> str:
    """Id de sesión pseudonimizado y NO enumerable, para session ids/tags de Langfuse.

    A diferencia de :func:`anonymous_session_id` (sha256 plano — invertible en
    segundos por cualquiera que tenga el volumen de Langfuse y la base de
    datos), deriva un HMAC con una clave — ``settings.jwt_secret_key`` — que
    un atacante con acceso solo al almacén de trazas no posee.

    Estable entre reinicios del proceso: decisión explícita del owner
    (``spec.md`` Assumptions, ``contracts/trace-metadata-allowlist.md`` §4) —
    un salt por proceso sería más fuerte pero perdería la agrupación de
    trazas del mismo atleta/sesión tras un redeploy del backend, que solo una
    clave estable del lado del servidor entrega. Separada por dominio del
    anonimizador de pseudónimos de atletas (``race/ai/anonymizer.py``) y de
    ``anonymous_session_id`` (``_KEYED_SESSION_ID_DOMAIN`` arriba), para que
    la filtración de una derivación no debilite a la otra. Truncada a 16 hex
    para no cambiar el ancho de id consumido río abajo (mismo ancho que
    ``anonymous_session_id``).

    ``jwt_secret_key`` se lee perezosamente (dentro de la función, en cada
    llamada) — nunca cacheada a nivel de módulo — para que un test pueda
    monkeypatchear ``settings.jwt_secret_key`` sin recargar el módulo.
    """
    key = settings.jwt_secret_key.encode("utf-8")
    payload = _KEYED_SESSION_ID_DOMAIN + b":" + raw.encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()[:16]


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
