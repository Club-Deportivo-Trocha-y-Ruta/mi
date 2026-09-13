"""Tests de :mod:`app.services.ai.anthro.prechecks` (feature 042, T051).

Catálogo de reglas R01-R12 — categoría y ``must_block`` verificados contra
``specs/042-traceable-growth-ai/contracts/golden-eval-case.md`` §3 (fuente de
verdad), no contra el docstring de ``prechecks.py`` ni contra la intuición
del autor de este archivo. Donde el contrato y la implementación difieren
(ver ``test_r04_...`` más abajo) el test sigue el contrato — si eso lo deja
en rojo, es una discrepancia real a reportar, no a maquillar aquí.

Todos los nombres, series numéricas y fechas son sintéticos (CLAUDE.md /
Ley 1581) — ningún dato de un atleta real de Trocha y Ruta aparece en este
archivo.
"""

from __future__ import annotations

from app.services.ai.anthro.context import AnalysisContext
from app.services.ai.anthro.prechecks import run_prechecks
from app.services.ai.anthro.schemas import (
    AnthropometryInsightV1,
    Confidence,
    ConfidenceLevel,
)

# ---------------------------------------------------------------------------
# Fábricas mínimas
# ---------------------------------------------------------------------------


def _confidence(reason: str = "Hay mediciones suficientes para esta observación.") -> Confidence:
    return Confidence(level=ConfidenceLevel.MEDIUM, reason=reason)


def _insight(
    *,
    audience: str = "family",
    summary_line: str = "La estatura avanza de forma estable esta temporada.",
    changes: list[str] | None = None,
    meaning: list[str] | None = None,
    next_weeks: list[str] | None = None,
    warning_signs: list[str] | None = None,
    data_gaps: list[str] | None = None,
    confidence: Confidence | None = None,
) -> AnthropometryInsightV1:
    """Insight "limpio" por defecto: no dispara ninguna de las R01-R12.

    Cada test de violación parte de esta base y sobreescribe SOLO el campo
    necesario para disparar su regla, para poder afirmar que ninguna otra
    regla se dispara de rebote.
    """
    return AnthropometryInsightV1(
        audience=audience,
        summary_line=summary_line,
        changes=changes if changes is not None else ["El cambio de estatura fue moderado."],
        meaning=meaning
        if meaning is not None
        else ["Esto refleja un ritmo de desarrollo dentro de lo esperado."],
        next_weeks=next_weeks
        if next_weeks is not None
        else ["Mantener la rutina habitual de entrenamiento."],
        warning_signs=warning_signs if warning_signs is not None else [],
        confidence=confidence if confidence is not None else _confidence(),
        data_gaps=data_gaps if data_gaps is not None else [],
        word_count=20,
    )


def _context(
    *,
    identity: dict | None = None,
    measurement_deltas: dict | None = None,
    longitudinal_series: list[dict] | None = None,
    growth_summary: dict | None = None,
    training_load_window: dict | None = None,
    previous_analysis: dict | None = None,
) -> AnalysisContext:
    return AnalysisContext(
        identity=identity if identity is not None else {"age_decimal": 12.5, "age_group": "11-13"},
        measurement_deltas=measurement_deltas,
        longitudinal_series=longitudinal_series if longitudinal_series is not None else [],
        growth_summary=growth_summary if growth_summary is not None else {},
        training_load_window=training_load_window,
        previous_analysis=previous_analysis,
    )


def _only(result, rule_id: str):
    """La única violación de ``rule_id`` en ``result`` (falla si no hay exactamente una)."""
    matches = [v for v in result.violations if v.rule_id == rule_id]
    assert len(matches) == 1, f"esperaba exactamente una violación {rule_id}, hubo {matches}"
    return matches[0]


def _none(result, rule_id: str) -> None:
    assert not any(v.rule_id == rule_id for v in result.violations), (
        f"{rule_id} no debía dispararse: {result.violations}"
    )


