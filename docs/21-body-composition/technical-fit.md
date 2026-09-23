# Body composition (skinfolds) — Technical fit analysis

**Status**: read-only research, no code/schema/migration changes made.
**Scope**: backend + frontend fit for adding skinfold-based body composition to the
existing anthropometry module. Science (equation choice, site protocol) and UX
(family-facing framing of %BF) are being decided in parallel; this document
assumes the feature shape given in the brief and flags every point where a
science/UX decision changes the technical answer.
**Repo state referenced**: `main` @ `0e2c8ed`, `backend/` venv, `alembic heads` →
single head `b4e8d2f61a93` (59 migrations), `ruff check` clean on the touched
modules. Date: 2026-09-23.

---

## 1. Current module map

| Layer | File(s) | Relevant shape |
|---|---|---|
| Models | `app/models/anthropometry.py` — `AnthropometricRecord` (L48-104), `MaturationStatus` (L28-31), `NutritionalStatus` (L34-45) | One flat, wide table: raw measurements + Mirwald PHV fields (`leg_sitting_ratio`, `maturity_offset`, `age_at_phv`, `maturation_status`) + 8 nullable percentile/z-score columns (L76-92) added in feature 040, tagged with `growth_source` for versioning |
| Models | `app/models/growth.py` — `GrowthSource`, `GrowthIndicator` (L16-19), `GrowthReferenceLms` (L22-40) | Generic LMS table: `(source, indicator, sex, age_months) → (L, M, S)`, unique-constrained, indicator-agnostic |
| Models | `app/models/ai_explanation.py` — `AthleteAIExplanation` (L28-139) | Cache-by-`(athlete_id, anthropometric_record_id, use_case)`; 9 nullable trace columns incl. `structured_json: JSON` (L89) |
| Models | `app/models/parental_consent.py` (L17-75), `app/models/privacy_policy.py` | `ParentalConsent.anthropometry`/`third_party_sharing` bool scopes (L50-51); `PrivacyPolicy` append-only versions |
| Schemas | `app/schemas/anthropometry.py` (80 lines), `app/schemas/growth.py` (122 lines) | `AnthropometryCreate`/`Out`, `GrowthPercentiles`, `MorphologyMetrics`; `GrowthSummaryOut` with `LatestBands`, `LatestAiAnalysis` |
| Services | `app/services/growth.py` (341 l.), `growth_summary.py` (251 l.), `permissions.py`, `privacy.py`, `retention.py` | LMS math (Cole & Green), pure growth-summary derivation, RBAC helpers, consent gates, `audit_log` purge only |
| Services (AI) | `app/services/ai/anthro/{context,schemas,analyst,critic,fallback,guardrails_step,prechecks,persist,pipeline}.py` | 5-step plain orchestrator (feature 042), detailed in §6 |
| Routers | `app/routers/anthropometry.py` (301 l.), `growth.py` (235 l.), `reports.py` (PDF, L87-90) | `POST/GET .../anthropometry`, `GET growth-reference`, `GET growth-summary`, `GET` PDF report |
| Frontend | `components/athletes/AnthropometryForm.tsx`, `components/athletes/growth/*` (14 files), `hooks/athletes/use{Anthropometry,GrowthSummary}.ts` | RHF + Zod flat form; `GrowthTab.tsx` composes coach vs. parent views from `useGrowthSummary`/`useAnthropometry` |
| Tests | `backend/tests/anthro/*` (6 files), `tests/routers/test_anthropometry_bmi.py`, `tests/services/test_growth_*.py`, `tests/evals/test_anthropometry_analyst_eval.py` | Unit tests per pipeline step + a hypothesis-based privacy-seam property test |
| AI prompts/eval | `app/services/ai/anthro/prompts/anthropometry_{analyst,critic}_v1.md`, `eval/{judge,scorer}.py`, `backend/evals/anthropometry_analyst/golden/case_0??.json` (12 cases) + `baseline.json` | Golden-eval gate at composite ≥ 0.75 (`pytest -m golden`) |
| Exports | `templates/documents/pdf/anthropometry_report.html` (raw `weight_kg`/`standing_height_cm`, L55/60/70), `services/training/growth_chart_builder.py` | PDF downloadable by **both** coach and parent — see §8 |

