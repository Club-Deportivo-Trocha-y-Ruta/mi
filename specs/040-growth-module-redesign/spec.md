# Feature Specification: Growth module redesign — one reference standard, decision-first tab, family view

**Feature Branch**: `feat/040-growth-module-redesign`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "Rediseño del módulo de crecimiento" (the `Crecimiento` tab of the athlete detail, coach and parent views), specified from the audit and work plan in `docs/18-growth-module-redesign/proposal.md`; the owner asked to continue with `/speckit-plan` (with research) and `/speckit-tasks` afterwards.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every growth number comes from one reference standard (Priority: P1)

The coach records a measurement for an athlete. Every place that reads it — the growth tab, the point on the growth curve and its hover detail, the table behind the curve, the family newsletter PDF and the dashboard alerts — shows the **same** Z-score, percentile and classification band, and that classification is computed against the reference Colombia's Resolution 2465/2016 prescribes (WHO 2007) and labeled truthfully. Measurements recorded before this change are recomputed once against the same standard, without altering any raw value, and the coach receives a short list of which athletes changed band so they can revisit what families were told.

**Why this priority**: Today the stored classification and the curve on screen are computed against two different population references, so the same child can show two different percentiles on one screen under a label that claims a single regulatory source. Everything else in this feature would be decorating a number that is not trustworthy.

**Independent Test**: Record a measurement for a test athlete; open the growth tab, hover the point on the curve, open the table view and generate the family PDF. All four show one Z, one percentile, one band, and the source label reads "OMS 2007 / Res. 2465/2016". Run the historical recomputation on a copy of the data: raw height/weight/sitting-height values are unchanged, derived values are refreshed, and a band-change list is produced.

**Acceptance Scenarios**:

1. **Given** a new measurement for an athlete aged 5–19, **When** it is saved, **Then** height-for-age and BMI-for-age Z-score, percentile and band are computed against the WHO 2007 reference and stored with an explicit source tag.
2. **Given** that measurement, **When** the coach views the tab, hovers the curve point, opens the table view, or the family PDF is generated, **Then** all surfaces show identical Z-score (to two decimals), percentile and band label.
3. **Given** measurements stored before this feature, **When** the one-time recomputation runs, **Then** every derived value is refreshed to the WHO reference, no raw measurement changes, re-running is a no-op, and a report lists athletes whose band changed (by athlete identifier, never by name in logs).
4. **Given** an athlete older than 10 years, **When** the tab is viewed, **Then** no weight-for-age classification or curve is offered anywhere (WHO publishes none past age 10); weight is shown only as a plain measurement and trend.
5. **Given** an athlete whose age at measurement is outside the reference range (below 5 or above 19), **When** the tab is viewed, **Then** classification tiles show a calm "sin referencia para esta edad" state and no curve point is plotted, without error.

---

### User Story 2 - The coach reads the decision before the evidence (Priority: P1)

The coach opens an athlete's `Crecimiento` tab on the tablet. Without scrolling they see: the maturation stage (Pre / Circa / Post-PHV) with the estimated PHV age and how many months away it is; the current growth velocity (cm per year, over which interval) compared with what is expected for the stage; the height-for-age and BMI-for-age bands with the icon + label vocabulary used everywhere else in the app; when the next measurement is due and whether it is on time; and any active alert (in the growth spurt, very low height or BMI, rapid growth, approaching the spurt). Directly below, a compact block lists what changes in training this month for this athlete.

**Why this priority**: These are the inputs the coach actually uses to dose training for a growing child. Today the tab opens on three near-empty line charts and the coach has to leave the athlete (to the dashboard) to see velocity and due date, or read the AI's prose to find the velocity as a sentence.

