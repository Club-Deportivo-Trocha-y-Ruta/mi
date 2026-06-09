# Data Model: Faithful, Grounded AI Insights for Competitions

**Feature**: 011-ai-insights-grounding · **Date**: 2026-06-09

> **No new tables. No Alembic migration.** All persistence changes are additive JSON
> keys inside existing columns plus correct use of an existing enum column.

## Existing entities consumed (read-only)

### RaceEvent (table `race_events`) — conditions become the source of truth

| Field | Type | Notes |
|---|---|---|
| `climate` | `String(60) \| None` | e.g. "Nublado" |
| `temperature_c` | `Numeric(4,1) \| None` | e.g. 25.0 |
| `surface_condition` | `Enum SurfaceCondition \| None` | e.g. "Húmeda" (values_callable) |
| `altitude_msnm` | `SmallInteger \| None` | e.g. 1000 |
| `weather_notes` | `Text \| None` | free text — MUST be name-scrubbed before LLM |

Validation rule (FR-002/FR-003/FR-004): the analysis/chat may only surface fields that
are non-NULL; all-NULL → conditions topic omitted entirely.

### AnthropometricRecord (table `anthropometric_records`) — maturation source

- Latest record per athlete (by measurement date) provides `maturation_status`
  (`Pre-PHV` / `Circa-PHV` / `Post-PHV`, stored via values_callable).
- No records → `maturation_status = None` → no maturation claim in output (FR-007).

### Athlete — age / LTAD group source

- `age_decimal` (computed in app) → LTAD group mapping (existing logic):
  ≤12 → `bambino`, 13–15 → `juvenil`, else `junior`.

## Modified value objects (Pydantic / graph state — not persisted as schema)

### AnalysisInput (`app/services/race/schemas.py`)

| Change | Field | Type | Semantics |
|---|---|---|---|
| ADD | `race_meta` | `str \| None` | Pre-formatted, anonymized conditions block for THE válida this input analyzes. `None` → prompt omits conditions and the anti-fabrication veto activates. |
| ADD | `maturation_status` | `str \| None` | Real value from latest anthropometric record; `None` → no maturation claim. |
| REMOVE (dead reads) | — | — | `_build_v2_context` stops reading `podium_context["race_meta"]` and `podium_context["maturation_status"]` (keys that never existed). |

### Graph state (dict keys — contract in `contracts/graph-state.md`)

| Change | Key | Type | Producer → Consumers |
|---|---|---|---|
| ADD | `event_conditions` | `dict[int, EventConditions]` (key = valida_num) | `load_race_data` → `anonymize` (scrub notes) → `analyst_agent` (per-válida `race_meta`), `critic_agent` (ground truth) |
| ADD | `maturation_status` | `str \| None` | router `initial_state` → `analyst_agent` |
| ADD (now real) | `ltad_group` | `str` (LTADGroup value) | router `initial_state` → `_resolve_ltad` (fallback path becomes exceptional + logged) |
| ADD | `per_valida_verdicts` | `dict[int, CriticFeedback]` | `critic_agent` → `hitl_gate_review`, `persist_insight`, confidence |
| ADD (now real) | `confidence` | `dict[int, InsightConfidence]` per válida | confidence computation (post-critic) → `persist_insight` |

`EventConditions` (internal TypedDict/dataclass): `{climate, temperature_c,
surface_condition, altitude_msnm, weather_notes_scrubbed}` — all optional.

## Persisted entity changes (additive, no migration)

### AthleteAiInsight (table `athlete_ai_insights`)

| Column | Change |
|---|---|
| `confidence` | **Behavioral**: stores the computed `InsightConfidence` per row (was: constant default `medium`). Enum and column unchanged. |
| `metrics_snapshot_json` | **Additive keys** (old insights without them remain valid, mirroring the T015/feature-010 precedent): `grounding` → `{event_conditions_used: EventConditions \| null, maturation_status_used: str \| null, ltad_group_used: str}`; `critic_verdict` → serialized per-draft CriticFeedback for THIS row's válida. |

State transitions (existing, now exercised by re-generation): an approved persist for
(athlete, season, valida_num) calls `deprecate_previous_active()` → prior active row
`is_active=0`, new row `is_active=1`. Failure before persist leaves the prior row
untouched (FR-014).

## Confidence derivation (deterministic — `ai/confidence.py`)

```
inputs: verdict: CriticFeedback | None, completeness: {has_conditions, has_maturation, season_n}
rules (first match wins):
  fallback analysis OR verdict.must_block OR any high issue → low
  any med issue OR verdict is None (critic disabled)        → medium
  missing conditions OR missing maturation OR season_n <= 1 → medium (cap)
  otherwise                                                  → high
```
