# Feature Specification: Interval Block Duration Usability — mm:ss Entry and Open-Ended "Until Lap Button" Blocks

**Feature Branch**: `main` (per explicit user request, no dedicated branch — work happens on the current branch)

**Created**: 2026-07-22

**Status**: Draft

**Input**: User description: "The interval block editor is incomplete and hard to use because everything is in seconds; I want to be able to say the first block is free/open until the lap button is pressed, like other platforms (Garmin, TrainingPeaks, intervals.icu) do."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Enter block durations in minutes and seconds (Priority: P1)

As a coach building an interval structure for a training session, I enter each block's duration as minutes and seconds (e.g., `5:00` for a five-minute warmup) instead of a raw seconds count (e.g., `300`), so that authoring a structure is fast and free of mental arithmetic errors.

**Why this priority**: Every block of every structure goes through this input. Raw seconds is the single biggest friction point reported by the coach ("todo está en segundos, no es fácil de manejar") and affects fixed-time blocks — the vast majority — regardless of whether open-ended blocks are ever used.

**Independent Test**: Can be fully tested by creating a structure with several fixed-time blocks using only minutes:seconds entry and verifying the stored durations and the total estimated duration are correct. Delivers value even if no other story ships.

**Acceptance Scenarios**:

1. **Given** the structure editor with a new block, **When** the coach enters 5 minutes 00 seconds, **Then** the block is saved with a 5-minute duration and the block row and total show `5:00`.
2. **Given** a block with duration 90 seconds saved before this feature, **When** the coach opens the editor, **Then** the duration displays as `1:30` (not `90`) and can be edited in minutes:seconds.
3. **Given** the duration entry, **When** the coach enters 0 minutes 0 seconds, **Then** a validation message blocks saving (duration must be greater than zero).
4. **Given** the seconds part of the entry, **When** the coach types a value of 60 or more seconds, **Then** the editor prevents it or normalizes it so the stored duration is unambiguous (e.g., seconds field constrained to 0–59).
5. **Given** the template library block editor, **When** the coach edits a template block duration, **Then** the same minutes:seconds entry is used.

---

### User Story 2 - Mark a warmup or cooldown as open-ended ("Libre — hasta botón de vuelta") (Priority: P2)

As a coach, I mark the first (warmup) and/or last (cooldown) block of a structure as open-ended: the athlete rides it as long as they need and ends it by pressing the lap button on their device (iGPSport/Magene/Garmin), exactly as the industry-standard platforms model it (Garmin "Lap Button Press" step duration, TrainingPeaks "open-ended steps", intervals.icu "Press lap" flag).

**Why this priority**: This is the capability gap that motivated the request — today the coach must invent a fake fixed duration for free-length warmups. It builds on top of Story 1's duration-type presentation.

**Independent Test**: Create a structure whose warmup is open-ended and whose remaining blocks are fixed-time; verify it saves, displays "Libre — hasta botón de vuelta", and requires no duration value for that block.

**Acceptance Scenarios**:

1. **Given** a warmup block, **When** the coach selects duration type "Libre — hasta botón de vuelta", **Then** the duration entry disappears/disables for that block and the structure saves without a duration for it.
2. **Given** an open-ended block, **When** the coach views it, **Then** intensity zone and cadence targets are still required and shown (open duration ≠ open intensity).
3. **Given** a work or recovery block, **When** the coach looks for the open-ended option, **Then** it is not offered (only warmup and cooldown block types can be open-ended).
4. **Given** a block inside a repeat group, **When** the coach tries to make it open-ended (or tries to add an open-ended block to a repeat group), **Then** the editor blocks it with an explanatory message (no platform supports lap-press steps inside repeats).
5. **Given** a structure with an open-ended warmup and 20:00 of fixed blocks, **When** the coach views the total estimated duration, **Then** it clearly indicates the fixed total plus an open part (e.g., "20:00 + calentamiento libre") instead of silently omitting or miscounting.
6. **Given** the 10–12 age band, **When** an open-ended block targets Z3 or higher, **Then** the existing age-gate rules apply unchanged (hard block for 10–12, confirm-and-record otherwise).

---

### User Story 3 - Plan-vs-actual comparison understands open-ended blocks (Priority: P3)

