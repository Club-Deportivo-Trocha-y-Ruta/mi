"""Shim de compatibilidad — el contenido real vive en ``app.services.llm.pricing``
(feature 042, W1: extracción a factoría LLM compartida stack-neutral).

No se borra ni se renombra: ``app.services.race.agents.__init__`` y ~30 tests
del módulo race importan estos símbolos por esta ruta exacta
(``monkeypatch.setattr("app.services.race.agents.pricing", ...)`` en algunos
casos, import directo en otros) — ver ``contracts/llm-transport.md`` §2.1.
Este shim se retira en una feature futura, no en esta.
"""

from __future__ import annotations

from app.services.llm.pricing import (
    PROMPT_VERSION_ANALYST,
    PROMPT_VERSION_ANALYST_V2,
    PROMPT_VERSION_CHAT,
    PROMPT_VERSION_CRITIC,
    PROMPT_VERSION_CRITIC_V2,
    compute_cost_usd,
    estimate_tokens_from_chars,
)

__all__ = [
    "PROMPT_VERSION_ANALYST",
    "PROMPT_VERSION_ANALYST_V2",
    "PROMPT_VERSION_CHAT",
    "PROMPT_VERSION_CRITIC",
    "PROMPT_VERSION_CRITIC_V2",
    "compute_cost_usd",
    "estimate_tokens_from_chars",
]
