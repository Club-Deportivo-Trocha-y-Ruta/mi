# Feature Specification: Structured Interval Training with Strava Correlation

**Feature Branch**: `026-structured-interval-training`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "Entrenamientos estructurados con intervalos + correlación con Strava — el coach diseña sesiones con estructura de intervalos (ej. 5min calentamiento + (2min Z2 + 1min recuperación)x2), genera un instructivo para que los padres lo configuren manualmente en el dispositivo del atleta (iGPSport/Magene/Garmin, sin push automático), y al sincronizar la actividad Strava se compara automáticamente lo planeado vs lo real por laps (sin datos GPS). Alcance v1 acotado tras entrevista con el coach: editor de intervalos como entidad adjunta separada + instructivo de descarga manual + matching automático con recálculo manual + laps persistidos (sin cadencia) + vista de detalle solo-coach + biblioteca de plantillas. Fallback sin-Strava, delta de RPE, alerta de cadencia, envío automático del instructivo y sugerencia de plantilla por calendario quedan explícitamente fuera de v1."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Design an interval structure for a session (Priority: P1)

A coach, while planning a training session, builds an interval-based structure for it: a warmup, one or more repeatable work/recovery block groups, and a cooldown — each block with a duration, a target heart-rate zone, and a target cadence. The structure is attached to that session as its own entity, the same way technical-skill and strength blocks are already attached to sessions today.

**Why this priority**: Nothing else in this feature (instructivo, matching, templates) can exist without an interval structure to source data from. It is the foundation and is fully usable/demoable on its own — a coach can already use it purely as a richer session-planning tool even before any Strava activity is ever linked.

**Independent Test**: Can be fully tested by creating a session, attaching a new interval structure with at least one repeated block group, saving it, and reopening the session to confirm the structure persisted correctly — no Strava data involved.

**Acceptance Scenarios**:

1. **Given** a coach is editing a training session for a 13-15 category athlete, **When** they add a warmup block, a work/recovery group repeated twice, and a cooldown block, each with duration/zone/cadence, **Then** the structure saves and is retrievable attached to that session.
2. **Given** a coach attempts to save a block with a cadence target below 60 rpm, **When** they submit the structure, **Then** the system rejects the save and explains the minimum-cadence rule.
3. **Given** a coach is editing a session for a 10-12 category athlete and adds a block at Z3 intensity or higher, **When** they try to save the structure, **Then** the save is blocked outright and the coach is told this intensity is not available for that age category.
4. **Given** a coach is editing a session for a 10-12 category athlete and the structure contains only Z1-Z2 blocks, **When** they save, **Then** the system requires an explicit confirmation step before saving and records that confirmation.
5. **Given** a coach is editing a session for an athlete under 13, **When** they look for a power/wattage target option on a block, **Then** no such option is offered — only zone- and cadence-based targets exist.

---

### User Story 2 - Review plan-vs-actual compliance after a Strava activity syncs (Priority: P2)

After a coach has linked a synced Strava activity to a session that has an interval structure (existing manual linking from feature 025), the system automatically compares the actual laps of that activity against the planned blocks and shows the coach a lap-by-block breakdown with a compliance indicator. If the coach edits the structure afterward, they can manually trigger a recalculation.

**Why this priority**: This is the core value proposition described in the original request — objective evidence of adherence to the plan, replacing subjective post-session recollection. It depends on User Story 1 existing (a structure to compare against) and on Strava activities already being linked (existing capability from feature 025).

**Independent Test**: Can be fully tested by attaching an interval structure to a session (per US1), linking a Strava activity with known laps to that session, and confirming the plan-vs-actual comparison appears automatically without further action; then editing the structure and confirming a manual recalculate button updates the comparison.

**Acceptance Scenarios**:

1. **Given** a session has an interval structure and a Strava activity is linked to it, **When** the activity's laps become available in the system, **Then** the plan-vs-actual comparison is computed automatically with no action required from the coach.
2. **Given** a computed plan-vs-actual comparison exists, **When** the coach opens the session's activity detail view, **Then** they see each planned block paired with its matched lap (or explicitly marked as unmatched) and a per-block compliance indicator.
3. **Given** the linked activity has fewer actual laps than planned blocks, **When** the comparison is computed, **Then** the unmatched trailing blocks are clearly flagged as not completed, without the system erroring or blocking the view.
4. **Given** the linked activity has more actual laps than planned blocks, **When** the comparison is computed, **Then** the extra laps are shown as unmatched/extra rather than silently discarded or forced onto the wrong block.
5. **Given** a coach edits the interval structure after a comparison was already computed, **When** they open the detail view, **Then** they can trigger a manual recalculation and the comparison updates to reflect the edited structure.
6. **Given** a parent or athlete account, **When** they attempt to view the plan-vs-actual comparison or the activity detail view for their own athlete, **Then** they cannot access it — this view is coach/admin-only in v1.

---

### User Story 3 - Generate a parent instructivo for manual device setup (Priority: P3)

