# Feature Specification: Body composition by skinfolds (plicómetro) for athletes aged 9 and up

**Feature Branch**: `main` (owner decision 2026-09-23: no dedicated branch; the `speckit.git.feature` hook and every auto-commit hook are skipped)

**Created**: 2026-09-23

**Status**: Draft

**Input**: User description: "Body composition by skinfolds (plicómetro) for athletes aged 9 and up. The coach already records weight, height and sitting height every few months, but those numbers cannot say whether a change in weight was lean tissue or fat; in a real case a female athlete measured six months apart could not be interpreted. The club owns a Slim Guide-class skinfold caliper; the measurer is the coach, not a certified anthropometrist, so the capture flow itself must teach where and how to measure. Guided illustrated capture (six default sites, two readings, third on disagreement, per-site opt-out, survives interruption), printable field guide, coach trends (four-site backbone sum and six-site sum, per-site history, coach-only estimated body fat and fat-free mass, noise-vs-real change, Colombian reference as context), traffic light with escalation and a neutral referral note, AI explanation extended with qualitative descriptions only, family card with a band and one sentence and no numbers, in-app notice without new consent, at most every 90 days. Owner decisions of 2026-09-23 in docs/21-body-composition/proposal.md §7–8. Everything on main, no branches, no auto-commits."

## Context

The anthropometry module records weight, standing height, sitting height and arm span, derives the growth-peak status (pre / circa / post PHV) and places height, weight and BMI on WHO percentiles. That answers "is this child growing as expected?" but not "what did the weight change consist of?". Weight and BMI cannot separate lean tissue from fat, and a rising weight in a girl around her growth peak is ambiguous by construction: girls normally gain fat mass through puberty while boys gain lean mass.

The research in `docs/21-body-composition/` (read `proposal.md` first) established, with sources:

- **Skinfolds are the right next level** for a club with a plastic caliper: cheap, repeatable, and the sum of skinfolds in millimetres tracks individual change better than any converted body-fat percentage.
- **Body-fat percentage is an estimate, not a fact.** Youth equations carry about ±4 points of error and a Colombian validation study found them underestimating fat in adolescents by 9–11 points. Any percentage shown must be labelled as an estimate, restricted to the coach, and never used as a target.
- **Measurement error dominates early on.** A non-certified measurer needs roughly a 7 mm change in the four-site sum over six months before a change can be called real. The tool must say "within the measurement margin" rather than invent trends.
- **Body-image safeguards are not optional.** Body-composition feedback to adolescents is associated with negative body image and dietary restriction. The feature therefore extends the spirit of Constitution Principle V (wellbeing tool, not diagnosis; baseline-anchored interpretation; mastery climate; human in the loop; referral on persistence) to body composition: athletes never see numbers, families see a band and a sentence, the coach sees everything and decides.
- **A Colombian reference exists** (Bogotá schoolchildren aged 9–17.9, open licence, percentile parameters published) for triceps and subscapular skinfolds. It is context for the coach, never a verdict: it is a school population, not an athlete population.

Owner decisions taken on 2026-09-23 (`proposal.md` §7–8): the caliper is a Slim Guide-class plastic caliper reading in 1 mm graduations; six default sites; families see a band and one sentence only; the second-adult check is a reminder, not a gate; cadence is 90 days for everyone; the referral note is generic (no partner named); the AI explanation is part of this release; families are informed with an in-app notice and no new consent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guided, illustrated skinfold capture (Priority: P1)

The coach has just saved the usual weight/height evaluation for an athlete on the tablet. The app offers "Guardar y agregar pliegues". The coach lands on a pre-check screen that lists the conditions (not right after training, dry skin without lotion, a private space, a second adult present, the athlete standing relaxed) as reminders and a short reassurance that the athlete may decline any site. The coach then goes through one screen per site, in this order: triceps, biceps, subscapular, medial calf, iliac crest, supraspinale. Each screen shows a generic line-art illustration of the right side of the body with the landmark, the fold direction and where the caliper goes, two or three lines of "Dónde" and "Cómo", two reading fields in millimetres, and a prominent "Omitir este sitio" action. When the two readings disagree beyond tolerance, the screen asks for a third reading and uses the middle value. A review screen lists every site with its value or "Omitido", the sums that could be computed, and saves the set with the evaluation. If the tablet loses connection or the coach is interrupted, the half-finished set is restored when the coach comes back.

