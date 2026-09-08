# Checklist — Family copy review (T063, feature 040, US4)

**Reviewer**: `parent-communicator` · **Date**: 2026-09-04 · **Branch**: `feat/040-growth-module-redesign`
**Scope**: every family-facing string introduced in Phases 4–6 — `lib/growth/bands.ts` (`familyLabel` + `narrative`), `FamilyStageCard.tsx`, `FamilyBandCards.tsx`, the family chart caption in `GrowthCurveSection.tsx`, and the coach-audience AI prompt `phv_explanation_coach_v1.md`. Checked for español neutro, full diacritics and a non-judgmental, warm tone (no clinical jargon, no alarmism, no medical diagnosis).

## Edits applied

| # | File | Band / string | Before | After | Why |
|---|---|---|---|---|---|
| 1 | `frontend/src/lib/growth/bands.ts` | `talla_alta.narrative` (height, shown on "Estatura para su edad") | "La estatura está significativamente por encima del promedio. No es patológico; útil considerar estado de maduración biológica." | "La estatura está significativamente por encima del promedio. No es un problema de salud; puede relacionarse con su etapa de maduración biológica." | Broken sentence ("útil considerar…" has no verb) and the clinical term "patológico" reached the parent card verbatim — replaced with a plain, grammatical sentence, same meaning. |
| 2 | `frontend/src/lib/growth/bands.ts` | `delgadez_severa.narrative` (BMI, shown on "Peso para su estatura", the most severe band — `referral: true`) | "El IMC está por debajo del rango saludable. En atleta activo descartar disponibilidad energética insuficiente. Recomendamos evaluación nutricional." | "El peso para su estatura está por debajo del rango esperado. En quienes entrenan con regularidad, esto puede indicar que la alimentación no está cubriendo el gasto de energía. Recomendamos una evaluación nutricional." | Ungrammatical fragment ("En atleta activo descartar…") carrying the sports-medicine term "disponibilidad energética insuficiente" (energy availability / RED-S) straight to a parent, and "IMC" contradicted the card's own accessible title (decision D3). Reworded in plain language, kept the referral. |
| 3 | `frontend/src/lib/growth/bands.ts` | `delgadez.narrative` (BMI) | "El IMC está un poco bajo. Vigilamos que la alimentación sea suficiente para el entrenamiento." | "El peso para su estatura está un poco bajo. Vigilamos que la alimentación sea suficiente para el entrenamiento." | "IMC" swapped for the card's own accessible name, for consistency with D3 (the family title deliberately avoids the acronym; the tooltip is the only place it should appear). |
| 4 | `frontend/src/lib/growth/bands.ts` | `adecuado.narrative` (BMI) | "El IMC está dentro del rango saludable para su edad." | "El peso para su estatura está dentro del rango esperado para su edad." | Same D3 consistency fix; also aligned wording ("rango esperado") with the other narratives in the set. |
| 5 | `frontend/src/lib/growth/bands.ts` | `sobrepeso.narrative` (BMI) | "El IMC está en el límite superior. En ciclistas que entrenan con regularidad puede reflejar mayor masa muscular. Se monitorea la tendencia." | "El peso para su estatura está en el límite superior. En ciclistas que entrenan con regularidad, esto puede reflejar mayor masa muscular. Seguimos la tendencia en las próximas mediciones." | "IMC" fix (D3); passive/impersonal closing ("Se monitorea la tendencia") replaced with a first-person, warmer closing consistent with the club's voice; added the missing comma after the introductory clause. |
| 6 | `frontend/src/lib/growth/bands.ts` | `obesidad.narrative` (BMI, `referral: true`) | "El IMC está por encima del rango saludable. Requiere evaluación; muy raro en atletas activos." | "El peso para su estatura está por encima del rango esperado. Es poco frecuente en deportistas activos; recomendamos una evaluación para tener claridad." | "Requiere evaluación; muy raro en atletas activos" is a verbless fragment and reads as blunt/alarming for the most severe band. Rewritten as a full sentence, keeps the referral, softer framing ("para tener claridad" instead of a bare command). |
| 7 | `backend/app/services/ai/prompts/phv_explanation_coach_v1.md` | Step 3 of "Cómo responder" (coach-audience prompt) | "énfasis técnico vs. carga, recuperación, cuidado articular…" | "énfasis técnico o de carga, recuperación, cuidado articular…" | "vs." is an English abbreviation inside an otherwise español-neutro instruction; replaced with "o de" — tone-only change, no new fields, guardrails untouched. |