**Independent Test**: Open the tab for an athlete with two or more measurements on a 1024 px-wide tablet and on a 390 px phone. Confirm the five readings (stage, velocity, two bands, next measurement) and any alert are visible on the first screen (tablet) or within one scroll (phone), and that a coach can answer "¿en qué etapa está?", "¿cuánto ha crecido?", "¿cuándo mido de nuevo?", "¿está en su canal?" and "¿qué no debe hacer esta semana?" from this tab alone.

**Acceptance Scenarios**:

1. **Given** an athlete with at least two measurements, **When** the tab opens, **Then** stage, PHV age with months from today, growth velocity (cm/year + interval in months), height-for-age band, BMI-for-age band and next-measurement date with its on-time / due-soon / overdue status are visible without scrolling on a tablet.
2. **Given** an athlete with exactly one measurement, **When** the tab opens, **Then** the velocity tile explains that a second measurement is needed and the rest of the summary renders normally.
3. **Given** two measurements fewer than 30 days apart, **When** velocity is shown, **Then** it carries a visible caveat that the interval is short and the value is orientative.
4. **Given** an athlete in Circa-PHV, or with height-for-age or BMI-for-age below the 3rd percentile, or with velocity at or above the rapid-growth threshold, **When** the tab opens, **Then** the matching alert appears above the summary with icon + text, using the same wording as the coach dashboard.
5. **Given** the summary, **When** the coach reads the "Qué cambia en el entrenamiento" block, **Then** it lists only the rules that differ from the default for the athlete's age group and stage (allowed / caution / not allowed with icon + label), with a control to expand the full rule set, and it contains no estimated maximum heart-rate number.
6. **Given** any part of the summary fails to load, **When** the tab is shown, **Then** that part shows a friendly retry state and the rest of the tab still renders.

---

### User Story 3 - One growth curve that can actually be read (Priority: P2)

The coach scrolls to the growth curve. The horizontal axis is windowed around the athlete's own measurements (roughly two years before the first and three years after the last) with a control to widen to the full 5–19-year range; the athlete's trajectory stands out from the reference; the median and the outer reference limits are drawn, with the intermediate lines available on demand; the estimated PHV (or PWV for weight) is marked; the coach can switch indicator (height, BMI — weight only up to age 10), switch the axis between chronological and biological age, open a table of the same points, and export the chart as an image. Beneath the chart one sentence interprets the latest point in plain Spanish.

**Why this priority**: The curve is the only informative visual on the tab, but today it spans the whole 5–19-year range so 2–4 measurements occupy a sliver of the width, and its colouring reads as an alarm. It depends on Story 1 for correct numbers.

**Independent Test**: Open the curve for an athlete with three measurements over 14 months. Confirm the points span most of the plot width, the athlete line is visually distinct from every reference line, the P50 and outer limits are labeled, toggling "Detalle" adds the intermediate lines, the biological-age axis places the PHV marker at zero, the table view lists the same three points with the same values as the hover detail, and the exported image contains the chart title, source label and no athlete name.

**Acceptance Scenarios**:

1. **Given** an athlete with measurements, **When** the curve renders, **Then** the x-axis window is [first measurement − 2 y, last measurement + 3 y] clamped to 5–19 y, and a control widens it to the full range.
2. **Given** the curve, **When** the coach hovers or taps near a measurement, **Then** the detail shows month-year of the measurement, age, value, Z-score, percentile and band — the same values as the summary tiles and the table view.
3. **Given** the curve, **When** the coach opens the table view, **Then** a visible table lists every measurement with date (month-year), age, value, Z-score, percentile and band, and the table is the accessible alternative to the chart.
4. **Given** the coach role, **When** the axis toggle is set to biological age, **Then** ticks read as years relative to PHV and the marker sits at zero; the parent role never sees this toggle.
5. **Given** the athlete is older than 10 years, **When** indicators are listed, **Then** only height and BMI are offered.
6. **Given** the coach exports the chart, **When** the file is produced, **Then** it contains the chart, the indicator name and the reference source, and its file name carries no athlete name.

---

### User Story 4 - Families see growth in family language (Priority: P2)

