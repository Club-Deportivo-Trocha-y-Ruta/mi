# Feature Specification: National Championship Support (Series Level)

**Feature Branch**: `023-national-championship-level`

**Created**: 2026-07-08

**Status**: Draft

**Input**: User description: "Support National Championship events (distinct from Departmental Championship) so the system can register, ingest results, analyze, and report on the upcoming National XCO Championship in Pereira. Today the system only distinguishes series kind cup vs championship (feature 014); every championship is hardcoded as 'Departamental'. Add a level/scope concept to race series (departmental | national) so labels, notifications, and defaults reflect the correct championship level, while ingestion, standings exclusion, single-event guard, and monthly report grouping keep working unchanged. Existing Departmental Championship data must be preserved and default to departmental level."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Register the National Championship before race day (Priority: P1)

The coach knows the National XCO Championship will take place in Pereira. Before the event happens, the coach creates a new championship competition in the system identifying it as a **national**-level championship (not departmental), with its name, date, and city (Pereira). The system accepts it as a single-event championship, exactly like the existing Departmental Championship, but records that it is national in scope.

**Why this priority**: This is the prerequisite for everything else. Without the ability to register the event with the correct level, results cannot be ingested nor analyzed when the race happens. The user explicitly asked to "prepare the system before results exist".

**Independent Test**: Can be fully tested by creating a national championship series + its event in Pereira through the competitions UI and verifying it appears in the competitions list correctly identified as a national championship, without touching results, charts, or notifications.

**Acceptance Scenarios**:

1. **Given** a coach on the competition creation form, **When** they choose "Campeonato" and select level "Nacional", **Then** the system creates the championship series with national level and its single event (city Pereira), without asking for a "válida #".
2. **Given** an existing national championship series with one event, **When** the coach tries to add a second event to it, **Then** the system rejects it with the same single-event rule that applies to the departmental championship.
3. **Given** the competitions list, **When** the coach views the new event, **Then** it is labeled as a national championship (not "Campeonato Departamental").
4. **Given** a coach creating a national championship series, **When** the series is saved, **Then** it is not forced to carry Valle-specific defaults (organizer "Liga Vallecaucana de Ciclismo") — the coach can specify the actual organizer (e.g., Federación Colombiana de Ciclismo).

---

### User Story 2 - Ingest and analyze national championship results (Priority: P2)

After the race in Pereira, the coach imports the official results (PDF/CSV) into the system, linked to the previously created national championship. Results flow through the same parse → dry-run → commit pipeline. Race-analysis charts (distribution, evolution) then show the event correctly labeled as a national championship (e.g., "Cto. Nal. — Pereira"), never as "Cto. Dep.".

**Why this priority**: This is the core value when the race happens — the coach needs the results in the analytics with correct identification. Depends on US1 existing.

**Independent Test**: With a national championship registered (US1), import a results file linked to it and verify results commit successfully and charts label the event as national.

**Acceptance Scenarios**:

1. **Given** a registered national championship, **When** the coach launches the import from that competition, **Then** the import wizard prefills the locked identity (name/date/city/type) and hides the "válida #" field, and the commit links results to that event.
2. **Given** committed national championship results, **When** an athlete's evolution chart renders, **Then** the national championship point is labeled distinctly as a national championship with its city (e.g., "Cto. Nal. — Pereira") and never as "Cto. Dep.".
3. **Given** committed national championship results, **When** season standings / season panorama are computed, **Then** the national championship is excluded from cumulative points, same as the departmental championship today.
4. **Given** the monthly technical report for the month of the race, **When** competition results are grouped, **Then** the national championship appears as its own jornada group marked as not awarding season points.

---

### User Story 3 - Correct level in family communications (Priority: P3)

When race-related notifications are sent to parents (e.g., AI insight ready emails), messages referring to the Pereira event say "Campeonato Nacional", and messages about the Ginebra event keep saying "Campeonato Departamental".

**Why this priority**: Important for trust and clarity with families, but the event can operate (registration, ingestion, analytics) without it. Lower risk if delivered later.

**Independent Test**: Trigger a race notification for each championship type and verify the label in the message body matches the championship's level.

**Acceptance Scenarios**:

1. **Given** an insight notification for the national championship event, **When** the email is generated, **Then** the event is referred to as "Campeonato Nacional".
2. **Given** an insight notification for the existing departmental championship, **When** the email is generated, **Then** it still says "Campeonato Departamental" (no regression).

---

### Edge Cases

