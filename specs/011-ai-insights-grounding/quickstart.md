# Quickstart: Verifying Faithful, Grounded AI Insights

**Feature**: 011-ai-insights-grounding

## Setup

```bash
source backend/.venv/bin/activate
cd backend && uvicorn app.main:app --reload   # or: docker compose up
```

Seed credentials (dev only): coach `entrenador@trochyruta.com` / `Coach2026!`.
`AI_ENABLED=true` with a valid `AI_API_KEY` is required for live runs; the regression
tests run fully mocked (no API key needed).

## 1. The canonical fabrication case (SC-001 / SC-006)

The reported bug: athlete 3, Válida 4 (IV Valida XCO, Cali 2026-05-17, event id 14),
recorded conditions = surface **Húmeda**, climate **Nublado**, **25 °C**, **1000 msnm**.

1. Open `Atletas → atleta 3 → Análisis IA → Lanzar`, launch Válida 4.
2. When the insight lands in Histórico, read "Qué pasó en esta válida":
   - PASS: it states wet/cloudy conditions (or omits conditions entirely).
   - FAIL: any mention of "seca", "soleado", "terreno mixto" or other unrecorded facts.
3. The previously stored fabricated insight must now show as replaced (deprecated)
   by the new active one — single re-generate action, US6.

## 2. Omission when no conditions are recorded (FR-003)

1. Pick/create a completed event with all condition fields empty
   (`Competencias → <válida> → Condiciones` shows "— sin registro —").
2. Launch the analysis for an athlete with results in that event.
3. PASS: the narrative contains zero references to clima/pista/terreno.

## 3. Real maturation + LTAD group (SC-002)

1. Athlete 3 is Circa-PHV (offset +0.7): launch an analysis and confirm the stored
   `metrics_snapshot_json.grounding.maturation_status_used == "Circa-PHV"` (and the
   narrative never frames her as Pre-PHV).
2. For a 13–15 athlete, confirm `ltad_group_used == "juvenil"`.
3. For an athlete without anthropometric records, confirm no maturation claim appears.

## 4. Review coverage + confidence (SC-003/SC-004/SC-005)

1. Launch a group analysis covering ≥2 válidas.
2. Inspect the run/insights: each persisted row carries its own critic verdict
   (`metrics_snapshot_json.critic_verdict`) — N drafts → N verdicts.
3. Confidence: a clean run with full data shows **alta**; the same athlete on an event
   without conditions (or with critic issues) shows **media/baja** — the badge varies.

## 5. Chat grounding (FR-012)

In the competition chat ask: «¿Cómo estaban la pista y el clima en la válida 4?»

- Event with recorded conditions → answer matches Húmeda/Nublado/25 °C.
- Event without conditions → answer says it was not recorded; no invented values.

## 6. Test suite

```bash
cd backend && pytest tests/ -k "grounding or critic or confidence" -v
cd frontend && npm test -- --run InsightsTimeline
```

Regression tests to look for (Constitution II — each fails on unfixed code):

- `test_race_meta_populated_from_event_conditions` / `test_race_meta_none_when_unrecorded`
- `test_prompt_has_no_conditions_section_when_unrecorded` (+ veto present)
- `test_maturation_status_not_defaulted` / `test_ltad_group_injected`
- `test_critic_reviews_all_drafts` (N drafts → N verdicts)
- `test_critic_flags_contradiction_with_ground_truth`
- `test_confidence_varies_with_inputs` (not constant `medium`)
- `test_failed_regeneration_keeps_previous_insight_active`
- privacy: `test_weather_notes_scrubbed_before_prompt`
