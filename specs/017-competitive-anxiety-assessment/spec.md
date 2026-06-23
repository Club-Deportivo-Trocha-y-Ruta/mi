# Feature Specification: Competitive Anxiety Assessment

**Feature Branch**: `claude/spec-kit-agent-setup-poepvz` (developed on the designated session branch; spec directory `017-competitive-anxiety-assessment`)

**Created**: 2026-06-23

**Status**: Draft

**Input**: User description: "Construye un módulo de 'Evaluación de Ansiedad Competitiva' para una plataforma de gestión de entrenamiento de ciclistas de montaña XCO juveniles (10–15 años) del Club Trocha y Ruta." (full description in the package "Componente Ansiedad Competitiva (CSAI-2R)", Section 2)

## Overview

The Competitive Anxiety Assessment module lets the coach administer, store, score, and interpret **state** competitive-anxiety questionnaires for youth XCO athletes (ages 10–15) around competitions, and review each athlete's evolution across the season. Its purpose is to **support psychological preparation** (arousal regulation, cognitive reframing, confidence building) and to inform the coach's pre-race conversation. It is explicitly **not** a diagnostic or mental-health-screening tool.

> **Language note**: This spec is a development artifact written in English per the project working-language policy. All athlete- and coach-facing copy (UI strings, questionnaire wording, generated interpretations, the LLM interpretation system prompt) MUST be in español neutro (Colombia). Governed by Constitution Principle V (Youth Psychological Assessment Safeguards) and Principle III (Language policy).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure a pre-race assessment (Priority: P1)

The coach creates an assessment for a single athlete or a group, associated with a calendar event (with its A/B/C priority) and a date/time. The system auto-selects the instrument by each athlete's age band and allows a manual override with an explicit warning.

**Why this priority**: This is the entry point of the whole module. Without configuration there is nothing to answer, score, or interpret. It also encodes the most safety-critical rule (age-driven instrument selection), so it must exist first.

**Independent Test**: Can be fully tested by signing in as a coach, creating an assessment tied to a Race A event for a mixed-age group, and verifying that each athlete receives the correct instrument (SAS-2 for under-13, CSAI-2R for 13–15) and that overriding to CSAI-2/2R for an under-13 raises a warning. Delivers value as a ready-to-send assessment.

**Acceptance Scenarios**:

1. **Given** a coach and an athlete aged 11, **When** the coach creates an assessment for that athlete, **Then** the instrument auto-selects to SAS-2.
2. **Given** a coach and an athlete aged 14, **When** the coach creates an assessment, **Then** the instrument auto-selects to CSAI-2R by default.
3. **Given** an athlete aged 11, **When** the coach manually overrides the instrument to CSAI-2R, **Then** the system shows a warning that CSAI-2/2R is below its validated range for under-13s before allowing the override.
4. **Given** a calendar with a Race A event, **When** the coach creates a group assessment linked to that event, **Then** the assessment stores the event reference and its A/B/C priority.
5. **Given** a coach completing configuration, **When** they confirm, **Then** the full configure-and-send flow for a group can be completed in under 2 minutes.

---

### User Story 2 - Athlete answers the questionnaire (Priority: P1)

The athlete completes the questionnaire on their own device. The UI is simple, jargon-free, one question at a time, with the instruction "responde cómo te sientes ahora mismo" (answer how you feel right now). Each item uses a 1–4 Likert scale (1 = "nada", 4 = "mucho").

**Why this priority**: Without responses there are no scores. Paired with Story 1 this forms the minimum viable loop (configure → answer). Mobile accessibility for minors is a core requirement.

**Independent Test**: Can be tested by opening an assigned assessment on a phone-sized viewport, answering all items on the 1–4 scale one at a time, and confirming the responses are captured item-by-item. Delivers a completed response set.

**Acceptance Scenarios**:

