# Feature Specification: Traceable AI growth analysis — structured, longitudinally grounded, self-reviewed measurement insights with per-generation traceability

**Feature Branch**: `feat/042-traceable-growth-ai`

**Created**: 2026-09-11

**Status**: Draft

**Input**: User description: "Traceable AI growth analysis: move the club's AI-assisted interpretation of anthropometric measurements (and, as a transport migration, every other AI text generation in the app) onto a traceable pipeline so the coach and the developer can see, per generation, which model ran, how long it took, what it cost, which prompt version produced it, and whether the safety review passed — while upgrading the anthropometric analysis itself from a single free-prose paragraph into a structured, longitudinally grounded, self-reviewed insight."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The coach reads an honest, structured reading of one measurement (Priority: P1)

The coach opens a measurement of one athlete and asks for the AI analysis. Instead of one long paragraph that repeats the rule-based training implications, the coach sees a one-line summary, then four short labelled sections — what changed, what it means, the next 2–4 weeks, and warning signs — plus a confidence level with its reason and an explicit list of data gaps. The reading uses the athlete's whole measurement history, the growth summary already shown in the Crecimiento tab (stage, qualitative bands, expected velocity range for the stage), the last 28 days of training load, and the athlete's own previous structured analysis, so it can talk about trend and continuity rather than only "since last time". When two measurements are less than 26 weeks apart, the analysis calls the growth velocity an early signal instead of classifying it; it names a change of maturation phase only when a second reading corroborates it; and near a phase boundary or outside ages 11–15 it always says that the maturity estimate carries a margin of several months. Before anything is shown or stored, a deterministic check and a cheap second-opinion review look for population comparisons, diagnoses, invented numbers, a leaked name, an exact PHV date, coach-only numbers in a family text, or over-confident velocity claims; at most one bounded revision is attempted, and otherwise a plain deterministic fallback text is stored with low confidence.

**Why this priority**: This is the product value of the feature. The current analysis over-claims (velocity after 8 weeks presented as reliable, phase crossings announced from a single reading) and duplicates the rule box. False clinical certainty about a minor is the failure mode the constitution tolerates least.

**Independent Test**: With AI enabled and a fake model, request the analysis for an athlete with (a) one measurement, (b) two measurements 10 weeks apart, (c) two measurements 30 weeks apart, (d) a borderline phase change without corroboration; assert the stored insight has the six parts, the velocity wording matches the interval rule, the phase change is named only in the corroborated case, and a draft containing a population comparison is never persisted as approved.

**Acceptance Scenarios**:

1. **Given** an athlete with three measurements and AI consent, **When** the coach requests the analysis of the latest one, **Then** the stored and displayed result contains a summary line of at most 140 characters, the four sections, a confidence level with a reason, and a data-gaps list, all in español neutro without Markdown, and the coach version stays within 110 words while the family version stays within 180.
2. **Given** the previous measurement is 10 weeks old, **When** the analysis is generated, **Then** the velocity is described as an early signal that does not yet confirm a trend, and it is never labelled typical, high or low for the stage.
3. **Given** the previous measurement is 30 weeks old and the height delta exceeds the instrument noise, **When** the analysis is generated, **Then** the velocity is classified against the stage's expected range, and a value above the upper bound in Circa-PHV is described as above typical, never as alarming.
4. **Given** the latest reading crosses a phase boundary but the reading before it does not corroborate the prior phase over the stage's re-test interval, **When** the analysis is generated, **Then** the phase change is not stated as confirmed; at most the text says the next measurement will confirm it.
5. **Given** the athlete is 15.4 years old or the maturity offset is within one year of a phase boundary, **When** the analysis is generated, **Then** the text includes an explicit margin-of-several-months statement and never gives a decimal age or a month as the PHV prediction.
6. **Given** the model draft contains a comparison with other children, a clinical label, a number absent from the inputs, or a proper name, **When** the review runs, **Then** the draft is not delivered as approved; the coach sees either a revised approved text or the fallback text marked "con observaciones", and the family never receives it.
7. **Given** the review step is unavailable (timeout or malformed answer) and the deterministic check found no blocking issue, **When** the analysis completes, **Then** the coach sees the draft with confidence lowered to low and a "sin revisión" mark, the unavailability is recorded, and families keep seeing the "not yet available" message until a reviewed generation exists; **Given** the deterministic check found a blocking issue, **Then** the fallback text is stored regardless.
8. **Given** no training session exists in the last 28 days, **When** the analysis is generated, **Then** the text declares that gap and states nothing about attendance, effort or hours.
9. **Given** a previous structured analysis exists for the athlete, **When** a new one is generated, **Then** its summary line differs from the previous one; persistence is expressed as continuity, not repetition.
10. **Given** an analysis stored before this feature (free prose), **When** the coach or a parent opens that measurement, **Then** it renders exactly as before, with no error and no re-generation.

