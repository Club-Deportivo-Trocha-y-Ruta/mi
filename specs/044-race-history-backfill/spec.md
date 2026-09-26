# Feature Specification: Race history backfill — Copa Valle 2024 and 2025 seasons with cross-season athlete progression

**Feature Branch**: `main` (owner decision 2026-09-18: no dedicated branch for the specification)

**Created**: 2026-09-18

**Status**: Draft — amended 2026-09-26 (results loading moves to a skill; see Clarifications)

**Input**: User description: "Historical Copa Valle XCO backfill (seasons 2024 and 2025) with cross-season athlete progression. The coach wants to see how each club athlete has progressed over three seasons (2024, 2025, 2026). Athletes move up a category as they age (Infantil → Prejuvenil → Juvenil), so raw position or percentile comparisons across seasons are misleading: dropping in percentile after moving up can be real progress. Official results for 2024 (7 válidas) and 2025 (8 válidas) are published as native-text PDFs linked from the organiser's public blog. Today only the 2026 season is loaded. Owner decisions of 2026-09-18: full start list of every category; one continuous series per athlete with a marker at each category change, built on gap-% to the category median and average speed; fuzzy identity suggestions confirmed by the coach and blocking before the bulk commit; families see their child's complete history including pre-club válidas; renames map to the current catalogue but subdivisions do not, and the printed category label is frozen on each result; a category with lost rows blocks its own commit; only the per-válida RESULTADOS file is ingested; longitudinal analytics of third parties must be structurally impossible before any historical load, while erasure and retention are deferred to the following feature."

## Clarifications

### Session 2026-09-26

Owner directive that opened this session: reading results from uploaded PDF or CSV files is unreliable because every organiser prints a different layout, so every upload option is removed and results enter the platform only through a skill run by hand on a computer with an LLM coding assistant; the same script is tested against a local database and then loads production (recorded in Assumptions as the owner decision of 2026-09-26).

- Q: When the skill reads an official results file, may the LLM see the riders' names (almost all minors, most of them from other clubs)? → A: No. The LLM never sees real rows: a local script replaces every name, club and city with a placeholder token before any file content reaches the LLM; the LLM works out how to read that organiser's layout (columns, category headers) on the masked version, and the script applies that reading to the real file without the LLM.
- Q: Once the skill has validated a válida locally, how do its results reach the production database? → A: Direct load. The same script targets the local database by default and writes to production only when explicitly asked (explicit flag plus confirmation); the extracted data stays on the operator's computer, in a folder that is never committed. No database data migration, because it would commit minors' names to the repository.
- Q: Once the skill has written a válida to the database, where is it reviewed and committed — in the web app or inside the skill session? → A: In the web app. The skill leaves the válida pending in the target database; the coach reviews it there (category mapping, incomplete categories, identity candidates) and commits it with the existing screens. The web app loses only the file-upload step.
- Q: If the skill tries to load a válida that is already committed (the organiser published a correction, or the reading was wrong), what happens? → A: It can only be staged as a revision. The new reading stays pending; the coach sees its differences (rows added, changed, removed) in the web app and commits it with a reason from the closed list; athlete links are preserved, every change is audited, and nothing changes until the coach commits. An identical file is still refused. (Corrected the same day during planning: the first answer assumed a single-row editor that the platform does not have; the only audited correction path is the whole-válida revision.)
- Q: Now that the official file is no longer uploaded to the web app, should the platform still keep a copy of each loaded válida's PDF or CSV? → A: Yes. The skill uploads the original file to the club's file storage, as the upload did before, as evidence linked to its import.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - No result is lost in silence when an official file is read (Priority: P1)

The operator runs the results-loading skill on an official results file of a past válida and gets back a preview that accounts for every printed row (since 2026-09-26 no file is uploaded to the platform; see Clarifications). Today that is not true for the historical files: when a rider's club name is long enough to spill over the neighbouring time column, the two texts are read mixed together and the row is dropped without any warning (measured during planning on three official files: 16 % to 25 % of all rows of each file, among them category winners), and whole categories whose printed header is not recognised disappear from the preview (5 categories in the first válida of 2025, 9 in the first válida of 2024, among them the complete elite men's field). After this story, rows with overlapping columns are read whole, every category header is either recognised or shown to the coach as unrecognised, and each category is checked for completeness: the positions of its classified finishers must form the full sequence 1…N. A category that fails the check is marked inconsistent, shows which positions are missing or duplicated, and cannot be committed until the coach corrects it by hand. The other categories of the same válida are not held back.

**Why this priority**: Every metric of this feature divides by the size and the times of the field. A preview that silently loses the winner or a third of a category poisons the median, the percentile and the gap before any analysis starts, and the loss is invisible afterwards. Nothing else may be loaded until reading is trustworthy.

**Independent Test**: With three synthetic results files that reproduce the historical layout (long club values printed over the time column, historical category headers, one category with a deliberately removed row), run the preview and assert that every overlapping row appears once with its position, time and points; that no category is dropped without being listed as unrecognised; that the category with the removed row is marked inconsistent naming the missing position; and that committing it is refused while the remaining categories commit normally.

**Acceptance Scenarios**:

1. **Given** a results file where a rider's club or city spills over the neighbouring column, **When** the file is previewed, **Then** that rider appears as a single complete row with position, name, club, time and points.
2. **Given** a results file that contains a category header the platform does not recognise, **When** the file is previewed, **Then** the category is listed as unrecognised with its printed header and its row count, and it is never discarded without notice.
3. **Given** a category whose classified positions are 1, 2, 4, 5, **When** the preview is shown, **Then** the category is marked inconsistent, position 3 is named as missing, and its commit is blocked.
4. **Given** a category with a duplicated position, **When** the preview is shown, **Then** it is marked inconsistent naming the duplicated position and its commit is blocked.
5. **Given** an inconsistent category, **When** the coach adds or corrects the missing row by hand in the preview, **Then** the check runs again and the block lifts as soon as the sequence is complete.
6. **Given** a gap that really exists in the official file, **When** the coach acknowledges it choosing a mandatory reason from a closed list, **Then** the category can be committed and the acknowledgement is recorded in the audit trail with author and time.
7. **Given** a válida with one inconsistent category and ten consistent ones, **When** the coach commits, **Then** the ten consistent categories are loaded and the inconsistent one stays pending.
8. **Given** a results file of the 2026 season that is already loaded, **When** the skill reads it again, **Then** it yields exactly the rows already loaded, with no row gained, lost or changed.

---

### User Story 2 - Historical categories keep their own meaning (Priority: P1)

The category names printed in 2024 and 2025 differ from the 2026 catalogue in two distinct ways. Some are pure renames of the same group (the women's and girls' categories were printed as "DAMAS" and "NIÑAS" and are now "FEMENINO"): these map to the current catalogue entry so an athlete's series stays continuous. Others are structural: in 2025 the master categories were two groups (B, C) where 2024 and 2026 have four (B1, B2, C1, C2), and in both historical seasons the pre-infantile girls raced as a single group where 2026 splits them in two (A, B). Those are loaded as categories of their own season and are never folded into a subdivision, because doing so would invent an age range that did not exist that year. In addition, every result keeps, frozen, the category label and the age range exactly as they applied when it was loaded, so that a later edit of the catalogue can never rewrite what a past result meant.

**Why this priority**: The continuous series of User Story 6 depends on knowing when a category change is real and when it is only a new name for the same group. It also protects the historical record from well-intentioned catalogue edits.

**Independent Test**: Preview a historical file containing a renamed category and a master B category; assert the renamed one resolves to the current catalogue entry, the master B one resolves to a season-specific category distinct from B1 and B2, both results store the printed label and age range, and that editing the catalogue entry afterwards leaves the stored label and range of the already loaded results unchanged.

**Acceptance Scenarios**:

1. **Given** a historical header that is a pure rename of a current category, **When** the file is previewed, **Then** its rows resolve to the current catalogue entry and the printed label is kept on each result.
2. **Given** a historical category that was later subdivided, **When** the file is previewed, **Then** its rows resolve to a category specific to that season and are never assigned to any of the later subdivisions.
3. **Given** a loaded result, **When** the label or the age range of its catalogue category is edited later, **Then** the label and age range stored on the result do not change.
4. **Given** the results already loaded for 2026, **When** this feature is deployed, **Then** each of them receives the frozen label and age range of its current catalogue category, and nothing else about them changes.
5. **Given** a season-specific historical category, **When** any selector or filter of the current season is shown, **Then** that category is not offered for new 2026 data.

---

### User Story 3 - A third party can never be profiled over time (Priority: P1)

Loading the full start list of fifteen válidas brings several hundred riders who do not belong to the club into the platform, most of them minors, across three seasons. Their results are needed only as the denominator that situates the club's own athletes: the size of the field, the median time, the winner's time. Before any historical file is loaded, the platform makes it structurally impossible to obtain the progression of a competitor who is not linked to a club athlete: the request is refused for every role and from every entry point, not merely never offered in the interface. Third-party names keep not reaching families, newsletters, generated documents, logs or AI prompts, exactly as today.

**Why this priority**: The legal basis for holding these results is legitimate interest in a sporting context, limited to situating the club's own athletes. That the files are posted on a public blog does not make them "public data" in the legal sense. The guarantee must exist before the data does, which is why this story precedes the load.

**Independent Test**: With one competitor linked to a club athlete and one unlinked competitor that both have results in three seasons, request the progression of each as admin, coach, parent and athlete; assert the unlinked request is refused for all four roles, the linked one follows today's permission rules, and an inspection of every log line, AI prompt and family-facing output produced during the test contains zero third-party names.

**Acceptance Scenarios**:

1. **Given** a competitor not linked to any club athlete, **When** any role requests that competitor's progression, history across válidas or any per-person time series, **Then** the platform refuses, whatever the entry point.
2. **Given** a competitor linked to a club athlete, **When** the coach requests the progression, **Then** it is served as today.
3. **Given** the historical seasons are loaded, **When** a parent opens any results or history view, **Then** they see only rows of their own children and no third-party name, club or city.
4. **Given** the historical seasons are loaded, **When** any AI analysis, newsletter or generated document is produced, **Then** it contains no third-party name, and field-level figures (field size, median, winner's gap) appear only as aggregates.
5. **Given** a competitor whose link to a club athlete is removed, **When** the progression is requested afterwards, **Then** it is refused from that moment on.

---

### User Story 4 - The coach decides who is who before anything is merged (Priority: P1)

Across three seasons the same person is sometimes printed differently (a second surname added one year, accents dropped, surnames inverted), and different people share the same name, especially in children's categories where common first-name and surname pairs repeat across towns and clubs. After the historical files are previewed and before any of them is committed, the platform presents a review of identity candidates computed over the whole universe (the fifteen historical válidas plus the competitors already loaded): probable same-person pairs with a confidence score, and probable homonyms where an identical name appears with a clearly different club or city or in two categories of the same válida. For each candidate the coach sees both records side by side (seasons, categories, club and city as printed) and answers "same person" or "different people". Nothing is merged automatically. Every decision is audited, remembered so the same question is not asked again when a file is re-read, and reversible.

**Why this priority**: With the full start list the number of name collisions grows faster than the number of riders. A wrong merge mixes two children's histories, and if one of them is later linked to a club athlete the family would see results that are not their child's. It is cheap to decide before the load and expensive to untangle after it.

**Independent Test**: Preview synthetic files of two seasons containing one person written with and without a second surname, and two different riders with an identical name from different towns; assert both situations appear as candidates, that committing any historical válida is refused while either is unresolved, that after answering "same person" and "different people" the load yields one competitor for the first case and two for the second, that the audit trail holds both decisions, and that re-previewing the same files asks nothing again.

**Acceptance Scenarios**:

1. **Given** previewed historical files, **When** the coach opens the identity review, **Then** candidates are listed ordered by confidence, each showing both records with seasons, categories, club and city as printed.
2. **Given** unresolved identity candidates, **When** the coach tries to commit any historical válida, **Then** the commit is refused and the number of pending candidates is shown.
3. **Given** a candidate answered "same person", **When** the historical files are committed, **Then** the results of both spellings belong to a single competitor.
4. **Given** a candidate answered "different people", **When** the historical files are committed, **Then** two distinct competitors exist even though their names are identical, and later files keep them apart using club and city.
5. **Given** an identical name with matching club and no contradiction, **When** the files are previewed, **Then** no question is raised and the rows attach to the existing competitor.
6. **Given** a decision already taken, **When** the same file is previewed again, **Then** the decision is applied without asking again.
7. **Given** a "same person" decision the coach later finds wrong, **When** they reverse it from the review, **Then** the results return to two separate competitors and the reversal is audited.
8. **Given** a candidate in which one record is already linked to a club athlete, **When** the coach answers "same person", **Then** the historical results become part of that athlete's history and the audit entry records that a linked athlete was involved.
9. **Given** a review interrupted halfway, **When** the coach returns another day, **Then** the decisions already taken are preserved and only the pending candidates remain.

---

### User Story 5 - The fifteen historical válidas are loaded through the same trusted path (Priority: P1)

With reading, categories, the privacy guarantee and the identity review in place, the seven válidas of 2024 and the eight of 2025 are loaded, each from its official per-válida results file: the operator stages each válida with the results-loading skill as a pending import, and the coach reviews and commits it in the web app with the same preview → dry-run → commit screens, the same duplicate protection and the same audit trail as the 2026 imports; it is not a separate route with different rules. The 2024 and 2025 seasons appear as seasons of the same cup, each válida with its date and venue, and their standings are calculated from the loaded results. The cumulative standings files published by the organiser are not loaded.

**Why this priority**: This is the step that actually delivers the history. It is last among the P1 stories only because the four before it are its preconditions.

**Independent Test**: Load two synthetic historical válidas of one season; assert the season exists with both válidas, dates and venues, every category of each file is present with its full field, calculated standings equal the sum of the loaded points, loading the same file a second time creates nothing new, and every commit is visible in the audit trail with author and time.

**Acceptance Scenarios**:

1. **Given** the official results file of a historical válida, **When** the operator stages it with the skill and the coach commits it in the web app, **Then** the válida exists in its own season with date and venue and all its consistent categories.
2. **Given** a file that was already loaded, **When** the skill stages it again, **Then** no duplicate válida, competitor or result is created and the operator is told it was already loaded.
3. **Given** a load interrupted after some válidas, **When** the coach resumes, **Then** the remaining válidas can be loaded without redoing the finished ones.
4. **Given** a season fully loaded, **When** its standings are shown, **Then** they are calculated from the loaded results and labelled as calculated by the platform.
5. **Given** a file whose season, válida number or venue cannot be read from its header, **When** the skill reads it, **Then** the operator is asked to supply them and nothing is assumed.
6. **Given** the historical seasons are loaded, **When** any 2026 view is opened, **Then** it shows exactly what it showed before the load.
7. **Given** a válida that is already committed, **When** the skill stages a different file or a different reading of that same válida, **Then** it is staged as a pending revision: the coach sees the rows added, changed and removed in the web app and commits it with a reason from the closed list, and no committed result changes until then.
8. **Given** the operator runs the skill without explicitly asking for production, **When** the load runs, **Then** only the local database receives the staged válida.
9. **Given** a válida staged by the skill, **When** the coach has not committed it yet, **Then** it appears nowhere outside the import review of the web app, where the coach can review, commit or discard it; the stored official file is linked to it as evidence.
10. **Given** any skill run, **When** file content is shown to the LLM, **Then** every rider name, club and city in it has been replaced by a placeholder token.
11. **Given** any role in the web app, **When** they look for a way to load results from a file, **Then** none exists, and any attempt to send a results file to the platform is refused.

---

### User Story 6 - The coach sees whether an athlete is improving across seasons (Priority: P2)

For any club athlete the coach opens one continuous series covering 2024 to 2026. The series is drawn with the two measures that survive a category change: the gap in percent to the median time of the athlete's own category in that válida, and the average speed where the válida has a course profile. Each category change is a visible vertical marker, not an invisible break. A season the athlete did not race appears as a dashed gap; a DNF, DSQ or DNS appears with its own symbol and never as a time. Position and position percentile are available, but only inside one category and one season, never joined across them. Every figure carries its field size, and the caveats that always apply are written next to the data: circuits differ between venues, weather and surface differ, fields under five finishers are unreliable, non-finishers are excluded from time averages, and a three-rider category puts everyone on the podium. A per-season summary shows completion as a plain count ("5 de 7").

**Why this priority**: This is the answer to the question that motivated the feature. When an athlete moves up they race older riders, so a worse percentile can be real progress; only a field-relative time measure and a distance-normalised speed tell the truth across that step.

**Independent Test**: Seed one athlete with results in three seasons who changes category between the first and second, skips one válida, and has one DNF and one válida with four finishers; assert a single continuous series with one category-change marker at the right válida, a dashed gap at the skipped válida, a distinct DNF symbol without a time value, "sin dato" for gap and percentile in the four-finisher válida, average speed only where a course profile exists, percentile never connected across the category change, and the caveats visible.

**Acceptance Scenarios**:

1. **Given** an athlete with results in three seasons, **When** the coach opens the progression, **Then** one continuous series spans all three seasons on a time axis.
2. **Given** consecutive results in different categories, **When** the series is drawn, **Then** a marker sits at the first válida of the new category naming both categories, and a pure rename is not marked as a change.
3. **Given** a válida with at least five full-distance finishers in the athlete's category, **When** the series is drawn, **Then** the gap to the median is shown as a signed percentage, negative when the athlete was faster than the median.
4. **Given** a válida with fewer than five full-distance finishers in the athlete's category, **When** the series is drawn, **Then** gap to the median and percentile read "sin dato" while the position and the field size are still shown.
5. **Given** a válida without a course profile, **When** the series is drawn, **Then** average speed reads "sin dato" for that válida and is never estimated.
6. **Given** a DNF, DSQ or DNS, **When** the series is drawn, **Then** it appears with its own symbol, contributes to no time average, and counts in the season completion summary.
7. **Given** an athlete classified with laps down, **When** the series is drawn, **Then** that result has no gap to the median, and lapped riders are not part of the median either.
8. **Given** the position percentile, **When** it is displayed, **Then** it is grouped by category and season and no line connects values of different categories or seasons.
9. **Given** any figure in this view, **When** it is displayed, **Then** the field size is shown beside it and the standing caveats are visible without any extra action.
10. **Given** the view is opened on the coach's tablet, **When** it loads an athlete with three seasons of results, **Then** it responds within the same time budget as today's single-season progression.

---

### User Story 7 - Families see their child's complete history (Priority: P2)

A parent opens their child's results and sees the complete history, including válidas the child raced before joining the club, with the same continuous series, category-change markers and caveats as the coach, in family-friendly wording. They never see another rider's row, name, club or city: the field appears only as aggregates (field size, gap to the median). Because pre-club results are data the family did not hand to the club, the privacy notice shown to families states that the child's published historical results, including those prior to joining, are displayed; pre-club results are shown to a family only once that notice is in force.

**Why this priority**: The owner decided families get the whole history. It is P2 because it consumes what User Stories 5 and 6 produce, and because the notice wording must be in place first.

**Independent Test**: With a parent of one athlete who has results before and after joining the club, open the family history; assert both periods appear in one series, no third-party row or name exists anywhere in the response, a parent of a different athlete sees none of it, and with the updated notice not yet in force the pre-club results are withheld while post-joining results are shown.

**Acceptance Scenarios**:

1. **Given** a child with results before and after joining the club and the updated privacy notice in force, **When** the parent opens the history, **Then** both periods appear in one continuous series.
2. **Given** the updated privacy notice is not yet in force, **When** the parent opens the history, **Then** only results from the joining date onwards are shown and nothing suggests missing data.
3. **Given** any family-facing history view, **When** it is displayed, **Then** it contains only the child's own results and field-level aggregates, and no third-party name, club or city.
4. **Given** a parent of another athlete, **When** they try to open this child's history, **Then** access is refused as it is today.
5. **Given** a category change in the child's history, **When** the parent sees the marker, **Then** a short explanation in plain language says that moving up means racing older riders and that a lower placing right after the change is expected.
6. **Given** the family view on a mobile connection, **When** it loads, **Then** the summary and the latest results are readable before the chart finishes rendering.

---

### Edge Cases

- An athlete changes category in the middle of a season: the marker sits at that válida, and season-level percentile groups split accordingly.
- An athlete skips an entire season: the series shows a dashed gap spanning it, with no interpolation.
- The field has an even number of full-distance finishers: the median is the mean of the two central times.
- The athlete's own time is part of the field: it is included in the median like any other finisher.
- A category has exactly five full-distance finishers and one is later corrected to DNF: gap and percentile for that válida become "sin dato".
- The same name appears in two categories of the same válida: it is always raised as a homonym candidate, because one person cannot race two fields at the same time.
- Two riders share name and club (siblings or cousins in the same club): the candidate is raised when their categories or sexes are incompatible; otherwise the city and the categories raced are shown to the coach to decide.
- A "same person" answer joins an unlinked historical record with a competitor already linked to a club athlete: allowed, audited, and immediately visible in that athlete's history under the family-visibility rule.
- A historical file lists a rider of the club who is no longer in the club: they are loaded like any third party; existing rules for former athletes apply to any link.
- A printed row has no time but has a position (organiser omission): it is kept as classified, shows "sin dato" for every time-based figure, and does not enter the median.
- The official file itself contains a position gap or a repeated position (both were found in the 2025 files during planning): the coach acknowledges it with a reason from the closed list (User Story 1, scenario 6).
- A historical category exists in one season only and never again: it stays a season-specific category and appears in no current selector.
- Points printed in a historical file follow a different table than 2026: the printed points are kept as awarded; no recalculation against the current table takes place.
- The organiser applied a discard rule to final standings that the files do not state: the platform's calculated standings may differ from the official final table, which is why they are labelled as calculated.
- A historical válida later receives a course profile through the existing course-profile flow: its average speed appears in the series from then on, with no reload of results.
- The same file is provided under a different name: duplicate protection recognises it by content.
- The organiser publishes corrected results after a válida is committed: the skill stages the corrected file as a revision; the coach reviews the differences and commits it with a reason, and athlete links survive.
- A results file is scanned rather than text: the skill rejects it with a clear message, because its content cannot be masked before the LLM sees it; reading images is out of scope.
- A new organiser prints a layout never seen before: the LLM defines a new reading on the masked file; nothing about the platform changes.
- A válida staged by the skill is never committed: it stays pending and the coach can discard it from the web app, as today.
- The operator runs the load script without the production flag: it writes only to the local database, whatever other configuration is present.

## Requirements *(mandatory)*

### Functional Requirements

**Reading integrity**

- **FR-001**: The results-loading skill MUST read as one complete row a result whose club or city text overlaps a neighbouring column (or is printed across several lines), and MUST NOT discard any printed row without listing it to the operator.
- **FR-002**: The results-loading skill MUST list every category header it does not recognise, with the printed header and its row count, and MUST NOT drop a category silently.
- **FR-003**: For every category in a preview, the platform MUST verify that the positions of classified finishers form the complete sequence 1…N without gaps or duplicates, MUST mark a failing category as inconsistent naming the missing or duplicated positions, and MUST refuse to commit that category.
- **FR-004**: The coach MUST be able to correct an inconsistent category by hand in the preview of the web app (never through the LLM); the check MUST run again after each correction and the block MUST lift when the sequence is complete.
- **FR-005**: The coach MUST be able to acknowledge a gap that exists in the official file by choosing a mandatory reason from a closed list (free text is avoided on purpose: it invites rider names); the acknowledgement MUST be audited with author and time and MUST unblock only that category.
- **FR-006**: An inconsistent category MUST NOT block the commit of the consistent categories of the same válida.
- **FR-007**: Results of the 2026 season already loaded MUST remain unchanged by the move to skill-only loading; re-reading an already loaded 2026 file with the skill MUST yield exactly the rows already loaded.

**Categories across seasons**

- **FR-008**: A historical category header that is a pure rename of a current category MUST resolve to that current category.
- **FR-009**: A historical category that was later subdivided, merged or discontinued MUST be loaded as a category specific to its season and MUST NOT be assigned to any current subdivision; season-specific categories MUST NOT be offered for new data of the current season.
- **FR-010**: Every result MUST keep, frozen at load time, the category label and the age range that applied to it; later catalogue edits MUST NOT alter them. Results already loaded MUST receive these values from their current catalogue category when the feature is deployed.
- **FR-011**: The mapping of each historical header (rename or season-specific) MUST be reviewable by the coach in the preview before commit.

**Third-party protection**

- **FR-012**: The platform MUST refuse any progression, cross-válida history or per-person time series for a competitor that is not linked to a club athlete, for every role and from every entry point; this guarantee MUST be in force before the first historical file is committed and MUST be covered by a denied-path test.
- **FR-013**: Third-party names, clubs and cities MUST NOT appear in anything shown or sent to families, in newsletters or generated documents, in logs or traces, or in AI prompts; results of third parties MAY be used only as field-level aggregates (field size, median time, winner's time).
- **FR-014**: The city printed beside a rider MUST be kept only as an identity-disambiguation signal, MUST be visible only to coach and admin inside the identity review, and MUST NOT be displayed or exported anywhere else.
- **FR-015**: The specification of record for this feature MUST state the legal basis (legitimate interest in a sporting context, limited to situating the club's own athletes) and that publication on a public blog does not make the data "public data"; the mandatory privacy audit MUST be completed before the historical load runs against real data.

**Identity review**

- **FR-016**: After the historical files are previewed, the platform MUST compute identity candidates over the whole universe (all previewed historical válidas plus existing competitors): probable same-person pairs with a confidence score, and probable homonyms (identical name with clearly divergent club or city, incompatible category or sex, or presence in two categories of the same válida).
- **FR-017**: The platform MUST NOT merge two differently written names automatically, and MUST NOT attach a row to an existing competitor when a homonym signal is present, without a decision by the coach.
- **FR-018**: The platform MUST refuse to commit any historical válida while unresolved identity candidates exist, and MUST show how many are pending.
- **FR-019**: For each candidate the coach MUST see both records side by side (seasons, categories, club and city as printed) and MUST be able to answer "same person" or "different people" with a single action.
- **FR-020**: The platform MUST support distinct competitors that share an identical name, and MUST keep them apart in later loads using the recorded decision together with club and city.
- **FR-021**: Every identity decision MUST be audited (who, when, both records, answer), MUST be remembered so that re-reading a file does not ask again, MUST survive an interrupted review, and MUST be reversible by the coach with the reversal audited.
- **FR-022**: Linking a competitor to a club athlete MUST remain an explicit coach decision as it is today; an identity decision that involves an already linked competitor MUST be flagged as such in the audit trail.

**Historical load**

- **FR-023**: Every season (2024, 2025 and the current one) MUST be loaded through the same path: the skill stages the válida as a pending import in the target database, and the coach previews, corrects, resolves identities, dry-runs and commits it in the web app, with the same duplicate protection and audit trail; no parallel path with different rules may exist.
- **FR-024**: Only the per-válida results file is ingested; the organiser's cumulative standings files MUST NOT be loaded.
- **FR-025**: Each historical season MUST appear as a season of the same cup with its válidas, dates and venues; when the header of a file does not yield season, válida number, date or venue, the operator running the skill MUST be asked and nothing is assumed.
- **FR-026**: The points printed in each file MUST be kept as the points awarded; season standings MUST be calculated from loaded results and labelled as calculated by the platform.
- **FR-027**: Loading a file that was already loaded MUST create nothing new; an interrupted load MUST be resumable without redoing the válidas already committed. The skill MUST NOT change an already committed válida directly: an identical file creates nothing, and a different reading of a válida of the cup whose season and válida number are already committed MAY only be staged as a revision, which stays pending until the coach reviews its differences (rows added, changed, removed) and commits it in the web app with a reason from the closed list; athlete links are preserved and every change is audited.
- **FR-028**: The full start list of every category of every historical válida MUST be loaded, including categories where no club athlete raced.
- **FR-029**: Loading the historical seasons MUST NOT change anything displayed for the 2026 season.

**Cross-season progression**

- **FR-030**: For each result of a club athlete the platform MUST provide the field size, defined as the number of riders of the same category and válida who finished (including riders classified with laps down), and the number of timed finishers (full distance, with a time). These are the definitions already in use for the per-season field reading.
- **FR-031**: The platform MUST provide the gap to the median as (athlete's time − median time of full-distance finishers of the same category and válida) ÷ that median × 100, to one decimal, only when there are at least five timed finishers and the athlete finished the full distance with a time; otherwise "sin dato".
- **FR-032**: The platform MUST provide the position percentile as (field size − position) ÷ (field size − 1) × 100, only when the field size is at least five; it MUST be presented grouped by category and season and MUST NOT be connected or averaged across categories or seasons.
- **FR-033**: The progression MUST include the average speed derived from the course profile of the válida when one exists, under the same "sin dato, never estimated" rule that already governs it.
- **FR-034**: The progression MUST carry a category-change flag on the first result whose category differs from the athlete's previous result in chronological order; a pure rename MUST NOT raise the flag.
- **FR-035**: The platform MUST provide, per athlete and season, the completion summary as finished results over results with a start, always displayed with both numbers.
- **FR-036**: DNF, DSQ and DNS results MUST be excluded from every time average and median, MUST be displayed with a distinct symbol, and lapped riders MUST be excluded from the median and show "sin dato" for the gap.
- **FR-037**: The coach view MUST present one continuous series per athlete across all loaded seasons with a visible marker at each category change, a dashed gap for válidas or seasons not raced, and the field size beside every figure.
- **FR-038**: The standing caveats (different circuits between venues, weather and surface, fields under five finishers, non-finishers excluded from averages, three-rider categories) MUST be visible next to the data in both coach and family views, without requiring any action.
- **FR-039**: Points MUST NOT be summed, averaged or compared across seasons.

**Family visibility**

- **FR-040**: A parent MUST see the complete history of their own child, including válidas raced before joining the club, under the same continuous series, markers and caveats, and MUST see nothing of any other rider beyond field-level aggregates.
- **FR-041**: The privacy notice presented to families MUST state that the child's published historical results, including those prior to joining the club, are displayed; results prior to the joining date MUST be withheld from a family until that notice is in force, without any hint of missing data.
- **FR-042**: Family-facing copy at a category-change marker MUST explain in plain language that moving up means racing older riders and that a lower placing right after the change is expected; all copy MUST avoid comparative or discouraging language about a minor.

**Skill-only loading (amendment 2026-09-26)**

- **FR-044**: Every way of loading results by uploading a file (PDF, CSV or any other format) MUST be removed from every screen and every entry point of the platform, for every role; no entry point may accept a results file, and this MUST be covered by a denied-path test.
- **FR-045**: Results MUST enter the platform only through the results-loading skill, run by hand by an operator on a computer with an LLM coding assistant; the script tested against a local database MUST be the same one that loads production.
- **FR-046**: No rider name, club or city — of a club athlete or of a third party — MUST reach the LLM's context. A local, deterministic step MUST replace them with placeholder tokens before any file content is shown to the LLM; the LLM defines how to read the organiser's layout on the masked version only, and the script applies that reading to the real file locally without the LLM.
- **FR-047**: The skill's load script MUST write directly to the target database. It MUST target the local database by default and MUST write to production only when the operator asks for it explicitly (a dedicated flag plus a confirmation naming the target); production credentials are read from a local file that is never committed and are never printed. Results MUST NOT be loaded through database data migrations or any other file committed to the repository, and the extracted data MUST stay on the operator's computer, outside anything committed to the repository.
- **FR-048**: The skill MUST only stage a válida: it stays pending, and invisible outside the import review, until the coach commits it in the web app; the skill MUST NOT commit, correct, acknowledge or decide identities. The web app keeps its review screens (preview, category mapping, completeness correction and acknowledgement, identity review, dry-run, commit, discard) and loses only the file-upload step.
- **FR-049**: The skill MUST upload the original official file to the file storage of the target environment (the club's storage in production, the local fallback in local tests), validated by content type like any upload, and MUST link it to the staged import as evidence, together with the content fingerprint used for duplicate protection. The web app MUST NOT read or re-parse that file: review, dry-run and commit work on the rows the skill staged. Retention of these files remains deferred under FR-043.

**Deferred, recorded here on purpose**

- **FR-043**: The specification MUST record that a real erasure path for unlinked competitors and a retention policy for stored source files are required by the privacy audit and are deferred to the feature immediately following this one; until then the historical load is an accepted, documented governance debt.

### Key Entities

- **Season of the cup**: one year of the Copa Valle; 2024 (seven válidas) and 2025 (eight válidas) join 2026. Holds its válidas, each with number, date and venue.
- **Result**: one rider in one category of one válida; gains the frozen category label and age range that applied when it was loaded.
- **Season-specific category**: a category that existed with its own meaning in a past season and has no one-to-one current equivalent; never offered for current data.
- **Competitor**: a person appearing in results; two competitors may share an identical name. Carries club and, only for disambiguation, the city as printed. May be linked to a club athlete by explicit coach decision.
- **Identity candidate**: a pair of records the platform suspects to be the same person, or the same name belonging to different people; has a confidence, the evidence shown to the coach, and a state (pending, same person, different people, reversed).
- **Identity decision**: the audited answer to a candidate: who, when, both records, the answer, whether a linked athlete was involved, and any reversal.
- **Category completeness check**: per category of a preview, whether positions form 1…N, which are missing or duplicated, any manual correction, and any audited acknowledgement of a gap in the source.
- **Progression point**: for a club athlete and a válida: category, category-change flag, status, position, field size, gap to the median, percentile, average speed when available. Computed from results at read time; exists only for competitors linked to a club athlete.
- **Season completion summary**: per club athlete and season, finished results over results with a start.
- **Reading profile**: how one organiser's layout is read (columns, category headers and their mapping), defined by the LLM on a masked file; holds no rider data and is reusable for later files with the same layout.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the reference historical files, 100 % of printed result rows appear in the preview (row count per category equals the printed count) and 0 categories disappear without being listed; the 16–25 % loss measured per file during planning drops to 0 %.
- **SC-002**: Across the fifteen historical válidas, 0 categories are committed with an incomplete position sequence unless an audited acknowledgement with a chosen reason exists.
- **SC-003**: 100 % of identity candidates have an audited coach decision before the first historical válida is committed, and 0 competitors are created or merged by an automatic name match when a homonym signal was present.
- **SC-004**: A request for the progression of a competitor not linked to a club athlete is refused in 100 % of attempts, for all four roles.
- **SC-005**: An inspection of every log line, trace, AI prompt, newsletter and family-facing response produced during the historical load and a subsequent analysis run finds 0 third-party names.
- **SC-006**: Loading a file that is already loaded creates 0 new válidas, competitors or results, and staging a different reading of an already committed válida changes 0 committed results until the coach commits the revision.
- **SC-007**: Every view of the 2026 season renders identically before and after the historical load.
- **SC-008**: From a single view and in under one minute, the coach can say whether a given athlete improved between 2024 and 2026 and point to the válida where the category changed.
- **SC-009**: The coach resolves an identity candidate in one action and under 15 seconds on average, and can stop and resume the review without losing a decision.
- **SC-010**: A parent sees their child's complete history with 0 third-party rows, names, clubs or cities, and results prior to joining appear in 0 % of family views while the updated privacy notice is not in force.
- **SC-011**: The cross-season progression of an athlete with three seasons of results is displayed within the same time budget as today's single-season progression on the coach's tablet and on a parent's mobile connection.
- **SC-012**: Gap to the median and percentile read "sin dato" in 100 % of válidas with fewer than five full-distance finishers; no estimated figure is ever shown. (Average speed was removed from the cross-season history on 2026-09-22 — see Assumptions; it still applies per-válida via feature 043.)
- **SC-013**: Across every skill run, content shown to the LLM contains 0 rider names, clubs or cities, verified by checking the masked content against the real rows the script extracted.
- **SC-014**: 0 screens or entry points of the platform accept a results file upload, for any role.

## Assumptions

- **Owner decisions (2026-09-18), not to be re-asked**: (1) the full start list of every category of all fifteen historical válidas is loaded; (2) the athlete's view is one continuous series with a marker at each category change, built on gap to the median and average speed¹, with position and percentile confined to one category and season; (3) identity is resolved by platform suggestions confirmed by the coach, audited, and blocking before the bulk commit; (4) families see the child's complete history including pre-club válidas; (5) renames map to the current catalogue, subdivisions stay season-specific, and the printed label and age range are frozen on each result; (6) a category with lost rows blocks its own commit until corrected by hand; (7) only the per-válida results file is ingested; (8) the third-party progression lock ships before any load, while erasure and retention follow in the next feature.
- **Owner decision (2026-09-21), not to be re-asked — "separar por categoría"**: two different people printed with the identical name, club and city (the realistic case is a parent and child of the same club) must not collapse into one competitor. The platform raises them as a homonym pair when their rows sit in two categories of the same válida or in age-incompatible categories (or the sex / age-path signals fire); once the coach answers "different people", each is kept apart by a discriminator derived from its category, and later results are assigned by category. If the mixed competitor is already linked to a club athlete, the split is refused until the coach unlinks it (the platform cannot tell which of the two is the athlete).
- **Owner decision (2026-09-22), not to be re-asked — average speed removed from the history¹**: "no es un dato relevante" in a cross-season view. Supersedes the average-speed half of the 2026-09-18 decision above; the series is now gap to the median alone, with no metric toggle. Feature 043's per-válida speed (Circuito tab, `EvolutionChart`/`EvolutionTable`) is unaffected.
- **Owner decision (2026-09-22), not to be re-asked — identity review scoped to club athletes**: a real local load of the 15 official files raised 781 pending candidates (760 same-person suspects, 21 homonyms), only 20 of them involving a club athlete. The review therefore asks only about pairs where at least one side is an existing competitor linked to a Trocha y Ruta athlete. Records that involve only third parties raise nothing and are resolved without asking, **separate by default**: a name match alone never attaches a third-party row to an unlinked competitor with a different club or city; two rows with the identical name, club and city in the same válida become two competitors (category discriminator, or bib when the category is the same); pending candidates already in the queue that fall out of scope are removed by the next rebuild (decided ones are kept). Accepted cost: a third party who changed club or city appears as two competitors — their cross-válida data is not shown anywhere (third-party lock), so nothing visible degrades.
- **Owner decision (2026-09-26), not to be re-asked — results enter only through a skill**: each organiser prints a different layout, so a fixed parser behind a file upload keeps breaking. Every PDF and CSV upload option is removed; results are loaded only through a skill run by hand on a computer with an LLM coding assistant, tested against a local database first, and the same script loads production by writing to it directly (never through a data migration). The skill only stages; the coach still reviews and commits every válida in the web app. The LLM never sees rider names, clubs or cities (Clarifications, 2026-09-26). This supersedes every earlier mention of the coach uploading a file to the platform.
- **Sources**: the organiser publishes each válida's results file through links on its public results pages for 2024 and 2025. The coach (or an operator on the coach's behalf) obtains the fifteen files and gives them to the operator who runs the results-loading skill; automatic crawling of the organiser's site is out of scope. A sample of three of those files was inspected on 2026-09-18: all are text-based documents of the same visual family as the 2026 files.
- **Evidence behind the reading requirements**: on that sample the platform read 214 of 282, 232 of 277 and 211 of 280 printed rows (24 %, 16 % and 25 % lost); 5 categories of the 2025 opening válida and 9 of the 2024 opening válida (including the full elite men's field) were discarded for unrecognised headers. These numbers are the baseline for SC-001.
- **Thresholds**: five full-distance finishers is the minimum field for gap to the median and percentile. The median uses full-distance finishers only; the athlete's own time is included. Rounding: percentages to one decimal.
- **Why the median and not the winner**: the gap to the winner, which exists today, depends on a single exceptional rider; the gap to the median is stable against that and is the primary cross-category measure. The existing gap to the winner is kept where it already appears.
- **Average speed in historical válidas**: removed from this cross-season history (owner decision 2026-09-22, above). Not relevant here regardless of course-profile coverage; per-válida speed is still available on the Circuito tab and `EvolutionChart`/`EvolutionTable` (feature 043) when a course profile exists.
- **Completeness rule**: the official files do contain defects (a repeated position in one children's category of both 2025 files inspected, and a missing position in another); any such case is an inconsistency to be corrected by hand or acknowledged.
- **Standings**: points printed per row are taken as awarded. Calculated standings may differ from the organiser's final table if a discard rule was applied; they are informative and labelled as calculated. No check against the cumulative standings files is performed.
- **Identity signals**: name similarity, club and city as printed, sex, category compatibility between seasons (a rider cannot move down an age category), and co-occurrence in one válida. Birth dates of third parties are not available and are not sought.
- **Remembered decisions without a management screen**: decisions are taken, reviewed and reversed inside the identity review of the import; a general competitor merge/split or alias-management screen is out of scope.
- **Family notice**: the updated wording of the privacy notice is part of this feature; it relies on the existing mechanism by which a notice version comes into force, and no new per-family consent gate is introduced. "Joining date" is the date the athlete was registered in the club.
- **AI analysis**: unchanged by this feature. Cross-season metrics are not added to any AI prompt here; the existing rule that no third-party name reaches a provider stays in force and is re-verified by the privacy audit.
- **Stored source files**: the skill uploads the original file of each válida to the club's file storage, linked to its import, as the upload did before 2026-09-26 (Clarifications, 2026-09-26); the stored file is evidence only and is never parsed by the platform. How long those files are kept is the retention question deferred by FR-043.
- **Privacy audit**: a preliminary review on 2026-09-18 concluded "approved with conditions" (third-party progression lock before load; erasure path; retention policy; legal basis written down). The mandatory audit is repeated on the implemented feature before real data is loaded.
- **Testing data**: all fixtures are synthetic reproductions of the historical layout; no official file and no real rider name is committed to the repository.
- **The mechanism is not historical-only**: nothing in this feature is keyed to the 2024–2025 seasons. The category of a result is recorded per result, the printed label and age range are frozen on every insert (current season included), the category-change marker compares an athlete's consecutive results in date order with no season-boundary logic, the continuous series spans every loaded season, and the identity review gates every import. So an athlete who moves up between the current season and the next is handled by exactly the same path, with the same gap-to-median and average-speed reading, and a mid-season change is marked at the válida where it happened. What the platform does **not** do (out of scope, below) is check that the category a rider was entered in matches the one their birth date implies, or adjust any figure for relative age or maturation.
- **Planning adjustments (2026-09-18, see `research.md`)**: (1) rows are lost because a long club name is printed over the time column, not because text wraps; the loss is 16–25 % of each file, not one category (R-01). (2) Four-group masters already existed in 2024; the season-specific groups are 2025's two master groups and the single pre-infantile girls' group of both seasons; 2025 itself prints the same category both as "DAMAS" and as "FEMENINO" (R-03). (3) The acknowledgement of a gap in the source uses a closed list of reasons instead of free text, following the existing precedent for revision reasons, because free text about a results sheet of minors invites names (R-05). (4) Field size keeps the definition already used for the per-season field reading (finishers including lapped riders); the minimum of five applies to field size for the percentile and to timed finishers for the gap to the median (R-08). (5) The platform has no joining date for an athlete; "joining date" is the date the athlete was registered in the platform, which for the current roster means every 2024–2025 result is withheld from families until the updated privacy notice is in force (R-09).
- **Planning adjustments (2026-09-26, see `research.md` R-17…R-31)**: (1) the organiser's GENERAL file (cumulative season standings) is no longer accepted for any season, not only the historical ones — it never created results, and dropping it avoids creating third-party competitor records without a result (R-25); (2) race conditions are no longer captured when a válida is loaded; the coach enters them on the válida's *Condiciones* tab, which already exists (R-31); (3) the correction path chosen in Clarifications (a revision of the whole válida) exists only in part today — detection, the reason catalogue and the diff screen exist, but the diff is never computed and a revision commit only adds rows — so this amendment wires the diff and the apply step (R-24); (4) loads staged through the old upload before the change must be prepared again with the skill; they can still be discarded (R-27).
- **Language**: all product copy is español neutro (Colombia) with full diacritics; this specification and the planning artifacts are in English per the constitution's language policy.
- **Out of scope**: a general alias or merge/split management screen; a season-versioned category catalogue; the erasure path and the retention policy (next feature); seasons before 2024; other race series; the organiser's cumulative standings files; any upload of a results file (PDF, CSV or other) through the web app or the API; letting the LLM read unmasked results; loading results through database data migrations; reading scanned or image files; automatic download from the organiser's site; validating an athlete's expected category from their birth date; adjusting figures for relative age or maturation (they may be shown as context in a later feature, never as a correction); any change to AI prompts; any season-to-season aggregate of points.
