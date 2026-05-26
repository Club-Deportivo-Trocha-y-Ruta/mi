"""Tests v2 — invariantes de guardrails para el RaceAnalyst v2.

Contratos asumidos (Task #9). Se esperan nuevas reglas en
``app.services.ai.guardrails`` (o un módulo paralelo ``race_guardrails``):

- ``forbidden_real_names``: rechaza output si contiene cualquier nombre real
  cargado dinámicamente desde DB (``forbidden_names: list[str]`` inyectado
  por construcción). Match por palabra completa (``\\b...\\b``,
  case-insensitive).

- ``max_words_per_section``: enforce 120/120/120/200 palabras por sección
  (qué pasó / recorrido / hacia dónde va / resumen). Tolerancia +10%
  por sección.

- ``no_pseudonym_in_section_1``: en la sección 1 ("## Qué pasó") no debe
  aparecer el patrón pseudónimo ``Atleta-XXX-NNN`` — el coach espera
  redacción en lenguaje natural.

- Veto duro: 5 frases bloquean rejected=True:
    "debe ganar"
    "tiene que llegar al podio"
    "necesita más horas"
    "más intensidad"
    "trabajo de potencia para superar a"

Como las APIs concretas pueden variar (función, clase, kwarg names), los
tests se marcan xfail si la importación falla — esto los hace tolerantes a
implementaciones todavía en flux.
"""

from __future__ import annotations

import re

import pytest

# Esperamos un nuevo módulo o extensión. Probamos varios paths esperados.
_GUARDRAIL_API: object | None = None
_IMPORT_ERR: Exception | None = None
try:
    # Path esperado #1: nueva clase RaceAnalystGuardrails
    from app.services.ai.guardrails import Guardrails as _GuardrailsCls  # type: ignore

    _GUARDRAIL_API = _GuardrailsCls
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERR = exc


VETO_PHRASES = [
    "debe ganar",
    "tiene que llegar al podio",
    "necesita más horas",
    "más intensidad",
    "trabajo de potencia para superar a",
]


def _build_v2_text(
    *,
    section_1: str = "Progreso técnico en frenada y curvas.",
    section_2: str = "Recorrido sólido con mejoría sostenida.",
    section_3: str = "Próximo foco en cadencia consistente.",
    section_4: str = "Temporada de aprendizaje y disfrute.",
) -> str:
    return (
        f"## Qué pasó\n{section_1}\n\n"
        f"## Recorrido hasta aquí\n{section_2}\n\n"
        f"## Hacia dónde va\n{section_3}\n\n"
        f"## Resumen de temporada\n{section_4}\n"
    )


# ---------------------------------------------------------------------------
# Invariante 1: forbidden_real_names
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="v2: forbidden_real_names dinámico pendiente — espera kwarg en Guardrails",
    strict=False,
)
def test_forbidden_real_names_rejects_word_match():
    """Texto con \\bIsabel\\b cuando forbidden_names=['Isabel'] → rechazo."""
    # API tentativa — se ajustará cuando el implementador defina la firma.
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=["Isabel"])  # type: ignore[call-arg]
    text = _build_v2_text(section_1="Isabel mostró progreso en frenada.")
    report = g.scrub_with_report(text)
    assert report.rejected is True
    # El violation name debe identificar la regla.
    assert any("forbidden" in v.lower() or "name" in v.lower() for v in report.violations)


@pytest.mark.xfail(
    reason="v2: forbidden_real_names — match por palabra completa",
    strict=False,
)
def test_forbidden_real_names_word_boundary_not_substring():
    """``isabella`` NO debe matchear cuando forbidden=['Isabel'] (no es \\b)."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=["Isabel"])  # type: ignore[call-arg]
    text = _build_v2_text(section_1="La ciudad de Isabella es lejana.")
    report = g.scrub_with_report(text)
    # No es un nombre — substring match no debería activar la regla.
    # Si la implementación es ingenua (substring), este test detecta el bug.
    assert report.rejected is False or not any(
        "forbidden" in v.lower() for v in report.violations
    )


@pytest.mark.xfail(reason="v2 pending", strict=False)
def test_forbidden_real_names_empty_list_passes():
    """Sin lista de nombres prohibidos, no debería rechazar nada por esta regla."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=[])  # type: ignore[call-arg]
    text = _build_v2_text(section_1="Isabel y María avanzaron bien.")
    report = g.scrub_with_report(text)
    # Si forbidden_names está vacío, la regla NO activa.
    assert not any("forbidden_real_names" in v for v in report.violations)


