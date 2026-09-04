# Data Model: Season comparison groups

**Feature**: 039-season-comparison-groups · **Date**: 2026-09-03

No schema change. Everything below is derived at read time from `race_series`, `race_events`, `race_results` and `race_competitors` (features 014 / 023 data), or is an additive key in the JSON `metrics_snapshot` of `athlete_newsletters`.

## 1. ComparisonGroup (derived, backend + API)

| Field | Type | Source / rule |
|---|---|---|
| `comparison_group` | `str` | `"cup:{series_id}"` or `"championship:{series_id}"` |
| `series_id` | `int` | `race_series.id` |
| `kind` | `"cup" \| "championship"` | `race_series.kind` |
| `level` | `"departmental" \| "national"` | `race_series.level` (cups carry the default `departmental`; ignored in labels) |
| `label` | `str` | cup: `"{name} {season_year}"`; championship: `build_race_label(kind, seq, location, level)` |
| `n_points` | `int` | races of the athlete in the group with a non-null metric value |
| `first_event_date` | `date` | ordering key: cups by earliest raced round, then championships by date |

**Invariants**
- INV-1: a race belongs to exactly one group (its series).
- INV-2: a championship group has exactly one race (guaranteed by `series_rules.assert_championship_single_event`).
- INV-3: the group list of a season for an athlete is the set of distinct `series_id` among the athlete's active results (`deleted_at IS NULL`) in that `season_year`.

## 2. ProgressionRow (pandas, `analytics.athlete_progression`)

Existing columns are kept. Added:

| Column | Type | Note |
|---|---|---|
| `event_id` | `Int64` | enables dedupe by event across linked competitors |
| `series_id` | `Int64` | group key |
| `series_name` | `str` | label source |
| `comparison_group` | `str` | see §1 |

`series_kind`, `series_level`, `location`, `valida_num`, `points_awarded`, `gap_to_winner_pct` already exist.

## 3. SplitProgression (pure helper output)

```text
SplitProgression
├── cups: list[CupProgression]            # ordered by first_event_date
│     ├── series_id: int
│     ├── label: str                      # "{name} {season_year}"
│     └── rows: list[ProgressionRow]      # chronological, cup rounds only
└── championships: list[ProgressionRow]   # chronological
```

## 4. ChampionshipReading (newsletter card + detail card)

| Field | Type | Source |
|---|---|---|
| `event_id` | `int` | `race_events.id` |
| `label` | `str` | `"Campeonato Departamental"` / `"Campeonato Nacional"` (readable) |
| `short_label` | `str` | `"Cto. Dep. — Ginebra"` / `"Cto. Nal. — Pereira"` |
| `level` | `"departmental" \| "national"` | series |
| `location` | `str \| None` | event |
| `event_date` | `date` | event |
| `category_label` | `str \| None` | `race_categories.label` via existing batch lookup |
| `finished` | `bool` | `status == finished` |
| `position` | `int \| None` | own result (null when not finished) |
| `field_size` | `int` | finishers-and-others count in the athlete's category for that event (`field_metrics.field_size`) |
| `gap_pct` | `float \| None` | `field_metrics.gap_pct` (1 decimal) |
| `percentile` | `float \| None` | `field_metrics.percentile` (position-based, D3) |

**Validation**: `percentile` ∈ [0, 100]; `gap_pct ≥ 0`; when `finished = false` → `position`, `gap_pct`, `percentile` are `null` and the card shows the not-finished state. Never includes names, bibs or competitor ids.

## 5. EvolutionPoint / EvolutionResponse (Pydantic + TS mirror)

`EvolutionPoint` (additive): `series_id: int`, `series_name: str`, `series_level: Literal["departmental","national"]`, `comparison_group: str`, `field_size: int | None`, `percentile: float | None`, `position: int | None` (finished position in category, `null` when not finished), `gap_pct: float | None` (`100 * (race_time_ms - winner_time_ms) / winner_time_ms`, 1 decimal; `0.0` for the winner; `null` when not finished or no winner time — F-1 / B-2, exposed for every `metric`, not only `ranking`/`podium_gap_ms`). Existing: `valida_num`, `event_id`, `event_date`, `value`, `unit`, `series_kind`, `label`.

`EvolutionResponse` (additive): `groups: list[ComparisonGroupOption]` (fields of §1 minus `first_event_date`), `selected_group: str | None` (echo of the applied filter). Existing: `season`, `metric`, `series`, `confidence` (now computed over the returned `series`).

`RaceParticipationOption` (additive): `series_id: int`, `series_name: str`, `series_level`.

## 6. Newsletter snapshot keys (`athlete_newsletters.metrics_snapshot`)

```text
email_blocks.race_results
├── has_races, competitor_id, results[], projection      # unchanged
├── progression_history[]                                # kept one release (flat, back-compat)
├── cups[]            → [{series_id, label, history: [ProgressionRow-serialized]}]
└── championships[]   → [ChampionshipReading]

pdf_only_blocks.charts_context
├── has_data: bool                                       # any cup with rows
├── has_championship: bool                               # kept
└── cups[] → [{series_id, label, n_samples, low_confidence,
              positions[], gap_pcts[], points_accumulated[]}]   # same point shape {x, label, y} as today
```

Stored snapshots from before this feature lack `cups` / `championships`; the PDF template must treat missing keys as empty lists (regenerating the newsletter fills them).

## 7. AI state (LangGraph `RaceAnalysisState`)

| Key | Change |
|---|---|
| `metrics.progression` | unchanged (flat) |
| `metrics.progression_groups` | NEW: `{"cups": {series_id: [rows]}, "championships": [rows]}` |
| `full_season_results[i]` | + `series_id`, `series_kind`, `series_level` |
| `season_comparative` | priors restricted to the analyzed race's `series_id`; `event_label` from `build_race_label` |
| `progression_assessment` | `first_reference` for championships |
| `field_context` | unchanged (already keyed by `event_id`, carries `series_kind` / `series_level` / `is_championship`) |

## 8. State transitions

None new. Selector state in the frontend: `seriesId` (number | undefined) → query key `["athlete-evolution", athleteId, season, metric, seriesId]`; on season change, `seriesId` resets to undefined so the server default (first cup) applies.
