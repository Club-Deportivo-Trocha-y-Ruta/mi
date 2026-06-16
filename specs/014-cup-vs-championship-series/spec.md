# Feature Specification: Distinguish Cups (with rounds) from single annual Championships

**Feature Branch**: `main` (no feature branch — work proceeds on `main` per user instruction)

**Created**: 2026-06-15

**Status**: Draft

**Input**: User description: "Distinguir copas (con válidas) de campeonatos anuales únicos — el sistema hoy trata todo evento de resultados como una válida de copa, forzando a registrar el Campeonato Departamental como Válida #1 de la Copa Valle. Necesitamos distinguir series tipo copa (con válidas numeradas y ranking acumulado) de series tipo campeonato (evento anual único, sin válidas, sin puntos al acumulado)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Register a championship as a single annual event (Priority: P1)

The coach needs to register the Departmental Championship — a single annual event run by the Liga Vallecaucana de Ciclismo that is **not** part of the Copa Valle — as an event in its own right. Today the only way to record it is to attach it to the Copa Valle as a numbered round, which is sportingly wrong and confusing.

**Why this priority**: This is the core problem. Without it, every championship is misrepresented as a cup round, and the coach must invent fake round numbers. It is the minimum slice that delivers value: the coach can finally model reality correctly.

**Independent Test**: Create a new series classified as a championship, organized by the Liga Vallecaucana de Ciclismo, and register the Departmental Championship under it as a single event. Verify the round-number concept never appears in the creation flow and the event is not associated with the Copa Valle.

**Acceptance Scenarios**:

1. **Given** the coach is creating a new competition series, **When** they classify it as a "championship", **Then** the series accepts exactly one event and never asks for or displays a round number for that event.
2. **Given** a championship series already exists for the current season, **When** the coach registers its single event, **Then** the event is saved without any cup-round numbering and without belonging to the Copa Valle.
3. **Given** a championship series with its one event already registered, **When** the coach attempts to add a second event to that same championship series, **Then** the system prevents it and explains that a championship represents exactly one annual event.

---

### User Story 2 - Choose the right series when creating or editing a competition (Priority: P1)

When the coach creates or edits a competition, the app must let them choose which series it belongs to, instead of assuming it is always the Copa Valle. For a cup series the coach indicates the round number; for a championship series no round number is requested or shown.

**Why this priority**: The creation/edit experience is where the misclassification originates. Removing the hardcoded "Copa Valle" assumption is required for User Story 1 to be usable in practice and for any future championship (Nacional, Panamericano) to be modeled.

**Independent Test**: Open the competition create form, select a cup series, and confirm a round-number field is required; then select a championship series and confirm the round-number field disappears entirely. Repeat in edit mode for an existing competition.

**Acceptance Scenarios**:

1. **Given** the competition create form, **When** the coach opens it, **Then** no series is pre-selected as "Copa Valle" by default and the coach must explicitly pick the series.
2. **Given** the coach selects a cup series, **When** the form renders, **Then** a round-number input is shown and required.
3. **Given** the coach selects a championship series, **When** the form renders, **Then** the round-number input is not shown and is not required.
4. **Given** an existing competition that belongs to a championship series, **When** the coach edits it, **Then** the edit form behaves as a championship (no round number) and never reverts to a cup-round representation.

---

### User Story 3 - Import results with the correct series type (Priority: P1)

When the coach imports results, the import flow must reflect the type of the target series: ask for a round number only for cups, and omit the round-number concept entirely for championships. The flow must not assume the Copa Valle.

**Why this priority**: Results import is the second place the "Válida #1" mislabel is forced today. Fixing it together with creation closes the loop so that no entry path can mislabel a championship.

**Independent Test**: Run the import flow targeting a cup series and confirm it asks for a round number; run it targeting a championship series and confirm the round-number step is absent. Confirm neither path pre-fills "Copa Valle".

**Acceptance Scenarios**:

1. **Given** the import flow targeting a cup series, **When** the coach proceeds, **Then** the flow requests the round number.
2. **Given** the import flow targeting a championship series, **When** the coach proceeds, **Then** the flow does not request or mention a round number.
3. **Given** any import, **When** the flow starts, **Then** the series is not defaulted to "Copa Valle"; the coach selects (or the flow derives) the correct series explicitly.

---

### User Story 4 - See cup rounds vs championships clearly in lists and details (Priority: P2)

