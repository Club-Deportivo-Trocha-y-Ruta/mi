# Feature Specification: Session Create/Edit Flow & UX Overhaul

**Feature Branch**: `claude/session-create-edit-ux-Ogacm`

**Created**: 2026-06-07

**Status**: Draft

**Input**: User description: "Improve flow, ui/ux to create, edit session."

## Clarifications

### Session 2026-06-07

- Q: Which structure should the create/edit flow use? → A: Stepped wizard (multi-step,
  reusing the existing ImportWizard stepper pattern; each step validates before advancing)
- Q: What is the scope of the P3 nice-to-haves (clone session, smart prefills, pre-submit
  review summary) for this feature? → A: Defer all P3 to a follow-up spec; ship P1+P2 only
- Q: How should the route file (.gpx/.fit) be attached "in one pass" given the backend
  only accepts it after the session exists? → A: Client auto-uploads the file to the
  existing endpoint immediately after the session is created (no new backend contract)

## User Scenarios & Testing *(mandatory)*

The two product users of this flow are the **coach** (and admin), who plans and edits
training sessions — frequently on a tablet or phone in the field over intermittent
3G/4G — and, indirectly, the **parents**, who receive notifications about the sessions
their child is called up to. The flow must be faster, clearer, and resilient to
interruptions, while never losing an existing capability and never leaking minors' data.

### User Story 1 - Plan a session without losing data, with everything persisted (Priority: P1)

A coach opens "New session", fills in the date, time, duration, location, technical
focus, description, the session kind (e.g. training / joint activity / outing / other),
and its objectives, selects the athletes called up, optionally records route notes and a
Strava link, and saves. Every field the form shows is actually stored and visible again
when the session is reopened. If the coach is interrupted (navigates away, loses signal,
the browser closes), the in-progress work is preserved and offered back on return.

**Why this priority**: This is the core defect and the core value. Today two visible
fields (session kind and objectives) are silently dropped because the backend does not
accept them, and any interruption loses all work. A create flow that quietly discards
input or loses field work is worse than no flow. Fixing persistence + draft resilience is
the minimum that makes the feature trustworthy.

**Independent Test**: Create a session filling all fields including session kind and
objectives, save, reopen it, and confirm every value round-trips. Separately, fill part
of the form, simulate an interruption (reload / navigate away), return, and confirm the
draft is restored. Delivers a reliable, complete create experience on its own.

**Acceptance Scenarios**:

1. **Given** a coach on the new-session flow, **When** they set a session kind and
   objectives and save, **Then** reopening the session shows the same session kind and
   objectives (the values are persisted, not discarded).
2. **Given** a coach editing an existing session, **When** they change session kind,
   objectives, or coach notes and save, **Then** the changes persist and are shown on
   the next view.
3. **Given** a coach with a partially filled form, **When** the page reloads or they
   navigate away and come back, **Then** they are offered the option to restore the
   unsaved draft, and choosing restore repopulates every field they had entered.
4. **Given** a restored or saved draft, **When** the session is successfully created,
   **Then** the local draft for that flow is cleared so it is not offered again.
5. **Given** a coach who explicitly discards the draft, **When** they confirm,
   **Then** the form starts empty and no stale draft is offered later.

---

### User Story 2 - A guided, mobile-friendly flow with clear validation (Priority: P1)

A coach completes the create/edit flow on a tablet or phone as a guided, multi-step
wizard (e.g. General → Athletes → Route & Notes → Review) with a clear sense of progress
and what is required. Required fields are obvious, errors appear inline as the coach works
(not only as a jarring jump on submit), each step validates before advancing, a persistent
summary shows what still blocks saving, and all inputs — dates, times, textareas, choice
chips, athlete selection — are comfortable to use with a finger (≥48 px targets) outdoors.

**Why this priority**: The flow's clarity and field-usability determine whether a coach
can actually complete a session at the trailhead. A complete-but-confusing form fails the
primary user. This is tied P1 with Story 1 because correct persistence is useless if the
coach can't comfortably complete the form in context.

**Independent Test**: Complete the full flow on a small touch viewport: confirm progress
orientation, inline validation on each section, a sticky/visible summary of remaining
blockers, ≥48 px interactive targets, and zero accessibility violations. Delivers a
usable mobile/tablet experience independently of the draft and persistence work.

**Acceptance Scenarios**:

1. **Given** a coach filling the form, **When** a field fails validation, **Then** an
   inline, localized (español neutro) message appears for that field as they progress,
   without a disorienting jump.
2. **Given** required fields are still empty or invalid, **When** the coach attempts to
   save, **Then** a persistent, scannable summary lists exactly what remains and focuses/
   reveals the relevant field on selection.
