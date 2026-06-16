# Phase 1 Data Model — Race-analysis Championship Charts Fix

**No database migration.** All persistent columns already exist (feature 014, migration
`b1c2d3e4f5a6`). This document describes the **read models / API schemas** that change and the
domain entities they project.

## Domain entities (from spec)

| Entity | Source tables | Identity | Notes |
|---|---|---|---|
| **Race** | `race_events` (+ `race_series`) | `event_id` | Belongs to a `race_series`; `series.kind ∈ {cup, championship}`. |
| **Cup round** | `race_events` where `series.kind='cup'` | `event_id` | Has a round marker (`sequence_number` 1..7) + host city. |
| **Departmental Championship** | `race_events` where `series.kind='championship'` | `event_id` | Standalone single-event series; `sequence_number=1` server-forced — **never** represented by a round number. |
| **Athlete race participation** | `race_results` (`athlete_id`, `event_id`) | `(athlete_id, event_id)` | Source of truth for which races the Distribution picker offers. Includes DNF/DNS/DSQ (they participated). |
| **Time distribution** | `race_results` for `(event_id, category_id)`, `status='finished'` | — | Athlete's time vs the category field for one race. |
| **Evolution series** | `race_results` for `(athlete_id, season)` | ordered by `event_date` | One point per competed race. |

Persistent columns relied upon (already present):
`race_series.kind` (enum `cup|championship`, `values_callable`), `race_events.series_id`,
`race_events.sequence_number`, `race_events.event_date`, `race_events.name`,
`race_events.location`, `race_results.event_id`, `race_results.athlete_id`,
`race_results.category_id`, `race_results.race_time_ms`, `race_results.status`,
`race_results.deleted_at`, `race_categories.code`, `race_competitors.display_name`.
Index: `ix_race_results_athlete_event (athlete_id, event_id)`.

## New schema — `RaceParticipationOption` / `RaceParticipationResponse`

`backend/app/schemas/athlete_race_analysis.py` (Pydantic v2, `extra="forbid"`).

```text
RaceParticipationOption
  event_id:        int   (ge=1)          # stable race identity
  sequence_number: int   (ge=1, le=99)   # round marker; informational only
  series_kind:     "cup" | "championship"
  event_date:      date
  event_name:      str                   # public federation name
  location:        str | None            # host city
  label:           str   (min_length=1)  # server-built display label

RaceParticipationResponse
  season: int (ge=2020, le=2100)
  items:  list[RaceParticipationOption]  # competed races only, ordered by event_date
```

- **Privacy**: contains **no** `athlete_id`/`competitor_id`/user ids. Event name + city are public
  data from the federation PDF (not minor PII).
- **Label rule** (pure, server-side; mirrored client-side for the synthetic aggregate entry):
  - `cup` → `"Válida {roman(sequence_number)} — {location}"` (e.g. `"Válida IV — Cali"`)
  - `championship` → `"Cto. Dep. — {location}"` (e.g. `"Cto. Dep. — Ginebra"`)
- The "Temporada (todas)" aggregate is **not** an item here; the frontend prepends it as a
  synthetic, non-fetching entry (Decision 5).

## Changed schema — `DistributionResponse`

| Field | Before | After | Reason |
|---|---|---|---|
| race identity | `valida_num: int (ge=0, le=99)` | `event_id: int (ge=1)` | Identify by stable race id (FR-004/006). |
| empty fallback | `category_id=0`, `category_code=""` (schema-invalid → 500) | **removed**; no-data returns a valid payload (real category, `athlete_time_ms` may be `null`, `curve=[]`, `confidence=low`) or the endpoint returns **404** for a non-participated `event_id` | FR-001/002 — never 500/blank. |

Unchanged: `season`, `category_id (ge=1)`, `category_code (min_length=1)`, `sample_size`,
`mean_ms`, `stddev_ms`, `athlete_time_ms`, `athlete_z_score`, `athlete_percentile`,
`points[]` (pseudonym + optional coach-only `display_name`), `curve[]`, `confidence`.

> The `valida_num` field referenced by the **AI insights** read models (`AthleteInsightOut`,
> `ClubInsightByRaceItem`, `AthleteRunOut`, etc.) is **out of scope and unchanged** — only the
> Distribution analytics response swaps to `event_id`.

## Changed schema — `EvolutionPoint` (additive)

| Field | Change | Reason |
|---|---|---|
| `series_kind` | **add** `"cup" \| "championship"` | Label the championship as its own point (FR-009/011). |
| `label` | **add** `str (min_length=1)` | Server-built display label (same rule as above) so the chart never re-derives identity from a round number. |
| `valida_num` | **kept** (`ge=0, le=99`) | Back-compat of the field; frontend stops using it for identity/label. |
| `event_id`, `event_date`, `value`, `unit` | unchanged | `event_id` is the unique key; `event_date` drives chronological order (FR-010). |

`EvolutionResponse` shape (`season`, `metric`, `series[]`, `confidence`) is unchanged.

## State / behavior rules

- **Distribution selection**
  - `event_id` of a competed race → time distribution for that race's own category (FR-006).
  - no comparable data (DNF / field too small) → valid payload → friendly "no data" state (FR-002).
  - "Temporada (todas)" sentinel → informational state, **no** request (Decision 5).
  - zero competed races → picker shows only the aggregate entry + friendly empty (edge case).
- **Evolution**
  - one point per competed race, keyed by `event_id`; championship labeled via `series_kind`,
    positioned by `event_date`; DNF/DNS/DSQ → `value=null` (listed below the chart, unchanged).
- **RBAC / privacy (all surfaces)** — reuse `verify_athlete_access`; `display_name` only for
  coach/admin; parents always see pseudonyms; no minor PII in responses, logs, or the 404 body.
