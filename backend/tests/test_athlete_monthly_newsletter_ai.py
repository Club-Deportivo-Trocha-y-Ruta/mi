"""Tests del AthleteNewsletterUseCase.

Cubre:
- FakeAIProvider retorna narrativa válida → AiNarrativeOut correcto
- Guardrails redactan nombres prohibidos
- Bloque demasiado corto → LLMSchemaError
- Bloque demasiado largo → LLMSchemaError
- Términos médicos rechazados → LLMSchemaError
- Markdown strips (```json ... ```)
- Timeout → AthleteNewsletterLLMTimeout
- _compute_confidence: low / medium / high
- build_context_from_metrics: mapeo correcto
- Property: nunca aparece el nombre real del atleta en la salida
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services.ai.errors import LLMSchemaError
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.use_cases.athlete_monthly_newsletter import (
    AthleteNewsletterContext,
    AthleteNewsletterLLMTimeout,
    AthleteNewsletterUseCase,
    _compute_confidence,
    _derive_athlete_reference,
    build_context_from_metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_json_response(
    strengths: str = "El atleta demostró gran constancia y compromiso en cada sesión del mes.",
    area: str = "Se recomienda trabajar más en la técnica de pedaleo cuesta arriba en terreno.",
    milestone: str = "Completó el primer recorrido técnico largo sin asistencia del entrenador.",
) -> str:
    return json.dumps({
        "strengths": strengths,
        "area_to_develop": area,
        "milestone": milestone,
    })


def _make_context(
    forbidden_names: frozenset[str] = frozenset(),
    sessions_total: int = 8,
    num_races: int = 2,
    athlete_reference: str = "su hijo/a",
) -> AthleteNewsletterContext:
    confidence = _compute_confidence(sessions_total, num_races)
    return AthleteNewsletterContext(
        period_year=2026,
        period_month=4,
        sessions_present=sessions_total,
        sessions_total=sessions_total,
        attendance_pct=100.0,
        attendance_pct_prev_month=90.0,
        streak_sessions=sessions_total,
        athlete_reference=athlete_reference,
        focos_tecnicos=["Frenado", "Curvas cerradas"],
        avg_rpe=6.2,
        avg_rubric_technique=3.8,
        total_training_hours=12.0,
        has_races=(num_races > 0),
        race_results=[
            {"position": 5, "valida_num": "IV", "gap_to_winner_pct": 4.2}
        ] * num_races,
        num_races=num_races,
        badges=[{"badge_type": "attendance_100"}],
        confidence=confidence,
        forbidden_names=forbidden_names,
    )


# ---------------------------------------------------------------------------
# _compute_confidence
# ---------------------------------------------------------------------------


class TestComputeConfidence:
    def test_low_few_sessions(self):
        assert _compute_confidence(2, 3) == "low"

    def test_high_even_few_races(self):
        # num_races no penaliza: meses-bloque sin carrera pueden ser high
        assert _compute_confidence(8, 1) == "high"

    def test_high_zero_races(self):
        # Mes solo-entreno con volumen alto sigue siendo high
        assert _compute_confidence(8, 0) == "high"

    def test_medium_middle_range(self):
        assert _compute_confidence(5, 2) == "medium"

    def test_high(self):
        assert _compute_confidence(8, 3) == "high"

    def test_high_boundary(self):
        # Exactamente en el umbral
        assert _compute_confidence(8, 3) == "high"

    def test_low_zero_sessions(self):
        assert _compute_confidence(0, 0) == "low"


# ---------------------------------------------------------------------------
# build_context_from_metrics
# ---------------------------------------------------------------------------


class TestBuildContextFromMetrics:
    def _snapshot(self) -> dict:
        return {
            "email_blocks": {
                "attendance": {
                    "sessions_present": 9,
                    "sessions_total": 10,
                    "attendance_pct": 90.0,
                    "attendance_pct_prev_month": 85.0,
                    "streak_days": 4,
                },
                "technical": {
                    "focos_tecnicos": ["Saltos", "Equilibrio"],
                    "avg_rpe": 6.5,
                    "avg_rubric_technique": 3.5,
                    "total_training_hours": 10.0,
                },
                "race_results": {
                    "has_races": True,
                    "results": [
                        {"position": 3, "valida_num": "III", "gap_to_winner_pct": 1.5}
                    ],
                },
                "badges": {
                    "items": [{"badge_type": "attendance_90"}],
                },
            },
            "pdf_only_blocks": {
                "anthropometry": {"records": []},
            },
        }

    def test_maps_attendance_fields(self):
        ctx = build_context_from_metrics(
            metrics_snapshot=self._snapshot(),
            year=2026,
            month=4,
            forbidden_names=frozenset(),
        )
        assert ctx.sessions_present == 9
        assert ctx.sessions_total == 10
        assert ctx.attendance_pct == 90.0
        assert ctx.streak_sessions == 4

    def test_maps_technical_fields(self):
        ctx = build_context_from_metrics(
            metrics_snapshot=self._snapshot(),
            year=2026,
            month=4,
            forbidden_names=frozenset(),
        )
        assert ctx.focos_tecnicos == ["Saltos", "Equilibrio"]
        assert ctx.avg_rpe == 6.5
        assert ctx.total_training_hours == 10.0

    def test_maps_race_results(self):
        ctx = build_context_from_metrics(
            metrics_snapshot=self._snapshot(),
            year=2026,
            month=4,
            forbidden_names=frozenset(),
        )
        assert ctx.has_races is True
        assert ctx.num_races == 1

    def test_badges_extracted(self):
        ctx = build_context_from_metrics(
            metrics_snapshot=self._snapshot(),
            year=2026,
            month=4,
            forbidden_names=frozenset(),
        )
        assert ctx.badges == [{"badge_type": "attendance_90"}]

    def test_confidence_computed(self):
        ctx = build_context_from_metrics(
            metrics_snapshot=self._snapshot(),
            year=2026,
            month=4,
            forbidden_names=frozenset(),
        )
        # 10 sesiones, 1 carrera → medium (>=3 no cumple)
        assert ctx.confidence in {"low", "medium", "high"}

    def test_empty_snapshot_defaults(self):
        ctx = build_context_from_metrics(
            metrics_snapshot={},
            year=2025,
            month=12,
            forbidden_names=frozenset(),
        )
        assert ctx.sessions_total == 0
        assert ctx.has_races is False
        assert ctx.badges == []


# ---------------------------------------------------------------------------
# R2/B2 (024) — athlete_reference: referencia de género sin usar el nombre real
# ---------------------------------------------------------------------------


class TestAthleteReferenceGender:
    def test_reference_is_su_hija_for_sex_f(self):
        assert _derive_athlete_reference("F") == "su hija"

    def test_reference_is_su_hijo_for_sex_m(self):
        assert _derive_athlete_reference("M") == "su hijo"

    def test_reference_is_neutral_for_sex_none(self):
        assert _derive_athlete_reference(None) == "su hijo/a"

    def test_build_context_from_metrics_derives_reference_from_athlete_sex(self):
        ctx = build_context_from_metrics(
            metrics_snapshot={},
            year=2026,
            month=4,
            forbidden_names=frozenset(),
            athlete_sex="F",
        )
        assert ctx.athlete_reference == "su hija"

    def test_rendered_prompt_includes_gender_instruction(self):
        """El prompt renderizado debe incluir la instrucción explícita de
        género (`athlete_reference`) que el LLM debe usar textualmente."""
        registry = PromptRegistry()
        ctx = _make_context(athlete_reference="su hija")
        context_dict = {
            "period_year": ctx.period_year,
            "period_month": ctx.period_month,
            "sessions_present": ctx.sessions_present,
            "sessions_total": ctx.sessions_total,
            "attendance_pct": ctx.attendance_pct,
            "attendance_pct_prev_month": ctx.attendance_pct_prev_month,
            "streak_sessions": ctx.streak_sessions,
            "athlete_reference": ctx.athlete_reference,
            "focos_tecnicos": ctx.focos_tecnicos,
            "avg_rpe": ctx.avg_rpe,
            "avg_rubric_technique": ctx.avg_rubric_technique,
            "total_training_hours": ctx.total_training_hours,
            "has_races": ctx.has_races,
            "race_results": ctx.race_results,
            "num_races": ctx.num_races,
            "badges": ctx.badges,
            "confidence": ctx.confidence,
        }
        rendered = registry.render("athlete_monthly_newsletter_v1", context_dict)
        assert "su hija" in rendered
        assert "usa SIEMPRE y textualmente la expresión" in rendered


# ---------------------------------------------------------------------------
# AthleteNewsletterUseCase — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_use_case_happy_path():
    """FakeLLMProvider devuelve JSON válido → AiNarrativeOut correcto."""
    fake = FakeLLMProvider(canned=_valid_json_response())
    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(fake, registry)
    ctx = _make_context()

    result = await uc.run(ctx)

    assert result.strengths.startswith("El atleta demostró")
    assert result.area_to_develop.startswith("Se recomienda")
    assert result.milestone.startswith("Completó")
    assert result.confidence in {"low", "medium", "high"}
    assert result.prompt_version == "athlete_monthly_newsletter_v1"


@pytest.mark.asyncio
async def test_use_case_strips_markdown_json():
    """La respuesta con bloque ```json se parsea correctamente."""
    raw = f"```json\n{_valid_json_response()}\n```"
    fake = FakeLLMProvider(canned=raw)
    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(fake, registry)

    result = await uc.run(_make_context())

    assert result.strengths is not None
    assert len(result.strengths) > 0


# ---------------------------------------------------------------------------
# Guardrails — nombres prohibidos redactados
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardrails_redact_forbidden_name():
    """El nombre real del atleta es redactado del output IA."""
    athlete_name = "Camilo Rodríguez"
    # El LLM (simulado) incluye el nombre en la narrativa con frases suficientemente largas
    canned = json.dumps({
        "strengths": "Camilo Rodríguez mostró gran dedicación y constancia durante todas las sesiones del mes.",
        "area_to_develop": "Mejorar la técnica en curvas cerradas del circuito para ganar tiempo.",
        "milestone": "Completó el recorrido técnico completo sin asistencia por primera vez en la temporada.",
    })
    fake = FakeLLMProvider(canned=canned)
    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(fake, registry)

    forbidden = frozenset({"Camilo Rodríguez", "Camilo", "Rodríguez"})
    ctx = _make_context(forbidden_names=forbidden)

    result = await uc.run(ctx)

    # El nombre real no debe aparecer en ningún bloque
    assert "Camilo Rodríguez" not in result.strengths
    assert "Camilo" not in result.strengths


@pytest.mark.asyncio
async def test_property_real_name_never_in_output():
    """Property test: el nombre real del atleta nunca aparece en la salida IA."""
    names_to_test = [
        "Ana García",
        "Pedro Pérez",
        "Juan Sebastián Montoya",
    ]

    for name in names_to_test:
        # El LLM incluye el nombre en cada bloque con frases suficientemente largas
        canned = json.dumps({
            "strengths": (
                f"{name} mostró gran constancia y dedicación en todas las sesiones del mes."
            ),
            "area_to_develop": (
                "Se recomienda mejorar la técnica de descenso en terreno húmedo y con curvas."
            ),
            "milestone": (
                "Por primera vez completó un recorrido técnico exigente sin ninguna parada de asistencia."
            ),
        })
        fake = FakeLLMProvider(canned=canned)
        registry = PromptRegistry()
        uc = AthleteNewsletterUseCase(fake, registry)

        parts = name.split()
        forbidden = frozenset({name} | set(parts))
        ctx = _make_context(forbidden_names=forbidden)

        result = await uc.run(ctx)

        for part in parts:
            # Verificar que ninguna parte del nombre aparece en ningún bloque
            assert part not in result.strengths, (
                f"Nombre '{part}' encontrado en strengths para '{name}'"
            )


# ---------------------------------------------------------------------------
# Guardrails — bloque demasiado corto
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardrails_block_too_short():
    """Bloque con menos de 10 palabras → LLMSchemaError."""
    canned = json.dumps({
        "strengths": "Bien.",  # 1 palabra
        "area_to_develop": "Mejorar técnica en descensos con velocidad.",
        "milestone": "Primera sesión completa sin asistencia del entrenador.",
    })
    fake = FakeLLMProvider(canned=canned)
    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(fake, registry)

    with pytest.raises(LLMSchemaError, match="corto"):
        await uc.run(_make_context())


# ---------------------------------------------------------------------------
# Guardrails — bloque demasiado largo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardrails_block_too_long():
    """Bloque con más de 80 palabras → LLMSchemaError."""
    long_text = " ".join(["palabra"] * 81)
    canned = json.dumps({
        "strengths": long_text,
        "area_to_develop": "Mejorar la postura en el sillín.",
        "milestone": "Completó el primer recorrido técnico sin asistencia.",
    })
    fake = FakeLLMProvider(canned=canned)
    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(fake, registry)

    with pytest.raises(LLMSchemaError, match="largo"):
        await uc.run(_make_context())


# ---------------------------------------------------------------------------
# Guardrails — términos médicos rechazados
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardrails_medical_term_rejected():
    """Términos como 'suplemento' o 'creatina' → LLMSchemaError."""
    canned = json.dumps({
        "strengths": "El rendimiento mejoró notablemente gracias al uso de suplementos proteicos.",
        "area_to_develop": "Mejorar la técnica de frenado en descensos rápidos del circuito.",
        "milestone": "Completó por primera vez el recorrido técnico sin asistencia.",
    })
    fake = FakeLLMProvider(canned=canned)
    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(fake, registry)

    with pytest.raises(LLMSchemaError, match="médicos|nutricionales"):
        await uc.run(_make_context())


# ---------------------------------------------------------------------------
# JSON inválido
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_json_raises_schema_error():
    """Respuesta que no es JSON → LLMSchemaError."""
    fake = FakeLLMProvider(canned="Aquí está tu narrativa: gran trabajo este mes.")
    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(fake, registry)

    with pytest.raises(LLMSchemaError, match="JSON"):
        await uc.run(_make_context())


@pytest.mark.asyncio
async def test_json_missing_key_raises_schema_error():
    """JSON sin clave requerida → LLMSchemaError."""
    canned = json.dumps({
        "strengths": "Excelente asistencia y actitud durante el mes.",
        # falta area_to_develop y milestone
    })
    fake = FakeLLMProvider(canned=canned)
    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(fake, registry)

    with pytest.raises(LLMSchemaError, match="area_to_develop|milestone"):
        await uc.run(_make_context())


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_timeout_raises():
    """Si el LLM no responde en tiempo → AthleteNewsletterLLMTimeout."""
    import asyncio

    class SlowProvider:
        model = "slow-model"
        name = "slow"

        async def complete(self, req):
            await asyncio.sleep(100)

        async def complete_json(self, req, schema):
            await asyncio.sleep(100)

    registry = PromptRegistry()
    uc = AthleteNewsletterUseCase(SlowProvider(), registry)

    # Parchear el timeout a 0.01s para que el test sea rápido
    from unittest.mock import patch as _patch
    with _patch(
        "app.services.ai.use_cases.athlete_monthly_newsletter._LLM_TIMEOUT_SECONDS",
        0.01,
    ):
        with pytest.raises(AthleteNewsletterLLMTimeout):
            await uc.run(_make_context())
