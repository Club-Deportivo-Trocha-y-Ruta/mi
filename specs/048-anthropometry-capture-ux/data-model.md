# Data model: feature 048

**No schema change and no Alembic migration.** Every decision in `research.md` (R3, R4, R5 and clarifications 1, 2 and 4) was chosen to avoid new stored state. The single head stays `448f7dfbca14`.

## Existing entities touched

### AnthropometricRecord (`anthropometric_records`, `backend/app/models/anthropometry.py`)

| Field | Change |
|---|---|
| `evaluation_date`, `weight_kg`, `standing_height_cm`, `sitting_height_cm` (net), `arm_span_cm`, `notes` | Now **editable** via PUT (FR-001). One value per measure, as today (clarification 2). |
| `leg_length_cm`, `leg_sitting_ratio`, `maturity_offset`, `age_at_phv`, `maturation_status`, `training_implications`, `bmi`, `*_z_score`, `*_percentile`, `nutritional_status`, `growth_source` | **Recomputed** on PUT through `derive_record_fields` (R1). |
| `evaluated_by` | Unchanged on PUT; it is the authority for edit/delete (R2). |
| lifecycle | New: **deleted** (hard delete) by the evaluator or an admin, cascading to its skinfold set and AI explanations (R6). |

**Validation (create and update, backend + frontend Zod, same numbers)**:
- `evaluation_date` ≤ today.
- weight 20–150 kg; standing height 100–220 cm; sitting height (net) 50–120 cm; arm span 100–220 cm or null.
- sitting / standing ∈ [0.40, 0.65], otherwise 422 `sitting_ratio_impossible` (FR-016, R5).
- Uniqueness **at application level**: one record per (athlete_id, evaluation_date). POST → 409 `anthropometry_same_date_exists`; PUT changing the date onto an existing one → the same 409 (R4). No DB constraint (legacy data may hold pairs).

### SkinfoldMeasurement (`skinfold_measurements`)
- Deleted with its record (ORM cascade + FK CASCADE).
- On a PUT weight change: estimates recomputed (`recompute_estimates_for_record`).
- On a PUT date change: `check_min_age` + `check_interval_for_date` (new; excludes the record itself) → 409 with the wizard's detail codes (FR-007).

### AthleteAIExplanation (`athlete_ai_explanations`)
- All rows for the record are deleted on PUT (FR-006) and on DELETE (explicit, not relying on SQLite FK enforcement), each audited (table is `AUDIT_STRICT`).

### AuditLog
- `action=update`: `entity_type=anthropometric_record`, `changed_fields=[...]`, values only for `evaluation_date`.
- `action=delete`: `meta={"had_skinfolds": bool}`.
- No measurement values and no names anywhere (FR-004, FR-032).

## Derived, never stored

### PlausibilityWarning (read-time, R5)

| Field | Type | Notes |
|---|---|---|
| `code` | `height_decreased` \| `height_velocity_implausible` \| `weight_change_large` \| `sitting_ratio_atypical` \| `arm_span_ratio_atypical` | Stable API codes; the Spanish copy lives in the frontend. |
| `measure` | `weight` \| `standing_height` \| `sitting_height` \| `arm_span` | Used to jump back to the step. |

- **"Revisar" marker**: `plausibility_flags: list[code]` per record in the coach/admin GET. Computed against the previous record by date. Omitted for parents.

### Roster row (read-time, R9)
`athlete_id`, `full_name`, `category`, `sex`, `birth_date`, `last_evaluation_date | null`, `has_record_on_date`, `skinfolds_eligible`.

## Client-only state (never sent to the server as such)

| State | Where | Lifetime | Content |
|---|---|---|---|
| Capture values | React Hook Form | Until the screen closes | The four measures, date, notes, bench height. No draft (clarification 1). |
| Capture mode preference | `localStorage` `tyr.anthro.captureMode` | Device | `guided` \| `quick`. |
| Bench height | `localStorage` `tyr.anthro.benchHeightCm` | Device | Number in cm; not personal data (FR-014). |
| Measurement session | Zustand store, **not persisted** | Until reload or logout | `date`, `athleteIds[]`, per-athlete status `pending` \| `measured` \| `skipped`, `recordId?`, `hasWarnings?` (FR-022–FR-026). |

### Session state transitions

```text
pending ──save ok──▶ measured
pending ──"Omitir por hoy"──▶ skipped ──"Medir ahora"──▶ pending
measured ──(edit from summary)──▶ measured
```
