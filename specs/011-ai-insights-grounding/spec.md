# Feature Specification: Faithful, Grounded AI Insights for Competitions

**Feature Branch**: `011-ai-insights-grounding`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Faithful, Grounded AI Insights for Competitions — the Competitions AI analysis fabricates race conditions (verified: Válida IV Cali 2026-05-17 described as dry/sunny when recorded as wet/cloudy/25°C), analyzes every athlete as Pre-PHV/Bambino regardless of real maturation and age group, reviews only one draft per batch, and shows a hardcoded 'Confianza media' badge. Full integrity pass: ground all analysis and chat output in recorded data, omit unrecorded conditions entirely, use real maturation/LTAD group, review every draft, compute confidence for real, and let the coach re-generate stored analyses that contain fabricated content."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Race conditions in the analysis match what was recorded (Priority: P1)

The coach launches a per-válida or group AI analysis for a competition. Every statement the analysis makes about race conditions (climate, temperature, track surface, altitude) reflects exactly what is recorded for that event in the Conditions tab. When an event has no recorded conditions, the analysis omits the conditions topic entirely — it never mentions climate or track and never fills in plausible-sounding values.

**Why this priority**: This is the reported, verified bug. Fabricated facts in a parent-facing product destroy trust in the entire AI feature; nothing else matters if the analysis lies about basic observable facts.

**Independent Test**: Re-run the analysis for the known case (Válida IV, Cali, 2026-05-17 — recorded as wet surface, cloudy, 25°C, 1000 msnm) and verify the output either states those exact recorded conditions or omits the topic; then clear the conditions of a test event, re-run, and verify the analysis contains no mention of climate or track conditions.

**Acceptance Scenarios**:

1. **Given** an event with recorded conditions (surface=Húmeda, climate=Nublado, 25°C, 1000 msnm), **When** the coach generates a per-válida analysis, **Then** any condition mentioned in the output matches the recorded values and no contradictory or additional condition is stated.
2. **Given** an event with no recorded conditions, **When** the coach generates an analysis, **Then** the output contains no reference to climate, weather, or track surface — neither invented values nor "no data" filler.
3. **Given** an event with partially recorded conditions (e.g., only temperature), **When** the analysis is generated, **Then** only the recorded fields may be mentioned; absent fields are omitted entirely.
4. **Given** a group launch covering several athletes and válidas, **When** the analyses are generated, **Then** every analysis in the batch satisfies the same grounding rule for its own event.

---

### User Story 2 - Each athlete is analyzed with their real maturation status and age group (Priority: P1)

The coach generates an analysis for any athlete and the guidance reflects that athlete's actual maturation status (Pre-PHV / Circa-PHV / Post-PHV, from their anthropometric history) and their actual age/LTAD group (10–12 vs 13–15), instead of silently treating everyone as a Pre-PHV 10–12 rider.

**Why this priority**: Recommending loads and training framing for the wrong maturation phase violates the club's non-negotiable principle that biological age outranks chronological age, and gives a 13–15 rider guidance designed for a 10–12 child. This is a sports-safety and credibility issue on par with the fabrication bug.

**Independent Test**: Generate an analysis for a known Circa-PHV athlete aged 12.8 (the reported case) and for a 13–15 athlete, and verify the analysis context and recommendations reflect Circa-PHV and the 13–15 group respectively — never a Pre-PHV/10–12 default.

**Acceptance Scenarios**:

1. **Given** an athlete whose latest anthropometric record classifies them as Circa-PHV, **When** an analysis is generated, **Then** the analysis treats the athlete as Circa-PHV (not Pre-PHV).
2. **Given** a 13–15 (juvenil) athlete, **When** an analysis is generated, **Then** the developmental guidance applied corresponds to the 13–15 group (e.g., structured work allowed within limits), not the 10–12 play-based block.
3. **Given** an athlete with no anthropometric records, **When** an analysis is generated, **Then** the analysis makes no maturation-phase claim and applies age-group guidance derived from the athlete's chronological age only.

---

### User Story 3 - Every analysis in a batch is quality-reviewed, including faithfulness to the data (Priority: P2)

When the coach launches an analysis run that produces several drafts (up to one per válida), every draft — not just the first — passes the quality review before it is delivered. The review checks the structure actually produced by the current analysis format and can flag statements that contradict the recorded event and result data.

**Why this priority**: Without full review coverage and data-aware review, fabrications (conditions, times, positions) can ship unchecked in most of the batch. It builds directly on P1 grounding but is independently testable.

**Independent Test**: Launch a group analysis covering N ≥ 2 válidas and verify N review verdicts exist (one per draft); seed a draft with a statement contradicting recorded data and verify the review flags it.