1. **Given** an assigned assessment, **When** the athlete opens it on a mobile device, **Then** items are presented one at a time with a clear 1–4 scale and age-appropriate language.
2. **Given** an athlete answering, **When** they submit, **Then** every individual item answer is persisted (not only the computed scores).
3. **Given** an athlete who skips one or more items, **When** they submit, **Then** the response is accepted and marked as partial.
4. **Given** any athlete-facing screen, **When** rendered, **Then** no clinical interpretation is shown — at most a short, encouraging message.

---

### User Story 3 - Score the responses (Priority: P1)

The system computes the three subscale scores (cognitive anxiety, somatic anxiety, self-confidence) according to the **official scoring key** of the selected instrument, handling reverse-scored items if applicable, and averaging over answered items when responses are missing.

**Why this priority**: Scoring is the bridge between raw answers and any interpretation. It must be correct and recomputable, and it carries the licensed-source constraint.

**Independent Test**: Can be tested by feeding a known set of item answers for each instrument and asserting the resulting subscale scores match the official key and the documented ranges. Delivers verified scores.

**Acceptance Scenarios**:

1. **Given** a complete CSAI-2R response, **When** scored, **Then** each subscale = (sum of its items / number of items) × 10, yielding a 10–40 range (7 somatic, 5 cognitive, 5 self-confidence).
2. **Given** a complete CSAI-2 response (historical), **When** scored, **Then** each subscale = sum of its 9 items (range 9–36) and total ranges 27–108.
3. **Given** a SAS-2 response, **When** scored, **Then** the cognitive subscale (worry + concentration disruption) and somatic subscale follow the SAS-2 official key.
4. **Given** a partial response, **When** scored, **Then** subscales are averaged over answered items and the result is flagged as partial.
5. **Given** stored item-by-item answers, **When** a recompute is requested, **Then** the same scores are reproduced.
6. **Given** any subscale, **When** interpreted, **Then** higher cognitive/somatic = more anxiety and higher self-confidence = more confidence (self-confidence is a positive dimension and is NOT reverse-scored).

---

### User Story 4 - Generate per-athlete interpretation (Priority: P1)

For each athlete the system generates a reading that identifies which dimension is elevated/low, the dominant pattern, and 2–3 concrete mental-skills strategies, written in a mastery climate. The interpretation is anchored to the athlete's own baseline and, when available, to the trend versus previous assessments. The reading is produced by a dedicated LLM interpretation system prompt (provided by the club, in Spanish) returning structured JSON; a **rule-based fallback** MUST exist when the LLM is unavailable.

**Why this priority**: This is the core value to the coach — turning numbers into an actionable, safe, age-appropriate reading. The fallback guarantees the module still works without the LLM.

**Independent Test**: Can be tested by providing scores plus a baseline and asserting the JSON output contains a per-dimension reading, dominant pattern, 2–3 strategies, an adaptable coach message, and flags — and that with the LLM disabled, the rule-based fallback returns the same schema. Delivers an actionable interpretation.

**Acceptance Scenarios**:

1. **Given** scores and an existing baseline, **When** interpretation runs, **Then** each subscale reading compares against the athlete's own baseline (relative change), not against clinical cutoffs.
2. **Given** the interpretation output, **When** returned, **Then** it conforms to the structured schema: `resumen`, `por_dimension` (cognitiva, somatica, autoconfianza), `estrategias` (2–3), `mensaje_para_el_atleta`, `banderas`.
3. **Given** any generated text, **When** reviewed, **Then** it contains no diagnostic language and is framed in process/effort/coping, never results, podiums, or comparisons with other athletes.
4. **Given** the LLM is unavailable, **When** interpretation is requested, **Then** the rule-based fallback produces a valid reading in the same schema using the coarse bands and the documented pattern→strategy mapping.
5. **Given** sustained high anxiety AND low confidence across evaluations, **When** interpreted, **Then** a flag is raised recommending an individual conversation and, if it persists, referral to a health professional.

---

### User Story 5 - Individual and group dashboards (Priority: P2)

The coach sees, per athlete, the three scores, their evolution versus the April baseline, the interpretation, and any alerts. At the group level, the coach sees who arrives with high somatic vs. high cognitive vs. low confidence, to plan the warm-up and the pre-race huddle.

