# Feature Specification: Race course profile — optional course track, laps per category and track description for each válida

**Feature Branch**: `feat/043-race-course-profile`

**Created**: 2026-09-15

**Status**: Draft

**Input**: User description: "Race course profile: optional course track, laps per category and track description for each válida. Today a válida only records the results and five weather/surface conditions; nothing describes the circuit itself (lap length, climbing, technicality, laps per category), so times from different válidas cannot be compared fairly, the AI analyst is forbidden from mentioning terrain, and the coach has no place to share the circuit with riders and families before race day. Some younger categories ride a reduced version of the circuit (roughly 70 % of the loop, defined by the organisers) and that difference is invisible today. The coach records the circuit with their own GPS device; only the clean shape of one lap is kept. Laps per category, route variants, a structured track description, derived distance and average speed per result, course context for the AI analysis, and a reconnaissance view for coach and families."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The coach attaches the recorded circuit and sets laps per category (Priority: P1)

The coach creates or edits a válida, or reaches the optional "Circuito" step of the results import, and attaches the circuit they recorded that day with their own GPS device. The platform reads the recording, keeps only the geometric shape and the elevation of one lap, discards timestamps, heart rate, cadence, temperature and every other personal metric, and never keeps the original file. If the recording contains several laps, the platform proposes the detected single lap with its distance and climbing and the coach confirms or corrects it; if no closed lap can be detected, the coach states how many laps the recording contains and the platform divides accordingly. The coach may attach more than one route variant for the same válida (for example "Circuito completo" and "Recorrido reducido"), each with its own recording. Then, in a table listing the categories present in the válida, the coach sets the number of laps and the variant each category rode. The table arrives pre-filled from the previous válida of the same series so that confirming takes seconds; each válida keeps its own configuration. Everything in this story is optional: a válida without a circuit keeps working exactly as today.

**Why this priority**: Without the circuit and the laps table nothing else in the feature exists. It is also where the privacy constraint lives: the recording comes from the coach's personal device and must be reduced to the course shape at the moment of upload.

**Independent Test**: With a synthetic multi-lap recording containing timestamps and heart-rate fields, attach it to a válida as "Circuito completo", confirm the detected lap, attach a second shorter recording as "Recorrido reducido", assign laps and variants to three categories, save; reload and assert the two variants show lap distance and elevation gain, the laps table is persisted, and no timestamp, heart rate or original file exists anywhere in the platform's storage.

**Acceptance Scenarios**:

1. **Given** a válida without course data, **When** the coach attaches a valid recording of a single closed lap and names the variant, **Then** the platform stores the lap shape, its distance and its elevation gain, shows them to the coach, and the original recording is not retained.
2. **Given** a recording containing three consecutive laps of the same loop, **When** the coach attaches it, **Then** the platform proposes one detected lap with its distance and climbing and the coach can confirm it or state a different number of recorded laps before saving.
3. **Given** a recording with no detectable closed lap (an out-and-back or a partial loop), **When** the coach attaches it, **Then** the platform asks how many laps the recording contains, defaults to one, and derives lap distance and climbing from that answer.
4. **Given** a recording that carries timestamps, heart rate, cadence, power or temperature, **When** it is processed, **Then** none of those fields is stored, displayed or written to any log, and only position and elevation remain.
5. **Given** a file that is not a recognised GPS recording, is malformed, or exceeds the size limit, **When** the coach attaches it, **Then** the platform rejects it with a clear message in español neutro and the válida is left unchanged.
6. **Given** a válida with two route variants and five categories present, **When** the coach opens the laps table, **Then** every category appears with a laps field and a variant selector, pre-filled from the previous válida of the same series when that válida had a configuration for the same category, and empty otherwise.
7. **Given** the laps table is saved, **When** the coach later re-opens the válida, **Then** the same laps and variants are shown, independent of any later change to another válida.
8. **Given** a variant assigned to at least one category, **When** the coach tries to delete that variant, **Then** the platform refuses and names the categories that still use it.
9. **Given** the results import wizard for a válida, **When** the coach reaches the optional "Circuito" step, **Then** they can attach recordings and fill the laps table with the same behaviour as in the válida editor, or skip the step without consequence for the import.
10. **Given** a válida imported before this feature exists, **When** the coach edits it, **Then** they can add its course data afterwards with the same flows.

---

### User Story 2 - Results show real distance and average speed (Priority: P1)

