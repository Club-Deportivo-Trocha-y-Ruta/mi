# Contract — analysis context (allow-list, thresholds, compaction)

**Module**: `backend/app/services/ai/context_builders.py` (existing file, extended — LD-2/plan.md
Project Structure) — new constant `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS`, new builder
function(s), alongside the untouched `ATHLETE_CONTEXT_ALLOWED_KEYS` / `AthleteAIContextBuilder`
that the legacy prose use cases still use during the transition.
**Consumer**: `backend/app/services/ai/anthro/context.py` (step 1 of the pipeline).
**Related contracts**: `insight-schema.md` (what the analyst returns), `measurement-analysis-api.md`
(who calls step 1), `data-model.md` §2.2 (`AnalysisContext` shape).
**Source**: prompt-design agent's design note §1, reconciled with the actual code in
`context_builders.py` (read at planning time — thresholds and privacy rounding already exist and
are reused, not reinvented) and with the lead's `schema_version` renaming (§2.6 below corrects
that design note's draft wording).

---

## 0. Relationship to the existing allow-list

`ATHLETE_CONTEXT_ALLOWED_KEYS` (`context_builders.py:111-142`) stays exactly as it is — it still
serves `PHVExplainerUseCase` and `AnthropometricRecordExplainerUseCase` for as long as any code
path can still construct them (there is none once W2 deletes both, but the constant is not
deleted with them; it remains the historical record of what the pre-042 prompts were allowed to
see, and nothing currently forbids a future use case from reusing it).

`ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS` is a **new, separate, closed** frozenset. It is a
superset in spirit (it carries everything the old allow-list did, plus the new longitudinal,
growth-summary and training-load fields) but is declared independently rather than by extending
the old one, so a future prompt-registry cleanup that prunes `ATHLETE_CONTEXT_ALLOWED_KEYS` can
never accidentally narrow what the anthropometry pipeline is allowed to see. Same `_sanitize()`
silently-drop pattern as the existing builder (`context_builders.py:373-379`): a key produced by
the builder that is not on the list is dropped before it reaches Jinja, never raises.

## 1. Thresholds (existing, reused verbatim — never redefine)

| Constant | Value | Source | Meaning |
|---|---|---|---|
| `DELTA_HEIGHT_SIGNIFICANT_CM` | `0.7` | `context_builders.py:26` | Below this, a height delta is instrument noise. |
| `DELTA_WEIGHT_SIGNIFICANT_KG` | `1.5` | `context_builders.py:27` | Idem, weight. |
| `MIN_WEEKS_FOR_VELOCITY` | `8` | `context_builders.py:29` | Floor below which `growth_velocity_cm_per_year` is not computed at all (unchanged by this feature — FR-004). |
| `VELOCITY_RELIABLE_WEEKS` | `26` **(new)** | this feature, `context_builders.py` | At or above this interval, a computed velocity is labelled `"reliable"`; between the two floors it is `"early_signal"` (FR-004, lead ruling 8). Clinical-monitoring precedent for the six-month floor is recorded in `docs/01-marco-teorico.md` §1's new subsection (User Story 5, spec.md:102). |
| `HISTORY_MAX_POINTS` | `16` **(new)** | this feature | Above this many measurements, the oldest are compacted into yearly checkpoints rather than dropped (Edge Case spec.md:126) — a token-budget valve, not a scope cut. |

## 2. Full context key list

Every key below is (a) on `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS`, (b) produced by a pure
function of already-loaded SQLAlchemy instances (no new query pattern beyond what §2.5 lists), and
(c) either directly rendered into one of the five Jinja blocks or consumed only by
`prechecks.py`/`guardrails_step.py` (never reaching the prompt).

### 2.1 Identity — unchanged from the existing builder

| Key | Type | Nullable | Derivation |
|---|---|---|---|
| `age_decimal` | `float`, 1 dp | no | `compute_age_decimal(athlete.birth_date, today)` — same rounding as `context_builders.py:222`. |
| `age_group` | `"10-12"\|"13-15"\|"16+"` | no | `_age_group()`, `context_builders.py:162-167`. |
| `sex` | `"M"\|"F"` | no | `athlete.sex.value`. |
| `category` | `str` (FCC code) | no | `get_category(athlete.birth_date.year, athlete.sex.value)`. |
| `audience` | `"family"\|"coach"` | no | Request query param — not athlete-derived, added to the allow-list as a plain string (not sensitive on its own). |

### 2.2 `measurement_deltas` (target vs the immediately previous record; `null` on a first measurement)