The coach (and indirectly the families) must be able to tell at a glance whether a competition is a cup round (e.g., "V3") or a championship (e.g., "CD"). The visual distinction that already exists today must be preserved.

**Why this priority**: Readability of the existing screens matters but is secondary to getting the data model and entry flows right. The current badge logic already works and must keep working once series carry an explicit type.

**Independent Test**: View the competitions list and a competition detail for both a cup round and a championship, and confirm the cup round shows its round label (e.g., "V3") while the championship shows a championship label (e.g., "CD"), consistent with today's behavior.

**Acceptance Scenarios**:

1. **Given** a cup-round competition, **When** it appears in a list or detail, **Then** it is labeled with its round (e.g., "V3").
2. **Given** a championship competition, **When** it appears in a list or detail, **Then** it is labeled as a championship (e.g., "CD") and shows no round number.

---

### User Story 5 - Keep championships out of the cup season ranking (Priority: P2)

The cumulative points ranking of a season must include only cup rounds and exclude championships entirely. Championships record positions and times but do not contribute to any season points table.

**Why this priority**: This protects the integrity of the season ranking, which is the number the coach and families care about. It depends on series carrying an explicit type, so it follows the model and entry work.

**Independent Test**: With at least one cup series (several rounds) and one championship in the same season, compute the season points ranking and confirm the championship's results do not appear in or affect the cumulative points.

**Acceptance Scenarios**:

1. **Given** a season with cup rounds and a championship, **When** the season points ranking is produced, **Then** only cup-round results contribute to the cumulative points.
2. **Given** a championship event with recorded positions and times, **When** the season ranking is produced, **Then** those results are excluded from the cumulative points table.

---

### User Story 6 - Reclassify the existing Departmental Championship 2026 (Priority: P2)

The Departmental Championship 2026 that is currently stored under the Copa Valle (as a fake round) must be reclassified into its own championship series organized by the Liga Vallecaucana de Ciclismo, detached from the Copa Valle, without losing any of its already-recorded results.

**Why this priority**: This corrects the real, live data that motivated the feature. It is essential to delivering value in production but depends on the new classification existing first.

**Independent Test**: After the change, verify the existing Departmental Championship event belongs to a standalone championship series (organizer: Liga Vallecaucana de Ciclismo), no longer belongs to the Copa Valle, no longer carries a fake round number, and that all its previously recorded results are still present and intact.

**Acceptance Scenarios**:

1. **Given** the existing Departmental Championship event currently under the Copa Valle, **When** the reclassification is applied, **Then** it belongs to a standalone championship series and no longer to the Copa Valle.
2. **Given** the reclassified championship, **When** the coach views it, **Then** it carries no cup-round number and is organized by the Liga Vallecaucana de Ciclismo.
3. **Given** the reclassification, **When** results are checked, **Then** every previously recorded result for that event is preserved with no loss.
4. **Given** the reclassification, **When** the season points ranking is recomputed, **Then** the Departmental Championship no longer contributes points to the Copa Valle cumulative ranking.

---

### Edge Cases

