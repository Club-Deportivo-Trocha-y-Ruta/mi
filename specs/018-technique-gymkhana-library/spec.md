# Feature Specification: Technique & Gymkhana Library + Session Builder

**Feature Branch**: `claude/spec-kit-agent-setup-poepvz` (developed on the designated session branch; spec directory `018-technique-gymkhana-library`)

**Created**: 2026-06-25

**Status**: Draft

**Input**: User description: "Technique & Gymkhana Library + Session Builder — a new module so the coach can browse a catalog of technique drills and gymkhana exercises (by skill, age band 7–15, difficulty, materials), see illustrative circuit layouts with the club's real materials (cones, tires, stakes, curbs), assemble them into a training session reusing the existing Training Sessions module, and track each athlete's technical progress per skill across the season. Catalog pre-seeded from the verified research report `docs/14-tecnica-gymkana-7-15/research.md` and editable by the coach/admin."

## Overview

The Technique & Gymkhana Library is a new module that turns the club's scattered skill-development know-how into a single, searchable, in-app resource and ties it to real planning and athlete tracking. The coach can browse and filter a catalog of technique drills and gymkhana exercises by skill, age band (7–9, 10–12, 13–15), difficulty, and required materials; open any exercise to see how to run it and an illustrative layout of the circuit (cone/tire/stake/curb placement); assemble chosen exercises into a technique session that is saved through the **existing Training Sessions module** (no duplicate session system); and record each athlete's progress per skill over the season as personal, coach-mediated growth.

Its purpose is to make the club's first non-negotiable priority — **skills before fitness** — practical, fast, and consistent, and to make per-athlete technical progress visible for the first time. It is explicitly **not** a fitness/load-prescription tool, **not** a comparison/ranking surface, and **not** an automated skill assessor.

> **Language note**: This spec is a development artifact written in English per the project working-language policy (Constitution Principle III). All coach- and admin-facing copy in the running product (UI strings, exercise content, labels, messages) MUST be in español neutro (Colombia). The catalog content seeded from `docs/14-tecnica-gymkana-7-15/research.md` MUST be presented to users in Spanish.

> **Scope note (age span)**: The platform today centers on ages 10–15. This module extends the *content* reach to **7–15** to support the FUNdamentals (7–9) stage. Athlete records for the 7–9 band may not yet exist; the catalog and session-building MUST work regardless, and per-athlete progress tracking applies only to athletes who have a record in the system.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse and search the technique & gymkhana catalog (Priority: P1)

The coach opens the module and browses a catalog of technique drills and gymkhana exercises. They filter by skill (e.g., balance, vision, braking, slow-speed control, cornering, body–bike separation, pressure/terrain, gears & cadence), by age band (7–9, 10–12, 13–15), by difficulty, and by the materials available that day (e.g., only cones and tires). The catalog comes pre-loaded with the club's researched exercise bank.

**Why this priority**: This is the entry point and the minimum viable value on its own — a coach with nothing else gains a usable, filterable reference library of age-appropriate skill drills in the field. Without it there is nothing to view, assemble, or track against.

**Independent Test**: Sign in as a coach, open the catalog, and confirm it is pre-seeded with the researched exercise bank; apply a skill filter, an age-band filter, a difficulty filter, and a materials filter (alone and combined) and confirm only matching exercises are shown. Delivers a working reference library.

**Acceptance Scenarios**:

1. **Given** a coach with no exercises created, **When** they open the catalog for the first time, **Then** it is already populated with the seeded researched exercise bank (~24 exercises spanning the three age bands).
2. **Given** the catalog, **When** the coach filters by the age band "7–9", **Then** only exercises appropriate for that band are listed.
3. **Given** the catalog, **When** the coach filters by a skill (e.g., "frenado") and a difficulty (e.g., "fácil"), **Then** only exercises matching both criteria are listed.
4. **Given** the coach has only cones and tires available, **When** they filter by those materials, **Then** the list shows only exercises that can be run with cones and/or tires (including no-equipment exercises).
5. **Given** an empty filter result, **When** no exercise matches the combination, **Then** a clear empty state is shown (not a blank screen or an error).