**Why this priority**: High value for race-day planning, but depends on Stories 1–4 producing data first. Group triage is what makes the module operationally useful at the event.

**Independent Test**: Can be tested by loading a set of scored, interpreted assessments for a group and verifying the individual view shows scores + baseline evolution + interpretation + alerts, and the group view clearly separates the three dominant patterns. Delivers race-day decision support.

**Acceptance Scenarios**:

1. **Given** an athlete with multiple assessments, **When** the coach opens the individual view, **Then** the three subscale scores and their evolution vs. the April baseline are shown, with the interpretation and any flags.
2. **Given** a group with scored assessments, **When** the coach opens the group view, **Then** athletes are grouped/visually distinguished by dominant pattern (somatic-high, cognitive-high, confidence-low) for warm-up and huddle planning.
3. **Given** an athlete with an active alert flag, **When** the group view loads, **Then** the alert is surfaced prominently.

---

### User Story 6 - Import historical results (Priority: P3)

The coach uploads results for athletes already assessed (file format to be defined in `/clarify`). The system scores and interprets them retroactively to build the baseline and the time series.

**Why this priority**: Valuable for continuity and for establishing baselines from existing data, but not required for the live pre-race loop. Best done after the core scoring/interpretation engine is proven.

**Independent Test**: Can be tested by importing a sample historical file (including CSAI-2 27-item data) and verifying records are scored, charted, and that the earliest record can seed the baseline. Delivers a populated history.

**Acceptance Scenarios**:

1. **Given** a historical results file, **When** imported, **Then** each record is scored using the correct instrument's key and stored with item-level answers when available.
2. **Given** imported CSAI-2 (27-item) historical data, **When** scored, **Then** it is interpreted with the 9/9/9 structure and 9–36 subscale ranges.
3. **Given** imported records for an athlete with no prior baseline, **When** processed, **Then** the earliest qualifying record (April) can be set as the baseline and later records form the time series.
4. **Given** imported and interpreted records, **When** the coach opens the dashboards, **Then** the historical series is correctly charted alongside new assessments.

---

### Edge Cases

- **Incomplete responses**: average over answered items and mark the assessment as partial; never block submission for skipped items.
- **Athlete with no baseline yet**: the first assessment becomes the baseline; the interpretation explicitly notes that no prior baseline exists and uses only coarse bands.
- **Athlete crossing from 12 to 13 mid-season**: the instrument changes (SAS-2 → CSAI-2R); the system warns that the two series are not directly comparable and does not splice them into a single comparable trend line.
- **Sustained very-high anxiety AND very-low confidence**: raise an alert flag, suggest an individual conversation, and if it persists recommend a health professional.
- **Manual override to an age-inappropriate instrument**: allowed only after an explicit warning; the override and warning acknowledgment are recorded.
- **LLM unavailable or returns malformed JSON**: fall back to the rule-based interpreter and record that the fallback was used.
- **Missing guardian consent**: the assessment cannot be administered/stored for that athlete until consent is registered.

## Requirements *(mandatory)*

### Functional Requirements

**Instrument selection & safeguards**

- **FR-001**: System MUST support three instruments — CSAI-2R (17 items), SAS-2 (15 items), and CSAI-2 (27 items, import/historical only) — each on a 1–4 Likert scale measuring cognitive anxiety, somatic anxiety, and self-confidence.
- **FR-002**: System MUST auto-select the instrument by the athlete's age band: SAS-2 for ages 10–12, CSAI-2R for ages 13–15 (default).
- **FR-003**: System MUST suggest/force SAS-2 for athletes under 13 and MUST display an explicit warning when a coach attempts to apply CSAI-2/2R to an under-13 athlete (below its validated range), recording the override.
- **FR-004**: System MUST source item content and the item→subscale scoring key from the licensed official source of each instrument and MUST NOT invent items. The scoring key MUST be loaded as data, not hard-assumed.

**Configuration**