`docs/21-body-composition/` was empty before this file.

## 2. Data model options

| | (a) Columns on `anthropometric_records` | (b) Child table `skinfold_measurements` (1:1) | (c) Normalized `skinfold_readings` rows |
|---|---|---|---|
| Raw-reading persistence | Possible but ~24 more nullable columns on an already-wide table (~25 cols today) | Contained to a new table; raw readings as `JSON` array per site (precedented: `AthleteAIExplanation.structured_json`, `ai_explanation.py:89`) or 3 explicit `Numeric` columns per site | Most literal fit — one row per raw reading, trivially recomputable |
| Explicit skip semantics | Ambiguous — NULL already means "not asked" for `arm_span_cm`; reusing it collides "not asked" with "declined" | Clean: `{site}_skipped: Boolean` alongside nullable value columns | Clean: a `skipped` row per site, but needs care to not conflate "no reading rows" with "explicitly skipped" |
| Equation versioning | `equation_version`/`caliper_model` would live once more on an already-multi-purpose table | Lives once per record on the new table — same pattern as `growth_source` on `AnthropometricRecord` (L87-92) | Would need a separate `skinfold_summary` row anyway to hold per-record equation metadata, defeating some of the normalization benefit |
| Query cost (trend charts) | Cheapest — no join | One indexed join on `anthropometric_record_id` (nullable FK, most rows have none) | Requires `GROUP BY (record_id, site)` aggregation at read time for every chart point |
| Alembic complexity | One large additive migration, `batch_alter_table` (SQLite-safe) | One new table + FK + optional Boolean/JSON/Numeric columns — same shape as recent migrations | New table + a new `Enum(SkinfoldSite, values_callable=...)` (MySQL 8.4 enum-alter gotcha, CLAUDE.md) + unique constraint on `(record_id, site, reading_no)` |
| MySQL 8.4 + aiosqlite | All types used already proven dual-dialect (`Numeric`, `Boolean`, `JSON`) | Same | Same, plus an extra enum to get `values_callable` right |
| Row volume | N/A | 1 row per record with skinfolds (most records: 0 rows) | Up to 24 rows per record (8 sites × 3 readings) — irrelevant at this club's scale (~20 athletes) but more moving parts |

**Recommendation: (b), a nullable 1:1 child table `skinfold_measurements`.** It keeps
`anthropometric_records` untouched (matches "keep the parent table's shape stable"
precedent — feature 040 already widened it once), gives explicit skip a first-class
column per site, and lets Σ/%BF/FM/FFM/`equation_version`/`caliper_model` live
together on one row that is simply absent for the ~100% of historical records and
any future record where skinfolds weren't taken. Store raw readings as a small
`JSON` array per site (reuses a type already proven in this codebase, avoids a
migration every time the protocol moves from 2 to 3 readings) and the computed
site value as an explicit `Numeric` column (cheap to query for trend charts
without unpacking JSON). Option (c) is worth revisiting only if the science team
ends up wanting a fully dynamic, unbounded site list — the brief names a fixed
core-3 + optional-5 set, so that flexibility isn't needed yet.

## 3. Computation placement

Two precedents already coexist in this codebase:

- **Persisted-at-write**: `leg_sitting_ratio`, `maturity_offset`, `age_at_phv`,
  `maturation_status` (Mirwald, computed in `routers/anthropometry.py:132-138` via
  `services/phv.py`) and all 8 percentile/z-score/BMI fields (computed
  `routers/anthropometry.py:144-157` via `services/growth.py`, tagged with
  `growth_source` so a reference-table change never silently reinterprets old rows).
- **Derived-at-read**: `services/race/course/derived.py::derive_figures` — a pure,
  dependency-free function (stdlib only) computing `distance_km`/`avg_speed_kmh`/
  `elevation_gain_m` at serialization time, never persisted (CLAUDE.md invariant).