# ---------------------------------------------------------------------------
# Invariante 2: max_words per sección
# ---------------------------------------------------------------------------


def _words(n: int) -> str:
    return " ".join(["palabra"] * n)


@pytest.mark.xfail(reason="v2: max_words per sección pendiente", strict=False)
def test_max_words_section_1_at_132_passes():
    """120 + 10% tolerancia = 132 palabras OK en sección 1."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=[])  # type: ignore[call-arg]
    text = _build_v2_text(section_1=_words(132))
    report = g.scrub_with_report(text)
    assert not any("max_words" in v for v in report.violations), (
        f"132 palabras (tolerancia) no debería disparar la regla. "
        f"Violations: {report.violations}"
    )


@pytest.mark.xfail(reason="v2: max_words per sección pendiente", strict=False)
def test_max_words_section_1_at_133_rejects():
    """133 palabras (>120+10%) en sección 1 → violación."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=[])  # type: ignore[call-arg]
    text = _build_v2_text(section_1=_words(133))
    report = g.scrub_with_report(text)
    assert any("max_words" in v for v in report.violations) or report.rejected


@pytest.mark.xfail(reason="v2: max_words per sección pendiente", strict=False)
def test_max_words_section_4_higher_cap_220():
    """Sección 4 (resumen) tiene cap 200 + 10% = 220 palabras."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=[])  # type: ignore[call-arg]
    # 220 palabras en sec 4: pasa.
    text = _build_v2_text(section_4=_words(220))
    report = g.scrub_with_report(text)
    assert not any("max_words" in v for v in report.violations)

    # 221 palabras: rechazo.
    text_over = _build_v2_text(section_4=_words(221))
    report_over = g.scrub_with_report(text_over)
    assert any("max_words" in v for v in report_over.violations) or report_over.rejected


# ---------------------------------------------------------------------------
# Invariante 3: no_pseudonym_in_section_1
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="v2: regla no_pseudonym_in_section_1 pendiente",
    strict=False,
)
def test_pseudonym_pattern_in_section_1_rejects():
    """``Atleta-XXX-NNN`` en sec 1 → violación."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=[])  # type: ignore[call-arg]
    text = _build_v2_text(
        section_1="Atleta-ABC-042 mostró progreso técnico en frenada."
    )
    report = g.scrub_with_report(text)
    assert any("pseudonym" in v.lower() or "section_1" in v.lower() for v in report.violations)


@pytest.mark.xfail(reason="v2 pending", strict=False)
def test_pseudonym_pattern_in_section_3_does_not_trigger_rule_1():
    """El mismo pseudónimo en sección 3 NO debe disparar la regla de sec 1."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=[])  # type: ignore[call-arg]
    text = _build_v2_text(
        section_3="Foco próximo: rotación con Atleta-XYZ-099 en peraltes."
    )
    report = g.scrub_with_report(text)
    # La regla específica de sec 1 NO debe activarse.
    assert not any(
        v == "no_pseudonym_in_section_1" for v in report.violations
    )


# ---------------------------------------------------------------------------
# Veto duro: 5 frases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", VETO_PHRASES)
@pytest.mark.xfail(
    reason="v2: veto_hard_phrases pendiente — frases bloquean rejected=True",
    strict=False,
)
def test_veto_hard_phrase_rejects(phrase: str):
    """Cada una de las 5 frases vetadas debe disparar rejected=True."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=[])  # type: ignore[call-arg]
    text = _build_v2_text(
        section_3=f"Recomendamos que {phrase} en la próxima válida."
    )
    report = g.scrub_with_report(text)
    assert report.rejected is True, (
        f"Frase vetada '{phrase}' no disparó rechazo. Violations: {report.violations}"
    )


@pytest.mark.xfail(reason="v2 pending", strict=False)
def test_no_veto_phrase_passes():
    """Texto sin frases vetadas no debe rechazarse por veto."""
    g = _GUARDRAIL_API(use_case="race_analyst_v2", forbidden_names=[])  # type: ignore[call-arg]
    text = _build_v2_text()
    report = g.scrub_with_report(text)
    # No debe contener violaciones de veto.
    assert not any("veto" in v.lower() for v in report.violations)


# ---------------------------------------------------------------------------
# Sanity check de imports
# ---------------------------------------------------------------------------


def test_guardrails_module_importable():
    """Sanity: el módulo guardrails sigue siendo importable (regresión v1)."""
    if _IMPORT_ERR is not None:
        pytest.fail(f"Guardrails import roto: {_IMPORT_ERR}")
    assert _GUARDRAIL_API is not None