---

### User Story 2 - View an exercise with its illustrative circuit layout (Priority: P1)

The coach opens a single exercise and sees everything needed to run it: the skill it builds, the recommended age band and difficulty, the materials needed, a step-by-step way to run it (including a structured coaching method and a mastery-climate framing), and an **illustrative layout** showing how to place cones, tires, stakes, and curbs for the circuit.

**Why this priority**: A list without runnable detail is not actionable in the field. The illustrative layout is the core differentiator the coach asked for ("debe ser ilustrativo, con conos, topes, estacas, llantas"). Paired with US1 this already delivers a complete field reference.

**Independent Test**: Open any seeded exercise and confirm it displays skill, age band, difficulty, materials, run-it steps with a coaching method and mastery framing, and an illustrative circuit layout. Delivers a runnable, self-contained exercise card.

**Acceptance Scenarios**:

1. **Given** an exercise in the catalog, **When** the coach opens it, **Then** the detail shows its skill, recommended age band(s), difficulty, and the list of required materials.
2. **Given** a gymkhana exercise, **When** the coach opens it, **Then** an illustrative layout of the circuit (placement of cones/tires/stakes/curbs) is shown.
3. **Given** an exercise detail, **When** the coach reads the "how to run it" section, **Then** it includes a step-by-step coaching method and framing centered on personal progress and effort (mastery climate), never on winning or comparison.
4. **Given** a no-equipment exercise, **When** the coach opens it, **Then** the materials section clearly indicates that no materials are required.

---

### User Story 3 - Assemble a technique session saved through the existing Training Sessions module (Priority: P1)

The coach selects several exercises from the catalog and assembles them into a technique training session (warm-up / main set / cool-down). On saving, the session is created as a **normal club training session** in the existing Training Sessions module — so it appears in the calendar and supports the existing attendance and rubric flows — rather than as a separate, duplicated record.

**Why this priority**: Turning the library into a saved, schedulable session is the bridge from "reference" to "planning". Reusing the existing module is what prevents this feature from forking session management.

**Independent Test**: Select two or more exercises, assemble them into a session, save, and confirm the result is a training session in the existing module (visible in the calendar / session list) that references the chosen exercises and supports attendance/rubric. Delivers a ready-to-run, scheduled technique session.

**Acceptance Scenarios**:

1. **Given** the catalog, **When** the coach adds exercises to a new technique session and saves it, **Then** a training session is created in the existing Training Sessions module (not in a separate session store).
2. **Given** a saved technique session, **When** the coach opens it from the calendar/session list, **Then** the selected exercises are listed within it and the session supports the existing attendance and rubric flows.
3. **Given** a technique session in progress, **When** the coach assembles it, **Then** they can place exercises into warm-up, main set, and cool-down segments consistent with the club's session format.
4. **Given** an assembled session, **When** the coach finds an age-appropriate set of exercises in the catalog, **Then** the full find-and-assemble flow can be completed in under 3 minutes.
5. **Given** a session built with exercises from more than one age band, **When** the coach saves it, **Then** the system allows it but surfaces a visible notice that the session mixes age bands.

---

### User Story 4 - Record and review per-athlete skill progress across the season (Priority: P2)

For each athlete who has a record in the system, the coach records and reviews technical progress per skill — for example, marking a skill as introduced, in progress, or mastered — and sees how that has evolved over the season. Progress is framed as personal growth anchored to the athlete's biological age (PHV), and is never displayed as a ranking or athlete-vs-athlete comparison.

**Why this priority**: This is the "make progress visible" value, but the module is already useful without it (US1–US3). It also introduces the only minors'-data surface, so it is deliberately a separate, later slice with its own privacy guarantees.

**Independent Test**: As a coach, set a per-skill status for one athlete, change it later, and view a per-athlete progress view that shows current status per skill and its history across the season — with no surface that compares this athlete to another. Delivers visible, individual technical progress.