A parent opens their child's growth section. They read the stage in plain words ("Tu hijo está en su pico de crecimiento — etapa clave"), two cards that say whether height and weight-for-height are within the expected range using a short narrative sentence and a coloured icon + label, a simplified growth curve (median and expected band only, no clinical toggles), the coach-approved AI explanation, and the list of measurements (date, height, weight). They never see Z-scores, percentile numbers, the maturity-offset index, clinical headline labels such as "obesidad" or "delgadez", or scientific bibliography.

**Why this priority**: Parents currently receive the coach's clinical view verbatim, including labels that can stigmatize a child, and — because of a latent defect — the classification of the **oldest** measurement instead of the latest. Families are the audience with the least context and the most at stake.

**Independent Test**: Log in as the parent of an athlete with three measurements whose latest is in a different band than the oldest. Confirm the classification shown corresponds to the latest measurement, no numeric Z/percentile appears anywhere on the page, no clinical headline label appears, the bibliography section is absent, and the AI explanation is read-only.

**Acceptance Scenarios**:

1. **Given** a parent viewing their child, **When** the growth section opens, **Then** stage, two narrative band cards and the simplified curve are based on the **latest** measurement.
2. **Given** the parent view, **When** any band is shown, **Then** it uses the family label and narrative for that band (e.g., "Por encima del rango esperado — revisaremos la tendencia"), never the clinical term, and colour is always accompanied by icon + text.
3. **Given** the parent view, **When** the page is searched for numerals, **Then** no Z-score, percentile, maturity offset or reference-line label is present; the curve shows only the athlete line, the median and the expected band.
4. **Given** a parent with more than one child, **When** they switch child, **Then** the section re-renders for the new child with no data from the previous one.
5. **Given** the coach has not yet generated the AI explanation for this child, **When** the parent opens the section, **Then** a calm "aún no disponible" state is shown instead of a generate action.

---

### User Story 5 - The tab belongs to the product (Priority: P3)