As a coach reviewing the automatic plan-vs-actual comparison after a linked Strava activity, I see the lap matched to an open-ended block reported informationally (its real duration shown) without it ever being judged "fuera de tolerancia", because an open block has no planned duration to compare against.

**Why this priority**: Without it, open-ended blocks would corrupt the comparison (division against a missing planned duration or false out-of-tolerance flags). It only matters once Story 2 exists.

**Independent Test**: Link an activity with laps to a session whose structure has an open-ended warmup; verify the first lap is consumed by the warmup with an informational status and all subsequent blocks still match positionally with the existing ±30% tolerance.

**Acceptance Scenarios**:

1. **Given** a structure with an open-ended warmup followed by fixed blocks, **When** the comparison runs, **Then** the warmup consumes the first qualifying lap, is shown with its actual duration and a distinct informational status (e.g., "libre"), and is never marked "fuera_tolerancia".
2. **Given** an open-ended block with no corresponding lap in the activity, **When** the comparison runs, **Then** that block is reported as "sin_dato" exactly like a fixed block with no lap.
3. **Given** structures already compared before this feature, **When** their stored comparisons are viewed, **Then** they render unchanged (no retroactive recomputation required).
4. **Given** the comparison table, **When** an open-ended block row is displayed, **Then** the planned-duration cell shows "Libre" instead of a time.

---

### User Story 4 - PDF instructivo and templates carry the open-ended instruction (Priority: P3)

As a coach generating the brand-specific PDF instructivo (iGPSport/Magene/Garmin) or reusing a template from the club library, open-ended blocks appear with the instruction "Libre — hasta botón de vuelta" instead of a fabricated time, and templates preserve the duration type when attached to a session.

**Why this priority**: The PDF is how athletes actually execute the structure on their devices — the instructivo already tells them to press the lap button per block, so the open instruction closes the loop. Depends on Story 2.

**Acceptance Scenarios**:

1. **Given** a structure with an open-ended warmup, **When** the PDF instructivo is generated for any supported brand, **Then** the warmup row reads "Libre — hasta botón de vuelta" (with zone and cadence still shown) instead of "X min Y s".
2. **Given** a template containing an open-ended cooldown, **When** the coach attaches it to a session (copy-on-attach), **Then** the copied structure keeps the open-ended duration type.
3. **Given** the template library editor, **When** the coach authors template blocks, **Then** the same duration-type rules apply as in the structure editor (warmup/cooldown only, never inside repeat groups).

---

### Edge Cases