**Acceptance Scenarios**:

1. **Given** an athlete with a record, **When** the coach sets a skill's status (e.g., "en progreso"), **Then** the status is saved for that athlete and that skill.
2. **Given** a skill status that changes over time, **When** the coach reviews the athlete, **Then** they see the current status per skill and how it evolved across the season.
3. **Given** the athlete's progress view, **When** it is rendered, **Then** it is anchored to the athlete's own trajectory and biological age, and contains no leaderboard or comparison against other athletes.
4. **Given** progress data for minors, **When** any view, log, export, or AI prompt is produced, **Then** it contains no exposure of a minor's PII beyond what the authenticated coach/admin is authorized to see in-app.
5. **Given** an athlete in the 7–9 band without a full record, **When** the coach attempts per-athlete tracking, **Then** the system handles the absence gracefully (tracking applies only to athletes who have a record).

---

### User Story 5 - Curate the catalog: add, edit, and hide exercises (Priority: P3)

The coach or admin tailors the catalog to the club: adding their own exercises, editing seeded ones (e.g., adjusting materials or the layout to match local conditions), and hiding exercises they don't use — without permanently deleting curated content others may rely on.

**Why this priority**: The seeded bank covers the MVP, so curation is valuable but not required for first value. It keeps the library a living resource over time.

**Independent Test**: As a coach/admin, add a new custom exercise (with skill, age band, difficulty, materials, layout), confirm it appears in browse/filters; edit a seeded exercise and confirm the change persists; hide an exercise and confirm it no longer appears in the default catalog. Delivers a maintainable, club-specific library.

**Acceptance Scenarios**:

1. **Given** a coach/admin, **When** they create a new exercise with skill, age band, difficulty, materials, and layout, **Then** it appears in the catalog and is reachable through the relevant filters.
2. **Given** a seeded exercise, **When** a coach/admin edits its fields, **Then** the edits persist and are reflected in the detail and filters.
3. **Given** an exercise the club doesn't use, **When** a coach/admin hides it, **Then** it no longer appears in the default catalog but is not destroyed.
4. **Given** an exercise referenced by an already-saved technique session, **When** it is hidden or edited, **Then** the previously saved session remains intact and viewable.

---

### Edge Cases

