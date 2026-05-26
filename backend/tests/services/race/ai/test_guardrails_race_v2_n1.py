"""Invariantes N=1 (Task #15-18, #20) sobre guardrails v2.

Cubre el veto duro N=1: cuando ``Guardrails(use_case="race_analyst_v2",
is_first_in_season=True)`` rechaza cualquier output con verbos de tendencia o
progresión, porque con una sola válida disputada en TODA la temporada no hay
datos longitudinales que soporten esa lectura. El veto vive en
``app.services.ai.guardrails`` (:func:`check_v2_veto_n1` +
tupla ``_VETO_N1_VERBS``).

Task #20: el banner + veto N=1 gatillan por ``is_first_in_season``
(atleta tiene 1 válida en toda la temporada), NO por ``len(valida_nums)``
del set lanzado. Evita falsos positivos cuando el coach lanza un set [V4]
aislado para un atleta que ya tiene V1, V2, V3 en la temporada.

CA-6 (spec): la sección "Recorrido hasta acá" debe arrancar con la frase
literal estándar para reforzar al lector que la interpretación es
descriptiva y no proyectiva.
"""
import pytest

from app.services.ai.guardrails import (
    Guardrails,
    _VETO_N1_VERBS,
    check_v2_veto_n1,
)


N1_SUFFIX_OK = (
    "## Qué pasó en esta válida\n"
    "La deportista participó y completó las vueltas exigidas.\n\n"
    "## Recorrido hasta acá\n"
    "Con una sola válida disputada aún no es posible establecer una "
    "tendencia de progresión. Ese día ejecutó su prueba y registró "
    "tiempo competitivo.\n\n"
    "## Hacia dónde va\n"
    "Practicar transferencia de peso en bermas (categoría=technique, "
    "prioridad=med) [1].\n"
)


class TestVetoN1:
    @pytest.mark.parametrize("verb", list(_VETO_N1_VERBS))
    def test_each_verb_is_detected(self, verb):
        text = f"La deportista {verb} durante la prueba."
        assert verb in check_v2_veto_n1(text)

    def test_clean_text_passes(self):
        """Frase canónica CA-6 ya no incluye sustantivos en _VETO_N1_VERBS.

        Solo verbos conjugados afirmativos. La frase canónica usa
        'tendencia'/'progresión' como sustantivos negados, no veto.
        """
        assert check_v2_veto_n1(N1_SUFFIX_OK) == []

    def test_guardrails_rejects_when_is_first_in_season_true(self):
        """N=1 gatilla por temporada, no por set lanzado."""
        g = Guardrails(
            use_case="race_analyst_v2",
            is_first_in_season=True,
        )
        bad = (
            "## Qué pasó en esta válida\nOk.\n"
            "## Recorrido hasta acá\nLa deportista mejoró respecto a la "
            "anterior y subió posiciones.\n"
            "## Hacia dónde va\nReforzar técnica.\n"
        )
        report = g.scrub_with_report(bad)
        assert report.rejected is True
        assert any(v.startswith("veto_n1_") for v in report.violations)

    def test_guardrails_passes_when_is_first_in_season_false(self):
        """Con historial previo, los verbos de tendencia son válidos."""
        g = Guardrails(
            use_case="race_analyst_v2",
            is_first_in_season=False,
        )
        text_with_progresion = (
            "## Qué pasó en esta válida\nOk.\n"
            "## Recorrido hasta acá\nLa deportista mejoró su tiempo.\n"
            "## Hacia dónde va\nReforzar técnica.\n"
        )
        report = g.scrub_with_report(text_with_progresion)
        assert not any(v.startswith("veto_n1_") for v in report.violations)

    # -------------------------------------------------------------------------
    # Escenarios Task #20 — separan claramente "set lanzado" vs
    # "historial de temporada".
    # -------------------------------------------------------------------------

    def test_set_size_1_but_season_has_history_no_veto(self):
        """Set=[V4] pero atleta ya tiene V1..V3 → NO debe vetar 'mejoró'.

        Task #20: el guardrail no mira el tamaño del set lanzado, sino el
        historial real de la temporada. Lanzar un análisis aislado de V4
        para un atleta con historial NO es un escenario N=1.
        """
        g = Guardrails(
            use_case="race_analyst_v2",
            is_first_in_season=False,
        )
        text = (
            "## Qué pasó en esta válida\nOk.\n"
            "## Recorrido hasta acá\nLa deportista mejoró su gestión "
            "del oxígeno respecto a las válidas previas.\n"
            "## Hacia dónde va\nReforzar técnica de descenso.\n"
        )
        report = g.scrub_with_report(text)
        assert not any(v.startswith("veto_n1_") for v in report.violations), (
            "Falso positivo: 'mejoró' fue vetado pese a haber historial "
            "de temporada (is_first_in_season=False)."
        )

    def test_genuinely_first_validates_veto(self):
        """Atleta con realmente 1 válida en toda la temporada → veto activo."""
        g = Guardrails(
            use_case="race_analyst_v2",
            is_first_in_season=True,
        )
        text = (
            "## Qué pasó en esta válida\nOk.\n"
            "## Recorrido hasta acá\nLa deportista mejoró su tiempo "
            "respecto al año pasado.\n"
            "## Hacia dónde va\nReforzar técnica.\n"
        )
        report = g.scrub_with_report(text)
        assert report.rejected is True
        assert any(v.startswith("veto_n1_") for v in report.violations), (
            "El veto debe activarse cuando is_first_in_season=True."
        )

    def test_recorrido_starts_with_literal_phrase_ca6(self):
        """CA-6: sección Recorrido debe arrancar con la frase literal."""
        import re

        m = re.search(
            r"##\s+Recorrido\s+hasta\s+ac[áa]\s*\n+(.+?)(?=\n##|\Z)",
            N1_SUFFIX_OK,
            re.DOTALL | re.IGNORECASE,
        )
        assert m is not None
        body = m.group(1).strip()
        assert body.startswith(
            "Con una sola válida disputada aún no es posible establecer "
            "una tendencia de progresión."
        )

    def test_word_boundaries_prevent_false_positives(self):
        # "mejor" NO debe matchear "mejoró"
        text = "Es la mejor forma de practicar."
        assert check_v2_veto_n1(text) == []


