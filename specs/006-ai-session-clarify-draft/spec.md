# Feature Specification: AI Session Clarify & Draft

**Feature Branch**: `006-ai-session-clarify-draft`

**Created**: 2026-06-08

**Status**: Draft

**Input**: User description: "AI-assisted session clarify-and-draft for the training session wizard. The AI asks a short batch of clarifying questions with selectable options (single/multi-select + free-text 'Other') before drafting the session, then prefills the editable session wizard. Coach always reviews and edits; nothing is auto-saved."

## Clarifications

### Session 2026-06-08

- Q: Where does the assistant live in the session-creation flow? → A: A pre-wizard launch — an "Asistente IA" entry point shown before/at the start of session creation; on finishing the conversation it opens the existing wizard pre-filled.
- Q: Which wizard fields does the draft pre-fill? → A: Everything — training content (focus, objectives, structured description, duration, session kind), inferable logistics (location, and date/time when stated in the intent), and a proposed athlete call-up. Privacy constraint preserved: the AI proposes athletes only by non-identifying criterion (e.g., age group or "todos los convocados"), which the system resolves to specific athletes locally; the AI never receives or emits any minor's name. The coach reviews and edits every pre-filled field, including the athlete selection.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clarify then draft a session from a short intent (Priority: P1)

A coach starts a new training session and, instead of filling every field by hand,
opens an "Asistente IA" (AI assistant) and optionally types a one-line intent such as
*"salida de 90 min en La Cumbre, bajadas técnicas, grupo 13-15, faltan 12 días para la
válida"*. The assistant replies with a short batch of clarifying questions, each shown
as selectable option chips. The coach taps answers (and types a free-text answer where
offered), then the assistant produces a complete draft session that pre-fills the normal
session wizard. The coach reviews every field, edits anything, and saves through the
existing flow.

**Why this priority**: This is the core value of the feature — it turns a blank,
multi-field form into a guided two-tap conversation that produces a compliant starting
point, which is the single biggest time saver for the coach. It is independently
shippable and demonstrable on its own.

**Independent Test**: Open the assistant, submit a short intent, answer the returned
questions, and confirm a full draft appears in the wizard with all visible fields
editable and nothing saved until the coach explicitly saves. Delivers value even if no
other story ships.

**Acceptance Scenarios**:

1. **Given** a coach on the new-session screen, **When** they open the AI assistant and
   submit a short free-text intent, **Then** the system returns between 2 and 4
   clarifying questions, each with 2–4 selectable options and a short description per
   option.
2. **Given** a returned question marked as single-select, **When** the coach selects an
   option, **Then** only one option can be active at a time for that question.
3. **Given** a returned question marked as multi-select, **When** the coach selects
   several options, **Then** all selected options remain active and are all submitted.
4. **Given** a question that allows a free-text answer, **When** the coach chooses
   "Otro" and types text, **Then** that free text is captured as the answer for that
   question.
5. **Given** the coach has answered the questions, **When** they request the draft,
   **Then** the system returns a complete proposed session (focus, objectives, a
   structured description with warm-up / main set / cool-down, duration, and session
   kind) that populates the wizard fields.
6. **Given** a generated draft is shown in the wizard, **When** the coach edits any
   field and saves, **Then** the saved session reflects the coach's edits, and no
   session was persisted before that explicit save.

### User Story 2 - Smarter questions and drafts from club context (Priority: P2)

When the coach has already chosen which athletes are called up (or indicated an age
group), the assistant tailors both its questions and the generated draft to the group's
age mix and to where the club is in its season — for example, easing intensity when a
Copa Valle A-race is near, and never proposing structured intervals for a 10–12 group.

**Why this priority**: Context-awareness is what makes the assistant trustworthy and
distinctively useful versus a generic generator, but the feature still delivers value
without it (Story 1). It builds directly on Story 1.

**Independent Test**: Provide a draft request for a 10–12 group close to an A-race and
confirm the questions and the resulting draft avoid prohibited content (no structured
intervals, appropriate volume) and reflect race proximity, without any individual
athlete being named.

**Acceptance Scenarios**:

1. **Given** a called-up group that is entirely 10–12, **When** the assistant generates
   questions and a draft, **Then** neither proposes structured high-intensity intervals
   and the emphasis is play- and skills-based.
2. **Given** an imminent A-priority race, **When** the assistant generates a draft,
   **Then** the proposed load reflects taper/reduced intensity appropriate to race
   proximity.
