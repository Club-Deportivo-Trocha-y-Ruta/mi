# Feature Specification: Coach Home Mission Control

**Feature Branch**: `claude/coach-profile-ux-analysis-kaar7d`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Run /speckit-specify for each feature until 033" — feature 4 of 6. Covers phase 4 (coach home) of the coach experience redesign program (`docs/17-coach-ux-redesign/proposal.md` §5; evidence: `docs/17-coach-ux-redesign/agent-reports/04-product-design-modern-patterns.md`; program spec: `specs/027-coach-experience-redesign/spec.md`, Story 4).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - "What's next" at a glance (Priority: P1)

When the coach opens the app, the first screen shows the next planned session (name, relative day, place — tap to open) and the next race with days remaining and its preparation guidance by race class (A: full taper 5–7 days; B: mini-taper 3–4 days; C: none), with urgency visually distinguished.

**Why this priority**: Today's landing shows three static counters with no links; the two questions the coach actually opens the app with — "what's the next session?" and "how far is the next race?" — require manual navigation and scanning. Both tiles can be built entirely from data the product already loads.

**Independent Test**: Seed data for the states (session today / in N days / none planned; race inside and outside its taper window; season finished) and verify each tile's content, link target, urgency treatment, and empty state.

**Acceptance Scenarios**:

1. **Given** at least one future planned session, **When** the coach lands, **Then** the next session's name, relative day ("hoy", "mañana", "en N días") and place are shown and tapping opens that session.
2. **Given** no planned future session, **When** the coach lands, **Then** the tile shows a purposeful empty state with a shortcut to plan one.
3. **Given** the competition calendar, **When** the coach lands, **Then** the next race shows days remaining and its class-based preparation guidance, and entering the taper window changes the tile's urgency treatment.
4. **Given** the season is over (no future race), **When** the coach lands, **Then** the race tile states it plainly instead of showing stale or empty data.
5. **Given** today's session exists, **When** the coach lands on any device, **Then** reaching it takes at most 2 interactions.

---

### User Story 2 - "What's pending" as an actionable inbox (Priority: P2)

The landing shows a pending-work list — race results to import, external activities to link, newsletters due this month, missing or expired consents, outdated AI analyses — each row with a count and a link to the exact place where it gets resolved, degrading gracefully while any count is unavailable.

**Why this priority**: These five chores are the coach's recurring administrative load; today each requires remembering to check a different screen. An inbox converts "remember to check" into "see and resolve". It is second priority because two counts need new server-side aggregates.

**Independent Test**: Seed pending work of each kind and verify each row's count and link; disable the aggregate-backed rows and verify the list renders without them (no errors, no empty placeholders).

**Acceptance Scenarios**:

1. **Given** unimported results, unlinked activities, or newsletters due, **When** the coach lands, **Then** each pending kind shows an accurate count and its row links to the screen where it is resolved.
2. **Given** missing/expired consents or outdated AI analyses (aggregate-backed counts), **When** the aggregates are available, **Then** their rows appear with accurate counts; **When** unavailable, **Then** the list renders gracefully without them.
3. **Given** zero pending work of every kind, **When** the coach lands, **Then** the inbox shows a positive all-clear state, not blank space.
4. **Given** any inbox row, **When** resolved at its destination, **Then** returning home reflects the updated count without a full reload.

---

### User Story 3 - Load planning against the club's own rule (Priority: P3)

The landing shows this week's planned training load per age band against the club's non-negotiable "weekly hours ≤ athlete age" cap, warning visibly as a band approaches or exceeds its cap.

**Why this priority**: This makes a core coaching principle visible where planning decisions start. It is third priority because it requires a new server-side aggregate and is advisory rather than blocking.

**Independent Test**: Seed planned sessions producing under-cap, near-cap, and over-cap weekly totals per age band and verify the meter's states and wording.

**Acceptance Scenarios**:

1. **Given** planned sessions this week, **When** the coach lands, **Then** planned load per age band is shown against its cap, with a clear visual difference between comfortable, near-cap, and over-cap.
2. **Given** an over-cap band, **When** displayed, **Then** the wording is advisory and process-framed (adjust the plan), never alarmist, and links to the sessions involved.
3. **Given** the aggregate is unavailable, **When** the coach lands, **Then** the tile degrades gracefully (absent or clearly "sin datos"), never blocking the rest of the home.

---

### User Story 4 - A home that respects roles and existing alerts (Priority: P2)

The admin's landing shows only content their role can open (with no links into coach-only screens), and the existing measurement alerts (overdue anthropometry, growth-spurt flags) remain exactly as they are today.

**Why this priority**: The redesigned home must not recreate the admin dead-click class of bug fixed in 028, and the measurement alerts are the one part of today's landing that already works well — they are explicitly preserved.

**Independent Test**: Land as admin and verify every visible element opens; land as coach and verify measurement alerts behave identically to before the redesign.