**Recommendation: persist Σskinfolds, %BF, FM, FFM at write time** (same tier as
BMI/percentiles), for three reasons: (1) **equation versioning** — Slaughter–Lohman
coefficients depend on sex + maturation stage, and a future equation revision must
not silently recompute history; `equation_version` on the child table plays the
same role `growth_source` already plays (`anthropometry.py:87-92`, "NULL = legacy
row not yet recalculated"), and a deliberate backfill script (mirroring
`scripts/backfill_anthropometry.py`) is how old rows would ever move to a new
version — never an implicit reinterpretation; (2) the AI context builder
(`context.py`) reads already-sanitized values straight off the ORM object — a
derive-at-read step there would duplicate the Slaughter equation in two places
with drift risk; (3) the "significant vs. instrument noise" delta (mirroring
`context.py::_build_measurement_deltas`, L141-181) needs a **previous record's**
stored %BF/FFM to diff against, which only works if those values are columns, not
recomputed on demand.

**Exception — keep the coach-only traffic-light band derived at read time**, in a
pure function, not persisted. This mirrors why `NutritionalStatus` bands ARE
persisted but `GrowthSummaryAlert`s are NOT (`growth_summary.py::_build_alerts`,
L160-192, recomputed fresh from stored z-scores on every read) — a band threshold
is a tunable policy (like `GROWTH_VELOCITY_THRESHOLD`), and keeping it in a pure
classifier means a threshold tweak applies retroactively to every history view
without a backfill, the same way `classify_nutritional_status_height` is called
both at write time and again at read time for legacy rows
(`routers/anthropometry.py:101-108`).

**Where the logic should live**: a new `app/services/body_composition.py`, sibling
to `growth.py` (LMS math) and `phv.py` (Mirwald math) — same separation-of-concerns
precedent. It owns: raw-reading aggregation (median/mean), Σ3/Σ7 sums, the
Slaughter–Lohman equations gated by sex + `MaturationStatus` (already computed and
stored on the parent record, L65-67 — no new maturation input needed), FM/FFM from
`weight_kg`, and the noise-vs-significant delta classifier.

## 4. Reference LMS seeding

Highly reusable. `GrowthIndicator` (`growth.py:16-19`) has 3 values today; adding
`triceps_skinfold_for_age`/`subscapular_skinfold_for_age` is additive to the enum
(needs the same `values_callable` migration care CLAUDE.md already flags for
`MaturationStatus`). `growth_reference_lms` (`growth.py:22-40`) is already
indicator-agnostic — no schema change beyond the enum values — and
`get_lms_params`/`calculate_z_score`/`z_to_percentile`/`get_reference_curve`
(`services/growth.py:27-92, 95-108, 111-119, 257-340`) work unmodified for a new
indicator. Seed pattern to copy verbatim:
`docs/04-percentiles/003-lms-seed-and-backfill.md` — vendor the reference CSVs
under `app/data/` (sibling to `app/data/cdc_lms/`), read offline in
`app/seed_growth_data.py` (idempotent, dialect-aware upsert on the existing unique
constraint), wire into `entrypoint.sh` exactly like the current two lines.

**Open dependency on the science decision**: `calculate_z_score` implements Cole &
Green's LMS formula, which requires L/M/S parameters, not just percentile tables.
Addo & Himes (2010) and the CDC skinfold references need to be confirmed as
LMS-parameterized (or convertible) before this reuse is free; if only percentile
tables are publicly available, `get_lms_params`'s age-interpolation shell still
works but `calculate_z_score` needs a percentile-table lookup path instead — a
materially different, still small, addition.

Frontend: `GET /growth-reference` (`routers/growth.py:60-111`) already takes
`indicator`/`sex`/`source`/age range and returns banded `CurvePoint`s; the two new
indicator values are a pure enum extension on both ends, feeding the existing
`PercentileChart.tsx` the same way `NutritionalClassification.tsx` does today.

## 5. API surface