3. **Given** the flow is a multi-step wizard, **When** the coach moves between steps,
   **Then** their orientation (which step they are on, what's left) is always visible and
   the current step's required fields are validated before advancing.
4. **Given** any touch surface, **When** the coach interacts with dates, times,
   textareas, choice chips, and the save/next controls, **Then** every interactive
   target is at least 48×48 px and operable by keyboard with visible focus.
5. **Given** the page-level and any dialog/sheet surfaces, **When** evaluated for
   accessibility, **Then** there are zero automated accessibility violations and dialogs
   trap focus and close on Escape.

---

### User Story 3 - Efficient athlete call-up for clubs with many athletes (Priority: P2)

A coach selects the athletes called up to a session from a list that supports search,
select-all / clear-all, a clear separation of who is already selected (chips) versus the
rest, and a count of how many are selected that stays visible while scrolling. Selecting
20 of 60 athletes is quick and unambiguous.

**Why this priority**: Call-up is required for every session and is the most tedious part
today (whole list rendered, substring-only search, no selected/unselected separation,
non-sticky count). It's P2 because the session can still be saved without these
improvements, but they materially speed up the most repeated action.

**Independent Test**: With a club of many athletes, search and select a subset, use
select-all and clear-all, confirm selected athletes appear as removable chips and the
running count stays visible. Delivers faster, clearer call-up independently.

**Acceptance Scenarios**:

1. **Given** a club with many athletes, **When** the coach types in the search box,
   **Then** the list narrows to matching athletes responsively.
2. **Given** some athletes are selected, **When** the coach views the selector, **Then**
   selected athletes are clearly distinguished (e.g. chips) and individually removable,
   and the selected count remains visible while scrolling.
3. **Given** the coach wants everyone (or no one), **When** they use select-all or
   clear-all, **Then** the selection updates accordingly and the count reflects it.
4. **Given** at least one athlete must be called up, **When** none are selected, **Then**
   saving is blocked with a clear localized message.

---

### User Story 4 - Route info, coach notes, and parent notification in one pass (Priority: P2)

When planning a session, the coach can in the same flow: record route notes and a Strava
link, attach a route file (e.g. .gpx/.fit), and write private coach notes — without
having to save first and come back. When saving, the coach decides whether to notify
parents and receives clear confirmation of whether the notification actually went out,
including a clear, non-blocking message if it failed (the session is still saved).

**Why this priority**: These capabilities exist in the system but are split across steps
or hidden (coach notes not exposed; route file only attachable after creation; parent
notification is a two-stage flow with silent failure). Consolidating them removes
round-trips and the "did the email send?" uncertainty. P2 because the session can be
created without them, but they complete the "one-pass planning" goal.

**Independent Test**: Create a session attaching a route file and coach notes in the same
flow, choose to notify parents, and verify a clear success-or-failure result for the
notification while the session is persisted either way. Delivers single-pass planning
independently.

**Acceptance Scenarios**:

1. **Given** the create flow, **When** the coach adds route notes, a Strava link, a route
   file, and private coach notes, **Then** all are saved with the session in one pass from
   the coach's perspective (the route file is auto-uploaded immediately after the session
   is created, with no manual "save first, then attach" round-trip).
2. **Given** an invalid Strava link or an unsupported/oversized route file, **When** the
   coach tries to attach it, **Then** a clear localized error explains the problem and
   the rest of the form is preserved.
3. **Given** the coach chooses to notify parents on save, **When** the notification
   succeeds, **Then** a clear success confirmation is shown.
4. **Given** the coach chooses to notify parents on save, **When** the notification
   fails, **Then** the session is still saved and a clear, non-blocking message tells the
   coach the notification did not go out, with a way to retry.
5. **Given** the coach chooses not to notify parents, **When** they save, **Then** no
   notification is sent and the choice is reflected without extra dialogs.

---

### Out of Scope (deferred to a follow-up spec)

The following "reuse past sessions" quality-of-life capabilities were considered but are
**deferred** (see Clarifications 2026-06-07) so this feature stays focused on the P1/P2
core and ships sooner. They are valuable for recurring weekly patterns but are not
required for a correct, complete, usable flow:

- **Clone session**: pre-seed a new draft from a previous session (kind, duration,
  location, focus, called-up athletes), excluding execution/attendance results.
- **Smart prefills**: offer easily-overridden defaults (e.g. last-used duration/location)
  when starting a new session.
- **Pre-submit review summary**: a concise confirmation (date, kind, athlete count,
  notification choice) before committing a session with many called-up athletes.

These will be captured in a separate follow-up specification and are intentionally not
included in this feature's requirements or success criteria.

---

### Edge Cases

