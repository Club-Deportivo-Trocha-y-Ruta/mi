# Feature Specification: Season evolution charts read cup rounds and championships as separate comparison groups

**Feature Branch**: `039-season-comparison-groups` (spec directory only — no git branch was created, by explicit request of the project owner; work continues on `main`)

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "The 'Evolución en la temporada' charts in the family newsletter and in the athlete detail mix Copa Valle rounds with the Departmental and National Championships. Championships gather a different field (all of Valle, or all of Colombia), so their positions and gaps are not comparable with cup rounds and the connected line suggests a performance drop that does not exist. Reorganize the charts so each competition is read against its own field, keep the cup rounds as the season progression, show championships separately, apply the same reading to the AI insights, and make sure the design works when a season has more than one cup."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The family newsletter reads the cup and the championships separately (Priority: P1)

A parent opens the monthly newsletter (PDF or email) of their child. The "Evolución en la temporada" section now shows the three season charts (position per round, gap to the winner, accumulated points) only for the rounds of the cup the athlete raced. Below them, a separate "Campeonatos" block shows one card per championship the athlete competed in during the season, with the athlete's position, the size of the field in their category, the gap to the winner and the percentile within that field, plus a short note explaining that a championship gathers a different field and is read on its own.

**Why this priority**: This is the surface families actually receive. Today a national championship result drawn at the end of the cup line reads as a collapse in form, which is misleading for parents and unfair to the child. Fixing the newsletter removes the misleading message from the product's most visible output.

**Independent Test**: Generate the newsletter for an athlete who raced five cup rounds, the Departmental Championship and the National Championship in the season. Confirm the three charts contain only the five cup rounds, the accumulated-points chart ends at the cup total, and the "Campeonatos" block lists exactly two cards with the four readings each.

**Acceptance Scenarios**:

1. **Given** an athlete with cup rounds and at least one championship in the season, **When** the newsletter is generated, **Then** the three evolution charts contain only cup-round points, ordered by date, labeled with the round number, and no championship appears on their axes.
2. **Given** the same athlete, **When** the newsletter is generated, **Then** a "Campeonatos" block appears after the evolution charts with one card per championship, showing position, field size, gap to the winner (%) and percentile within the field, and the championship label states its level (departmental or national) and city.
3. **Given** an athlete with cup rounds and no championship in the season, **When** the newsletter is generated, **Then** the "Campeonatos" block is absent and the evolution section looks as it does today.
4. **Given** an athlete who only raced championships (no cup round), **When** the newsletter is generated, **Then** the evolution charts are omitted, the "Campeonatos" block is shown, and no error or empty chart frame is rendered.
5. **Given** a championship where the athlete did not finish, **When** the card is rendered, **Then** it shows a calm "no completó la prueba" state instead of numbers, and no chart or card breaks.

---

### User Story 2 - The athlete detail lets the viewer choose the competition to read (Priority: P2)

A coach (or a parent viewing their own child) opens the athlete's evolution chart in the Insights tab. A new "Competencia" selector lists the comparison groups the athlete raced in the selected season: each cup (for example "Copa Valle 2026") and each championship ("Cto. Departamental — Ginebra", "Cto. Nacional — Pereira"). The first cup is selected by default and the line chart shows only its rounds. Selecting a championship replaces the line with the championship reading (position, field size, gap to the winner, percentile) and the table view, since a single race has no trend to draw. The compact sparkline in the Panorama view follows the same rule and only draws the first cup.

**Why this priority**: The coach uses this chart to decide training focus and to talk with families. It must tell the same story as the newsletter, otherwise the two surfaces contradict each other. It depends on the same data separation as P1 but is a different surface, so it is sequenced second.

**Independent Test**: Open the evolution chart for an athlete who raced cup rounds and both championships. Confirm the selector lists three options, the default view shows only cup rounds, switching to a championship shows its card and table with no line, and the sparkline shows only the cup rounds.

**Acceptance Scenarios**:

1. **Given** an athlete with cup rounds and championships in the season, **When** the evolution chart loads, **Then** the "Competencia" selector lists every comparison group the athlete raced in, cups first and then championships in date order, and the first cup is selected.
2. **Given** a cup is selected, **When** the chart renders, **Then** only that cup's rounds appear, the confidence notice reflects the number of rounds in that cup, and the metric and season selectors keep working as today.
3. **Given** a championship is selected, **When** the view renders, **Then** the viewer sees the championship reading and the table, not a one-point line, and the label reflects the championship level and city.
4. **Given** an athlete who only raced championships, **When** the chart loads, **Then** the first championship is selected and the "Necesitas al menos 2 análisis" style empty state is not shown in error.
5. **Given** a parent viewing their own child, **When** any option is selected, **Then** the data shown is identical in shape to the coach view and no real competitor name is displayed.
6. **Given** the Panorama sparkline, **When** it renders, **Then** it draws only the rounds of the first cup and its tooltip never labels a national championship as departmental.

---

### User Story 3 - AI insights never compare a championship with a cup round (Priority: P3)

The coach launches an AI analysis for a championship, or a season summary for an athlete who raced both cup rounds and championships. The analysis reads the championship against its own field (size, percentile, gap to the winner) and never states that the athlete "dropped" or "improved" positions relative to a cup round. When the analysis targets a cup round, the prior-race comparison only uses earlier rounds of the same cup. Labels inside the analysis distinguish the departmental from the national championship.

**Why this priority**: The AI text is approved by the coach and can reach families through the newsletter. A narrative that treats a national-championship 11th place as a regression from a cup 4th place is exactly the misleading message this feature removes. It is sequenced third because it depends on the data separation of P1 and on the golden-evaluation gate.

**Independent Test**: Run the analysis pipeline on an athlete fixture with five cup rounds, a departmental and a national championship. For the national championship run, confirm the structured output contains no cross-competition position comparison and labels the race as national; for a cup-round run, confirm the season comparative lists only earlier rounds of that cup; confirm the golden evaluation still passes its blocking threshold.

**Acceptance Scenarios**:

1. **Given** an analysis of a championship, **When** the insight is generated, **Then** its progression assessment is not derived from cup rounds and the text contains no claim comparing the championship position or gap with a cup round.
2. **Given** an analysis of a cup round, **When** the season comparative is built, **Then** it contains only earlier rounds of the same cup, ordered by date, and never a championship or a round of another cup.
3. **Given** a season summary, **When** the insight is generated, **Then** the cup progression and the championship readings are presented as two separate sections and the championship readings use percentile and field size.
4. **Given** any generated insight about a national championship, **When** its label is rendered anywhere (timeline, hero card, dialogue history), **Then** it reads as a national championship, never as departmental.
5. **Given** the existing golden evaluation, **When** the updated analysis prompt runs against the dataset extended with a championship case, **Then** the composite score stays at or above the blocking threshold already enforced in CI.

---

### User Story 4 - A season with more than one cup keeps each cup separate (Priority: P4)

Today the club only races the Copa Valle, but the system must already handle a season where the athlete races two cups (for example a departmental league in parallel). Each cup is its own comparison group: the newsletter shows one evolution block per cup, the athlete detail selector lists each cup by name, and accumulated points are per cup.

**Why this priority**: Confirmed by the project owner as a design constraint rather than an immediate need. It is testable today with a synthetic dataset and prevents the same mixing problem from reappearing when a second cup is added.

**Independent Test**: Load a synthetic season with two cups and one championship for one athlete. Confirm the newsletter renders two evolution blocks titled with each cup's name, the detail selector lists both cups and the championship, and switching between cups never shows rounds of the other cup.

**Acceptance Scenarios**:

1. **Given** an athlete with rounds in two cups in the same season, **When** the newsletter is generated, **Then** one evolution block per cup is rendered, each titled with the cup's name and containing only its rounds, and each accumulated-points chart sums only that cup's points.
2. **Given** the same athlete, **When** the evolution chart loads in the athlete detail, **Then** the selector lists both cups by name and the championship, and the default selection is the cup with the earliest raced round.
3. **Given** two cups, **When** the AI season comparative is built for a round of cup A, **Then** no round of cup B is included.