# ---------------------------------------------------------------------------
# R01 — comparación poblacional / con pares (privacy, must_block)
# ---------------------------------------------------------------------------


def test_r01_population_comparison_blocks():
    context = _context()
    dirty = _insight(changes=["Su estatura está por encima del promedio para su edad."])

    result = run_prechecks(dirty, context)

    violation = _only(result, "R01")
    assert violation.category == "privacy"
    assert violation.must_block is True
    assert result.must_block is True

    clean = _insight()
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R01")


# ---------------------------------------------------------------------------
# R02 — etiqueta diagnóstica o clínica (ltad, must_block)
# ---------------------------------------------------------------------------


def test_r02_diagnostic_label_blocks():
    context = _context()
    dirty = _insight(changes=["Este cambio no constituye un diagnóstico médico."])

    result = run_prechecks(dirty, context)

    violation = _only(result, "R02")
    assert violation.category == "ltad"
    assert violation.must_block is True
    assert result.must_block is True

    clean = _insight()
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R02")


# ---------------------------------------------------------------------------
# R03 — número inventado (grounding, degrada)
# ---------------------------------------------------------------------------


def test_r03_invented_number_degrades_only():
    context = _context()  # números permitidos: 12.5 / 12 (edad) + estructurales 2/3/4
    dirty = _insight(changes=["El avance fue de 7 unidades este periodo."])

    result = run_prechecks(dirty, context)

    violation = _only(result, "R03")
    assert violation.category == "grounding"
    assert violation.must_block is False
    assert result.must_block is False

    clean = _insight(changes=["El avance se mantuvo en 3 unidades este periodo."])
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R03")


# ---------------------------------------------------------------------------
# R04 — fecha exacta / edad decimal como predicción de PHV
# ---------------------------------------------------------------------------
#
# CONTRATO vs IMPLEMENTACIÓN: golden-eval-case.md §3 lista R04 como
# categoría "ltad" (must_block); `prechecks.py::check_r04_exact_phv_prediction`
# devuelve `category="privacy"`. Este test sigue el contrato (instrucción
# explícita del feature: la fuente de verdad es el contrato, no el código) —
# si queda en rojo por esto, es la discrepancia real a reportar al
# orquestador, no algo que este test deba disimular.


def test_r04_exact_phv_prediction_blocks():
    # age_at_phv=13.4 vive en el contexto (dato legítimo del analista) para
    # que la mención de "13.4 años" en el borrador no dispare TAMBIÉN R03
    # (número inventado) — queremos aislar R04.
    context = _context(growth_summary={"age_at_phv": 13.4})
    dirty = _insight(
        meaning=["Se estima el pico de crecimiento cerca de los 13.4 años."]
    )

    result = run_prechecks(dirty, context)

    violation = _only(result, "R04")
    assert violation.category == "ltad"
    assert violation.must_block is True
    assert result.must_block is True

    clean = _insight()
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R04")


# ---------------------------------------------------------------------------
# R05 — velocidad presentada como confiable sin serlo (grounding, degrada)
# ---------------------------------------------------------------------------


def test_r05_unreliable_velocity_claimed_reliable_degrades_only():
    context = _context(measurement_deltas={"velocity_confidence": "early_signal"})
    dirty = _insight(changes=["La velocidad de crecimiento es confiable en esta etapa."])

    result = run_prechecks(dirty, context)

    violation = _only(result, "R05")
    assert violation.category == "grounding"
    assert violation.must_block is False
    assert result.must_block is False

    clean = _insight()
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R05")

    # Si el contexto SÍ marca la velocidad como confiable, la misma frase deja
    # de ser una violación (no hay nada que corroborar).
    reliable_context = _context(measurement_deltas={"velocity_confidence": "reliable"})
    reliable_result = run_prechecks(dirty, reliable_context)
    _none(reliable_result, "R05")


# ---------------------------------------------------------------------------
# R06 — nombre/identificador prohibido filtrado (privacy, must_block)
# ---------------------------------------------------------------------------
#
# Nombre SINTÉTICO (no corresponde a ningún atleta real ni a la lista real
# de nombres prohibidos del club) usado solo para ejercer la regla.

