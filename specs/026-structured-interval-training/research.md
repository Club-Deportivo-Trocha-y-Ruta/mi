# Phase 0 Research: Structured Interval Training with Strava Correlation

**Feature**: `026-structured-interval-training` · **Date**: 2026-07-10

All Technical Context unknowns are resolved. Sources: prior deep-research pass (TrainingPeaks / intervals.icu / Zwift ZWO / Garmin FIT / device manuals / Strava API, fully cited below), a targeted follow-up web verification, and three codebase mapping passes (attached-block pattern 018/021, Strava 025 internals, PDF/RBAC/routing conventions).

---

## D1. Interval structure data model — relational blocks with inline repeat groups

**Decision**: Two tables per shape: `interval_structures` (1:1 with `training_sessions`, coach-declared `target_age_band`, age-gate confirmation columns) + `interval_structure_blocks` (ordered rows: `position`, `block_type` enum `warmup|work|recovery|cooldown`, `duration_s`, `target_zone` enum `Z1..Z5`, `target_cadence_rpm`, and repeat modeling via nullable `repeat_group` + `repeat_count` shared by the group's rows). Same block shape duplicated for templates (`interval_templates` + `interval_template_blocks`).

**Rationale**: The step-atomic model (duration-or-trigger + target + sequence position, grouped into repeat blocks) is the industry-consistent pattern across TrainingPeaks, intervals.icu, Zwift ZWO, and Garmin FIT ([TrainingPeaks Structured Workout Builder](https://help.trainingpeaks.com/hc/en-us/articles/235164967-Structured-Workout-Builder), [intervals.icu syntax](https://forum.intervals.icu/t/workout-builder-syntax-quick-guide/123701), [ZWO reference](https://github.com/h4l/zwift-workout-file-reference/blob/master/zwift_workout_file_tag_reference.md), [FIT Workout](https://developer.garmin.com/fit/file-types/workout/)). Relational rows (vs. a JSON column) let the DB enforce ordering/uniqueness, keep Alembic diffs honest, and make the matching engine's flattening step trivial and testable. Inline `repeat_group`/`repeat_count` avoids a third table for a structure that is at most ~15 rows.

**Alternatives considered**: (a) JSON `structure_json` column on the session (spec-022 `metrics_snapshot` pattern) — rejected: guardrail validations (cadence ≥60, Z3+ gate) belong in typed columns + service checks, and templates would have to duplicate the JSON contract anyway. (b) Separate `interval_block_groups` table — rejected as premature; two nullable columns express the same thing at this scale.

## D2. No power target field exists at all (FR-005)

**Decision**: Blocks have exactly two target dimensions: HR zone and cadence. There is no wattage/power column, schema field, or UI control — for any age.

**Rationale**: The club rule is "no power meter <13"; v1 targets are HR-zone + cadence only per the interview. Making power structurally impossible (rather than age-conditional) satisfies FR-005 by construction and removes a whole class of guardrail tests. RPE-as-target is the confirmed industry gap and the club's primary metric, but it was explicitly deferred to v2 (interview P1/P8), so v1 deliberately ships without it.

**Alternatives considered**: Nullable `target_watts` gated by age — rejected: dead column, more guardrail surface, contradicts the locked v1 scope.

## D3. Age gating — coach-declared band on the structure, hybrid enforcement (FR-006/FR-007)

**Decision**: `interval_structures.target_age_band` reuses the existing `AgeBand` enum (`10-12` / `13-15`, defined in `app/models/technique_exercise.py`) and is **declared by the coach**, mirroring `StrengthBlock.target_age_band`. Enforcement in `services/intervals/structures.py`: if band is `10-12` and any flattened block has `target_zone >= Z3` → hard 422 with machine-readable code (`age_gate_z3_blocked`), no override. If band is `10-12` and all blocks are Z1–Z2 → require `age_gate_confirmed=true` in the payload; persist `age_gate_confirmed_by_user_id` + `age_gate_confirmed_at`. Same checks run at template-attach time (spec edge case).

**Rationale**: Codebase mapping confirmed the 021 guardrail is **not** derived from `athletes.birth_date` — sessions are club-wide multi-athlete entities with no single athlete age; the coach-declared band compared against content, with an inline recorded override, is the established, tested pattern (`services/strength/blocks.py::_validate_age_band_guardrail`, `is_age_override`/`override_note` columns, `AgeBandGuardrailDialog.tsx`). The hybrid split (hard vs. confirm) is the interview decision P6=C.

**Alternatives considered**: Deriving the band from attendees' birth dates — rejected: sessions can mix bands, attendance may not exist yet at planning time, and it would diverge from the proven 018/021 pattern.

## D4. Laps persistence — new `strava_activity_laps` table, fetched at match time (FR-012/FR-013)

**Decision**: New table owned by the activity: `strava_activity_id` FK (CASCADE), `lap_index`, `elapsed_time_s`, `moving_time_s`, `average_heartrate` (nullable), `average_speed_m_s` (nullable), `fetched_at`; `UNIQUE(strava_activity_id, lap_index)`. **Explicitly absent**: `start_latlng`, `end_latlng`, polyline/map, `average_cadence` (deferred to v2 by interview P9), `average_watts`, free-text lap name. Laps are fetched via a new `StravaClient.get_activity_laps(activity_id)` calling `GET /activities/{id}/laps`, following the existing `_request()` choke-point (auth refresh + 429 → `StravaRateLimited`). Re-fetch on every recalculation replaces the activity's lap rows (delete-and-insert keyed by activity).

**Rationale**: Interview P4=A (persist). Strava's laps endpoint returns device-recorded laps as-is — manual lap-button laps included — and the per-km "splits" are a separate Strava-computed concept that does **not** contaminate the laps list ([Strava API reference](https://developers.strava.com/docs/reference/), [Strava workout analysis guide](https://communityhub.strava.com/insider-journal-9/spotlight-feature-running-workout-analysis-guide-1491)). Lap fields used are all non-geo, satisfying Ley 1581 by construction. Codebase mapping confirmed no laps method exists today — additive change to `client.py`.

**Known caveat (documented for the matching engine)**: Strava has a reported processing behavior where very short laps can be removed upstream ([community report](https://communityhub.strava.com/developers-api-7/activities-returning-with-laps-removed-1732)). The matching engine must therefore tolerate missing short laps gracefully (they surface as `sin_dato` blocks) rather than assume device-count fidelity.

**Alternatives considered**: On-demand fetch without persistence — rejected in interview (rate limits, Render cold start latency on every view, kills future longitudinal analysis).

## D5. Matching engine — sequential order-based pairing with duration tolerance (FR-014/FR-016)

**Decision**: Pure function in `services/intervals/matching.py`:
1. Flatten the structure (expand repeat groups into the real step sequence).
2. Filter laps: drop laps with `elapsed_time_s < 10` (double-click noise), keep device order by `lap_index`.
3. Pair by position: `plan[i] ↔ lap[i]`.
4. Per-block status: `cumplido` if `|lap_duration − block_duration| / block_duration ≤ 0.30`; `fuera_tolerancia` otherwise; `sin_dato` for planned blocks without a lap; extra laps reported as `extra` (never silently discarded, never force-fitted).
5. Output: per-block rows + aggregate counts, persisted as one `interval_match_results` row (JSON result column + `engine_version` + `computed_at`), unique per `(structure_id, strava_activity_id)`.

**Rationale**: This replicates the only production mechanism proven to work without streams: TrainingPeaks consumes device laps *as-is* and pairs them against planned blocks by sequence, naming laps after plan blocks ([TP lap-data-as-is confirmation](https://forum.intervals.icu/t/solved-different-average-power-values-in-laps-between-interval-icu-and-trainingpeaks-for-40-20-intervals-ans-tp-uses-lap-data-directly/114116)). Stream-based auto-detection (intervals.icu's approach) requires high-resolution HR/power streams we deliberately do not persist ([intervals.icu analyze](https://www.intervals.icu/features/analyze/)). ±30% tolerance is a slightly looser cousin of TrainingPeaks' ±20% compliance color-coding ([Workout Card](https://help.trainingpeaks.com/hc/en-us/articles/204861204-Workout-Card-Overview)) — appropriate for children marking laps manually; the threshold lives in one constant.

**Alternatives considered**: (a) Consecutive-lap collapse heuristic (merge adjacent laps when their sum fits the planned duration better) — deferred: adds matching ambiguity and test surface; v1 degrades transparently to `fuera_tolerancia`/`extra` and the coach can read the table. (b) Proportional re-split when laps are missing — rejected: dishonest without streams; spec mandates explicit `sin_dato` degradation.

## D6. Matching trigger — deferred computation via existing `TaskDispatcher` (FR-014/FR-015)

**Decision**: Two auto-triggers + one manual: (1) `PATCH /api/activities/{id}/link` — after the link commits, dispatch a deferred job (same `TaskDispatcher` pattern as the Strava webhook path) that fetches laps, persists them, and computes the match if the session has a structure; (2) structure create/update on a session that already has a linked activity — same deferred job; (3) `POST /api/intervals/structures/{id}/recalculate` — coach-triggered, re-fetches laps and recomputes. The detail view shows a "comparación en cálculo…" state until the result row exists.

**Rationale**: Codebase mapping shows `link_activity` is currently a DB-only endpoint; adding a synchronous outbound Strava call there would put third-party latency (+ token refresh, + 429 handling) inside a user-facing request and threaten the p95 ≤1500 ms write budget (Constitution IV). The deferred-dispatch pattern already exists, is tested, and opens its own session/commit. Trigger (2) covers the spec's "structure created after the activity was linked" ordering; the manual trigger is interview P3=C.

**Alternatives considered**: Synchronous compute in the link request — rejected on the performance budget; polling Strava on view — rejected with D4.

## D7. Orphaned comparisons on structure delete (spec edge case, deferred to planning)

**Decision**: `interval_match_results.structure_id` FK is `ON DELETE CASCADE` — deleting a structure deletes its comparisons. `strava_activity_laps` are **never** deleted by structure or match lifecycle (owned by the activity; removed only with the activity itself via CASCADE).

**Rationale**: A comparison is a derived artifact meaningless without its plan side; keeping it would surface dangling rows in the detail view. Laps, by contrast, are facts about the activity and the expensive-to-refetch asset — they survive, which also matches the spec's instruction that laps are not implicitly deleted.

**Alternatives considered**: `SET NULL` + keep orphaned comparisons for audit — rejected: no user-facing surface reads them, and recomputation is cheap once a new structure exists.

## D8. Instructivo PDF — existing `DocumentGenerator` + per-brand template blocks (FR-010/FR-011)

**Decision**: New Jinja template `templates/documents/pdf/session_instructivo.html` (extends `base/layout.html`, brand tokens), registered as a new `DocumentTemplate` enum value; wrapper `services/intervals/instructivo_pdf.py` (mirrors `athlete_newsletter_pdf.py`); endpoint `GET /api/intervals/sessions/{session_id}/instructivo?brand=garmin|magene|igpsport` returning the in-memory `Response(..., media_type="application/pdf", Content-Disposition: attachment)` pattern already used by `reports.py`. Brand-specific content, in español neutro:
- **Garmin**: use the native on-device editor — `Entrenamiento > Intervalos`, set rest `Type = Open` so the device waits for the lap button (manual on-device config supports open/lap-triggered rest reliably; the FIT-file degradation only affects externally pushed files — [Edge owner's manual](https://www8.garmin.com/manuals/webhelp/edge530/EN-US/GUID-026D9232-D9D6-4AF7-93B8-4E54572332C5.html)).
- **Magene**: `training-create` menu blocks (Warm-up/Riding/Recovery/Cool-down) accept fixed Duration only — instruct estimated durations + manual lap presses ([Magene support](https://support.magene.com/hc/en-us/articles/8398522327449-What-s-in-the-training-create-menu)).
- **iGPSport**: no structure editor exists — the PDF is the reference sheet itself; the athlete follows it and presses lap ([intervals.icu forum confirmation](https://forum.intervals.icu/t/how-to-import-workouts-to-igpsport-630/95988)).
- **All three brands**: an explicit "desactivá el auto-lap (vuelta automática por km)" step — auto-laps would pollute sequential matching (insight from [Runna's device guidance](https://support.runna.com/en/articles/14302433-using-your-smart-watch-with-runna)).

**Rationale**: Reuses the full proven pipeline (Jinja env, filters `date_es`/`hms`, executor-offloaded WeasyPrint, filename builder); zero new dependencies; v1 delivery is manual download only (interview P10=A), which this endpoint shape enforces — no email hook, no public token page.

**Alternatives considered**: Per-brand separate templates — rejected: one template with brand conditional blocks keeps shared layout/steps table single-sourced.

## D9. API surface & RBAC — dedicated `/api/intervals` router, coach/admin-only (FR-018)

**Decision**: New router `routers/intervals.py`, prefix `/api/intervals`, every route behind `Depends(require_role([UserRole.admin, UserRole.coach]))` + club scoping through the session's club (`user_club_role`), exactly like `routers/strength.py`. Parents/athletes get 403 on everything — including the match detail and laps (which are only ever embedded in match responses, never a standalone public listing). Contract detail in [contracts/api.md](./contracts/api.md).

**Rationale**: FR-018 demands server-side denial, not just hidden UI; the strength router is the copy-paste-proven reference including its RBAC test suite (`tests/strength/test_rbac.py`).

**Alternatives considered**: Hanging endpoints off `training_sessions.py` — rejected: that router serves a union coach/parent audience (`can_view_session`), making accidental exposure easier; a separate prefix keeps the deny-all-parents invariant auditable.

## D10. Frontend placement — session detail section + lazy coach-only routes

**Decision**: `SessionDetailPage.tsx` gains an "Estructura de intervalos" section (create/edit via `StructureEditor`, template attach via `TemplatePicker`, instructivo download button) and, when a linked activity + computed match exist, a link into a lazy `ActivityMatchPage` (`/training/sessions/:id/activity-match/:activityId`) rendering `PlanVsActualTable`. Template library at lazy `/intervals/templates`. Both new routes wrapped in `ProtectedRoute allowedRoles={[coach, admin]}`. Editor validation via Zod (cadence ≥60 inline error, repeat count ≥2); age-gate 422 responses mapped to `AgeGateDialog` (confirm → resubmit with `age_gate_confirmed: true`), mirroring `extractAgeBandGuardrail`/`AgeBandGuardrailDialog` from strength.

**Rationale**: Session detail is where attendance, media, and Strava evidence already converge — mapped precedent (`ActivityEvidenceStrip` renders there). Lazy routes keep the 150 KB per-route budget; the strength feature demonstrates the exact hook/api/component topology to mirror.

**Alternatives considered**: New wizard step — rejected in interview (P2=B); standalone builder page as the only edit surface (strength's approach) — softened: editing belongs next to the session since structures are 1:1 with sessions, unlike reusable strength blocks.

---

## Resolved-unknowns checklist

| Unknown | Resolution |
|---|---|
| Strava laps endpoint fields & geo exposure | D4 — non-geo fields only; endpoint confirmed |
| Device laps vs Strava splits contamination | D4 — separate concepts; splits never enter the laps list |
| Existing laps capability in `StravaClient` | None exists; additive method (codebase map) |
| Where matching hooks into linking | `link_activity` + deferred dispatcher (D6) |
| Age band source of truth | Coach-declared, `AgeBand` enum reuse (D3) |
| Repeat-group modeling | Inline nullable columns (D1) |
| Orphaned comparison behavior | CASCADE match, preserve laps (D7) |
| PDF pipeline reuse points | `DocumentGenerator` + registry + `Response` pattern (D8) |
| Alembic head | `a4b5c6d7e8f9` (verified via down_revision scan) |
| Per-brand manual-config reality | Garmin native Open rest / Magene fixed durations / iGPSport paper-only (D8) |