- **All exercises hidden / no matches**: the catalog shows a clear empty state with a way to clear filters or unhide content.
- **Exercise with no materials**: bodyweight/no-equipment exercises are first-class and discoverable when filtering by "sin material".
- **Mixed-age session**: assembling exercises across age bands is permitted but visibly flagged (age-appropriateness is the coach's call, with a nudge).
- **7–9 athlete without a record**: per-athlete progress tracking degrades gracefully and is simply unavailable for athletes who have no record.
- **Field use on intermittent 3G / cold start**: browsing, viewing layouts, and assembling must present clear loading/offline/"server starting" states rather than spinners or raw errors.
- **Referenced content changes**: hiding, editing, or removing an exercise must never corrupt or blank out a previously saved technique session.
- **Attempted comparison**: there is no path, view, or export that ranks or compares athletes against each other on skill progress.
- **Difficulty vs. age mismatch**: surfacing an advanced (difficulty ③) drill while filtering the 7–9 band is prevented or clearly warned, consistent with the differentiated methodology.

## Requirements *(mandatory)*

### Functional Requirements

**Catalog & discovery**
- **FR-001**: The system MUST provide a catalog of technique drills and gymkhana exercises that the coach can browse.
- **FR-002**: The system MUST allow filtering the catalog by skill, by age band (7–9, 10–12, 13–15), by difficulty, and by required materials, individually and in combination.
- **FR-003**: The system MUST organize exercises against a defined skill taxonomy covering at least: position & balance, vision, braking, slow-speed control, cornering, body–bike separation, pressure/terrain, and gears & cadence.
- **FR-004**: The system MUST present a clear empty state when no exercise matches the active filters.
- **FR-005**: The catalog MUST be pre-seeded, on first use, with the club's researched exercise bank and circuit layouts sourced from `docs/14-tecnica-gymkana-7-15/research.md` (~24 exercises spanning the three age bands), in español neutro (Colombia).

**Exercise detail & illustrative layout**
- **FR-006**: For each exercise, the system MUST show the skill it builds, recommended age band(s), difficulty, and required materials.
- **FR-007**: For each exercise, the system MUST show how to run it, including a step-by-step coaching method and a framing centered on personal progress, effort, and coping (mastery climate).
- **FR-008**: For each gymkhana exercise, the system MUST show an illustrative layout depicting the placement of materials (cones, tires, stakes, curbs, and the like).
- **FR-009**: The system MUST treat no-equipment exercises as first-class and clearly indicate when no materials are required.

**Session assembly (reusing Training Sessions)**
- **FR-010**: The coach MUST be able to select multiple exercises and assemble them into a technique session organized into warm-up, main set, and cool-down segments consistent with the club's session format.
- **FR-011**: On save, the system MUST persist the assembled technique session **through the existing Training Sessions module** as a normal club training session — it MUST NOT create a separate, parallel session store.
- **FR-012**: A saved technique session MUST be visible where club training sessions already appear (calendar/session list) and MUST support the existing attendance and rubric flows.
- **FR-013**: A saved technique session MUST retain the set of exercises it was built from, viewable from the session.
- **FR-014**: The system MUST allow a session that mixes age bands but MUST surface a visible notice when it does.

**Per-athlete skill progress**
- **FR-015**: The coach MUST be able to record, per athlete and per skill, a progress status, and to update it over time.
- **FR-016**: The system MUST let the coach review an athlete's current status per skill and its evolution across the season.
- **FR-017**: Per-athlete progress MUST be framed as individual growth anchored to the athlete's own trajectory and biological age (PHV); the system MUST NOT present any ranking or athlete-vs-athlete comparison of skill progress.
- **FR-018**: Per-athlete progress tracking MUST apply only to athletes who have a record in the system and MUST degrade gracefully when a record (e.g., a 7–9 rider) does not exist.

**Curation**
- **FR-019**: A coach/admin MUST be able to add new exercises (with skill, age band, difficulty, materials, run-it content, and layout), edit existing exercises (including seeded ones), and hide exercises.
- **FR-020**: Hiding or editing an exercise MUST NOT alter or corrupt any previously saved technique session that referenced it.

**Access, privacy & principles**
- **FR-021**: Access to the module MUST be restricted to the coach and admin roles; the module MUST NOT expose any athlete- or parent-facing view in this version.
- **FR-022**: Any handling of per-athlete progress MUST uphold minors'-privacy rules: no minor PII in logs, error messages, public outputs, or third-party/AI prompts; access limited to authorized coach/admin in-app.
- **FR-023**: All user-facing copy and seeded content MUST be in español neutro (Colombia) and MUST avoid judgmental or clinical language about minors.
- **FR-024**: Content and recommendations MUST embody the club's non-negotiables: fun first; skills before fitness; biological > chronological age; cadence ≥60 rpm (and ≥70 for these ages); RPE as the primary intensity guide; and the differentiated age-band methodology (7–9 play-based with no structured intervals; 10–12 with play predominating; 13–15 limited to at most 2 high-intensity sessions per week).
- **FR-025**: The system MUST support 7–15 content even though the platform's athlete records center on 10–15; catalog browsing, exercise detail, and session assembly MUST NOT require a 7–9 athlete record to function.

### Key Entities *(include if feature involves data)*

- **Technique Exercise**: a drill or gymkhana exercise. Attributes (conceptual): name, description, the skill(s) it builds, recommended age band(s), difficulty, required materials, "how to run it" content (coaching method + mastery framing), an illustrative circuit layout, and a visibility/seeded flag. Belongs to one or more skills; may require zero or more materials.
- **Skill**: an entry in the club's technique taxonomy (e.g., balance, vision, braking, cornering, body–bike separation, pressure/terrain, gears & cadence). Used to organize exercises and to track per-athlete progress.
- **Material**: a physical item used in an exercise (cone, tire, stake, curb/kerb, plank/pallet, bottle, rope, branch, etc.), including a "none" case. Used for filtering and for the layout.
- **Circuit Layout**: the illustrative depiction of how materials are placed for a gymkhana exercise; associated with a Technique Exercise.
- **Technique Session (via Training Sessions)**: not a new session entity — a club training session, created through the existing module, that references the set of Technique Exercises it was assembled from, arranged into warm-up / main set / cool-down.
- **Athlete Skill Progress**: per athlete and per skill, the current progress status and its history over the season. Minors' data; coach/admin only; never comparative.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can find an age- and difficulty-appropriate set of exercises and assemble a complete technique session in **under 3 minutes**.
- **SC-002**: On first use, the catalog is populated with the full researched exercise bank (**~24 exercises** across the 7–9, 10–12, and 13–15 bands) and their circuit layouts, with **no manual data entry required** to start.
- **SC-003**: For any age band + skill + materials combination a coach selects, the catalog returns the matching exercises (and a clear empty state when there are none) on the **first attempt**, with **100%** of seeded exercises reachable through at least one filter path.
- **SC-004**: For any athlete with a record, the coach can see at a glance **which skills are introduced / in progress / mastered** and how each has changed across the season.
- **SC-005**: **Zero** surfaces in the module rank or compare athletes against each other on skill progress (verified by inspection of every progress view and export).
- **SC-006**: **100%** of technique sessions created in the module appear as normal club training sessions in the existing calendar/session list (no parallel/duplicate session records exist).
- **SC-007**: **Zero** athlete- or parent-facing exposure of the module in this version (coach/admin only), and **zero** minor-PII leakage into logs or external/AI prompts.

## Assumptions

- **Progress granularity (resolving the original open question)**: per-skill progress uses a **simple 3-state status — introduced / in progress / mastered** ("introducido / en progreso / dominado"), optionally with a short coach note. This matches the wording already used in the feature's success outcomes. A numeric level or reuse of the existing session-rubric scale was considered and set aside for v1; this can be revisited in `/speckit-clarify` if the coach prefers a finer scale.
- **Access**: coach and admin only in v1. No parent or athlete views. Athletes do not log in.
- **Seeding source**: the catalog is seeded from `docs/14-tecnica-gymkana-7-15/research.md` (the verified research report containing the 24-exercise bank, the A–H skill taxonomy, and the ASCII circuit layouts). Seeded content is editable and hideable but not silently lost.
- **Session reuse**: technique sessions are persisted through the existing Training Sessions module rather than a new session system; the existing attendance/rubric flows apply unchanged.
- **Illustrative layout representation**: the *that* (an illustrative layout per gymkhana exercise) is in scope; the *how* it is rendered (text diagram, generated graphic, or uploaded image) is deferred to `/speckit-plan`.
- **Biological age**: per-athlete progress references the athlete's biological age via the platform's existing PHV/maturation data; this module does not recompute maturation.
- **Age-span extension**: 7–9 content is supported even though athlete records may not exist for that band yet; per-athlete tracking simply applies only where a record exists.
- **Mastery climate**: progress and content framing follow the club's mastery-climate stance (process/effort over results), consistent with how the club already frames athlete-facing material.
- **Connectivity**: coaches use this on a tablet in the field over intermittent 3G/4G and against a backend that may cold-start; loading/offline/"server starting" states are expected on every async surface.

## Dependencies

- The existing **Training Sessions module** (sessions, calendar/list, attendance, rubric) — technique sessions are created through it.
- The existing **athlete records and PHV/maturation data** — used to anchor per-athlete progress to biological age.
- The existing **role/permission model** (admin, coach, parent) — used to restrict the module to coach/admin.
- The research artifact **`docs/14-tecnica-gymkana-7-15/research.md`** — source of the seeded catalog content and layouts.
