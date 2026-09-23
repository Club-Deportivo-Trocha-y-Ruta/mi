# Research — Body composition by skinfolds (feature 046)

Phase 0 output. Every unknown in the plan's Technical Context is resolved below. The scientific and product evidence lives in `docs/21-body-composition/` (`research-protocol.md`, `research-safeguards-referral.md`, `research-measurer-ux.md`, `technical-fit.md`, `proposal.md`); this file records the engineering decisions taken on top of it, with rationale and alternatives.

## R1 — Data model: 1:1 child table with fixed site columns

- **Decision**: new table `skinfold_measurements`, one row per anthropometric record that has skinfolds (`anthropometric_record_id` unique FK, `ondelete=CASCADE`), with fixed columns per site (`{site}_mm`, `{site}_declined`, `{site}_readings` JSON) for the six sites, plus computed columns (`sum4_mm`, `sum6_mm`, `body_fat_pct`, `fat_mass_kg`, `fat_free_mass_kg`), `equation_version`, `protocol_version`, `caliper_model`, and the actor/timestamp mixin used by `anthropometric_records` since feature 041.
- **Rationale**: keeps the already-wide parent table stable; explicit declined state per site (NULL alone cannot distinguish "not asked" from "declined"); raw readings persisted for recomputation (constitution "persist item-level answers"); trend charts read one indexed join; JSON is already proven dual-dialect in `athlete_ai_explanations.structured_json`.
- **Alternatives considered**: (a) 20+ nullable columns on `anthropometric_records` (rejected: widens a table feature 040 already widened, ambiguous NULL); (c) fully normalised `skinfold_readings` rows (rejected: needs a site enum and `GROUP BY` for every chart point; the site list is fixed at six).

## R2 — Computation placement: persist sums and estimates, derive the reading

- **Decision**: sums, body-fat percentage, fat mass and fat-free mass are computed in the service at write time and stored with `equation_version = "slaughter_tc_1988_v1"`; the change classification, reference context and traffic light are pure functions evaluated at read time and never stored.
- **Rationale**: mirrors `bmi`/z-scores (persisted with `growth_source`) versus `growth_summary` alerts (derived); a threshold tweak must apply retroactively without a backfill; the AI context reads stored values off the ORM.
- **Alternatives**: derive everything at read (rejected: equation drift, previous-record diffs need stored values); persist the band (rejected: policy, not data).

## R3 — API shape: sub-resource `PUT`, not a bigger `POST`

- **Decision**: `PUT /api/athletes/{athlete_id}/anthropometry/{record_id}/skinfolds` creates or replaces the set (idempotent), `DELETE` removes it; `POST …/anthropometry` is untouched. `GET /api/athletes/{athlete_id}/body-composition` serves the coach view; `growth-summary` gains a `body_composition` block for both roles.
- **Rationale**: the guided flow runs after the fast save and may be resumed from a draft; a wizard failure must never lose the weight/height record; "replace the most recent set" (FR-011) is a natural `PUT`.
- **Alternatives**: nested `skinfolds` in the create payload (rejected: couples the 30-second path to a 6–8-minute flow; no replace semantics).

## R4 — Interval rule semantics (FR-011)

- **Decision**: on `PUT`, if the athlete has a skinfold set on a *different* record whose `evaluation_date` is less than `BODY_COMP_MIN_INTERVAL_DAYS` (90) before the target record's `evaluation_date`, respond `409 {"code": "skinfold_interval_too_short", "next_allowed_date": …}`. Replacing the set on the same record is always allowed. The frontend hides the "agregar pliegues" exit before the date and shows the reason. Sets that are fully declined (all six sites) do not count as the "previous set" for the interval.
- **Rationale**: enforces the cadence server-side (spec SC-007) while keeping corrections possible.
- **Alternatives**: client-only rule (rejected: unverifiable); blocking replacement too (rejected: FR-011 requires corrections).

## R5 — Equation and constants

- **Decision**: Slaughter–Lohman (1988) triceps + medial calf, no race intercept, no maturation split: boys `%BF = 0.735·(T+C) + 1.0`; girls `%BF = 0.610·(T+C) + 5.0`; `fat_mass_kg = weight × %BF/100`; `fat_free_mass_kg = weight − fat_mass_kg`; margin shown as "±4 puntos". Computed only when both sites have a value; recomputed if the record's weight is corrected.
- **Rationale**: `research-protocol.md` §3 — the triceps+subscapular boys' equations require a White/Black intercept with no valid Colombian mapping; triceps+calf is race-free and validated for ages 6–17.
- **Alternatives**: triceps+subscapular with Mirwald→Tanner mapping (rejected: unvalidated crosswalk plus the race term); adult equations (rejected: invalid in children).

