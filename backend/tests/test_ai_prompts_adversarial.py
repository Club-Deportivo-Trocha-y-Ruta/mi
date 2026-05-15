"""Tests adversariales de prompts e2e — Ola 2.

Verifican que outputs canónicos del LLM que intentan filtrar comparativas
poblacionales, valores clínicos inventados o etiquetas diagnósticas, se
limpian o se rechazan por los guardrails. También chequean propiedades del
system prompt cargado por `PromptRegistry`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ai.errors import LLMSchemaError
from app.services.ai.guardrails import (
    MAX_VIOLATIONS_BEFORE_REJECT,
    Guardrails,
)
from app.services.ai.prompts.registry import PromptRegistry


# ---------------------------------------------------------------------------
# 1. Outputs adversariales canónicos pasan por `scrub`
# ---------------------------------------------------------------------------
#
# El `FakeLLMProvider` no es necesario para verificar guardrails: los
# guardrails operan sobre texto ya generado. Estos tests inyectan el texto
# adversarial directamente al saneador, replicando lo que haría un use case
# tras recibir la respuesta del modelo.


def test_adversarial_comparativa_poblacional_es_eliminada():
    """'Su hijo está por encima del promedio para su edad...' debe
    quedar limpio o ser rechazado por `comparative_norm`."""
    g = Guardrails()
    text = (
        "Su hijo está por encima del promedio para su edad en talla. "
        "Recomendamos seguir con el plan actual."
    )
    report = g.scrub_with_report(text)
    assert "comparative_norm" in report.violations
    assert "promedio" not in report.text.lower()
    # No viola otras reglas, así que no debe rechazar
    assert not report.rejected


def test_adversarial_imc_numerico_es_eliminado():
    """'Tiene un IMC de aproximadamente 22...' debe ser eliminado por
    `numeric_clinical_metrics`."""
    g = Guardrails()
    text = (
        "Tiene un IMC de aproximadamente 22, lo cual sugiere desarrollo "
        "adecuado para la fase de maduración."
    )
    report = g.scrub_with_report(text)
    assert "numeric_clinical_metrics" in report.violations
    # El término clínico + número desaparece
    assert "22" not in report.text or "IMC" not in report.text.upper()
    assert not report.rejected


def test_adversarial_comparacion_con_otros_ninos_eliminada():
    """'Comparado con otros niños del club...' debe ser eliminado por
    `comparative_norm`."""
    g = Guardrails()
    text = (
        "Comparado con otros niños del club, su crecimiento luce normal "
        "y constante."
    )
    report = g.scrub_with_report(text)
    assert "comparative_norm" in report.violations
    assert "otros niños" not in report.text.lower()


def test_adversarial_red_s_es_eliminada_en_record_analysis():
    """'Esto podría ser RED-S...' debe ser eliminado solo cuando el
    guardrail conoce el use case `anthropometric_record_analysis`
    (regla `reds_term` en `_RECORD_ANALYSIS_RULES`)."""
    g = Guardrails(use_case="anthropometric_record_analysis")
    text = (
        "Esto podría ser RED-S y conviene observar la energía disponible "
        "en las próximas semanas."
    )
    report = g.scrub_with_report(text)
    assert "reds_term" in report.violations
    assert "RED-S" not in report.text


def test_adversarial_output_valido_pasa_sin_violaciones():
    """Un output que respeta las restricciones no debe disparar ninguna regla."""
    g = Guardrails()
    text = (
        "Su hijo se encuentra en fase Pre-PHV. En las próximas semanas el "
        "club mantendrá énfasis técnico y descanso adecuado; cualquier "
        "molestia persistente la revisará el entrenador."
    )
    report = g.scrub_with_report(text)
    assert report.violations == ()
    assert not report.rejected
    # El texto debería pasar sin cambios materiales
    assert report.text == text.strip()


def test_adversarial_combinacion_supera_max_violations_y_rechaza():
    """Cuando se acumulan ≥ MAX_VIOLATIONS_BEFORE_REJECT violaciones el
    saneador debe lanzar `LLMSchemaError`."""
    g = Guardrails()
    # Combinamos varias violaciones globales para superar el umbral.
    text = (
        "Su hijo está por encima del promedio para su edad y en el "
        "percentil 75 de peso. Su IMC ronda los 22. Comparado con otros "
        "niños del club, va muy bien."
    )
    report = g.scrub_with_report(text)
    # Verificamos que efectivamente supera el umbral configurado
    assert len(report.violations) >= MAX_VIOLATIONS_BEFORE_REJECT
    with pytest.raises(LLMSchemaError):
        g.scrub(text)


def test_adversarial_phrases_estructura_post_scrub():
    """Tras saneo, ninguna de las frases prohibidas debe sobrevivir."""
    g = Guardrails()
    cases = [
        "Su hijo está por encima del promedio para su edad.",
        "Tiene un IMC alrededor de 21.",
        "Comparado con otros niños del club, va bien.",
        "Su z-score de talla está cerca de +1.",
    ]
    for raw in cases:
        report = g.scrub_with_report(raw)
        assert report.violations, f"Esperaba violación para: {raw!r}"
        sanitized_lower = report.text.lower()
        # Ningún término comparativo o clínico debe sobrevivir
        for forbidden in (
            "promedio",
            "percentil",
            "otros niños",
            "imc",
            "z-score",
            "z score",
        ):
            assert forbidden not in sanitized_lower, (
                f"'{forbidden}' sobrevivió en: {report.text!r}"
            )


# ---------------------------------------------------------------------------
# 2. Propiedades del system prompt cargado por PromptRegistry
# ---------------------------------------------------------------------------


def test_system_prompt_define_funcion_analitica():
    """El system prompt debe declarar al LLM como función analítica
    (cambio central de Ola 2). El término exacto es importante para que
    los tests legacy y el contrato Ola 2 se mantengan estables."""
    r = PromptRegistry()
    sp = r.system_prompt().lower()
    assert "función analítica" in sp


@pytest.mark.parametrize(
    "forbidden",
    [
        "potenciómetro",   # regla guardrail powermeter_under_13
        "suplemento",      # regla guardrail suplements (cubre singular/plural)
    ],
)
def test_system_prompt_no_contiene_terminos_enforced_por_guardrails(forbidden):
    """Los términos pedagógicos cubiertos por guardrails NO deben aparecer
    en el system prompt — están en `tone_guide.md` como referencia humana."""
    r = PromptRegistry()
    sp = r.system_prompt().lower()
    assert forbidden not in sp, (
        f"El system prompt no debe mencionar '{forbidden}'; es responsabilidad "
        f"de los guardrails y vive en tone_guide.md."
    )


# ---------------------------------------------------------------------------
# 3. `tone_guide.md` existe pero no es system prompt
# ---------------------------------------------------------------------------


def test_tone_guide_existe_como_archivo_de_referencia():
    """`tone_guide.md` debe estar en disco junto a `system_principles.md`."""
    tone_guide = (
        Path(__file__).resolve().parent.parent
        / "app" / "services" / "ai" / "prompts" / "tone_guide.md"
    )
    assert tone_guide.exists(), "tone_guide.md debe existir como referencia humana"
    content = tone_guide.read_text(encoding="utf-8")
    assert "Diversión primero" in content
    assert "Cero suplementos" in content


def test_tone_guide_no_es_cargado_por_system_prompt():
    """`PromptRegistry.system_prompt()` NO debe leer tone_guide.md.

    Verificamos que el system prompt cargado no contiene ninguna de las
    frases distintivas del tone guide. Esto detecta accidentes futuros si
    alguien intentara concatenar tone_guide.md al system prompt.
    """
    r = PromptRegistry()
    sp = r.system_prompt()
    # Frases distintivas del tone guide (encabezados + reglas):
    distintivas = (
        "Diversión primero",
        "referencia humana",
        "Mapeo a guardrails",
        "Cero suplementos",
    )
    for frase in distintivas:
        assert frase not in sp, (
            f"'{frase}' apareció en system_prompt — tone_guide.md no debe cargarse."
        )