| Key | Type | Nullable | Derivation / min-data condition |
|---|---|---|---|
| `weeks_since_prev_measurement` | `int` | yes | `null` iff no prior record exists. |
| `delta_height_cm` | `float`, 1 dp | yes | idem. |
| `delta_weight_kg` | `float`, 1 dp | yes | idem. |
| `delta_height_significant` | `bool` | no (when deltas exist) | `abs(delta_height_cm) >= DELTA_HEIGHT_SIGNIFICANT_CM`. |
| `delta_weight_significant` | `bool` | no (when deltas exist) | `abs(delta_weight_kg) >= DELTA_WEIGHT_SIGNIFICANT_KG`. |
| `growth_velocity_cm_per_year` | `float`, 1 dp | yes | `null` unless `weeks_since_prev_measurement >= MIN_WEEKS_FOR_VELOCITY (8)`. |
| `velocity_confidence` | `"reliable"\|"early_signal"\|null` | yes | `null` iff `growth_velocity_cm_per_year` is `null`; `"reliable"` iff `weeks_since_prev_measurement >= VELOCITY_RELIABLE_WEEKS (26)`; `"early_signal"` for `8 <= weeks < 26`. |
| `crossed_phv_phase` | `bool` | no (when deltas exist) | `previous.maturation_status != target.maturation_status`. |
| `prev_maturation_status` | `str` | yes | The immediately previous record's `maturation_status.value`. |
| `phase_crossing_corroborated` | `bool` | no (when deltas exist) | `true` only if **the record before the previous one** shows the same phase as `prev_maturation_status` **and** the interval between that record and the previous one covers the stage's re-test interval (the existing `MEASUREMENT_INTERVALS` constant — 30/90/120 days — verify exact module at implementation time, likely `app/schemas/alerts.py` or a sibling `measurement_alerts` module). Encodes FR-005 as data, never as an LLM judgement call. |

### 2.3 `longitudinal_series` (full history, compact)

| Key (per point) | Type | Notes |
|---|---|---|
| `weeks_offset_from_latest` | `int` | Never an absolute date — same privacy pattern as the existing `trend.weeks_ago` (`context_builders.py:149`). |
| `height_cm` | `float`, 1 dp | |
| `weight_kg` | `float`, 1 dp | |
| `maturation_status_at_point` | `str` | |
| `delta_height_cm_from_prior_point` | `float`, 1 dp | `null` on the oldest point in the (possibly compacted) series. |

**Compaction rule** (`HISTORY_MAX_POINTS = 16`): once a history exceeds 16 records, the most
recent 15 stay per-point and everything older collapses into one synthetic checkpoint per
calendar year (average height/weight, the maturation status most represented that year), each
still expressed only as `weeks_offset_from_latest`. **Excluded per point, always**:
`sitting_height_cm`, `arm_span_cm` (only the *latest* record's `arm_span_cm` is carried, as a
top-level key outside this list, mirroring the existing builder's single-value treatment,
`context_builders.py:291-294`), any absolute date.

### 2.4 `growth_summary` (qualitative codes only, from `build_growth_summary()` — feature 040)

| Key | Type | Derivation | Privacy note |
|---|---|---|---|
| `stage` | `str \| null` | `GrowthSummaryOut.stage.value` | |
| `maturity_offset` | `float, 1dp \| null` | idem, existing rounding | Same 1-dp privacy rounding already applied for the legacy PHV prompts (`context_builders.py:229-233`) — not widened. |
| `age_at_phv` | `float, 1dp \| null` | idem | idem. |
| `months_from_phv` | `int \| null` | idem | idem. |
| `expected_velocity_range_cm_year` | `tuple[float, float]` | `GrowthSummaryOut.velocity.expected_cm_per_year` (`backend/app/schemas/growth.py:51`) | **The only source** the analyst may cite for a velocity anchor (FR-007, lead ruling 8) — replaces the prompt-embedded Circa-PHV anchors the audit found stale. Never the prompt's own literal. |
| `height_band` | `str` (band code) | `.band.value` of `LatestBands.height` | Never `.z_score`/`.percentile`/`.value` — same exclusion `context_builders.py:277-281` already documents for the legacy prompt. |
| `weight_band` | `str` (band code) | `.band.value` of `LatestBands.weight` | idem. |
| `nutritional_status` | `str` (band code) | `.band.value` of `LatestBands.bmi` | idem — qualitative only, matching the existing `nutritional_status` key. |
| `alerts` | `list[str]` (codes) | `GrowthSummaryOut.alerts`, `GrowthSummaryAlert` values | The family Jinja block must never render a code verbatim (FR-008) — codes reach the *coach* block as-is; the family block's conditional text only ever says "el entrenador lo seguirá", never the code name. |
| `measurement_due_status` | `str` | `GrowthSummaryOut.measurement.status.value` | |

### 2.5 `training_load_window` (last 28 days, three fields only)

