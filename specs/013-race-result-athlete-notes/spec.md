# Feature Specification: Coach Per-Athlete Qualitative Notes on Competition Results

**Feature Branch**: `claude/athlete-notes-race-results-zjdesm`

**Created**: 2026-06-14

**Status**: Draft

**Input**: User description: "Notas del entrenador por deportista en resultados de competencia. Cuando el entrenador revisa los resultados de una válida de la Copa Valle, no tiene dónde dejar registrada su observación cualitativa de cada corredor (cómo se sintió, qué pasó en la salida, una caída, una mejora técnica, el ánimo). Hoy ese contexto se pierde o queda en notas sueltas fuera del sistema, y sin él tanto el insight automático por corredor como el chat de IA de la competencia razonan solo con los datos numéricos del resultado, perdiendo el 'porqué' detrás del tiempo o la posición. La nota debe alimentar TANTO el insight automático por corredor/válida COMO el chat de IA coach-only de la competencia."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record a qualitative observation per athlete from the results view (Priority: P1)

From the results view of a specific válida, the coach can add a short free-text note about how an individual rider did in that race — the start, a crash, a technical improvement, their mood, how they felt — and save it so it stays linked to that rider and that válida. The note is the coach's own private observation, captured in the same screen where the coach is already reading the numeric results, without leaving for another tool or page.

**Why this priority**: This is the root capability. Without the ability to capture the observation in the moment, no downstream value (review later, feeding AI) is possible. It directly solves the reported problem of qualitative context being lost or kept in loose notes outside the system.

**Independent Test**: Can be fully tested by opening a competition's results, writing a note against one rider, saving it, and confirming it persists tied to that rider and that válida — delivering standalone value as a coach observation log even before any AI consumes it.

**Acceptance Scenarios**:

1. **Given** a competition with committed results, **When** the coach (or admin) opens the results view, **Then** each listed rider offers a clear affordance to add a qualitative note.
2. **Given** the coach writes a short note for a rider and saves it, **When** the save succeeds, **Then** the note is stored linked to that specific rider and that specific válida and is visible immediately without a page reload.
3. **Given** a rider already has a note for the válida, **When** the coach opens that rider's note, **Then** the existing text is shown for editing rather than starting blank.
4. **Given** a parent-role user views the competition results, **When** they open any view, **Then** no note affordance or note content is shown to them.
5. **Given** a note longer than the allowed length is attempted, **When** the coach tries to save, **Then** the system prevents the save and explains the limit in localized copy.

---

### User Story 2 - Review past notes when reopening a válida (Priority: P2)

When the coach reopens a past válida's results, the notes previously written for each rider are shown, so the coach can recall what they observed in that race (e.g., to prepare the next session or talk with a parent) without depending on memory or external documents.

**Why this priority**: The longitudinal recall is a core part of the stated success ("al volver a abrir una válida pasada puede ver sus notas anteriores"). It is the payoff of capturing notes, but depends on User Story 1 existing first.

**Independent Test**: Can be tested by writing notes for two riders in one válida, navigating away, reopening that válida, and verifying both notes appear correctly associated with their riders.

**Acceptance Scenarios**:

1. **Given** the coach wrote notes for several riders in a válida, **When** the coach reopens that válida later, **Then** each rider's saved note is displayed with its rider.
2. **Given** a rider has no note for a válida, **When** the coach views that válida, **Then** the rider simply shows no note (and an affordance to add one), with no error or placeholder noise.
3. **Given** the coach edits an existing note and saves, **When** the válida is reopened, **Then** the updated text is shown.
4. **Given** the coach deletes a note, **When** the válida is reopened, **Then** the rider shows no note and the add affordance is available again.

---

### User Story 3 - Notes enrich the per-athlete insight and the coach-only competition chat (Priority: P2)

The qualitative note the coach wrote for a rider in a válida is made available as context to BOTH the automatic per-athlete/per-válida insight AND the coach-only AI chat for that competition, so the AI can reason about the "why" behind a time or position, not just the numbers. When a rider has a note, the insight and a relevant chat answer reflect the coach's observation; when there is no note, both behave exactly as today with no fabricated context.

**Why this priority**: This is the differentiating value the coach asked for — turning a private observation into better AI reasoning across both AI surfaces. It is prioritized alongside review (P2) because it depends on notes existing (P1) but is a primary motivation for the feature.

**Independent Test**: Can be tested by writing a distinctive note for a rider, running the per-athlete insight and asking about that rider in the competition chat, and verifying both incorporate the observation; then removing the note and confirming both revert to numbers-only reasoning.

**Acceptance Scenarios**:

1. **Given** a rider has a coach note for a válida, **When** the automatic per-athlete insight for that rider/válida is produced, **Then** the insight reflects the qualitative observation alongside the numeric result.
2. **Given** a rider has a coach note for a válida, **When** the coach asks about that rider in the competition's coach-only chat, **Then** the answer can incorporate the note's context.
3. **Given** a rider has no note for a válida, **When** the insight is produced or the chat is asked about that rider, **Then** neither invents qualitative context and both behave as before this feature.
4. **Given** any insight or chat answer that uses a note, **When** it is generated, **Then** it never exposes the minor's personal identifying data in any logged prompt or public-facing output, consistent with the project's minors-privacy rule.
5. **Given** the coach updates a note and re-runs the insight or asks again in chat, **When** the AI responds, **Then** it reflects the updated note rather than the prior version.

---

### Edge Cases

- What happens when a rider in the results is not a club-managed athlete (e.g., an external competitor in the same category)? The note capability targets club-managed riders; non-managed entries do not offer notes.
- What happens when a note is written, then the rider's result row changes on a re-import of results? The note remains tied to the rider and válida regardless of result re-imports.
- How does the system behave on tablet with intermittent connectivity when saving a note that does not reach the server? The coach must receive clear feedback that the note was not saved, with no silent loss and no false "saved" confirmation.
- What happens when two notes are attempted for the same rider in the same válida? There is a single note per rider per válida; a second save edits the existing note rather than creating a duplicate.
- What happens when the coach enters only whitespace? An empty/whitespace-only note is treated as no note (or rejected), not stored as content.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a coach (and admin) to create a short free-text qualitative note about an individual club-managed rider, scoped to a specific válida, from within that competition's results view.
- **FR-002**: The system MUST associate each note with exactly one rider and one válida, and MUST keep at most one note per rider per válida (a subsequent save updates the existing note).
- **FR-003**: The coach MUST be able to view, edit, and delete a note they hold for a rider in a válida.
- **FR-004**: The system MUST persist notes so that reopening a past válida shows the previously saved notes associated with their riders.
- **FR-005**: The system MUST restrict creating, reading, editing, and deleting these notes to coach and admin roles; parents and athletes MUST NOT see or access note content or affordances.
- **FR-006**: The system MUST enforce a maximum note length appropriate for a brief observation and MUST reject or normalize empty/whitespace-only notes, surfacing localized validation messages.
- **FR-007**: The system MUST make a rider's note for a válida available as qualitative context to the automatic per-athlete/per-válida insight for that rider.
- **FR-008**: The system MUST make a rider's note for a válida available as qualitative context to the coach-only AI chat scoped to that competition.
- **FR-009**: When a rider has no note for a válida, the per-athlete insight and the competition chat MUST behave as they did before this feature, without fabricating qualitative context.
- **FR-010**: The system MUST ensure note content and any minor's personal identifying data never appear in public-facing outputs or in logged AI prompts, consistent with the project's minors-privacy rule.
- **FR-011**: The system MUST give the coach clear save/failure feedback so a note that fails to persist (e.g., over intermittent connectivity) is never reported as saved.
- **FR-012**: Updating a note MUST cause subsequently produced insights and chat answers to reflect the updated text rather than a prior version.

### Key Entities *(include if feature involves data)*

- **Coach Race Note**: A short, coach-authored qualitative observation about one club-managed rider's performance or experience in one válida. Attributes: the rider it describes, the válida it belongs to, the note text, the authoring coach, and created/updated timestamps. Relationships: belongs to one rider (athlete) and one competition (válida); authored by one coach (user). At most one note exists per rider per válida.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can record a qualitative observation for one rider, from the results view, in under one minute.
- **SC-002**: When reopening any past válida, 100% of the notes the coach previously saved for that válida are shown, correctly associated with their riders.
- **SC-003**: For a rider with a note, the per-athlete insight and a relevant competition-chat answer demonstrably incorporate the coach's observation in 100% of test cases, and for a rider without a note neither output introduces qualitative context.
- **SC-004**: Note content and minors' personal identifying data appear in zero public-facing outputs and zero logged AI prompts across the verification suite.
- **SC-005**: Parents and athletes can access note content in zero cases (no exposure through any role other than coach/admin).
- **SC-006**: When a note save fails over intermittent connectivity, the coach receives an explicit failure indication in 100% of simulated failure cases, with no false success confirmation.

## Assumptions

- "Válida" refers to a competition/race event already represented in the existing competitions module; notes attach to a club-managed rider within that event, not to external competitors.
- Notes are private to the coaching staff (coach/admin); there is no parent-facing or athlete-facing view, and no adult-to-adult threading — the note is a single observation, not a conversation.
- The per-athlete insight and the coach-only competition chat already exist (competitions AI insights and event-scoped chat); this feature feeds them additional context rather than creating new AI surfaces.
- A single note per rider per válida is sufficient; the coach refines an observation by editing rather than appending multiple notes.
- The note is plain text only; attaching photos or files is explicitly out of scope.
- This feature does not replace or alter the technical rubric or the monthly report.
- The feature must remain usable for a coach on a tablet in the field with intermittent connectivity, consistent with the project's UX and performance expectations.
- AI grounding must keep `AI_LOG_PROMPTS` disabled in production and honor the existing minors-privacy guardrails when notes are included as context.
