# Feature Specification: Session Content Unification

**Feature Branch**: `claude/coach-profile-ux-analysis-kaar7d`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Run /speckit-specify for each feature until 033" — feature 5 of 6. Covers phase 5 (flow redesigns: one attach model + session screen reorganization) of the coach experience redesign program (`docs/17-coach-ux-redesign/proposal.md` §6; evidence: `docs/17-coach-ux-redesign/agent-reports/01-ux-heuristics-workflows.md`; program spec: `specs/027-coach-experience-redesign/spec.md`, Story 5).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One way to build a complete session (Priority: P1)

The coach plans a complete training session — technique exercises, strength blocks, and interval structure — from the session itself, through one identical attach interaction for all three content types, never leaving the session context and never producing a duplicate session.

**Why this priority**: "Attach training content" is the core weekly planning act, and today it follows three contradictory patterns: intervals attach inline (the good one), strength requires building elsewhere and then searching for the target session, and technique could only create a brand-new duplicate session through a parallel path (removed in 029). Unifying on the inline pattern fixes the least consistent core workflow in the product.

**Independent Test**: Create a session, then from that session attach one set of technique exercises, one strength block, and one interval structure — verifying all three use the same interaction pattern, the session count does not grow, and each attachment is visible on the session afterward.

**Acceptance Scenarios**:

1. **Given** an existing session, **When** the coach adds technique exercises, **Then** the flow starts from the session, follows the same pattern as intervals (choose from the library or compose, then confirm), and results in the exercises attached to that same session.
2. **Given** an existing session, **When** the coach adds a strength block, **Then** the flow starts from the session and the block attaches to it without searching for the session by name.
3. **Given** a build screen opened from a session, **When** it opens, **Then** that session is already preselected as the target, and completing the build returns the coach to the session.
4. **Given** any of the three attach flows, **When** completed, **Then** exactly zero new sessions are created as a side effect, and the attached content appears in the session's plan.
5. **Given** the technique library (Biblioteca), **When** the coach starts a build from there instead of from a session, **Then** they are asked which session to attach to — with recent/upcoming sessions offered first — using the same pattern.

---

### User Story 2 - A session screen organized for work (Priority: P2)

The coach works on a session through at most four clearly named sections — summary, attendance, plan, media — instead of one continuous scroll of seven stacked blocks, with the active section preserved on refresh and back-navigation.

**Why this priority**: The session screen is the densest in the app and the coach's main field surface; today attendance (the most-used field tool) sits below route, details, and other blocks. Sectioning puts each mode of work one tap away. It follows the attach unification because the "plan" section is where the unified attach lives.

**Independent Test**: Open a session, switch between the four sections, refresh, and navigate back — the active section persists; verify attendance is reachable in one tap from the session header on a tablet.

**Acceptance Scenarios**:

1. **Given** a session, **When** it opens, **Then** content is organized into at most four sections — summary (details, route, status), attendance, plan (technique, strength, intervals, plan-vs-actual), media — with a default that favors the coach's most likely task.
2. **Given** an active section, **When** the coach refreshes or navigates away and back, **Then** the same section is active.
3. **Given** the plan section, **When** the coach reviews it, **Then** attached technique, strength, and interval content appear as one coherent plan with their attach/edit actions in place.
4. **Given** a session with none of the optional content, **When** the plan section renders, **Then** it shows purposeful empty states with the three attach actions — not blank space.

---

### User Story 3 - Today's session is one tap away (Priority: P3)

The coach finds today's session instantly: the sessions list offers a "hoy" shortcut, today's row is visually distinct, and the list's default view highlights what is imminent rather than requiring a scan of the whole month.

**Why this priority**: Finding today's session under field conditions is the highest-frequency navigation act; today it requires scanning a month-long list with identical rows. Small, isolated, and immediately felt — but less structural than the two stories above.

**Independent Test**: With sessions seeded across a month including today, open the sessions list and reach today's session in one interaction via the "hoy" shortcut; verify today's row is visually distinct without relying on color alone.

**Acceptance Scenarios**:

1. **Given** the sessions list with a session today, **When** it renders, **Then** a "hoy" shortcut surfaces it in one interaction and today's row is visually distinct (not by color alone).
2. **Given** no session today, **When** the coach uses the "hoy" shortcut, **Then** the next upcoming session is offered instead, clearly labeled.

