# Feature Specification: Multi-coach governance — change log, attribution and per-coach reports

**Feature Branch**: `feat/041-multi-coach-governance`

**Created**: 2026-09-09

**Status**: Draft

**Input**: User description: "Multi-coach governance: change log (audit trail), attribution of who did what, and club-wide vs per-coach reports." Club Deportivo Trocha y Ruta is about to onboard a second coach who will manage the club the same way the current coach does. The owner resolved the six design decisions on 2026-09-08 (shared club scope with attribution; log covers writes plus document exports/sends; co-coached sessions; minimal staff admin screen; 24-month retention with explicit manual purge; newsletter note author visible to coaches only). The readiness audit that motivated this feature is summarised under Assumptions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every change has a name on it (Priority: P1)

Two coaches share the same club. Whenever either of them (or an administrator) creates, edits, approves, sends, cancels, archives or deletes something — an athlete profile, a measurement, a training session, an attendance or rubric entry, a calendar event, a monthly report, a family newsletter, an AI analysis run, a race import, a staff account — the system records who did it, when, on which record, and which fields changed. Exporting or sending a document that contains a minor's data (a growth or anthropometry PDF, a medical-authorisation DOCX, a family newsletter) is recorded the same way. Plain reads of an athlete page are not recorded. A coach or administrator can open a "recent history" view for the club, filter it by person, period, record type or athlete, and read entries in plain Spanish ("Ana Coach aprobó el informe mensual de marzo"). Parents never see this view. No entry ever contains a minor's name, birth date, measurement values, medical or narrative content — only identifiers, field names and a reason chosen from a fixed list.

**Why this priority**: Today nothing outside the race-results domain records who edited or deleted anything. With one coach the author was implicit; with two it is unknowable, and the club cannot answer a family's "who changed this?" or reconstruct what happened before a dispute. This is the foundation every other story builds on.

**Independent Test**: With two coach accounts in the same club, have coach A create a session and coach B edit and then cancel it; have the admin deactivate a parent account; have coach A download an athlete's anthropometry PDF. The club history shows five entries with the correct actor, action, record and time; filtering by coach B shows exactly two; a parent account requesting the history is refused; a scan of every entry finds no name, date of birth or free text.

**Acceptance Scenarios**:

1. **Given** two coaches in the same club, **When** coach B edits a training session created by coach A, **Then** a history entry records coach B as the actor, the action "update", the session as the record and the list of changed fields, with the time of the change.
2. **Given** any recorded write, **When** the entry is inspected, **Then** it contains only identifiers, field names, a reason from a fixed catalogue and a correlation reference; it never contains a minor's name, birth date, measurement value, medical detail, feedback text, note text or narrative block.
3. **Given** a coach downloads or sends a document containing a minor's data, **When** the download or send completes, **Then** a history entry records the actor, the document type, the athlete concerned (by identifier) and the action "export" or "send".
4. **Given** a change made by an automated process (an inbound email-status webhook, the daily activity reconciliation, a start-up backfill), **When** it writes data, **Then** the entry records the kind of automated actor instead of a person and is never attributed to the last logged-in user.
5. **Given** a single user action that changes several records at once (for example, updating a session roster), **When** the entries are listed, **Then** they share one correlation reference so the reviewer can see them as one operation.
6. **Given** a parent account, **When** it requests the club history or the history of its own child, **Then** the request is refused and nothing is revealed.
7. **Given** a coach of another club, **When** they request this club's history, **Then** the request is refused.
8. **Given** a coach filters the history by actor, record type, athlete and period, **When** the filters are applied, **Then** only matching entries are shown, newest first, with the actor's display name resolved (never a raw numeric identifier).

---

### User Story 2 - Deleting an athlete keeps the evidence (Priority: P1)