Once a válida has course data, every classified result shows the real distance the rider covered and their average speed, computed from the laps of their category (minus the laps down recorded in the official results) and the lap distance of the variant that category rode, together with the lap distance and elevation gain of that variant. When any input is missing (no course data, no laps configured for the category, a rider classified with laps down whose count is unknown, or a result without a time) the platform shows "sin dato" and never estimates.

**Why this priority**: Comparable distance and speed are the first concrete payoff of the circuit data and they feed both the comparison views and the AI analysis.

**Independent Test**: Seed a válida with one variant of 4.2 km and 110 m of climbing, a category set to 3 laps on that variant, one finished rider at 30 minutes, one rider classified one lap down at 28 minutes, and one rider with status DNF; assert the first shows 12.6 km and 25.2 km/h, the second shows 8.4 km and 18.0 km/h, and the third shows "sin dato" for both values.

**Acceptance Scenarios**:

1. **Given** a finished rider in a category with laps and variant configured, **When** the results are displayed, **Then** the distance equals laps × lap distance to one decimal in kilometres and the average speed equals distance ÷ time to one decimal in km/h.
2. **Given** a rider classified with laps down and a known laps-down count, **When** the results are displayed, **Then** the distance uses the laps actually completed and the speed is derived from that distance.
3. **Given** a rider with laps down but an unknown count, a rider without time, or a category without laps configured, **When** the results are displayed, **Then** both values read "sin dato" and no number is shown.
4. **Given** a válida without course data, **When** the results are displayed, **Then** the results table looks exactly as it does today, without empty columns or placeholders that suggest missing work.
5. **Given** the parent of one rider, **When** they open their child's result, **Then** they see only their own child's distance and speed, never another rider's.
6. **Given** two válidas of the same series where only one has course data, **When** any view compares them (season overview, comparison groups, rider evolution), **Then** course-based figures appear only for the válida that has them and the comparison says "sin dato" for the other, never mixing normalised and raw figures silently.

---

### User Story 3 - The coach describes the track (Priority: P2)

In the same "Circuito" section the coach describes the track with structured fields (terrain type, technical difficulty from 1 to 5, key sectors chosen from a fixed list such as long climb, technical descent, rock garden, singletrack, fast flat, creek crossing) plus free notes about difficulties and recommendations. The description belongs to the válida and can be written or changed at any moment.

**Why this priority**: The structured part is what makes circuits comparable and gives the AI analysis a vocabulary; the free notes are the coach's reconnaissance memory. It is independent from the recording: a description without a track is still useful.

**Independent Test**: Save a description with terrain "mixto", difficulty 4, two key sectors and 300 characters of notes; reload and assert every field is displayed in español neutro; save a description with only notes and no track and assert it is accepted.

**Acceptance Scenarios**:

1. **Given** a válida, **When** the coach fills terrain type, difficulty, key sectors and notes and saves, **Then** the description is stored and shown on the válida with the labels in español neutro.
2. **Given** a válida without any recording, **When** the coach saves only a description, **Then** it is accepted; the description never requires a track.
3. **Given** the difficulty field, **When** the coach chooses a value, **Then** only integers from 1 to 5 are accepted and each value shows a short label (for example "1 — Muy fácil" … "5 — Muy técnico").
4. **Given** free notes longer than the allowed length, **When** the coach tries to save, **Then** the platform tells them the limit and does not truncate silently.

---

### User Story 4 - The AI analysis uses the circuit only when it exists (Priority: P2)

When the per-válida AI analysis runs for a rider whose válida has course data, the analysis receives the lap distance and elevation gain of the variant their category rode, the number of laps, the terrain type, the difficulty and the key sectors, and may use them to put the result in context (for example, a slower time on a longer or more technical circuit). When the válida has no course data, or the rider's category has no laps configured, the analysis keeps today's rule and says nothing about distance, laps, terrain or climbing. The free notes of the coach are not passed to the analysis.

**Why this priority**: It is a stated goal of the owner and the reason for structured fields, but it depends on stories 1 and 3 and must not degrade the analysis quality the club already relies on.

**Independent Test**: With a fake model capturing the prompt, run the analysis for a rider in a válida with course data and assert the prompt carries lap distance, climbing, laps, terrain, difficulty and key sectors and not the free notes; run it for a válida without course data and assert none of those words appears; run the existing golden evaluation and assert its composite score stays at or above the current threshold.

