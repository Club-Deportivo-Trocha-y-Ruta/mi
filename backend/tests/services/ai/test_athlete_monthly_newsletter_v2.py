"""Tests de AthleteMonthlyNewsletterV2UseCase (feature 038, T201).

Cubre:
- FakeLLMProvider devuelve JSON completo válido -> StageNarrative correcto,
  sin violaciones.
- Violación de grounding (número no presente en el prompt) -> el bloque cae
  a ``None`` (fallback estático, ver stage_log_builder.py) y la violación
  queda registrada en ``grounding_violations``.
- Frase prohibida (ej. "podio", "percentil") -> bloque rechazado.
- ``regenerate_block``/``only_block`` -> retorna solo el valor de ese bloque.
- Extras: nombre real redactado, solapamiento con el mes anterior, "?"
  faltante en la pregunta de la brújula, timeout, y el fallback de
  parseo manual + reintento de reparación cuando el proveedor no soporta
  (o falla) structured output.

451 / 409 / convert son tests de router — ver
``tests/routers/test_athlete_monthly_newsletter_v2_router.py``.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services.ai.errors import LLMSchemaError
from app.services.ai.providers.fake import FakeLLMProvider
from app.services.ai.prompts.registry import PromptRegistry
from app.services.race.audience import FAMILY_EXCLUDED_METRIC_FIELDS
from app.services.ai.use_cases.athlete_monthly_newsletter_v2 import (
    AthleteMonthlyNewsletterV2UseCase,
    StageNarrativeLLMTimeout,
    build_context_from_metrics_v2,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _snapshot(**overrides) -> dict:
    base = {
        "email_blocks": {
            "period": {"year": 2026, "month": 6, "label": "Junio 2026"},
            "attendance": {
                "sessions_present": 9,
                "sessions_total": 10,
                "attendance_pct": 90.0,
                "attendance_pct_prev_month": 85.0,
                "streak_sessions": 6,
            },
            "technical": {
                "focos_tecnicos": ["Frenado", "Curvas cerradas"],
                "avg_rpe": 6.2,
                "avg_rubric_technique": 3.8,
            },
            "race_results": {
                "has_races": True,
                "results": [
                    {
                        "position": 4,
                        "label": "Válida III — Cali",
                        "gap_to_winner_pct": 3.2,
                        "gap_to_median_pct": 2.4,
                        "event_date": "2026-06-14",
                        "category_label": "Prejuvenil A",
                    }
                ],
            },
            "badges": {"items": [{"badge_type": "attendance_90"}]},
            "calendar": {
                "next_race_events": [
                    {"date": "2026-07-12", "valida": "IV", "location": "Ginebra", "priority": "A"}
                ]
            },
        },
        "pdf_only_blocks": {
            "weekly": [
                {"date": "2026-06-02", "attended": True, "rpe": 6, "rubric_avg": 3.5},
                {"date": "2026-06-09", "attended": True, "rpe": 7, "rubric_avg": 4.0},
            ],
            "next_focus_groups": [{"name": "Frenado"}, {"name": "Salto"}],
        },
    }
    base.update(overrides)
    return base


def _happy_canned_json() -> dict:
    return {
        "stage_title": "Una etapa de constancia: 9 de 10 sesiones y un P4 en la Válida III — Cali",
        "summit_caption": "El P4 en la Válida III — Cali confirma lo que se vio en cada entrenamiento del mes.",
        "observations": [
            {
                "claim": "La constancia fue la base de esta etapa.",
                "evidence": "9/10 sesiones asistidas.",
                "block_ref": "attendance",
            },
            {
                "claim": "El trabajo de frenado ya se nota en pista.",
                "evidence": "Foco técnico: frenado y curvas cerradas.",
                "block_ref": "technical",
            },
            {
                "claim": "La racha de entrenamiento se sostuvo todo el mes.",
                "evidence": "Racha actual de 6 sesiones.",
                "block_ref": "streak",
            },
        ],
        "next_segment_text": "El próximo tramo sigue afinando frenado y curvas cerradas, con la mira en la próxima carrera.",
        "family_compass": {
            "conversation_question": "¿Qué fue lo que más disfrutaste entrenar este mes?",
            "monthly_challenge": "Celebrar cada sesión completa, sin importar el resultado de la próxima carrera.",
            "what_to_watch": "Cómo se siente en las frenadas fuertes durante los próximos entrenamientos.",
        },
        "analyst_reading": {
            "headline_family": "El entrenador notó que el trabajo de frenado ya se refleja en carrera.",
            "action_family": "Seguir practicando frenado en curvas cerradas dos veces por semana.",
        },
    }


def _make_ctx(
    forbidden_names: frozenset[str] = frozenset(),
    analyst_reading_input: dict | None = None,
    previous_stage_title: str | None = None,
    previous_stage_text: str | None = None,
    snapshot: dict | None = None,
):
    return build_context_from_metrics_v2(
        snapshot or _snapshot(),
        2026,
        6,
        forbidden_names,
        athlete_sex="F",
        analyst_reading_input=analyst_reading_input,
        previous_stage_title=previous_stage_title,
        previous_stage_text=previous_stage_text,
    )


def _use_case(canned_json: dict) -> AthleteMonthlyNewsletterV2UseCase:
    fake = FakeLLMProvider(canned_json=canned_json)
    return AthleteMonthlyNewsletterV2UseCase(fake, PromptRegistry())


# ---------------------------------------------------------------------------
# build_context_from_metrics_v2
# ---------------------------------------------------------------------------


class TestBuildContextFromMetricsV2:
    def test_maps_attendance_and_streak(self):
        ctx = _make_ctx()
        assert ctx.sessions_present == 9
        assert ctx.sessions_total == 10
        assert ctx.streak_sessions == 6

    def test_maps_effort_weeks_from_weekly_block(self):
        ctx = _make_ctx()
        assert len(ctx.effort_weeks) >= 1
        assert ctx.effort_weeks[0]["sessions_attended"] >= 1

    def test_maps_planned_focus_groups_and_next_race(self):
        ctx = _make_ctx()
        assert ctx.planned_focus_groups == ["Frenado", "Salto"]
        assert ctx.next_race is not None
        assert ctx.next_race["venue"] == "Ginebra"

    def test_athlete_reference_from_sex(self):
        ctx = build_context_from_metrics_v2(
            _snapshot(), 2026, 6, frozenset(), athlete_sex="M"
        )
        assert ctx.athlete_reference == "su hijo"

    def test_confidence_computed_from_sessions_and_races(self):
        ctx = _make_ctx()
        assert ctx.confidence in {"low", "medium", "high"}

    def test_empty_snapshot_defaults(self):
        ctx = build_context_from_metrics_v2({}, 2026, 6, frozenset())
        assert ctx.sessions_total == 0
        assert ctx.planned_focus_groups == []
        assert ctx.next_race is None


# ---------------------------------------------------------------------------
# Brecha en el prompt (feature 045): «Brecha vs. mediana», nunca «al P1»
# ---------------------------------------------------------------------------

# Valor centinela: si aparece en el prompt renderizado, la brecha contra el
# ganador se filtró al LLM.
_WINNER_GAP_SENTINEL = 41.7


def _race_row(**overrides) -> dict:
    row = {
        "position": 4,
        "label": "Válida III — Cali",
        "gap_to_winner_pct": _WINNER_GAP_SENTINEL,
        "gap_to_median_pct": 2.4,
        "event_date": "2026-06-14",
        "category_label": "Prejuvenil A",
    }
    row.update(overrides)
    return row


def _snapshot_with_races(*rows: dict) -> dict:
    snapshot = _snapshot()
    snapshot["email_blocks"]["race_results"] = {"has_races": True, "results": list(rows)}
    return snapshot


def _render_prompt(snapshot: dict) -> str:
    ctx = _make_ctx(snapshot=snapshot)
    context_dict = AthleteMonthlyNewsletterV2UseCase._context_dict(
        ctx, only_block=None, instruction=None
    )
    return PromptRegistry().render("athlete_monthly_newsletter_v2", context_dict)


def _race_line(prompt: str) -> str:
    return next(line for line in prompt.splitlines() if line.startswith("- Válida III"))


class TestContextExcludesWinnerAndPodiumGaps:
    """Defensa en profundidad (FR-022): el contexto del prompt no lleva las
    claves de la brecha al ganador/podio, ni siquiera sin renderizarlas."""

    @staticmethod
    def _row_with_all_excluded_keys() -> dict:
        row = _race_row(gap_to_median_pct=2.4)
        row.update({key: 99 for key in FAMILY_EXCLUDED_METRIC_FIELDS})
        return row

    def test_context_race_results_lack_every_family_excluded_key(self):
        ctx = _make_ctx(snapshot=_snapshot_with_races(self._row_with_all_excluded_keys()))

        assert len(ctx.race_results) == 1
        assert FAMILY_EXCLUDED_METRIC_FIELDS.isdisjoint(ctx.race_results[0])
        # Explícito: winner, podio (P3) y los heredados de la 037.
        for key in (
            "gap_to_winner_pct", "gap_to_winner_ms", "gap_to_podium_pct",
            "gap_to_podium_ms", "gap_pct", "gap_to_p1_ms", "gap_to_p3_ms",
        ):
            assert key not in ctx.race_results[0]

    def test_context_keeps_median_gap_and_display_fields(self):
        ctx = _make_ctx(snapshot=_snapshot_with_races(self._row_with_all_excluded_keys()))

        row = ctx.race_results[0]
        assert row["gap_to_median_pct"] == 2.4
        assert row["position"] == 4
        assert row["label"] == "Válida III — Cali"
        assert row["event_date"] == "2026-06-14"

    def test_dict_handed_to_the_registry_lacks_excluded_keys(self):
        ctx = _make_ctx(snapshot=_snapshot_with_races(self._row_with_all_excluded_keys()))

        context_dict = AthleteMonthlyNewsletterV2UseCase._context_dict(
            ctx, only_block=None, instruction=None
        )

        assert FAMILY_EXCLUDED_METRIC_FIELDS.isdisjoint(context_dict["race_results"][0])

    def test_source_snapshot_is_not_mutated(self):
        """El snapshot persistido (que el coach/PDF sí pueden leer) conserva
        sus claves: solo la copia del contexto se redacta."""
        snapshot = _snapshot_with_races(self._row_with_all_excluded_keys())

        _make_ctx(snapshot=snapshot)

        stored = snapshot["email_blocks"]["race_results"]["results"][0]
        assert FAMILY_EXCLUDED_METRIC_FIELDS <= stored.keys()

    def test_races_count_still_drives_confidence(self):
        ctx = _make_ctx(snapshot=_snapshot_with_races(self._row_with_all_excluded_keys()))

        assert ctx.confidence in {"low", "medium", "high"}


class TestPromptRaceGap:
    def test_prompt_uses_median_gap_and_never_the_winner_gap(self):
        prompt = _render_prompt(_snapshot_with_races(_race_row()))
        line = _race_line(prompt)

        assert "Brecha vs. mediana: +2.4 % vs. la mediana de su categoría" in line
        assert "tiempo 2.4 % mayor" in line
        assert "al P1" not in prompt
        assert str(_WINNER_GAP_SENTINEL) not in prompt

    def test_negative_median_gap_renders_sign_and_magnitude(self):
        prompt = _render_prompt(
            _snapshot_with_races(_race_row(gap_to_median_pct=-1.3))
        )
        line = _race_line(prompt)

        assert "Brecha vs. mediana: -1.3 % vs. la mediana de su categoría" in line
        assert "tiempo 1.3 % menor" in line
        assert str(_WINNER_GAP_SENTINEL) not in prompt

    def test_zero_median_gap_has_no_direction_tail(self):
        line = _race_line(
            _render_prompt(_snapshot_with_races(_race_row(gap_to_median_pct=0.0)))
        )

        assert "Brecha vs. mediana: +0.0 %" in line
        assert "mayor" not in line and "menor" not in line

    def test_none_median_gap_omits_the_gap_line(self):
        prompt = _render_prompt(
            _snapshot_with_races(_race_row(gap_to_median_pct=None))
        )
        line = _race_line(prompt)

        assert "Brecha vs. mediana" not in line
        assert "al P1" not in prompt
        assert str(_WINNER_GAP_SENTINEL) not in prompt

    def test_legacy_snapshot_without_median_key_renders_without_gap(self):
        """Snapshots anteriores a la 045 no traen ``gap_to_median_pct``: con
        ``StrictUndefined`` el template no debe reventar ni caer al P1."""
        row = _race_row()
        del row["gap_to_median_pct"]

        prompt = _render_prompt(_snapshot_with_races(row))

        assert "Brecha vs. mediana" not in _race_line(prompt)
        assert str(_WINNER_GAP_SENTINEL) not in prompt

    def test_prompt_instructs_model_never_to_cite_winner_or_podium_gaps(self):
        prompt = _render_prompt(_snapshot_with_races(_race_row()))

        assert "Nunca menciones brechas, tiempos ni posiciones del ganador" in prompt
        assert "del líder o del podio" in prompt

    @pytest.mark.asyncio
    async def test_llm_request_carries_median_gap_not_winner_gap(self):
        fake = FakeLLMProvider(canned_json=_happy_canned_json())
        uc = AthleteMonthlyNewsletterV2UseCase(fake, PromptRegistry())
        ctx = _make_ctx(snapshot=_snapshot_with_races(_race_row(gap_to_median_pct=-1.3)))

        await uc.run(ctx)

        sent = fake.last_request.messages[-1].content
        assert "Brecha vs. mediana: -1.3 %" in sent
        assert "al P1" not in sent
        assert str(_WINNER_GAP_SENTINEL) not in sent

    @pytest.mark.asyncio
    @pytest.mark.parametrize("gap, cited", [(2.4, "2.4"), (-1.3, "1.3"), (-1.3, "-1.3")])
    async def test_median_gap_cited_by_model_is_grounded(self, gap, cited):
        """El modelo cita la cifra con o sin signo: ambas formas están en el
        prompt renderizado, así que el guardrail de grounding no descarta el
        bloque (una brecha negativa sin la magnitud caería a estático)."""
        canned = _happy_canned_json()
        canned["summit_caption"] = f"La brecha vs. la mediana fue de {cited} % en la Válida III."
        uc = _use_case(canned)
        ctx = _make_ctx(snapshot=_snapshot_with_races(_race_row(gap_to_median_pct=gap)))

        result = await uc.run(ctx)

        assert result.summit_caption is not None
        assert not any("ungrounded_number" in v for v in result.grounding_violations)

    @pytest.mark.asyncio
    async def test_winner_gap_cited_by_model_is_ungrounded(self):
        """Si el modelo inventara la brecha al P1 (que no está en el prompt),
        el grounding la rechaza: red de seguridad detrás de la instrucción."""
        canned = _happy_canned_json()
        canned["summit_caption"] = f"Terminó a {_WINNER_GAP_SENTINEL} % del primer lugar."
        uc = _use_case(canned)
        ctx = _make_ctx(snapshot=_snapshot_with_races(_race_row()))

        result = await uc.run(ctx)

        assert result.summit_caption is None
        assert any("ungrounded_number" in v for v in result.grounding_violations)


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_all_blocks_populated_no_violations():
    ctx = _make_ctx(analyst_reading_input={
        "headline": "Ganó posiciones en el tramo técnico.",
        "action_text": "Practicar frenado en curvas dos veces por semana.",
        "action_category": "tecnico",
        "valida_label": "Válida III — Cali",
    })
    uc = _use_case(_happy_canned_json())

    result = await uc.run(ctx)

    assert result.grounding_violations == []
    assert result.stage_title is not None and "9 de 10" in result.stage_title
    assert result.summit_caption is not None
    assert result.observations is not None and len(result.observations) == 3
    assert result.next_segment_text is not None
    assert result.family_compass is not None
    assert result.family_compass.conversation_question.endswith("?")
    assert result.analyst_reading is not None
    assert result.model == "fake-model"
    assert result.prompt_version == "athlete_monthly_newsletter_v2"
    assert result.confidence in {"low", "medium", "high"}


@pytest.mark.asyncio
async def test_analyst_reading_omitted_when_no_family_insight_input():
    """Sin FamilyInsightInput, analyst_reading nunca se acepta aunque el LLM
    lo devuelva — data-model.md §2: "only when FamilyInsightInput was given"."""
    ctx = _make_ctx(analyst_reading_input=None)
    uc = _use_case(_happy_canned_json())

    result = await uc.run(ctx)

    assert result.analyst_reading is None


# ---------------------------------------------------------------------------
# Grounding — número no presente en el prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ungrounded_number_falls_back_to_none_and_records_violation():
    canned = _happy_canned_json()
    canned["stage_title"] = "Una etapa con 999 sesiones asistidas este mes"
    uc = _use_case(canned)

    result = await uc.run(_make_ctx())

    assert result.stage_title is None
    assert any("ungrounded_number" in v for v in result.grounding_violations)
    # El resto de bloques, sin violación, se acepta con normalidad.
    assert result.observations is not None


@pytest.mark.asyncio
async def test_grounded_number_from_context_is_accepted():
    """Un número que sí está en el contexto (9/10, 6 de la racha) nunca
    dispara el guardrail de grounding."""
    uc = _use_case(_happy_canned_json())

    result = await uc.run(_make_ctx())

    assert not any("ungrounded_number" in v for v in result.grounding_violations)


# ---------------------------------------------------------------------------
# Frases prohibidas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase", ["podio", "percentil", "mejor que", "por debajo", "ranking", "ganar", "esperado"]
)
async def test_forbidden_phrase_rejects_block(phrase):
    canned = _happy_canned_json()
    canned["summit_caption"] = f"Este resultado fue {phrase} de lo previsto para el mes."
    uc = _use_case(canned)

    result = await uc.run(_make_ctx())

    assert result.summit_caption is None
    assert any("forbidden_phrase" in v for v in result.grounding_violations)


# ---------------------------------------------------------------------------
# only_block / regenerate_block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regenerate_block_returns_only_that_key():
    fake = FakeLLMProvider(
        canned_json={"stage_title": "Una etapa de constancia con 9 de 10 sesiones asistidas"}
    )
    uc = AthleteMonthlyNewsletterV2UseCase(fake, PromptRegistry())

    value = await uc.regenerate_block(_make_ctx(), "stage_title", instruction="más corto")

    assert value == "Una etapa de constancia con 9 de 10 sesiones asistidas"
    # El prompt renderizado debe incluir la instrucción del coach.
    assert "más corto" in fake.last_request.messages[-1].content
    assert '"stage_title"' in fake.last_request.messages[-1].content


@pytest.mark.asyncio
async def test_regenerate_block_unknown_block_raises_value_error():
    uc = _use_case(_happy_canned_json())
    with pytest.raises(ValueError):
        await uc.regenerate_block(_make_ctx(), "not_a_real_block")


@pytest.mark.asyncio
async def test_regenerate_block_observations_returns_list_of_three():
    fake = FakeLLMProvider(canned_json=_happy_canned_json())
    uc = AthleteMonthlyNewsletterV2UseCase(fake, PromptRegistry())

    value = await uc.regenerate_block(_make_ctx(), "observations")

    assert isinstance(value, list)
    assert len(value) == 3


# ---------------------------------------------------------------------------
# Nombres prohibidos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forbidden_name_is_redacted_from_block():
    """``scrub_block`` redacta el nombre en vez de rechazar el bloque cuando
    la redacción deja el texto limpio — el nombre real nunca sobrevive."""
    canned = _happy_canned_json()
    canned["next_segment_text"] = "Camilo Rodríguez seguirá afinando frenado el próximo mes."
    uc = _use_case(canned)

    ctx = _make_ctx(forbidden_names=frozenset({"Camilo Rodríguez", "Camilo", "Rodríguez"}))
    result = await uc.run(ctx)

    assert result.next_segment_text is not None
    assert "Camilo" not in result.next_segment_text
    assert "[REDACTADO]" in result.next_segment_text


@pytest.mark.asyncio
async def test_block_too_long_is_rejected():
    """Guardrail v1 heredado: > 80 palabras rechaza el bloque."""
    canned = _happy_canned_json()
    canned["next_segment_text"] = " ".join(["palabra"] * 81)
    uc = _use_case(canned)

    result = await uc.run(_make_ctx())

    assert result.next_segment_text is None
    assert any("too_long" in v for v in result.grounding_violations)


# ---------------------------------------------------------------------------
# Solapamiento con el mes anterior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overlap_with_previous_month_rejects_stage_title():
    previous_title = "Una etapa de constancia: 9 de 10 sesiones y un P4 en la Válida III — Cali"
    canned = _happy_canned_json()
    # Repite casi textual el título del mes anterior.
    canned["stage_title"] = previous_title
    uc = _use_case(canned)

    ctx = _make_ctx(previous_stage_title=previous_title, previous_stage_text=previous_title)
    result = await uc.run(ctx)

    assert result.stage_title is None
    assert any("overlap_previous_month" in v for v in result.grounding_violations)


# ---------------------------------------------------------------------------
# "?" faltante en la brújula de la familia
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_family_compass_without_question_mark_is_rejected():
    canned = _happy_canned_json()
    canned["family_compass"]["conversation_question"] = "Qué fue lo que más disfrutaste este mes"
    uc = _use_case(canned)

    result = await uc.run(_make_ctx())

    assert result.family_compass is None
    assert any("missing_question_mark" in v for v in result.grounding_violations)


# ---------------------------------------------------------------------------
# Conteo de observaciones inválido
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observations_wrong_count_falls_back_to_none():
    canned = _happy_canned_json()
    canned["observations"] = canned["observations"][:2]  # solo 2, no 3
    uc = _use_case(canned)

    result = await uc.run(_make_ctx())

    assert result.observations is None
    assert any("invalid_count" in v for v in result.grounding_violations)


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_timeout_raises():
    class SlowProvider:
        model = "slow-model"
        name = "slow"

        async def complete(self, req):
            await asyncio.sleep(100)

        async def complete_json(self, req, schema):
            await asyncio.sleep(100)

    uc = AthleteMonthlyNewsletterV2UseCase(SlowProvider(), PromptRegistry())

    from unittest.mock import patch as _patch

    with _patch(
        "app.services.ai.use_cases.athlete_monthly_newsletter_v2._LLM_TIMEOUT_SECONDS",
        0.01,
    ):
        with pytest.raises(StageNarrativeLLMTimeout):
            await uc.run(_make_ctx())


# ---------------------------------------------------------------------------
# Fallback manual (sin structured output) + reintento de reparación
# ---------------------------------------------------------------------------


class _ChatOnlyProvider:
    """Proveedor sin ``complete_json`` — fuerza el modo manual de parseo."""

    model = "chat-only-model"
    name = "chat-only"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def complete(self, req):
        from app.services.ai.models import LLMResponse, TokenUsage

        self.calls.append(req.messages[-1].content)
        text = self._responses.pop(0) if self._responses else "{}"
        return LLMResponse(
            text=text, usage=TokenUsage(), model=self.model, provider=self.name, latency_ms=0
        )


@pytest.mark.asyncio
async def test_manual_parse_used_when_provider_lacks_structured_output():
    provider = _ChatOnlyProvider([json.dumps(_happy_canned_json())])
    uc = AthleteMonthlyNewsletterV2UseCase(provider, PromptRegistry())

    result = await uc.run(_make_ctx())

    assert result.stage_title is not None
    assert len(provider.calls) == 1  # sin reintento: el primer parseo funcionó


@pytest.mark.asyncio
async def test_repair_retry_recovers_from_invalid_json_once():
    provider = _ChatOnlyProvider(
        ["esto no es JSON en absoluto", json.dumps(_happy_canned_json())]
    )
    uc = AthleteMonthlyNewsletterV2UseCase(provider, PromptRegistry())

    result = await uc.run(_make_ctx())

    assert result.stage_title is not None
    assert len(provider.calls) == 2  # primer intento + reparación


@pytest.mark.asyncio
async def test_raises_schema_error_when_repair_retry_also_fails():
    provider = _ChatOnlyProvider(["no json aquí tampoco", "sigue sin ser JSON"])
    uc = AthleteMonthlyNewsletterV2UseCase(provider, PromptRegistry())

    with pytest.raises(LLMSchemaError):
        await uc.run(_make_ctx())