## Reviewed, no change needed

| File | Notes |
|---|---|
| `frontend/src/lib/growth/bands.ts` — `retraso_talla`, `riesgo_retraso_talla`, `talla_adecuada` narratives + all 9 `familyLabel` values | Already warm, grammatical, correct diacritics, no jargon, no comparison between athletes (population-average phrasing is pre-existing, contract-approved wording, not a comparison to a named teammate). |
| `frontend/src/lib/growth/bands.ts` — `WEIGHT_LABEL_OVERRIDES` | Out of scope: only reached via `getBandVocabulary("weight_for_age", …)`, which `FamilyBandCards.tsx` never calls (it renders only `height_for_age` and `bmi_for_age`) — this override is coach-only today. |
| `frontend/src/components/athletes/growth/FamilyStageCard.tsx` | "Etapa de desarrollo", "Evaluado en {mes} {año}" and the three stage phrases ("Tu hijo/a está en etapa de desarrollo temprano" / "…en su pico de crecimiento — etapa clave" / "El crecimiento de tu hijo/a se está estabilizando") are warm, non-alarming, correctly accented, no clinical vocabulary. Pinned verbatim by `FamilyStageCard.test.tsx` — left untouched. |
| `frontend/src/components/athletes/growth/FamilyBandCards.tsx` | Titles ("Estatura para su edad", "Peso para su estatura"), tooltip ("Índice de masa corporal para la edad, OMS 2007"), empty-state message ("Aún no hay datos suficientes para mostrar esta medida.") and the `aria-label` are accessible, correctly accented, non-judgmental. No changes. |
| `frontend/src/components/athletes/growth/GrowthCurveSection.tsx` | No literal family-facing caption string exists in this file — it composes `PercentileChart`/`PercentileTable`/`PercentileInterpretationBlock` and only decides *whether* to show the coach's PHV footnote (`phvNote = null` in family mode). The actual family chart legend/caption ("Deportista" / "Promedio" / "Rango esperado") lives in `PercentileChart.tsx`, which is outside this task's file-ownership list — not reviewed here. |

## Privacy / tone gate re-check

- [x] No minor's name, birth date or medical data (weight/height numbers, diagnosis) introduced in any edit — all six `bands.ts` narratives stay qualitative ("por debajo del rango esperado", "en el límite superior"); the two `referral: true` bands point to a professional evaluation without disclosing any figure.
- [x] No comparison between athletes — the pre-existing population-average phrasing ("por debajo del promedio") is unchanged and was already present.
- [x] No pressure language, no result promises, no diagnosis — "descartar disponibilidad energética insuficiente" (a clinical judgement) removed; replaced with a plain observation plus a referral.
- [x] Full diacritics verified by re-running the affected test suites (below); no new `[A-Za-z]` accent gaps introduced.

## Tests run after the edits

| Command | Result |
|---|---|
| `cd frontend && npx vitest run src/lib/growth src/components/athletes/growth src/components/athletes/PercentileInterpretationBlock.test.tsx src/components/athletes/NutritionalClassification.test.tsx src/routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx` | **PASS — 300/300, 21 files** |
| `cd frontend && npm run typecheck` | **PASS — 0 errors** |
| `cd backend && .venv/bin/python -m pytest tests/test_ai_router.py -q -k phv` | **PASS — 24 passed, 2 deselected** |

No test pinned the exact narrative strings that changed (only `toBeTruthy()` / label / tone assertions in `bands.test.ts`, and the `FamilyBandCards.test.tsx` regex `/La estatura está por debajo del rango esperado/` matches an untouched narrative), so no test file needed an update.

---

**Signed**: `parent-communicator` — 2026-09-04