- **FR-005**: Coaches MUST be able to create an assessment for a single athlete or a group, associated with a calendar event, its A/B/C priority, and a date/time.
- **FR-006**: System MUST allow administration to be tied to the competition calendar, with the intended administration window of ~1–2 h before Race A events.

**Answering**

- **FR-007**: Athletes MUST be able to answer on a mobile device with a simple, jargon-free, one-question-at-a-time UI using the prompt "responde cómo te sientes ahora mismo".
- **FR-008**: System MUST NOT show clinical interpretations to the athlete; at most a short, encouraging message.

**Scoring**

- **FR-009**: System MUST compute the three subscale scores per the official key, handling reverse-scored items where applicable, and MUST treat self-confidence as a positive dimension (not reverse-scored).
- **FR-010**: System MUST persist every item-by-item answer in addition to the computed scores, so scores can be recomputed at any time.
- **FR-011**: When responses are missing, System MUST average over answered items and mark the assessment as partial.
- **FR-012**: System MUST apply the documented subscale structures and ranges: CSAI-2R → (sum/items)×10, range 10–40 (7 somatic / 5 cognitive / 5 self-confidence); CSAI-2 → sum per 9-item subscale, range 9–36, total 27–108; SAS-2 → its own key (cognitive = worry + concentration disruption, plus somatic).

**Interpretation**

- **FR-013**: System MUST generate a per-athlete interpretation containing: a summary of the dominant pattern, a per-dimension reading, 2–3 concrete actionable strategies, a short adaptable coach message, and alert flags — returned in the structured JSON schema (`resumen`, `por_dimension`, `estrategias`, `mensaje_para_el_atleta`, `banderas`).
- **FR-014**: System MUST anchor interpretation to the athlete's own baseline (relative change) and, when present, to the trend versus previous assessments; absolute low/moderate/high bands are coarse guidance only and MUST NOT be presented as diagnostic thresholds.
- **FR-015**: System MUST frame all generated text in a mastery climate (process/effort/coping) and MUST NOT emit diagnostic language or reference results, podiums, rankings, or comparisons between athletes.
- **FR-016**: System MUST provide a rule-based interpretation fallback that returns the same schema when the LLM is unavailable or returns invalid output, and MUST record that the fallback was used.
- **FR-017**: System MUST raise an alert flag recommending an individual conversation (and, if sustained, professional referral) when anxiety is very high and confidence very low across evaluations.

**Dashboards**

- **FR-018**: Coaches MUST be able to view, per athlete, the three scores, their evolution versus the April baseline, the interpretation, and any alerts.
- **FR-019**: Coaches MUST be able to view a group panel that distinguishes athletes by dominant pattern (high somatic / high cognitive / low confidence) for warm-up and huddle planning.

**Baseline & history**

- **FR-020**: System MUST treat the first assessment (April) as the athlete's baseline per subscale when none exists, and MUST flag interpretations made without a baseline.
- **FR-021**: Coaches MUST be able to import historical results, which the system scores and interprets retroactively to build the baseline and time series. (Import file format: see Clarifications.)
- **FR-022**: When an athlete changes age band mid-season (instrument change), System MUST warn that SAS-2 and CSAI-2R series are not directly comparable and MUST NOT merge them into one comparable trend.

**Privacy, access & export**

- **FR-023**: System MUST restrict assessment data access to the coach role and MUST require registered guardian consent before an athlete can be assessed/stored.
- **FR-024**: System MUST NOT send automatic messages to athletes or parents; the module only informs the coach's conversation.
- **FR-025**: System MUST keep all athlete- and coach-facing copy in español neutro (Colombia), with technical terms in English in parentheses where helpful.
- **FR-026**: System MUST allow the coach to export assessment data to CSV/JSON.
- **FR-027**: System MUST NOT expose minors' personal data (name, DOB, medical detail) in logs, error messages, or any third-party/AI-provider prompt, consistent with minors-privacy and data-minimization rules.

### Key Entities *(include if feature involves data)*

