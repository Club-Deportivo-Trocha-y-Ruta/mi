# Feature Specification: Cleanup Duplicate Competition

**Feature Branch**: `009-cleanup-duplicate-competition`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Remove a duplicate competition (and its linked calendar event). The Competitions list can end up with two entries for the same real race — one authoritative entry that holds the race results, and an empty duplicate that has no results but is still linked to a calendar event. The coach has no way to clean this up today: deletion is admin-only and is also blocked whenever a competition has results OR a linked calendar event, and there is no way to detach a competition from its calendar event. Provide a single, coach-accessible, confirmed cleanup flow that removes a no-results duplicate competition together with its linked calendar event. Competitions with results stay protected."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Coach removes a no-results duplicate competition (Priority: P1)

A coach reviewing the Competitions list finds two entries for the same real race (for example, "IV Válida Copa Valle XCO" / sede "Cali - Club del departamento" is an empty shell that duplicates the authoritative "IV Valida XCO" / sede "Cali", which holds the real results). The empty duplicate has no results but is still linked to a calendar event, so it cannot be deleted today. The coach selects a cleanup action on the empty duplicate, confirms it, and the duplicate competition together with its linked calendar event is removed in a single step — without admin involvement and without touching the authoritative entry.

**Why this priority**: This is the entire purpose of the feature. Without it the coach is permanently stuck with a confusing duplicate that pollutes both the competition history and the calendar. It is independently shippable and delivers the full value on its own.

**Independent Test**: Create a competition with no results that is linked to a calendar event. As a coach, trigger the cleanup action, confirm, and verify that (a) the competition disappears from the Competitions list and (b) the previously linked calendar event no longer appears on the calendar. No other data changes.

**Acceptance Scenarios**:

1. **Given** a competition that has no results and is linked to a calendar event, **When** a coach triggers the cleanup action and confirms it, **Then** the competition is removed from the Competitions list and its linked calendar event is also removed from the calendar.
2. **Given** a competition that has no results and is **not** linked to any calendar event, **When** a coach triggers the cleanup action and confirms it, **Then** the competition is removed and no calendar event is affected.
3. **Given** the cleanup action has been triggered, **When** the confirmation step is shown, **Then** it clearly states that both the competition entry and its associated calendar event will be permanently removed and that the action cannot be undone.
4. **Given** the cleanup confirmation is shown, **When** the coach cancels instead of confirming, **Then** nothing is removed and both the competition and its calendar event remain unchanged.

---

### User Story 2 - Authoritative competition with results is protected (Priority: P1)

A coach views a competition that holds imported race results. The cleanup action must not be available for it, so the authoritative entry — and its results — can never be removed through this flow, even by mistake.

**Why this priority**: Data safety is non-negotiable. Allowing this flow to remove a competition that holds results would destroy real, hard-won race data for minors and break the analytics built on top of it. This guard is as critical as the main story.

**Independent Test**: Open a competition that has results. Verify the cleanup action is not offered (or is clearly disabled with an explanation). Confirm there is no path through this flow that removes a competition holding results.

**Acceptance Scenarios**:

1. **Given** a competition that has results, **When** the coach opens its available actions, **Then** the duplicate-cleanup action is not available (hidden or disabled with an explanation that competitions with results cannot be removed this way).
2. **Given** a competition that has results, **When** any attempt is made to run the cleanup flow against it, **Then** the system refuses and no data is removed.

---

### Edge Cases

- **Already deleted / stale list**: The coach triggers cleanup on a competition that another session already removed. The system reports that the competition no longer exists and the list refreshes; nothing breaks.
- **Calendar event already detached or gone**: The competition has no results and is not linked to a calendar event (or the linked event was already removed). Cleanup still removes the competition cleanly and reports success without error.
- **Concurrent results import**: Results are imported for the competition between the moment the coach opens the action and the moment they confirm. On confirmation the system re-checks and refuses, because the competition now holds results.
- **Permission mismatch**: A non-coach role (parent, athlete) never sees or can invoke the cleanup action.
- **Calendar event shared expectations**: A competition links to at most one calendar event and a calendar event links back to at most one competition, so removing the pair never orphans or detaches a third record.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a coach to remove a competition that has no results in a single confirmed action.
- **FR-002**: When the competition being removed is linked to a calendar event, the system MUST also remove that linked calendar event as part of the same action.
- **FR-003**: The system MUST make the cleanup action available only for competitions that have no results; competitions that hold results MUST be excluded from this action (hidden or disabled with an explanation).
- **FR-004**: The system MUST require explicit confirmation before performing the removal, and the confirmation MUST state that both the competition and its associated calendar event will be permanently removed and that the action cannot be undone.
- **FR-005**: The system MUST restrict the cleanup action to the coach role; it MUST NOT be available to parents, athletes, or other non-coach roles.
- **FR-006**: The system MUST never remove, detach, or alter imported race results through this flow; if a competition holds results, the action MUST be refused even if it was initiated before the results existed.
- **FR-007**: After a successful cleanup, the system MUST reflect the removal so the competition no longer appears in the Competitions list and the linked calendar event no longer appears on the calendar.
- **FR-008**: The system MUST handle the case where the competition has no linked calendar event by removing only the competition, without error.
- **FR-009**: The system MUST handle stale state gracefully: if the targeted competition no longer exists when cleanup is confirmed, it MUST inform the coach and refresh rather than fail silently or corrupt data.
- **FR-010**: The system MUST leave the existing general competition-deletion behavior unchanged for all cases outside this no-results duplicate-cleanup flow.

### Key Entities *(include if feature involves data)*

- **Competition (race event)**: An entry in the Competitions list representing a race. May or may not hold race results, and may or may not be linked to a calendar event. The unit being removed by this feature when it holds no results.
- **Calendar event**: A scheduling entry shown on the calendar. May be linked one-to-one with a competition. When linked to the competition being cleaned up, it is removed together with that competition.
- **Race result**: Imported performance data tied to a competition. Its presence makes a competition "authoritative" and protected from this cleanup flow.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can fully remove a no-results duplicate competition and its linked calendar event from the Competitions list in a single guided flow, with no admin involvement.
- **SC-002**: After cleanup, 100% of the time the removed competition no longer appears in the Competitions list and its linked calendar event no longer appears on the calendar.
- **SC-003**: In 100% of attempts, a competition that holds results cannot be removed through this flow.
- **SC-004**: A coach can complete the cleanup of a known duplicate in under 30 seconds without leaving the Competitions view to hunt through the calendar.
- **SC-005**: No race results are ever lost or orphaned as a result of this flow (zero data-loss incidents).

## Assumptions

- A competition links to at most one calendar event, and that calendar event links back to at most one competition (one-to-one), consistent with the existing associate-competition-to-calendar behavior (feature 008). This feature is effectively its inverse plus removal.
- "No results" is the gating condition for the cleanup action; "has results" makes a competition authoritative and protected.
- On cleanup, the linked calendar event is always removed together with the competition — it is never kept as a standalone calendar entry. This is the coach's expressed preference for the duplicate-cleanup case.
- Detecting or preventing duplicates up front (e.g., warning when two competitions share the same válida number, date, or venue) is out of scope for this feature.
- Merging competitions or re-pointing results from one competition to another is out of scope.
- The action is confined to coach-level scheduling data; no personal data of minors is exposed or processed by this flow, consistent with project privacy rules.
- The existing admin-only general deletion path and its safeguards remain in place and unchanged for all non-cleanup cases.