**Extend the existing payload, don't add a sub-resource.** Add an optional nested
`skinfolds` object to `AnthropometryCreate`/`AnthropometryOut`
(`schemas/anthropometry.py:9-22, 47-80`) on the same
`POST/GET /api/athletes/{id}/anthropometry` — one coach visit captures weight,
height, and skinfolds together, and the existing audit call
(`routers/anthropometry.py:206-215`) should cover all of it in one transaction. A
separate sub-resource only makes sense if skinfolds were captured asynchronously,
which the brief doesn't indicate.

- **`growth-summary` extension**: add an optional `body_composition` block to
  `GrowthSummaryOut` (`schemas/growth.py:106-121`), populated the same read-only,
  non-recomputing way `LatestBands` already is (`growth_summary.py:79-104`) —
  `None` whenever the latest record has no skinfold row.
- **Parent-filtered reads**: extend the existing
  `if current_user.role == UserRole.parent: out.notes = None; out.morphology = None`
  block (`routers/anthropometry.py:294-297`) with whatever the science/UX call on
  %BF visibility turns out to be. Raw skinfold mm values likely follow the existing
  precedent that raw weight/height **are** parent-visible today, both in the list
  endpoint and in the PDF (`routers/reports.py:87-90` has no role gate beyond
  `verify_athlete_access`) — %BF is the one field that needs an explicit product
  call, since it reads as a more sensitive, body-image-adjacent number than cm/kg.
- **Validation**: today `schemas/anthropometry.py:9-22`'s `AnthropometryCreate` has
  **no** numeric range validation at all — only a `field_validator` rejecting a
  future `evaluation_date` (L17-22); weight/height min-max ranges exist only in
  the frontend Zod schema (`AnthropometryForm.tsx:17-18`, `z.number().min().max()`).
  The new skinfold sub-schema should add `Field(ge=..., le=...)` for plausible mm
  ranges per site directly in Pydantic — a genuinely new pattern for this file, not
  a mirror of an existing backend precedent — plus a validator rejecting
  "0 readings and not skipped" as an inconsistent state.
- **Denied-path tests required** (constitution Principle II, non-negotiable):
  parent POSTing skinfolds → 403 (mirrors `require_role([admin, coach])`,
  `routers/anthropometry.py:122`); coach of another club → 403 via
  `verify_athlete_access`; parent GET for a non-linked athlete → 403/404 (existing
  behavior); a body-composition-specific assertion added to
  `tests/routers/test_anthropometry_bmi.py`'s sibling rather than a new mechanism.

## 6. AI pipeline extension

The feature-042 pipeline (`context → analyst → prechecks R01–R12 → critic →
[≤1 reanalysis] → guardrails_step → persist`, orchestrated in
`app/services/ai/anthro/pipeline.py`) is built for exactly this kind of additive
block:

- **Context**: add a `body_composition: dict | None` leaf to `AnalysisContext`
  (`context.py:80-95`), built by a new `_build_body_composition_dict()` mirroring
  `_build_growth_summary_dict()` (L184-209) — **qualitative codes only**
  (`skinfold_sum_band`, `ffm_trend_direction`, `sites_skipped_count`), never a raw
  mm value or a %BF number, matching the rule already documented at L185
  ("solo códigos cualitativos — nunca z-score/percentil/valor crudo"). Add a
  matching `_render_body_composition_block()` (sibling to the 5 renderers at
  L302-401) threaded into `context_blocks` (L486-493).
- **Allow-list**: add the new leaf keys to
  `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS`
  (`app/services/ai/context_builders.py:393-441`) — this frozenset is the single
  choke point `sanitize_insight_context()` enforces; a missed key is a silent drop,
  not a leak, so this is the one edit that matters most for privacy here.
- **Prompts**: `anthropometry_{analyst,critic}_v1.md` need a new optional block
  (rendered only when skinfolds exist for the record, same pattern as
  `training_load_block`) and an explicit rule that %BF/raw-mm are never stated as
  a number to a family audience.
