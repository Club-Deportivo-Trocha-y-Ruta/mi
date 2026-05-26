"""Tests de Guardrails — enforce principios no negociables del CLAUDE.md."""

from __future__ import annotations

import pytest

from app.services.ai.errors import LLMSchemaError
from app.services.ai.guardrails import Guardrails
from app.services.ai.use_cases.athlete_monthly_newsletter import AthleteNewsletterGuardrails


# ---------------------------------------------------------------------------
# Suplementos
# ---------------------------------------------------------------------------


def test_supplement_keyword_replaced():
    g = Guardrails()
    out = g.scrub("Recomendamos creatina antes del entrenamiento.")
    assert "creatina" not in out.lower()
    assert "comida real" in out


def test_protein_powder_replaced():
    g = Guardrails()
    out = g.scrub("Le sugiero proteína en polvo después del esfuerzo.")
    assert "proteína" not in out.lower() or "polvo" not in out.lower()


# ---------------------------------------------------------------------------
# Días por semana
# ---------------------------------------------------------------------------


def test_six_days_replaced():
    g = Guardrails()
    out = g.scrub("Entrena 6 días por semana para progresar.")
    assert "6 días" not in out
    assert "máximo 5 días" in out


def test_seven_days_replaced():
    g = Guardrails()
    out = g.scrub("El plan será 7 días a la semana.")
    assert "7 días" not in out
    assert "máximo 5 días" in out


def test_five_days_unchanged():
    g = Guardrails()
    text = "Entrena 5 días por semana, descansa los demás."
    out = g.scrub(text)
    # No debe activar la regla — máximo permitido.
    assert "5 días" in out


# ---------------------------------------------------------------------------
# Cadencia
# ---------------------------------------------------------------------------


def test_low_cadence_corrected():
    g = Guardrails()
    out = g.scrub("Pedalea a 55 rpm para fortalecer.")
    assert "55 rpm" not in out
    assert "≥60 rpm" in out


def test_high_cadence_unchanged():
    g = Guardrails()
    text = "Mantén una cadencia de 80 rpm."
    out = g.scrub(text)
    assert "80 rpm" in out


# ---------------------------------------------------------------------------
# Calorías con atleta
# ---------------------------------------------------------------------------


def test_calorie_counting_replaced():
    g = Guardrails()
    out = g.scrub("Pídele al atleta llevar un conteo de calorías diario.")
    assert "calorías" not in out.lower() or "conteo" not in out.lower()
    assert "variedad y calidad" in out


# ---------------------------------------------------------------------------
# Potenciómetro según grupo de edad
# ---------------------------------------------------------------------------


def test_powermeter_blocked_for_10_12():
    g = Guardrails(age_group="10-12")
    out = g.scrub("Usa el potenciómetro para medir vatios.")
    assert "potenciómetro" not in out.lower()
    assert "vatios" not in out.lower()


def test_powermeter_allowed_for_13_15():
    g = Guardrails(age_group="13-15")
    text = "Usa el potenciómetro con supervisión."
    out = g.scrub(text)
    assert "potenciómetro" in out.lower()


# ---------------------------------------------------------------------------
# Texto limpio pasa intacto
# ---------------------------------------------------------------------------


def test_clean_text_passes_through():
    g = Guardrails()
    text = (
        "Tu hijo está en Pre-PHV. Recomendamos sesiones técnicas y juego, "
        "5 días por semana con cadencia de 80 rpm."
    )
    out = g.scrub(text)
    assert out == text.strip()


# ---------------------------------------------------------------------------
# Guardrails boletín mensual — términos nutricionales clasificatorios (P6)
# Ley 1098/2006 Art. 27: solo personal de salud autorizado puede emitir
# etiquetas diagnósticas sobre menores. Regresión contra gap detectado en
# auditoría de curvas de percentiles (2026-05-25).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden_term", [
    "obesidad",
    "Obesidad",
    "sobrepeso",
    "bajo peso",
    "talla baja",
    "desnutrición",
    "desnutricion",
])
def test_newsletter_guardrail_blocks_nutritional_labels(forbidden_term: str):
    """AthleteNewsletterGuardrails debe rechazar etiquetas diagnósticas nutricionales."""
    from app.services.ai.errors import LLMSchemaError

    g = AthleteNewsletterGuardrails()
    # Texto sintético con suficiente largo (≥10 palabras) para pasar la guardia de
    # MIN_WORDS pero que contiene el término prohibido.
    text = (
        f"Este mes el deportista mostró buen progreso técnico "
        f"aunque presenta {forbidden_term} según la evaluación de crecimiento."
    )
    with pytest.raises(LLMSchemaError, match="médicos/nutricionales"):
        g.scrub_block(text)