---

### User Story 2 - Every AI generation is traceable and accounted for (Priority: P1)

The developer running the app locally with the tracing tool enabled sees one trace per AI generation — for the growth analysis, the session assistant, the monthly report and its blocks, and the family newsletter — showing which model and provider ran, how long each step took, how many tokens went in and out, what it cost, which prompt version was used, and whether the deterministic check and the review approved, revised or rejected the draft. Prompt and response content are never visible in the trace. In production the tracing tool is off and cannot be turned on; the generation record itself still keeps model, provider, prompt version, tokens, latency, cost, review verdict and a trace reference, and the per-coach spend view introduced by the multi-coach governance feature shows this stack's spend alongside the race spend. The other generations keep their prompts, outputs and tests unchanged; a feature switch lets the developer route them through the new transport or the previous one during the transition.

**Why this priority**: "This reading looks off" is currently unanswerable. Traceability is the reason the owner asked for the migration, and it is what makes the golden evaluation, cost visibility and future prompt changes safe.

**Independent Test**: Run each AI use case once with a fake model and the tracing tool disabled, then enabled against the local instance; assert one trace per generation with redacted content and the expected tags, and assert the generation record carries the accounting fields. Flip the transport switch off and re-run the existing tests for the migrated use cases unchanged.

**Acceptance Scenarios**:

1. **Given** tracing is enabled locally, **When** any of the six AI generations runs, **Then** exactly one trace is produced with the generation name, a keyed-hash session identifier, and tags for audience (where applicable), prompt version, provider and model, and every input, output and metadata payload reads as redacted.
2. **Given** tracing is enabled locally and the structural-metadata switch is also on, **When** the growth analysis runs, **Then** the trace additionally carries only operational fields from the audited allow-list (rule names and counts, verdict code, cache hit or miss, fallback flag, retry counts, content-free size buckets, hashed identifiers) and never sex, age, category, maturation phase, deltas, dates, coach free text or any text fragment.
3. **Given** the application starts with the production profile and either tracing switch set on, **When** it boots, **Then** startup fails with a clear configuration error.
4. **Given** tracing is disabled or misconfigured, **When** any AI generation runs, **Then** it completes normally with no trace and no error surfaced to the user.
5. **Given** any AI generation completes, **When** its record is stored, **Then** the record includes model, provider, prompt version, tokens in and out, latency, cost and the trace reference (empty in production), and the per-coach spend view shows the cost attributed to the requesting coach and to this stack.
6. **Given** the transport switch is off, **When** the session assistant, monthly report, report blocks or newsletter generate text, **Then** their outputs and their existing tests are unchanged; **Given** the switch is on, **Then** the outputs are the same and each run is traced.
7. **Given** a generation for this stack, **When** cost is recorded, **Then** the race-results spending limit is unaffected and no growth generation is ever refused because of it.
8. **Given** the race chat trace, **When** its session identifier is produced, **Then** it uses the same keyed hash as the new traces instead of the previous truncated plain hash.

---

### User Story 3 - Families read a safe, plain version and never a flagged one (Priority: P2)

