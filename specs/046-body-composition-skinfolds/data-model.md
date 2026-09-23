# Data model — Body composition by skinfolds (feature 046)

## 1. `skinfold_measurements` (new table)

One row per anthropometric record that has a skinfold set. Absent row = no skinfolds taken for that evaluation (the case for every historical record).

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INT PK autoincrement | no | |
| `anthropometric_record_id` | INT FK → `anthropometric_records.id` ON DELETE CASCADE, **UNIQUE** | no | 1:1 |
| `athlete_id` | INT FK → `athletes.id` | no | denormalised for trend queries; must equal the record's athlete (validated in service) |
| `triceps_mm`, `biceps_mm`, `subscapular_mm`, `medial_calf_mm`, `iliac_crest_mm`, `supraspinale_mm` | NUMERIC(4,1) | yes | site value (mean of 2 / median of 3), NULL when declined |
| `triceps_declined`, … `supraspinale_declined` | BOOLEAN default false | no | explicit per-site decline |
| `triceps_readings`, … `supraspinale_readings` | JSON | yes | raw readings `[r1, r2]` or `[r1, r2, r3]`, NULL when declined |
| `sum4_mm` | NUMERIC(5,1) | yes | triceps + biceps + subscapular + medial_calf; NULL if any of the four is declined |
| `sum6_mm` | NUMERIC(5,1) | yes | all six; NULL if any is declined |
| `body_fat_pct` | NUMERIC(4,1) | yes | Slaughter TC; NULL if triceps or medial_calf declined |
| `fat_mass_kg` | NUMERIC(5,2) | yes | weight × pct / 100 |
| `fat_free_mass_kg` | NUMERIC(5,2) | yes | weight − fat_mass |
| `equation_version` | VARCHAR(32) | yes | `slaughter_tc_1988_v1`; NULL when no estimate |
| `protocol_version` | VARCHAR(16) | no | `v1` (six sites, tolerance rule max(5 %, 1 mm)) |
| `caliper_model` | VARCHAR(32) | no | `slim_guide` (default; other values allowed for future calipers) |
| `measured_by` | INT FK → `users.id` | no | coach/admin who saved the set |
| `created_at`, `updated_at`, `created_by`, `updated_by` | mixin | | same `ActorTimestampMixin` as `anthropometric_records` |

Indexes: unique on `anthropometric_record_id`; index on `(athlete_id)`.

Invariants (enforced in `services/body_composition.py`, tested):
- For every site exactly one of: `declined = true` (then `_mm` and `_readings` NULL) or `readings` has 2–3 values in `[2.0, 60.0]` mm and `_mm` equals the computed site value.
- `sum4_mm` is present iff the four backbone sites have values; `sum6_mm` iff all six.
- `body_fat_pct` present iff triceps and medial_calf have values; then `fat_mass_kg` and `fat_free_mass_kg` derive from the parent record's `weight_kg` at the time of the last write; a weight correction on the record triggers recomputation of the three fields (service hook on record update).
- The athlete's age at the record's `evaluation_date` is ≥ `BODY_COMP_MIN_AGE_YEARS` (9).

## 2. Relationship changes

- `AnthropometricRecord.skinfolds: Mapped[SkinfoldMeasurement | None]` (`uselist=False`, `cascade="all, delete-orphan"`), eager-loaded with `selectinload` on the list endpoint and on the growth-summary latest/previous records.
- `SkinfoldMeasurement.record` back-reference.

## 3. Enum extensions on `growth_reference_lms`

| Enum | Existing values | Added |
|---|---|---|
| `GrowthSource` (`source`) | `WHO`, `CDC` | `FUPRECOL` |
| `GrowthIndicator` (`indicator`) | `height_for_age`, `weight_for_age`, `bmi_for_age` | `triceps_skinfold_for_age`, `subscapular_skinfold_for_age`, `triceps_subscapular_sum_for_age` |

Seed rows: source `FUPRECOL`, sex `M`/`F`, `age_months` ∈ {114, 126, …, 210} (band midpoints for 9–9.9 … 17–17.9), `L`, `M` (= P50), `S` from the article's tables. Provenance in `app/data/fuprecol_lms/README.md` (citation, DOI, licence CC BY 4.0, Holtain caliper, **left side**, Bogotá schoolchildren n = 9 618).

MySQL: both columns are `ENUM`; the migration `ALTER TABLE growth_reference_lms MODIFY COLUMN source ENUM(...)`/`indicator ENUM(...)` (via `op.alter_column(..., type_=sa.Enum(..., name=...), existing_type=...)`), and the downgrade deletes `FUPRECOL` rows first, then shrinks the enums. SQLite (tests): `Enum` maps to VARCHAR without constraint; no alter needed. The mapped enums use `values_callable=lambda e: [x.value for x in e]` like the existing ones.

## 4. Settings

| Setting | Default | Used by |
|---|---|---|
| `BODY_COMP_MDC_SUM4_MM` | 7.0 | delta classifier (Σ4) |
| `BODY_COMP_MDC_SUM6_MM` | 10.0 | delta classifier (Σ6) |
| `BODY_COMP_MIN_INTERVAL_DAYS` | 90 | interval rule, next-due |
| `BODY_COMP_MIN_AGE_YEARS` | 9 | capture gate |
| `AI_ANTHRO_PROMPT_VERSION` | `v2` (allowed: `v1`, `v2`) | prompt loader |