# ---------------------------------------------------------------------------
# Demasiadas violaciones → rechazo
# ---------------------------------------------------------------------------


def test_too_many_violations_raises():
    g = Guardrails()
    text = (
        "Toma creatina y proteína en polvo. "
        "Entrena 6 días por semana a 50 rpm."
    )
    with pytest.raises(LLMSchemaError):
        g.scrub(text)


def test_report_lists_violations():
    g = Guardrails()
    report = g.scrub_with_report("Toma creatina hoy.")
    assert "suplements" in report.violations
    assert not report.rejected


# ---------------------------------------------------------------------------
# Entrenamiento diario (regla `daily_training`)
# ---------------------------------------------------------------------------
#
# Bypass del LLM al límite "máx 5 días/semana": formulaciones que no usan
# el patrón "6/7 días por semana" pero implican entrenamiento diario.
# La regla exige co-ocurrencia con vocabulario de entrenamiento para evitar
# falsos positivos como "recordar todos los días tomar agua".


@pytest.mark.parametrize(
    "frase",
    [
        # "todos los días" + verbo/sustantivo de entrenamiento (ambos órdenes)
        "Entrenar todos los días para mejorar.",
        "Todos los días subir a la bicicleta es ideal.",
        # variante sin tilde
        "Entrenar todos los dias para progresar.",
        # "diariamente"
        "Diariamente con la bicicleta para mejorar la técnica.",
        "Pedalear diariamente al ritmo del grupo.",
        # "cada día" / "cada dia"
        "Rodar cada día con el club.",
        "Cada dia montar bicicleta a buen ritmo.",
        # Rama numérica/palabra explícita (no requiere contexto adicional)
        # NOTA: se omiten frases con "7 días por semana" porque las captura
        # primero la regla `days_per_week_excess`, dejando un texto que ya no
        # contiene "7"/"siete" para que `daily_training` enganche.
        "Le sugiero siete sesiones por semana.",
        "Plan: 7 sesiones a la semana sostenidas.",
        "Siete días semanales en bicicleta.",
    ],
)
def test_daily_training_detected(frase):
    g = Guardrails()
    report = g.scrub_with_report(frase)
    assert "daily_training" in report.violations, (
        f"La frase debería disparar daily_training: {frase!r}"
    )
    # El reemplazo aporta el mensaje correctivo
    assert "máximo 5 días por semana" in report.text.lower()


@pytest.mark.parametrize(
    "frase",
    [
        # Sin contexto de entrenamiento — no debe disparar
        "Recordar todos los días tomar agua.",
        "Diariamente leer un libro ayuda al desarrollo.",
        "Cada día es una nueva oportunidad.",
        "Cepillarse los dientes todos los días.",
    ],
)
def test_daily_training_not_triggered_in_non_training_context(frase):
    g = Guardrails()
    report = g.scrub_with_report(frase)
    assert "daily_training" not in report.violations, (
        f"La frase NO debería disparar daily_training: {frase!r}"
    )
    # El texto se mantiene esencialmente igual (puede haber strip pero sin cambios)
    assert report.text.lower().rstrip(".") in frase.lower().rstrip(".") or \
        frase.lower().rstrip(".").replace(".", "") in report.text.lower()


def test_daily_training_replacement_message():
    """Cuando dispara, reemplaza por el mensaje correctivo del club."""
    g = Guardrails()
    out = g.scrub("Entrenar diariamente con la bicicleta acelera el progreso.")
    assert "máximo 5 días por semana" in out.lower()
    assert "diariamente" not in out.lower()


# ---------------------------------------------------------------------------
# Comparativas poblacionales / cuasi-diagnósticas (`comparative_norm`)
# ---------------------------------------------------------------------------
#
# Regla GLOBAL: aplica a todos los use cases que escriban a padres. Bajo la
# Ley 1098/2006 Art. 27 solo personal de salud autorizado puede emitir
# afirmaciones comparativas poblacionales sobre menores.