**Why this priority**: Without a capture flow that a non-certified measurer can follow correctly, no other part of the feature has data. The illustrated, one-site-per-screen design is the owner's explicit requirement ("la medición debe ser ilustrativa").

**Independent Test**: Create an evaluation for a test athlete, add skinfolds for six sites with one site skipped and one site needing a third reading, close the tab mid-way, reopen, finish, and confirm the set is stored with that evaluation and shows the skipped site as "Omitido" rather than as an error.

**Acceptance Scenarios**:

1. **Given** the coach has just saved a weight/height evaluation for an athlete aged 9 or older, **When** the save succeeds, **Then** the coach sees two exits, "Guardar y terminar" (today's behaviour) and "Guardar y agregar pliegues", and the fast path is unchanged.
2. **Given** the coach opens the skinfold flow, **When** the pre-check screen appears, **Then** every condition is shown as a reminder the coach can acknowledge, none of them blocks "Siguiente", and the screen states that the athlete may decline any site without consequence.
3. **Given** the coach is on a site screen, **When** the screen renders, **Then** it shows the illustration for that site with a plain-language text alternative, the "Dónde"/"Cómo" instructions, two millimetre inputs accepting half-millimetre steps, and an "Omitir este sitio" control at least as prominent as "Siguiente".
4. **Given** two readings for a site differ by more than the tolerance (the greater of 5 % of their mean or 1 mm), **When** the second reading is entered, **Then** the screen asks for a third reading with a non-alarming message, and the site value becomes the middle of the three; when the readings agree, the site value is their mean and no third reading is requested.
5. **Given** the coach taps "Omitir este sitio", **When** the site is skipped, **Then** the flow continues, the site is recorded as declined (not empty), and no reason is demanded.
6. **Given** a reading is outside the plausible range for that site and age, **When** it is entered, **Then** the coach sees a soft "¿Seguro?" warning and can still proceed.
7. **Given** the coach closes the app half-way through, **When** they reopen the same athlete within the same day, **Then** the draft is offered for restore or discard, and nothing was lost.
8. **Given** the review screen, **When** the coach saves, **Then** the set is attached to the same evaluation date and the athlete's growth tab reflects it without a page reload.

---

### User Story 2 - Reading the change: sums, estimates and noise (Priority: P1)

For an athlete with skinfold sets on file, the coach opens the growth tab and sees a "Composición corporal" section: the trend of the four-site backbone sum (triceps + biceps + subscapular + calf) over time, the six-site sum when all six were taken, per-site history, an estimated body-fat percentage and fat-free mass labelled "estimado", the change since the previous set with an explicit "dentro del margen de medición" or "cambio real" reading, and, as context, where the athlete's triceps and subscapular values sit against the Colombian reference for their age and sex. The section also shows when the next skinfold set is due.

**Why this priority**: This is the question that started the feature: did lean mass, fat mass or both change? Capture without interpretation would leave the coach where they are today.

**Independent Test**: Load two synthetic sets at least 90 days apart for a test athlete (weight up, height up, backbone sum up by exactly the noise threshold) and confirm the screen shows the sums, the estimated fat-free-mass change, the "cambio real" reading at the threshold and the "dentro del margen" reading one millimetre below it.

**Acceptance Scenarios**:

1. **Given** an athlete with at least two sets, **When** the coach opens the section, **Then** the backbone-sum trend and the six-site-sum trend (when available) are charted with dates, and each point can be inspected.
2. **Given** the latest set and the previous set, **When** the change is shown, **Then** the difference in the backbone sum is displayed together with the reading "dentro del margen de medición" when the absolute change is below the noise threshold, and "cambio real" otherwise, with the threshold stated.
3. **Given** a set with triceps and calf present, **When** the coach views the estimates, **Then** the body-fat percentage and fat-free mass appear with the label "estimado" and the margin of error, and they are visible only to coach and admin.
4. **Given** a set in which triceps or calf was skipped, **When** the coach views the estimates, **Then** no percentage or fat-free mass is shown and the reason ("falta tríceps" / "falta pantorrilla") is stated.
5. **Given** a set in which a backbone site was skipped, **When** the coach views the sums, **Then** the backbone sum is shown as "suma incompleta" for that date, the trend line skips that point, and the individual sites still trend.
6. **Given** an athlete aged 9–17 with triceps and subscapular values, **When** the coach views the context, **Then** the app shows the percentile band of each against the Colombian reference for the athlete's age and sex, worded as context ("como referencia") and labelled with the reference's population and side of measurement.
7. **Given** the last set is older than 90 days, **When** the coach opens the athlete, **Then** the section shows that a skinfold set is due; before 90 days it shows the due date and does not suggest a new set.

---

### User Story 3 - Traffic light, escalation and referral note (Priority: P2)

The coach sees a traffic-light reading (verde / ámbar / rojo) for the athlete's body composition with the reason stated in one sentence. The reading combines the athlete's own trend with weight, height velocity and growth-peak stage. A rising sum in a girl around her growth peak reads as expected. Rojo is reserved for the combined pattern: sum falling beyond the margin while weight stalls and height keeps growing. Ámbar and rojo come with a coach-only prompt describing what to do (private conversation, then family conversation, then referral if it persists). From a rojo reading the coach can generate a neutral referral note in Spanish that describes the observed pattern without any label or diagnosis and states that raw history is shared only with the family's authorization.

**Why this priority**: Detecting something that deserves a professional is the owner's second goal, and doing it wrongly (labelling, alarming, diagnosing) is the feature's main harm risk. It depends on Story 2's data.

**Independent Test**: Run a fixed set of synthetic histories (rising sum in a circa-PHV girl; flat sum in a post-PHV boy; falling sum with flat weight and rising height; single set at a high percentile) and confirm the readings are verde, verde, rojo and ámbar respectively, each with its stated reason.

**Acceptance Scenarios**:

1. **Given** a girl at or after her growth peak whose backbone sum rose beyond the margin while weight and height rose within the expected velocity, **When** the reading is computed, **Then** it is verde with a sentence explaining that fat-mass gain around the growth peak is expected.
2. **Given** an athlete whose backbone sum fell beyond the margin while weight stayed flat or fell and height kept growing, **When** the reading is computed, **Then** it is rojo with the pattern stated and the escalation prompt shown to the coach only.
3. **Given** an athlete whose change is within the margin, **When** the reading is computed, **Then** it is verde with "sin cambio real desde la última toma".
4. **Given** an athlete with a real change that no growth pattern explains (for example, sum up sharply while height velocity is flat), **When** the reading is computed, **Then** it is ámbar with a prompt to have a private conversation, never a number.
5. **Given** an athlete with a single set, **When** the reading is computed, **Then** it can be verde or ámbar (from the reference context) but never rojo, and the text says a second set is needed for a trend.
6. **Given** a rojo reading, **When** the coach chooses "Generar nota de remisión", **Then** a Spanish note is produced that describes the observed pattern in neutral terms, contains no diagnosis, label, percentage or target, names no professional or institution, and states that measurement history is attached only with the family's explicit authorization.
7. **Given** any reading, **When** it is stored or displayed, **Then** it is never sent automatically to the family or the athlete.

---

### User Story 4 - Family card and in-app notice (Priority: P2)

A parent opens their child's growth view on an Android phone and sees a "Composición corporal" card with a band label and one sentence in neutral Colombian Spanish, with no percentage and no millimetres. The first time skinfolds exist for the child (or before, when the coach enables the feature), the parent sees a notice explaining what the measurement is, that it is voluntary site by site, that it is taken in a private space, and how results are used. No new consent is requested. Any document the family can download about the athlete follows the same no-numbers rule.

**Why this priority**: Families must not be surprised by a new measurement of their child, and the number-free presentation is the core safeguard. It depends on Story 1's data but not on Story 3's escalation.

**Independent Test**: Log in as a parent linked to a test athlete with a skinfold set, open the growth view and every downloadable document, and confirm the card shows a band and a sentence, the notice is present, and no body-fat percentage or millimetre value appears anywhere; log in as a parent not linked to that athlete and confirm nothing is visible.

**Acceptance Scenarios**:

1. **Given** a parent linked to an athlete with at least one skinfold set, **When** they open the growth view, **Then** they see one card with the band label ("En su curva esperada" / "En observación" / "Requiere acompañamiento profesional") and its sentence, and nothing numeric.
2. **Given** a parent linked to an athlete with no skinfold set, **When** they open the growth view, **Then** the card is absent or shows the neutral "Aún no hay datos suficientes" message used elsewhere.
3. **Given** the in-app notice, **When** the parent reads it, **Then** it explains the measurement, its voluntary and private nature, and how results are used, in the wording approved in `docs/21-body-composition/research-safeguards-referral.md` §5, and it does not ask for a new consent.
4. **Given** a parent downloads the anthropometry document for their child, **When** the document renders, **Then** it contains no skinfold values, no sums and no body-fat percentage.
5. **Given** a parent not linked to an athlete, **When** they request that athlete's growth data, **Then** access is denied exactly as for the rest of the growth data.

---

### User Story 5 - Printable field guide (Priority: P3)

The coach downloads a generic, club-wide "Instructivo de toma de pliegues cutáneos" to laminate and hang at the measurement station. It contains the pre-check list, one section per site with the same illustration and "Dónde"/"Cómo" text as the app, the reading protocol (two readings, tolerance, third reading, rotate through sites, read at about two seconds, right side), and a footer stating that the sheet carries no athlete data.

**Why this priority**: It supports the measurer away from the tablet and reinforces consistency, but the app flow already carries the same guidance.

**Independent Test**: Download the guide as coach and confirm it contains all six sites with illustrations, the protocol, no athlete data, and that a parent cannot download it.

**Acceptance Scenarios**:

1. **Given** a coach or admin, **When** they request the field guide, **Then** a printable document is produced containing the six default sites, each with illustration and instructions, plus the pre-check list and the reading protocol.
2. **Given** the guide, **When** printed in black and white, **Then** landmarks and caliper positions remain distinguishable (shape and label, never colour alone).
3. **Given** a parent, **When** they request the guide, **Then** it is not available to them.

---

### User Story 6 - AI explanation extended to body composition (Priority: P3)

When the coach requests the existing AI explanation of a measurement, and the measurement has a skinfold set, the explanation also covers body composition, for both the coach and the family audience, using qualitative descriptions only ("la suma de pliegues subió de forma esperada para su etapa", "sin cambio real"), never a percentage, a millimetre value, or weight-loss or diet language. The same review, fallback and guardrails as today apply.

**Why this priority**: The owner wants it in this release, but the charts and traffic light already answer the coach's questions; the narrative is an aid, and it carries the highest regression risk.

**Independent Test**: Request the explanation for a measurement with a skinfold set in the offline test lane (no real provider) and confirm the prompt contains only qualitative codes (no name, no millimetre value, no percentage) and the family text contains no number related to body composition; then confirm the reference evaluation set still passes at the existing threshold.

**Acceptance Scenarios**:

1. **Given** a measurement with a skinfold set and valid AI consent, **When** the explanation is generated, **Then** the body-composition part is present for both audiences and describes direction and meaning qualitatively.
2. **Given** the generated family text contains a body-fat percentage, a millimetre value, or weight-loss/diet language, **When** the guardrails run, **Then** the text is blocked and the family sees "no analysis yet", as with today's other rules.
3. **Given** a measurement with a skinfold set and no AI consent, **When** the coach opens the explanation, **Then** nothing is generated, exactly as today.
4. **Given** the provider is unavailable, **When** the explanation is requested, **Then** the rule-based fallback covers body composition with the same qualitative wording.

---

### Edge Cases

- **All six sites skipped**: the set is stored as declined for every site; no sums, no estimates, no traffic light; the coach sees "Sin datos: el/la deportista prefirió no medirse" and the 90-day counter does not restart.
- **Backbone site skipped**: the backbone sum for that date is "incompleta"; the six-site sum is unavailable; per-site trends continue; the traffic light uses whatever legs remain and says which legs are missing.
- **Triceps or calf skipped**: no body-fat or fat-free-mass estimate for that date; the sums and the traffic light still work.
- **Third reading requested but not taken**: the site value is the mean of the two readings and the site is marked "sin confirmar"; the flow does not block.
- **A new set sooner than 90 days**: the app does not offer the step and explains why; the coach can replace or correct the most recent set (same evaluation) but cannot attach a new set to an evaluation dated less than 90 days after the previous set.
- **Only one set on file**: trends, changes and rojo are unavailable; the reading is verde or ámbar from the reference context and says a second set is needed.
- **Athlete younger than 9**: the skinfold step is not offered.
- **Athlete older than the reference range (18+)**: estimates and sums still work; the reference context shows "sin referencia para esta edad".
- **Height velocity unavailable** (fewer than two evaluations): the traffic light omits that leg and says so; rojo cannot fire without it.
- **Evaluation deleted or corrected**: the attached skinfold set is removed or stays attached to the corrected evaluation; sums and estimates are recomputed for that date only.
- **Weight changed on the evaluation after skinfolds were taken**: fat-free-mass estimate is recomputed from the corrected weight; the skinfold values are untouched.
- **Parent with several children**: each child has its own card; nothing about one child appears in another's view.
- **Lost connection at save**: the draft is kept and the save retried; the coach sees "Sin conexión: se guardará cuando vuelvas a tener señal" and never a raw error.
- **Illustration cannot render**: the text alternative is shown; the flow continues.

## Out of Scope

- Bioimpedance scales or any device other than the skinfold caliper.
- Abdominal and front-thigh sites; somatotype, girths or bone breadths.
- Any ranking, leaderboard or comparison between athletes on body composition.
- Body-fat or weight targets, nutrition plans, calorie or diet guidance.
- Automatic messages to families or athletes about body composition.
- Use of body composition for selection or talent identification.
- Changes to the existing weight/height capture flow itself.
- Backfilling historical skinfold data.
- Naming a referral partner or institution in the referral note.
- A new consent scope or a privacy-policy version bump.

## Requirements *(mandatory)*

### Functional Requirements

**Capture**

- **FR-001**: The system MUST let a coach or admin attach one skinfold set to an existing weight/height evaluation of an athlete aged 9 or older, as an optional step offered right after saving the evaluation and also from the evaluation's history entry.
- **FR-002**: The capture flow MUST start with a pre-check screen listing the measurement conditions (not right after training, dry skin without lotion or sunscreen, private space, a second adult present, athlete standing relaxed) as reminders that never block progress, plus a statement that the athlete may decline any site without consequence.
- **FR-003**: The flow MUST present one screen per site, in this default order: triceps, biceps, subscapular, medial calf, iliac crest, supraspinale.
- **FR-004**: Each site screen MUST show a generic line-art illustration of the right side of the body marking the landmark, the fold direction and the caliper position, plus a plain-language text alternative, and "Dónde"/"Cómo" instructions of at most three short lines each.
- **FR-005**: Each site MUST accept two readings in millimetres in half-millimetre steps and MUST request a third reading when the two differ by more than the greater of 5 % of their mean or 1 mm; the site value MUST be the median of three readings when three exist and the mean of two otherwise.
- **FR-006**: Every site MUST offer an "Omitir este sitio" action that records the site as declined, requires no reason, is visually as prominent as the primary action, and is never styled as an error.
- **FR-007**: The system MUST warn, without blocking, when a reading is outside the plausible range for the site and the athlete's age.
- **FR-008**: The flow MUST keep a local draft of a half-finished set so that an interruption, a page reload or a lost connection does not lose entered readings, and MUST offer to restore or discard it on return.
- **FR-009**: A review screen MUST list each site with its value or "Omitido", the number of readings taken, the sums that could be computed, and MUST save the whole set in one action attached to the evaluation date.
- **FR-010**: The system MUST store, for each set, the raw readings per site, the site value, the declined state per site, the caliper model and the protocol version, so that values can be recomputed if the protocol changes.
- **FR-011**: The system MUST NOT offer a new skinfold set for an athlete until 90 days have passed since the evaluation date of the previous set, MUST explain the waiting period, and MUST still allow correcting or replacing the most recent set.

**Computation and display (coach and admin only)**

- **FR-012**: The system MUST compute and show the four-site backbone sum (triceps + biceps + subscapular + calf) for every set where those four sites are present, and the six-site sum when all six are present; a set missing a backbone site MUST show "suma incompleta" for that date.
- **FR-013**: The system MUST chart the backbone sum and, when available, the six-site sum over time, and MUST show per-site history.
- **FR-014**: The system MUST compute an estimated body-fat percentage and fat-free mass using a youth-validated skinfold equation that needs only triceps and calf and no race-based term, MUST label both as "estimado" with their margin of error, and MUST NOT compute them when triceps or calf was declined.
- **FR-015**: The system MUST show the change in the backbone sum since the previous set with the reading "dentro del margen de medición" when the absolute change is below the noise threshold and "cambio real" otherwise; the threshold MUST default to 7 mm for the backbone sum and 10 mm for the six-site sum and MUST be adjustable without a code change when the club measures its own error.
- **FR-016**: The system MUST show the percentile band of the athlete's triceps and subscapular values against the Colombian reference for their age and sex as context, labelled with the reference's population, age range and side of measurement, and MUST show "sin referencia para esta edad" outside the reference range.
- **FR-017**: The system MUST show when the next skinfold set is due (90 days after the last set) alongside the existing next-measurement information.
- **FR-018**: Estimates, sums, per-site values and the traffic-light reason MUST be visible only to coach and admin.

**Traffic light, escalation and referral**

- **FR-019**: The system MUST derive a traffic-light reading (verde / ámbar / rojo) for each athlete with skinfold data from: the change in the backbone sum relative to the noise threshold, the reference percentile bands, the change in BMI-for-age position, the height velocity against the stage-expected range, and the growth-peak stage and sex; the reading MUST state its reason in one sentence and list any leg that could not be evaluated.
- **FR-020**: A rising backbone sum MUST NOT by itself produce rojo; in a girl at or after her growth peak with weight and height rising within the expected velocity it MUST read verde with an explanation that fat-mass gain around the growth peak is expected.
- **FR-021**: Rojo MUST require at least two sets and all three legs of the combined pattern "backbone sum falling beyond the margin, weight flat or falling, height still growing"; with a single set, or with any leg unavailable, the reading MUST be verde or ámbar only and MUST say which leg is missing.
- **FR-022**: Ámbar and rojo MUST show a coach-only prompt with the escalation ladder (private conversation → family conversation → referral if it persists after the next set) worded without numbers, diet or weight-loss language.
- **FR-023**: From a rojo reading the coach MUST be able to generate a Spanish referral note that describes the observed pattern neutrally, contains no diagnosis, label, percentage or target, names no professional or institution, and states that measurement history is attached only with the family's explicit authorization.
- **FR-024**: The system MUST NOT send any body-composition reading, prompt or note to families or athletes automatically.

**Family surface**

- **FR-025**: A parent linked to the athlete MUST see one "Composición corporal" card with a band label and one sentence in neutral Colombian Spanish, using the approved copy (verde: "En su curva esperada"; ámbar: "En observación"; rojo: "Requiere acompañamiento profesional"), and MUST NOT see any percentage, millimetre value, sum or per-site value.
- **FR-026**: Every downloadable document about the athlete available to a parent MUST follow the same no-numbers rule for body composition.
- **FR-027**: The system MUST show families an in-app notice explaining the skinfold measurement, its voluntary site-by-site nature, the private setting and the use of results, using the approved addendum copy, and MUST NOT require a new consent or a policy re-acceptance; capture MUST remain gated by the existing anthropometry consent.
- **FR-028**: Parent access MUST follow the existing rule: only their own linked athletes, denied otherwise.

**AI explanation**

- **FR-029**: When a measurement has a skinfold set, the existing AI explanation MUST cover body composition for both audiences using qualitative descriptions only; the information given to the provider MUST be limited to qualitative codes (band, direction of change, number of declined sites) and MUST never include names, millimetre values or percentages.
- **FR-030**: The guardrails MUST block any generated text that contains a body-fat percentage, a millimetre value, or weight-loss or diet language, with the same consequence as today's blocked cases; the rule-based fallback MUST cover body composition with the same qualitative wording.
- **FR-031**: The reference evaluation set for the growth explanation MUST gain cases with body-composition input and MUST keep passing at the existing threshold.

**Field guide**

- **FR-032**: Coach and admin MUST be able to download a printable, club-wide field guide with the pre-check list, the six default sites (illustration + instructions), the reading protocol and a footer stating it carries no athlete data; it MUST remain legible in black and white and MUST NOT be available to parents.

**Privacy and safeguards**

- **FR-033**: No log entry, error message or provider request MAY contain an athlete's name together with a skinfold value, sum, estimate or reading; test fixtures MUST be synthetic.
- **FR-034**: The feature MUST NOT rank, compare or list athletes by any body-composition value, MUST NOT offer targets or goals for any value, and MUST NOT be usable for selection.
- **FR-035**: Every interactive control in the capture flow, including the reading inputs and "Omitir este sitio", MUST meet the 48 × 48 px touch-target floor; each illustration MUST have a text alternative; step changes MUST move focus to the step heading; warnings MUST use the shared amber "attention" semantics, never the red "error" semantics.

### Key Entities *(include if feature involves data)*

- **Skinfold set**: the body-composition measurement attached to exactly one weight/height evaluation of one athlete; holds the per-site readings and values, the declined state per site, the caliper model, the protocol version, the computed sums, the estimated body-fat percentage and fat-free mass with their equation version, and the evaluation date it inherits.
- **Skinfold site**: one of the six default sites (triceps, biceps, subscapular, medial calf, iliac crest, supraspinale) with its illustration, instructions, fold orientation, plausible range by age and whether it belongs to the backbone sum.
- **Body-composition reading**: the derived, non-stored interpretation for an athlete at a point in time: change since the previous set, noise-vs-real flag, reference percentile context, traffic-light band with reason and missing legs.
- **Colombian skinfold reference**: the published percentile parameters for triceps and subscapular by sex and age used for context, with its provenance (population, age range, side, licence).
- **Family notice**: the informational text families see about the measurement; not a consent record.
- **Referral note**: a generated, neutral Spanish document describing an observed pattern for a health professional, produced on demand by the coach and never sent automatically.
- **Field guide**: the generic printable instructivo; contains no athlete data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any athlete with two skinfold sets at least 90 days apart, the coach can answer "did lean mass, fat mass or both change?" from a single screen that shows the backbone-sum change, the estimated fat-free-mass change and the noise-vs-real reading.
- **SC-002**: A measurer who has never taken skinfolds completes the six default sites for one athlete in under 10 minutes on a tablet without leaving the flow to look up instructions (validated in a supervised trial with an adult volunteer).
- **SC-003**: 100 % of family-facing screens, documents and AI texts about body composition contain no percentage, sum or millimetre value, verified by automated tests over every family surface.
- **SC-004**: Across the fixed scenario set (rising sum in a circa-PHV girl; flat sum in a post-PHV boy; falling sum with flat weight and rising height; single set at a high percentile), the traffic light returns verde, verde, rojo and ámbar respectively, and no scenario with a rising sum alone returns rojo.
- **SC-005**: A capture interrupted at any step is restored with all entered readings intact in 100 % of attempts (page reload, tab close, connection loss).
- **SC-006**: Every page- and dialog-level screen of the capture flow, the coach section and the family card passes the accessibility audit with zero violations, and every control meets the 48 px floor.
- **SC-007**: No new skinfold set can be attached less than 90 days after the previous set's evaluation date, while correcting the most recent set remains possible.
- **SC-008**: The growth-explanation reference evaluation, extended with body-composition cases, passes at the existing threshold, and every provider request in the offline test lane is free of names, millimetre values and percentages.
- **SC-009**: The field guide is produced in one action by a coach and contains all six sites with illustrations; a parent cannot obtain it.

## Assumptions

- The club's caliper is a Slim Guide-class plastic caliper with 1 mm graduations read to the nearest 0.5 mm; the coach checks the zero before each session and runs the self-calibration sessions on adult volunteers described in `docs/21-body-composition/proposal.md` §5 (W0) before trusting any trend. The noise thresholds (7 mm backbone, 10 mm six-site, per six months) are starting values from the published novice error, not club-measured values.
- The estimated body-fat percentage uses the Slaughter–Lohman triceps + calf equation (no race term, no maturation split) as decided in `proposal.md` D4; its stated margin is about ±4 points.
- The reference context uses the Bogotá FUPRECOL 2016 percentile parameters (ages 9–17.9, open licence, measured on the left side); it is a school population, shown as context only.
- Six default sites are taken in the stated order; abdominal and front thigh are excluded; the four-site backbone sum is the comparable series across time and the six-site sum is secondary.
- Cadence is a flat 90 days for every maturation stage (owner decision C5).
- The referral note is generic; the club has no named referral partner (owner decision C6).
- The AI explanation extension is part of this release (owner decision C7) and reuses the existing review, fallback, guardrail and consent behaviour of the growth explanation.
- Families are informed through an in-app notice using the approved addendum copy; the existing anthropometry consent covers skinfolds; no privacy-policy version bump (owner decision C8).
- The tool is an internal monitoring aid and is never presented as an official classification under Resolución 2465 de 2016.
- Existing role rules apply unchanged: coach and admin capture and interpret; parents read only their own athletes; athletes do not log in.
- Height velocity, growth-peak stage, BMI-for-age position and the family growth view already exist and are reused, not rebuilt.
- Work happens on `main` with no feature branch and no auto-commits (owner decision).
