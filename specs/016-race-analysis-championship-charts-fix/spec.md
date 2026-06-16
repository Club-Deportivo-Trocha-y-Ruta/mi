# Feature Specification: Race-analysis Distribution & Evolution charts handle the Departmental Championship correctly

**Feature Branch**: `016-race-analysis-championship-charts-fix`

**Created**: 2026-06-16

**Status**: Draft

**Input**: User description: "Fix and improve the athlete AI-analysis 'Distribution' and 'Evolution' charts so the Departmental Championship is handled correctly alongside the cup rounds."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Selecting any race in Distribution never breaks (Priority: P1)

A coach (or a parent viewing their own child) opens an athlete's AI-analysis view and uses the "Distribution" chart. They select the Departmental Championship — or any race for which the athlete has no comparable data. Instead of a broken screen, they always see either the race's time distribution or a calm "no data for this race" state.

**Why this priority**: This is the live defect. Today selecting the Departmental Championship returns an error and shows nothing, and any race without comparable data does the same. The chart is one of the primary tools coaches and parents use to understand performance, so a hard failure on the season's most important A-priority race is the highest-impact problem to remove.

**Independent Test**: Open the Distribution chart for an athlete who competed in the Departmental Championship and select it; confirm no error appears and either a distribution or a friendly empty state is shown. Repeat for a race where the athlete did not finish.

**Acceptance Scenarios**:

1. **Given** an athlete who competed in the Departmental Championship, **When** the user selects the Departmental Championship in the Distribution chart, **Then** the chart shows that championship's time distribution with no error.
2. **Given** an athlete with no comparable data for the selected race (e.g. DNF, or nothing to compare against), **When** the user selects that race, **Then** the chart shows a clear, friendly "no data for this race" state instead of an error or blank screen.
3. **Given** any race already shown correctly today, **When** the user selects it, **Then** it continues to behave exactly as before.

---

### User Story 2 - Distribution lists the athlete's real races, identified correctly (Priority: P2)

The Distribution chart's race picker offers every race the athlete actually competed in this season — each cup round and the Departmental Championship — plus a clearly-labeled whole-season aggregate. Each option is tied to the real competition it represents and labeled with the race's real name and round marker, so no two options can be confused with each other.

**Why this priority**: Removing the error (P1) makes the chart safe, but the championship is only truly usable once it is selectable and unambiguously identified. Identifying each option by the real race — rather than a round number that can collide between a cup round and a championship — is what makes "select the championship" reliably show the championship and not some other race.

**Independent Test**: Open the Distribution race picker for an athlete who competed in several cup rounds and the championship; confirm every competed race is listed exactly once, each labeled with its real name and round marker, the whole-season aggregate is present and labeled, and no two options collide.

**Acceptance Scenarios**:

1. **Given** an athlete who competed in cup rounds and the Departmental Championship, **When** the user opens the Distribution race picker, **Then** every competed race appears exactly once, labeled with its real name and round marker (e.g. "Válida IV — Cali", "Cto. Dep. — Ginebra").
2. **Given** the same picker, **When** the user looks for the whole-season view, **Then** a clearly-labeled season aggregate option ("Temporada (todas)") is available and works.
3. **Given** a cup round and the championship that historically shared the same round number, **When** the user picks each, **Then** each resolves to its own distinct race with no collision.
4. **Given** a race the athlete did NOT compete in, **When** the user opens the picker, **Then** that race is not listed.

---

### User Story 3 - Evolution shows the Departmental Championship as its own point (Priority: P3)

In the "Evolution" chart, the Departmental Championship appears as its own distinct point, placed in correct chronological order by its actual date and clearly marked as the championship — never merged with or mislabeled as a cup round.

**Why this priority**: The championship is a key A-priority race in the season's progression. Coaches reviewing how an athlete is trending across the season need to see it as a separate, correctly-placed point. It depends on the same correct race identification as P2 but is a distinct surface, so it is sequenced after the Distribution fixes.

**Independent Test**: Open the Evolution chart for an athlete who competed in the championship; confirm the championship shows as exactly one distinct point, in date order between the May and August cup rounds, labeled as the championship.

**Acceptance Scenarios**:

1. **Given** an athlete who competed in the Departmental Championship, **When** the user opens the Evolution chart, **Then** the championship appears as exactly one distinct point.
2. **Given** the season calendar, **When** the championship point is placed, **Then** it sits in correct chronological order by its actual date (between the May cup round and the August cup round).
3. **Given** the championship point, **When** the user reads its label, **Then** it is clearly identified as the championship and is not merged with or labeled as a cup round.

---

### Edge Cases