A parent opening their child's measurement or the Crecimiento tab sees the analysis in family language: no growth velocity in cm/year, no months to PHV, no phase-alert codes, only the significant height and weight changes in centimetres and kilograms, and a neutral provenance line "Generado por el asistente de IA del club" with the date. If the coach's latest analysis was flagged by the review, the parent sees the same "not yet available" message both cards already share; nothing flagged is ever delivered with a caveat.

**Why this priority**: Families are the most sensitive audience; today they see a raw model slug and a text that can over-claim. This story keeps the family surface at the bar the constitution sets for minors.

**Independent Test**: Log in as a parent of an athlete whose latest analysis is (a) approved, (b) flagged, (c) absent; assert the family text has no cm/year figure or alert code, shows the neutral provenance line, and cases (b) and (c) show the identical placeholder.

**Acceptance Scenarios**:

1. **Given** an approved family analysis, **When** the parent opens the measurement, **Then** the summary and the warning-sign section are visible, the rest is behind "Ver análisis completo", the provenance line has no provider or model name, and no number other than significant deltas appears.
2. **Given** the latest analysis was flagged by the review, fell back, or was not reviewed, **When** the parent opens the measurement or the Crecimiento tab, **Then** they see "Aún no hay análisis disponible para esta medición. El entrenador lo generará pronto." and nothing else from the AI.
3. **Given** the PHV explanation card and the measurement card in parent mode with no cached content, **When** rendered, **Then** both show the same passive message instead of one of them rendering nothing.

---

### User Story 4 - The Crecimiento tab tells the coach whether the latest analysis is still current (Priority: P2)

In the Crecimiento tab, right above the measurement history, the coach sees one line with the latest analysis summary, its measurement date and a "Ver análisis completo" link that opens that measurement's dialog. If a newer measurement was recorded since, or the analysed measurement was corrected afterwards, the line is marked "Desactualizado" and the old text stays readable in a muted style; the server decides staleness, the tab never guesses. Each history row whose analysis carries a warning sign shows a small "Con señal para revisar" marker so the coach can scan four measurements without opening each dialog. In family mode the same line appears without the generate action, without the word "Desactualizado" and without a link when there is nothing to open.

**Why this priority**: The coach's field question is "did the last measurement change anything?" Today the analysis is invisible until each dialog is opened and never says it is outdated after a correction.

**Independent Test**: For an athlete with two analysed measurements, correct the latest one and then add a third measurement; assert the summary line shows the stale state in both situations, the link opens the right dialog, and the row marker appears only where a warning sign exists.

**Acceptance Scenarios**:

1. **Given** the latest measurement has an approved analysis, **When** the coach opens the Crecimiento tab, **Then** one summary line with the measurement date and a link to the detail appears above the history and opens the correct measurement dialog.
2. **Given** the analysed measurement was edited after the analysis was generated, or a newer measurement exists without analysis, **When** the tab loads, **Then** the line is marked "Desactualizado", the previous summary stays visible in a muted style, and the growth summary request carries that state computed by the server.
3. **Given** no analysis exists yet, **When** the coach opens the tab, **Then** the line invites the coach to open the latest measurement to generate one, without adding a second generate button to the tab.
4. **Given** a history row whose analysis has at least one warning sign, **When** the history renders on desktop and on mobile, **Then** that row shows the "Con señal para revisar" marker and rows without warning signs show none.

---

### User Story 5 - Quality is guarded before any prompt or model change (Priority: P3)

The developer changes the analysis prompt or switches the model. A blocking golden evaluation on twelve synthetic cases (first measurement, sub-8-week interval, reliable velocity, early-signal velocity, age edge, corroborated and uncorroborated phase change, sub-noise delta, above-typical velocity, missing training window, near-duplicate previous analysis, injection through upstream free text) scores grounding, uncertainty calibration, privacy and developmental safety, tone and format, and actionability, and fails below a composite of 0.75, the same bar the race analyst uses. The theoretical framework gains a subsection on the uncertainty of maturity-offset estimates with references, so the anchors the prompts embed are documented and reviewable.

**Why this priority**: Without a gate the improvements of story 1 erode with the next prompt tweak; the race stack proved the pattern. Documentation keeps the sports-science anchors auditable.