A coach removes an athlete who left the club. The athlete disappears from lists, dashboards, reports, newsletters, AI contexts and the parents' view, but the record is archived rather than destroyed: the parental-consent evidence, the measurements and the history of who did what remain available to an administrator, the removal itself is recorded with the actor and a reason, and an administrator can restore the athlete if the removal was a mistake. Deleting a coach or administrator account that has recorded activity is not possible; such accounts are deactivated instead, and their name remains readable on their past actions.

**Why this priority**: The current removal is an irreversible cascade that also destroys the parental-consent record — the very evidence Ley 1581 requires the club to keep — and leaves no trace of who did it. Any coach can trigger it in two clicks. With two coaches the chance of an accidental or contested removal doubles.

**Independent Test**: Archive an athlete as coach A. Verify the athlete is absent from the athlete list, the dashboard, the monthly report, the newsletter list, the AI athlete picker and the linked parent's "my athletes" page; verify the consent record and measurements still exist for an admin; verify the history shows the archive entry with coach A and a reason; restore as admin and verify the athlete reappears everywhere. Attempt to delete coach A's account as admin and verify it is refused with a message pointing to deactivation.

**Acceptance Scenarios**:

1. **Given** an active athlete, **When** a coach removes them and picks a reason from the fixed list, **Then** the athlete is archived (not destroyed), the removal is recorded with actor and reason, and the athlete no longer appears in any coach, parent, report, newsletter or AI surface.
2. **Given** an archived athlete, **When** an administrator views the archive, **Then** the parental-consent evidence, measurement history and change history are intact and readable.
3. **Given** an archived athlete, **When** an administrator restores them, **Then** the athlete reappears in every surface and the restoration is recorded.
4. **Given** an athlete with attendance, event or race history whose removal used to fail half-way with an opaque error, **When** a coach removes them, **Then** the archive succeeds cleanly and the history is preserved.
5. **Given** a parent account linked only to an archived athlete, **When** the parent logs in, **Then** they see a calm "no athletes linked" state, not the archived athlete and not an error.
6. **Given** a coach or administrator account with recorded activity, **When** an administrator tries to delete it, **Then** the deletion is refused with guidance to deactivate; **When** they deactivate it, **Then** the person can no longer sign in and their name still appears on their past entries.
7. **Given** a parent account is removed by an administrator, **When** the removal completes, **Then** it is recorded with the actor, and no other record loses its "created by" attribution as a side effect.

---

### User Story 3 - The second coach is onboarded from the app (Priority: P1)

An administrator opens a "Personal del club" screen, creates the new coach with name, email and club (club is mandatory), and the new coach receives the standard "set your password" email. From their first sign-in the new coach sees exactly what the existing coach sees: every athlete, session, event, report and result of the club. The administrator can list staff (active and inactive), see when each account was created and by whom, and deactivate an account. A coach cannot create, edit or deactivate another coach or an administrator.

**Why this priority**: There is no user-management screen today; a coach can only be created by hand against the API, and omitting the club leaves the new coach signed in but staring at an empty app with no error. With staff rotation this will happen every time.

**Independent Test**: As admin, create a coach from the screen without choosing a club and verify the form refuses; choose the club and verify the coach appears in the staff list as active with "created by admin" and today's date; sign in as the new coach and verify the athlete list, session list and calendar show the club's data; deactivate the coach as admin and verify they can no longer sign in; sign in as the original coach and verify the staff screen is not reachable.

**Acceptance Scenarios**:

1. **Given** an administrator on the staff screen, **When** they submit a new coach without a club, **Then** the form shows an inline error and nothing is created.
2. **Given** an administrator submits a valid new coach, **When** the account is created, **Then** it is active, belongs to the chosen club with the coach role, the creation is recorded with the administrator as actor, and the new coach receives the existing set-password email.
3. **Given** the new coach signs in for the first time, **When** they open athletes, sessions, calendar, reports and competitions, **Then** they see the same club data the existing coach sees, with no empty-state caused by a missing club membership.
4. **Given** the staff list, **When** an administrator views it, **Then** each staff member shows name, role, active state, creation date and creator, and the list can be filtered by active state.
5. **Given** a coach account, **When** the coach tries to reach the staff screen or its underlying actions, **Then** access is refused and the navigation entry is not shown.
6. **Given** an administrator deactivates a coach, **When** the coach next tries to sign in, **Then** sign-in is refused with the existing "account inactive" message, and the deactivation is recorded with actor and time.
7. **Given** a club membership whose role does not match the account's role, **When** an administrator tries to save it, **Then** the save is refused with a clear message; memberships are always created consistent with the account role.