**Acceptance Scenarios**:

1. **Given** a run producing N drafts, **When** the run completes, **Then** each of the N drafts has its own review verdict recorded.
2. **Given** a draft containing a statement that contradicts the recorded event data (e.g., wrong track condition or wrong finishing position), **When** the review evaluates it, **Then** the contradiction is flagged as an issue.
3. **Given** a well-formed draft using the current analysis section structure, **When** the review evaluates it, **Then** it is not penalized for lacking sections that belong to an older format.

---

### User Story 4 - The confidence badge reflects the actual analysis (Priority: P2)

The coach sees a confidence indicator next to each analysis that is computed from the actual run (e.g., review outcome, data completeness), instead of always reading "Confianza media".

**Why this priority**: A constant badge is false reassurance for the coach and families. Once review coverage exists (P3 story), confidence becomes meaningful and cheap to surface.

**Independent Test**: Generate analyses under deliberately different circumstances (complete data + clean review vs. sparse data or flagged issues) and verify the displayed confidence differs accordingly.

**Acceptance Scenarios**:

1. **Given** an analysis whose review found no issues and whose event/athlete data was complete, **When** the insight is shown, **Then** its confidence is higher than that of an analysis with flagged issues or missing data.
2. **Given** any two analyses with materially different review outcomes, **When** both are displayed, **Then** their confidence indicators are not guaranteed to be identical (the value varies with the run, it is not a constant).

---

### User Story 5 - The competition chat is held to the same grounding rule (Priority: P3)

When the coach asks the competition chat about race conditions or other recorded facts, the answer uses only what is recorded for the event. If the information was not recorded, the chat says so instead of inventing an answer.

**Why this priority**: Fixing the analysis but leaving the chat free to fabricate would reintroduce the same trust problem through another door. Slightly lower priority because the chat is coach-facing only.

**Independent Test**: Ask the chat "¿cómo estaban la pista y el clima?" for an event with recorded conditions and for one without, and verify the answers match the recorded data and acknowledge absence respectively.

**Acceptance Scenarios**:

1. **Given** an event with recorded conditions, **When** the coach asks the chat about climate or track, **Then** the answer states the recorded values.
2. **Given** an event without recorded conditions, **When** the coach asks the chat about climate or track, **Then** the answer states that the conditions were not recorded and does not invent values.

---

### User Story 6 - Coach can re-generate a stored analysis that contains fabricated content (Priority: P3)

The coach opens a previously stored analysis (such as the Válida IV insight that fabricated the conditions) and replaces it with a freshly generated, faithful version in a single re-generate action. The replaced version becomes the one shown everywhere the insight is consumed.

**Why this priority**: Existing stored insights with fabricated content remain visible (and emailable to families) until replaced. Depends on P1/P2 being in place to produce a faithful replacement.

**Independent Test**: Re-generate the known fabricated insight (athlete 3, Válida 4) and verify the stored insight is replaced by one whose condition statements match the recorded data (or omit the topic).

**Acceptance Scenarios**:

1. **Given** a stored analysis with fabricated content, **When** the coach triggers re-generation for it, **Then** a new analysis is produced under the grounding rules and replaces the stored one as the current version.
2. **Given** a re-generation attempt that fails (e.g., AI service unavailable), **When** the failure occurs, **Then** the existing stored analysis remains intact and the coach is informed the re-generation did not complete.

---

### Edge Cases

