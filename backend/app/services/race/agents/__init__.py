"""Capa agéntica del módulo race (Fase 3 race-results v2).

Tres roles LLM independientes:

- :class:`RaceAnalystAgent` (``analyst.py``) — produce el análisis
  cualitativo a partir de datos anonimizados + memoria + RAG.
- :class:`RaceCriticAgent` (``critic.py``) — revisa el draft del analyst
  contra reglas inviolables del club. Feature-flag.
- :class:`RaceChatAgent` (``chat.py``) — agente conversacional con tools.

Todos consumen Gemini 2.5 Flash Lite vía ``langchain-google-genai``.
``pricing.py`` centraliza tarifas → ``RunMetrics.cost_usd``.
"""

from app.services.race.agents.analyst import RaceAnalystAgent
from app.services.race.agents.chat import RaceChatAgent
from app.services.race.agents.critic import RaceCriticAgent
from app.services.race.agents.pricing import (
    PROMPT_VERSION_ANALYST,
    PROMPT_VERSION_CHAT,
    PROMPT_VERSION_CRITIC,
    compute_cost_usd,
)

__all__ = [
    "RaceAnalystAgent",
    "RaceCriticAgent",
    "RaceChatAgent",
    "PROMPT_VERSION_ANALYST",
    "PROMPT_VERSION_CRITIC",
    "PROMPT_VERSION_CHAT",
    "compute_cost_usd",
]