Everything on the tab uses the app's shared visual language: metric tiles, status badges (icon + label), collapsible sections, solid hairline grids, the product accent for the athlete's own series, status colours only for status. Maturation is shown as a simple timeline (Pre → Circa → Post with today's position and the estimated PHV age) instead of a line chart of an index. Morphology and bike-fit keep their content on shared tiles. The tab is a deliberate destination — the athlete page no longer jumps to it automatically — and its heavy chart assets load only when the tab is opened, so the athlete page itself gets lighter for everyone, including parents who never open it.

**Why this priority**: The rest of the coach surface was unified in the 027→035 program; this tab still carries hand-rolled tiles, three colour systems and a chart style the design rules forbid. It also silently costs every visitor the weight of chart libraries and reference tables they may never use.

**Independent Test**: Visual review of the tab against the design-system checklist (tiles, badges, grid, colours); confirm the athlete page opens on "Info general" and stays there; measure the athlete page's initial transfer size before and after and confirm chart assets are only fetched on opening the tab.

**Acceptance Scenarios**:

1. **Given** the athlete page, **When** it opens without an explicit tab in the address, **Then** it shows "Info general" regardless of how many measurements exist, and the growth summary the coach needs at a glance is present in the page's top tiles.
2. **Given** the tab, **When** it is opened for the first time in a session, **Then** a skeleton is shown while chart assets load, and the athlete page itself loaded earlier without those assets.
3. **Given** any status shown on the tab (stage, band, measurement due, rule), **When** rendered, **Then** it uses the shared status badge with icon + label; no status is conveyed by colour alone.
4. **Given** the maturation timeline, **When** rendered, **Then** it shows the three stages, today's position, the estimated PHV age, and a text alternative for assistive technology.
5. **Given** the morphology block with arm span recorded, **When** rendered, **Then** talla, envergadura, difference and ape index are shown on shared tiles with the bike-fit guidance and the "no usar para selección de talento" note unchanged; without arm span it shows the existing prompt to record it.

---

### Edge Cases

- Athlete with no measurements: the tab is not offered; the page's tiles show an empty state with a call to record the first measurement.
- Single measurement: velocity unavailable with explanation; next-measurement date computed from that single record's stage.
- Two measurements fewer than 30 days apart: velocity shown with a "intervalo corto" caveat; rapid-growth alert suppressed for intervals under 30 days.
- Age at measurement outside 5–19 years: no reference; tiles and curve show a no-reference state; PHV stage still shown when computable.
- Athlete older than 10 years: weight-for-age is never classified or plotted; weight appears only as measurement and trend.
- Historical measurements not yet recomputed (e.g., recomputation failed at startup): tiles show the value with a "referencia anterior" note rather than mixing sources silently; the coach dashboard flags that recomputation is pending.
- AI explanation without guardian consent: the AI card is absent for both roles (existing consent gate unchanged).
- Arm span not recorded: morphology block shows the prompt to record it.
- Parent whose child has measurements but the coach never opened the tab: family view still works (no dependency on coach actions except the AI explanation).
- Very slow network: cached summary shows immediately with a refresh indicator; chart skeleton never becomes an unbounded spinner; server cold-start state is surfaced as elsewhere in the app.
- Post-PHV athlete measured long after the spurt: timeline shows "hace N meses"; velocity compared to the post-spurt expected range, not the peak range.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST compute height-for-age and BMI-for-age Z-score, percentile and classification band against the WHO 2007 growth reference for every measurement of athletes aged 5–19, and MUST store the reference source alongside the derived values.
- **FR-002**: The system MUST NOT compute, store or display a weight-for-age classification or curve for athletes older than 10 years; weight MUST remain visible as a raw measurement and trend.
- **FR-003**: Every surface that shows a measurement's Z-score, percentile or band (growth tab tiles, curve hover detail, table view, family newsletter PDF, dashboard alerts, AI context) MUST read the same stored derived values; no surface may recompute against a different reference.
- **FR-004**: The system MUST provide a one-time, idempotent recomputation of derived values for existing measurements that never modifies raw measurements, tags each row with the reference used, and produces a report of athletes whose band changed, identified by athlete identifier only.
- **FR-005**: Classification band cut-offs MUST follow Resolution 2465/2016 for ages 5–17 (height-for-age: retraso < −2, riesgo −2 to < −1, adecuada ≥ −1 with "talla alta" only above +2 as informational; BMI-for-age: delgadez < −2, riesgo −2 to < −1, adecuado −1 to +1, sobrepeso > +1 to +2, obesidad > +2) and MUST be defined once and shared by every surface.
- **FR-006**: The system MUST provide, per athlete, a growth summary containing: maturation stage, maturity offset, estimated PHV age, months from PHV to today, growth velocity in cm/month and cm/year with the interval used, the expected velocity range for the stage, next measurement due date, measurement status (on time / due soon / overdue / never), days overdue, active growth alerts, and the latest bands with their source; the summary MUST be readable by coach, admin, and the athlete's own parent only.
- **FR-007**: Growth velocity MUST be derived from the two most recent measurements; it MUST be reported as unavailable with a single measurement and MUST carry a short-interval caveat when the interval is under 30 days, during which the rapid-growth alert is suppressed.
- **FR-008**: Measurement intervals (Pre-PHV 90 days, Circa-PHV 30 days, Post-PHV 120 days) and growth alerts (rapid growth ≥ 0.6 cm/month, approaching the spurt, stage changed) MUST be the same ones the coach dashboard already uses, defined once.
- **FR-009**: The coach growth tab MUST show, before any chart and without scrolling on a tablet-width screen: stage tile, velocity tile, height-for-age tile, BMI-for-age tile, next-measurement card and active alerts.
- **FR-010**: The training-implications block MUST derive from a single rule table keyed by age group (10–12 / 13–15) and stage, MUST show by default only the rules that differ from the age-group default with an expand control for the full set, MUST express each rule as allowed / caution / not allowed with icon + label, and MUST NOT display an estimated maximum heart-rate value.
- **FR-011**: The growth curve MUST window its age axis to [first measurement − 2 years, last measurement + 3 years] clamped to the reference range, MUST offer a control to show the full 5–19-year range, and MUST use round axis ticks.
- **FR-012**: The growth curve MUST draw the athlete's series in the product accent and visually distinct from all reference lines; by default it MUST show the median and the outer reference limits (P3, P97) with the intermediate lines (P10, P25, P75, P90) available on demand; MUST use solid hairline grids; and MUST NOT fill full-height alarm-coloured areas.
- **FR-013**: The growth curve MUST mark the estimated PHV age (PWV for weight, offset by sex as today) and MUST keep the indicator-specific explanatory note.
- **FR-014**: The growth curve MUST offer a visible table view listing every measurement with month-year, age, value, Z-score, percentile and band, serving as the accessible alternative to the chart, and an image export whose file name contains no athlete name.
- **FR-015**: The chronological / biological axis toggle MUST be available to coach and admin only, and only for indicators where PHV applies.
- **FR-016**: The family (parent) view MUST show the stage in family wording, one narrative card per band (height-for-age; BMI-for-age titled in family terms), a simplified curve (athlete line, median and expected band only, no toggles), the read-only AI explanation, and the measurement list; it MUST NOT show Z-scores, percentiles, maturity offset, clinical headline labels, reference-line labels or bibliography.
- **FR-017**: The family view MUST always be based on the athlete's latest measurement.
- **FR-018**: Every band, stage and measurement status MUST be presented with the shared status badge (icon + label); colour MUST never be the only channel; hues MUST follow the app's status vocabulary (success / attention / error / neutral).
- **FR-019**: Maturation MUST be shown as a three-stage timeline with today's position, the estimated PHV age and a text alternative; the maturity-offset-over-time line chart and the height/weight-over-time line charts MUST be removed (their information moves to the tiles' trend indicators and to the table view).
- **FR-020**: The athlete page MUST open on "Info general" unless a tab is specified in the address; it MUST NOT auto-switch to the growth tab; the page's top tiles MUST include stage, latest height with percentile, velocity and next-measurement status so the glance-level summary survives the change.
- **FR-021**: The growth tab's chart assets and reference tables MUST load only when the tab is opened; the athlete page MUST render without them.
- **FR-022**: All athlete-facing and parent-facing copy introduced or changed MUST be español neutro with full diacritics and MUST avoid clinical or judgmental language toward the child (existing strings without diacritics on this tab MUST be corrected).
- **FR-023**: Loading, empty, error and retry states MUST exist for the summary, the curve, the table and the family cards; the server cold-start state MUST be surfaced as elsewhere in the app.
- **FR-024**: The AI PHV explanation MUST address the coach when shown on the coach tab and the family when shown to parents; both variants MUST keep the existing consent gate and guardrails, and the coach variant MUST include the velocity as a number.
- **FR-025**: No name, birth date or free-text note of a minor MUST appear in logs, recomputation reports, export file names or any new request/response beyond what today's measurement listing already returns; the growth summary MUST expose no third-party data.

