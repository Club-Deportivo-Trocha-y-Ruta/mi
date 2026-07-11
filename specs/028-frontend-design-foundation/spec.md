# Feature Specification: Frontend Design Foundation & Everyday Reliability

**Feature Branch**: `claude/coach-profile-ux-analysis-kaar7d`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Run /speckit-specify for each feature until 033" — feature 1 of 6. Covers phases 0 (bugs & quick wins) and 1 (component & token foundation) of the coach experience redesign program (`docs/17-coach-ux-redesign/proposal.md` §3, §7–§9, §13; program spec: `specs/027-coach-experience-redesign/spec.md`, Story 1).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Field controls that work with gloves in the sun (Priority: P1)

The coach, on a tablet outdoors, can operate every daily control — above all the effort rubric — with gloved fingers and read every label in direct sunlight.

**Why this priority**: The effort rubric is the single most-used field control and today its slider thumbs measure 20×20 px against the project's 48×48 px rule; secondary text uses a contrast level below the project's own sunlight bar. This story alone removes the worst daily friction.

**Independent Test**: On a touch device (or emulation), record attendance and the full effort rubric (RPE, esfuerzo, actitud, técnica) for several athletes wearing gloves; measure every interactive target; check secondary text contrast against the project's stricter token.

**Acceptance Scenarios**:

1. **Given** the effort rubric, **When** the coach records any of its four values, **Then** each value is set by tapping discrete step controls (no drag sliders) and every step target measures at least 48×48 px.
2. **Given** any coach screen, **When** measured on a real rendering engine, **Then** every interactive control (table row actions, duration fields, analysis buttons) is at least 48×48 px.
3. **Given** small or secondary text on coach surfaces (slider labels, table timestamps, form hints), **When** rendered, **Then** it uses the project's stricter sunlight-readability contrast (the existing high-contrast token today used only in the parent portal).
4. **Given** the media uploader on a tablet, **When** the coach adds a photo during a session, **Then** they can open the camera directly instead of only the gallery picker.

---

### User Story 2 - Never dead-ended (Priority: P1)

Whatever fails or wherever the coach or admin taps, there is always a way forward: failed loads offer retry, no visible link silently bounces, and small broken behaviors (calendar day tap, stale season, dead styling) are fixed.

**Why this priority**: These are confirmed defects: four admin-visible surfaces link to a coach-only screen and silently redirect; four high-traffic pages have no retry on failure (on rural 3G, transient failure is the common case); the calendar's day-tap handler is empty; one screen hardcodes the season year.

**Independent Test**: As admin, click every athlete name on the dashboard, competition views, and newsletter detail — none may silently bounce. Throttle the network to fail loads on sessions, athletes, dashboard, and calendar — each shows a retry that recovers. Tap an empty calendar day — event creation opens with the date prefilled.

**Acceptance Scenarios**:

1. **Given** an admin on any screen showing athlete names, **When** they interact, **Then** each name is either a working link or plain non-interactive text — never a silent redirect.
2. **Given** any data view whose load fails, **When** the failure occurs, **Then** a friendly message with a visible retry action appears, retry reloads only that view, and raw technical error text is never shown.
3. **Given** the club calendar, **When** the coach taps an empty day, **Then** event creation starts with that date prefilled.
4. **Given** any season-scoped screen, **When** the year changes, **Then** the season follows the current date automatically (no hardcoded year).
5. **Given** the monthly newsletter overview on a slow connection, **When** it opens, **Then** all athletes' statuses load as one summary (no one-request-per-athlete waterfall) within the project's page-load budget.

---

### User Story 3 - One consistent feedback language (Priority: P2)

Every action responds the same way everywhere: destructive actions use one confirmation dialog with safe defaults, long-running work shows progress on the triggering control, outcomes are confirmed with brief non-blocking notifications, and multi-step flows announce each step to assistive technology.