- **Edit vs. create draft collision**: A restored create-draft must never overwrite an
  unrelated existing session being edited; drafts are scoped per flow (new vs. a specific
  session id) and per user.
- **Stale draft after schema/feature change**: A restored draft that no longer matches
  the current form (missing/extra fields) must restore what it can and ignore the rest
  without crashing.
- **Already-executed or cancelled session**: Editing a session that is executed or
  cancelled must respect the existing lifecycle rules (no silent re-opening of state);
  the flow surfaces which fields are still editable.
- **Athlete removed/deactivated between draft and save**: If a called-up athlete is no
  longer valid at save time, the coach is told which entries were dropped rather than
  failing the whole save silently.
- **Notification send when no parent has a valid contact**: The coach is told plainly
  that no notification could be delivered, distinct from a send failure.
- **Connectivity drop mid-save**: A failed save must keep the form populated and the
  draft intact so the coach can retry without re-entering anything.
- **Route file partially uploaded on flaky connection**: A failed/partial upload must not
  block saving the rest of the session, and must report clearly.
- **Concurrent edit**: If the session changed on the server since it was opened, the
  coach is warned before overwriting rather than silently clobbering.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The create/edit flow MUST persist every field it presents end-to-end —
  including session kind and objectives — so values entered are stored and shown again on
  reopen. No presented field may be silently discarded.
- **FR-002**: The flow MUST expose and persist private coach notes within the same
  create/edit pass (not only after the session exists).
- **FR-003**: The system MUST preserve in-progress create/edit work locally (autosave)
  and, on return after an interruption (reload, navigation, closed browser, dropped
  connection), MUST offer to restore the unsaved draft.
- **FR-004**: Restoring a draft MUST repopulate all previously entered fields; the coach
  MUST also be able to explicitly discard a draft. A successful save MUST clear the
  corresponding draft.
- **FR-005**: Drafts MUST be scoped per user and per flow target (new session vs. a
  specific session id) so they never bleed across users or across unrelated sessions.
- **FR-006**: The flow MUST be a guided, multi-step wizard (reusing the existing
  ImportWizard stepper pattern) with clear progress orientation so the coach always knows
  which step they are on and what remains; each step MUST validate its required fields
  before the coach can advance.
- **FR-007**: Validation MUST be inline and localized (español neutro, Colombia),
  surfacing errors as the coach progresses rather than only on submit, and MUST NOT let
  native HTML5 validation compete with the form's own validation on the same field.
- **FR-008**: When a save is blocked, the system MUST show a persistent, scannable
  summary of exactly what remains, and selecting an item MUST reveal/focus the relevant
  field.
- **FR-009**: All interactive targets in the flow MUST be at least 48×48 px on touch
  surfaces, keyboard-operable with visible focus, and any dialog/sheet MUST trap focus
  and close on Escape and via an explicit close control.
- **FR-010**: The flow MUST meet WCAG 2.1 AA and produce zero automated accessibility
  violations on page-level and dialog-level surfaces.
- **FR-011**: The athlete call-up selector MUST support search, select-all and clear-all,
  a clear visual separation of selected (e.g. removable chips) vs. unselected athletes,
  and a selected-count indicator that remains visible while scrolling.
- **FR-012**: The flow MUST require at least one called-up athlete and block save with a
  clear localized message when none is selected.
- **FR-013**: The flow MUST allow recording route notes and a Strava link, and MUST
  validate the Strava link with a single, consistent rule shared between client and
  server (no divergent rules producing inconsistent acceptance).
- **FR-014**: The flow MUST allow attaching a route file (e.g. .gpx/.fit) during the
  create pass as a single coach action; the file is auto-uploaded to the existing
  upload endpoint immediately after the session is created (no new create-with-file
  backend contract). Type MUST be validated by content (magic bytes, not extension) and
  by size, and any upload error MUST be reported clearly without losing the saved session
  or other form data.
- **FR-015**: At save, the coach MUST be able to choose whether to notify parents, and
  the system MUST report clearly whether the notification was sent, distinguishing
  success, send failure (with a retry path), and "no deliverable recipients".
- **FR-016**: A notification failure MUST NOT roll back or hide a successfully saved
  session; the session persists and the coach is informed.
- **FR-017**: A failed save (e.g. connectivity) MUST keep the form populated and the
  draft intact so the coach can retry without re-entering data.
- **FR-018**: The flow MUST respect the existing session lifecycle (planned → executed →
  cancelled) without changing the model; it MUST surface which fields are editable for a
  given state and MUST NOT silently change state.
- **FR-019**: The flow MUST detect when the session was modified on the server since it
  was opened and warn the coach before overwriting.
- **FR-020**: The flow MUST be available only to coach and admin roles; parent-facing
  views MUST remain filtered and MUST NOT expose coach notes, route file storage paths,
  or other athletes' data.