## R6 — Thresholds and knobs as settings

- **Decision**: `Settings` gains `BODY_COMP_MDC_SUM4_MM = 7.0`, `BODY_COMP_MDC_SUM6_MM = 10.0`, `BODY_COMP_MIN_INTERVAL_DAYS = 90`, `BODY_COMP_MIN_AGE_YEARS = 9`; the reading tolerance (greater of 5 % of the mean or 1 mm) is a constant in the service and mirrored in `lib/bodyComposition/readings.ts` with shared fixtures.
- **Rationale**: FR-015 "adjustable without a code change"; the club will replace the novice TEM-derived thresholds with its own after the W0 calibration sessions.
- **Alternatives**: DB-stored settings (rejected: no admin UI exists; env is the project's knob mechanism).

## R7 — Reference percentiles: seed FUPRECOL into the existing LMS table

- **Decision**: add `GrowthSource.FUPRECOL` and `GrowthIndicator.triceps_skinfold_for_age`, `subscapular_skinfold_for_age`, `triceps_subscapular_sum_for_age`; vendor `app/data/fuprecol_lms/fuprecol_skinfolds.csv` (columns `indicator,sex,age_months,L,M,S`) extracted from Ramírez-Vélez et al. 2016 Tables 2–4 (CC BY 4.0; L, S and P50 = M per sex and one-year band, ages 9–17.9), one row per band midpoint (9.5 y = 114 months … 17.5 y = 210 months); seed through `seed_growth_data.py` (idempotent upsert on the existing unique constraint) and `entrypoint.sh`. Percentile is computed with the existing `calculate_z_score`/`z_to_percentile` after `get_lms_params` interpolation; outside 108–216 months the context is "sin referencia para esta edad".
- **Rationale**: verified 2026-09-23 that the article prints the LMS parameters; the LMS machinery is indicator-agnostic (`technical-fit.md` §4); a Colombian school reference beats a US one for this population.
- **Migration note**: the two columns are MySQL `ENUM`s; the migration must `ALTER … MODIFY` them with the extended value lists (and shrink them back on downgrade after deleting FUPRECOL rows). On SQLite (test lane) SQLAlchemy stores `Enum` as VARCHAR without a CHECK constraint, so the alter is a no-op there; the real check is `pytest -m mysql`.
- **Alternatives**: Addo & Himes 2010 (LMS tables paywalled/unconfirmed); percentile-table lookup instead of LMS (unnecessary since L/M/S are published).

## R8 — Traffic-light rules

- **Decision**: encoded as a pure classifier in `services/body_composition.py::build_reading` with the legs and rules written in `contracts/body-composition-reading.md`: rojo only with ≥ 2 sets and all three legs (Σ4 `down_real`, weight not rising significantly, height still growing); ámbar for real changes without a growth explanation, reference extremes (≤ P5 / ≥ P95), BMI-z drop ≥ 1.0 SD, or height velocity below range for two cycles; verde otherwise, including the "expected pubertal fat gain" case (female, circa/post PHV, height velocity within or above range) and the pre-PHV pre-spurt accumulation case (any sex, height velocity within or above range).
- **Rationale**: spec FR-019–FR-021 and `research-safeguards-referral.md` §2; every rule is "coarse guidance" and tunable without a backfill because nothing is persisted.
- **Alternatives**: persisting a band per set (rejected R2); firing rojo on percentile extremes alone (rejected: anti-pattern 7, single measurement never diagnostic).

## R9 — Family projection and the PDF gap

- **Decision**: parents receive `body_composition` in `growth-summary` as `{has_data, band, family_label, family_sentence, latest_set_date}` only; `AnthropometryOut.skinfolds` is set to `None` for parents in the list endpoint (same block that already strips `notes`/`morphology`); `GET …/body-composition` returns 403 for parents; the existing parent-downloadable `anthropometry_report.html` is **not** extended with skinfolds at all (simplest guarantee of FR-026); the coach-only PDFs are the field guide and the referral note.
- **Rationale**: `technical-fit.md` §8 found the PDF is downloadable by parents without a role gate; not adding skinfolds there closes the gap by construction.
- **Alternatives**: role-conditional PDF sections (rejected: one more surface to test for leaks).

## R10 — AI explainer extension

- **Decision**: add a `body_composition: dict | None` leaf to `AnalysisContext` (qualitative codes only), extend `ANTHROPOMETRY_INSIGHT_CONTEXT_ALLOWED_KEYS`, render a "Composición corporal" block only when the leaf exists, ship `anthropometry_analyst_v2.md` / `anthropometry_critic_v2.md` and make `AI_ANTHRO_PROMPT_VERSION` default to `v2` (with `v1` kept in the allowed list for rollback), add prechecks R13 (family text containing `%` or `mm` numbers, must_block) and R14 (diet / weight-loss lexicon in either audience, must_block), extend the rule-based fallback, add four golden cases and refresh `baseline.json`.
- **Rationale**: the pipeline is built for additive blocks (`technical-fit.md` §6); prompt versioning already exists and is persisted per explanation row (`prompt_version`), giving a no-deploy rollback; the allow-list is the single privacy choke point.
- **Alternatives**: editing v1 in place (rejected: loses the rollback lever); folding R13/R14 into R12 (rejected: one rule one concern).

## R11 — Capture surface: dedicated lazy route

- **Decision**: `/athletes/:id/anthropometry/:recordId/skinfolds` (registered in `frontend/src/App.tsx` next to `/athletes/:id`) renders `SkinfoldCapturePage` (coach/admin; parents redirected as other coach-only routes are), reached from the post-save choice in `AnthropometryForm` and from the history row action; steps = pre-check → 6 sites → review, reusing `Stepper`, the `SessionWizard` focus contract and `useFormDraft` with target `skinfolds:{recordId}`.
- **Rationale**: page-level route gives a stable URL, its own accessibility audit, lazy chunk and simpler focus management; drafts key on the record, so a re-take restores the right set.
- **Alternatives**: inline wizard inside the anthropometry tab (rejected: dense tab, no deep link); modal (rejected: 8 steps in a dialog on a tablet).

## R12 — Illustrations: inline SVG from one shared spec

- **Decision**: `lib/bodyComposition/siteDiagrams.ts` holds, per site, the silhouette variant, landmark coordinates, fold orientation, caliper position, side tag "D" and the Spanish alt text; `SkinfoldSiteDiagram.tsx` renders it as inline SVG using theme tokens (stroke ≥ 2 px, shape + label never colour alone); the six Jinja partials under `templates/documents/pdf/diagrams/` reproduce the same coordinates for the field guide.
- **Rationale**: feature-019 gymkhana decision record (one schema, two renderers); ISAK images are copyrighted, the landmark descriptions are not; no photos of minors; print-safe.
- **Alternatives**: licensed illustration set (rejected: wrong register, licence risk); GIF/animation (rejected: motion policy; static first).

## R13 — Printable field guide

- **Decision**: `GET /api/body-composition/field-guide.pdf` (coach/admin) renders a static Jinja template through WeasyPrint with the six SVG partials, the pre-check list and the reading protocol; frontend `FieldGuideDownloadButton` reuses the `InstructivoDownloadButton` blob pattern.
- **Rationale**: existing instructivo pattern (`intervals/instructivo_pdf.py`); no athlete data, so it can be cached by the browser.

## R14 — Referral note

- **Decision**: `GET /api/athletes/{athlete_id}/body-composition/referral-note.pdf` (coach/admin) renders the template with the neutral pattern description generated from the reading (age band, sex, pattern codes → Spanish sentences, training hours from the 28-day window), initials only, no diagnosis, a fixed authorization sentence; `409` when no set exists. The button is shown on rojo (spec FR-023); the endpoint itself only requires a set.
- **Rationale**: `research-safeguards-referral.md` §4 template; WeasyPrint is the established document path.

## R15 — Family notice

- **Decision**: `FamilySkinfoldNotice` is an always-available collapsible block ("¿Qué es esta medición?") on the family growth view, shown whenever the athlete is 9+ (before or after the first set), using the approved addendum text; no persisted "seen" state, no consent record.
- **Rationale**: data minimisation; FR-027 asks to inform, not to record acknowledgement.

## R16 — Testing lanes and deferred checks

- **Decision**: default `pytest` lane covers services, routers, context, prechecks and the privacy property; `pytest -m mysql` covers the enum alter and downgrade; `pytest -m golden` gates the prompt change (requires an AI key); Playwright `e2e/body-composition.spec.ts` covers capture → reading → family card on the isolated e2e stack. The report must state explicitly which of the three real-infrastructure lanes were not run.
- **Rationale**: CLAUDE.md "deferred real-infra checks" invariant.