- Structure whose **every** block is open-ended (open warmup + open cooldown, no work): allowed by the rules above only if it has no work/recovery blocks; total estimated duration then shows no fixed part (e.g., "Duración libre"). The existing minimum-structure validations (if any) still apply.
- Editing an existing fixed-time warmup into open-ended and back: duration value is restored/re-entered by the coach; no silent data loss without warning.
- A block marked open-ended while it is part of a repeat group (e.g., group toggled after type selection): validation must catch it at save time as well as in the UI, in whichever order the coach performs the actions.
- Comparison where the athlete never pressed the lap button (one long lap spanning warmup + first work block): positional matching will attribute the long lap to the open warmup and shift the rest — subsequent blocks may show "sin_dato"/mismatch. This is accepted behavior (identical to today's behavior when laps are missing) and the existing tolerance caption/help should not claim otherwise for open blocks.
- Laps shorter than the existing minimum lap noise threshold still get discarded before matching, including for open-ended blocks.
- Old clients or in-flight drafts submitting a block without a duration type: treated as fixed-time (backward-compatible default).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The structure editor and the template library editor MUST let the coach enter fixed block durations as minutes and seconds (mm:ss semantics), replacing the raw-seconds numeric entry. Stored durations remain an exact whole number of seconds; no precision is lost round-tripping display ↔ storage.
- **FR-002**: The duration entry MUST reject a total of zero and MUST constrain or normalize the seconds part so the resulting duration is unambiguous (seconds component 0–59).
- **FR-003**: Everywhere a block duration is displayed (block rows, totals, comparison table, PDF instructivo), it MUST render in minutes:seconds form, never as a raw seconds integer.
- **FR-004**: Each block MUST have a duration type: **fixed time** (default, current behavior) or **open — until lap button press** (UI copy: "Libre — hasta botón de vuelta"). Blocks without an explicit type (pre-existing data, older drafts) MUST be treated as fixed time.
- **FR-005**: Open-ended duration MUST be allowed only on warmup and cooldown block types, and MUST be rejected for any block that belongs to a repeat group. These rules MUST be enforced both in the editor UI and by server-side validation at save time.
- **FR-006**: Open-ended blocks MUST NOT carry a duration value, and MUST still require the same intensity zone and cadence targets as fixed blocks. All existing intensity guardrails (cadence ≥ 60 rpm, Z3+ age gate for the 10–12 band with confirm-and-record otherwise) apply unchanged to open-ended blocks.
- **FR-007**: The total estimated duration MUST sum only fixed-time blocks (respecting repeat expansion as today) and, when open-ended blocks exist, MUST visibly indicate that the total is partial (e.g., "20:00 + calentamiento libre"); a structure with no fixed blocks shows an explicit open-duration label instead of "0:00".
- **FR-008**: The plan-vs-actual comparison MUST consume a lap for an open-ended block positionally (same ordering rules as today), report the lap's actual duration with a distinct informational status, and MUST never classify an open-ended block as out-of-tolerance. An open-ended block with no lap MUST be reported with the existing "no data" status. Existing stored comparisons MUST remain valid and render unchanged.
- **FR-009**: The PDF instructivo for every supported brand MUST render open-ended blocks as "Libre — hasta botón de vuelta" (keeping zone and cadence guidance) in place of the fixed-time text.
- **FR-010**: Interval templates MUST support the same duration types under the same rules, and copy-on-attach MUST preserve the duration type of every block.
- **FR-011**: All pre-existing structures, templates, and comparisons MUST keep their current meaning without data migration side effects visible to users: every existing block behaves as fixed time with its stored duration.

### Key Entities

- **Interval structure block**: gains a duration-type dimension — *fixed time* (has a duration in whole seconds, > 0) or *open until lap press* (no duration). Position, block type (warmup/work/recovery/cooldown), intensity zone, cadence, and repeat-group membership are unchanged; open type is mutually exclusive with repeat-group membership and restricted to warmup/cooldown.
- **Interval template block**: mirrors the structure block, including the duration-type dimension; copied verbatim on attach.
- **Plan-vs-actual comparison row**: gains one informational outcome for open-ended blocks ("libre" — lap consumed, actual duration shown, no tolerance judgment) alongside the existing outcomes (cumplido / fuera_tolerancia / sin_dato / extra).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can author a 6-block structure with typical durations (e.g., 10-minute warmup, 4×(2:00 work / 1:00 recovery), 5-minute cooldown) entering every duration directly in minutes and seconds, with zero manual conversion to raw seconds.
- **SC-002**: A coach can express "warmup free until lap button" without inventing a placeholder duration, and the generated PDF instructivo communicates it to the athlete in those terms.
- **SC-003**: 100% of structures, templates, and stored plan-vs-actual comparisons created before this feature display and behave exactly as before.
- **SC-004**: In comparisons of structures containing open-ended blocks, no open-ended block is ever reported as out-of-tolerance, while fixed blocks keep the existing ±30% judgment.
- **SC-005**: All duration displays across the feature (editor, totals, comparison, PDF) show minutes:seconds or the open-ended label; no raw-seconds integer remains visible to users.

## Assumptions

- The seconds-based storage unit is kept internally; this feature changes entry/display semantics and adds the open duration type — it does not introduce hours-scale blocks (mm:ss covers realistic youth XCO block lengths; totals may exceed 60 minutes and may display as they do today).
- Open-ended applies to duration only; intensity zone and cadence remain mandatory (Zwift-style "free ride" intensity is explicitly out of scope).
- Industry-pattern guardrails are adopted as stated: open-ended only for warmup/cooldown and never inside repeat groups (consistent with Garmin/TrainingPeaks/intervals.icu behavior researched for this spec).
- The comparison's positional matching strategy and ±30% tolerance for fixed blocks are unchanged; whether the engine version identifier is bumped is an implementation decision for planning.
- Distance-based durations, power targets, and any change to Strava ingestion or lap capture are out of scope.
- Existing rows default to fixed time; no user-visible data migration.
- Product end-user copy is in español neutro (Colombia) — canonical label "Libre — hasta botón de vuelta" (final wording may be polished at implementation without changing meaning).