3. **Given** any draft request, **When** context is assembled for the assistant,
   **Then** only aggregate group information (e.g., age mix) is used and no individual
   athlete name or personal datum is included.

### User Story 3 - Safe, principle-compliant output the coach can trust (Priority: P2)

Every question and every generated draft respects the club's non-negotiable training
principles and the privacy rules for minors. If the assistant is unavailable or returns
something unusable, the coach is told clearly and can continue filling the wizard
manually with nothing lost.

**Why this priority**: Safety, compliance, and graceful failure are required for the
feature to be allowed into production at all; they are separable from the core happy
path and testable on their own.

**Independent Test**: Force the assistant to be disabled or to return malformed/unsafe
content and confirm the coach sees a clear message, the manual wizard still works, and
no prohibited content reaches the coach.

**Acceptance Scenarios**:

1. **Given** the AI capability is turned off or unreachable, **When** the coach opens
   the assistant, **Then** they see a clear, non-technical message and can proceed with
   the manual wizard with no data loss.
2. **Given** the assistant returns content that would violate a non-negotiable
   principle (e.g., a supplement suggestion, cadence below the minimum, a power-meter
   prescription for under-13s), **When** the response is processed, **Then** that
   content is removed or corrected before the coach sees it.
3. **Given** any assistant interaction, **When** prompts and responses are handled,
   **Then** no minor's name or personal data is logged and prompt logging stays
   disabled.
4. **Given** only one round of questions is supported, **When** the coach submits their
   answers, **Then** the assistant proceeds to draft rather than asking a second round
   of follow-up questions.

### Edge Cases

- **No intent typed**: The coach opens the assistant without any free text. The system
  still returns useful questions based on available context (or sensible defaults) and
  can produce a draft.
- **Coach skips questions**: One or more questions are left unanswered. The draft is
  still produced using reasonable defaults for the unanswered items.
- **Assistant returns zero questions**: If the assistant is confident, it may return no
  questions and go straight to a draft; the coach still reviews and edits.
- **Free-text answer is empty**: If "Otro" is selected but nothing is typed, that
  question is treated as unanswered.
- **Draft conflicts with chosen athletes**: If the coach later changes the called-up
  athletes after generating a draft, the draft remains editable; the system does not
  silently overwrite the coach's manual changes.
- **Slow or timed-out assistant**: A clear waiting state is shown, and a timeout yields
  a recoverable error, never a frozen screen or raw error text.
- **Non-permitted user**: A parent (or any non-coach/admin) cannot access the assistant.
- **Unusually long or off-topic intent**: The assistant still returns on-topic questions
  or a clear "could not interpret" message; it never blocks session creation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a pre-wizard "Asistente IA" launch point at the
  start of session creation, from which a coach opens the assistant and optionally
  provides a short free-text description of the intended session; on finishing the
  conversation, the assistant opens the existing wizard pre-filled.
- **FR-002**: The system MUST return a single batch of 2–4 clarifying questions per
  request, where each question includes a short label, the question text, an indicator
  of whether multiple answers are allowed, an indicator of whether a free-text answer is
  allowed, and 2–4 options each with a label and a short description.
- **FR-003**: The system MUST render single-select questions so that at most one option
  is active, and multi-select questions so that several options can be active at once.
- **FR-004**: The system MUST allow a free-text ("Otro") answer for questions that
  permit it, and capture that text as the answer.
- **FR-005**: The system MUST accept the coach's answers (selected option labels plus any
  free text) and return a complete proposed session draft.
- **FR-006**: The generated draft MUST include, at minimum, a technical focus,
  objectives, a structured description covering warm-up / main set / cool-down, a
  duration, and a session kind, and MAY additionally pre-fill logistics it can
  confidently infer from the intent (location, and date/time when stated) and a proposed
  athlete call-up, in a form that pre-fills the existing session wizard.
- **FR-016**: When the draft proposes an athlete call-up, it MUST express the proposal as
  a non-identifying criterion (e.g., an age group or "todos los convocados") that the
  system resolves to specific athletes locally; the assistant MUST NOT receive or emit
  any individual athlete name or personal datum to produce this proposal. The coach MUST
  be able to review and change the resulting athlete selection before saving.
- **FR-007**: The system MUST treat all generated content as an editable draft: every
  pre-filled field MUST remain editable and nothing MUST be persisted until the coach
  explicitly saves through the normal flow.
