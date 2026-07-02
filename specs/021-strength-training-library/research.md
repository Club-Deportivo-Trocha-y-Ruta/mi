# Research: Strength Training Exercise Library (021)

**Date**: 2026-07-02 · **Inputs**: deep-research run wf_a8c9ff5c-32b (101 agents, 21/25 claims confirmed by 3-vote adversarial verification), codebase exploration of features 018/019, spec-panel review.

All `NEEDS CLARIFICATION` from Technical Context: **none remained** — the spec resolved its single open marker (FR-011) before planning. Decisions below consolidate evidence and pattern choices.

---

## D1. Seed catalog content & dosing rules

**Decision**: ~22 seeded exercises across the 5-category movement taxonomy (upper push / upper pull / lower bilateral / lower single-leg / core-stability). 10-12 band: bodyweight only. 13-15 band: bodyweight + bands + dumbbells + light gym equipment; **no clean/snatch/deadlift/back-squat**. Suggested dosing defaults per entry expressed as reps ranges + estimated minutes, consistent with 10-15RM (10-12) and 8-15RM (13-15).

**Rationale** (verified findings, HIGH confidence):
- Supervised youth RT is safe, does not impair growth; injuries stem from poor technique/supervision/load (NSCA 2009 position stand: RT = 0.7% of youth sport injuries vs ~19% football).
- ASCA age-banded dosing maps directly onto the club's bands: Level 2 (~9-12y) bodyweight/light-machine, 10-15RM @ ~60% max; Level 3 (~12-15y) progressive free weights, 8-15RM @ ~70% max, avoiding complex lifts without accredited coaching.
- Pre-pubertal strength gains are neural, not hypertrophic → bodyweight/technique emphasis for 10-12 is evidence-backed, not just policy.

**Alternatives considered**: importing free-exercise-db's 800+ exercises wholesale — rejected: adult-oriented content, no age-band semantics, stock-photo imagery unusable for minors. Used as taxonomy/text reference only (Unlicense = legally clean).

## D2. The 30-minute ceiling

**Decision**: modeled as a **configurable business rule** — single backend constant surfaced in the block schema (`duration_target_min`, default 30), indicator computed client-side (within / at / over). Advisory, never blocking. UI copy states it as the club's session-design rule.

**Rationale**: deep-research explicitly **refuted** the one claim that seemed to support a scientific basis (RT4T 15-20-of-40-min block ratio: 0-3 votes). No primary source validates the exact figure → it is the coach's product preference and must not be worded as clinical guidance (spec FR-009).

**Alternatives considered**: hard server-side validation rejecting >30-min blocks — rejected: contradicts club principle #9 (flexible plan) and has no evidence basis to justify rigidity.

## D3. Age-band guardrail enforcement (FR-011)

**Decision**: **warn-and-allow with recorded override**. Adding an age-inappropriate exercise to a block surfaces an explanatory warning dialog; proceeding requires explicit confirmation; the override is persisted on the block entry (`is_age_override`, `override_note`, implicit who/when via block audit columns).

**Rationale**: honors club non-negotiable #9 (coach professional judgment for legitimate edge cases — e.g., a mature 12-year-old post-PHV) while keeping a safety audit trail (SC-004 measurable). ASCA provides **no** competency-gating criteria (claim refuted 0-3), so any rigid gate would be invented, not sourced.

