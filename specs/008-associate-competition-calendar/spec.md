# Feature Specification: One-click associate a competition to the calendar

**Feature Branch**: `008-associate-competition-calendar`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "If I'm editing a competition that doesn't have an event associated in the calendar, we have the option to redirect to the creating event page. That makes sense, but I have to re-fill other fields like name, date, that we already have at competition detail page. How do we create that event easier with less interaction from this page?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Associate a competition to the calendar in one action (Priority: P1)

A coach opens a competition (a Copa Valle válida) that is not yet on the club calendar. The competition detail page shows an "Asociar a calendario" action. Today that action opens an empty calendar-event form, forcing the coach to re-type the competition's name, date, and venue — data the competition already holds. With this feature, the coach can put the competition on the calendar in a single action that automatically reuses the competition's existing name, date, and venue, creating the calendar entry as an all-day event without any re-entry.

**Why this priority**: This is the core of the request and delivers the entire value on its own — it removes the redundant data entry and the risk of typos/mismatches between a competition and its calendar entry. Shipping only this story already solves the coach's stated problem.

**Independent Test**: Open a competition with no linked calendar event, trigger the one-click associate action, and confirm a calendar event is created and linked using the competition's name, date, and venue, marked all-day, with zero manual field entry.

**Acceptance Scenarios**:

1. **Given** a coach is viewing a competition that has no linked calendar event, **When** they trigger the one-click "Asociar a calendario" action, **Then** a calendar event is created and linked to the competition, reusing the competition's name, date, and venue, and shown as an all-day event.
2. **Given** the calendar event was just created, **When** the coach returns to the competition, **Then** the competition no longer offers the "associate" action and instead indicates it is on the calendar.
3. **Given** a competition with no venue recorded, **When** the coach triggers the one-click associate action, **Then** the calendar event is still created and linked using the available name and date, leaving the venue empty.

---

### User Story 2 - Review and adjust details before associating (Priority: P2)

When a coach wants to tweak something before the calendar event is saved (for example, refine the title or correct the venue), the associate action offers an "edit details first" path. This opens a calendar-event form already pre-filled with the competition's name, date, and venue, so the coach reviews and adjusts rather than retyping from scratch, then confirms to create and link the event.

**Why this priority**: It covers the less-common case where the coach needs to change something before saving. It enhances the primary flow but is not required to solve the core pain; the one-click path already works without it.

**Independent Test**: From a competition with no linked calendar event, choose the "edit details first" path and confirm the form opens pre-filled with the competition's name, date, and venue; on confirming, the event is created and linked.

**Acceptance Scenarios**:

1. **Given** a coach is viewing a competition with no linked calendar event, **When** they choose the "edit details first" path, **Then** a calendar-event form opens pre-filled with the competition's name, date, and venue.
2. **Given** the pre-filled form is open, **When** the coach adjusts one or more fields and confirms, **Then** the calendar event is created and linked to the competition with the coach's adjusted values.
3. **Given** the pre-filled form is open, **When** the coach cancels without confirming, **Then** no calendar event is created and the competition still offers the associate action.

---

### Edge Cases

- **Concurrent association**: If a calendar event for the competition is somehow already created (e.g., in another tab or by a prior action) when the coach triggers associate, the system must not create a duplicate; it should reflect the existing link instead.
- **Missing optional data**: A competition without a venue still associates successfully (venue left empty); a competition without a date cannot produce a valid all-day event and the action must be blocked or surfaced as an error rather than creating an invalid event.
- **Non-coach access**: A user who is not a coach must not be offered or able to perform this action.
- **Save failure**: If creating the calendar event fails, the competition must remain unlinked and the coach must be told the association did not complete, with the option to retry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The competition detail view MUST offer a one-click action to create and link a calendar event for a competition that has no linked calendar event.
- **FR-002**: When the one-click action is used, the system MUST create the calendar event automatically reusing the competition's existing name, date, and venue, with no manual re-entry required.
- **FR-003**: The auto-created calendar event MUST be created as an all-day event (a competition has a date but no specific start time or duration).
- **FR-004**: The created calendar event MUST be linked to the originating competition in a one-to-one relationship.
- **FR-005**: After a calendar event is created and linked, the competition MUST stop offering the "associate" action and MUST indicate that it is on the calendar.
- **FR-006**: The system MUST also offer an "edit details first" path that opens a calendar-event form pre-filled with the competition's name, date, and venue, allowing the coach to review/adjust before confirming.
- **FR-007**: On confirming the pre-filled form, the system MUST create and link the calendar event using the values shown (including any coach edits); on cancelling, the system MUST NOT create any calendar event.
- **FR-008**: Only coaches MUST be able to perform this association; the action MUST NOT be available to other roles.
- **FR-009**: The system MUST NOT create a duplicate calendar event for a competition that is already linked.
- **FR-010**: If creating the calendar event fails, the system MUST leave the competition unlinked, inform the coach the association did not complete, and allow a retry.

### Key Entities *(include if feature involves data)*

- **Competition (válida)**: A Copa Valle race entry that already holds a name, a date, and a venue. It may or may not be linked to a calendar event.
- **Calendar event**: A club-calendar entry that links one-to-one to a competition. For this feature it carries the competition's name, date (as an all-day event), and venue.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the common case, a coach can put an unlinked competition on the calendar with a single action and zero manual field entry.
- **SC-002**: 100% of calendar events created through this flow match the originating competition's name, date, and venue, and are all-day events.
- **SC-003**: After associating, the competition correctly reflects its linked state (no longer offers "associate") in 100% of cases.
- **SC-004**: The coach completes the association in under 10 seconds via the one-click path, versus the prior multi-field manual re-entry.
- **SC-005**: No duplicate calendar events are created for an already-linked competition.

## Assumptions

- The one-click create-and-link path is the primary experience; the "edit details first" pre-filled form is a secondary escape hatch (confirmed with the coach).
- The auto-created calendar event is always all-day, since a competition stores a date but no start time or duration (confirmed with the coach).
- This action is coach-only; admins and parents are out of scope for this flow (confirmed with the coach).
- The name, date, and venue carried into the calendar event are the same fields already stored on the competition.
- Scope is limited to the "associate when missing" flow. Out of scope (non-goals): editing or re-syncing a competition that is already linked to a calendar event (no two-way sync), the create-a-competition flow and any "also add to calendar" option there, and giving the auto-created event a specific start time or duration.
- No minor personal data is involved; competitions carry name/date/venue, not athlete data.