- **Athlete**: the youth rider being assessed; key attributes: identifier, date of birth (for age band), age group (10–12 / 13–15). Reuses the existing athletes model.
- **Instrument**: a questionnaire definition; attributes: type (CSAI-2 / CSAI-2R / SAS-2), version, subscale definitions, and the official scoring key (loaded as data).
- **Assessment**: one administration to one athlete; attributes: athlete reference, instrument, event reference (calendar FK), A/B/C priority, date/time, item-by-item answers, computed subscale scores, partial flag, generated interpretation, alert flags, fallback-used flag.
- **Baseline**: per athlete and per subscale, the reference value fixed at the initial (April) assessment.
- **Interpretation**: the structured reading attached to an assessment (summary, per-dimension reading, strategies, coach message, flags).
- **Guardian consent**: the record that authorizes assessing/storing a given minor's data.
- **(Optional) Daily wellness link**: an optional association to the existing daily wellness questionnaire for additional context.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can configure and send a pre-race (Race A) assessment to a group in under 2 minutes.
- **SC-002**: Every assessed athlete receives an actionable interpretation anchored to their own baseline (or explicitly marked as baseline-establishing when none exists).
- **SC-003**: The group dashboard lets the coach correctly identify each athlete's dominant pattern (somatic / cognitive / confidence) at a glance for warm-up and huddle planning.
- **SC-004**: 100% of imported historical results are correctly scored and charted, with baselines established where data permits.
- **SC-005**: 0 generated outputs contain diagnostic labels; every output is framed in a mastery climate (verifiable by review/automated checks).
- **SC-006**: When the LLM is disabled, 100% of interpretation requests still return a valid, same-schema reading via the rule-based fallback.
- **SC-007**: For 100% of under-13 athletes, the default instrument is SAS-2, and any CSAI-2/2R override is preceded by a warning and recorded.
- **SC-008**: An athlete can complete a questionnaire on a mid-tier Android phone with the standard accessibility floor (WCAG 2.1 AA) and no horizontal scrolling.

## Assumptions

- The existing athletes model and competition calendar (`race_events` with A/B/C priority) are reused as the source of athletes and events.
- Athlete login is constrained (`can_login=false` in the base model); how athletes access their assigned questionnaire (e.g., coach-mediated link/token vs. limited athlete login) is an open item — see Clarifications.
- The exact historical import file format (CSV columns / JSON shape, item ordering, instrument detection) is deferred to `/speckit-clarify`.
- The licensed official scoring keys (Human Kinetics for CSAI-2/2R; validated Spanish CSAI-2R) are available to the team to load as data; the module ships the loader, not invented item text.
- The LLM interpretation uses the project's existing AI provider configuration (`AI_*` env vars); `AI_LOG_PROMPTS` remains `false` in production. Concrete provider/model wiring is a `/plan` concern, not part of this spec.
- "April baseline" maps to the season's early diagnostic window (around the La Cumbre III válida timeframe); baseline is per athlete and per subscale.
- Perceived direction (facilitative vs. debilitative, CSAI-2D style) is explicitly a future enhancement and out of scope for v1.

## Out of Scope (Non-Goals)

- Not a clinical diagnostic or mental-health screening tool.
- No automatic messaging to athletes or parents.
- Does not apply CSAI-2/2R to under-13 athletes as a normal flow (SAS-2 only for that group; CSAI-2/2R override is an exception with a warning).
- Does not use adult load metrics (TSS/IF/NP) and does not link results to rankings.
- Perceived-direction capture (CSAI-2D) is deferred to a future version.

## Clarifications

> Resolved in `/speckit-clarify`. Tracked here as open questions that affect scope/UX/privacy.

- **CL-001 (scope/format)**: What is the exact historical import file format (columns/shape, per-item vs. per-subscale data, instrument detection)? Affects FR-021.
- **CL-002 (UX/privacy)**: How does an athlete access their assigned questionnaire given `can_login=false` — a coach-issued one-time link/token, or limited athlete login? Affects FR-007, FR-023.
- **CL-003 (privacy)**: What is the guardian-consent capture and verification mechanism (where it is recorded, who registers it, expiry)? Affects FR-023, FR-027.