- What happens when multiple championships exist in the same season (e.g., Departmental, National, Panamerican)? Each is its own standalone championship series and they must coexist without colliding with each other or with any cup series.
- What happens if the coach tries to add a second event to a championship series? The system must prevent it (a championship is exactly one annual event).
- What happens to existing cup rounds after the change? They must keep their round numbers, their cumulative-points contribution, and their existing visual labels unchanged.
- How are positions and times handled for a championship? They are recorded and viewable like any event, but they never feed a season points ranking.
- What happens if a coach edits a competition and tries to convert a cup round into a championship (or vice versa)? Changing a competition's series/type must not silently corrupt round numbering or the cumulative ranking; the resulting state must remain valid for its new type.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let a competition series be classified as exactly one of two types: a "cup" (a series of several numbered rounds with a cumulative season points ranking) or a "championship" (a single annual event without rounds and without round numbering).
- **FR-002**: For a cup series, the system MUST associate each of its competitions with a round number that is unique within that series and season.
- **FR-003**: For a championship series, the system MUST NOT request, store, or display any round number for its event.
- **FR-004**: The system MUST allow multiple distinct championship series to exist within the same season (e.g., Departmental, National, Panamerican) without them colliding with each other or with any cup series of that season.
- **FR-005**: A championship series MUST represent exactly one annual event; the system MUST prevent adding more than one event to a championship series and MUST explain why when it does.
- **FR-006**: When creating or editing a competition, the system MUST require the coach to choose the series explicitly and MUST NOT default to the Copa Valle (or any specific cup).
- **FR-007**: The competition create/edit experience MUST show and require a round-number input only when the chosen series is a cup, and MUST hide it entirely when the chosen series is a championship.
- **FR-008**: The results-import experience MUST request a round number only when importing into a cup series and MUST omit the round-number concept when importing into a championship series, without defaulting to the Copa Valle.
- **FR-009**: Lists and detail views MUST clearly distinguish a cup round (labeled with its round, e.g., "V3") from a championship (labeled as a championship, e.g., "CD"), preserving the visual distinction that exists today.
- **FR-010**: The season cumulative points ranking MUST include only results from cup-series rounds and MUST exclude all championship results.
- **FR-011**: The system MUST record positions and times for championship events so they can be viewed, even though those results do not contribute to any season points ranking.
- **FR-012**: The system MUST reclassify the existing Departmental Championship 2026 — currently stored under the Copa Valle as a fake round — into its own standalone championship series organized by the Liga Vallecaucana de Ciclismo, detached from the Copa Valle, preserving all of its previously recorded results.
- **FR-013**: After reclassification, the Departmental Championship 2026 MUST carry no cup-round number and MUST no longer contribute points to the Copa Valle cumulative ranking.
- **FR-014**: The system MUST NOT introduce any series type other than "cup" or "championship".
- **FR-015**: The system MUST NOT expose any personal data of minor athletes as part of this feature; the scope is the classification of series and competitions, not athlete data.

### Key Entities *(include if feature involves data)*

- **Competition Series**: A named grouping of competitions for a given season. Carries a type that is either "cup" (many numbered rounds, cumulative season ranking) or "championship" (a single annual event, no rounds). Identified within a season by its name; the same season can hold one or more cup series and one or more championship series. A championship series additionally records its organizer (e.g., Liga Vallecaucana de Ciclismo).
- **Competition (Event)**: An individual competition that belongs to exactly one series. When its series is a cup, it carries a round number unique within the series/season. When its series is a championship, it carries no round number, and its series may contain only this single event.
- **Result**: A recorded outcome (position, time, and related data) for an athlete in a given competition. Results exist for both cup rounds and championship events. Only results from cup rounds contribute to the season cumulative points ranking; championship results are recorded and viewable but never counted toward season points.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The coach can register a championship (e.g., the Departmental Championship) as a single annual event without entering any round number and without attaching it to the Copa Valle, in a single create flow.
- **SC-002**: 100% of championship results are excluded from the season cumulative points ranking, while 100% of cup-round results remain included — verifiable by comparing the ranking before and after a championship is added (the championship adds zero points).
- **SC-003**: After reclassification, the previously misfiled Departmental Championship 2026 belongs to a standalone championship series organized by the Liga Vallecaucana de Ciclismo, with zero of its previously recorded results lost.
- **SC-004**: No create, edit, import, or view screen pre-selects or assumes "Copa Valle"; in every entry flow the coach selects the series explicitly.
- **SC-005**: The existing at-a-glance distinction between a cup round ("V3") and a championship ("CD") remains correct in lists and details for every competition, with no regression for existing cup rounds.
- **SC-006**: Multiple championships can coexist in the same season without any naming or numbering collision among themselves or with cup series.

## Assumptions

- Championships are standalone and do **not** award points to any cumulative ranking; the season points ranking is exclusive to cup series. (Confirmed default.)
- Multiple championships may exist in the same season; each is its own standalone single-event series. (Confirmed default.)
- The scope of this feature includes reclassifying the existing real Departmental Championship 2026 event so that it is detached from the Copa Valle and placed under its own standalone championship series. (Confirmed default.)
- "Liga Departamental 2026" mentioned in legacy notes is only an illustrative example, not a real dataset entity, and is therefore not modeled as a special case. (Confirmed default.)
- The Copa Valle de Ciclomontañismo remains a cup series with numbered rounds and an unchanged cumulative points ranking; existing cup rounds keep their numbering, points contribution, and visual labels.
- No personal data of minor athletes is read or written as part of this feature beyond what already exists for results; the work concerns series/competition classification, so the minors-privacy invariant is satisfied by not changing how athlete data is exposed.
- The coach is the primary actor (desktop) for create/edit/import and ranking views; families are indirect beneficiaries who only view correctly classified competitions.