- Existing Departmental Championship series (created by feature 014) has no level recorded → it must be treated as departmental everywhere with no data fix required by the coach.
- Old snapshots / already-generated reports and insights that predate this feature must keep rendering without errors (they may keep their original labels).
- A cup series must not expose or require a level — level applies to championships only (cups are inherently departmental/regional today and their labels don't change).
- Import wizard used standalone (not from a competition) creating a new championship series: the coach must be able to state the level at that point too.
- Filtering competitions by type: the existing "Campeonatos" filter must include both departmental and national championships.
- Two championships in the same season (departmental + national) must coexist: same season, both single-event, both excluded from standings, without conflicting with each other.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a championship series to carry a level: **departmental** or **national**.
- **FR-002**: Coaches MUST be able to select the level when creating a championship series, both from the competition form and from the results import wizard; level selection MUST NOT appear for cup series.
- **FR-003**: All existing championship data MUST default to **departmental** level with no manual intervention (backward compatibility).
- **FR-004**: Anywhere the system renders a championship label (competition list/detail, race-analysis chart labels, filters), the label MUST reflect the series level: national championships MUST never be presented as "Departamental" (chart short label "Cto. Nal. — {ciudad}" vs "Cto. Dep. — {ciudad}").
- **FR-005**: Parent-facing notifications referencing a championship event MUST use the level-correct name ("Campeonato Nacional" / "Campeonato Departamental").
- **FR-006**: When creating a national championship series, the system MUST NOT force Valle-specific defaults; the coach MUST be able to provide the organizer, and the series MUST NOT be misattributed to "Liga Vallecaucana de Ciclismo".
- **FR-007**: Results ingestion (parse → dry-run → commit) for a national championship MUST work through the existing pipeline when the import is linked to the competition, with no change in behavior for cups or the departmental championship.
- **FR-008**: National championships MUST be excluded from cumulative season standings and the season panorama, identically to the departmental championship (no points awarded).
- **FR-009**: The single-event-per-championship rule (INV-2) MUST apply to national championships exactly as it does to departmental ones.
- **FR-010**: The monthly technical report MUST group a national championship's results as their own jornada marked as not awarding points, using the existing grouping behavior (no new report logic).
- **FR-011**: A departmental and a national championship MUST be able to coexist in the same season as separate series.
- **FR-012**: Level MUST be visible when listing/filtering competitions so the coach can distinguish the two championships at a glance; the existing championship filter MUST match both levels.

### Key Entities

- **Race Series**: A competition series (cup with numbered válidas, or single-event championship). Gains a **level** attribute (departmental | national) meaningful for championships; existing series default to departmental.
- **Race Event**: A single race belonging to a series; carries city and date. The Pereira event is the single event of the new national championship series. No structural change.
- **Race Result**: Athlete results linked to an event; unchanged, flows through existing ingestion.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The coach can register the national championship (series + Pereira event) in under 2 minutes using the existing competition form, before any results exist.
- **SC-002**: 100% of championship labels shown to users (lists, charts, filters, notifications) match the championship's level — zero occurrences of "Departamental"/"Cto. Dep." for the Pereira event.
- **SC-003**: Results import for the national championship completes through the existing wizard with no additional steps compared to importing the departmental championship.
- **SC-004**: Season standings computed after ingesting national championship results are byte-identical to standings computed without them (championships award no points).
- **SC-005**: All pre-existing data (departmental championship, cups, reports, insights) renders without errors and without label changes after the feature ships.

## Assumptions

- Only two levels are needed now: departmental and national. Other scopes (e.g., municipal, panamerican) are out of scope; the level concept should not preclude adding more later.
- Level is meaningful for championships only; cup series keep their current behavior and labels ("Válida N — ciudad") and are not asked for a level.
- The national championship does not award points in any club-tracked ranking; it is excluded from standings exactly like the departmental championship.
- The results file format for the national championship is compatible with the existing parser (same PDF/CSV structures used for Copa Valle / departmental). If the national federation publishes a different format, parser extension would be a separate feature.
- Category structure of the national event maps to the existing category catalog; unmapped categories follow the ingestion pipeline's existing unmatched-row handling.
- Notification tier/urgency for the national championship is treated like the current championship tier (highest importance); no new tier scheme is introduced.
- Existing race-analysis anchoring by event (feature 016) already disambiguates two `sequence 1` championships; no analytics identity change is required.
- No changes to ranking logic, the single-event guard, or monthly report grouping — verified in code analysis that these generalize via championship kind.