_FORBIDDEN_NAME = "Zorion Kalantxo"


def test_r06_leaked_identifier_blocks():
    context = _context()
    dirty = _insight(changes=[f"Se mencionó por error a {_FORBIDDEN_NAME} en la nota."])

    result = run_prechecks(dirty, context, forbidden_names=(_FORBIDDEN_NAME,))

    violation = _only(result, "R06")
    assert violation.category == "privacy"
    assert violation.must_block is True
    assert result.must_block is True

    # Sin el nombre en el texto, la misma lista de nombres prohibidos no
    # dispara nada.
    clean = _insight()
    clean_result = run_prechecks(clean, context, forbidden_names=(_FORBIDDEN_NAME,))
    _none(clean_result, "R06")

    # Y sin ninguna lista (default del llamador), tampoco puede disparar —
    # forbidden_names es keyword-only y por defecto una tupla vacía.
    default_result = run_prechecks(dirty, context)
    _none(default_result, "R06")


# ---------------------------------------------------------------------------
# R07 — presupuesto de palabras excedido (style, degrada), tolerancia 10%
# ---------------------------------------------------------------------------
#
# Presupuesto family = 180 palabras; con 10% de tolerancia el límite real es
# 180*1.10 = 198.0 (exceeds_word_budget exige `> límite`). 198 palabras debe
# quedar justo DENTRO de la tolerancia (sin violación); 199, justo FUERA.


def _insight_with_word_count(total_words: int) -> AnthropometryInsightV1:
    # summary_line (1) + meaning (4) + next_weeks (5) = 10 palabras fijas;
    # el resto del presupuesto se rellena en `changes` con un token neutro
    # que no dispara ninguna otra regla (sin dígitos, sin vocabulario
    # clínico/comparativo/de suplementos, sin markdown).
    filler_words = total_words - 10
    assert filler_words > 0
    filler = " ".join(["cm"] * filler_words)
    return _insight(
        summary_line="Resumen.",
        changes=[filler],
        meaning=["Significado breve del cambio."],
        next_weeks=["Seguir entrenando normalmente esta semana."],
    )


def test_r07_word_budget_ten_percent_tolerance():
    context = _context()

    just_inside = _insight_with_word_count(198)
    inside_result = run_prechecks(just_inside, context)
    _none(inside_result, "R07")

    just_outside = _insight_with_word_count(199)
    outside_result = run_prechecks(just_outside, context)
    violation = _only(outside_result, "R07")
    assert violation.category == "style"
    assert violation.must_block is False
    assert outside_result.must_block is False


# ---------------------------------------------------------------------------
# R08 — elogio desproporcionado sobre un delta no significativo (style, degrada)
# ---------------------------------------------------------------------------


def test_r08_sycophancy_over_non_significant_delta_degrades_only():
    context = _context(
        measurement_deltas={
            "delta_height_significant": False,
            "delta_weight_significant": False,
        }
    )
    dirty = _insight(changes=["Tuvo un excelente progreso en esta medición."])

    result = run_prechecks(dirty, context)

    violation = _only(result, "R08")
    assert violation.category == "style"
    assert violation.must_block is False
    assert result.must_block is False

    clean = _insight()
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R08")

    # La misma frase de elogio deja de ser una violación cuando el contexto
    # dice que el delta SÍ es significativo.
    significant_context = _context(measurement_deltas={"delta_height_significant": True})
    significant_result = run_prechecks(dirty, significant_context)
    _none(significant_result, "R08")


# ---------------------------------------------------------------------------
# R09 — mención de suplemento (ltad, must_block)
# ---------------------------------------------------------------------------


def test_r09_supplement_mention_blocks():
    context = _context()
    dirty = _insight(changes=["Se recomienda evaluar el uso de creatina en su alimentación."])

    result = run_prechecks(dirty, context)

    violation = _only(result, "R09")
    assert violation.category == "ltad"
    assert violation.must_block is True
    assert result.must_block is True

    clean = _insight()
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R09")