**Acceptance Scenarios**:

1. **Given** a válida with course data and a rider whose category has laps configured, **When** the analysis runs, **Then** the course facts are available to it and the produced text may mention them.
2. **Given** a válida without course data, **When** the analysis runs, **Then** the produced text does not mention distance, laps, terrain, climbing or difficulty.
3. **Given** a válida with a description but no recording, **When** the analysis runs, **Then** only terrain, difficulty and key sectors are available; no distance or climbing is invented.
4. **Given** the coach's free notes, **When** the analysis runs, **Then** the notes are never part of what the analysis receives.
5. **Given** the existing golden evaluation of the race analysis, **When** it runs after this feature, **Then** its composite score is at or above the current blocking threshold.

---

### User Story 5 - Coach and families recognise the circuit before and after the event (Priority: P2)

On the válida page the coach, and on the family app the parents of riders registered in that válida, see the circuit map, its elevation profile, the lap distance and elevation gain of each variant, the number of laps their category rides and the track description. Families see this from the moment the coach publishes the course, even before the event, as a reconnaissance aid; they never see other riders' data through this view.

**Why this priority**: Reconnaissance is a direct benefit for young riders and their families and reuses everything stored by the other stories; it is deliberately read-only.

**Independent Test**: Log in as a parent whose child is on the roster of a scheduled válida with course data and assert the map, profile, laps of the child's category and description are visible; log in as a parent whose child is not registered and assert the válida shows no course data; assert no results or other riders' names are shown in that view; run the accessibility check with zero violations.

**Acceptance Scenarios**:

1. **Given** a válida with course data and a parent whose child is registered in it, **When** the parent opens the válida, **Then** they see the map of each variant, the elevation profile, lap distance, elevation gain, the laps of their child's category and the description.
2. **Given** a parent with two children in different categories of the same válida, **When** they open it, **Then** they see the laps and variant of each child's category, labelled by child.
3. **Given** a parent whose children are not registered in the válida, **When** they open the club's calendar entry for it, **Then** no course data is shown.
4. **Given** a válida without course data, **When** anyone opens it, **Then** the circuit section is absent, not empty.
5. **Given** a family on a slow mobile connection, **When** the map is loading, **Then** the lap distance, climbing, laps and description are readable before the map appears.

---

### Edge Cases

- A recording whose start and end points are close but which never returns to the start in between: treated as one lap, not several.
- GPS noise near the start line creates a false "lap closure" within the first few hundred metres: a lap is only detected after a minimum distance has been ridden.
- A flat circuit whose raw elevation readings drift by tens of metres: the stored elevation gain is computed after smoothing so that a flat circuit reports near-zero climbing.
- A recording without elevation data: distance is stored, elevation gain is "sin dato", the profile is not shown.
- A recording with fewer than a handful of points, or spanning an impossible distance for a youth XCO lap (for example above 15 km per lap or below 300 m): rejected with a clear message.
- The coach uploads a new recording for an existing variant: the previous shape and figures are replaced, and derived distance and speed on results refresh accordingly.
- A category present in the results but missing from the laps table: its results show "sin dato" and the coach sees a hint to complete the table.
- A category configured in the laps table but with no results in the válida: allowed; it simply has no derived figures.
- The previous válida of the series has no configuration: the table opens empty; no earlier válida is searched.
- A válida is deleted: its variants, laps table and description go with it.
- The same válida receives course data while an AI analysis is running: the running analysis keeps the data it started with; later analyses use the new data.
- Two variants with the same label: rejected within the same válida.
- A results revision changes a rider's laps-down count: the derived distance and speed follow the revised value.

## Requirements *(mandatory)*

### Functional Requirements

**Course recording and route variants**

