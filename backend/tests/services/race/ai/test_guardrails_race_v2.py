"""Tests v2 — guardrails del RaceAnalyst v2 contra la API real.

Este archivo nació como un boceto previo a la implementación (xfail con una
API supuesta). Se reescribió sobre lo que ``app.services.ai.guardrails``
implementa de verdad; lo que ya estaba cubierto en otro archivo se eliminó
de aquí:

- Nombre real prohibido → reemplazo por "la deportista" y lista vacía sin
  reglas: ``test_race_ai_privacy_invariants.py::TestGuardrailForbiddenNamesUnit``.
- Veto N=1: ``test_guardrails_race_v2_n1.py``.

Lo que queda aquí no tenía cobertura en ningún otro archivo:

1. ``forbidden_name_*`` respeta límites de palabra (``Isabel`` ≠ ``Isabella``).
2. ``no_pseudonym_what_happened``: el patrón ``Atleta-XXX-NNN`` se reemplaza
   por "la deportista". La regla aplica a TODO el texto, no solo a la
   sección "Qué pasó" (más estricta que el spec §4, que solo lo exige ahí).
3. Veto duro (spec §7, lista literal cerrada de 5 frases):
   ``check_v2_veto_duro`` y la violación ``veto_duro_*`` del reporte. El
   rechazo/reintento lo aplica ``RaceAnalystAgent`` — ver
   ``test_analyst_agent_v2.py``; ``Guardrails.rejected`` NO se activa con
   una sola frase vetada (solo suma a ``MAX_VIOLATIONS_BEFORE_REJECT``).

4. Límite de palabras por sección (spec: 120 + 10 % de tolerancia):
   ``check_v2_section_word_limits`` y la violación ``word_limit_*`` del
   reporte. Los borradores xfail originales asumían un cuarto bloque de 200
   palabras ("Resumen de temporada") que el guardrail v2 no define: solo
   limita las tres secciones de la válida.

Todos los nombres son ficticios (Ley 1581).
"""

from __future__ import annotations

import pytest

from app.services.ai.guardrails import (
    Guardrails,
    check_v2_section_word_limits,
    check_v2_veto_duro,
)


def _build_v2_text(
    *,
    section_1: str = "Frenada estable y buena lectura de las curvas.",
    section_2: str = "Recorrido sólido con tiempos parejos.",
    section_3: str = "Próximo foco en cadencia consistente.",
) -> str:
    return (
        f"## Qué pasó en esta válida\n{section_1}\n\n"
        f"## Recorrido hasta acá\n{section_2}\n\n"
        f"## Hacia dónde va\n{section_3}\n"
    )


def _v2(forbidden_names: list[str] | None = None) -> Guardrails:
    return Guardrails(use_case="race_analyst_v2", forbidden_names=forbidden_names or [])


# ---------------------------------------------------------------------------
# 1. forbidden_name_*: límite de palabra
# ---------------------------------------------------------------------------


def test_forbidden_name_does_not_match_inside_a_longer_word():
    """``Isabella`` no es ``Isabel``: el match es ``\\b...\\b``, no substring."""
    report = _v2(["Isabel"]).scrub_with_report(
        _build_v2_text(section_1="La ruta pasó por la vereda Isabella.")
    )
    assert "Isabella" in report.text
    assert not any(v.startswith("forbidden_name_") for v in report.violations)


def test_forbidden_name_whole_word_is_scrubbed_next_to_punctuation():
    """El nombre pegado a puntuación sí es palabra completa y se reemplaza."""
    report = _v2(["Isabel"]).scrub_with_report(
        _build_v2_text(section_3="Buen trabajo, Isabel.")
    )
    assert "Isabel" not in report.text
    assert "la deportista" in report.text
    assert report.violations.count("forbidden_name_Isabel") == 1


# ---------------------------------------------------------------------------
# 2. no_pseudonym_what_happened
# ---------------------------------------------------------------------------


def test_pseudonym_in_what_happened_is_replaced():
    report = _v2().scrub_with_report(
        _build_v2_text(section_1="Atleta-ABC-042 mostró control en la frenada.")
    )
    assert "Atleta-ABC-042" not in report.text
    assert "la deportista mostró control" in report.text
    assert report.violations == ("no_pseudonym_what_happened",)
    # Una sola violación no rechaza: el texto se entrega saneado.
    assert report.rejected is False