- **New precheck R13** (rather than folding into R12): reuse the exact pattern of
  `check_r12_coach_only_leak_to_family` (`prechecks.py:527-551`,
  `must_block=True`) for a body-fat-percentage-number-in-family-text regex —
  keeps the rule catalog one-rule-one-concern, matching how R01/R02/.../R12 are
  each a single regex/cross-check.
- **Schema**: `AnthropometryInsightV1` (`schemas.py:69-94`) likely needs no new
  fields — body-composition commentary folds into the existing `changes`/`meaning`
  lists, inside the current 180/110-word family/coach budgets (`schemas.py:145-148`).
- **Fake-provider / privacy tests**: extend `tests/anthro/test_privacy_seam.py`'s
  4 hypothesis properties with a 5th — no raw mm or %BF number ever reaches a
  rendered family-audience prompt — using the same technique (call the private
  per-block renderer directly on adversarial synthetic leaves).
- **Golden eval**: `backend/evals/anthropometry_analyst/golden/case_0??.json` (12
  cases, schema per `case_001.json`) needs cases with a `body_composition` input
  leaf and an extended `forbidden_terms` list; `baseline.json` will need a fresh
  run once prompts change. Budget real iteration time here — per prior work on
  this same pipeline (`feature-042-traceable-growth-ai` memory), ~10/12 golden
  cases already trip a `must_block` precheck on the first analyst attempt today,
  so a new rule (R13) landing on top of that fallback rate is a real risk, not
  just plumbing.

## 7. Frontend

- **Form**: `AnthropometryForm.tsx`'s flat `anthropometrySchema` (L12-24) already
  has one optional-nullable numeric field (`arm_span_cm`) as precedent. Extend
  with a nested optional `skinfolds` object where each site is a discriminated
  shape — `{ readings: number[2-3] }` **or** `{ skipped: true }` — so "explicitly
  declined" is a first-class Zod variant, not an empty field, at the form layer
  too, not just the DB layer.
- **Query invalidation**: `useCreateAnthropometry`'s `onSuccess`
  (`hooks/athletes/useAnthropometry.ts`) invalidates `["anthropometry", id]`,
  `["athlete", id]`, `["ai","phv",id]` — **not** `["growth-summary", id]`, a
  pre-existing gap this feature should close, since any new body-comp band would
  hang off the same POST.
- **Local persistence**: `useGrowthSummary`'s doc comment flags its query key as
  deliberately excluded from `persistAllowList.ts` (default-deny) because the
  payload carries a minor's Z-scores/bands — any new body-composition query key
  must simply never be added to that allowlist (the safe state is "not listed").
- **Charts**: `Sparkline.tsx`/`PercentileChart.tsx` (`components/athletes/growth/`)
  are already generic; a Σskinfold/FFM trend is a personal-history line (no
  population curve) and should reuse `Sparkline.tsx`, while per-site skinfold
  percentile curves (once §4 ships) reuse `PercentileChart.tsx` unchanged.
- **Family view**: `FamilyBandCards.tsx`/`FamilyStageCard.tsx` already show bands
  without numerals — a family body-comp card should follow the same convention
  pending the %BF-visibility product call.
- **Tests**: vitest for the new Zod schema/skip-state UI (mirrors
  `AnthropometryForm.test.tsx`), `jest-axe` on any new card (constitution
  Principle III, zero violations required), MSW handlers for the extended POST
  and the two new `growth-reference` indicator values.

## 8. Privacy & compliance checklist

- **Consent**: `ParentalConsent.anthropometry` (`parental_consent.py:50`) already
  exists — reuse it, don't add a new scope; skinfolds are more anthropometry data,
  not a new category. `third_party_sharing` (L51) already gates all AI processing
  via `athlete_has_ai_processing_consent` (`privacy.py:106-139`), so the
  body-composition AI block inherits this gate for free. A privacy-policy version
  bump (`is_policy_version_in_force`, `privacy.py:58-75`) is warranted only if
  %BF language needs explicit disclosure in the policy text — a product decision,
  not a technical blocker.
