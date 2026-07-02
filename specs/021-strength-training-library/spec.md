# Feature Specification: Strength Training Exercise Library

**Feature Branch**: `021-strength-training-library`

**Created**: 2026-07-02

**Status**: Draft

**Input**: User description: "Un módulo que maneje ejercicios de fortalecimiento para deportistas, que no supere los 30 minutos por sección, debe ser ilustrativo. Que incluya la librería de ejercicios, con y sin equipos de gym."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse and search the illustrated strength exercise library (Priority: P1)

The coach opens the strength library and browses a curated catalog of strength-training exercises. Each exercise shows an illustration (own diagram/ASCII or original static artwork — never a licensed third-party photo) plus a plain-language description of how to execute it and the most common execution errors. The coach filters the catalog by equipment availability (bodyweight / no-equipment vs. gym-equipment) and by age band (10-12 / 13-15) so he only sees exercises appropriate for the athletes in front of him.

**Why this priority**: Without a searchable, illustrated catalog there is no product. This is the minimum viable slice: even with nothing else, a coach can look up a safe, age-appropriate, well-illustrated exercise on his tablet in the field. It mirrors the already-proven technique/gymkhana library (spec 018) and reuses the club's own-artwork approach (spec 019).

**Independent Test**: Load the library, apply an equipment filter and an age-band filter, open a result, and confirm the illustration, execution steps, and common-errors text render. Delivers standalone value as a reference tool.

**Acceptance Scenarios**:

1. **Given** a seeded exercise catalog, **When** the coach filters by "no-equipment" and age band "10-12", **Then** only bodyweight exercises tagged as appropriate for 10-12 are shown, each with an illustration and execution guidance.
2. **Given** the coach is viewing an exercise, **When** he opens its detail, **Then** he sees a step-by-step execution description and a list of common errors, with no licensed third-party photograph anywhere on screen.
3. **Given** a free-text search term (e.g., "plank"), **When** the coach searches, **Then** matching exercises are returned ranked by relevance and still respect any active equipment/age-band filters.

---

### User Story 2 - Assemble a time-boxed strength block and attach it to a training session (Priority: P2)

The coach selects several exercises and assembles them into a named "strength block". As he adds exercises, a running total of the block's estimated duration is always visible, and the system communicates whether the block is within, at, or over the 30-minute target. Each exercise entry in the block carries a suggested duration/reps. Once assembled, the coach attaches the block to a new or existing training session in the existing Training Sessions module (Phase 1.5), so strength work appears alongside the rest of that session's plan.

**Why this priority**: Turning the reference catalog into an actionable, time-boxed plan attached to a real session is the core workflow the coach asked for ("no supere los 30 minutos por sección"). It depends on P1 (a catalog to pick from) but delivers the planning value.

**Independent Test**: With a seeded catalog, create a block, add exercises until the running total approaches/exceeds 30 minutes, observe the within/at/over indicator, then attach the block to a training session and confirm it appears in that session's plan.

**Acceptance Scenarios**:

1. **Given** the coach is assembling a block, **When** he adds an exercise with a suggested duration, **Then** the block's running total updates and the within/at/over-30-minutes indicator reflects the new total.
2. **Given** a completed strength block, **When** the coach attaches it to an existing training session, **Then** the block appears in that session's plan without duplicating session infrastructure.
3. **Given** a strength block attached to a session, **When** the coach reopens that session, **Then** the block and its exercises are still present and editable.

---

### User Story 3 - Age-band safety guardrails during assembly (Priority: P2)

While assembling a block for a given age band, the coach is prevented from — or clearly warned against — adding an exercise that is not appropriate for that band (for example, an external-load/free-weight progression exercise reserved for 13-15 being added to a 10-12 block). The guardrail encodes the club's dosing differentiation (10-12 bodyweight-only, no structured loading; 13-15 progressive equipment under supervision) so the coach does not have to re-derive safe defaults each time.

**Why this priority**: This is the safety spine of the feature and the club's differentiator, but it is only meaningful once assembly (P2) exists. Grouped at P2 because the guardrail and the assembly flow ship together.

**Independent Test**: Start a block targeting age band 10-12, attempt to add an exercise flagged as 13-15-only, and confirm the guardrail behavior (block or warn) fires with a clear explanation.

**Acceptance Scenarios**:

1. **Given** a block targeting age band 10-12, **When** the coach attempts to add a 13-15-only exercise, **Then** the system shows a clear warning explaining why it is not appropriate and blocks the add until the coach explicitly confirms an override, which is then recorded.
2. **Given** a block targeting age band 13-15, **When** the coach adds a bodyweight exercise also valid for 10-12, **Then** it is accepted without warning.

---

### User Story 4 - Per-athlete strength progress notes (coach-only) (Priority: P3)

