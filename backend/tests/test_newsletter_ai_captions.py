"""Property tests US3 (T025): subtítulos por bloque + resumen del mes IA.

Verifica que `block_captions` y `month_highlights`:
  - NUNCA contienen el nombre real del atleta/compañeros (redacción guardrail).
  - Respetan el límite de palabras (campo descartado si excede, sin romper).
  - Bloquean términos médicos/diagnósticos (campo descartado).
  - El campo de antropometría es pedagógico y solo viaja en block_captions
    (su exclusión del email se verifica en el dispatcher/templates).
"""

from __future__ import annotations

import json

import pytest

from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.use_cases.athlete_monthly_newsletter import (
    _ALLOWED_CAPTION_KEYS,
    AthleteNewsletterContext,
    AthleteNewsletterUseCase,
    _compute_confidence,
)

# Frases base válidas (>=10 palabras, sin términos médicos ni nombres).
_VALID_STRENGTHS = "El atleta demostró gran constancia y compromiso en cada una de las sesiones del mes."
_VALID_AREA = "Se recomienda seguir trabajando la técnica de pedaleo cuesta arriba en terreno irregular."
_VALID_MILESTONE = "Completó por primera vez el recorrido técnico largo sin asistencia del entrenador del club."

_VALID_CAPTIONS = {
    "attendance": "La asistencia constante ayuda a consolidar el aprendizaje y a construir hábitos sólidos de entrenamiento.",
    "technical": "El trabajo técnico del mes se enfocó en habilidades concretas que se construyen con paciencia.",
    "race_results": "Participar en competencia es una experiencia de aprendizaje valiosa para crecer sobre la bici cada mes.",
    "anthropometry": "Este seguimiento acompaña el crecimiento y la maduración de manera pedagógica para planificar el entrenamiento.",
}
_VALID_HIGHLIGHTS = "Un mes con buena constancia y progreso técnico, base sólida para seguir disfrutando del proceso sobre la bici."


def _make_context(
    forbidden_names: frozenset[str] = frozenset(),
    sessions_total: int = 8,
    num_races: int = 2,
) -> AthleteNewsletterContext:
    return AthleteNewsletterContext(
        period_year=2026,
        period_month=4,
        sessions_present=sessions_total,
        sessions_total=sessions_total,
        attendance_pct=100.0,
        attendance_pct_prev_month=90.0,
        streak_days=sessions_total,
        focos_tecnicos=["Frenado", "Curvas cerradas"],
        avg_rpe=6.2,
        avg_rubric_technique=3.8,
        total_training_hours=12.0,
        has_races=(num_races > 0),
        race_results=[{"position": 5, "valida_num": "IV", "gap_to_winner_pct": 4.2}] * num_races,
        num_races=num_races,
        badges=[{"badge_type": "attendance_100"}],
        confidence=_compute_confidence(sessions_total, num_races),
        forbidden_names=forbidden_names,
    )


def _canned(
    *,
    captions: dict[str, str] | None = None,
    highlights: str | None = None,
    strengths: str = _VALID_STRENGTHS,
) -> str:
    payload: dict = {
        "strengths": strengths,
        "area_to_develop": _VALID_AREA,
        "milestone": _VALID_MILESTONE,
    }
    if captions is not None:
        payload["block_captions"] = captions
    if highlights is not None:
        payload["month_highlights"] = highlights
    return json.dumps(payload)


async def _run(canned: str, forbidden: frozenset[str] = frozenset()):
    uc = AthleteNewsletterUseCase(FakeLLMProvider(canned=canned), PromptRegistry())
    return await uc.run(_make_context(forbidden_names=forbidden))


# ---------------------------------------------------------------------------
# Happy path: captions/highlights válidos sobreviven el guardrail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_captions_and_highlights_survive():
    result = await _run(_canned(captions=dict(_VALID_CAPTIONS), highlights=_VALID_HIGHLIGHTS))
    assert result.block_captions is not None
    for key in _ALLOWED_CAPTION_KEYS:
        assert key in result.block_captions
    assert result.month_highlights == _VALID_HIGHLIGHTS