- **FR-021**: No minor's personal data (name, DOB, medical detail, identifying metadata)
  MUST appear in logs, error messages, or any third-party prompt as a result of this
  flow; locally stored drafts MUST be treated as sensitive and cleared on save/discard.
- **FR-022**: All end-user copy introduced by this flow MUST be in español neutro
  (Colombia) with full diacritics and MUST avoid clinical or judgmental language about
  minors.
> Note: The previously listed nice-to-haves (clone session, smart prefills, pre-submit
> review summary) are **deferred to a follow-up spec** (see Clarifications 2026-06-07 and
> the "Out of Scope" subsection) and are intentionally not requirements of this feature.

### Key Entities *(include if feature involves data)*

- **Training Session**: The plannable/editable unit. Relevant attributes for this flow:
  scheduled date, start time, duration, location, technical focus, description, **session
  kind**, **objectives**, route notes, Strava link, route file reference, **coach notes**,
  lifecycle status (planned/executed/cancelled), and its set of called-up athletes. This
  feature adds end-to-end persistence for session kind, objectives, and coach-notes
  exposure; it does not change the lifecycle model.
- **Session Call-up (Attendance link)**: The relationship between a session and each
  called-up athlete. This flow manages selection (who is called up); it does not change
  post-execution attendance/rubric semantics.
- **Local Draft**: A client-side, per-user, per-target snapshot of unsaved create/edit
  input used only to recover from interruptions. Treated as sensitive (may contain
  minors' references); cleared on successful save or explicit discard.
- **Parent Notification (outcome)**: The result of the optional notify-parents action at
  save time, surfaced to the coach as success / failure (retryable) / no-recipients.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of fields shown in the create/edit flow (explicitly including session
  kind and objectives) round-trip correctly — entered, saved, and shown again on reopen —
  verified across create and edit.
- **SC-002**: After any interruption (reload, navigation away, closed tab) with a
  partially filled form, the coach can restore 100% of previously entered fields.
- **SC-003**: A coach can complete a typical session (all required fields + ~15 called-up
  athletes) in under 2 minutes on a tablet, and under 3 minutes on a phone over simulated
  3G, on first attempt.
- **SC-004**: At least 90% of coaches complete the create flow on first attempt without
  hitting a dead-end or losing data in usability testing.
- **SC-005**: Zero automated accessibility violations on all page- and dialog-level
  surfaces of the flow; every interactive target measured at ≥48×48 px on touch.
- **SC-006**: Selecting a subset of athletes from a list of 60 takes under 30 seconds,
  with selected athletes always visibly distinguished and counted.
- **SC-007**: 100% of save attempts that include a notify-parents choice produce an
  explicit, correct outcome message (success / failure-with-retry / no-recipients); zero
  silent notification failures.
- **SC-008**: Zero occurrences of a saved-but-data-lost session (no field silently
  dropped) and zero data-loss-on-failed-save events in testing.
- **SC-009**: No minor's personal data appears in logs, error messages, or third-party
  prompts attributable to this flow (privacy audit passes with zero high/critical
  findings).
- **SC-010**: Route file and coach notes can be attached during initial creation in a
  single pass with zero required "save-then-return" round-trips.

## Assumptions

- This is primarily a frontend UX overhaul plus the minimal backend contract changes
  required to actually persist session kind and objectives and to surface coach notes;
  the unified Training Session lifecycle model (planned → executed → cancelled) is
  unchanged and no broad data-model redesign is in scope.
- Existing building blocks are reused rather than reinvented: the existing duration
  picker, choice-chip pattern, form + schema-validation approach, server-state/query
  layer, the shared component system, and the existing stepper/wizard pattern used
  elsewhere in the product.
- The set of session-kind options and the route-file types/size limits already defined in
  the system are authoritative; this flow surfaces and persists them rather than
  redefining them.
- Parents are notified through the existing notification mechanism and templates; this
  flow changes only how the choice is made and how the outcome is reported, not the
  template content beyond keeping it in español neutro.
- Drafts are stored on the coach's own device for interruption recovery only; they are not
  synced to the server and are not a substitute for saving.
- "Clone session", prefills, and the pre-submit review summary are out of scope for this
  feature and will be specified separately (see Clarifications 2026-06-07); this feature
  delivers the P1/P2 stories only.
- The guided flow is implemented as a multi-step wizard reusing the existing ImportWizard
  stepper pattern (rather than an enhanced single page or a per-device adaptive layout).
- The route file is uploaded via the existing upload endpoint immediately after the
  session is created; no new "create with file" backend endpoint is introduced.
- Coach and admin are the only roles that can create/edit sessions; parent access remains
  read-only and filtered.