def test_pseudonym_rule_is_not_scoped_to_the_first_section():
    """La regla corre sobre todo el texto: un pseudónimo en "Hacia dónde va"
    también se reemplaza (comportamiento actual, más estricto que el spec)."""
    report = _v2().scrub_with_report(
        _build_v2_text(section_3="Rotación con Atleta-XYZ-099 en peraltes.")
    )
    assert "Atleta-XYZ-099" not in report.text
    assert "no_pseudonym_what_happened" in report.violations


def test_pseudonym_rule_is_inactive_outside_race_analyst_v2():
    report = Guardrails().scrub_with_report("Atleta-ABC-042 mostró control.")
    assert "no_pseudonym_what_happened" not in report.violations


# ---------------------------------------------------------------------------
# 3. Veto duro (spec §7)
# ---------------------------------------------------------------------------


_VETO_CASES = [
    ("debe ganar", "debe_ganar"),
    ("tiene que llegar al podio", "tiene_que_llegar_al_podio"),
    ("necesita más horas", "necesita_mas_horas"),
    ("más intensidad", "mas_intensidad"),
    ("trabajo de potencia para superar a", "trabajo_de_potencia_para_superar_a"),
]


@pytest.mark.parametrize(("phrase", "rule"), _VETO_CASES)
def test_each_veto_phrase_is_detected(phrase: str, rule: str):
    text = _build_v2_text(section_3=f"Recomendamos que {phrase} en la próxima válida.")
    assert check_v2_veto_duro(text) == [rule]
    report = _v2().scrub_with_report(text)
    assert f"veto_duro_{rule}" in report.violations


@pytest.mark.parametrize(
    "variant",
    ["DEBE GANAR", "necesita mas horas", "mas  intensidad", "Necesita\nmás horas"],
)
def test_veto_phrase_survives_case_accent_and_whitespace_variants(variant: str):
    """El LLM no evade el veto con mayúsculas, sin tilde o saltos de línea."""
    assert check_v2_veto_duro(f"La deportista {variant} la próxima vez.")


def test_clean_text_has_no_veto():
    text = _build_v2_text()
    assert check_v2_veto_duro(text) == []
    report = _v2().scrub_with_report(text)
    assert not any(v.startswith("veto_duro_") for v in report.violations)
    assert report.rejected is False


def test_veto_phrase_embedded_in_longer_word_is_not_detected():
    """``\\b`` evita falsos positivos: "debe ganarse" no es "debe ganar"."""
    assert check_v2_veto_duro("La confianza se debe ganarse con práctica.") == []


# ---------------------------------------------------------------------------
# 4. Límite de palabras por sección
# ---------------------------------------------------------------------------


def _words(n: int) -> str:
    return " ".join(["palabra"] * n)


def test_section_at_the_tolerance_ceiling_passes():
    """120 + 10 % = 132 palabras siguen siendo válidas."""
    text = _build_v2_text(section_1=_words(132))
    assert check_v2_section_word_limits(text) == []
    report = _v2().scrub_with_report(text)
    assert not any(v.startswith("word_limit_") for v in report.violations)


def test_section_over_the_tolerance_ceiling_is_flagged_by_name():
    text = _build_v2_text(section_1=_words(133))
    # La clave devuelta es la variante sin acentos (el guardrail normaliza el título).
    assert check_v2_section_word_limits(text) == ["que paso en esta valida"]
    report = _v2().scrub_with_report(text)
    assert any(v.startswith("word_limit_") for v in report.violations)


def test_only_the_offending_section_is_flagged():
    text = _build_v2_text(section_2=_words(140))
    assert check_v2_section_word_limits(text) == ["recorrido hasta aca"]


def test_unknown_sections_have_no_word_limit():
    """Un encabezado que no es de la válida v2 no se limita (no hay tope inventado)."""
    text = _build_v2_text() + f"\n## Resumen de temporada\n{_words(300)}\n"
    assert check_v2_section_word_limits(text) == []