@pytest.mark.parametrize(
    "frase",
    [
        # Variante A: por encima/debajo del promedio
        "Su hijo está por encima del promedio para su edad.",
        "Su talla está por debajo de lo esperado.",
        "Se encuentra sobre la media de su grupo.",
        "Bajo el promedio para su edad en estatura.",
        # Variante B: más alto/bajo que la mayoría/otros niños
        "Es más alto que la mayoría de su edad.",
        "Está más bajo que otros niños del club.",
        # Variante C: percentiles
        "Está en el percentil 75 de peso.",
        "Se ubica en el percentil 25.",
        # Variante D: comparado con
        "Comparado con otros niños, su crecimiento es bueno.",
        # Variante E: respecto a la norma
        "Respecto a la norma poblacional, va bien.",
    ],
)
def test_comparative_norm_detected(frase):
    g = Guardrails()
    report = g.scrub_with_report(frase)
    assert "comparative_norm" in report.violations, (
        f"La frase debería disparar comparative_norm: {frase!r}"
    )
    # El replacement es vacío: ninguno de los términos comparativos debe quedar.
    assert "promedio" not in report.text.lower()
    assert "percentil" not in report.text.lower()
    assert "mayoría" not in report.text.lower()
    assert "norma poblacional" not in report.text.lower()


@pytest.mark.parametrize(
    "frase",
    [
        # No comparación poblacional — uso geográfico/genérico de "por encima"
        "El club queda por encima del nivel del mar a 1000 m.",
        # Frase clínica permitida (cualitativa, no comparativa con población)
        "Su estado nutricional es adecuado y su maduración es Pre-PHV.",
        # Frase deportiva sin referencia poblacional
        "Mantén una cadencia de 80 rpm en zonas Z1-Z2.",
    ],
)
def test_comparative_norm_not_triggered(frase):
    g = Guardrails()
    report = g.scrub_with_report(frase)
    assert "comparative_norm" not in report.violations, (
        f"La frase NO debería disparar comparative_norm: {frase!r}"
    )


# ---------------------------------------------------------------------------
# Métricas clínicas numéricas inventadas (`numeric_clinical_metrics`)
# ---------------------------------------------------------------------------
#
# Regla GLOBAL: el context_builder no entrega valores numéricos clínicos al
# LLM, así que cualquier número con término clínico es una alucinación.


@pytest.mark.parametrize(
    "frase",
    [
        "Su IMC ronda los 22.",
        "El índice de masa corporal alrededor de 18,5 indica algo.",
        "El z-score de talla cerca de +1 sugiere progresión.",
        "Sus z scores son cercanos a 0.",
        "Puntaje z de -0.5 en peso.",
        "Percentiles cercanos a 50.",
    ],
)
def test_numeric_clinical_metrics_detected(frase):
    g = Guardrails()
    report = g.scrub_with_report(frase)
    assert "numeric_clinical_metrics" in report.violations, (
        f"La frase debería disparar numeric_clinical_metrics: {frase!r}"
    )


@pytest.mark.parametrize(
    "frase",
    [
        # Número sin término clínico → no toca
        "Mantén una cadencia de 80 rpm.",
        # Término clínico sin número adyacente → no toca
        "Su estado nutricional es adecuado.",
        # Mención de IMC en abstracto (sin número en ventana) → no toca
        "Conversen con su pediatra sobre el IMC y otros indicadores.",
    ],
)
def test_numeric_clinical_metrics_not_triggered(frase):
    g = Guardrails()
    report = g.scrub_with_report(frase)
    assert "numeric_clinical_metrics" not in report.violations, (
        f"La frase NO debería disparar numeric_clinical_metrics: {frase!r}"
    )


def test_comparative_norm_report_violation_name():
    g = Guardrails()
    report = g.scrub_with_report("Su hijo está sobre la media del grupo.")
    assert "comparative_norm" in report.violations


def test_numeric_clinical_metrics_report_violation_name():
    g = Guardrails()
    report = g.scrub_with_report("Su IMC ronda 22.")
    assert "numeric_clinical_metrics" in report.violations
