"""Tarifas LLM para cálculo de ``cost_usd`` en :class:`RunMetrics`.

Fuente: pricing público de Google Gemini Flash Lite (model
``gemini-2.5-flash-lite``) a fecha 2026-05-20.

- Input:  USD 0.075 / 1M tokens
- Output: USD 0.30  / 1M tokens

Si Google cambia tarifas o se cambia de modelo, **solo este módulo
se toca** — los agentes consumen :func:`compute_cost_usd`.

Decisión: mantenemos las constantes como floats simples (no enums
ni dicts por modelo) porque MVP usa **un solo modelo**. Si en el
futuro se introduce Pro/Flash dual, refactorizar a un dict
``{model_id: PricingRow}``.
"""

from __future__ import annotations

# USD por 1M tokens (Gemini 2.5 Flash Lite — 2026-05).
GEMINI_FLASH_LITE_INPUT_USD_PER_1M = 0.075
GEMINI_FLASH_LITE_OUTPUT_USD_PER_1M = 0.30

# Prompt version registry — mantener en sincronía con archivos en prompts/.
# Sirve a auditoría / Langfuse / golden eval para correlacionar outputs con
# versión exacta del prompt. SIEMPRE bump al editar un prompt.
PROMPT_VERSION_ANALYST = "race_analyst_v1"
PROMPT_VERSION_CRITIC = "race_critic_v1"
PROMPT_VERSION_CHAT = "race_chat_v1"


def compute_cost_usd(tokens_in: int, tokens_out: int) -> float:
    """Calcula costo en USD para una invocación.

    Args:
        tokens_in: tokens del prompt enviado al modelo.
        tokens_out: tokens generados por el modelo.

    Returns:
        Costo en USD redondeado a 6 decimales (precisión sub-cent).
    """
    cost = (
        tokens_in * GEMINI_FLASH_LITE_INPUT_USD_PER_1M / 1_000_000
        + tokens_out * GEMINI_FLASH_LITE_OUTPUT_USD_PER_1M / 1_000_000
    )
    return round(cost, 6)


def estimate_tokens_from_chars(text: str) -> int:
    """Fallback declarado (workflow §3.2) cuando ``usage_metadata`` no llega.

    Heurística: ``len(text) // 4``. Funciona razonable para español/inglés
    con tokenizers BPE modernos.
    """
    return max(0, len(text) // 4)