---

### User Story 4 - Sessions can be co-coached, and families hear the right name (Priority: P2)

When a coach plans a training session, the session carries the set of coaches who will lead it — by default the coach creating it, with the option to add the other coach. Both can be on the same session. When a session is edited, executed or cancelled, the notification to families names the coach who actually performed the action, not the one who originally planned it. Attendance, effort and attitude ratings and individual feedback for each athlete record which coach entered them, and editing another coach's entry keeps both names (original recorder and last editor). Removing an athlete from a session roster no longer destroys any rating or feedback already entered for them; it is archived with the removal recorded.

**Why this priority**: Today a session only knows who pressed "create". If coach B cancels a session coach A planned, the cancellation email tells the families that coach A cancelled it. Ratings and feedback about a minor have no author at all, and removing an athlete from a roster silently deletes them.

**Independent Test**: Coach A creates a session and adds coach B as co-coach; verify both names show on the session and in the family invitation. Coach B cancels the session; verify the cancellation email names coach B. Coach A records attendance and feedback for an athlete, coach B edits it; verify the entry shows "recorded by A, last edited by B". Remove that athlete from the roster and verify the feedback is still visible to an admin in the archived state and that the removal appears in the history.

**Acceptance Scenarios**:

1. **Given** a coach creates a session, **When** the session is saved, **Then** it lists the creating coach as a session coach by default and the wizard offers the other active coaches of the club to add.
2. **Given** a session with two coaches, **When** families receive the invitation, update or cancellation, **Then** the message lists both coaches as leading the session and names the acting coach for the change ("El entrenador B ha cancelado…").
3. **Given** a session, **When** a coach tries to remove the last remaining session coach, **Then** the removal is refused; a session always has at least one coach.
4. **Given** a coach records attendance, ratings or feedback for an athlete, **When** the entry is saved, **Then** it records that coach as the recorder; **When** the other coach edits it, **Then** the entry shows the original recorder and the last editor with the time.
5. **Given** an athlete is removed from a session roster after ratings or feedback were entered, **When** the roster is saved, **Then** the entry is archived rather than destroyed, the removal is recorded, and an administrator can still read the archived entry.
6. **Given** a session is marked as executed, **When** the execution is saved, **Then** the history records which coach executed it.
7. **Given** a session listing or a calendar listing, **When** a coach filters by coach, **Then** only sessions where that coach is a session coach (or events that coach created) are shown.

---

### User Story 5 - Two coaches never silently overwrite each other (Priority: P2)

Coach A drafts the narrative of an athlete's monthly family newsletter and writes the coach's note. Coach B opens the same newsletter later and edits another part. Coach B's save keeps coach A's work; if both edit the same newsletter at the same time, the second save is refused with a clear conflict message and the option to reload before retrying. The coach's note remembers who wrote it and when, visible to coaches only; families keep seeing the club's institutional voice. A monthly report that has been approved keeps the record of who approved it and when even if the report is later regenerated; regeneration is itself recorded.

**Why this priority**: Today the newsletter editor sends the whole draft and the last save wins, so the second coach's save discards the first coach's edits without any warning; the coach's note has no author; and regenerating a monthly report overwrites who generated it and resets the approval, destroying the evidence that the previous version was approved.

