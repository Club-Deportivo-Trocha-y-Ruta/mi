# Contract — Course block for the race AI analysis

**State**: `backend/app/services/race/ai/state.py` (`RaceAnalystState`). **Loader**: `ai/nodes/load_race_data.py` (`:344` where `fetch_event_conditions` is called) + `ai/queries.py` (`fetch_event_conditions:270-321` is the pattern). **Formatter and context**: `race/agents/analyst.py` (`format_race_meta:468-504`, `_build_v3_context:1377-1407`, `AnalystV3Input`). **Prompts**: `race/prompts/race_analyst_v3.md` (conditions block at `:85-92`), `race/prompts/race_season_summary_v3.md`. **Golden eval**: `backend/tests/evals/test_race_analyst_eval.py`, cases in `backend/evals/race_analyst/golden_v3/case_NNN.json`. Binding: `research.md` R-10. Requirements: FR-018–FR-021; SC-004; User Story 4.

## 1. State

`RaceAnalystState` + `course_context: dict[int, dict]` — keyed by `valida_num` like `event_conditions`; **every requested válida is present as a key**; value is `{}` when the válida has no course data or the rider's category has no setup ("absence must be representable", same rule as conditions). Populated in `load_race_data` right after `event_conditions` by:

```python
fetch_course_context(db, season, validas, category_id) -> dict[int, dict]
# per valida_num: {"lap_distance_m", "elevation_gain_m", "laps", "terrain_type",
#                  "technical_difficulty", "key_sectors"}  — never "course_notes"
```

The query selects only those columns (the `course_notes` column is never in the select list — structural exclusion, FR-020) and joins `race_course_category_setups` → `race_course_variants` for the rider's `category_id`; terrain/difficulty/sectors come from the cached event rows.

## 2. Formatter — `format_course_meta(course: dict | None) -> str | None` in `analyst.py`

Returns `None` when `course` is falsy or when it carries neither a variant nor any description field (the SIN DATO veto must fire). Otherwise bullets in español neutro, only for present fields, numbers formatted with comma decimal like the rest of the prompt:

```text
- Distancia por vuelta: 4,2 km
- Desnivel positivo por vuelta: 110 m
- Vueltas de la categoría: 3 (distancia total 12,6 km)
- Terreno: mixto
- Dificultad técnica: 4/5 (técnico)
- Sectores clave: subida larga, rock garden
```

`AnalystV3Input` + `course_meta: str | None`; `_build_v3_context` + `"course_block": input_.course_meta`. The season summary receives one `course_block` per válida inside its per-válida table (same formatter, rendered by a loop the template already has for conditions or, if none, a new `course_by_valida` mapping — implementer's choice, documented in the prompt file header).

## 3. Prompt block (both v3 templates), placed immediately after the conditions block

```jinja
{% if course_block %}
## Circuito registrado

Estas son las **únicas** características del circuito registradas. No agregues ninguna otra ni estimes distancias o desniveles no listados.

{{ course_block }}
{% else %}
## Circuito — SIN DATO

PROHIBIDO mencionar distancia, vueltas, terreno, desnivel, altimetría o dificultad técnica del circuito.
{% endif %}
```

The `race_analyst_v2` prompts are **not** modified; rendering them with the extended context must still succeed (context keys are a superset; a rendering test asserts both versions render).

## 4. Golden evaluation

Two new cases in `golden_v3/`: `case_0XX_course_present.json` (`input.course_meta` set; `expected_themes` includes contextualising the time by distance/terrain; `forbidden_terms` unchanged) and `case_0XX_course_absent.json` (`input.course_meta = null`; `forbidden_terms` += `["km", "vuelta", "vueltas", "terreno", "desnivel", "técnico", "dificultad"]`). `RACE_EVAL_THRESHOLD` stays 0.75; the baseline file is regenerated after the run and its composite must be ≥ 0.75 (FR-021). The case builder passes `course_meta` straight to `AnalystV3Input`.

## 5. Tests (default lane, fake provider)

- `fetch_course_context` returns every requested válida as a key; `{}` when no setup for the category; never contains `course_notes` (assert on the SQL text compiled and on the dict).
- `format_course_meta({})` → `None`; with only description fields → bullets without distance; with everything → six bullets.
- Prompt render with `course_block` present contains "Circuito registrado"; absent contains "PROHIBIDO mencionar distancia".
- End-to-end with `FakeLLM`: run the per-válida pipeline for a válida with course data and assert the captured prompt contains the six bullets and not the notes text; for a válida without it, assert the veto text is present.
- Privacy: `course_notes` containing a forbidden name never reaches the prompt (it cannot, but the test pins it).
