# Data model — Growth module redesign (040)

Only the deltas. Existing entities are referenced by their current names.

## 1. `anthropometric_records` (existing table) — additive column

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `growth_source` | `Enum(GrowthSource)` values `WHO`, `CDC` | yes | Reference used for the stored `*_z_score` / `*_percentile` / `nutritional_status`. New rows: `WHO`. Rows recomputed by the backfill: `WHO`. `NULL` = legacy row not yet recomputed (UI shows "referencia anterior"). |

Migration: `backend/alembic/versions/<id>_growth_source_on_anthropometry.py`, down-revision = current head (`f9a0b1c2d3e4` at planning time — re-check before writing). Upgrade adds the nullable column; downgrade drops it. No data migration inside Alembic (the recompute is the idempotent script).

Existing derived columns keep their names and precision. Rule changes to their **values**:

- `weight_z_score`, `weight_percentile`: `NULL` when age at evaluation > 120.5 months (no WHO reference).
- `nutritional_status` (BMI band) and the inferred height band (`_infer_nutritional_status_height` in the router) now come from WHO Z-scores; cut-offs unchanged (`services/growth.py:117-155`).

Validation: raw columns (`weight_kg`, `standing_height_cm`, `sitting_height_cm`, `arm_span_cm`, `evaluation_date`, `notes`) are never written by the recompute — asserted by test.

## 2. `growth_reference_lms` (existing table) — new rows

Rows with `source='WHO'`: `height_for_age` and `bmi_for_age` × {M, F} × 168 monthly ages (61.5 … 228.5), `weight_for_age` × {M, F} × 60 ages (61.5 … 120.5). Unique key `uq_lms_source_indicator_sex_age` already exists; the seed upserts. CDC rows remain.

## 3. `GrowthSummary` (derived, never stored) — response schema

```text
GrowthSummary
├── athlete_id: int
├── computed_at: date                     # today (server), for "hace N meses" math on the client
├── records_count: int
├── latest_evaluation_date: date | None
├── stage: "Pre-PHV" | "Circa-PHV" | "Post-PHV" | None
├── maturity_offset: float | None         # years, from latest record
├── age_at_phv: float | None              # years
├── months_from_phv: float | None         # (age today − age_at_phv) × 12, 1 decimal; negative = before PHV
├── velocity: GrowthVelocity | None       # None when < 2 records
│   ├── cm_per_month: float
│   ├── cm_per_year: float
│   ├── window_days: int
│   ├── interval_short: bool              # window_days < 30
│   └── expected_cm_per_year: [float, float]   # by stage and sex (R-05)
├── measurement: MeasurementDue
│   ├── status: "ok" | "due_soon" | "overdue" | "never"
│   ├── interval_days: int                # 90 / 30 / 120 by stage (default 90)
│   ├── next_due_date: date | None
│   └── days_overdue: int | None
├── alerts: list["circa_phv" | "height_p3" | "bmi_p3" | "rapid_growth" | "approaching_circa" | "phase_changed"]
└── latest: LatestBands | None
    ├── record_id: int
    ├── growth_source: "WHO" | "CDC" | None
    ├── height: BandReading | None        # None when no reference for the age
    │   ├── value: float                  # cm
    │   ├── z_score: float
    │   ├── percentile: float
    │   └── band: NutritionalStatus       # retraso_talla | riesgo_retraso_talla | talla_adecuada | talla_alta
    ├── bmi: BandReading | None           # value kg/m²; band delgadez_severa | delgadez | adecuado | sobrepeso | obesidad
    └── weight: BandReading | None        # only when age ≤ 120.5 months; band uses the height vocabulary (peso bajo…)
```

Derivation rules:

- `stage`, `maturity_offset`, `age_at_phv`: copied from the latest record (Mirwald, unchanged).
- `velocity`: `measurement_alerts.calculate_growth_velocity(latest, previous)`; `cm_per_year = round(cm_per_month × 12, 1)`.
- `measurement`: `calculate_next_due(latest.evaluation_date, stage)`; status thresholds identical to `routers/alerts.py` (`due_soon` when 0 < days to due ≤ 7).
- `alerts`: `circa_phv` if stage is Circa; `height_p3` / `bmi_p3` when the respective percentile < 3; `rapid_growth` when `cm_per_month ≥ 0.6` **and** `not interval_short`; `approaching_circa` via `detect_approaching_circa(offset)`; `phase_changed` when previous record stage ≠ latest stage.
- `latest.*.band`: from stored `nutritional_status` (BMI) and `_infer_nutritional_status_height` (height) — no recomputation in the endpoint.

## 4. Band vocabulary (frontend constants, `lib/growth/bands.ts`) — extended

```text
BandSpec
├── coachLabel: string        # "Talla adecuada", "Sobrepeso", …
├── familyLabel: string       # "Dentro del rango esperado", "Por encima del rango esperado", …
├── narrative: string         # existing family sentence
├── tone: "success" | "warning" | "danger" | "neutral"   # StatusBadge status
└── referral: boolean         # true for retraso_talla, delgadez_severa, obesidad (coach-only hint "derivar")
```

Keyed by `NutritionalStatus` value (backend enum) instead of the old five-step `GrowthBand`; `classifyBand` remains for the local fallback and becomes indicator-aware (height: `1 < z ≤ 2` → `talla_adecuada`).

Family titles (D3): height card "Estatura para su edad"; BMI card "Peso para su estatura" (tooltip: "Índice de masa corporal para la edad, OMS 2007").

## 5. Training rule (frontend constant, `lib/growth/rules.ts`)

```text
TrainingRule
├── id: string                # "high_intensity", "bodyweight_strength", "external_load", "weekly_hours",
│                              # "cadence", "max_hr_test", "powermeter", "intensity_distribution", "train_race_ratio"
├── topic: string             # label shown
├── ageGroup: "10-12" | "13-15"
├── stage: "Pre-PHV" | "Circa-PHV" | "Post-PHV" | "any"
├── status: "allowed" | "caution" | "forbidden"
└── text: string              # español neutro, no numeric HR estimate
```

`rulesFor(ageGroup, stage)` returns one rule per `id` (stage-specific overrides the `any` row). `differsFromDefault` compares with the `(ageGroup, "any")` row.

## 6. AI explanation (existing `athlete_ai_explanations`) — new `use_case` value

`use_case ∈ {"phv_explanation" (family, existing), "phv_explanation_coach" (new)}`. Cache key unchanged (`athlete_id`, `anthropometric_record_id`, `use_case`). Prompt registry gains `phv_explanation_coach_v1`.

## 7. Frontend view-model

```text
GrowthTabProps { athlete: AthleteDetailOut; mode: "coach" | "parent"; onRecordMeasurement?: () => void }
GrowthTab state: indicator ("height_for_age" | "bmi_for_age" | "weight_for_age"), axis ("chrono" | "bio"),
                 range ("window" | "full"), detail (bool), view ("chart" | "table")
Queries: ["athlete", id] · ["anthropometry", id] · ["growth-summary", id] · ["ai", "phv", id, audience]
```

State transitions: `indicator` defaults to `height_for_age`; `weight_for_age` is only offered when `athlete.age_decimal ≤ 10`; `axis` resets to `chrono` when `indicator === "bmi_for_age"` (no PHV axis for BMI) or `mode === "parent"`; `view` is independent of the others.
