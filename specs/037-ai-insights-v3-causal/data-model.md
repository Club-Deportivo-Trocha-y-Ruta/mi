# Data model — feature 037

## InsightV3 (Pydantic, `app/services/race/insight_v3.py`; TS mirror `frontend/src/types/insightV3.types.ts`)

```python
class EvidenceDomain(str, Enum): race="race"; field="field"; training="training"; maturation="maturation"; conditions="conditions"; history="history"
class ActionCategory(str, Enum): technique, volume, recovery, nutrition, psychology, tactics
class Priority(str, Enum): low, med, high
class Horizon(str, Enum): next_week="next_week"; next_race="next_race"; season="season"
class CatalogKind(str, Enum): technique_skill, strength_block, interval_template

class Observation(BaseModel):
    claim: str            # ≤ 300 chars, one interpretive sentence
    evidence: list[str]   # 1..3 items, ≤ 140 chars, each containing ≥1 number copied from the data
    domain: EvidenceDomain
    confidence: Literal["high","medium","low"]

class CatalogRef(BaseModel):
    kind: CatalogKind
    code: str             # skill code "A".."H", or numeric id as str for blocks/templates
    label: str | None     # filled by prechecks from catalog_context

class ActionV3(BaseModel):
    text: str             # ≤ 280 chars, imperative, concrete (what, how often, how long)
    category: ActionCategory
    priority: Priority
    horizon: Horizon
    catalog_ref: CatalogRef | None
    derived_from: int | None   # index into observations

class FieldReading(BaseModel):
    percentile: float | None          # 0..100, 100 = winner
    expected_position: int | None
    actual_position: int | None
    delta_vs_expected: int | None
    gap_to_p3_hhmmss: str | None
    series_label: str                 # "Válida V · Copa Valle" / "Cto. Departamental"
    summary: str                      # ≤ 200 chars, prose

class InsightV3(BaseModel):
    schema_version: Literal["v3"] = "v3"
    headline: str                      # ≤ 200 chars
    field_reading: FieldReading | None
    trend: Literal["improving","stable","declining","mixed","first_reference"]
    observations: list[Observation]    # 2..4
    actions: list[ActionV3]            # 2..3
    watch_signals: list[str]           # 0..2, ≤ 140 chars
    coach_question: str                # ≤ 240 chars, ends with "?"
    data_gaps: list[str]               # 0..3, ≤ 140 chars
    principles_cited: list[str]        # section titles of docs/01-marco-teorico.md, 0..3
```

## AnthroContext (dict written by `load_athlete_context`)

```
{
  "records_count": int,
  "latest": {"evaluation_date": "YYYY-MM-DD", "days_before_event": int, "maturity_offset_years": float, "age_at_phv": float,
             "maturation_status": "Pre-PHV|Circa-PHV|Post-PHV", "height_percentile": float|None},
  "previous": {"evaluation_date": ..., "maturity_offset_years": ..., "maturation_status": ...} | None,
  "growth_velocity_cm_per_year": float | None,      # from calculate_growth_velocity × 12
  "months_from_phv": float | None,                  # maturity_offset_years × 12, signed
  "flags": ["approaching_circa_phv" | "stale_measurement_gt_120d" | ...]
}
```
Never included: weight, BMI, z-scores, nutritional_status, arm span, notes.

## TrainingWindow

```
{
  "window_days": 28, "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD",
  "sessions_in_window": int,            # club sessions where the athlete has an attendance row
  "attended": int, "absent": int, "excused": int, "attendance_pct": float | None,
  "training_hours": float | None,       # sum duration_min of attended / 60
  "rpe_mean": float | None, "rpe_last7_mean": float | None, "rpe_prev21_mean": float | None,
  "rubric_effort_mean": float | None, "rubric_attitude_mean": float | None, "rubric_technique_mean": float | None,
  "technical_foci": [str],              # deduped, ≤6, via group_focus_texts labels when available
  "skill_codes_worked": ["A","F"],      # from technique_session_exercises
  "strength_sessions": int, "interval_sessions": int,
  "days_since_last_session": int | None,
  "days_since_previous_race": int | None,
  "coach_feedback": [str],              # ≤3, ≤200 chars each, scrubbed with club_forbidden_names
  "strava_load": None                   # reserved
}
```
`None` when the athlete has zero attendance rows in the window (analyst must list it in `data_gaps`).

## FieldMetrics (per event, `field_metrics.py`)

```
{
  "event_id": int, "valida_num": int, "event_date": "YYYY-MM-DD", "series_kind": "cup|championship", "series_level": str, "is_championship": bool,
  "field_size": int, "position": int | None, "percentile": float | None,
  "race_time_ms": int | None, "gap_to_p1_ms": int | None, "gap_pct": float | None, "gap_to_p3_ms": int | None,
  "category_median_time_ms": int | None, "gap_to_median_pct": float | None, "laps_behind": int | None,
  "prior_index": float | None, "expected_position": int | None, "delta_vs_expected": int | None,
  "field_strength": float | None, "coverage_with_prior": float
}
```

## DB — `athlete_ai_insights` new columns

| column | type | notes |
|---|---|---|
| `structured_json` | JSON NULL | `InsightV3.model_dump()`; `None` for v1/v2 rows |
| `coach_answer_text` | VARCHAR(1000) NULL | scrubbed on write with club forbidden names |
| `coach_answer_at` | DATETIME NULL | |
| `coach_rating` | TINYINT NULL | 1 útil / -1 no útil |

## API deltas

- `AthleteInsightOut` += `headline: str | None` (from `structured_json.headline`), `coach_rating`.
- `AthleteInsightDetailOut` += `structured: InsightV3 | None`, `coach_answer_text`, `coach_answer_at`, `coach_rating`. Parent mode: `structured.field_reading.expected_position/delta_vs_expected`, `coach_question`, training-domain observations' evidence and `coach_answer_*` are omitted server-side.
- `POST /api/athletes/{id}/race-analysis/insights/{insight_id}/answer` → 200 `AthleteInsightDetailOut`.
- `POST /api/athletes/{id}/race-analysis/season-summary` → 202 `{run_id, status}` (was 200 with summary_text).
- `POST /api/race-analysis/runs` body += `analysis_kind: "valida"|"season"` (default `valida`); 451 when AI consent is missing.
- Run event `hitl_gate_review` payload += `structured_draft: InsightV3 | None`.
- `POST /api/race-analysis/chat` body += `athlete_id: int | None` scope.