- **Championship with no finishing time (DNF/DSQ)**: The race is still listed/selectable; Distribution shows the friendly no-data state; Evolution omits the metric for that point per existing rules rather than erroring.
- **Athlete competed in zero races this season**: The Distribution picker shows only the season aggregate (or a friendly empty state); no error.
- **Athlete competed in the championship but no cup rounds (or vice versa)**: The picker lists exactly the races competed in; Evolution shows whatever points exist, correctly ordered.
- **Legacy round-number collision**: A cup round and the championship that historically shared the same round number must still resolve to two distinct races everywhere.
- **Small comparison field (fewer than the minimum needed for a curve)**: The existing pseudonymized fallback (table of times) continues to work; no error.
- **Parent viewing another club athlete in aggregate views**: Pseudonymization and visibility rules remain exactly as today.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Distribution chart MUST never present an error or blank state when a race is selected, regardless of whether the athlete has comparable data for that race.
- **FR-002**: When the athlete has no comparable data for the selected race, the Distribution chart MUST show a clear, friendly "no data for this race" state in español neutro, not an error or raw failure.
- **FR-003**: The Distribution race picker MUST list every race the athlete actually competed in during the selected season — all cup rounds plus the Departmental Championship — and MUST NOT list races the athlete did not compete in.
- **FR-004**: Each race option MUST be tied to the real competition it represents, such that no two options (in particular a cup round and the championship) can be confused or collide, even when they historically shared a round number.
- **FR-005**: Each race option MUST be labeled with the race's real name and round marker (e.g. "Válida IV — Cali", "Cto. Dep. — Ginebra").
- **FR-006**: Selecting the Departmental Championship MUST display that championship's own time distribution (its own category field), distinct from any cup round.
- **FR-007**: The Distribution chart MUST retain a clearly-labeled whole-season aggregate option ("Temporada (todas)").
- **FR-008**: The whole-season aggregate view, and any race already displayed correctly today, MUST continue to behave with no regression.
- **FR-009**: The Evolution chart MUST display the Departmental Championship as its own distinct data point.
- **FR-010**: The Departmental Championship point in Evolution MUST be positioned in correct chronological order by its actual race date.
- **FR-011**: The Departmental Championship point in Evolution MUST be clearly labeled as the championship and MUST NOT be merged with, nor labeled as, a cup round.
- **FR-012**: Both charts MUST treat all races of the same discipline together (today every race is the same discipline). The behavior MUST be designed so that a future per-discipline filter (e.g. XCM, XCC) can be added later, but this feature MUST NOT introduce a discipline/modality data concept now.
- **FR-013**: In both charts, parent users MUST continue to see only pseudonymized competitors; real competitor names MUST remain visible only to coach/admin, exactly as today.
- **FR-014**: This change MUST NOT newly expose any minor's personal data in logs, error messages, or responses.
- **FR-015**: Both charts MUST remain usable for a coach on a tablet over intermittent connectivity — every async surface MUST present defined loading, empty, and error states with no unbounded spinner and no raw exception text.

### Key Entities *(include if feature involves data)*

- **Race**: A single dated competition an athlete may have participated in. It belongs either to a multi-round cup (and therefore has a round marker) or to a single-event championship (identified by its own identity, not a round number).
- **Cup round**: A race within the season's cup, identified by its round marker (I–VII) and its host city.
- **Departmental Championship**: A standalone single-event championship race with its own date and identity; it must never be represented by a cup round number.
- **Athlete race participation**: The set of races an athlete actually competed in within a season; this set is the source of truth for which options the Distribution picker offers.
- **Time distribution**: The comparison of the athlete's time against the field of their category for a single race.
- **Evolution series**: The athlete's performance progression across the season's races, ordered by date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the races an athlete competed in (every cup round plus the Departmental Championship) can be opened in the Distribution chart without producing an error.
- **SC-002**: Selecting the Departmental Championship results in zero broken/error screens — it always yields either a distribution or a friendly empty state (down from a 100% error rate today).
- **SC-003**: For every athlete who competed in the Departmental Championship, it appears in the Evolution chart as exactly one distinct point in correct date order.
- **SC-004**: Zero ambiguous options exist in the Distribution picker — each option maps to exactly one real competition, with no collision between a cup round and the championship.
- **SC-005**: The whole-season aggregate view and all previously-working races show no behavioral regression when compared against current behavior.
- **SC-006**: Parent views display zero real competitor names; coach/admin visibility is unchanged.

## Assumptions

- The cup-vs-championship distinction established in feature 014 is authoritative and already present in the data; no data migration is required for this feature.
- "Same discipline" today means every race is XCO; no discipline/modality data field is introduced, and Evolution therefore groups all races together for now.
- The whole-season aggregate ("Temporada (todas)") remains valuable and is kept as a selectable option, distinct from individual races.
- Pseudonymization rules and role-based visibility (parent vs coach/admin) are unchanged from current behavior and are simply preserved.
- Spanish-neutral (Colombia) copy such as "Válida N — <ciudad>" and "Cto. Dep. — <ciudad>" is acceptable for race option labels and the no-data state.
- The Distribution picker scopes its options to races the athlete participated in during the currently selected season.
- This feature touches only the Distribution and Evolution charts; AI insight text, chat, imports, results, and ranking computations are out of scope and unchanged.