| Key | Type | Nullable |
|---|---|---|
| `sessions_count_28d` | `int` | no (0 when none) |
| `avg_rpe_28d` | `float, 1dp` | yes |
| `hours_28d` | `float, 1dp` | yes |

Reuses `app.services.race.ai.athlete_context.load_training_window(db, athlete_id, club_id,
date_from, date_to)` verbatim (already club-scoped, already tested, already excludes archived
rows) — a cross-module import from `app/services/ai/anthro/context.py` into `race/ai/
athlete_context.py`. This is the one place the anthropometry pipeline imports from the race
package; it is a pure aggregation query with no race-specific config coupling, so it does not
violate the one-way `AI_*`/`RACE_AI_*` inheritance rule (`contracts/config-env.md` §0). If `None`
is returned (no session table access, defensive), all three fields degrade to `null`/`0` and
`"sin datos de entrenamiento en las últimas 4 semanas"` is added to `data_gaps` by the analyst
per the prompt's `SIN DATO` branch — never synthesised by the context builder itself.

### 2.6 `previous_analysis` (the athlete's own last **structured** insight, if any)

| Key | Type | Nullable |
|---|---|---|
| `insight_schema_version` | `"v1"` (the insight-payload version, `data-model.md` §0) | no (when present) |
| `summary_line` | `str` | no |
| `confidence_level` | `"high"\|"medium"\|"low"` | no |
| `weeks_since` | `int` | no — never an absolute date |

**Correction to the prompt-design note's draft wording**: that note, written before the lead's
ruling fixed the DB discriminator's naming, says "only included if a `schema_version=='v1'` row
exists" — referring to what became `AthleteAIExplanation.schema_version`. Under the shipped
naming (`data-model.md` §1), the lookup is:

```python
select(AthleteAIExplanation)
    .where(
        AthleteAIExplanation.athlete_id == athlete.id,
        AthleteAIExplanation.use_case == use_case,
        AthleteAIExplanation.schema_version == "v2",   # structured rows only
    )
    .order_by(AthleteAIExplanation.generated_at.desc())
    .limit(1)
```

Legacy free-prose rows (`schema_version IS NULL`) are **never** read as `previous_analysis` — a
free-prose row has no `summary_line`/`confidence` to extract, and the point of this field is
continuity between two *structured* generations (FR-010, "a new analysis must not repeat the
previous one's summary line verbatim"). The very first structured analysis for an athlete
therefore always has `previous_analysis = null`, even if the athlete has years of legacy prose
history — that history is still visible to the analyst through `longitudinal_series` (§2.3),
which is numeric-history-based and version-agnostic.

## 3. Forbidden, explicitly (defense in depth beyond "not on the allow-list")

Never on `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS`, and covered by the `data-privacy-guard`
audit checklist for this feature:

- `height_z_score`, `weight_z_score`, any percentile, any raw band numeric value (`BandReading.
  value`) — only `.band.value` qualitative codes travel, per §2.4.
- Any absolute date (`evaluation_date`, `birth_date`, `created_at`) anywhere in the context —
  every temporal fact is a relative offset in weeks.
- `sitting_height_cm` per longitudinal point (§2.3) — only the latest `arm_span_cm` survives, as
  today.
- Coach free text (`training_implications`) beyond what `_sanitize_training_implications()`
  already produces (`context_builders.py:70-106`) — the anthropometry context reuses that same
  sanitizer unchanged; it does not get a laxer or stricter version for this feature.
- Athlete name, parent name, email, phone, any identifier other than the internal integer ids
  used for the DB lookup itself (which never reach the prompt).

## 4. Tests

- `test_context_allowlist_snapshot` — `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS` equals a fixed,
  reviewed literal set (same pattern as `test_ai_context_builder_privacy.py`'s existing assertion
  for the legacy allow-list).
- `test_velocity_confidence_boundaries` — table-driven over `weeks_since_prev_measurement in {0, 7,
  8, 25, 26, 27}` asserting the exact `null`/`early_signal`/`reliable` transition.
- `test_phase_crossing_corroboration_requires_two_prior_records` — a borderline single-reading
  crossing never sets `phase_crossing_corroborated=true`.
- `test_history_compaction_above_16_points` — a 20-record fixture asserts exactly 15 per-point
  entries plus yearly checkpoints for the remainder, and that no checkpoint carries an absolute
  date.
- `test_previous_insight_skips_legacy_rows` — a fixture with one legacy (`schema_version=NULL`)
  row and no `"v2"` row asserts `previous_analysis is None`.
- Property test (hypothesis, reusing the existing sentinel pattern): for any generated context,
  none of `height_z_score`, `weight_z_score`, `percentile`, `sitting_height_cm`, `birth_date`
  appears as a key or substring of a rendered prompt block.