**Why this priority**: Today there are three different confirmation mechanisms (including browser-native prompts), hand-rolled one-off notifications, buttons that go silent during multi-second AI generations, and wizards that never move focus on step change. Consistency here is what makes the app feel like one product and is required by the constitution's UX principle.

**Independent Test**: Trigger every destructive action (delete athlete, media, session cancellation with parent notification) and every long-running generation (report, newsletter, AI analysis): confirm one dialog pattern (safe default focus, Escape dismisses, focus returns), visible in-progress states, and consistent completion notifications; walk both wizards with a screen reader and verify step announcements.

**Acceptance Scenarios**:

1. **Given** any destructive action, **When** the confirmation appears, **Then** it uses the app's single dialog pattern: initial focus on the safe option, Escape dismisses, focus returns to the trigger; browser-native prompts are gone.
2. **Given** any long-running operation, **When** it is in flight, **Then** the triggering control shows an in-progress state, and completion or failure is announced via a brief non-blocking notification, consistent app-wide.
3. **Given** a multi-step flow (session creation, results import), **When** the coach advances a step, **Then** the new step's heading receives focus and the change is announced to assistive technology.
4. **Given** the parent-notification dialog for session cancellation, **When** opened via keyboard or assistive technology, **Then** focus is trapped inside, Escape closes it, and focus is restored — like every other dialog.

---

### User Story 4 - Recognizably one product on every screen (Priority: P3)

Headers, empty states, error states, status labels, cards, and headings look and behave identically wherever the coach goes, and the documented brand heading font finally renders (program decision D3: ship it).

**Why this priority**: The same page furniture is hand-built dozens of times with drift (59 page headers, 37 empty states, 81 retry blocks, 6 status-label systems, 3 steppers), and the brand font has silently never loaded. This story sets the shared foundation later features build on; it follows the behavioral fixes because those deliver user value sooner.

**Independent Test**: Visual sweep across all coach modules: page headers, empty states, error states, and status labels are visibly uniform; headings render in the brand display font from one central definition; no per-screen font or shadow one-offs remain.

**Acceptance Scenarios**:

1. **Given** any two coach screens, **When** compared, **Then** their page header, empty state, error state, and status label presentation follow the same shared patterns.
2. **Given** the brand display font (decision D3), **When** any heading renders, **Then** it uses the self-hosted brand font applied through one central definition; the design-system document matches shipped reality.
3. **Given** status labels anywhere (sync, session, consent, freshness, newsletter), **When** rendered, **Then** they draw from one shared status vocabulary with an icon or text label — never color alone.

---

### Edge Cases