**Independent Test**: Open the same newsletter as coach A and coach B in two browsers. Coach A saves a note; coach B, without reloading, saves a narrative edit and gets a conflict message; coach B reloads, sees A's note with A's name and timestamp, edits and saves successfully. Approve a monthly report as coach A, regenerate it as coach B; verify the report shows "generated by B" and still shows "previously approved by A on <date>" and that both actions appear in the history. Open the family view of the newsletter and verify no coach name appears.

**Acceptance Scenarios**:

1. **Given** two coaches editing the same newsletter, **When** the second saves over a version they have not seen, **Then** the save is refused with a conflict message and a reload action, and no edit is lost.
2. **Given** a coach writes or edits the coach's note, **When** it is saved, **Then** the note records author and time, shown to coaches on the studio and never to families.
3. **Given** an approved newsletter, **When** any coach edits it, **Then** the approval is cleared as today, and the history records who edited it and that the approval was cleared.
4. **Given** an approved monthly report, **When** a coach regenerates it, **Then** the report shows who generated the new version and retains who approved the previous version and when; both events are in the history.
5. **Given** a newsletter already sent to families, **When** a coach tries to edit it, **Then** the edit is refused as today (sent content is immutable).

---

### User Story 6 - Either coach can act on the club's AI runs and imports (Priority: P2)

The club has one scope rule: anything of the club can be seen and acted on by any coach of the club. Coach A launches a race-analysis run that stops to wait for a human decision and then goes on holiday; coach B opens the run and takes the decision. Coach B can resume a race-import wizard coach A started. Every run and import shows who launched it and, for decisions, who decided. On the AI administration page the trailing-30-day spend is shown per coach as well as in total, and when a run is blocked because the club's budget is exhausted the message says so and names the period.

**Why this priority**: Today AI runs and import parses are the only surfaces that are locked to their creator (the other coach gets "no access") while their listings are not filtered, so a run can be stuck waiting for a decision only its absent author can take. The AI budget is club-wide, so one coach can exhaust it and block the other without anyone noticing.

**Independent Test**: Coach A launches a run that reaches the "awaiting decision" state; coach B opens it, approves it and sees it complete; the run shows "launched by A, decided by B". Coach A starts an import wizard; coach B opens the same parse and commits it. On the AI page, spend for the last 30 days is split by coach and sums to the total. A coach of another club still gets "no access" to the run.

**Acceptance Scenarios**:

1. **Given** a run launched by coach A awaiting a human decision, **When** coach B of the same club opens it, **Then** they can read it, decide, cancel or re-execute it, and the decision records coach B.
2. **Given** an import parse started by coach A, **When** coach B opens it, **Then** they can review and commit it, and the commit records coach B while the parse keeps coach A as importer.
3. **Given** a coach of a different club, **When** they request the run or the parse, **Then** access is refused.
4. **Given** the AI administration page, **When** an administrator or coach views it, **Then** the trailing-30-day spend is shown per coach and in total, and the per-coach amounts sum to the total.
5. **Given** the club budget is exhausted, **When** a coach tries to launch a run, **Then** the refusal message states the budget period and that in-flight runs will finish.

---

### User Story 7 - Club-wide and per-coach reports (Priority: P3)

The club-wide reports the coach uses today — monthly technical report, dashboard summary, race insights, season panorama — stay exactly as they are and keep the club's institutional signature. In addition, a coach or administrator can open a per-coach activity view for any period: sessions each coach led or co-led (planned, executed, cancelled), attendance and feedback entries each recorded, AI runs each launched, race-results operations each performed (imports, revisions, competitor links), documents each approved or sent, and a link to that coach's entries in the history. Wherever the app shows "created by", "evaluated by", "generated by" or "approved by", it shows the person's name instead of a numeric identifier. The per-coach view is an internal management view and is never delivered to families.

**Why this priority**: Every report today aggregates by club only; no listing can be filtered by author; and the one place that shows an author prints a raw numeric identifier. With two coaches the owner needs to see each person's contribution without losing the club-wide picture.