# -----------------------------------------------------------------------------
# Task #24 (QA) — extensión: kwarg ``athlete_age`` + check ``age_mismatch``.
#
# Pendiente en Task #23 (fastapi-architect). Tests xfail para que cuando la
# implementación llegue, pasen automáticamente sin tocar el archivo.
# Defensa: el prompt v2 puede inducir al LLM a inventar la edad si no se le
# guía bien. El kwarg permite que el guardrail post-gen rechace cualquier
# afirmación numérica de edad inconsistente con la edad real cargada del
# state.
# -----------------------------------------------------------------------------


class TestAgeMismatchKwarg:
    """Verifica que el kwarg ``athlete_age`` rechaza outputs que mienten
    sobre la edad del menor — defensa contra alucinaciones del LLM.

    El kwarg está implementado en :class:`Guardrails` (use_case=race_analyst_v2).
    """

    def test_guardrails_rejects_when_output_lies_about_age(self):
        g = Guardrails(use_case="race_analyst_v2", athlete_age=14)
        bad = (
            "## Qué pasó en esta válida\n"
            "La deportista tiene 12 años y rodó con su grupo.\n\n"
            "## Recorrido hasta acá\nOk.\n\n"
            "## Hacia dónde va\nOk.\n"
        )
        report = g.scrub_with_report(bad)
        assert report.rejected is True
        assert any(
            v.startswith("age_mismatch") for v in report.violations
        ), f"violations={report.violations!r}"

    def test_guardrails_passes_when_output_matches_real_age(self):
        g = Guardrails(use_case="race_analyst_v2", athlete_age=14)
        good = (
            "## Qué pasó en esta válida\n"
            "La deportista tiene 14 años y compitió en la categoría juvenil.\n\n"
            "## Recorrido hasta acá\nOk.\n\n"
            "## Hacia dónde va\nOk.\n"
        )
        report = g.scrub_with_report(good)
        assert not any(
            v.startswith("age_mismatch") for v in report.violations
        )