---

### Edge Cases

- **Mid-attach connection loss**: a failed attach keeps the coach's selections and offers retry (028 standard); retrying must not attach duplicates.
- **Concurrent edits**: content attached from another device appears on the session after the standard data refresh — no stale duplicate attach actions.
- **Age-band safeguards**: the existing safety gates (bodyweight-only for 10–12 in strength; intensity-zone blocks/confirmations in intervals) apply identically inside the unified flow — unification must not create a path around them.
- **Long plans**: a session with many technique exercises, several strength blocks, and a full interval structure must remain navigable within the plan section (grouped, collapsible where long).
- **Deep links**: existing links into a session (e.g., from the activities review or plan-vs-actual comparison) keep working and land on the correct section.
- **Timezone**: "hoy" is computed in the club's timezone, consistent with the home tile (031).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Technique exercises, strength blocks, and interval structures MUST all attach to an existing session through one identical interaction pattern initiated from the session, modeled on the current inline interval flow.
- **FR-002**: Build screens opened from a session MUST preselect that session as the target and return the coach to the session on completion; attach flows MUST NOT create new sessions as a side effect.
- **FR-003**: Builds started from the library (not from a session) MUST ask which session to attach to, offering recent/upcoming sessions first, using the same pattern.
- **FR-004**: The session screen MUST be organized into at most four sections — summary, attendance, plan, media — with the active section preserved across refresh and back-navigation and reachable in one tap each.
- **FR-005**: The plan section MUST present attached technique, strength, and interval content as one coherent plan, with attach/edit/remove actions in place and purposeful empty states offering the three attach actions when empty.
- **FR-006**: Existing age-band safety gates for strength and interval content MUST apply unchanged within the unified flow — no new path may bypass a block or a confirm-and-record step.
- **FR-007**: The sessions list MUST offer a "hoy" shortcut (falling back to the next upcoming session when today is empty) and MUST visually distinguish today's row without relying on color alone.
- **FR-008**: All existing deep links into sessions MUST keep working and land on the appropriate section; no screen address changes.
- **FR-009**: Attach flows MUST meet the 028 feedback standards: in-progress states, non-blocking confirmations, retry without duplication.

### Key Entities

No new domain data. The feature reorganizes how existing session-content relationships (session ↔ technique exercises, strength blocks, interval structures) are created and presented; the relationships themselves already exist.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All three content types attach from the session screen through one identical pattern in at most 3 interactions each (today: one type cannot attach at all, one requires re-finding the session by search).
- **SC-002**: 0 duplicate sessions are created by attach flows (today: the technique path created one per use).
- **SC-003**: A coach can assemble a complete session (technique + strength + intervals) without ever leaving the session context, in under 3 minutes with library content prepared.
- **SC-004**: Attendance is reachable in 1 tap from the session header (today: below several scroll-lengths of other content).
- **SC-005**: The coach reaches today's session from the sessions list in 1 interaction (today: a visual scan of up to a month of identical rows).
- **SC-006**: The session screen's active section survives refresh and back-navigation 100% of the time.
- **SC-007**: 0 regressions in age-band safety behavior: every gate that blocks or requires confirmation today does so identically in the unified flow.

## Assumptions

- **Program context**: feature 5 of 6 (specs 028–033), program Story 5, proposal §6. Depends on 029 having removed the standalone technique builder (D4) — this feature restores session-assembly capability through the unified attach; recommended after 028 (feedback standards) and independent of 030/031.
- **The interval flow is the reference pattern**: attach-in-context with a library picker; the unification brings technique and strength up to it rather than inventing a new pattern.
- **Wizard scope unchanged**: session creation (the multi-step wizard) is not extended to include content attachment; content attaches on the session after creation, as intervals do today. Extending the wizard was considered and rejected as scope creep.
- **Age-band safeguards** (constitution Principle-level: minors safety) are reused exactly as implemented; this feature changes where flows start, not what they allow.
- **Language**: all new copy in español neutro (Colombia).
- **Scope boundary**: no library-catalog redesign (the technique/strength catalogs and their internal components are consolidated under 033's visual pass), no navigation changes (030), no home changes (031).
