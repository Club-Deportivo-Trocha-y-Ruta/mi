# Contract: race AI pipeline inputs (LangGraph state + prompts)

**Feature**: 039 · **Nodes**: `compute_metrics`, `analyst_agent`, `load_race_data` · **Prompts**: `race_analyst_v3.md` (edit), `race_season_summary_v3.md` (verify only)

## State keys

| Key | Producer | Shape / change |
|---|---|---|
| `metrics.progression` | `compute_metrics` | unchanged flat list (rows carry `event_id`, `series_id`, `series_kind`, `series_level`, `comparison_group`) |
| `metrics.progression_groups` | `compute_metrics` | NEW `{"cups": {"<series_id>": [rows]}, "championships": [rows]}` |
| `full_season_results[i]` | `load_race_data` | + `series_id`, `series_kind`, `series_level` (already has `event_id`, `valida_num`) |
| `season_comparative` | `compute_metrics` | priors = same `series_id` as the analyzed race, `event_date` earlier, ordered by date; `event_label` via `build_race_label`; `[]` for championships |
| `progression_assessment` | `compute_metrics` | `first_reference` for championships |
| `field_context` | `compute_metrics` | unchanged; keyed by `event_id` |

## Race resolution rules (applies to v2 and v3 paths)

1. If `state.event_id` is set (launch anchored from a competition), the analyzed row is the progression row with that `event_id`. Never by `valida_num` alone.
2. Without an anchor, `valida_num` resolves only among rows with `series_kind == "cup"`; a championship can only be analyzed through an anchored launch (the UI already sends `event_id`).
3. Field metrics for the analyzed race are looked up by `event_id` first (`_field_metrics_by_valida` already prefers the anchored entry; extend the same rule to `race_row`).

## Prompt context

`race_analyst_v3.md` — new inviolable rule (number 10), in Spanish, equivalent to:

> Un campeonato reúne un pelotón distinto (departamental o nacional). Nunca compares su puesto ni su gap con una válida de copa, ni digas que el atleta "subió" o "cayó" posiciones respecto a una válida. Lee el campeonato por percentil, tamaño y fuerza del pelotón; el puesto solo se menciona dentro de esa carrera.

`_progression_to_md` ("Recorrido hasta acá" table) and `_v3_season_block` (the pelotón-metrics table): both add a `serie` column (`Válida N · Copa`, `Cto. Departamental`, `Cto. Nacional`) so the model can see which rows are comparable. Post-review fix (F-4, `checklists/integration-review.md` §G): when the season mixes cup and championship rows, each function renders **two headed markdown tables** — `**Válidas de copa**` and `**Campeonatos (pelotón propio, no comparable con la copa)**` — instead of one, so the model never reads a cup round and a championship as adjacent, comparable rows. `_progression_to_md` additionally sub-groups the cup table by `series_id`/`series_name` when the row carries that field. `_v3_season_block`'s rows come from `field_context`/`FieldMetrics`, which does not carry `series_id` — its cup table stays a single ungrouped group even with two cups in the season (a documented residual, not a regression). A season with only one kind of row keeps the original headless single-table format on both functions.

`race_season_summary_v3.md`: already carries the rule (rule 3) and the method step 1; verified, not edited.

## Rollback

`RACE_AI_PROMPT_VERSION=race_analyst_v2` remains valid. If the golden composite drops below `RACE_EVAL_THRESHOLD` (0.75) after the rule, fork `race_analyst_v4.md` instead of weakening the rule.

## Golden evaluation

New case `evals/race_analyst/golden_v3/case_009.json`: `analysis_kind = "valida"`, national championship (`field_metrics.is_championship = true`, `series_level = "national"`), `season_rows` with cup rounds + CD + CN. `forbidden_terms` include cross-competition position comparisons; `expected_themes` include the field reading (percentile / pelotón nacional). Gate: `pytest -m golden`, average ≥ 0.75.

## Privacy

No change to anonymization: rows contain no names; `field_size`, `percentile` and `gap_pct` are aggregates. `AI_LOG_PROMPTS=false` in production is unaffected.