- **Logs/errors**: every module in the existing pipeline enforces "generic rule
  name only, never the value" (`prechecks.py:45-49`, `persist.py:69-74`); new code
  must follow the same convention — no raw mm, no %BF number in any
  `logger.warning`/`HTTPException.detail`.
- **Fixtures**: synthetic only (matches `test_privacy_seam.py`'s own docstring
  and the project-wide rule against real minor data in git).
- **Exports/PDF — the one real gap to close explicitly**:
  `templates/documents/pdf/anthropometry_report.html` already renders raw
  `weight_kg`/`standing_height_cm` (L55/60/70) and is downloadable by **both**
  coach and parent (`routers/reports.py:87-90` has no role gate beyond
  `verify_athlete_access`). If skinfolds/%BF are added to this template — or to
  `services/training/growth_chart_builder.py`, which feeds the monthly report —
  whatever family-visibility rule is decided for the JSON API **must** be applied
  here too, or the PDF becomes a silent bypass of it.
- **Strava**: no overlap, unaffected.
- **Retention**: `services/retention.py` purges only `audit_log` at 24 months
  (L59); `anthropometric_records`/`athlete_ai_explanations` have no purge job
  today. Skinfold data introduces no *new* retention gap beyond the one that
  already exists for the rest of anthropometry — worth a one-line note in the
  eventual spec, not a blocker.

## 9. Migration & ops

`alembic heads` (run from `backend/`, venv active) returns a single head,
`b4e8d2f61a93`, across 59 migrations — clean starting point. Model the new
migration on `686ce1d873f3_ai_explanations_traceability.py`: purely additive,
nullable columns/table, `batch_alter_table` (required for the SQLite test lane,
not just MySQL), no `server_default`, symmetric `downgrade()`. Any new DB enum
(a skinfold-site enum, if option (c) were chosen; the two new `GrowthIndicator`
values either way) must use `values_callable=lambda e: [x.value for x in e]`,
exactly like `MaturationStatus`/`NutritionalStatus`/`GrowthSource` already do
(`anthropometry.py:66,84,90-91`) — CLAUDE.md calls this out as a known footgun.
`downgrade()` correctness is only actually exercised under `pytest -m mysql`,
deferred here (no MySQL in this session). No Render-specific risk: additive
nullable columns/tables are zero-downtime, and `entrypoint.sh` already runs
`alembic upgrade head` before serving. No backfill needed — this is 100% new,
optional data; existing records simply have no skinfold row, the same non-event
as `arm_span_cm` being NULL today.

## 10. Effort estimate

| Wave | Scope | Size | Main risk |
|---|---|---|---|
| W1 | `skinfold_measurements` model + migration, `body_composition.py` service (aggregation + Slaughter equations + band classifier), unit tests | M | Equation/site choice not yet final (science) |
| W2 | API: extend create/list schemas + router, `growth-summary` extension, RBAC denied-path tests | S–M | %BF family-visibility rule not yet final (UX) |
| W3 | Frontend: form extension (skip-state Zod), history/detail display, query invalidation fix | M | None significant — well-precedented patterns |
| W4 | Charts (Σ/FFM trend, site percentile curves) + LMS seed for 2 new indicators + family cards | M | LMS-vs-percentile-table availability for Addo & Himes/CDC skinfold refs (science) |
| W5 | AI pipeline: context leaf, prompt blocks, R13 precheck, allow-list, golden-eval cases, privacy-seam property #5, `data-privacy-guard` audit | L | Existing ~83% first-attempt `must_block` rate on this pipeline (memory: feature 042) means a new rule risks pushing more runs to fallback — plan for prompt iteration, not just plumbing |

Sequencing follows feature 042's own pattern (backend model/service → API/tests →
frontend capture → charts/family/AI → docs/privacy audit). W1–W3 have no
dependency on the still-open science/UX decisions and can start immediately; W4
depends on confirming an LMS parameterization for the skinfold references, and W5
depends on the family %BF-visibility call — both are explicitly out of scope for
this document and owned by the parallel research tracks.