### Key Entities *(include if feature involves data)*

- **Growth measurement**: an existing dated record of height, weight, sitting height and optional arm span for one athlete, with derived maturation values (stage, offset, PHV age) and derived growth values (BMI, Z-scores, percentiles, bands). Gains a **reference source** tag.
- **Growth reference**: population reference constants by sex, age in months and indicator, from a named source (WHO 2007 as the standard; CDC retained only for legacy/document use). Contains no athlete data.
- **Growth summary**: a derived, per-athlete reading (stage, PHV timing, velocity and its interval, expected velocity range, next measurement date and status, alerts, latest bands with source). Never stored; always derived from the two latest measurements.
- **Band vocabulary**: the single definition of cut-offs, coach label, family label, narrative sentence and status tone per indicator and band.
- **Training implication rule**: one row per (age group, stage, topic) with status (allowed / caution / not allowed) and short text; the default row per age group defines what counts as "differs from default".

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an audit set of at least six measurements across both sexes and three stages, the Z-score, percentile and band shown on the tab tiles, curve detail, table view and family PDF match exactly (0 discrepancies), and every source label reads "OMS 2007 / Res. 2465/2016".
- **SC-002**: On a 1024 px-wide tablet, stage, velocity, both bands and next-measurement status are visible without scrolling; on a 390 px phone within one scroll. Verified on both breakpoints for athletes with 1, 2 and 6 measurements.
- **SC-003**: A coach can answer the five questions of Story 2 from the tab alone in under 30 seconds each in a moderated test with the club's coach (5/5 answered, 0 navigations away).
- **SC-004**: The parent view contains zero numeric Z-scores or percentiles, zero clinical headline labels and zero bibliography entries, and reflects the latest measurement for 100 % of parent-linked test athletes.
- **SC-005**: The athlete page's initial transfer drops by at least 100 KB (compressed) for a first visit, and opening the growth tab shows the summary within 1 second from cached data and the chart within 2 seconds on a simulated 3G connection.
- **SC-006**: Zero accessibility violations on the coach tab and the family view (automated audit), a visible table alternative exists for the curve, and every interactive control measures at least 48 × 48 px.
- **SC-007**: The historical recomputation processes 100 % of existing measurements, changes zero raw values, is a no-op on a second run, and produces a band-change report that the coach reviews before the next newsletter cycle.
- **SC-008**: For an athlete with three measurements over 14 months, the default curve window is bounded to the measurements plus fixed clinical context (2 years before the first, 3 years after the last), so the measurements span at least 18 % of the curve width — more than twice the retired full-range chart (8.4 %) — and consecutive measurements 7 months apart sit at least 60 px apart on a 1024 px-wide viewport; the "Ver 5–19 años" control restores the full reference range. *(Amended 2026-09-04 during implementation: the original "≥ 60 %" figure was an estimate that is arithmetically unreachable under FR-011 for any athlete age; the Phase 5 gate measured the real values — see `checklists/coach-tab.md`.)*
- **SC-009**: Existing behaviour that must survive: PHV stage and offset values unchanged for every athlete (0 differences before/after), PNG export still works, AI explanation still generated only with consent, dashboard measurement alerts unchanged.

## Assumptions

- The owner accepted the recommended defaults for the seven open decisions in `docs/18-growth-module-redesign/proposal.md` §10 by proceeding to specification: weight-for-age is dropped above age 10 (D1); the upper height band follows Resolution 2465 (D2); family BMI wording is neutral, clinical label coach-only (D3); no maximum heart-rate estimate is displayed (D4); the automatic jump to the growth tab is removed (D5); image export is kept in the chart toolbar (D6); the training-implications block stays on the tab in compact form (D7).
- WHO 2007 reference constants are freely available and already vendored on the client; they can be vendored on the server under the same terms.
- The PHV method (Mirwald), measurement intervals and growth-alert thresholds are unchanged; this feature makes them visible per athlete, not different.
- The AI explanation's content pipeline, consent gate and guardrails are unchanged; only its audience framing and a numeric velocity are added.
- The family newsletter PDF chart follows the same reference switch; its layout is unchanged.
- Adult-height prediction, body-composition measures and integration with external growth software remain out of scope (as in the original 04-percentiles design).
- The measurement capture form is unchanged.
- Approximately 30 athletes with up to ~10 measurements each; the recomputation is small and runs at deployment.
- Coach and admin share the coach tab; parents see only their own children, enforced by the existing access rules.