**Alternatives considered**: hard-block (max safety, zero flexibility — rejected as contrary to principle #9); shown-but-blocked without override (educates but still rigid — rejected same reason). Flagged for re-confirmation in `/speckit-clarify`.

## D4. Illustration approach

**Decision**: v1 = original ASCII illustration + mandatory `illustration_alt` accessibility text + step-by-step execution text + common-errors list. Rendered via the 018 `CircuitLayout` **fallback pattern**: `<pre>` monospace wrapped in `role="img"` + `aria-label`. An optional `illustration_json` column is **not** added in v1 (no strength-figure SVG grammar exists yet; 019's `layout_json` grammar is circuit-specific — cones/gates/beams — and does not describe body positions).

**Rationale**: zero third-party image rights risk; free-exercise-db photos confirmed to be adult stock photography unsuitable for a minors product (MEDIUM-confidence finding + internal precedent 018/019). ASCII+alt shipped and audited successfully in 018.

**Alternatives considered**: original SVG body-position figures (019-style) — deferred to a follow-up feature; requires designing a new figure grammar + authoring ~22 diagrams, disproportionate for v1. Licensed photo/GIF libraries — rejected (rights + minors-appropriateness).

## D5. Reusable StrengthBlock vs. 018-style direct assembly

**Decision**: first-class `StrengthBlock` entity (name, target age band, entries with per-entry duration/reps) attached to sessions via a join table (`strength_session_blocks`). Blocks are reusable across sessions; attach does not copy.

**Rationale**: spec FR-008/FR-012/FR-013 + assumption "block may be attached to more than one session". 018 assembles exercises directly into a session (no reusable intermediate), which cannot express reuse or a block-level duration budget/age-band context for the guardrail.

**Alternatives considered**: 018-style direct `strength_session_exercises` join — rejected: loses reuse, block naming, and the target-age-band context the guardrail needs. Copy-on-attach — rejected pending coach feedback (documented assumption; trivially changeable at the service layer later).

## D6. Free-text search

**Decision**: DB-side `LIKE %term%` over `name` + `summary`, combined AND-wise with facet filters (equipment, age band, movement category). No external search engine.

**Rationale**: catalog is ~22-50 rows; LIKE is instant at this scale and stays within stack discipline (no new deps). 018 shipped facets-only; 021's spec (FR-005) adds free-text explicitly.

**Alternatives considered**: MySQL FULLTEXT index — unnecessary at this scale, complicates aiosqlite test parity; client-side filtering — rejected, breaks server pagination contract `{items, total}`.

## D7. Schema/seed/migration pattern

**Decision**: mirror 018 exactly — enums via `SAEnum(values_callable=...)`; `slug` unique idempotent seed key; `is_seeded` / `is_hidden` (soft-hide, FK RESTRICT from block entries so hiding never corrupts saved blocks); `club_id` nullable (null = shared seed); seed data in `backend/app/data/strength_catalog.py` consumed by the Alembic migration's `upgrade()` (chained off head `f1a2b3c4d5e6`); seed does not run separately in prod — migration carries it.

**Rationale**: proven in 018 (`e1f2a3b4c5d6`) and 019 (`f1a2b3c4d5e6` backfill); idempotent by slug; consistent with entrypoint.sh auto-migration deploy flow.

**Alternatives considered**: seeding via `backend/scripts/seed.py` — rejected: seed.py does not run in production (`APP_ENV != development`), and the catalog must exist in prod day one (SC-007).

## D8. Progress notes model

**Decision**: append-only `strength_progress_notes` mirroring 018's `AthleteSkillProgress`: `(athlete_id, exercise_id, status, coach_note, season, recorded_by_user_id, recorded_at)`; current state = latest row. Reuse the `introducido / en_progreso / dominado` status vocabulary. Coach/admin-only via existing club-scope check pattern (`technique.py:417` `_require_athlete_club_scope`).

**Rationale**: append-only preserves history without update anomalies; identical privacy posture already audited in 018 (`test_progress_privacy.py`).

**Alternatives considered**: mutable single-row-per-(athlete,exercise) — rejected: loses trajectory, diverges from 018.

## D9. Scope exclusions confirmed by research

- **PHV-stage eligibility modeling**: excluded from v1 — "windows of trainability" claims rated MEDIUM/refuted (girls' double-window claim killed 0-3; general windows lack longitudinal support). Chronological bands only.
- **Coach-created custom exercises** (018 has `POST/PUT /exercises`): **not in spec FRs** — v1 catalog is seed-only; curation endpoints deferred until the coach asks.
- **wger as second seed source**: unverified in research pass; unnecessary at ~22-exercise scale.
- **1RM testing / repetitions-till-fatigue protocols**: the pro-RTF claim was refuted 0-3; no testing protocols ship (FR-019).