- **FR-001**: The coach MUST be able to attach a GPS recording of the circuit to a válida, both from the válida creation/edit flow and from an optional step of the results import, and attaching is always optional.
- **FR-002**: The platform MUST accept GPX recordings (the universal export of GPS devices, Garmin Connect and Strava), MUST reject any other format, compressed files, malformed content or files above the existing route-file size limit, and MUST leave the válida unchanged on rejection. FIT support is deferred (see Assumptions).
- **FR-003**: From the recording the platform MUST keep only the position and elevation of the points of one lap, MUST discard timestamps, heart rate, cadence, power, temperature and any other extension field at upload time, and MUST NOT retain the original file in any storage.
- **FR-004**: The platform MUST detect a single closed lap in a multi-lap recording, present the detected lap distance and climbing for confirmation, and MUST let the coach override the detection by stating the number of laps recorded; when no closed lap is detectable it MUST ask for that number with a default of one.
- **FR-005**: The stored lap MUST be simplified to a compact shape that preserves the visual route and the distance within 1 %, so that it can be shown on a map and an elevation profile without transferring the raw recording.
- **FR-006**: The platform MUST compute and store, per variant, the lap distance in kilometres (one decimal) and the elevation gain in metres after smoothing elevation noise; when the recording has no elevation the gain is stored as unknown.
- **FR-007**: The platform MUST reject a lap whose distance falls outside 0.3–15 km or that has too few points to form a route, with a message in español neutro.
- **FR-008**: A válida MUST support any number of named route variants; labels MUST be unique within the válida; a variant MUST NOT be deleted while a category references it.
- **FR-009**: Replacing a variant's recording MUST replace its shape and figures and refresh every derived value that depends on it.

**Laps per category**

- **FR-010**: For each category present in a válida the coach MUST be able to set the number of laps (integer, 1–20) and the route variant that category rode.
- **FR-011**: When the laps table is opened for a válida without configuration, it MUST be pre-filled from the configuration of the immediately previous válida of the same series for the categories that match, and left empty otherwise; the prefill is a suggestion saved only when the coach saves.
- **FR-012**: Each válida MUST keep its own laps configuration; changing it never affects another válida.

**Track description**

- **FR-013**: The coach MUST be able to describe the track with a terrain type (fixed list), a technical difficulty from 1 to 5 with labels, zero or more key sectors from a fixed list, and free notes up to 1,000 characters; the description MUST be savable with or without a recording.

**Derived figures on results**

- **FR-014**: For every classified result whose category has laps and a variant configured, the platform MUST show the real distance (laps completed × lap distance, where laps completed = category laps − laps down) and the average speed (distance ÷ race time), each to one decimal, plus the lap distance and elevation gain of the variant.
- **FR-015**: The platform MUST show "sin dato" and never an estimate when course data, laps configuration, race time or a required laps-down count is missing, or when the result status is not classified.
- **FR-016**: Any view that compares válidas (season overview, comparison groups, rider evolution) MUST use course-based figures only when every válida in the comparison has them, and MUST label the missing side "sin dato" instead of mixing normalised and raw values.
- **FR-017**: Derived figures shown to a parent MUST be limited to that parent's own children, under the same access rules as results.

**AI analysis**

- **FR-018**: When a válida has course data and the rider's category has laps configured, the per-válida AI analysis MUST receive lap distance, elevation gain, laps, terrain type, difficulty and key sectors of the variant that category rode.
- **FR-019**: When a válida has no course data or the category has no laps configured, the AI analysis MUST keep the current prohibition on mentioning distance, laps, terrain, climbing or difficulty; when only a description exists, only terrain, difficulty and key sectors are passed.
- **FR-020**: The coach's free notes MUST never be part of what the AI analysis receives.
- **FR-021**: The existing golden evaluation of the race analysis MUST remain at or above its current blocking threshold after the change.

**Reconnaissance view**

- **FR-022**: The válida page for the coach MUST show, when course data exists, the map of each variant, the elevation profile, lap distance, elevation gain, the laps table and the description; when no course data exists the section MUST be absent.
- **FR-023**: Parents MUST see the course data of a válida only when at least one of their children is registered in that válida's roster or has a result in it, and only the laps and variant of their own children's categories are highlighted; the view MUST NOT expose results or other riders.
- **FR-024**: The reconnaissance view MUST present distance, climbing, laps and description as text that is readable before any map has loaded, and MUST pass the project's accessibility check with zero violations.

**Privacy and audit**

- **FR-025**: No timestamp, physiological metric or original recording of the coach MAY appear in storage, logs, error messages, traces or AI prompts.
- **FR-026**: Uploading, replacing or deleting a variant and saving the laps table MUST be attributed to the acting coach with a date, following the attribution already used for válida changes.
- **FR-027**: Course data MUST be removed together with its válida when the válida is deleted.

### Key Entities

