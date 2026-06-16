# Feature Specification: Prefill results import from an existing competition

**Feature Branch**: `015-prefill-import-from-competition`

**Created**: 2026-06-16

**Status**: Draft

**Input**: User description: "Prefill import from competition — From an existing competition's detail view, the coach should be able to launch the results-import flow already prefilled with everything the system can determine about that competition (identity, name, date, discipline/type, and series), with prefilled fields locked read-only (plus an explicit 'edit metadata' escape hatch), type and series derived automatically and not editable inside import, the standalone no-competition import flow left unchanged, and the 'válida #' concept hidden for championships."

## Clarifications

### Session 2026-06-16

- Q: When a competition's series or type cannot be determined from its record, should the prefilled import block, fall back to the empty standalone flow, or prefill only known fields and let the coach choose series/type? → A: Block the prefilled import and direct the coach to the "edit metadata" escape hatch to assign a series/type before importing — keeping type/series 100% derived and never selectable inside the import flow.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launch a prefilled import from a competition (Priority: P1)

After a válida or championship has taken place, the coach opens the detail view of the competition that already exists in the system and starts importing its official results from there. The import flow opens already populated with everything the system can determine about that competition — its identity, name, date, discipline/type, and the series it belongs to — so the coach does not re-enter any of it and only has to provide the results themselves.

**Why this priority**: This is the core problem. Today the coach must start the import from scratch and manually re-enter information the system already knows, which is slow and the single biggest source of mismatched-series and mistyped-event errors. The minimum slice that delivers value is letting the coach launch an import that already knows which competition it targets.

**Independent Test**: Open an existing competition's detail view, launch its results import, and confirm the flow opens with the competition's identity, name, date, type, and series already filled in, so the coach can proceed directly to supplying results without re-entering metadata.

**Acceptance Scenarios**:

1. **Given** an existing competition in its detail view, **When** the coach launches the results import from that competition, **Then** the import flow opens already populated with that competition's identity, name, date, type, and series.
2. **Given** a prefilled import launched from a competition, **When** the coach proceeds, **Then** the imported results are linked to that exact competition without the coach selecting or confirming the competition again.
3. **Given** a prefilled import, **When** the coach reviews the prefilled metadata, **Then** all of it matches the source competition's detail view (no divergence).

---

### User Story 2 - Protect the competition link with locked, derived fields (Priority: P1)

The metadata the system already knows about the competition appears locked (read-only) in the import flow so the coach cannot accidentally change it and break the link between the results and the competition. The competition's type and series are derived automatically from the competition record and are not editable inside the import flow. If a genuine correction is needed, an explicit "edit metadata" escape hatch is available.

**Why this priority**: Prefilling without protecting the prefilled values would re-introduce the same mismatched-series and mistyped-event errors the feature exists to eliminate. Locking the derived fields by default — with a deliberate escape hatch — is what makes the link trustworthy. It ships together with User Story 1 because prefill without protection is not safe.

**Independent Test**: In a prefilled import, confirm the prefilled identity, name, date, type, and series are read-only by default, that type and series cannot be edited inside the import flow, and that an explicit "edit metadata" action exists for genuine corrections.

**Acceptance Scenarios**:

1. **Given** a prefilled import, **When** the flow renders, **Then** the prefilled identity, name, date, type, and series are shown as locked (read-only) by default.
2. **Given** a prefilled import, **When** the coach looks for a way to change the type or series, **Then** there is no control to edit type or series inside the import flow (both are derived from the competition).
3. **Given** a prefilled import where a real correction is needed, **When** the coach uses the explicit "edit metadata" escape hatch, **Then** the coach can make the correction through that deliberate action rather than by accidental edit.
4. **Given** a prefilled import the coach did not alter, **When** the import completes, **Then** the results are linked to the same competition the import was launched from, with no series mismatch.

---

### User Story 3 - Keep the standalone (no-competition) import unchanged (Priority: P1)