**Independent Test**: Over a test month, coach A leads 3 sessions and co-leads 1, coach B leads 2 and co-leads the same 1, coach A launches 2 AI runs, coach B approves 1 monthly report. The per-coach view shows A: 4 sessions, 2 runs, 0 approvals; B: 3 sessions, 0 runs, 1 approval. The club-wide monthly report is unchanged from before the feature (same sections, same signature). Every "created by" surface shows a name.

**Acceptance Scenarios**:

1. **Given** a period and a coach, **When** the per-coach view is opened, **Then** it shows sessions led or co-led by state, entries recorded, runs launched, results operations performed and documents approved or sent, each count consistent with the underlying records.
2. **Given** a co-coached session, **When** the per-coach view is computed, **Then** the session counts for each of its coaches.
3. **Given** the club-wide reports, **When** compared before and after the feature, **Then** their content, filters and institutional signature are unchanged.
4. **Given** any surface that displays an author, **When** it renders, **Then** it shows the person's display name; a deactivated person's name still resolves.
5. **Given** a parent account, **When** it requests the per-coach view, **Then** the request is refused.
6. **Given** an athlete's detail page viewed by a coach or administrator, **When** the "historial" section is opened, **Then** it lists who changed that athlete's records, when and what kind of change, newest first, with the same privacy rules as the club history.

---

### User Story 8 - The history is kept for two seasons and purged deliberately (Priority: P3)

History entries are kept for 24 months. Nothing purges them automatically inside the app. An administrator runs a documented procedure that first previews how many entries older than 24 months would be removed and then, on explicit confirmation, removes them and records the purge itself as a history entry. The procedure can be scheduled to run monthly from outside the app, with the preview result visible before any removal.

**Why this priority**: The system has no general retention policy today. Without one the history grows indefinitely and there is no criterion for answering a suppression request; without an explicit, previewed procedure a purge could silently erase evidence.

**Independent Test**: Seed entries dated 25 and 23 months ago. Run the preview: it reports one entry to remove and removes nothing. Run with confirmation: the 25-month entry is gone, the 23-month entry remains, and a new entry records the purge with the count.

**Acceptance Scenarios**:

1. **Given** entries older and younger than 24 months, **When** the preview runs, **Then** it reports the count to remove and changes nothing.
2. **Given** the same entries, **When** the purge runs with explicit confirmation, **Then** only entries older than 24 months are removed and the purge is recorded with the count and the actor kind.
3. **Given** the app running normally, **When** time passes, **Then** no entry is ever removed or altered by the app itself.

---

### Edge Cases

- A change made by an automated process (email-delivery webhook, activity reconciliation, start-up data backfill) has no signed-in person; it is recorded with its actor kind and never attributed to a person.
- A request fails after some records were written: the history entries for that request are written in the same unit of work as the data, so a failed request leaves neither the data change nor the entry.
- A coach is deactivated while they still appear as the only coach of future sessions: the sessions keep them listed (history is not rewritten) and the session list flags sessions whose only coach is inactive so the other coach can take them over.
- An administrator attempts to delete a person who authored history entries: refused; deactivation is the only path.
- Two coaches edit the same newsletter at the same time: the second save is refused with a conflict message; no edit is lost.
- A coach removes the last coach from a session: refused.
- A parent's only linked athlete is archived: the parent sees a calm "no athletes linked" state and receives no error.
- An archived athlete is referenced by a session roster, a race result or a calendar audience: those records keep the reference; the athlete is simply excluded from active surfaces and counts.
- An athlete is archived and restored several times: every archive and restore is recorded; the athlete's history remains continuous.
- The history is filtered by an athlete who has since been archived: entries are still returned to coach and admin.
- A record type is added to the app in the future without being wired to the history: an automated check fails so the omission cannot ship unnoticed.
- The purge preview is run by someone without administrator rights: refused.

## Requirements *(mandatory)*

### Functional Requirements

**Change history**