Constants (service + frontend mirror, shared fixtures): reading tolerance = max(0.05 × mean, 1.0 mm); plausible ranges per site by age band (soft warning only): triceps 4–30, biceps 2–20, subscapular 4–30, medial calf 4–30, iliac crest 4–40, supraspinale 3–35 mm for 9–12 y; upper bounds +10 mm for 13–17 y.

## 5. Derived (never stored): `BodyCompositionReading`

Built by `services/body_composition.py::build_reading(latest_set, previous_set, latest_record, previous_record, velocity, reference_context, settings)`.

| Field | Values | Source |
|---|---|---|
| `sets_count` | int | sets with at least one non-declined site |
| `sum4_change_mm`, `sum6_change_mm` | float or null | latest − previous (same sum present in both) |
| `sum_change_code` | `none` \| `within_noise` \| `up_real` \| `down_real` | Σ4 vs `BODY_COMP_MDC_SUM4_MM` (Σ6 informative only) |
| `weight_change_code` | `up` \| `flat_or_down` \| `unavailable` | Δweight ≥ +1.5 kg → `up` (reuses `DELTA_WEIGHT_SIGNIFICANT_KG`) |
| `height_growth_code` | `growing` \| `stalled` \| `unavailable` | Δheight ≥ 0.7 cm between the two records → `growing` |
| `velocity_code` | `within_or_above` \| `below` \| `unavailable` | `GrowthVelocity` vs `get_expected_velocity_range(stage, sex)` |
| `bmi_z_change_code` | `ok` \| `drop_moderate` (−1.0 < Δz ≤ −0.5) \| `drop_large` (Δz ≤ −1.0) \| `unavailable` | stored `bmi_z_score` of both records |
| `reference_triceps`, `reference_subscapular` | `{percentile, code}` with code `low_extreme` (< P5) \| `low` (P5–P10) \| `normal` \| `high` (P85–P95) \| `high_extreme` (≥ P95) \| `unavailable` | FUPRECOL |
| `ffm_trend_code` | `up` \| `flat` \| `down` \| `unavailable` | Δfat_free_mass ≥ +1.0 kg / ≤ −1.0 kg |
| `sites_declined_count` | int | latest set |
| `band` | `verde` \| `ambar` \| `rojo` | rules in `contracts/body-composition-reading.md` |
| `band_reason_code` | enum (see contract) | drives Spanish sentences for coach, family and AI |
| `legs_missing` | list of `weight` \| `height` \| `velocity` \| `bmi_z` \| `reference` \| `previous_set` | |
| `next_due_date`, `days_until_due` | date, int | latest counted set + 90 days |

## 6. Read models

- `SkinfoldSetOut` (coach/admin): every column of §1 plus `needs_third_reading_unconfirmed: list[site]` (sites with two readings beyond tolerance).
- `BodyCompositionOut` (coach/admin): `athlete_id`, `sets: list[SkinfoldSetOut]` (ascending by evaluation date), `reading: BodyCompositionReading`, `series: {sum4: [{date, value}], sum6: [...], per_site: {site: [...]}}`, `estimates_latest: {body_fat_pct, fat_mass_kg, fat_free_mass_kg, equation_version, margin_pct: 4}`.
- `BodyCompositionSummary` (in `GrowthSummaryOut.body_composition`, both roles): `has_data`, `latest_set_date`, `band`, `family_label`, `family_sentence`, `next_due_date`, `days_until_due`; **coach/admin only** additional fields `coach_reason`, `sum4_mm`, `sum4_change_mm`, `sum_change_code`, `sum6_mm`, `body_fat_pct`, `fat_free_mass_kg`, `legs_missing`. For parents those fields are omitted (schema `BodyCompositionFamilySummary`), never nulled-but-present.
- `AnthropometryOut.skinfolds: SkinfoldSetOut | None` — `None` for parents.

## 7. State transitions

```
record saved (no skinfolds)
   └─ PUT skinfolds (age ≥ 9, interval ok) ──▶ set present ──▶ PUT again (replace) ──▶ set present
                                                   └─ DELETE ──▶ no skinfolds
record deleted ──▶ set deleted (cascade)
record weight corrected ──▶ estimates recomputed (same set)
```

Interval check applies only to a `PUT` on a record that has **no** set yet; replacing an existing set is always allowed.

## 8. Migration checklist

1. `alembic heads` → exactly one head (`b4e8d2f61a93` at planning time).
2. New revision: create `skinfold_measurements` (batch mode for SQLite parity), indexes, FKs; alter the two enums on MySQL (guarded by dialect check); no `server_default` beyond booleans and `protocol_version`/`caliper_model` literals.
3. Downgrade: drop table; delete `FUPRECOL` rows; shrink enums (MySQL only).
4. Seed: `seed_growth_data.py` gains the FUPRECOL entries; `entrypoint.sh` unchanged (it already calls the seed).
5. Verify with `pytest -m mysql` (upgrade → seed → downgrade → upgrade).