---

### Edge Cases

- **Championship not finished (DNF/DNS/DSQ)**: the championship still counts as raced; the card shows a calm not-finished state; no percentile or gap is computed; no chart or card breaks.
- **Cup with a single raced round**: the line chart shows one point with the low-confidence notice; accumulated points show that round's points.
- **Athlete linked to more than one competitor record** (raced under different name spellings): the same race must appear once per surface, never duplicated across groups.
- **Two championships of the same level in one season** (for example a re-scheduled championship): each is its own group with its own card and its own selector entry, distinguished by city and date.
- **Historical seasons** already in the system: they follow the same rule with no data migration; a past season with the old mixing will simply render separated from now on.
- **Insights already generated before this change**: they are not regenerated; their stored labels are displayed with the corrected level naming where the level is known.
- **Newsletter month with no race**: the season-wide evolution and championship blocks still reflect the season to date, as the charts already do today.
- **Parent viewing aggregate views**: pseudonymization and visibility rules remain exactly as today; the new championship readings contain only counts and percentages, never third-party names.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST classify every raced competition of a season into exactly one comparison group: each cup is one group containing all of its rounds; each championship is its own single-race group.
- **FR-002**: Every season evolution chart (position per round, gap to the winner, accumulated points), on every surface, MUST draw points from a single comparison group only, ordered by race date.
- **FR-003**: Accumulated points MUST be computed per cup and MUST equal the athlete's cup total already used by the season standings; championships MUST NOT appear on the accumulated-points axis.
- **FR-004**: The newsletter MUST render one evolution block per cup the athlete raced, titled with the cup's name, and MUST omit the block entirely when the athlete raced no cup round.
- **FR-005**: The newsletter MUST render a "Campeonatos" block with one card per championship raced in the season, each showing: championship label with level and city, race date, category, position, field size in the category, gap to the winner as a percentage, and percentile within the field; and MUST omit the block when no championship was raced.
- **FR-006**: Each championship card MUST include a one-sentence note, in español neutro, stating that the championship gathers a different field and is read separately from the cup.
- **FR-007**: The athlete detail evolution view MUST offer a "Competencia" selector listing every comparison group the athlete raced in the selected season, cups first (by earliest raced round) then championships by date, with the first cup selected by default or the first championship when no cup was raced.
- **FR-008**: When a championship group is selected in the athlete detail, the view MUST present the championship reading (position, field size, gap to the winner, percentile) and the table view instead of a single-point line.
- **FR-009**: The confidence notice of the evolution view MUST be computed from the number of usable points in the selected group, not from the whole season.
- **FR-010**: The Panorama sparkline MUST draw only the rounds of the first cup and MUST show an empty state when the athlete raced no cup round.
- **FR-011**: Everywhere a championship is labeled (newsletter, charts, sparkline tooltip, insight timeline and cards, dialogue history), the label MUST reflect the championship level: national championships MUST never be presented as departmental.
- **FR-012**: AI analyses MUST receive the cup progression and the championship readings as separate inputs, and MUST be instructed that championship positions and gaps are not comparable with cup rounds.
- **FR-013**: The AI season comparative for a cup round MUST include only earlier rounds of the same cup, ordered by date; for a championship it MUST be empty and the progression assessment MUST be "first reference" or an equivalent non-comparative state.
- **FR-014**: The AI pipeline MUST identify races by their stable race identity, never by round number alone, so a championship can never be confused with the first round of a cup.
- **FR-015**: The previous analysis prompt version MUST remain selectable as an immediate rollback, as the pipeline already allows.
- **FR-016**: The golden evaluation dataset MUST include at least one case with a departmental and a national championship, and the blocking threshold already enforced in CI MUST still be met before the feature is closed.
- **FR-017**: The race time distribution chart MUST keep listing cup rounds and championships as selectable races, unchanged, since it already reads each race against its own field.
- **FR-018**: Season standings, season panorama, result import, calendar and notifications MUST be unaffected.
- **FR-019**: Parent users MUST continue to see only pseudonymized competitors; the new championship readings MUST contain only counts, positions and percentages of the athlete's own result, never third-party names.
- **FR-020**: This change MUST NOT introduce any minor's personal data into logs, error messages, responses or AI-provider prompts beyond what the existing guardrails already allow.
- **FR-021**: Every new asynchronous surface (selector change, championship reading) MUST present defined loading, empty and error states with no unbounded spinner and no raw exception text.
- **FR-022**: All new end-user copy MUST be in español neutro (Colombia) with full diacritics.

