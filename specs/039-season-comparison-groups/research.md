# Phase 0 Research: Season comparison groups

**Feature**: 039-season-comparison-groups · **Date**: 2026-09-03

Sources: codebase reading (services, templates, prompts, tests), Context7 (`/recharts/recharts`, 3.x), shadcn registry state of `frontend/`, dataviz skill (`choosing-a-form.md`, `marks-and-anatomy.md`), specs 014 / 016 / 023 / 037 / 038.

---

## D1 — How to model the comparison group

**Decision**: Derive it; do not persist it. `comparison_group = f"cup:{series_id}"` for `RaceSeriesKind.cup`, `f"championship:{series_id}"` for `RaceSeriesKind.championship`. One pure module `app/services/race/comparison_groups.py` exposes `build_comparison_group(kind, series_id)`, `group_label(kind, level, name, season_year, location)` and `split_progression(rows) -> SplitProgression(cups: list[CupProgression], championships: list[row])`.

**Rationale**: Feature 014 already made each championship its own `race_series` (D1 there) and 023 added `level`. The series row therefore *is* the group; adding a column would duplicate `kind` + `id`. Multi-cup support falls out for free (each cup series is its own group). Zero migration on a Hostinger MySQL we cannot roll back cheaply.

**Alternatives considered**: (a) `comparison_group_id` column on `race_series` — rejected: needs Alembic + backfill for a value that is a pure function of existing columns; only justified if two different series ever share a field, which the owner confirmed is not a current case. (b) Grouping by `is_championship` on `race_events` — rejected: loses the per-cup split (all cups would collapse into one group).

## D2 — Series display label

**Decision**: `race_series.name` is stored without the year (`"Copa Valle de Ciclomontañismo"`, unique on `(name, season_year)`). Group label for cups = `f"{name} {season_year}"`; PDF heading = `"Evolución en la {name} {season_year}"`; championship label = existing `build_race_label(kind, seq, location, level)` (`"Cto. Dep. — Ginebra"`, `"Cto. Nal. — Pereira"`) and the readable form `"Campeonato Departamental"` / `"Campeonato Nacional"` already in `newsletter_builder._race_readable_label`.

**Rationale**: reuses the two label builders that exist; no hardcoded "Copa Valle" anywhere new (FR-004 multi-cup). Frontend truncates long names with CSS in the selector; the full label stays in the accessible `<option>` text.

**Alternatives**: hardcode "Copa Valle 2026" — rejected (multi-cup); add a `short_name` column — rejected (migration for cosmetics).

## D3 — Which percentile for the championship reading

**Decision**: Use the **position-based percentile** from `field_metrics.compute_field_metrics` (`100 × (1 − (pos − 1)/(n − 1))`, `n ≤ 1 → 100`), together with `field_size`, `gap_pct` and `position` from the same dict. Do not use the time-based percentile of `EvolutionMetric.PERCENTILE` in `analytics_charts`.

**Rationale**: the field-metrics dict is already what the AI reads (golden dataset `field_metrics.percentile`) and what the season table shows the coach; the newsletter card and the detail card must show the same number the insight cites (FR-012 / SC-002). It is also defined for `n < 5`, whereas the time-based one hides below five finishers.

**Alternatives**: time-based percentile — rejected (inconsistent with insights; undefined for small championship categories).

## D4 — `GET /evolution` filtering strategy

**Decision**: Keep the single CTE query unfiltered, add `series_id`, `series_name`, `series_level`, `season_year` to its select list, compute `groups` from all rows in Python, then filter `series` by the optional `series_id` query param. `confidence` is computed over the filtered series. Response fields are additive; `valida_num` stays (back-compat, spec assumption).

**Rationale**: one round-trip (constitution IV), O(tens) rows, and the client needs the full group list even when viewing one group. Adding a SQL `WHERE` would force a second query for the group list.

**Alternatives**: separate `GET /evolution/groups` endpoint — rejected (extra request over 3G, extra RBAC surface). Filtering client-side only — rejected: `confidence` must be per group and computed server-side to stay consistent with the newsletter.

## D5 — Single-race groups in the athlete detail: card, not chart

