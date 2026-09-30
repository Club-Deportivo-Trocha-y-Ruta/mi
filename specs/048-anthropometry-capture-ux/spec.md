# Feature Specification: Guided anthropometric capture (weight, standing height, sitting height, arm span)

**Feature Branch**: `main` (owner decision 2026-09-29: no dedicated branch, same pattern as 045/046/047; the `speckit.git.feature` hook is skipped)

**Created**: 2026-09-29

**Status**: Draft

**Input**: User description: "Feature 048 — Rediseño UX de la toma antropométrica básica (peso, talla de pie, talla sentado, envergadura). NO crear rama nueva: trabajar sobre la rama actual (main), igual que 045/046/047. Alcance: (1) modo guiado paso a paso por medida con ilustración (webp generadas con ChatGPT/Gemini, estilo de las de pliegues en frontend/src/assets/skinfolds, guardadas en frontend/src/assets/anthropometry/) + textos «Dónde/Cómo», manteniendo un modo rápido; (2) doble lectura por medida con tercera lectura si difieren (>0,5 cm tallas, >0,1 kg peso) y mediana; (3) altura del banco para talla sentado, recordada y restada automáticamente; (4) alertas suaves de plausibilidad contra la medición anterior (talla baja >1 cm, crecimiento inverosímil, peso ±10 %, ratio sentado/de pie fuera de rango) sin bloquear el guardado; (5) editar y eliminar un registro antropométrico con auditoría (hoy solo existe POST en backend/app/routers/anthropometry.py); (6) jornada de medición de grupo: elegir deportistas, cola de captura con progreso y resumen final; (7) chequeo previo de condiciones (sin zapatos, ropa liviana, misma franja horaria, sin entrenar antes) + borrador autoguardado y reintento sin conexión; (8) PHV movido a la revisión final con lenguaje claro, e instructivo PDF de campo ampliado con las medidas básicas. Contexto: coach en tablet en campo, medidor no certificado ISAK, deportistas menores 10–15 años (Ley 1581: sin fotos reales, ilustraciones no identificables). Reutilizar SkinfoldWizard/Stepper y useFormDraft de la feature 046; la salida «Guardar y agregar pliegues» debe seguir funcionando."

## Context

The anthropometric evaluation (weight, standing height, sitting height, optional arm span) feeds almost everything downstream: the maturity offset and PHV phase, WHO height/BMI percentiles, height velocity, the growth-module alerts, the anthropometry AI explanation, the monthly newsletter and, since feature 046, the skinfold set that hangs off the same record. Yet its capture surface is the oldest in the product: one dense four-field grid on the athlete's "Antropometría" tab, a single reading per measure, no teaching, no plausibility check, and **no way to correct or remove a saved record**. A typo (e.g. 14.5 instead of 145, or sitting height taken from the floor without subtracting the bench) is stored forever and silently distorts the PHV phase, the velocity curve, family-facing copy and AI output.

The measurer is the coach, not an ISAK-certified anthropometrist, working on a tablet at the training venue, usually measuring the whole group on the same day. Sitting height is the measure most prone to error — it is taken on a bench against the stadiometer and the bench height must be subtracted — and it drives the maturity-offset equation directly: a 2 cm error in sitting height moves the offset by a clinically meaningful amount and can flip an athlete between pre/circa/post PHV.

Feature 046 already solved the same problem for skinfolds: pre-check, one step per site with a non-identifiable line-art illustration and "Dónde / Cómo" text. This feature brings that teaching pattern to the basic measures (one reading per measure, by owner decision), relies on plausibility warnings to catch errors, adds correction/removal, and supports the real-world "measure the whole group today" session. Capture is online-only: every athlete is saved to the server as soon as the coach confirms it.

## Clarifications

### Session 2026-09-29