### Key Entities *(include if feature involves data)*

- **Comparison group**: The set of races whose results can be placed on the same line because they share a habitual field. Derived from the competition series: a cup is one group with all its rounds; a championship is a single-race group. Identified by the series it comes from and its kind (cup or championship) and level (departmental or national).
- **Cup**: A multi-round competition series within a season (for example Copa Valle 2026) with numbered rounds and cumulative points.
- **Championship**: A standalone single-race competition series with a level (departmental or national); awards no season points.
- **Championship reading**: The athlete's result in a championship expressed against its own field: position, field size in the category, gap to the winner (%), percentile within the field, and a not-finished state when applicable.
- **Evolution series**: The athlete's chronological results within one comparison group for a given metric.
- **Athlete race participation**: The set of races an athlete actually competed in within a season; the source of truth for which comparison groups are offered.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of season evolution charts rendered in the newsletter and in the athlete detail contain races from a single comparison group; zero charts mix a cup round with a championship (verified over the full set of athletes with results in the current season).
- **SC-002**: For every athlete who raced a championship, the newsletter shows exactly one championship card per championship raced, and the card's position, field size, gap and percentile match the official results for that race.
- **SC-003**: The accumulated-points value at the last cup round in the newsletter equals the athlete's cup total in the season standings for 100% of athletes.
- **SC-004**: 100% of championship labels across newsletter, charts, sparkline, insight timeline and dialogue history show the correct level; zero national championships labeled as departmental.
- **SC-005**: Over the golden evaluation dataset and a manual review of ten generated insights involving a championship, zero statements compare a championship position or gap with a cup round, and the golden composite score stays at or above the blocking threshold.
- **SC-006**: With a synthetic season of two cups and one championship, the newsletter renders two cup blocks and one championship card, and the detail selector offers three options with zero cross-group mixing.
- **SC-007**: A coach can switch the competition in the athlete detail with a single interaction and see the updated view within one second when the data is already loaded.
- **SC-008**: Parent views display zero real competitor names; coach and admin visibility is unchanged from today.
- **SC-009**: No regression on the race time distribution chart, the season standings, or the season panorama when compared with current behavior.

## Assumptions

- The cup-versus-championship distinction and the championship level established in features 014 and 023 are authoritative and already present in the data; no data migration is required.
- A comparison group is derived from the existing competition series; no new user-editable concept or configuration screen is introduced. If two different cups ever share a habitual field, a follow-up feature would add an explicit grouping.
- The newsletter's "Campeonatos" block and the evolution charts both cover the season to date, consistent with the current season-wide charts, even though the newsletter is monthly.
- With more than one cup in a season, the newsletter shows one evolution block per cup ordered by the earliest raced round; if this makes the PDF too long in practice, a later refinement may limit it to the primary cup.
- The championship reading in the athlete detail reuses the same four readings as the newsletter; no additional metrics are introduced.
- Percentile within the field normalizes for field size but not for field strength; it is therefore used only inside a championship reading and never to join a championship with cup rounds on one line.
- Insights generated before this change are kept as they are; only their level labeling is corrected where the race is known.
- Existing pseudonymization, role-based visibility and AI guardrails (forbidden-names list, word limits, consent gate) are preserved unchanged.
- The `data-privacy-guard` audit is mandatory for this feature because it touches athlete-identifiable results, even though no new personal data field is introduced.
- No git branch is created for this feature at specification time, by explicit request of the project owner; the branching rule of the constitution is expected to be honored when implementation starts.