**Independent Test**: Run the golden evaluation against a fake model that returns a known-good and a known-bad answer set; assert the composite crosses and fails the threshold respectively and that the dataset contains no real athlete data.

**Acceptance Scenarios**:

1. **Given** the twelve synthetic cases and a baseline, **When** the golden evaluation runs with the configured analysis model, **Then** it reports a composite score per case and overall and fails the run when the overall is below 0.75.
2. **Given** a case where the two measurements are 10 weeks apart, **When** the generated text classifies velocity as typical, high or low, **Then** that case fails the uncertainty-calibration dimension.
3. **Given** the framework document, **When** reviewed, **Then** it contains a subsection on interpreting maturity-offset estimates (error growing away from the 12–15 age window, pull of early and late maturers toward the mean, the 26-week velocity rule, what the AI may and may not claim) and a references list with author, year and source.

---

### User Story 6 - The AI surfaces meet the touch, focus and colour rules (Priority: P3)

On a tablet in the field the coach can hit "Regenerar análisis", "Copiar" and the dialog's close control without precision; the measurement dialog keeps keyboard focus inside and returns it on close; the budget and concurrency hint appears before launching a generation instead of after a failed round-trip; the AI disclaimer uses the neutral informational colour so amber keeps meaning "attention"; and the coach can open a technical-details disclosure showing model, prompt version and trace reference. The local-only command-line provider can no longer be configured in production, and the project guidance file names the real migration head.

**Why this priority**: Three of the findings are direct constitution violations on the exact surfaces this feature touches; fixing them in the same change avoids a second pass over the same components.

**Independent Test**: Render the measurement dialog and both AI cards in coach and parent mode; assert the three controls are at least 48 px tall, tab focus stays inside the dialog and returns to the trigger, the hint renders when the AI status says the budget is exhausted, the disclaimer has no amber token, and accessibility checks report zero violations.

**Acceptance Scenarios**:

1. **Given** the measurement dialog is open, **When** the coach presses Tab repeatedly, **Then** focus cycles within the dialog, Escape closes it, an explicit close control of at least 48×48 px exists, and focus returns to the row that opened it.
2. **Given** the AI status reports the budget exhausted or a run in progress, **When** the coach views a card with a generate or regenerate control, **Then** the hint is shown before the tap and the control is disabled, consistent with the other AI launch points.
3. **Given** the application starts with the production profile and the command-line provider selected for either stack, **When** it boots, **Then** startup fails with a clear configuration error.

---

### Edge Cases

- First measurement ever: no deltas, no velocity, no previous analysis; the analysis declares the baseline and the data gaps, and never fabricates a comparison.
- Two measurements less than 8 weeks apart: no velocity figure is computed at all; the text says the interval is too short for a velocity estimate.
- History longer than sixteen measurements: the oldest points are compacted into yearly checkpoints rather than dropped, so the history is complete but bounded.
- The athlete has no consent for AI: the request is refused as today and nothing is traced or stored.
- The model returns text that is not valid structured output twice in a row: the fallback text is stored with low confidence and the reason is recorded; the user sees the fallback, not an error page.
- The analysed measurement is corrected after generation: the cached analysis stays readable but is marked stale in the tab and in the dialog; regenerating replaces it.
- A parent whose child has only flagged analyses: every family surface shows the shared "not yet available" message; nothing indicates that a flagged text exists.
- Tracing configured but the local tracing instance is down: generations succeed; a single warning is logged once per process; no retry storm.
- Tracing enabled and the structural-metadata switch off: traces carry only tags, usage and timing; no metadata at all.
- The transport switch is off while tracing is on: the migrated use cases produce no trace and behave exactly as before this feature.
- A club with fewer than five athletes in a sex and age group: no trace field allows re-identification because no biological or demographic field is ever sent, regardless of club size.
- The developer runs the golden evaluation without a real model key: the run is skipped with an explicit reason, never silently passed.

## Requirements *(mandatory)*

### Functional Requirements

**Structured, grounded analysis**