- **Route variant**: a named version of the circuit ridden in one válida (for example "Circuito completo", "Recorrido reducido"); holds the simplified shape of one lap (position and elevation only), lap distance, elevation gain, who attached it and when. Belongs to exactly one válida.
- **Category course setup**: for one válida and one category, the number of laps and the route variant ridden. Belongs to the válida; references a variant of the same válida.
- **Track description**: terrain type, technical difficulty (1–5), key sectors, free notes; part of the válida.
- **Derived result figures**: real distance, average speed, lap distance and elevation gain shown beside a result; computed from the result, its category course setup and the variant, never stored as independent facts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a tablet, the coach attaches a recorded circuit, confirms the detected lap, sets laps for every category of the válida and fills the description in under 5 minutes.
- **SC-002**: In a válida with course data, 100 % of classified results with a known laps count show real distance and average speed; 0 % of results show an estimated figure when any input is missing.
- **SC-003**: A recording carrying timestamps and heart rate leaves zero occurrences of those values in storage, logs or traces after upload, verified by inspection of everything the platform wrote.
- **SC-004**: The AI analysis mentions distance, laps, terrain, climbing or difficulty in 0 % of runs for válidas without course data, and the race-analysis golden evaluation stays at or above its current threshold.
- **SC-005**: The elevation gain reported for a flat test circuit with noisy raw elevation stays below 5 % of the lap distance in metres per kilometre (for example below 20 m for a 4 km lap).
- **SC-006**: Parents of registered riders can open the circuit view and read laps, distance and description on a mobile connection before the map finishes loading; parents of non-registered riders see no course data in 100 % of cases.
- **SC-007**: Every válida created before this feature keeps rendering its results identically until course data is added.

## Assumptions

- **Owner decisions (2026-09-15)**: the circuit recordings (full and reduced) are made by the coach with their own device; only the clean lap shape is kept and the original file is discarded. Laps per category are defined per válida with a prefill from the previous válida of the same series. Each válida is loaded from scratch: reusing a stored circuit across válidas is out of scope. The description is structured plus free text. Course data can be entered both when creating/editing a válida and as an optional step of the results import, and can be added to válidas that already exist.
- **Variants**: any number of variants per válida is allowed, not only two; the reduced route is just a variant with its own recording, so there is no "percentage" field — the ratio is visible from the two distances.
- **Lap detection**: a lap is considered closed when the route returns within a short distance of its start after a minimum ridden distance; the coach can always override with the number of recorded laps. Distance is measured along the ground from positions; elevation gain is computed after smoothing and reported as unknown when the recording has no elevation.
- **Rounding**: distances to 0.1 km, speeds to 0.1 km/h, elevation gain to whole metres.
- **Family visibility**: a parent sees course data of a válida when one of their children is on its roster or has a result in it; the club calendar entry alone does not grant it.
- **Prefill source**: the previous válida is the one with the highest sequence number below the current one in the same series; categories are matched by their catalogue identity.
- **Description vocabulary**: terrain types and key sectors are fixed lists chosen with the coach during planning (initial proposal: terrain — sendero, trocha, mixto, pista, pavimento; sectors — subida larga, bajada técnica, rock garden, singletrack, plano rápido, paso de quebrada, zona de raíces, escalones), editable as product copy without a new feature.
- **AI analysis**: course facts enter the analysis as a new block with the same "present / SIN DATO" discipline the conditions block already follows; the season summary receives the same facts per válida. Free notes are excluded by design because they are unreviewed coach text.
- **Formats (planning decision 2026-09-15)**: GPX only. The training-session upload accepts FIT but never parses it; parsing FIT geometry would need a new dependency and a second privacy-stripping path, and every device the coach uses exports GPX. FIT can be added later without changing the data model.
- **Reuse**: the file validation already built for training-session routes is reused; the map display is rebuilt on the stored lap shape (no file is served); no new external dependency is expected. Storage of the lap shape must survive a deployment of the backend, unlike the current training-session route files.
- **Cost**: no change to spending caps; the analysis prompt grows by a few lines only when course data exists.
- **Language**: all product copy is español neutro (Colombia) with full diacritics; this specification and the planning artifacts are in English per the constitution's language policy.
- **Out of scope**: per-lap split times; any GPS or activity data of riders (Strava or devices); drawing, editing or measuring a route in the platform; copying a circuit between válidas; public sharing outside logged-in users; changes to the results PDF parser or to import deduplication; weather or surface conditions (already covered).