**Decision**: When the selected group is a championship, render `ChampionshipReadingCard` (stat-tile row: Posición · Pelotón · Gap al P1 · Percentil, plus the not-finished state) and the existing table view; no `LineChart`.

**Rationale**: dataviz `choosing-a-form.md`: "a single current value → stat tile, not a one-bar chart". recharts 3 draws a one-point line as a lone dot with an empty axis, which reads as broken data. Stat-tile contract from `marks-and-anatomy.md`: label in sentence case, value in sans semibold, text in text tokens (never the series color), no delta (no named prior period is comparable — that is the point of the feature).

**Alternatives**: keep the diamond marker on the cup line — rejected (that is the current, misleading behavior); a one-point line — rejected (empty chart frame).

## D6 — The "Competencia" selector control

**Decision**: A third native `<select>` with the same classes as the existing season and metric selectors in `EvolutionChart.tsx` (`rounded-lg … shadow-ring`, ≥ 48 px touch target). Options: cups first (by earliest raced round), then championships by date; default = first cup, else first championship.

**Rationale**: consistency within the component (constitution III); `frontend/src/components/ui/select.tsx` exists but no `athletes/ai` component uses it, and the project has no shadcn registries configured in `components.json` (verified via the shadcn MCP), so migrating three controls to the Radix Select is a separate visual-coherence change (feature 033 territory), not this one.

**Alternatives**: shadcn `Select` for the new control only — rejected (two control styles side by side).

## D7 — Recharts custom dot typing (Context7, recharts 3.x)

**Finding**: a function passed to `<Line dot={fn}>` receives `DotItemDotProps` = SVG props + `{ points, index, payload, dataKey, value }`; `payload` is the row of `chartData`. The existing `renderEvolutionDot` already uses this. Change: read `payload.series_level` to print `"Cto. Dep."` / `"Cto. Nal."` in `ChampionshipDot` instead of the hardcoded string. Since cup groups no longer contain championships, the diamond only appears when a mixed view is ever re-enabled; keep it level-aware anyway for the table/legend twins.

## D8 — Newsletter data flow and dedupe

**Finding**: `_build_race_block` concatenates `athlete_progression` for every `RaceCompetitor` linked to the athlete and dedupes by `event_date`. Two cups on the same date (or a cup and a championship on the same day) would drop a real result.

**Decision**: add `event_id` to the `athlete_progression` columns and dedupe by `event_id`. `race_results` block gains `cups: [{series_id, label, history: [...]}]` and `championships: [ChampionshipReading]`; `progression_history` (flat) is kept one release for stored snapshots. `_build_charts_context` returns `cups: [{series_id, label, positions, gap_pcts, points_accumulated, n_samples, low_confidence}]`; `has_data` = any cup has rows.

**Where the context is consumed**: `routers/athlete_monthly_newsletters.py:821` and `routers/parent_newsletters.py:224` pass `pdf_only_blocks.charts_context` to the PDF renderer; `stage_log_builder.summit` reads `race_results.results` (month rows) — unchanged, and its label already comes from `_race_readable_label` (level-aware).

**Championship readings source**: reuse `field_metrics.compute_field_metrics(results, events, series, categories, competitor_id, season)` per linked competitor (it already loads via the cached `queries.load_*`), pick the entries whose `series_kind == "championship"`. No new SQL.

## D9 — AI pipeline: what actually mixes today

**Findings**:
- `race_season_summary_v3.md` **already** contains the rule ("Los campeonatos … nunca se comparan puesto a puesto contra válidas de copa") and step 1 uses gap % and percentile as the cross-series metrics; `series_label_v3` labels championships by level in the season table. Season summary needs verification only.
- `race_analyst_v3.md` (per race) has **no** such rule.
- `_build_v3_inputs` picks `race_row = next(r for r in progression_all if r["valida_num"] == valida_num)` — a launch for the departmental championship (`sequence_number = 1`) can pick Válida I's row. `_field_metrics_by_valida` mitigates with the anchored `event_id` for field metrics but not for `race_row`.
- v2 path: `_compute_season_comparative(full_season_results, valida_nums)` groups by `valida_num` and `_event_label` uses the retired `99` convention. Still reachable via `RACE_AI_PROMPT_VERSION=race_analyst_v2`.
- `metrics.progression` (from `athlete_progression`) already carries `series_kind` / `series_level`; `_progression_to_md` just does not print them.