- Q: Where does an in-progress group measurement session live, and must it survive the device dying or being switched? → A: Nowhere persistent. Capture requires a connection; each athlete's record is saved to the server the moment it is confirmed, one child at a time. The session queue itself is not persisted or recoverable — if the tablet dies or the page is closed, the coach simply starts a new session with whoever is left. No device drafts, no offline queueing.
- Q: How many readings per measure are taken and what is stored? → A: One reading per measure; only that single value is stored (net value for sitting height, bench height not stored). No double/third readings.
- Q: Who may edit or delete a saved measurement? → A: Only the coach who took it (the record's evaluator) or an admin, for both edit and delete. Other coaches with access to the athlete can view it but not change it.
- Q: How is a measurement saved despite a plausibility warning shown later in the history? → A: A "Revisar" marker in the history, computed at display time by comparing each record with the previous one; nothing is stored, and the marker disappears once the data is corrected.
- Q: Who produces the illustrations and when? → A: The implementing agent generates them during implementation, driving the Gemini or ChatGPT web UI in the owner's Chrome session (Claude in Chrome), using the existing skinfold illustrations as style reference; the owner approves each image before it enters the product.

## User Scenarios & Testing *(mandatory)*

Primary device for every surface in this feature: **coach on a tablet (landscape or portrait) at the venue**; secondary: coach on a phone. Families and athletes see no new surface.

### User Story 1 - Correct or remove a wrong measurement (Priority: P1)

The coach notices in the history table that last week's record has a standing height of 14.5 cm (or a duplicate record from a double tap). They open the record, fix the value (or delete the record), and every derived figure — maturity offset, PHV phase, percentiles, BMI, height velocity, growth alerts — reflects the corrected data.

**Why this priority**: Without it, every other improvement still leaves the club stuck with any error that slips through. It is the smallest slice with the largest data-quality payoff.

**Independent Test**: Create a record with a wrong value, edit it, and verify all derived values and the history update; delete a duplicate and verify it disappears from history, charts and the next-measurement card, and that an audit entry exists for both actions.

**Acceptance Scenarios**:

1. **Given** a saved record, **When** the coach edits the sitting height and saves, **Then** the record shows the new value and its maturity offset, PHV phase, leg length, percentiles and BMI are recomputed from the corrected inputs.
2. **Given** a saved record with a skinfold set attached, **When** the coach edits the weight, **Then** the skinfold set stays attached and body-composition estimates that depend on same-day weight use the corrected weight.
3. **Given** a saved record, **When** the coach chooses "Eliminar", **Then** a confirmation explains what will be removed (the evaluation, and its skinfold set and AI explanation if present) and the record is removed only after explicit confirmation.
4. **Given** any edit or deletion, **Then** an audit entry records who, when, which record and which fields changed — without measurement values, names or other identifying data in the audit metadata.
5. **Given** a parent or athlete account, or a coach who did not take that measurement (and is not an admin), **Then** no edit or delete action is shown for that record and the underlying operations are refused.
6. **Given** the coach edits the evaluation date, **Then** the same validations as creation apply (not in the future; skinfold age/interval rules re-evaluated for an attached set).
7. **Given** a tablet or a 360 px phone, **Then** the edit form and the delete confirmation are fully usable without horizontal scroll.

---

### User Story 2 - Guided, trustworthy single-athlete capture (Priority: P1)

The coach starts "+ Nueva medición" for one athlete. A short pre-check reminds them of the conditions (barefoot, light clothing, same time of day as usual, before training). Then one step per measure — weight, standing height, sitting height, arm span — each with an illustration, "Dónde" and "Cómo" instructions, and a single reading. For sitting height the coach enters the bench height once; the app subtracts it and shows the net value. A review screen shows the final values, any plausibility warnings against the previous evaluation, and the PHV result in plain language, before saving. A coach who already masters the protocol can switch to a quick mode (all four measures on one screen) and the app remembers that preference.

**Why this priority**: This is where errors are born. Bench subtraction and plausibility warnings prevent the errors that US1 would otherwise have to fix after the fact, and they matter most for sitting height, which drives PHV.

**Independent Test**: Complete a guided capture for one athlete end to end — including a bench subtraction and a plausibility warning — and verify the saved values equal the values (net for sitting height) shown on review.

**Acceptance Scenarios**:

1. **Given** the guided mode, **Then** each measure step asks for exactly one reading.
2. **Given** the sitting-height step, **When** the coach enters a bench height of 40 cm and a gross reading of 112.0 cm, **Then** the step shows a net sitting height of 72.0 cm, and the review and saved record use the net value.
3. **Given** a bench height entered on a previous capture on this device, **When** the coach reaches the sitting-height step, **Then** that bench height is pre-filled and editable.
4. **Given** the previous evaluation of the athlete, **When** the new standing height is more than 1 cm lower, or the weight differs by more than 10 %, or the standing-height gain implies an implausible growth rate for the elapsed time, or the sitting/standing ratio is outside the plausible human range, **Then** the review screen shows a non-blocking warning naming the measure, asks the coach to re-check it, and still allows saving.
5. **Given** the review screen, **Then** the PHV result is shown in plain Spanish (e.g. "Aún no llega al estirón", "Está en pleno estirón", "Ya pasó el estirón") with its training implication, and the technical figures (maturity offset, age at PHV) are available but secondary.
6. **Given** the arm-span step, **When** the coach skips it, **Then** the record is saved without arm span (it remains optional).
7. **Given** the quick mode, **Then** the four measures fit on one screen, plausibility warnings still appear before saving, and the bench-height subtraction is still available for sitting height.
8. **Given** an athlete aged 9 or more with the skinfold interval open, **When** the coach finishes the review, **Then** both "Guardar y terminar" and "Guardar y agregar pliegues" are offered and the latter opens the existing skinfold wizard for the new record, exactly as today.
9. **Given** a 360 px phone, **Then** each guided step shows the illustration above the inputs in a single column, every target is at least 48×48 px, and inputs open a numeric keypad.

---

### User Story 3 - Measure the whole group in one session (Priority: P2)

On measurement day the coach opens "Jornada de medición", picks the athletes present (filterable by category), and works through a queue: each athlete goes through the same guided (or quick) capture, then the next one appears. A progress indicator shows done / pending / skipped. The coach can skip an absent athlete or one who prefers not to be measured today, and come back to them later in the same session. At the end, a summary lists who was measured, who was skipped, and which records carry plausibility warnings to double-check before leaving the venue.

**Why this priority**: It mirrors how the club actually measures (everyone on the same day, every few months) and removes the per-athlete navigation overhead, but single-athlete capture (US2) already delivers the core value.

**Independent Test**: Start a session with four athletes, measure two, skip one, finish the last one, and verify the summary and the four athletes' histories; close the app mid-session and verify the already-measured athletes have their records and are marked as measured today in the picker of a new session.

**Acceptance Scenarios**:

1. **Given** the athletes list, **When** the coach starts a session and selects N athletes, **Then** a queue of N appears with a progress indicator ("3 de 12").
2. **Given** an athlete in the queue, **When** the coach chooses "Omitir por hoy", **Then** no record is created for that athlete and the summary lists them as skipped; the coach can return to them before closing the session.
3. **Given** a session in progress, **When** the coach confirms an athlete's capture, **Then** that record is saved to the server immediately, before the next athlete appears; **When** the app is closed or the tablet dies, **Then** the saved athletes stay saved and the session itself is gone (the coach starts a new one with whoever is left; the athlete picker shows who already has a record for today).
4. **Given** the session end, **Then** the summary lists measured athletes (with a link to each record), skipped athletes, and records with plausibility warnings, and offers to open any of them for correction (the coach running the session is their evaluator).
5. **Given** athletes aged 9+ due for skinfolds, **Then** the session offers adding skinfolds per athlete without leaving the queue permanently (the coach returns to the queue after the skinfold wizard).
6. **Given** a coach who is not assigned to some athletes (multi-coach governance, feature 041), **Then** the selection list only shows athletes that coach may measure.
7. **Given** a 360 px phone, **Then** the athlete picker and the queue are usable as stacked lists with no horizontal scroll.

---

### User Story 4 - Clear behaviour when the connection fails (Priority: P2)

Capture needs internet. If the connection drops when the coach confirms a capture, the screen keeps the values just entered, says clearly that nothing was saved, and offers "Reintentar". A retry never creates a duplicate record. There is no offline mode and no draft that survives closing the page.

**Why this priority**: Weak 3G/4G at the venue is normal; the coach must know for certain whether a child was saved, and a double save creates exactly the error US1 has to clean up.

**Independent Test**: Confirm a capture with the network off, verify the "no se guardó" state with values intact; turn the network on, retry, verify exactly one record exists.

**Acceptance Scenarios**:

1. **Given** no connection at confirmation, **Then** the capture shows "Sin conexión — no se guardó" with a "Reintentar" action, and the values on screen are not cleared.
2. **Given** a retry after a save that actually reached the server but whose response was lost, **Then** no duplicate record is created.
3. **Given** the coach starts a capture with no connection, **Then** the app says a connection is required before measuring begins.
4. **Given** the page is closed or reloaded before confirmation, **Then** the unsaved capture is lost (no draft is kept on the device).

---

### User Story 5 - Printable field guide for the basic measures (Priority: P3)

The coach downloads the club's field guide (the one feature 046 introduced for skinfolds) and now finds a first section for weight, standing height, sitting height (including the bench subtraction) and arm span, with the same illustrations and "Dónde / Cómo" texts used in the app, to print and bring to the venue or hand to a helper.

**Why this priority**: Useful for training helpers and as a paper fallback, but the app itself already teaches in guided mode.

**Independent Test**: Download the field guide and verify it contains the four basic-measure sections with illustrations and the same instructions as the app, before the skinfold sections, and no athlete data.

**Acceptance Scenarios**:

1. **Given** the field-guide download, **Then** the document starts with the basic measures and the pre-check conditions, followed by the existing skinfold sections.
2. **Given** the in-app instructions change, **Then** the guide's text changes with them (one source for both).

---

### Edge Cases

- **First evaluation of an athlete**: no previous record, so plausibility checks against history are skipped; only absolute ranges and the sitting/standing ratio apply.
- **Very short interval** between evaluations (e.g. same week, or a correction re-entry): the growth-rate check must not fire spuriously because of dividing by a tiny interval; below a minimum interval only the "height decreased more than 1 cm" and weight checks apply.
- **Bench height omitted or zero** (athlete seated on a measuring box whose height is already zeroed on the stadiometer): the coach can set the bench to 0; the net value then equals the gross reading.
- **Net sitting height implausible** after subtraction (e.g. bench entered twice, net < 50 cm): hard validation error, not a soft warning.
- **Editing a record that is not the latest**: velocity and alerts for later records are recomputed too, since they depend on the previous record.
- **Correcting or deleting a record changes its neighbour's marker**: because "Revisar" compares each record with the previous one, fixing or removing a record can add or clear the marker on the next record; the history reflects this immediately.
- **Deleting the only record** of an athlete: growth tab and next-measurement card return to their empty states.
- **Deleting a record whose evaluation drove a parent notification** (approaching circa-PHV): already-sent notifications are not recalled; an edit that newly crosses the threshold must not send a second notification for the same record if one was already sent.
- **Editing the evaluation date of a record with a skinfold set** so that the athlete would be under 9 or the 90-day interval would be violated: the edit is refused with the same explanation the skinfold wizard gives.
- **AI explanation already generated for the record**: after an edit, the stored explanation no longer matches the data; it must be invalidated so a new one is generated on demand (never shown stale).
- **Two coaches measuring the same athlete the same day** in separate sessions: the second save produces a visible warning that a record for that date already exists and lets the coach open it instead of creating a duplicate.
- **Session with an athlete who becomes inaccessible** (reassigned mid-session): their capture is refused with a clear message; the rest of the queue continues.
- **Device dies or page closes mid-session**: already-confirmed athletes are saved; the unconfirmed capture and the session queue are lost by design; a new session shows who already has a record for today.

## Requirements *(mandatory)*

### Functional Requirements

**Correction and removal**

- **FR-001**: The coach who took a measurement (the record's evaluator) and admins MUST be able to edit any field of an existing anthropometric record (evaluation date, weight, standing height, sitting height, arm span, notes).
- **FR-002**: On edit, the system MUST recompute every derived value of that record (leg length, leg/sitting ratio, maturity offset, age at PHV, PHV phase, training implication, BMI, WHO z-scores/percentiles, nutritional status) with the same rules as creation, and anything derived from consecutive records (height velocity, growth alerts, next-measurement date) MUST reflect the change.
- **FR-003**: The coach who took a measurement and admins MUST be able to delete a record after an explicit confirmation that lists what else is removed with it (attached skinfold set, stored AI explanation).
- **FR-004**: Every edit and deletion MUST produce an audit entry with actor, timestamp, record id, action and the names of changed fields only — no measurement values, athlete names or other identifying data.
- **FR-005**: Parents, athletes, and coaches other than the record's evaluator (unless admin) MUST NOT be able to edit or delete records; the actions MUST be hidden for them, attempts MUST be refused, and each case MUST be covered by denied-path tests.
- **FR-006**: An edit MUST invalidate any stored AI explanation for that record so stale text is never shown.
- **FR-007**: Editing the evaluation date of a record with an attached skinfold set MUST re-apply the skinfold minimum-age and minimum-interval rules and refuse the edit with the same explanation when violated.
- **FR-008**: An edit MUST NOT send a second approaching-circa-PHV notification for a record whose notification was already sent.

**Guided capture**

- **FR-009**: The single-athlete capture MUST offer a guided mode (pre-check → one step per measure → review) and a quick mode (all measures on one screen), switchable at any time, with the coach's last choice remembered on the device. Guided mode is the default for a coach with no saved preference.
- **FR-010**: The pre-check MUST list the measurement conditions — barefoot, light clothing, similar time of day to previous evaluations, before training, equipment on a flat surface — as a reminder, not a gate.
- **FR-011**: Each guided step MUST show a non-identifiable illustration of the measure, a "Dónde" text and a "Cómo" text, and an accessible text alternative for the illustration.
- **FR-012**: Each measure MUST be captured with a single reading, in both modes.
- **FR-013**: Only the final value of each measure MUST be stored (net value for sitting height); the bench height is used for the subtraction but not stored with the record.
- **FR-014**: The sitting-height step MUST accept a bench height, subtract it from the gross reading, and display the net value; the bench height MUST be remembered on the device and pre-filled (editable, zero allowed) on later captures.
- **FR-015**: Arm span MUST remain optional and skippable in both modes.
- **FR-016**: Existing hard validation ranges MUST keep applying to the entered (net) values; the net sitting height MUST also satisfy a plausibility range relative to standing height.
- **FR-017**: Before saving, the system MUST show non-blocking plausibility warnings when, relative to the athlete's previous evaluation: standing height decreased by more than 1 cm; the standing-height gain implies a growth rate above a plausible maximum for the elapsed time (evaluated only when the interval is long enough to be meaningful); or weight changed by more than 10 %. Independently of history, it MUST warn when the sitting/standing ratio is outside the plausible range for children aged 9–16.
- **FR-018**: Warnings MUST name the measure and suggest re-measuring it, allow jumping back to that step, and allow saving anyway. The coach's history MUST show a "Revisar" marker on any record that currently triggers a plausibility warning, computed at display time from the same rules (FR-017) against the previous record; no flag is stored, and the marker disappears once the data is corrected. Families never see the marker.
- **FR-019**: The review MUST present the PHV phase in plain Spanish with its training implication, with technical figures (maturity offset, age at PHV) shown as secondary detail. The live PHV panel MUST no longer interrupt data entry in guided mode.
- **FR-020**: The "Guardar y terminar" / "Guardar y agregar pliegues" exits MUST keep their current eligibility rules (age ≥ 9, skinfold interval open) and behaviour.
- **FR-021**: The system MUST warn, before creating it, when a record for the same athlete and evaluation date already exists, offering to open the existing one.

**Group session**

- **FR-022**: Coaches MUST be able to start a measurement session by selecting athletes they have access to, filterable by category, and work through them as a queue with visible progress.
- **FR-023**: Each athlete in a session MUST go through the same capture (guided or quick) as US2, and MUST be skippable ("Omitir por hoy") without creating a record.
- **FR-024**: Each athlete's capture MUST be saved to the server when the coach confirms it, before moving to the next athlete. The session queue MUST NOT be persisted (neither on the device nor on the server); when starting a session, the athlete picker MUST mark athletes who already have a record for the chosen date.
- **FR-025**: At the end, the session MUST show a summary of measured, skipped and warning-flagged athletes, with direct access to correct any record.
- **FR-026**: From within a session, the coach MUST be able to open the skinfold wizard for an eligible athlete and return to the queue afterwards.

**Resilience**

- **FR-027**: Capture is online-only: the app MUST NOT keep drafts on the device nor queue saves for later; starting a capture without a connection MUST show that a connection is required.
- **FR-028**: A save that fails for lack of connectivity MUST keep the entered values on screen, state clearly that nothing was saved, and offer a manual "Reintentar".
- **FR-029**: Retried saves MUST NOT create duplicate records.

**Field guide**

- **FR-030**: The printable field guide MUST include, before the skinfold sections, the pre-check conditions and one section per basic measure with the same illustration and "Dónde / Cómo" text as the app, from a single shared source of text.

**Illustrations and privacy**

- **FR-031**: Illustrations MUST be non-identifiable line art in the same visual style as the skinfold illustrations (no photos of real athletes, no faces, no text inside the image), generated during implementation through the Gemini or ChatGPT web UI (driven from the owner's browser, using the skinfold illustrations as the style reference) and added to the product as static assets only after the owner approves each one; a missing asset MUST fail the build rather than leave a gap. Prompts sent to the image tool MUST contain no athlete data of any kind.
- **FR-032**: No measurement value, athlete name or identifying data MUST appear in logs, audit metadata, error messages, or analytics.

**Consistency**

- **FR-033**: All new copy MUST be in español neutro (Colombia) with full diacritics, avoiding clinical or judgmental wording about a child's body.
- **FR-034**: Every new screen MUST be usable at 360 px, 768 px and ≥ 1280 px with no page-level horizontal scroll, 48×48 px touch targets, numeric keypads on numeric inputs, and zero accessibility violations on page- and dialog-level components.

### Key Entities

- **Anthropometric record** (existing): one evaluation of one athlete on one date — weight, standing height, sitting height, optional arm span, notes, and all derived growth/maturity values. Gains: editable and deletable. Stores one value per measure, as today; no new stored fields (the "Revisar" marker is derived at display time).
- **Measurement session**: a coach's group measurement run — date, selected athletes, per-athlete status (pending / measured / skipped). Held only in the open screen; never persisted. The records it creates are ordinary anthropometric records.
- **Audit entry** (existing): gains edit/delete actions on anthropometric records.
- **Measure guide content**: the per-measure "Dónde / Cómo" text, illustration and accessible description, shared between the app and the printable field guide.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A wrong record can be corrected or removed by the coach in under 1 minute, and 100 % of the derived values displayed anywhere (growth tab, PHV phase, velocity, newsletter data) reflect the correction on the next view.
- **SC-002**: In a staged test with deliberately injected errors (height 10× off, sitting height without bench subtraction, height lower than the previous evaluation, weight +15 %), 100 % of them produce a warning or validation message before saving.
- **SC-003**: A coach measures one athlete in guided mode (4 measures) in under 2 minutes, and in quick mode in under 1 minute.
- **SC-004**: A group session of 12 athletes is completed with at most one navigation action between athletes, and a summary is available at the end.
- **SC-005**: Zero duplicate records are created across a connectivity loss and a retry, and in 100 % of failed saves the coach sees that the athlete was not saved.
- **SC-006**: On the next real measurement day, the coach rates the new flow as easier than the old grid, and the number of records later corrected or deleted within 7 days is tracked as the error-rate baseline.
- **SC-007**: Zero accessibility violations on every new page and dialog; every new screen usable at 360 px.
- **SC-008**: No measurement value or athlete name appears in audit metadata or logs (verified by privacy tests).

## Assumptions

- Owner decision: work on `main` without a dedicated branch or auto-commits, as in 045/046/047.
- Any coach with access (feature 041 rules) can capture; editing and deleting are limited to the record's evaluator or an admin (owner decision 2026-09-29). If the evaluator's account is deactivated, only an admin can correct their records.
- Deletion is a real removal of the record (with its skinfold set and AI explanation), not a soft-delete; the audit entry is the trace.
- The implausible-growth threshold and the sitting/standing ratio range are set during planning from published paediatric references (e.g. peak height velocity rarely exceeds ~12 cm/year; sitting/standing ratio roughly 0.48–0.56 at these ages).
- Capture is online-only (owner decision 2026-09-29); the feature-046 skinfold wizard keeps its own draft/offline behaviour unchanged.
- Plausibility warnings never block saving; hard validation ranges (existing) still do.
- Illustrations (weight, standing height with the Frankfort plane, sitting height on a bench, arm span, optional equipment/pre-check image) are generated by the implementing agent with Gemini or ChatGPT (web UI, owner's logged-in Chrome session) in the style of `frontend/src/assets/skinfolds/*.webp` (768×768, white background, no text), converted to webp, and reviewed by the owner before being committed. If the web tool is unavailable or the output keeps failing the style/privacy rules after a few attempts, the agent stops and asks the owner rather than shipping a substitute.
- The bench height is a device-level setting (the club uses one box), not per athlete.
- Families and athletes see no new surface; their existing views simply reflect corrected data.
- No change to the AI prompts or pipelines: the anthropometry AI receives the same fields as today, so no golden-eval re-run is required by this feature (an edit only invalidates a cached explanation).
- The monthly newsletter reads records as they are at generation time; already-sent newsletters are not re-issued after a correction.
- A `data-privacy-guard` audit is required (the feature reads and writes athlete-identifiable measurement data).