The coach records per-athlete completion/progress notes on strength exercises for his own planning reference, mirroring the technique library (spec 018). No screen ever compares one athlete's strength progress against another's.

**Why this priority**: Useful longitudinal tracking, but the catalog + assembly workflow already deliver the primary value; progress notes are an enhancement.

**Independent Test**: Record a progress note for one athlete on one exercise, reopen it, confirm it persists, and confirm no comparison/leaderboard view exists anywhere.

**Acceptance Scenarios**:

1. **Given** an athlete and a strength exercise, **When** the coach records a progress note, **Then** it is saved and visible only to coach/admin roles.
2. **Given** progress notes exist for multiple athletes, **When** the coach navigates the module, **Then** no UI surface presents an athlete-to-athlete comparison, ranking, or leaderboard.

---

### Edge Cases

- What happens when the coach adds exercises whose suggested durations sum to exactly 30 minutes (the "at" boundary) versus 30 minutes + 1 (the "over" boundary)? The indicator MUST distinguish within / at / over.
- How does the system handle an exercise that is valid for both age bands — it MUST appear under both 10-12 and 13-15 filters and never trigger a guardrail warning.
- What happens when a strength block is attached to a session and the session is later deleted? The block's relationship to the session MUST resolve without orphaning or corrupting the block.
- How does the system behave when the seeded catalog has no exercise matching an active filter combination (e.g., "gym-equipment" + "10-12", which the club's rules make sparse or empty)? An empty-state message MUST be shown rather than an error.
- How does the tablet-in-field, intermittent-connectivity context (the coach's primary device) affect browsing an already-loaded catalog? Read/browse of the catalog SHOULD degrade gracefully.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present a searchable, browsable catalog of strength-training exercises to coach and admin roles.
- **FR-002**: System MUST tag every exercise with an equipment requirement of at least two categories: no-equipment/bodyweight and gym-equipment.
- **FR-003**: System MUST tag every exercise with the age band(s) for which it is appropriate, using the club's two established chronological bands (10-12 and 13-15). An exercise MAY be valid for both bands.
- **FR-004**: System MUST tag every exercise with a movement category (a small fixed taxonomy such as upper-body push, upper-body pull, lower-body bilateral, lower-body single-leg/split, core/stability).
- **FR-005**: Coach MUST be able to filter and free-text search the catalog by equipment availability and by age band, with filters combinable.
- **FR-006**: System MUST display, for each exercise, an original illustration (own diagram/ASCII or original static artwork) and MUST NOT display any licensed third-party photograph or externally-hosted image asset.
- **FR-007**: System MUST display, for each exercise, a plain-language execution description and a list of common execution errors.
- **FR-008**: Coach MUST be able to assemble selected exercises into a named "strength block".
- **FR-009**: System MUST show, in real time during assembly, the running estimated total duration of the block and MUST indicate whether it is within, at, or over a 30-minute target. The 30-minute value is a coach product rule, NOT a scientifically-derived limit, and MUST be treated as a configurable business rule; acceptance criteria and UI copy MUST NOT imply clinical/scientific backing for the exact figure.
- **FR-010**: System MUST associate a suggested duration and/or reps with each exercise entry within a block so the running total is computable and visible.
- **FR-011**: System MUST enforce an age-band appropriateness guardrail when adding an exercise to a block that targets a specific age band. When the coach attempts to add an exercise not appropriate for the target band, the system MUST surface a clear, plain-language warning explaining why, and MUST allow the coach to proceed only via an explicit confirmation ("warn-and-allow"); each such override MUST be recorded (which exercise, which block, target band) for later coach review. Rationale: this honors the club's "flexible plan" principle (coach professional judgment for legitimate edge cases) while preserving a safety audit trail. (Decision pending final confirmation in `/speckit-clarify`; hard-block and shown-but-blocked-no-override were the considered alternatives.)
- **FR-012**: Coach MUST be able to attach an assembled strength block to a new or existing training session in the existing Training Sessions module, and the block MUST then appear within that session's plan.
- **FR-013**: System MUST persist strength blocks and their exercise entries so they remain present and editable when a session is reopened.
- **FR-014**: Coach MUST be able to record and update per-athlete progress notes on strength exercises, visible only to coach/admin roles.
- **FR-015**: System MUST NOT expose any athlete-to-athlete comparison, ranking, or leaderboard of strength progress on any screen.
- **FR-016**: System MUST ship with a pre-seeded starter catalog covering both equipment categories and both age bands, with the 10-12 band containing only bodyweight/no-structured-loading exercises consistent with the club's dosing rules.
- **FR-017**: System MUST restrict all creation, assembly, guardrail, and progress-note capabilities to coach/admin roles; parents and athletes MUST NOT have access to this module in v1.
- **FR-018**: System MUST NOT include AI/LLM-generated content, recommendations, or coaching commentary; the catalog is static curated content (same posture as spec 018).
- **FR-019**: System MUST NOT include calorie counting, nutrition/body-composition capture, supplement guidance, 1RM/max-strength testing protocols, or complex Olympic lifts (clean/snatch/deadlift/back-squat) as prescribable content.
- **FR-020**: System MUST NOT expose any minor's personal data (DOB, medical data) in logs, exports, or shared views; progress notes are coach-only and privacy-preserving.

### Key Entities *(include if feature involves data)*

- **Strength Exercise**: A single curated exercise. Attributes: name, movement category, equipment requirement (no-equipment / gym-equipment), appropriate age band(s), original illustration reference, execution description, common-errors list, suggested duration/reps default.
- **Strength Block**: A named, coach-assembled ordered collection of exercise entries with a computed running total duration and a target-age-band context used by the guardrail. Attachable to one or more training sessions.
- **Block Exercise Entry**: The inclusion of a Strength Exercise within a Strength Block, carrying its per-block suggested duration/reps.
- **Strength Progress Note**: A coach-only, per-athlete record of completion/progress against a Strength Exercise. No comparative semantics.
- **Training Session (existing)**: The Phase 1.5 entity to which a Strength Block is attached; reused, not redefined by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can find an age-appropriate, correctly-illustrated strength exercise for a given equipment situation in under 30 seconds from opening the module.
- **SC-002**: A coach can assemble a strength block and attach it to a training session in under 3 minutes.
- **SC-003**: 100% of exercises shown in any context use original illustrations only — zero licensed third-party photographs appear anywhere in the module.
- **SC-004**: 100% of saved blocks targeting the 10-12 age band contain only bodyweight/no-structured-loading exercises (guardrail effectiveness), measured over a review period.
- **SC-005**: The running-duration indicator correctly classifies within / at / over the 30-minute target in 100% of assembly interactions.
- **SC-006**: Zero screens in the module present an athlete-to-athlete strength comparison (privacy/UX compliance), verified by review.
- **SC-007**: The seeded starter catalog covers both equipment categories and both age bands on day one, with at least one usable exercise in every non-empty valid filter combination defined by the club's dosing rules.

## Assumptions

- The coach (and admin) is the sole user of this module in v1; parents and athletes have no access. This matches the coach-only, no-comparison posture of the technique library (spec 018) and the club's minors-privacy principle.
- The 30-minute ceiling is a coach-stated product preference, not a training-science finding (deep-research found no primary source for the exact figure). It is modeled as a configurable business rule, and copy avoids implying clinical justification.
- The feature organizes exercises by the club's two established chronological age bands (10-12 / 13-15) rather than by PHV/maturation stage. This is a deliberate, partial expression of the club's "biological age > chronological age" principle — PHV-stage modeling is explicitly out of scope for v1 because research rated PHV "windows of trainability" as low-empirical-support heuristics.
- Illustration follows the club's own-artwork precedents: ASCII/diagram (spec 018) and original SVG (spec 019). No third-party photo library is used, since such images are typically adult stock photography unsuitable for a minors product; open datasets like free-exercise-db (Unlicense/public domain) may inform text/taxonomy only, not imagery.
- Strength blocks integrate into the existing Training Sessions module (Phase 1.5) using its existing assembly/attachment pattern, mirroring how technique/gymkhana content already integrates; no parallel session infrastructure is built.
- A strength block may be attached to more than one training session (reusable); attaching does not force a copy. To be confirmed if the coach expects per-session isolated copies instead.
- Age-band guardrail enforcement is resolved as **warn-and-allow with a recorded override** (FR-011), chosen over hard-block / shown-but-blocked to honor the club's "flexible plan" non-negotiable while keeping a safety audit trail. This is the one decision most worth re-confirming with the coach in `/speckit-clarify`.
- Movement-competency gating between the progression steps within 13-15 (bodyweight → bands → dumbbells → supervised free weights) is treated as original club design, not sourced from any position stand. v1 assumes age-band gating only (no intra-band competency gates); intra-band gating is deferred to clarification/planning.

## Out of Scope (v1)

- AI/LLM-generated content, recommendations, or coaching commentary (static curated content — same posture as spec 018).
- Calorie counting, load/weight tracking tied to nutrition, or body-composition data capture.
- Supplement guidance or references (zero-supplement principle for <18).
- Athlete-facing comparison, leaderboard, or ranking of strength progress.
- Automated 1RM/max-strength testing protocols, or complex Olympic lifts (clean/snatch/deadlift/back-squat) as prescribable content.
- Wearable/sensor integration for load tracking (RPE-primary, no-power-meter-<13 principle applies to any future extension).
- PHV/maturation-stage modeling of exercise eligibility (chronological bands only in v1).