A coach generates a downloadable PDF instructivo from a session's interval structure, with step-by-step instructions for a parent to manually configure the equivalent interval/lap program on the athlete's iGPSport, Magene, or Garmin device before training.

**Why this priority**: Necessary to make the plan actionable in the real world (no automatic push to devices exists), but it is a downstream, independently shippable slice once a structure exists — it doesn't block or get blocked by the matching feature.

**Independent Test**: Can be fully tested by attaching an interval structure to a session (per US1), choosing a device brand, generating the PDF, and confirming it downloads with instructions matching the structure's blocks — no Strava linking required.

**Acceptance Scenarios**:

1. **Given** a session has a saved interval structure, **When** the coach requests the instructivo for a specific device brand (iGPSport, Magene, or Garmin), **Then** a PDF is generated and downloaded with brand-specific step-by-step configuration instructions matching every block in the structure.
2. **Given** an instructivo has just been generated, **When** the coach checks how it was delivered, **Then** it was only made available as a manual download — no email was sent and no public link/QR was created.

---

### User Story 4 - Reuse interval structures via a template library (Priority: P4)

A coach saves an interval structure as a reusable template, tagged by age band, mesocycle phase, and proximity to competition, and later attaches that same template to a different session instead of rebuilding it from scratch.

**Why this priority**: A pure efficiency gain on top of User Story 1 — valuable but not required to prove or use the core value proposition (matching) or the instructivo. Ships last without blocking anything else.

**Independent Test**: Can be fully tested by saving a structure from one session as a tagged template, then attaching that template to a second, different session, and confirming the second session's structure matches the template's blocks.

**Acceptance Scenarios**:

1. **Given** a coach has built an interval structure for a session, **When** they choose to save it as a template, **Then** they can tag it with an age band, a mesocycle phase, and a proximity-to-competition label, and it appears in the template library.
2. **Given** the template library has saved templates, **When** a coach is building a structure for a different session, **Then** they can browse/filter templates by tag and attach one, populating the new session's structure with a copy of the template's blocks.
3. **Given** a template has already been attached to one or more sessions, **When** the coach later edits or deletes the template itself, **Then** the sessions that already used it keep their own independent copy of the structure, unaffected by the change.

---

### Edge Cases

