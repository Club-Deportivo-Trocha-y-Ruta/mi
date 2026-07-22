# Research: Interval Block Duration Usability (034)

**Date**: 2026-07-22 · **Inputs**: web research on reference platforms + codebase exploration of feature 026

## R1 — How reference platforms model open-ended blocks

- **Decision**: Adopt the industry pattern: per-block duration *type* with an explicit "until lap button press" variant, restricted to warmup/cooldown and forbidden inside repeat groups.
- **Rationale**:
  - **Garmin Connect**: step duration is an enum — Time, Distance, **Lap Button Press**, Heart Rate, Calories, Open. Lap-press is a first-class duration type; repeats cannot end on lap press ([Garmin forums](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/129105/workout-repeat-until-lap-button-pressed)).
  - **TrainingPeaks**: "open-ended steps" with *End step on lap button* — target keeps displaying, timer doesn't reset, until lap press; canonical use is free-length warmup/cooldown ([TP help](https://help.trainingpeaks.com/hc/en-us/articles/115003385172-Open-ended-steps-for-Structured-Workouts)).
  - **intervals.icu**: per-step "Press lap" flag; on Garmin export the device waits for the lap button ([forum](https://forum.intervals.icu/t/how-to-create-workout-step-with-minimum-duration-and-than-press-lap-to-continue/92894)).
  - **Zwift**: only "free ride" *intensity* blocks with fixed duration — no lap-press (indoor erg); confirms open *duration* and open *intensity* are separate concepts. We adopt open duration only; zone + cadence stay mandatory.
  - The club's PDF instructivo already instructs athletes to mark each block with the lap button (`session_instructivo.html` L292), so the device workflow needs no change.
- **Alternatives considered**: minimum-duration + lap-press combo (TP supports it) — rejected for v1, adds UI complexity with no coach demand; distance-based durations — out of scope (spec).

## R2 — DB representation of open duration

- **Decision**: New enum column `duration_type` (`fixed` | `open_lap`, project-convention `values_callable`, `server_default='fixed'`) on `interval_structure_blocks` **and** `interval_template_blocks`; `duration_s` becomes nullable. Invariants: `fixed` ⇒ `duration_s` NOT NULL AND > 0; `open_lap` ⇒ `duration_s` IS NULL. Migration `c7d8e9f0a1b2` (down_revision `b5c6d7e8f9a0`, current head).
- **Rationale**: Explicit discriminator beats NULL-as-sentinel (ambiguity with corrupt data, no extensibility); matches Garmin's model; old rows migrate untouched (default `fixed`), satisfying FR-011.
- **Alternatives considered**: nullable `duration_s` alone (rejected: sentinel semantics); boolean `is_open` (rejected: closed to future duration types); sentinel value `duration_s=0` (rejected: silently breaks `gt=0` validation and total sums).

## R3 — Matching engine semantics for open steps

- **Decision**: Bump `ENGINE_VERSION` 1 → 2. `flatten_blocks` steps carry `duration_type`; `planned_duration_s=None` for open steps. `compute_match`: open step + qualifying lap → new status **`libre`** (lap consumed positionally, actual elapsed shown, tolerance math skipped entirely); open step without lap → existing `sin_dato`; `MIN_LAP_ELAPSED_S=10` noise filter unchanged; fixed steps keep ±30%.
- **Rationale**: `_is_within_tolerance` divides by `planned_duration_s` — open steps must never enter it (no division by None, no false `fuera_tolerancia`, FR-008). New output vocabulary ⇒ version bump; stored matches record their engine version, so pre-existing comparisons render unchanged (SC-003) and no recomputation is triggered.
- **Alternatives considered**: reuse `cumplido` for open+lap (rejected: lies — nothing was judged; spec demands distinct informational status); skip lap consumption for open steps (rejected: athlete DID ride the block and pressed lap — positional pairing must consume it or every later block shifts).

## R4 — mm:ss entry widget

- **Decision**: New reusable `MmSsInput` component: two numeric fields (Min ≥ 0, Seg 0–59) that read/write a single seconds value; form/schema source of truth remains `duration_s` in seconds. Used by `BlockRow` (structure editor and template editor path).
- **Rationale**: Constitution III — coach uses a tablet outdoors with gloves: two 48 px fields with native numeric keyboards beat a masked `mm:ss` text input (cursor traps, IME issues, harder RHF/Zod wiring). Per-field labels are screen-reader friendly. Keeping seconds as the stored/form unit means totals (`computeFlattenedDurationS`, `formatMmSs`), API schemas, and matching are untouched by the widget change.
- **Alternatives considered**: masked single input (rejected: touch ergonomics); changing form shape to `{min, sec}` with transform (rejected: ripples through zod schemas, drafts in `localStorage`, and edit hydration for zero user benefit).

## R5 — Backward compatibility & rollout

- **Decision**: Fully additive contract: `BlockIn.duration_type` optional with default `fixed` (older drafts/clients keep working, FR-004); `total_planned_duration_s` redefined as *fixed-blocks-only* sum (documented); frontend derives "+ calentamiento libre"/"+ libre" suffix from block data it already receives — no new response fields; PDF template gains one conditional. Deploy = run migration on Render (standard `entrypoint.sh` auto-upgrade).
- **Rationale**: Zero user-visible change for existing data (SC-003); no client/server deploy-order hazard because the server defaults the missing field.
- **Alternatives considered**: new `has_open_blocks` response field (rejected: derivable client-side, needless contract growth).

## R6 — UX copy & status color

- **Decision**: Duration-type select copy: "Tiempo fijo" / **"Libre — hasta botón de vuelta"**. Comparison badge for status `libre`: neutral gray (informational), planned-duration cell renders "Libre". Total label: `"{mm:ss} + calentamiento libre"` (or "+ enfriamiento libre" / "+ libre" when both or generic; structure with no fixed blocks → "Duración libre").
- **Rationale**: Constitution III color semantics — green means judged-success; `libre` is unjudged/informational ⇒ gray. Copy in español neutro (Colombia) with full diacritics.

All spec unknowns resolved — no NEEDS CLARIFICATION remain.