- Event with partially recorded conditions: only the recorded fields may appear in the output; absent fields are omitted (no "unknown" filler in the parent-facing narrative).
- Athlete with no anthropometric records: no maturation claim is made; age-group guidance falls back to chronological age. The analysis must never present a default maturation value as fact.
- Free-text condition notes that contain a person's name or other PII must not reach the language model un-anonymized.
- A batch where one draft fails review while others pass: only the affected draft is blocked or flagged; the rest of the batch is not discarded.
- Re-generation of an insight whose underlying event data changed since the original run (e.g., conditions corrected afterwards): the new analysis reflects the current recorded data.
- Historical insights are never modified automatically; only an explicit coach action replaces them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every AI competition analysis (per-válida and group) MUST receive the recorded race conditions of the event it analyzes (climate, temperature, track surface, altitude, and condition notes) as part of its input data.
- **FR-002**: Analysis output MUST NOT state any race condition that differs from, or is absent in, the event's recorded conditions.
- **FR-003**: When an event has no recorded conditions, the analysis output MUST omit the conditions topic entirely — no mention of climate, weather, or track surface, and no placeholder text in the narrative.
- **FR-004**: When an event has partially recorded conditions, the analysis MAY mention only the recorded fields and MUST omit the unrecorded ones.
- **FR-005**: Every analysis MUST use the athlete's actual maturation status derived from their most recent anthropometric assessment; a default maturation value MUST never be substituted when real data exists.
- **FR-006**: Every analysis MUST use the athlete's actual age/LTAD group; the 10–12 guidance block MUST never be applied to a 13–15 athlete (and vice versa).
- **FR-007**: When an athlete has no anthropometric records, the analysis MUST make no maturation-phase claim and MUST derive age-group guidance from chronological age only.
- **FR-008**: In a run that produces multiple analysis drafts, the quality review MUST evaluate every draft individually before delivery, and each draft's verdict MUST be recorded.
- **FR-009**: The quality review MUST validate against the section structure the current analysis format actually produces, and MUST NOT penalize drafts for lacking sections from a retired format.
- **FR-010**: The quality review MUST receive the recorded event and result data relevant to each draft so it can flag statements that contradict that data (conditions, positions, times, gaps).
- **FR-011**: Each stored insight's confidence level MUST be computed from the actual run (at minimum reflecting review outcome and input-data completeness) and MUST NOT be a fixed constant.
- **FR-012**: The competition chat MUST answer questions about recorded event facts (including conditions) using only the recorded data, and MUST state when the requested information was not recorded instead of inventing it.
- **FR-013**: The coach MUST be able to re-generate any previously stored analysis in a single action; the new version replaces the stored one everywhere the insight is consumed, and the original is preserved or replaced according to the existing insight versioning behavior.
- **FR-014**: If re-generation fails, the previously stored analysis MUST remain unchanged and the coach MUST be informed of the failure.
- **FR-015**: Race-condition and maturation data supplied to the language model MUST pass through the existing anonymization safeguards; free-text condition notes MUST NOT expose any minor's personally identifiable information to the model.
- **FR-016**: All product-facing output (analysis narrative, chat answers, confidence labels) MUST remain in español neutro (Colombia).

### Key Entities

- **Race event conditions**: The recorded climate, temperature, track surface, altitude, and notes of a competition event. Already captured today; this feature makes them the single source of truth for what any AI output may say about conditions.
- **Athlete maturation profile**: The maturation status (Pre-PHV / Circa-PHV / Post-PHV) and age/LTAD group of an athlete, derived from existing anthropometric assessments and date of birth. Consumed, not modified, by this feature.
- **Analysis insight**: A stored per-válida or season analysis for an athlete, with its confidence level and review verdict. Gains a real (computed) confidence and the ability to be replaced via coach-initiated re-generation.
- **Review verdict**: The quality-review outcome for one analysis draft (approval, severity, issues). Extended conceptually to exist per draft in a batch and to include data-contradiction findings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero fabricated race-condition statements: in a verification set of generated analyses (including the known Válida IV / Cali case), 100% of condition statements match the event's recorded data, and analyses for events without recorded conditions contain zero mentions of climate or track.
- **SC-002**: 100% of athletes with anthropometric data are analyzed under their correct maturation status, and 100% of athletes are analyzed under their correct age/LTAD group — no analysis defaults to Pre-PHV or to the 10–12 block when real data says otherwise.
- **SC-003**: In a group run producing N drafts, N review verdicts are recorded (review coverage = 100%, up from 1 per batch).
- **SC-004**: A seeded draft containing a statement that contradicts recorded data is flagged by the review in at least 9 out of 10 trials.
- **SC-005**: Confidence levels observed across a representative set of runs with differing review outcomes and data completeness take at least two distinct values (the indicator demonstrably varies; it is no longer constant).
- **SC-006**: The coach can replace a stored fabricated analysis with a faithful one in a single re-generate action, and the known fabricated insight (athlete 3, Válida 4) is replaceable this way end to end.

## Assumptions

- The conditions recorded through the existing capture flows (ingestion wizard and the Conditions tab editor) are the authoritative source of truth; no new capture or editing UI is in scope.
- The existing maturation (Mirwald PHV) and age/category computations are correct; this feature only ensures the analysis pipeline consumes their real outputs instead of defaults.
- Maturation status for an analysis comes from the athlete's most recent anthropometric assessment available at generation time; staleness handling beyond "use the latest" is out of scope.
- Re-generation is coach-initiated and per-insight; no bulk or automatic rewrite of historical analyses occurs.
- A simple, deterministic confidence scheme derived from review outcome and input-data completeness is acceptable; a calibrated statistical confidence model is out of scope.
- The narrative structure, visual design, and newsletter formats of the analyses do not change; only their factual faithfulness, grounding inputs, review coverage, and confidence computation do.
- The existing anonymization step continues to operate; this feature extends what data flows through it, not how anonymization works.