- **FR-008**: The assistant MUST tailor its questions and draft to the called-up group's
  age mix and to the club's current season position and race proximity, using only
  aggregate (non-identifying) context.
- **FR-009**: Both the questions and the generated draft MUST comply with the club's
  non-negotiable training principles (fun-first for 10–12 with no structured intervals,
  skills before fitness, biological age over chronological age, maximum 5 training days
  per week with at least one rest day, weekly hours not exceeding athlete age, zero
  supplements, cadence at or above the minimum, RPE primary with heart rate secondary,
  no power meters for under-13s, and a flexible plan).
- **FR-010**: The system MUST sanitize all assistant output so that any content
  violating a non-negotiable principle is removed or corrected before it reaches the
  coach.
- **FR-011**: The system MUST NOT include any minor's name or personal data in the
  context sent to the assistant, in its output shown to the coach, or in logs; prompt
  logging MUST remain disabled.
- **FR-012**: The assistant MUST support only a single round of clarifying questions per
  draft (no automatic multi-round follow-ups).
- **FR-013**: The system MUST restrict the assistant to coach and admin roles; other
  roles MUST NOT be able to access it.
- **FR-014**: The system MUST degrade gracefully: when the assistant is disabled,
  unreachable, slow, or returns unusable output, the coach MUST see a clear,
  non-technical message and MUST be able to continue creating the session manually with
  no loss of any data they already entered.
- **FR-015**: The system MUST handle partial input — missing intent, unanswered
  questions, or zero returned questions — by using reasonable defaults and still
  producing a usable draft.

### Key Entities *(include if feature involves data)*

- **Clarification Request**: The coach's starting point for a draft — an optional
  free-text intent plus available aggregate context (selected age group / age mix,
  season position, race proximity). Transient; not persisted.
- **Clarifying Question**: A single question returned to the coach, with a short label,
  question text, a single-vs-multiple indicator, a free-text-allowed indicator, and a
  set of 2–4 options.
- **Question Option**: One selectable choice within a question, with a display label and
  a short description explaining the choice.
- **Clarification Answers**: The coach's responses — for each question, the selected
  option label(s) and/or free text. Transient; sent back to obtain the draft.
- **Session Draft**: The proposed, fully editable session (focus, objectives, structured
  description, duration, session kind, and related fields) that pre-fills the wizard.
  Not persisted until the coach saves a real session.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can go from opening the assistant to a fully pre-filled, editable
  session draft in under 60 seconds and with no more than two interaction rounds (one
  intent, one set of answers).
- **SC-002**: The assistant returns between 2 and 4 questions, each with 2–4 options,
  in at least 95% of requests where it returns questions.
- **SC-003**: Across a representative test set covering 10–12 and 13–15 groups and
  near-race and off-season timing, 100% of generated drafts and questions are free of
  content that violates the non-negotiable principles after sanitization.
- **SC-004**: In 100% of interactions, no minor's name or personal datum appears in the
  assistant's context, its visible output, or logs.
- **SC-005**: When the assistant is unavailable or fails, 100% of the time the coach can
  still complete and save a session manually with no loss of already-entered data.
- **SC-006**: Coaches save an AI-seeded session (after any edits) in at least 60% of
  sessions where they opened the assistant, indicating the drafts are useful starting
  points rather than discarded.
- **SC-007**: Every field pre-filled by a draft is editable by the coach, verified for
  100% of draftable fields.

## Assumptions

- The feature reuses the existing session-creation wizard as the place where drafts are
  reviewed, edited, and saved; it does not introduce a separate save path.
- The conversation is stateless from the system's perspective: the coach's client holds
  the in-progress questions and answers between the two steps, and nothing about the
  conversation is stored server-side.
- Only one round of clarifying questions is in scope; iterative multi-round follow-ups
  are deliberately excluded and noted as a possible future enhancement.
- Voice input, weekly/microcycle batch generation, and assistant-driven editing of an
  already-saved session are out of scope for this feature.
- The assistant relies on the club's existing AI capability and its principle/privacy
  safeguards; if that capability is disabled, the feature is simply unavailable and the
  manual wizard is unaffected.
- Aggregate context (age mix, season position, race proximity) is derivable from data
  the system already holds; no new personal data collection is introduced.
- Reasonable defaults exist for every session field, so a draft can always be produced
  even with minimal coach input.