- **FR-001**: The per-measurement analysis MUST produce a structured insight with: a summary line of at most 140 characters, "qué cambió", "qué significa", "próximas 2–4 semanas", "señales de aviso" (may be empty), a confidence level (high, medium, low) with a reason of at most 200 characters, and a data-gaps list (may be empty); section cardinalities are 1–4, 1–4, 1–3, 0–2 and 0–3 items respectively, each item plain prose without Markdown.
- **FR-002**: The analysis MUST exist in two audiences: family and coach. The family version MUST contain no number other than significant height and weight deltas and MUST use "su hijo" / "su hija"; the coach version MAY state velocity in cm/year and months to or from PHV and MUST address the coach as "tu deportista". Word budgets: family ≤ 180, coach ≤ 110, enforced by the system's own count.
- **FR-003**: The analysis MUST be grounded on: the significant deltas against the previous measurement, the athlete's full measurement history compacted as offsets in weeks (no absolute dates, no sitting height or arm span per point), the growth summary already computed for the Crecimiento tab (stage, maturity offset, qualitative height and weight bands, expected velocity range for the stage, alert codes, next-measurement status), 28-day training-load aggregates (session count, mean effort, hours), and the athlete's own previous structured analysis (summary line, confidence, weeks since). Z-scores, percentiles and raw band values MUST NOT be included.
- **FR-004**: Growth velocity MUST continue to be computed from 8 weeks between measurements; the analysis MUST label it "reliable" only when the two measurements are at least 26 weeks apart and "early signal" otherwise, and MUST classify velocity as typical, high or low for the stage only when reliable and the delta exceeds the instrument noise.
- **FR-005**: A change of maturation phase MUST be named as confirmed only when corroborated: the reading before the previous one shows the same prior phase and the pair spans at least the stage's re-test interval. Uncorroborated crossings MAY only be described as pending confirmation by the next measurement.
- **FR-006**: When the maturity offset is within one year of a phase boundary or the athlete is younger than 11 or older than 15, the analysis MUST include an explicit statement that the estimate carries a margin of several months, and MUST never state a decimal age or a calendar month as the PHV prediction.
- **FR-007**: Velocity above the upper bound of the stage's expected range MUST be described as above typical, never with alarming language; velocity anchors shown to the model MUST come only from the growth summary's expected range, not from the prompt text.
- **FR-008**: Warning signs MUST be routed to "el entrenador lo revisará y, si lo cree necesario, sugerirá consulta pediátrica" and MUST never name a condition; the family version MUST never render alert codes verbatim.
- **FR-009**: Missing inputs (no previous measurement, no training window, insufficient history) MUST be declared in the data-gaps list and MUST never be compensated with invented content.
- **FR-010**: A new analysis MUST NOT repeat the previous analysis' summary line verbatim; continuity MUST be expressed as such.

**Review before delivery**

- **FR-011**: Before persistence, a deterministic check MUST evaluate the draft against a catalogue of rules covering at least: population or peer comparison, diagnostic or clinical labels, numbers absent from the inputs, exact PHV date or age, velocity presented as reliable when it is not, leaked names or identifiers, word budget (10 % tolerance), sycophancy over a non-significant delta, supplement mentions, Markdown inside fields, uncorroborated phase crossing, and coach-only numbers in a family text. Privacy and developmental-safety rules MUST block delivery outright; the others lower confidence.
- **FR-012**: A cheap second-opinion review MUST then judge only what the deterministic check cannot: contradiction with the growth summary, honesty of the confidence reason, and tone; it MUST return approve, revise or reject with rule-coded violations.
- **FR-013**: At most one revision MUST be attempted: mechanical fixes may be adopted directly from the review; interpretive violations MUST be sent back to the analysis step once with the violations attached. After that single attempt, any unapproved or blocked result MUST become the deterministic fallback text with low confidence and a fallback flag.
- **FR-014**: If the review step fails or times out and no blocking issue was found, the draft MUST be stored and shown to the coach with confidence lowered to low and the unavailability recorded (verdict "skipped"); if a blocking issue was found, the fallback MUST be stored regardless of the review.
- **FR-015**: The existing rendered-text guardrails MUST remain the last defence on any text that reaches the frontend, PDF or email, for both the new structured insight and the migrated generations.
- **FR-016**: Only an analysis approved or revised by the review MAY be delivered to a family audience. A flagged (still unapproved after the revision, or rejected), fallback or unreviewed ("skipped") analysis MUST never reach a family; the coach MUST see it marked ("Con observaciones" for flagged, the fallback copy for fallback, "Sin revisión" for skipped) and MUST be able to regenerate.