# ---------------------------------------------------------------------------
# R10 — Markdown/viñetas dentro de un campo (style, degrada)
# ---------------------------------------------------------------------------


def test_r10_markdown_in_fields_degrades_only():
    context = _context()
    dirty = _insight(meaning=["Esto es **muy importante** para el desarrollo."])

    result = run_prechecks(dirty, context)

    violation = _only(result, "R10")
    assert violation.category == "style"
    assert violation.must_block is False
    assert result.must_block is False

    clean = _insight()
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R10")


# ---------------------------------------------------------------------------
# R11 — cruce de fase sin corroborar presentado como confirmado (grounding,
# must_block — excepción documentada a "grounding solo degrada")
# ---------------------------------------------------------------------------


def test_r11_uncorroborated_phase_crossing_blocks():
    context = _context(
        measurement_deltas={
            "crossed_phv_phase": True,
            "phase_crossing_corroborated": False,
            "prev_maturation_status": "Pre-PHV",
        }
    )
    dirty = _insight(
        meaning=["El cambio de fase ya está confirmado con esta medición."]
    )

    result = run_prechecks(dirty, context)

    violation = _only(result, "R11")
    assert violation.category == "grounding"
    assert violation.must_block is True
    assert result.must_block is True

    clean = _insight()
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R11")

    # Con corroboración, la misma frase deja de ser una violación.
    corroborated_context = _context(
        measurement_deltas={
            "crossed_phv_phase": True,
            "phase_crossing_corroborated": True,
        }
    )
    corroborated_result = run_prechecks(dirty, corroborated_context)
    _none(corroborated_result, "R11")


# ---------------------------------------------------------------------------
# R12 — contenido exclusivo del entrenador filtrado a audiencia familiar
# (privacy, must_block)
# ---------------------------------------------------------------------------


def test_r12_coach_only_leak_to_family_blocks():
    # growth_velocity_cm_per_year vive legítimamente en measurement_deltas
    # (dato de entrenador) — R12 vigila que esa misma cifra no se filtre
    # textualmente a una salida `audience="family"`.
    context = _context(measurement_deltas={"growth_velocity_cm_per_year": 9.5})
    dirty = _insight(
        audience="family",
        changes=["Su velocidad de crecimiento fue de 9.5 cm/año en este periodo."],
    )

    result = run_prechecks(dirty, context)

    violation = _only(result, "R12")
    assert violation.category == "privacy"
    assert violation.must_block is True
    assert result.must_block is True

    clean = _insight(audience="family")
    clean_result = run_prechecks(clean, context)
    _none(clean_result, "R12")

    # La misma frase dirigida al entrenador no es una fuga.
    coach_insight = _insight(
        audience="coach",
        changes=["Su velocidad de crecimiento fue de 9.5 cm/año en este periodo."],
    )
    coach_result = run_prechecks(coach_insight, context)
    _none(coach_result, "R12")


# ---------------------------------------------------------------------------
# Propiedades agregadas de PrecheckResult
# ---------------------------------------------------------------------------


def test_must_block_true_iff_any_violation_blocks():
    context = _context(
        measurement_deltas={
            "velocity_confidence": "early_signal",
            "delta_height_significant": False,
            "delta_weight_significant": False,
        }
    )

    # Solo violaciones que degradan (R05 + R08): must_block debe ser False
    # aunque haya violaciones.
    degrade_only = _insight(
        changes=[
            "La velocidad de crecimiento es confiable en esta etapa.",
            "Tuvo un excelente progreso en esta medición.",
        ]
    )
    degrade_result = run_prechecks(degrade_only, context)
    assert len(degrade_result.violations) >= 2
    assert all(v.must_block is False for v in degrade_result.violations)
    assert degrade_result.must_block is False

    # Agregando una violación que sí bloquea (R09), el agregado pasa a True.
    with_blocker = _insight(
        changes=[
            "La velocidad de crecimiento es confiable en esta etapa.",
            "Tuvo un excelente progreso en esta medición.",
            "Se recomienda evaluar el uso de creatina en su alimentación.",
        ]
    )
    blocker_result = run_prechecks(with_blocker, context)
    assert any(v.must_block is True for v in blocker_result.violations)
    assert blocker_result.must_block is True