**Acceptance Scenarios**:

1. **Given** an admin landing, **When** it renders, **Then** every tile, row, and link is openable by admin; coach-only content is absent, not disabled.
2. **Given** the measurement alerts, **When** the home ships, **Then** their behavior (status chips, growth-spurt callouts, capped athlete list with links) is unchanged.
3. **Given** the server waking from cold start, **When** the coach lands, **Then** tiles show loading skeletons alongside the existing "server waking" notice — never error states during warm-up.

---

### Edge Cases

- **Cold start (~50 s)**: all tiles must present skeletons/degraded states during warm-up; retry affordances follow the 028 standard.
- **Season rollover**: on January 1 the race tile and any season-scoped content follow the new year automatically.
- **Same-day boundary**: a session today but already finished (by time) should not show as "hoy" pending; day math uses the club's timezone.
- **Large clubs on slow connections**: inbox counts must come from constant-size summaries — never one lookup per athlete.
- **Privacy**: the home shows counts and first-level info only; no minor's sensitive data (medical, psychological) appears on the landing; the consent row shows counts, not athlete lists, until opened at its destination.
- **Concurrent resolution**: two devices resolving the same pending item must not produce negative or stale-stuck counts (refetch on focus/return).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The coach landing MUST show the next planned session (name, relative day, place; tap to open) with a purposeful empty state offering creation when none exists.
- **FR-002**: The landing MUST show the next race with days remaining and class-based preparation guidance (A: full taper 5–7 days; B: mini-taper 3–4 days; C: none), visually distinguishing taper-window urgency, and stating plainly when the season has no future race.
- **FR-003**: The landing MUST show a pending-work inbox covering: results to import, activities to link, newsletters due this month, missing/expired consents, and outdated AI analyses — each row with a count and a link to its resolution screen.
- **FR-004**: Inbox rows whose counts are not yet available MUST be omitted gracefully; a zero-pending state MUST render as a positive all-clear.
- **FR-005**: When aggregate data is available, the landing MUST show planned weekly load per age band against the "weekly hours ≤ athlete age" cap with comfortable/near-cap/over-cap states and advisory, process-framed wording.
- **FR-006**: The existing measurement alerts MUST remain on the landing with unchanged behavior.
- **FR-007**: The admin landing variant MUST show only admin-openable content, with coach-only elements absent.
- **FR-008**: All landing data MUST come from constant-size summaries (never per-athlete request fans), MUST show skeletons during cold start, and MUST refresh counts when the coach returns to the home.
- **FR-009**: Season-scoped landing content MUST derive the season from the current date in the club's timezone.
- **FR-010**: The landing MUST NOT display any minor's sensitive personal data (medical, psychological, contact); pending-work rows show counts only.

### Key Entities

No new domain data. The home consumes read-only aggregates over existing records (sessions, race events, activities, newsletters, consents, analyses, anthropometry alerts). Up to three small server-side read-only summaries may be introduced: weekly load per age band, club-wide consent status counts, club-wide stale-analysis counts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On landing, the coach can state what's next (session and race, with preparation guidance) and what's pending (five counts) without navigating anywhere (today: none of this is visible on landing).
- **SC-002**: The coach reaches today's/next session from landing in at most 2 interactions.
- **SC-003**: Each pending-work row leads to its resolution screen in exactly 1 interaction, and resolving items is reflected on return without a manual reload.
- **SC-004**: 0 role dead-ends on the landing: 100% of visible elements are openable by the current role.
- **SC-005**: The landing keeps meeting the project load budget (≤ 2.5 s to main content on a mid-tier Android over simulated 3G) with a request count independent of club size.
- **SC-006**: The measurement alerts behave identically before and after (zero behavioral regressions).
- **SC-007**: In the weeks after release, the coach's first navigation of a session (opening the app to any concrete task) starts from a landing element at least 50% of the time — the home is used, not skipped.

## Assumptions

- **Program context**: feature 4 of 6 (specs 028–033), program Story 4, proposal §5. Best after 028 (feedback/retry standards) and 030 (the "Inicio" area exists); ships in two increments if needed — tiles with existing data first, aggregate-backed rows second.
- **Backend scope**: limited to the up-to-three read-only summaries named in Key Entities plus reuse of the batched newsletter summary from 028; no writes, no changes to AI pipelines or scoring.
- **Taper guidance** comes from the club's existing race-class definitions (A/B/C) already encoded in the product; the home surfaces it, it does not redefine it.
- **Measurement alerts** are preserved as-is by explicit decision — they are today's one well-functioning landing element.
- **Privacy**: minors-privacy rules apply in full (constitution Quality Gates); the landing is count-level only.
- **Scope boundary**: no navigation shell changes (030), no session-composition changes (032), no visual re-theming (033); the "hoy" shortcut inside the sessions list belongs to 032 — this feature covers the landing only.