**Traceability and accounting**

- **FR-017**: Every AI generation in the application (per-measurement analysis, PHV explanation, session assistant clarify and draft, monthly report, monthly report blocks, family newsletter) MUST be executed through one traceable transport so that, when local tracing is enabled, exactly one trace per generation is produced with steps for context preparation, each model call, review and persistence.
- **FR-018**: Trace content MUST always be redacted: no prompt, response, coach note, athlete name or measurement value ever leaves the process into the tracing tool, in any configuration.
- **FR-019**: Traces MUST carry a keyed-hash session identifier (a server-side key derived for this purpose, never the raw identifier, never enumerable from the trace store alone) and tags limited to generation name, audience where applicable, prompt version, provider and model; numeric scores MUST never carry text.
- **FR-020**: A separate switch, off by default and forbidden in production, MAY add structural metadata restricted to an audited allow-list: model, provider, prompt version, tokens, latency, cost, rule names and counts, review verdict code, cache hit or miss, fallback flag, retry and validation counts, content-free size buckets, and hashed identifiers. Sex, age, category, maturation phase, offsets, velocity, deltas, nutritional status, dates, coach free text, session titles and any text fragment MUST be excluded, and never more than one demographic dimension may be added in the future without re-running the privacy audit.
- **FR-021**: Both tracing switches MUST cause a startup failure in the production profile; when tracing is disabled, misconfigured or the local instance is unreachable, generations MUST complete normally with at most one warning per process.
- **FR-022**: Each stored generation MUST record model, provider, prompt version, tokens in and out, latency, cost and the trace reference (empty in production), and the per-coach spend view MUST show this stack's spend attributed to the requesting coach, separately from the race spend.
- **FR-023**: This stack MUST have no spending cap and MUST never count against, or be refused by, the race-results spending limit.
- **FR-024**: The race chat trace's session identifier MUST use the same keyed hash as the new traces.
- **FR-025**: The migrated generations (session assistant, monthly report, report blocks, newsletter) MUST keep their prompts, outputs and existing tests unchanged, and a feature switch MUST allow routing them through the previous transport during the transition.

**User interface**

- **FR-026**: The measurement dialog MUST render the structured insight collapsed by default (summary line and warning signs visible; "qué significa" and "próximas 2–4 semanas" behind a "Ver análisis completo" expander with proper expanded state announced to assistive technology), and MUST render analyses stored before this feature exactly as before.
- **FR-027**: The Crecimiento tab MUST show, above the measurement history in both coach and family mode, one line with the latest analysis summary, the measurement date and a link that opens that measurement's dialog; the server MUST compute whether it is stale (newer measurement recorded or analysed measurement corrected after generation) and the tab MUST show "Desactualizado" in coach mode while keeping the previous summary readable in a muted style. Family mode MUST omit the generate action, the "Desactualizado" wording and the link when there is nothing to open.
- **FR-028**: Measurement history rows (desktop and mobile) MUST show a "Con señal para revisar" marker when the row's analysis contains at least one warning sign.
- **FR-029**: The family provenance line MUST read "Generado por el asistente de IA del club" with the generation date and MUST NOT show provider or model; the coach MUST have a technical-details disclosure showing model, prompt version and trace reference.
- **FR-030**: The AI disclaimer MUST use the neutral informational colour token; amber MUST be reserved for the conditional training-implications box; delta chips MUST use the shared status tokens.
- **FR-031**: "Regenerar análisis", "Copiar" and the measurement dialog's close control MUST be at least 48 px tall; the dialog MUST trap focus, close on Escape, and return focus to its trigger; the copy of the regenerate control MUST be "Regenerar análisis".
- **FR-032**: The budget and concurrency hint used by the other AI launch points MUST appear above every generate or regenerate control on both AI cards and MUST disable the control while the budget is exhausted or a run is in progress.
- **FR-033**: The two parent read-only AI cards MUST show the same passive "not yet available" message when no approved analysis exists.
- **FR-034**: All new product copy MUST be in español neutro (Colombia) with full diacritics; every new or changed page- or dialog-level component MUST pass the accessibility check with zero violations.