- **Server cold start (~50 s)**: retry affordances and skeletons must coexist with the existing "server waking" notice — a cold start is not an error.
- **Repeated retry taps**: retrying a failed save must not duplicate records; attendance autosave's per-row retry is the reference behavior.
- **Reduced motion**: the existing app-wide reduced-motion behavior must be preserved by any new feedback patterns.
- **Very small screens**: 48 px targets must not force horizontal scrolling on 360 px-wide viewports; controls wrap or stack instead.
- **Assistive tech on wizards**: moving focus on step change must not steal focus from an open validation error.
- **Automated size checks**: target-size verification must run on a real rendering engine (existing unit-test tooling cannot measure pixels) without making the suite flaky.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All interactive touch controls on coach surfaces MUST measure at least 48×48 px; the effort rubric MUST use discrete step controls instead of drag sliders.
- **FR-002**: Small/secondary text on coach surfaces MUST meet the project's stricter sunlight-readability contrast bar (the existing high-contrast token).
- **FR-003**: No visible control may lead to a silent redirect; links to screens the current role cannot open MUST be hidden or rendered as plain text (fixes the four admin-facing dead-click surfaces).
- **FR-004**: Every data-loading view MUST offer a visible retry on failure that reloads only that view; raw technical error text MUST never be shown; cold-start states MUST be distinguished from errors.
- **FR-005**: Tapping an empty calendar day MUST start event creation with that date prefilled.
- **FR-006**: Season-scoped screens MUST derive the season from the current date.
- **FR-007**: The monthly newsletter overview MUST load all athletes' statuses as one summary rather than one lookup per athlete.
- **FR-008**: All destructive actions MUST use one consistent confirmation dialog (safe option focused, Escape dismisses, focus returns, focus trapped); browser-native confirmation prompts MUST be removed.
- **FR-009**: Long-running operations MUST show in-progress feedback on the triggering control and confirm outcomes via brief non-blocking notifications, consistent app-wide.
- **FR-010**: Multi-step flows MUST move focus to and announce each new step for assistive technology.
- **FR-011**: Page headers, empty states, error states, stat cards, steppers, and status labels MUST be presented through shared patterns so any two screens are visually and behaviorally consistent; status labels MUST always pair color with an icon or text.
- **FR-012**: The documented brand display font MUST be shipped (self-hosted, no third-party font service) and applied to headings through one central definition (program decision D3); scattered per-component font references and dead styling tokens MUST be removed, and the design-system document MUST be updated to match shipped reality.
- **FR-013**: Media capture on tablets MUST offer direct camera access in addition to the gallery picker.
- **FR-014**: Fixes in this feature MUST NOT change any screen address, stored data, or role permissions.

### Key Entities

No new domain data. All changes are presentation and interaction behavior over existing records.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of interactive touch controls on coach surfaces measure at least 48×48 px, verified on a real rendering engine (today's worst: 20×20 px on the most-used field control).
- **SC-002**: 100% of data-loading coach views offer a retry affordance on failure (today: the four highest-traffic pages have none).
- **SC-003**: 0 visible links lead to silent redirects for any role (today: 4 admin-facing surfaces).
- **SC-004**: The coach can record the full effort rubric for one athlete with gloves in under 15 seconds without a single missed tap.
- **SC-005**: Exactly one confirmation-dialog pattern exists app-wide; 100% of destructive confirmations are Escape-dismissible with safe default focus (today: 3 mechanisms, one focusing the destructive action).
- **SC-006**: 100% of long-running operations show in-progress feedback; outcome notifications follow one pattern (today: at least one multi-second generation shows none).
- **SC-007**: The newsletter overview issues a constant number of data requests regardless of club size (today: one per athlete).
- **SC-008**: Headings across 100% of coach screens render in the brand display font from one central definition (today: 0% — 115 references to a font that never loads).
- **SC-009**: Landing and athlete-list pages continue to meet the project load budget (≤ 2.5 s to main content on a mid-tier Android over simulated 3G) after all foundation changes.

## Assumptions

- **Program context**: this is feature 1 of 6 (specs 028–033) derived from the program spec `specs/027-coach-experience-redesign` and `docs/17-coach-ux-redesign/proposal.md`; it corresponds to proposal phases 0+1 and program Story 1. It is the recommended first feature to implement because later features consume its shared patterns.
- **Decision D3 (resolved 2026-07-11)**: the brand display font is shipped and self-hosted; no third-party font service may be used (privacy).
- **Scope boundary**: behavioral and visual foundation only — no navigation regrouping (feature 030), no screen removals (029), no home redesign (031), no session-composition changes (032), no app-wide color-semantics sweep or AI identity work (033). The status-label vocabulary is *established* here and *swept across charts and modules* in 033.
- **Parent portal**: out of scope except where shared patterns are consumed by both surfaces; no parent-facing behavior may regress.
- **One backend addition is permitted**: the batched newsletter-status summary; everything else is presentation-layer.
- **Constitution alignment**: 48×48 px targets, WCAG 2.1 AA, dialog focus rules, loading/empty/error state coverage, and performance budgets are hard acceptance bars (Principles III–IV); accessibility checks run on page- and dialog-level components as required by Principle II.