**Decision**:
1. `compute_metrics` returns `metrics.progression` (flat, unchanged for compat) **plus** `metrics.progression_groups = {"cups": {series_id: [rows]}, "championships": [rows]}` (from `split_progression`).
2. `_build_v3_inputs` / v2 `records_for_vn` resolve the race row by the anchored `event_id` when present (`state["event_id"]`), falling back to `valida_num` only for cup rows (`series_kind == "cup"`).
3. `_compute_season_comparative(full_season_results, analyzed, *, by="event")`: the analyzed record is located by `event_id` (anchored) or by `(series_id, valida_num)`; priors are records with the **same `series_id`** and earlier `event_date`; a championship yields `[]` + `first_reference`. `load_race_data._compacted_season_record` adds `series_id`, `series_kind`, `series_level`. `_event_label` is replaced by `build_race_label`.
4. `_progression_to_md` gains a `serie` column (via `series_label_v3`-style text) so the v2/v3 "Recorrido" table names the championship.
5. `race_analyst_v3.md` gains rule 10 (mirrors the season prompt): championship ≠ cup round; read a championship by percentile and field size; never say the athlete "dropped/improved N positions" against a cup round.
6. Prompt edited **in place** (rule addition, same JSON contract). `race_analyst_v2` remains the rollback per feature 037. If the golden composite falls below 0.75, fork to `race_analyst_v4` and point `RACE_AI_PROMPT_VERSION` at it instead of weakening the rule.

**Alternatives**: new `race_analyst_v4` from the start — rejected: duplicates a 250-line prompt for a one-rule change and doubles golden maintenance.

## D10 — Golden evaluation

**Decision**: add `backend/evals/race_analyst/golden_v3/case_009.json` — a `valida` analysis of a national championship (`field_metrics.is_championship = true`, `series_level = "national"`, `season_rows` containing cup rounds + CD + CN). `expected_themes` include "pelotón nacional" / "percentil"; `forbidden_terms` include phrases like "cayó N puestos", "perdió posiciones respecto a la válida". Threshold unchanged (`RACE_EVAL_THRESHOLD` 0.75). Run with `pytest -m golden` (needs `RACE_AI_API_KEY`; skips offline).

## D11 — Frontend test surface

**Decision**: extend `mockEvolution()` in `test/msw/athleteRaceAnalysisHandlers.ts` with `groups` and the new point fields; add handler variants `multiGroupEvolutionHandler` (1 cup + CD + CN), `championshipOnlyEvolutionHandler`, `twoCupsEvolutionHandler`. `EvolutionChart.test.tsx` covers selector population/order/default, cup-only rendering, championship card rendering, level-aware labels; `a11y.v2.test.tsx` re-runs jest-axe with the selector present; `MiniSparkline.test.tsx` covers first-cup-only and CN tooltip.

## D12 — MySQL dialect coverage

**Decision**: the `build_evolution` CTE changes (new select columns) get a case in `tests/services/race/test_mysql_dialect.py` (`-m mysql`), since the offline lane runs aiosqlite and enum columns behave differently across drivers (the code already normalizes `series_kind` / `series_level` for both).

## D13 — Copy (español neutro)

- PDF heading: `Evolución en la {nombre de la copa} {año}`
- Block title: `Campeonatos`
- Card labels: `Posición`, `Pelotón` (with `{n} en {categoría}`), `Gap al P1`, `Percentil`
- Card note: `Un campeonato reúne un pelotón distinto al de la copa: se lee por separado y no se compara con las válidas.`
- Not finished: `No completó la prueba.`
- Selector label (sr-only): `Competencia`; subtitle for cups: `Tendencia a lo largo de las válidas de {copa}.`; for championships: `Resultado frente a su propio pelotón.`
- Sparkline empty state when no cup: `Sin válidas de copa en esta temporada.`