**Quality gates and documentation**

- **FR-035**: A blocking golden evaluation on twelve synthetic cases (as listed in User Story 5) MUST score grounding (0.30), uncertainty calibration (0.20), privacy and developmental safety (0.20), tone and format (0.15) and actionability (0.15), fail below a composite of 0.75, and run in the opt-in evaluation lane and in continuous integration; the dataset MUST contain no real athlete data.
- **FR-036**: The theoretical framework document MUST gain a subsection on interpreting maturity-offset estimates (uncertainty and safeguards) and a references list; the prompts' Circa-PHV velocity anchors MUST be replaced by the growth summary's expected range so the framework, the growth module and the analysis agree on one source.
- **FR-037**: The local-only command-line provider MUST cause a startup failure in the production profile for both AI stacks; the project guidance file MUST record the current migration head.
- **FR-038**: The default offline test lane MUST stay green without network or model keys; the fake model used by existing privacy tests MUST keep exposing the last prompt it received so those assertions remain valid.

### Key Entities *(include if feature involves data)*

- **Structured growth insight**: the versioned result of one analysis for one measurement and one audience — summary line, four sections, confidence, data gaps, review verdict, fallback flag, prompt version, model, provider, tokens, latency, cost, trace reference, generation time and requesting coach. Coexists with the previous free-prose result under a version discriminator.
- **Analysis context**: the deterministic input assembled for one generation — identity fields (age group, decimal age, sex, category, audience), measurement deltas with significance flags, velocity with its confidence label, phase-crossing flag with corroboration, compacted longitudinal series, growth summary codes, 28-day training-load aggregates, previous-insight summary. Every key is on an explicit allow-list.
- **Review verdict**: approve, revise or reject with rule-coded violations and an optional mechanically revised insight.
- **Rule catalogue**: the twelve deterministic rules with their category (privacy, developmental safety, grounding, style) and blocking behaviour.
- **Trace metadata allow-list**: the closed list of operational fields that may accompany a trace when the structural-metadata switch is on, with the transformation applied to each.
- **Latest-analysis summary**: the server-computed line for the Crecimiento tab — measurement, generation time, version, summary line, verdict, warning-sign presence and staleness.
- **Golden case**: a synthetic scenario with its context, expected themes, forbidden terms, word limit and confidence bounds, plus the baseline scores.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100 % of generations run locally with tracing enabled, the developer can open one trace and read model, provider, prompt version, tokens, latency, cost and verdict, and finds no prompt, response or athlete value in it.
- **SC-002**: 100 % of structured insights stored contain the six parts within their cardinalities and word budgets; 0 approved insights contain a population comparison, clinical label, invented number, proper name or exact PHV date across the golden set and the offline test suite.
- **SC-003**: In the golden set, 100 % of cases with fewer than 26 weeks between measurements describe velocity as an early signal, and 100 % of uncorroborated phase crossings are not stated as confirmed; the composite score is at least 0.75 on the shipped prompt and model.
- **SC-004**: A family never sees a flagged analysis: across the parent test matrix, 0 responses to a parent contain a flagged, rejected or fallback text, and 100 % of "no analysis" states show the same message on both cards.
- **SC-005**: The coach can tell from the Crecimiento tab, without opening any dialog, whether the latest analysis is current and which of the last four measurements carry a warning sign.
- **SC-006**: The migrated generations produce byte-identical outputs to the previous transport for the same fake-model inputs, and their existing tests pass unchanged with the switch in either position.
- **SC-007**: The default offline test lane, the type check and the accessibility checks pass; the three AI-surface controls measure at least 48 px and the measurement dialog passes the focus-trap test.
- **SC-008**: A local generation of the coach analysis completes within 45 s at the 95th percentile with the configured models; the tab's summary line adds no additional request beyond the growth summary already fetched.
- **SC-009**: Starting the application with the production profile and any of the three forbidden settings (tracing, structural metadata, command-line provider) fails 100 % of the time with a message naming the offending variable.