- What happens when a session with an interval structure never gets a Strava activity linked to it? The detail view/matching simply shows a "no linked activity yet" state — no error, no fallback auto-report (that is out of scope for v1).
- What happens when the coach tries to attach a Z3+ template to a 10-12 category session? The same hard-block rule from User Story 1 applies at attach time, not just at manual-build time.
- What happens when a coach recalculates a comparison for an activity whose laps changed (e.g., re-synced from Strava)? The recalculation reflects the latest persisted laps at the time it's triggered.
- What happens if a coach deletes an interval structure that already has a computed plan-vs-actual comparison? The comparison and its underlying persisted laps are not deleted implicitly; behavior for orphaned comparisons is resolved during planning, not user-facing in this spec.
- What happens when the athlete's linked Strava activity has zero laps recorded? The comparison shows all planned blocks as unmatched, and the view says so explicitly rather than appearing broken or empty by mistake.
- What happens when a coach requests an instructivo for a session that has no interval structure yet? The option is not available/is disabled until a structure exists.
- What happens when a coach tries to set a cadence target below 60 rpm on a template intended for a 13-15 athlete? The same minimum-cadence validation from User Story 1 applies regardless of category — there is no age band where sub-60 rpm is ever allowed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow a coach to create an interval structure as an entity attached to exactly one training session, distinct from the session's own wizard fields — following the same "attached block" pattern already used for technical-skill and strength blocks.
- **FR-002**: An interval structure MUST consist of an ordered sequence of blocks, each with a type (warmup, work, recovery, cooldown), a duration, a target heart-rate zone (Z1-Z5), and a target cadence (rpm).
- **FR-003**: System MUST support repeatable block groups (e.g., a work+recovery pair repeated N times) so the coach does not have to duplicate each repetition manually.
- **FR-004**: System MUST reject any cadence target below 60 rpm on any block, in any interval structure or template, regardless of the athlete's age category.
- **FR-005**: System MUST NOT offer a power/wattage-based target option for athletes under 13 years old — only zone- and cadence-based targets are available for that age group.
- **FR-006**: System MUST prevent saving any block at Z3 intensity or higher on an interval structure or template attached to a 10-12 category session (hard block, no override).
- **FR-007**: For interval structures containing only sub-Z3 blocks attached to a 10-12 category session, system MUST require the coach to explicitly confirm before saving, and MUST record that confirmation for later reference.
- **FR-008**: System MUST allow a coach to save an interval structure as a reusable template, tagged with an age band, a mesocycle phase, and a proximity-to-competition label.
- **FR-009**: System MUST allow a coach to attach an existing template to a different session, producing an independent copy of the template's blocks for that session (subsequent edits to either do not affect the other).
- **FR-010**: System MUST generate a downloadable PDF instructivo from a session's interval structure, containing brand-specific step-by-step instructions for manually configuring the equivalent program on an iGPSport, Magene, or Garmin device, selected by the coach at generation time.
- **FR-011**: System MUST make the instructivo available only via manual download by the coach in v1 — no automatic email delivery and no public/QR-accessible page.
- **FR-012**: System MUST persist, for each Strava activity already synced and linked to a session (per existing feature 025 linking), its laps — duration, average heart rate, and average speed/pace — without storing GPS coordinates, route polylines, or map data.
- **FR-013**: System MUST NOT persist or expose real cadence data at the lap level in v1.
- **FR-014**: When a Strava activity is linked to a session that has an interval structure, system MUST automatically compute a plan-vs-actual comparison, matching persisted laps to planned blocks in sequence with a reasonable duration tolerance, without requiring coach action.
- **FR-015**: System MUST allow the coach to manually trigger a recalculation of an existing plan-vs-actual comparison at any time (e.g., after editing the structure or after the linked activity's laps change).
- **FR-016**: System MUST handle a mismatch between the number of actual laps and planned blocks — fewer laps (blocks flagged as not completed) or more laps (extra laps flagged as unmatched) — without erroring.
- **FR-017**: System MUST present a detail view showing, for a linked activity, each planned block paired with its matched lap (or its unmatched status) and a per-block compliance indicator.
- **FR-018**: System MUST restrict visibility of the plan-vs-actual comparison, the detail view, and the underlying persisted laps to coach/admin roles only — parent and athlete accounts MUST NOT have access to this data in v1.
- **FR-019**: System MUST NOT provide any self-report/manual-completion fallback for athletes without a linked Strava activity in v1 — sessions without a linked activity simply show no comparison.

### Key Entities *(include if feature involves data)*

- **Interval Structure**: An ordered, coach-authored plan of blocks attached to exactly one training session; the source of truth for both the parent instructivo and the planned side of the matching comparison.
- **Interval Block**: A single step within a structure (or template) — type, duration, target heart-rate zone, target cadence; blocks can be organized into repeatable groups.
- **Interval Template**: A reusable, saved interval structure not tied to any specific session, tagged by age band, mesocycle phase, and proximity to competition; cloned into a session's own structure when attached.
- **Strava Activity Lap**: A persisted segment of a synced, linked Strava activity — duration, average heart rate, average speed/pace only; never GPS, polyline, or map data.
- **Plan-vs-Actual Match**: The computed correspondence between a session's interval structure and its linked activity's laps, including per-block compliance status and unmatched blocks/laps.
- **Parent Instructivo**: A generated PDF artifact derived from an interval structure for a specific device brand, intended for manual download and sharing by the coach.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can design a complete interval structure (warmup, at least one repeated work/recovery block group, and cooldown) for a session in under 5 minutes.
- **SC-002**: 100% of save attempts for interval structures or templates containing a Z3+ block on a 10-12 category session are blocked, with zero exceptions observed in testing.
- **SC-003**: 100% of save attempts for a cadence target below 60 rpm are blocked, across every age category, with zero exceptions observed in testing.
- **SC-004**: Once a linked Strava activity's laps are available in the system, the plan-vs-actual comparison for that session is computed and visible to the coach with no manual action required, and the coach can trigger a manual recalculation that reflects changes within the same session.
- **SC-005**: A coach can generate and download a parent instructivo PDF for any interval structure in under 1 minute.
- **SC-006**: A coach who starts a new interval structure from a saved template completes it in noticeably less time than building an equivalent structure from scratch (baseline: SC-001), verified through side-by-side timing during usability testing.
- **SC-007**: Zero instances of GPS coordinates, route polylines, or map data appear anywhere in the persisted laps data, the plan-vs-actual comparison, or the generated instructivo, across an audit of the feature's outputs.
- **SC-008**: Parent and athlete accounts have zero successful access attempts to the plan-vs-actual comparison, the activity detail view, or the underlying laps data, verified via access-control testing.

## Assumptions

- Interval structures use heart-rate zone and cadence as the only quantitative targets in v1; RPE is not part of the planned structure itself (the RPE-vs-plan delta comparison is explicitly deferred to v2), consistent with the club's "RPE primary, HR secondary" principle.
- Instructivo content covers exactly three device brands in v1 — iGPSport, Magene, and Garmin — matching the devices already in use by club families; other brands are out of scope.
- Strava activity syncing and the existing coach-gated manual linking of an activity to a session (feature 025) are prerequisites this feature builds on, not something this feature re-implements.
- "Manual recalculation" reuses the same automatic matching logic on demand; there is no separate manual override to hand-reassign an individual lap to a different block in v1.
- Templates are copy-on-attach: attaching a template clones its blocks into the session's own structure, so later edits or deletion of the template do not retroactively change sessions that already used it.
- The existing coach/admin vs. parent/athlete role-based access control is reused to gate visibility of the detail view and comparison data — no new permission model is introduced.
- Athletes and parents without a linked Strava activity simply see no plan-vs-actual comparison for that session in v1; this is an accepted gap, not an error state, and is the reason the auto-report fallback is explicitly scoped to v2.