def test_privacy_and_developmental_safety_rules_block_grounding_and_style_degrade():
    """Invariante del catálogo (contracts/golden-eval-case.md §3):

    Las reglas de privacidad y seguridad de desarrollo (categorías
    ``privacy``/``ltad``) siempre bloquean; las de ``grounding``/``style``
    solo degradan la confianza — con la única excepción documentada de R11
    (``grounding`` que sí bloquea, por ser un cruce de fase presentado como
    confirmado sin corroboración).
    """
    always_block_rules = {"R01", "R02", "R04", "R06", "R09", "R12"}
    degrade_only_rules = {"R03", "R05", "R07", "R08", "R10"}
    grounding_exception = {"R11"}

    context = _context(
        growth_summary={"age_at_phv": 13.4},
        measurement_deltas={
            "velocity_confidence": "early_signal",
            "delta_height_significant": False,
            "delta_weight_significant": False,
            "crossed_phv_phase": True,
            "phase_crossing_corroborated": False,
        },
    )
    kitchen_sink = _insight(
        audience="family",
        summary_line="Su estatura está por encima del promedio para su edad.",
        changes=[
            "Este cambio no constituye un diagnóstico médico.",
            "El avance fue de 7 unidades este periodo.",
            "La velocidad de crecimiento es confiable en esta etapa.",
        ],
        meaning=[
            "Se estima el pico de crecimiento cerca de los 13.4 años.",
            "El cambio de fase ya está confirmado con esta medición.",
        ],
        next_weeks=[
            "Se recomienda evaluar el uso de creatina en su alimentación.",
            "Esto es **muy importante** para el próximo control.",
        ],
    )

    result = run_prechecks(kitchen_sink, context)
    seen_rule_ids = {v.rule_id for v in result.violations}

    # No afirmamos que las doce disparen a la vez (algunas son mutuamente
    # exclusivas por diseño, p. ej. R08 exige delta no significativo) — solo
    # que, de las que sí dispararon, el bloqueo coincide con su categoría.
    for violation in result.violations:
        if violation.rule_id in always_block_rules:
            assert violation.category in {"privacy", "ltad"}
            assert violation.must_block is True
        elif violation.rule_id in degrade_only_rules:
            assert violation.category in {"grounding", "style"}
            assert violation.must_block is False
        elif violation.rule_id in grounding_exception:
            assert violation.category == "grounding"
            assert violation.must_block is True

    assert seen_rule_ids & always_block_rules  # al menos una regla de bloqueo disparó
    assert result.must_block is True


def test_precheck_violation_detail_never_echoes_offending_text():
    """Requisito de privacidad (Ley 1581), no de estilo: ``detail`` es SIEMPRE
    una frase genérica — nunca reproduce el fragmento del borrador que
    disparó la regla, ni el nombre detectado.
    """
    context = _context(measurement_deltas={"growth_velocity_cm_per_year": 9.5})
    offending_phrase = f"Se mencionó por error a {_FORBIDDEN_NAME} en la nota."
    dirty = _insight(
        audience="family",
        changes=[
            offending_phrase,
            "Su estatura está por encima del promedio para su edad.",
            "Su velocidad de crecimiento fue de 9.5 cm/año en este periodo.",
        ],
    )

    result = run_prechecks(dirty, context, forbidden_names=(_FORBIDDEN_NAME,))

    assert result.violations, "se esperaban violaciones para ejercer este test"
    for violation in result.violations:
        assert _FORBIDDEN_NAME not in violation.detail
        assert "9.5" not in violation.detail
        assert "por encima del promedio" not in violation.detail
        assert offending_phrase not in violation.detail