## Assumptions

- **Scope decisions (owner, 2026-09-11)**: the whole AI text-generation stack is migrated to one traceable transport, but only the anthropometric analysis (per measurement and PHV explanation, both audiences) is rebuilt; the other generations move as-is behind a switch. The rebuilt analysis includes structured output, full longitudinal context, a deterministic pre-check plus a cheap review, and a blocking golden evaluation. Velocity keeps the 8-week computation floor with confidence language gated at 26 weeks. A review-flagged analysis is blocked for families. Cost is recorded with no cap and never counts against the race limit. Tracing may carry structural metadata only under the audited allow-list. The per-measurement analysis stays in the dialog and gains a summary line in the Crecimiento tab. Three config-hygiene items are bundled (production failure for the command-line provider, keyed hash for session identifiers including the race chat trace, corrected migration head in the guidance file).
- **Research (2026-09-11) that motivates the anchors**: the maturity-offset method in use has documented error that grows outside the 12–15 age window and pulls early and late maturers toward the mean, so uncertainty wording is mandatory near boundaries; alternative estimators were evaluated and rejected; the instrument-noise thresholds already in use are consistent with published field measurement error and stay unchanged; clinical growth monitoring places the reliable floor for a velocity estimate at six months, hence the 26-week gate; the previous prompts' Circa-PHV anchors sat inside rather than across the typical pubertal-peak envelope, hence the single source in the growth summary.
- **Privacy audit (2026-09-11)**: in a club of about twenty minors, sex and age group alone form equivalence classes of about five, and adding maturation phase drops them below two, so no demographic or biological field may accompany a trace even bucketed or rounded; only exclusion is safe. Identifiers are hashed with a server-side key derived for this purpose (owner choice: stable across restarts so local traces still group by athlete; the privacy audit's stricter per-process key was considered and rejected because it loses that grouping), domain-separated from the race anonymiser. Coach free text never reaches the tracing tool in any form, including its length.
- **Reuse**: the tracing tool, the model-client factory, the pricing table, the review pattern, the golden-evaluation harness and the training-load aggregation already exist for the race pipeline and are shared, not duplicated; no new runtime dependency is added. Structured output is requested as JSON in the prompt and validated by the system, because two supported providers have no reliable tool-calling; the prompt registry remains the source of truth for prompt versions (the tracing tool's prompt management and hosted datasets are not adopted).
- **Persistence**: structured insights extend the existing per-measurement AI cache with a version discriminator and the accounting fields; free-prose rows stay valid; the race run tables are not reused because they feed the race spending limit. The migration chain keeps a single head.
- **Existing patterns**: the growth summary from feature 040 is the single source of stage, bands and expected velocity ranges; the per-coach spend view and the attribution columns from feature 041 are the target for cost visibility and staleness detection; the shared budget hint and the shared dialog primitive are reused rather than re-implemented.
- **Timing**: local generation of the coach analysis is expected around 20–40 s with the configured models; the frontend already handles cold-start and long waits, so no background job or resumable run is introduced.
- **Language**: all product copy is español neutro (Colombia) with full diacritics; this specification and the planning artifacts are in English per the constitution's language policy.
- **Out of scope**: changing the maturity-offset formula or adopting alternative estimators; a separate spending cap; showing flagged analyses to families with a caveat; the tracing tool's prompt management or hosted datasets; any change to how the race pipeline analyses results; retiring the legacy provider layer (listed as a later step gated on a newsletter evaluation); a representative Android test device for the parent persona (tracked separately).