- **FR-001**: The system MUST record a history entry for every create, update, archive (soft-delete), permanent delete, restore, approve, un-approve, send, export, cancel, execute, link, unlink, role change and activation/deactivation performed on club data, in the same unit of work as the change itself.
- **FR-002**: Each entry MUST hold: the actor (person, or the kind of automated process when no person is signed in), the actor's role at the time, the action, the record type and identifier, the club, the athlete concerned when applicable, the list of changed field names, a reason chosen from a fixed catalogue when the action requires one, a correlation reference shared by all entries of the same request, and the time of the change with sub-second precision.
- **FR-003**: Entries MUST NOT contain a minor's name, birth date, sex, measurement values, medical detail, consent text, individual feedback text, coach notes, narrative blocks, AI output or any free text; only identifiers, field names and catalogue codes. Values MAY be stored only for an explicitly allow-listed set of non-sensitive fields (states, flags, dates of events, identifiers), and that allow-list MUST be covered by an automated privacy test.
- **FR-004**: Entries MUST be append-only: the application MUST never update or delete them; the only removal path is the explicit purge procedure of FR-030.
- **FR-005**: Exports and sends of documents containing a minor's data (anthropometry/growth PDF, medical-authorisation DOCX, family newsletter PDF and email, monthly report DOCX/PDF) MUST be recorded as history entries; plain page reads MUST NOT be recorded.
- **FR-006**: Administrators and coaches of the club MUST be able to list the club's history filtered by actor, period, record type and athlete, newest first, with actor names resolved; parents and coaches of other clubs MUST be refused.
- **FR-007**: The athlete detail page for coaches and administrators MUST offer a "historial" section listing the entries concerning that athlete, under the same privacy rules.
- **FR-008**: The club history MUST render each entry as a plain-Spanish sentence built from the actor name, the action and the record type, never exposing raw identifiers or field names to the reader except in an expandable detail.
- **FR-009**: An automated check MUST fail when a write operation on club data exists without a corresponding history entry, so that new record types cannot ship unaudited.

**Attribution on records**

- **FR-010**: Every club record that can be edited MUST retain who created it, who last edited it and when; records that can be archived MUST retain who archived it and when; records that can be approved MUST retain who approved it and when, and that approval evidence MUST survive later regeneration or edits (shown as "previously approved by").
- **FR-011**: Attendance, effort/attitude/technique ratings and individual feedback entries MUST record who recorded them and who last edited them.
- **FR-012**: The author and time of a newsletter coach's note MUST be stored and shown to coaches and administrators only; family-facing newsletter content MUST keep the institutional voice with no coach name.
- **FR-013**: Every surface that displays an author (created by, evaluated by, generated by, approved by, imported by) MUST show the person's display name, including for deactivated accounts, never a numeric identifier.

**Archiving instead of destroying**

- **FR-014**: Removing an athlete MUST archive the athlete rather than destroy data: the athlete MUST disappear from every coach, parent, report, newsletter, dashboard and AI surface, while parental-consent evidence, measurements, attendance, results and history remain intact and readable by administrators.
- **FR-015**: Archiving an athlete MUST require a reason from a fixed catalogue and MUST be recorded; administrators MUST be able to restore an archived athlete, and restoration MUST be recorded.
- **FR-016**: Removing an athlete from a session roster after ratings or feedback were entered MUST archive those entries rather than destroy them.
- **FR-017**: Cancelling a calendar event MUST record who cancelled it, when and the reason code; permanent deletion of a calendar event MUST be recorded with the actor.
- **FR-018**: Accounts of coaches or administrators with recorded activity MUST NOT be deletable; deactivation MUST be the only path, and deactivated names MUST remain resolvable on past entries. Removing a parent account MUST be recorded and MUST NOT clear the attribution of records that account created.

**Staff management**