# ---------------------------------------------------------------------------
# Property: nunca aparece el nombre real en captions/highlights
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    ["Ana García", "Pedro Pérez", "Juan Sebastián Montoya", "Camilo Rodríguez", "María José"],
)
async def test_real_name_never_in_captions_or_highlights(name):
    parts = name.split()
    forbidden = frozenset({name, *parts})

    # Insertar el nombre en cada caption y en highlights, con frases largas.
    poisoned_captions = {
        "attendance": f"{name} mantuvo una asistencia constante durante todas las sesiones del mes en el club.",
        "technical": f"{name} mejoró su técnica de pedaleo cuesta arriba en cada entrenamiento del periodo.",
        "race_results": f"{name} participó en la válida con gran actitud y aprendió mucho de la experiencia.",
        "anthropometry": f"{name} continúa su proceso de crecimiento y maduración de forma saludable y progresiva.",
    }
    poisoned_highlights = f"{name} tuvo un mes destacado con buena constancia y progreso técnico sobre la bici."

    result = await _run(
        _canned(captions=poisoned_captions, highlights=poisoned_highlights),
        forbidden=forbidden,
    )

    haystack = [result.month_highlights or ""]
    haystack += list((result.block_captions or {}).values())
    blob = " ".join(haystack)
    assert name not in blob, f"Nombre completo filtrado: {name}"
    for part in parts:
        assert part not in blob, f"Componente de nombre filtrado: {part}"


# ---------------------------------------------------------------------------
# Word limit: caption demasiado larga se descarta (no rompe el boletín)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overlong_caption_dropped_not_fatal():
    too_long = " ".join(["palabra"] * 100)  # > 80 palabras
    captions = dict(_VALID_CAPTIONS)
    captions["attendance"] = too_long

    result = await _run(_canned(captions=captions, highlights=_VALID_HIGHLIGHTS))
    # El boletín se genera; la caption larga se descarta, las demás permanecen.
    caps = result.block_captions or {}
    assert "attendance" not in caps
    assert "technical" in caps


@pytest.mark.asyncio
async def test_overlong_highlights_dropped_not_fatal():
    too_long = " ".join(["palabra"] * 100)
    result = await _run(_canned(captions=dict(_VALID_CAPTIONS), highlights=too_long))
    assert result.month_highlights is None
    # El resto de la narrativa sigue presente.
    assert result.strengths.startswith("El atleta")


# ---------------------------------------------------------------------------
# Términos médicos: caption con término prohibido se descarta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "medical_phrase",
    [
        "Se observa sobrepeso en el atleta según las mediciones del mes registradas por el entrenador.",
        "El atleta presenta talla baja respecto a la referencia poblacional usada en el club deportivo.",
        "Se recomienda un suplemento proteico para apoyar la recuperación tras los entrenamientos del mes.",
    ],
)
async def test_medical_terms_blocked_in_captions(medical_phrase):
    captions = dict(_VALID_CAPTIONS)
    captions["anthropometry"] = medical_phrase
    result = await _run(_canned(captions=captions, highlights=_VALID_HIGHLIGHTS))
    caps = result.block_captions or {}
    assert "anthropometry" not in caps, "Caption con término médico no fue bloqueada"
    # Las demás captions limpias sobreviven.
    assert "attendance" in caps


@pytest.mark.asyncio
async def test_medical_term_blocked_in_highlights():
    bad = "Este mes el atleta mostró signos de desnutrición según las mediciones realizadas por el club."
    result = await _run(_canned(captions=dict(_VALID_CAPTIONS), highlights=bad))
    assert result.month_highlights is None


# ---------------------------------------------------------------------------
# Robustez: campos ausentes o mal formados → None, sin romper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_optional_fields_are_none():
    # JSON sin block_captions ni month_highlights (compatibilidad hacia atrás).
    result = await _run(_canned())
    assert result.block_captions is None
    assert result.month_highlights is None


@pytest.mark.asyncio
async def test_unknown_caption_keys_ignored():
    captions = dict(_VALID_CAPTIONS)
    captions["unexpected_key"] = "Una clave inesperada que el modelo nunca debería emitir en la práctica real."
    result = await _run(_canned(captions=captions, highlights=_VALID_HIGHLIGHTS))
    caps = result.block_captions or {}
    assert "unexpected_key" not in caps
    assert set(caps.keys()) <= set(_ALLOWED_CAPTION_KEYS)
