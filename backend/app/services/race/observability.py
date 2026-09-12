"""Shim de compatibilidad — la implementación real vive en
``app.services.llm.observability``.

El cliente Langfuse singleton, el mask redact-always y la degradación a
no-op vivían aquí y se movieron (feature 042, T011) a
``app/services/llm/observability.py`` para que ``app/services/ai/`` también
pueda trazar sin depender del paquete ``race``. Este módulo se conserva como
shim porque ~10 tests de este archivo y ``app/main.py`` /
``app/routers/race_analysis.py`` importan/monkeypatchean por esta ruta de
módulo exacta (``contracts/llm-transport.md`` §2.1). Se retira en una
feature futura, nunca en esta (``plan.md`` Complexity Tracking).

**Reexportación simple vs. delegación — por qué no todo es un ``from ... import``**

Las funciones puras (``get_callbacks``, ``llm_tracing``, ``trace_id_for``,
``shutdown``, ``_mask``, ``REDACTED``, ``anonymous_session_id``,
``keyed_session_id``) se reexportan tal cual con un ``from ... import``: son
literalmente el mismo objeto función que en
``app.services.llm.observability``, así que llamarlas desde aquí ejecuta el
código real sin ninguna diferencia de comportamiento.

Los cuatro nombres con estado mutable de proceso (``_client``,
``_warned_missing_keys``, ``_create_client``, ``_handler_class``) NO se
pueden reexportar así. Un ``from ... import _client`` copiaría el valor UNA
sola vez al importar este módulo; un ``monkeypatch.setattr(observability,
"_client", ...)`` posterior solo reasignaría el nombre en el ``__dict__`` de
ESTE módulo, mientras que ``get_callbacks``/``llm_tracing`` — definidas en
``app.services.llm.observability`` y que leen/escriben esos nombres vía
``global`` — seguirían resolviendo sus propios globals contra el ``__dict__``
de ESE módulo, ignorando el patch por completo. Copiar el valor en cada
llamada (sincronizar antes/después) tampoco sirve: bajo concurrencia real
(p. ej. dos chats corriendo con ``asyncio.gather``, ver
``test_concurrent_scopes_each_redacted_with_own_usage``) un segundo
``await`` que reanuda mientras el primero aún no sincronizó de vuelta
pisaría el cliente recién creado por el primero con un valor obsoleto.

La solución es que leer o escribir uno de esos cuatro nombres EN ESTE
módulo delegue directo, sin copia, al atributo homónimo de
``app.services.llm.observability`` — para que sea, en los hechos, el MISMO
almacenamiento, no una copia sincronizada. Los módulos no exponen un gancho
para interceptar `setattr` (PEP 562 solo cubre `__getattr__`), así que este
módulo reemplaza su propia clase por una subclase de ``ModuleType`` con
``__getattr__``/``__setattr__`` propios — patrón estándar para atributos de
módulo delegados/deprecados.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from app.services.llm import observability as _impl
from app.services.llm.observability import (  # noqa: F401 — reexport público
    REDACTED,
    _mask,
    anonymous_session_id,
    get_callbacks,
    keyed_session_id,
    llm_tracing,
    shutdown,
    trace_id_for,
)

# Los únicos nombres con estado mutable de proceso — ver docstring del
# módulo. Todo lo demás (funciones puras, constantes) vive en el ``__dict__``
# normal de este módulo vía los imports de arriba.
_PROXIED_STATE = ("_client", "_warned_missing_keys", "_create_client", "_handler_class")


class _ObservabilityShimModule(ModuleType):
    """``ModuleType`` que delega get/set de ``_PROXIED_STATE`` a ``_impl``.

    Sin esto, un test que hace ``monkeypatch.setattr(observability,
    "_client", None)`` (donde ``observability`` es este módulo) nunca
    afectaría el ``_client`` que ``app.services.llm.observability._get_client``
    realmente lee/escribe.
    """

    def __getattr__(self, name: str) -> Any:
        if name in _PROXIED_STATE:
            return getattr(_impl, name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _PROXIED_STATE:
            setattr(_impl, name, value)
        else:
            super().__setattr__(name, value)


# Reemplazo de clase post-definición: técnica estándar para módulos con
# atributos delegados (no hay equivalente de PEP 562 para `__setattr__`, así
# que `__getattr__` también se resuelve aquí, en la clase, por simetría).
sys.modules[__name__].__class__ = _ObservabilityShimModule