The existing import entry point that does not start from a specific competition continues to work exactly as it does today, with no prefilled context. The coach who needs to import without an existing competition is unaffected.

**Why this priority**: The standalone import is a live, working path that other workflows depend on. The feature must add the prefilled path without regressing the from-scratch path; protecting it is essential to ship safely.

**Independent Test**: Launch the import from the standalone entry point (not from a competition) and confirm it behaves exactly as it does today — empty, with no prefilled identity, name, date, type, or series, and no locked fields imposed by this feature.

**Acceptance Scenarios**:

1. **Given** the standalone import entry point, **When** the coach launches it, **Then** the flow opens with no prefilled context, identical to today's behavior.
2. **Given** the standalone import, **When** the coach uses it, **Then** none of the read-only locking introduced for the prefilled path is imposed on the standalone path.
3. **Given** both entry points exist, **When** the coach uses either, **Then** results are parsed, ingested, and validated the same way (this feature changes only what is prefilled and locked, not how results are processed).

---

### User Story 4 - Hide round numbering for championships (Priority: P2)

When the prefilled import targets a championship, the "válida #" / round-number concept is not applicable and is hidden, consistent with how championships are already presented elsewhere in the product. When it targets a cup round, the round is part of the (locked) prefilled metadata as usual.

**Why this priority**: It keeps the prefilled import consistent with the existing cup-vs-championship distinction and avoids showing a nonsensical round number for championships. It is secondary because it refines presentation rather than enabling the core prefill, and it depends on the prefill carrying the derived type.

**Independent Test**: Launch a prefilled import from a championship competition and confirm no "válida #" / round-number concept appears; launch one from a cup round and confirm the round appears as part of the locked prefilled metadata.

**Acceptance Scenarios**:

1. **Given** a prefilled import launched from a championship competition, **When** the flow renders, **Then** no "válida #" / round-number concept is shown or requested.
2. **Given** a prefilled import launched from a cup-round competition, **When** the flow renders, **Then** the round is shown as part of the locked, prefilled metadata.
3. **Given** either type, **When** the import completes, **Then** the round-numbering presentation matches how that competition is already presented elsewhere in the product.

---

### Edge Cases

- What happens when a competition's series or type cannot be determined from its record? Per FR-009, the prefilled import is blocked and the coach is directed to the "edit metadata" escape hatch to assign a series/type first; results are never silently linked to a wrong or empty series, and no in-flow series/type selector is offered.
- What happens if the coach uses the "edit metadata" escape hatch and changes metadata so it no longer matches the source competition? The resulting state must remain valid and must not silently link results to a different competition than intended without the coach being aware.
- What happens if the coach lacks permission to import results for that competition? The prefilled import must respect the same role permissions that already govern who can import results; an unauthorized user must not be able to launch or complete it.
- What happens if the source competition already has results imported? This feature does not change how duplicate or re-imported results are handled; behavior matches today's import processing.
- How does the prefilled flow behave on a tablet in the field (smaller screen, intermittent connectivity)? The locked fields and escape hatch must remain usable; this feature does not change the underlying connectivity behavior of the import.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: From an existing competition's detail view, the system MUST let an authorized coach launch the results-import flow scoped to that competition.
- **FR-002**: When the import is launched from a competition, the system MUST prefill everything it can determine about that competition: its identity, name, date, discipline/type, and the series it belongs to.
- **FR-003**: The system MUST link results imported through the prefilled flow to the exact competition the import was launched from, without requiring the coach to re-select or re-confirm the competition.
- **FR-004**: The system MUST present the prefilled identity, name, date, type, and series as locked (read-only) by default to protect the integrity of the competition link.
- **FR-005**: The system MUST derive the competition's type and series automatically from the competition record and MUST NOT offer a way to edit type or series inside the import flow.
- **FR-006**: The system MUST provide an explicit "edit metadata" escape hatch so the coach can make a genuine correction deliberately, rather than by accidental edit of a prefilled field.
- **FR-007**: The system MUST keep the standalone (no-competition) import entry point working exactly as it does today, with no prefilled context and without imposing the prefilled path's read-only locking.
- **FR-008**: When the prefilled import targets a championship, the system MUST hide the "válida #" / round-number concept; when it targets a cup round, the round MUST appear as part of the locked prefilled metadata — consistent with how championships and cup rounds are already presented elsewhere.
- **FR-009**: When a competition's series or type cannot be determined from its record, the system MUST block the prefilled import (rather than proceed with a wrong or empty series) and MUST direct the coach to the "edit metadata" escape hatch to assign a series/type before the import can be launched. The system MUST NOT offer an in-flow series/type selector as a fallback, preserving the rule that type and series are always derived from the competition record (see FR-005).
- **FR-010**: The system MUST respect the existing role permissions that govern who can import results; the prefilled entry point MUST NOT grant import access to anyone who could not already import results.
- **FR-011**: The system MUST NOT change how results are parsed, ingested, or validated; the scope is limited to what is prefilled and locked, and where the import can be launched from.
- **FR-012**: The system MUST NOT add new competition metadata fields and MUST NOT change how series, types, cups, or championships are defined or managed.
- **FR-013**: The system MUST NOT introduce or expose any new personal data of minor athletes; the prefilled flow only carries forward competition-level metadata (identity, name, date, type, series) that the coach already sees on the competition detail view.

