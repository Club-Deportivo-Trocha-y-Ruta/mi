"""Tarifas LLM para cálculo de ``cost_usd`` en :class:`RunMetrics`.

Una tarifa por **proveedor** (no por modelo exacto) — MVP asume un solo
modelo activo por proveedor a la vez (``RACE_AI_MODEL`` en config.py).
Si en el futuro se necesita precisión por modelo, refactorizar
``_PRICING_USD_PER_1M`` a ``{model_id: PricingRow}``.

Fuentes (USD por 1M tokens):
- Gemini 3.1 Flash Lite (``gemini-3.1-flash-lite``, GA 2026-05-07) —
  pricing público a fecha 2026-07-14. Input 0.25 / Output 1.50.
  (Modelo activo desde 2026-07-14, reemplaza a Gemini 2.5 Flash Lite,
  que costaba 0.075 / 0.30.)
- Claude Sonnet 5 (``claude-sonnet-5``) — pricing estándar a fecha
  2026-07-10. Input 3.00 / Output 15.00. (Existe pricing introductorio
  2.00/10.00 hasta 2026-08-31 — usamos el estándar, más conservador
  para el budget guard de ``race_ai_budget_usd_30d``.)

Si un proveedor cambia tarifas, **solo este módulo se toca** — los
agentes consumen :func:`compute_cost_usd`.
"""

from __future__ import annotations

# (input_usd_per_1m, output_usd_per_1m) por proveedor.
_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    "anthropic": (3.00, 15.00),
    "google": (0.25, 1.50),
    # Ollama local (uso objetivo de "openai" en race/agents/) = costo 0.
    # Si se usa contra la API real de OpenAI esto subestima el costo — el
    # budget guard no lo detectará; aceptable porque el uso objetivo de
    # este provider hoy es Ollama local, no OpenAI real.
    "openai": (0.0, 0.0),
}

# (input_usd_per_1m, output_usd_per_1m) por modelo — feature 037 (T101).
# Solo cubre los modelos por-rol nuevos (analyst/critic). Usado por
# :func:`compute_cost_usd` cuando se pasa ``model`` y hay entrada exacta;
# si no, cae a la tarifa por proveedor de arriba.
# - gemini-3.8-flash (analyst, verificado disponible 2026-09-02): 0.75 / 3.75.
# - gemini-3.5-flash-lite (critic, verificado disponible 2026-09-02): 0.30 / 2.50.
_PRICING_USD_PER_1M_BY_MODEL: dict[str, tuple[float, float]] = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
}

# Prompt version registry — mantener en sincronía con archivos en prompts/.
# Sirve a auditoría / Langfuse / golden eval para correlacionar outputs con
# versión exacta del prompt. SIEMPRE bump al editar un prompt.
PROMPT_VERSION_ANALYST = "race_analyst_v1"
PROMPT_VERSION_ANALYST_V2 = "race_analyst_v2"
PROMPT_VERSION_CRITIC = "race_critic_v1"
PROMPT_VERSION_CRITIC_V2 = "race_critic_v2"
PROMPT_VERSION_CHAT = "race_chat_v1"


def compute_cost_usd(
    tokens_in: int, tokens_out: int, *, provider: str, model: str | None = None
) -> float:
    """Calcula costo en USD para una invocación.

    Args:
        tokens_in: tokens del prompt enviado al modelo.
        tokens_out: tokens generados por el modelo.
        provider: ``"anthropic"`` | ``"google"`` | ``"openai"`` — tarifa de
            fallback usada cuando ``model`` es ``None`` o no tiene entrada
            propia en :data:`_PRICING_USD_PER_1M_BY_MODEL`.
        model: model_id exacto (ej. ``"gemini-3.8-flash"``). Si tiene tarifa
            registrada por-modelo, esta gana sobre la tarifa por-proveedor
            (feature 037, T101 — modelos por rol con costo distinto al
            default histórico del proveedor).

    Returns:
        Costo en USD redondeado a 6 decimales (precisión sub-cent).

    Raises:
        KeyError: proveedor sin tarifa registrada en ``_PRICING_USD_PER_1M``
            y sin tarifa por-modelo tampoco.
    """
    rates = _PRICING_USD_PER_1M_BY_MODEL.get(model) if model else None
    if rates is None:
        rates = _PRICING_USD_PER_1M[provider]
    input_rate, output_rate = rates
    cost = tokens_in * input_rate / 1_000_000 + tokens_out * output_rate / 1_000_000
    return round(cost, 6)


def estimate_tokens_from_chars(text: str) -> int:
    """Fallback declarado (workflow §3.2) cuando ``usage_metadata`` no llega.

    Heurística: ``len(text) // 4``. Funciona razonable para español/inglés
    con tokenizers BPE modernos.
    """
    return max(0, len(text) // 4)