- **FR-019**: Administrators MUST be able to create a coach from a staff screen with name, email and a mandatory club; the form MUST refuse submission without a club, and the created account MUST belong to the club with the coach role in the same operation.
- **FR-020**: Administrators MUST be able to list staff with name, role, active state, creation date and creator, filter by active state, and deactivate or reactivate an account; each state change MUST be recorded.
- **FR-021**: Coaches MUST NOT be able to reach the staff screen or perform staff actions; the navigation entry MUST be hidden for them.
- **FR-022**: Club memberships MUST be created consistent with the account role; a membership whose role contradicts the account role MUST be refused.
- **FR-023**: The new coach MUST receive the existing set-password email on creation; no password is ever shown or sent in clear.

**Co-coached sessions and truthful notifications**

- **FR-024**: A training session MUST carry a set of one or more session coaches, defaulting to its creator; the wizard MUST allow adding any active coach of the club and MUST refuse removing the last one.
- **FR-025**: Family notifications for session invitation, update, execution and cancellation MUST list the session coaches and name the coach who performed the change.
- **FR-026**: Session and calendar listings MUST accept a coach filter (session coaches for sessions; creator for other events).

**Concurrency**

- **FR-027**: Saving a newsletter draft over a version the coach has not seen MUST be refused with a conflict message and a reload action; no edit MAY be lost silently.

**Single scope rule for AI runs and imports**

- **FR-028**: Any coach of the club MUST be able to read, decide, cancel and re-execute a race-analysis run and to review and commit an import parse started by another coach of the same club; coaches of other clubs MUST be refused; the run MUST show who launched it and who decided.
- **FR-029**: The AI administration page MUST show trailing-30-day spend per coach and in total; the budget-exhausted refusal MUST state the period and that in-flight runs finish.

**Retention**

- **FR-030**: History entries MUST be kept for 24 months. Removal MUST only happen through an explicit, documented procedure restricted to administrators that first previews the count to remove, removes only on explicit confirmation, and records the purge as a history entry with the count. The procedure MUST be schedulable from outside the app on a monthly basis with the preview visible before removal.

**Per-coach and club-wide reporting**

- **FR-031**: Club-wide reports (monthly technical report, dashboard summary, race insights, season panorama) MUST remain unchanged in content, filters and institutional signature.
- **FR-032**: Coaches and administrators MUST be able to open a per-coach activity view for a period showing, per coach: sessions led or co-led by state, attendance/feedback entries recorded, AI runs launched, results operations performed (imports, revisions, competitor links), documents approved or sent, and a link to that coach's history entries. Co-coached sessions count for each coach. Parents MUST be refused.

**Privacy policy**

- **FR-033**: The next version of the public privacy policy and the habeas-data channel text MUST state that more than one coach may access athlete data on behalf of the club; this text change MUST be bundled with the next policy version rather than released alone, because any policy change asks every family to renew consent.

**Testing**

- **FR-034**: The automated test suite MUST include a fixture with two coaches in the same club and MUST exercise every scenario above from both coaches' perspectives, including the refused paths (parent, other-club coach, coach on staff actions).

### Key Entities *(include if feature involves data)*

