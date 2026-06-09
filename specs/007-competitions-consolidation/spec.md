# Feature Specification: Unified Competitions Module

**Feature Branch**: `claude/race-competition-consolidation-dqRZv`

**Created**: 2026-06-08

**Status**: Draft

**Input**: User description: "Consolidate the two overlapping race areas (the /competitions CRUD module and the /coach/race-analysis AI analysis module) into ONE coherent Competitions module, AND build the core capabilities that were designed but never implemented: view per-event results and season points standings (club highlighted), reload/fix results via confirmable diff, associate competitions with club athletes (auto-match + confirm/fix + manual roster), bidirectional 1:1 calendar sync, and integrated AI insights (round/athlete/club/season, coach/admin only)." Full brief: `docs/12-competitions-unification/feature-brief.md`; approved architecture PRD: `docs/12-competitions-unification/workflow.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See a competition's results and the season standings (Priority: P1)

As a coach, after a Copa Valle round has been imported, I open that competition and immediately see the full finishing order for the round and the season's cumulative points standings, with my club's athletes clearly highlighted — without leaving the Competitions area.

**Why this priority**: This is the single most valuable missing capability. Results are imported today but there is no way to view them in the app — the results area is an empty placeholder. Delivering this alone turns the module from "data goes in" into "data is useful."

**Independent Test**: Import a round that has both a results PDF and a general-standings PDF, open the competition, and confirm the per-event finishing table and the season standings table both render with correct data and the club's athletes visually distinguished. Fully testable without any other story.

**Acceptance Scenarios**:

1. **Given** a competition with imported event results, **When** the coach opens its results view, **Then** a finishing-order table is shown with position, rider name, club, category, and time/gap, sortable/filterable by category.
2. **Given** a competition whose season has imported general standings, **When** the coach opens the standings view, **Then** the cumulative points classification is shown ranked by points.
3. **Given** results or standings include the coach's club athletes, **When** either table renders, **Then** those rows are visually highlighted and can be filtered to "our club only."
4. **Given** a competition with no imported results yet, **When** the coach opens the results view, **Then** a clear empty state with a call-to-action to import is shown (no error, no blank screen).
5. **Given** a parent viewing a competition, **When** they open results, **Then** they see only their own child's row/result and no other minor's data.

---

### User Story 2 - One Competitions module, one place to work (Priority: P1)

As a coach, I have a single "Competencias" entry in the navigation that is the only place for everything about races: planning, importing, viewing, fixing, athlete association, calendar, and AI insights. The previously separate AI-analysis area no longer exists as its own destination.

**Why this priority**: The explicit headline request — "we have two modules, I want one." A split mental model and duplicate navigation is the core pain. Removing the second destination (while keeping its capabilities) is foundational to every other story feeling coherent.

**Independent Test**: Navigate the entire app and confirm there is exactly one race/competition entry point, that AI analysis is reached only from within it, and that previously published deep links (e.g., from emails) still resolve to the right place during the transition.

**Acceptance Scenarios**:

1. **Given** the app navigation, **When** the coach looks for race/competition features, **Then** there is exactly one entry point and no duplicate or orphaned race pages.
2. **Given** an old deep link to the former AI-analysis destination, **When** it is opened during the transition period, **Then** the user is redirected to the equivalent location inside the unified module.
3. **Given** the transition period has ended, **When** an old link is opened, **Then** the user receives a clear "moved" response rather than a broken page.
4. **Given** a parent, **When** they attempt to reach any cross-round or club-wide analysis location, **Then** access is denied (403) and no other athletes' data is exposed.

---

### User Story 3 - Connect competition results to my club's athletes (Priority: P2)

As a coach, I can reliably tie the people in imported results to my actual club athletes through three complementary means: automatic matching during import, a review screen to confirm or correct ambiguous/unmatched cases, and a manual roster where I declare which club athletes were entered in a competition (even before results exist).

**Why this priority**: Accurate athlete association is what makes results and insights trustworthy and per-athlete views possible. It builds directly on Stories 1 and 2.

**Independent Test**: Import a round, confirm high-confidence riders auto-link, resolve an ambiguous match and an unmatched rival in the review screen, and separately build a call-up roster for an upcoming round that has no results yet; verify the roster reconciles with results once imported.

**Acceptance Scenarios**:

1. **Given** an import in progress, **When** a parsed rider strongly matches a club athlete, **Then** the link is proposed automatically and shown as confirmed.
2. **Given** an ambiguous or unmatched rider, **When** the coach reviews matches, **Then** they can link it to the correct athlete or mark it as a rival/other-club entry, and the decision persists.
3. **Given** a previously committed import, **When** the coach later opens the athletes/linking view, **Then** they can still link or unlink competitors retroactively.
4. **Given** a planned competition with no results, **When** the coach builds a call-up roster, **Then** they can add/remove club athletes, and this roster is independent of imported results.
5. **Given** a roster exists and results are later imported, **When** the coach views the competition, **Then** roster entries and result-linked athletes are reconciled and discrepancies (called-up but no result, or result but not called-up) are visible.

---

### User Story 4 - Fix a results mistake by re-importing (Priority: P2)

As a coach, when I receive a corrected official PDF for a round I already imported, I re-upload it, see exactly what will change as a confirmable diff, and apply the correction safely — and the system flags any analyses or family communications that the correction makes outdated.

**Why this priority**: Official results get corrected; without a safe, transparent re-import the data silently rots or requires destructive re-entry. Depends on results existing (Stories 1/3).

**Independent Test**: Re-upload a modified results file for an already-imported round, review a diff grouped by change type, confirm it, and verify the data updates transactionally while affected AI runs/newsletters are marked outdated (not auto-resent).

**Acceptance Scenarios**:

1. **Given** a round already imported, **When** the coach uploads a different file for the same round, **Then** the system recognizes it as a revision (not an error) and computes a diff.
2. **Given** a computed diff, **When** the coach reviews it, **Then** changes are grouped (position / time / gap / category / added / removed) and require explicit confirmation before applying.
3. **Given** deletions exist in the diff, **When** the coach confirms, **Then** a reason must be chosen from a fixed catalog (no free text) and an audit record is kept.
4. **Given** a confirmed revision, **When** it is applied, **Then** it is atomic (all-or-nothing) and re-uploading the identical file is a no-op.
5. **Given** a revision changes data feeding an AI analysis or an already-sent monthly newsletter, **When** it is applied, **Then** those artifacts are marked outdated and nothing is automatically re-run or resent.

---

### User Story 5 - Keep competitions and the calendar in sync (Priority: P3)

As a coach, creating a competition can create or link its calendar event automatically, and editing key details on either side keeps the other in step, so the season calendar and the competitions list never disagree.

**Why this priority**: Reduces double data-entry and prevents drift, but the module is usable without it.

**Independent Test**: Create a competition with the "add to calendar" option enabled and confirm a linked 1:1 calendar event appears; edit the competition's date/venue and confirm the calendar event updates; from a calendar race event, link/create the corresponding competition.

**Acceptance Scenarios**:

1. **Given** the create-competition flow, **When** the coach keeps the (default-on) "create calendar event" option, **Then** a single linked calendar event is created.
2. **Given** a competition linked to a calendar event, **When** the coach changes its date, name, or venue, **Then** the linked calendar event reflects the change.
3. **Given** a calendar race event, **When** the coach associates it with a competition, **Then** a strict 1:1 link is established (a round links to at most one calendar event).
4. **Given** the opt-out was chosen, **When** the competition is created, **Then** no calendar event is created and none is implied later unless the coach links one.

---

### User Story 6 - Read AI insights inside the competition module (Priority: P3)

As a coach, I can read AI-generated insights for a single round, for an individual athlete over time, for the club/group, and across a whole season — all reachable from within the Competitions module — while parents are blocked and no minor's name ever appears in generated text.

**Why this priority**: Valuable analysis, but it surfaces/relocates existing capability rather than creating net-new data; lowest risk to defer.

**Independent Test**: From a competition, open round insights; from the module, open per-athlete, club, and season views; confirm a parent receives 403 and generated narratives contain no minor names.

**Acceptance Scenarios**:

1. **Given** a coach viewing a competition, **When** they open its insights, **Then** round-level AI insights for that competition are shown.
2. **Given** a coach in the module, **When** they open cross-round views, **Then** per-athlete, club, and season analyses are available without leaving the module.
3. **Given** any AI-generated narrative, **When** it is displayed, **Then** it contains no minor athlete names (anonymized wording only).
4. **Given** a parent, **When** they attempt to open any insights location, **Then** access is denied (403).

---

### Edge Cases

- A competition is created but never imported (planned-only): results/standings show empty states; roster and calendar still work.
- A round's results are imported but the season general standings are not (or vice-versa): each view independently shows data-or-empty, never an error.
- Imported results contain riders not in any club, duplicate names across categories, or a club athlete entered in an unexpected category: matching must not mislink; ambiguity routes to the review screen.
- A re-import that results in no changes vs. the current data: treated as a no-op, no spurious revision.
- A competition is cancelled after a calendar event was created: the linked calendar event reflects the cancellation rather than going stale.
- Deleting a competition that has imported results, a roster, linked calendar event, or AI runs: blocked or guarded with a clear explanation of dependents (destructive deletion is admin-only).
- Parent opens a competition where their child did not participate: no rows shown, no leakage of other minors.
- Concurrent edits (coach edits competition while a calendar sync is in flight): the competition remains the source of truth and the calendar reconciles to it.
- Large results sets (full Copa Valle field across 26 categories): tables and standings must remain responsive on mobile/tablet.

## Requirements *(mandatory)*

### Functional Requirements

**Consolidation & navigation**

- **FR-001**: The system MUST present a single Competitions module as the only entry point for all race/competition features (planning, import, viewing, fixing, athlete association, calendar, insights).
- **FR-002**: The system MUST absorb the former standalone AI-analysis destination so that AI insights are reachable only from within the Competitions module.
- **FR-003**: The system MUST redirect previously published links to former race/analysis destinations to their new equivalents during a transition period, then return a clear "moved/gone" response afterward, without breaking external links mid-transition.
- **FR-004**: The system MUST NOT present duplicate or orphaned race/competition pages once consolidation is complete.

**Competition lifecycle (CRUD)**

- **FR-005**: Coaches and admins MUST be able to create a competition before any results file exists, capturing series, round number, date, venue, championship flag, status (scheduled/completed/cancelled), and optional race conditions.
- **FR-006**: Coaches and admins MUST be able to edit a competition's metadata and conditions at any time.
- **FR-007**: Admins MUST be able to delete a competition, with the action guarded when dependents (results, roster, linked calendar event, AI runs) exist.
- **FR-008**: The system MUST provide a filterable list of competitions (by season, status, championship, venue, has-results, upcoming) usable on both desktop and mobile.

**Load & view results**

- **FR-009**: Coaches and admins MUST be able to import a round's official event results and the season's general points standings via a guided parse → preview → confirm flow that is transactional and idempotent.
- **FR-010**: The system MUST display a per-event finishing-order table (position, rider, club, category, time/gap) filterable by category.
- **FR-011**: The system MUST display the season general points standings ranked by cumulative points.
- **FR-012**: The system MUST visually highlight the coach's own club athletes within both the results table and the standings, and allow filtering to club-only.
- **FR-013**: The system MUST show clear empty states (with import call-to-action) when results or standings are not yet available, and never expose raw errors for the absent-data case.

**Reload / fix results**

- **FR-014**: The system MUST detect a re-uploaded file for an already-imported round as a revision (not an error) and compute a diff against current data.
- **FR-015**: The system MUST present the diff grouped by change type (position / time / gap / category / added / removed) and require explicit confirmation before applying.
- **FR-016**: The system MUST require a reason from a fixed catalog (no free text) when a revision includes deletions, and retain an audit trail of revisions.
- **FR-017**: The system MUST apply confirmed revisions atomically and treat re-uploading an identical file as a no-op.
- **FR-018**: When a revision changes data feeding AI analyses or already-sent family communications, the system MUST mark those artifacts as outdated and MUST NOT automatically re-run analyses or resend communications.

**Athlete association**

- **FR-019**: During import, the system MUST automatically propose links between parsed riders and club athletes for high-confidence matches.
- **FR-020**: The system MUST provide a review step to confirm or correct ambiguous/unmatched riders, including marking a rider as rival/other-club, with decisions persisted.
- **FR-021**: The system MUST allow linking/unlinking competitors to club athletes retroactively after an import is committed.
- **FR-022**: Coaches and admins MUST be able to maintain a manual call-up roster of club athletes for a competition, independent of imported results and usable before results exist.
- **FR-023**: The system MUST reconcile the roster with imported results and surface discrepancies (called-up without a result; result without a call-up).

**Calendar sync**

- **FR-024**: When creating a competition, the system MUST offer a default-on option to create a linked calendar event, with a visible opt-out.
- **FR-025**: The system MUST maintain a strict 1:1 link between a competition and its calendar event, in either creation direction.
- **FR-026**: Changes to a competition's date, name, venue, or cancellation status MUST propagate to the linked calendar event, with the competition as the source of truth.

**AI insights**

- **FR-027**: The system MUST make AI insights available within the module at round, per-athlete, club, and season scopes.
- **FR-028**: AI-generated narratives MUST NOT contain minor athlete names (anonymized wording only).
- **FR-029**: AI re-execution after a correction MUST be manual and coach-initiated (no automatic or scheduled re-runs).

**Access control & privacy**

- **FR-030**: Coaches and admins MUST have full access to the module; parents MUST have read-only access scoped to their own child and MUST receive 403 on cross-round/club/season analysis and any other-athlete data.
- **FR-031**: The system MUST NOT expose minor personal data (names, dates of birth, medical details) in logs, commit artifacts, public responses, or AI prompts.

**Quality & resilience**

- **FR-032**: Every view MUST provide explicit loading, empty, and error states (no unbounded spinners or raw exceptions), and MUST surface the backend cold-start state when applicable.
- **FR-033**: The consolidation MUST be delivered incrementally in independently deployable, reversible increments (no big-bang migration), preserving existing test coverage at each step.

### Key Entities *(include if feature involves data)*

- **Competition (RaceEvent)**: A Copa Valle round — metadata (series, round number, date, venue, championship flag, status) and optional conditions; linked 1:1 to a calendar event; parent of its results and roster.
- **RaceSeries / RacePointsScheme**: Season grouping and the points rules that drive the general standings.
- **RaceCategory**: One of the 26 Copa Valle categories results are organized by.
- **Rider / RaceCompetitor**: A person appearing in results; may be linked to a club Athlete or marked as rival/other-club.
- **RaceResult**: One rider's outcome in one competition (position, time, gap, points, category).
- **SeasonStanding**: Cumulative points classification for a series/season, derived from results and the points scheme.
- **Roster / Call-up association** *(new)*: Which club athletes were entered for a competition, independent of results.
- **RaceImport / RaceResultRevision**: Ingestion records providing idempotency, audit trail, and revision diffs.
- **AI analysis run**: An analysis anchored to a round/athlete/club/season, carrying an outdated/stale marker.
- **Athlete**: Existing club athlete profile that riders/roster entries link to.
- **Calendar event**: Existing calendar entity linked 1:1 to a competition.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can complete the full lifecycle for one round — create → import event results and general standings → view both tables → correct a result → confirm the roster → see it linked on the calendar — without ever leaving the Competitions module.
- **SC-002**: The application exposes exactly one race/competition navigation entry and zero duplicate or orphaned race pages after consolidation.
- **SC-003**: Per-event results and the season general standings are viewable in-app for any imported round, with club athletes highlighted — a capability that does not exist today.
- **SC-004**: 100% of previously published deep links to former race/analysis destinations resolve correctly throughout the transition period (no broken external links).
- **SC-005**: A coach can correct an imported round via re-upload and confirmable diff in under 3 minutes, with the change applied atomically and downstream artifacts marked outdated.
- **SC-006**: A parent can never view another minor's results, roster, or analysis, and no AI-generated narrative contains a minor's name (verified by privacy invariants).
- **SC-007**: Results and standings tables for a full-field round (all 26 categories) remain responsive and usable on a mid-tier mobile device.
- **SC-008**: All pre-existing race/competition automated tests continue to pass, and the new capabilities are covered by tests including privacy and accessibility checks.

## Assumptions

- The existing PDF/CSV ingestion pipeline (parse/dry-run/commit, fuzzy matching, SHA256 idempotency, revision detection) is reused as the foundation; this feature surfaces and completes it rather than replacing it.
- The 26-category model, points schemes, and Copa Valle 2026 calendar already seeded remain authoritative.
- The data entities listed above largely exist in the current schema; the call-up roster association is the primary net-new data, and an outdated/stale marker on AI runs may be added.
- "Our club" highlighting refers to Club Deportivo Trocha y Ruta athletes resolved via athlete↔rider links.
- The transition period for redirects spans one release cycle, consistent with the approved unification PRD.
- Product-facing copy is español neutro (Colombia); the module targets coach use on a field tablet and parent use on intermittent mobile connectivity.
- Federation registration and event-day logistics are handled by other modules and are out of scope here.