### Key Entities *(include if feature involves data)*

- **Competition (Event)**: The existing competition the coach launches the import from. Provides the metadata that is prefilled and locked: identity, name, date, discipline/type, and the series it belongs to. Its type and series are the source of the derived, non-editable values in the import flow.
- **Competition Series**: The series the competition belongs to (a cup with numbered rounds, or a single-event championship). Determines whether the round-number concept is shown (cup) or hidden (championship) in the prefilled import.
- **Results Import**: The act of bringing official results into the system for a competition. When launched from a competition it is prefilled and link-scoped to that competition; when launched standalone it carries no prefilled context. This feature does not change how the import parses, ingests, or validates results.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When launching an import from an existing competition, the coach re-enters zero pieces of that competition's identity, name, date, type, or series (all are prefilled).
- **SC-002**: Starting an import from a competition takes the coach noticeably fewer steps than the from-scratch flow — measurably fewer manual inputs before reaching the results-supply step.
- **SC-003**: For imports launched from a competition and left unaltered, 100% link to the correct competition, eliminating mismatched-series errors for prefilled imports.
- **SC-004**: The prefilled identity, name, date, type, and series are read-only by default in 100% of prefilled imports, and type/series have no in-flow edit control.
- **SC-005**: The standalone (no-competition) import flow exhibits no behavioral change: it opens empty, with no prefilled context and no imposed locking, exactly as before this feature.
- **SC-006**: No prefilled import launched from a championship displays a "válida #" / round-number concept; every prefilled import launched from a cup round shows its round, matching how the competition is presented elsewhere.

## Assumptions

- The coach is the primary actor (desktop, and occasionally a tablet in the field). The standalone import audience is unchanged.
- "Identity" of a competition means the existing reference that uniquely identifies the competition record the import is scoped to; no new identifier is introduced.
- The competition's type and series are already stored on the competition record and are sufficient to derive the round-number presentation (cup shows round, championship hides it), consistent with the existing cup-vs-championship behavior (specs/014-cup-vs-championship-series).
- "Edit metadata" is a deliberate, explicit escape hatch for genuine corrections; routine prefilled imports do not require it.
- Results parsing, ingestion, validation, and duplicate/re-import handling are unchanged; this feature only changes the launch point, what is prefilled, and what is locked.
- No new competition metadata fields are added, and the definitions/management of series, types, cups, and championships are unchanged.
- The minors-privacy invariant is satisfied: only competition-level metadata already visible on the detail view is carried forward; no minor PII is introduced or newly exposed.