- **History entry**: one recorded action — actor (person or automated kind), actor role, action, record type and identifier, club, athlete concerned, changed field names, catalogue reason, correlation reference, time. Append-only; retained 24 months.
- **Session coach assignment**: the link between a training session and each coach leading it; a session has one or more; defaults to the creator.
- **Attribution on a record**: who created, last edited, archived or approved a record and when; approval evidence survives regeneration.
- **Archived athlete**: an athlete removed from active use whose consent evidence, measurements, results and history are preserved and who can be restored by an administrator; archived with a catalogue reason.
- **Staff account**: a coach or administrator of the club with an active state, a creator and a creation date; deactivated rather than deleted once it has recorded activity.
- **Per-coach activity view**: a period-bounded management summary of one coach's sessions, entries, runs, results operations and documents, derived from attribution and history; internal only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a scripted scenario of 20 mixed actions by two coaches and one administrator (creates, edits, approvals, a cancellation, an archive, a document download, a newsletter send), the club history shows 20 entries with the correct actor, action and record for every one (0 misattributions), and an automated scan of all entries finds 0 occurrences of any name, birth date or free text from the test data.
- **SC-002**: A coach can answer "who changed this athlete's record, and when?" from the athlete page in under 30 seconds without leaving the page, in a moderated test with the club's coach (5/5 questions answered).
- **SC-003**: After archiving an athlete with two years of history, 100 % of their consent, measurement, attendance and result records remain readable by an administrator, the athlete appears in 0 active surfaces, and restoring them returns them to every surface within one action.
- **SC-004**: An administrator creates a second coach from the staff screen in under 2 minutes, and that coach sees the same counts of athletes, sessions and events as the first coach on first sign-in (0 discrepancies).
- **SC-005**: Family notifications for session changes name the acting coach correctly in 100 % of a scripted set of 10 changes split between the two coaches.
- **SC-006**: In a concurrent-editing test on one newsletter, 0 edits are lost and the second coach always receives a conflict message before their save would overwrite the first coach's work.
- **SC-007**: A run awaiting a human decision launched by one coach is completed by the other coach without administrator intervention in 100 % of 5 trials.
- **SC-008**: The per-coach activity view totals reconcile exactly with the club-wide totals for the same period (sum of per-coach sessions counted once per session equals the club's session count).
- **SC-009**: Club-wide reports produced before and after the feature for the same month are identical in sections, figures and signature.
- **SC-010**: The purge preview and confirmation behave as specified on seeded data (1 removed, 0 unexpected removals) and no history entry is ever altered by normal app use over a full test run.

## Assumptions

- **Scope decisions (owner, 2026-09-08)**: both coaches see and edit everything in the club; the log covers writes plus document exports/sends, never plain reads; a session may be led by more than one coach; a minimal staff screen replaces manual API onboarding; retention 24 months with explicit manual purge; the newsletter note author is visible to coaches only.
- **Readiness audit (2026-09-08)** that motivates this feature: no "last edited by" attribution exists anywhere; some records lack even a "last edited at" time; athlete and parent removal is a destructive cascade including consent evidence; family emails attribute changes to the session creator; regenerating a monthly report overwrites its approval evidence; the newsletter studio overwrites concurrent edits; there is no staff screen and a coach created without a club sees an empty app; AI runs and import parses are creator-locked while their listings are not; the AI budget is club-wide and silent; no listing or report can be filtered by coach; one surface prints a raw numeric author identifier. An earlier claim that the migration chain had two heads was verified as false.
- **Legal**: parental consent is granted to the club as data controller and by purpose, not to a named person; adding a coach therefore does not require families to re-consent. The plural-coach wording is bundled into the next policy version (FR-033) because any policy version change triggers the blocking consent-renewal prompt for all families.
- **Existing patterns are reused**: the race-results revision trail, the competitor-link trail and the AI-run event stream stay as domain detail; the new history is the club-wide index and references them.
- **Automated actors**: inbound webhooks, the daily activity reconciliation and start-up backfills are recorded with an actor kind, not a person.
- **AI budget** remains a single club-wide limit; this feature makes spend visible per coach and improves the refusal message, but does not partition the budget per coach and does not add the overrun notification email (still a documented follow-up).
- **Permanent purge of archived athletes** (after a family's suppression request is fully served) is out of scope; archived data stays under the club's retention rules and a later documented procedure.
- **Free-tier hosting**: no background workers exist; the purge procedure runs on demand or from an external monthly schedule, and history entries are written inline with each change.
- **Session coach in past data**: existing sessions get their creator as the single session coach.
- **Language**: all new product copy (staff screen, history sentences, conflict messages, catalogue reason labels) is in español neutro (Colombia) with full diacritics; this specification and the planning artifacts are in English per the constitution's language policy.
- **Out of scope**: separate athlete portfolios per coach, owner-only editing, recording plain reads, a coach self-registration or invitation-by-token flow, and any change to how families see coach names in the newsletter.
