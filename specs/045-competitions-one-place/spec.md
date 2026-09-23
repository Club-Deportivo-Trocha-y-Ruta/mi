# Feature Specification: Competitions in one place — one area, one athlete tab, one set of metrics

**Feature Branch**: `main` (owner decision 2026-09-23: no dedicated branch; the `speckit.git.feature` hook and every auto-commit hook are skipped)

**Created**: 2026-09-23

**Status**: Draft

**Input**: User description: "Competitions in one place — condense every race-related surface (load → identity → results → metrics → AI analysis → history → families) into one intuitive structure. Owner decisions 2026-09-23: the area is named «Competencias»; the athlete tabs «Insights IA» and «Carreras» merge into one tab «Carreras» for coach and family (views Progresión · Análisis IA · Comparar, data first); families never see the gap to the winner or to the podium; percentile is time-based everywhere and every metric comes from one engine; approving an AI analysis never sends an automatic email; the identity gate blocks only on candidates that involve the import being committed; «Competencias» gets three sections (competitions, «Temporada», «Cargas e identidades» with resumable imports); Home «Pendientes» lands on what it announces; touch targets ≥ 48 px; old links keep working. Everything on main, no branches."

## Context

Feature 007 promised that «Competencias» would be the one place a coach goes for races. Features 036–044 then added race capabilities outside that tree. A product review on 2026-09-23 found:

- **The coach's three questions are scattered.** The questions are "what happened in this race?", "how is this athlete doing?" and "what do I still have to do?". Their answers are spread over:
  - 9 routes;
  - two overlapping athlete tabs, «Insights IA» (5 sub-views) and «Carreras»;
  - two pages with no menu entry (identity review, historical load);
  - Home signals that land on pages that do not show what they announce.
- **Some processes have no inbox.** The identity queue only appears as an error at commit time. AI approvals have no badge. Stale analyses have no list.
- **One number, several meanings.**
  - The gap to the winner is computed in three places under three names.
  - Percentile has three formulas: by position, by time, and by count worse-or-equal.
  - Field size is counted two ways.
  
  As a result, the same race shows different percentiles on different screens.
- **The vocabulary drifts.** The menu says «Válidas», the page says «Competencias» and the tab says «Carreras». There are five different "Histor-" things. Families see raw DNF/DNS/DSQ codes, and coaches see jargon.
- **Families have no direct entry to races**, only through the calendar. Families can also see the gap to the winner by default in the AI evolution chart. That contradicts the youth-safeguard decision the owner took the same day for the history table.

**Phase 0 prerequisites (delivered 2026-09-23, outside this feature's scope):**
- median gap in the AI evolution chart and championship card, with family filtering;
- no email on approval, and a note on the approval card saying so;
- an alias route for the broken email link;
- family `?tab=` parsing;
- season in the address and the "needs results" filter on the competitions list;
- history rows that link to their competition;
- a link from the coach calendar event to its competition.

This feature builds the structure on top of them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The coach reads an athlete's whole race story in one tab (Priority: P1)

A coach opens an athlete's record and finds a single tab, «Carreras». It opens on «Progresión». Progresión shows every season of the athlete's cup results as one continuous line, with markers at each category change, and each championship as its own stat card. The default metric is «Brecha vs. mediana». From the same tab the coach can:
- switch to «Análisis IA», where analyses awaiting approval come first, then the latest approved analysis, then the history, and where the coach launches new analyses, uses the analyst chat and generates the season summary;
- switch to «Comparar», for distribution and head-to-head comparison.

Every point and row links to its competition.

**Why this priority**: this is the question the coach asks most ("how is this athlete doing?"). Today it forces the coach to jump between two tabs that show different slices: one season including championships in one tab, several seasons without championships in the other. It also carries the median-gap metric the owner approved.

**Independent Test**: open any athlete with results in 2024–2026 and at least one championship. The coach should be able to answer "how has this athlete progressed and what did the AI say about the last race?" without leaving the tab. Opening an old `?tab=ai_analysis` link lands on «Carreras › Análisis IA».

**Acceptance Scenarios**:

1. **Given** an athlete with cup results in three seasons and one championship, **When** the coach opens «Carreras», **Then** «Progresión» is shown first with all three seasons, category-change markers, a separate championship card, and «Brecha vs. mediana» selected.
2. **Given** an analysis awaiting approval and two approved analyses, **When** the coach opens «Análisis IA», **Then** the pending one is listed first, followed by the latest approved one and then the older one.
3. **Given** a link that carries a specific analysis, **When** the coach opens it, **Then** the tab opens on «Análisis IA» with that analysis expanded.
4. **Given** a progression point, **When** the coach selects it, **Then** the app navigates to that competition's detail.
5. **Given** the old address `…?tab=ai_analysis`, **When** it is opened, **Then** it resolves to «Carreras › Análisis IA» with no error page.

---

### User Story 2 - One number means one thing on every screen (Priority: P1)

For any athlete and competition, «Parrilla», «Percentil», «Brecha vs. mediana», «Brecha vs. 1.ª posición» and «Brecha vs. podio» show the same value wherever they appear: the athlete tab, the championship card, the competition detail, the season view, family newsletters and the metrics the AI analyst receives. Percentile is time-based everywhere.

**Why this priority**: the coach has already found contradictions, such as a 4th place with a 0.0 % gap or percentiles that differ between two screens. Trust in every other view depends on this.

**Independent Test**: take one competition with ≥ 5 timed finishers in a category and compare every metric for one athlete across all screens that show it. All values match, and the labels are the glossary labels.

**Acceptance Scenarios**:

1. **Given** a category with 5 timed finishers and an athlete whose time equals the median, **When** any screen shows the athlete's median gap, **Then** it shows 0.0 %, and the coach view also shows a non-zero «Brecha vs. 1.ª posición» when that athlete did not win.
2. **Given** the same competition, **When** the percentile is shown on the athlete tab, the championship card or the competition detail, **Then** the value is identical and is time-based.
3. **Given** a category with fewer than 5 timed finishers, **When** percentile or median gap is shown, **Then** it reads «sin dato» everywhere, never 0 and never a dash.
4. **Given** an athlete who lost laps or did not finish, **When** metrics are shown, **Then** percentile and gaps read «sin dato» and the status is shown in plain words.

---

### User Story 3 - Loading a válida is never blocked by unrelated work and never lost (Priority: P1)

The coach uploads the official results of Sunday's válida.
- If the identity queue holds pending decisions about competitors of **other** imports (for example the 2024 backfill), the commit is not blocked.
- If a competitor of **this** import needs a decision, the coach resolves it and returns to the same import where it was left, without uploading the PDF again.

«Cargas e identidades» is one inbox, with a badge, that lists imports in progress, identity decisions («¿Es la misma persona?») and unlinked competitors.

**Why this priority**: with the historical backfill underway, the whole-queue gate can block the most time-sensitive task of the week. Losing an import when leaving it to review identities costs a re-upload and erodes trust.

**Independent Test**: stage a historical import that leaves pending candidates, then commit a new válida whose competitors are all resolved. The commit succeeds. Then create a candidate that involves the new import, leave the import to resolve it, and resume it from «Cargas e identidades» without re-uploading.

**Acceptance Scenarios**:

1. **Given** pending identity candidates that involve only competitors of another import, **When** the coach commits this import, **Then** the commit succeeds.
2. **Given** a pending candidate that involves a competitor of this import, **When** the coach tries to commit, **Then** the commit is blocked with a message that names how many decisions are pending for this import and links to them.
3. **Given** an import in progress, **When** the coach leaves to resolve identities and comes back through «Cargas e identidades», **Then** the import resumes at the step where it was left, with the uploaded file and choices intact.
4. **Given** pending identity decisions or imports in progress, **When** the coach looks at the menu, **Then** «Cargas e identidades» shows a badge with the count.

---

### User Story 4 - A family follows their child's races in one place, safely (Priority: P2)

A parent opens their child's record and finds the same «Carreras» tab, adapted for families:
- «Progresión» shows «Brecha vs. mediana», «Percentil» and «Puesto», never the gap to the winner or to the podium.
- «Análisis IA» shows only analyses the coach approved. It is labelled as AI-generated and reviewed by the coach.

Each result links to the family results page of that competition. Statuses are in plain Spanish. The tab is reachable in two taps from the family home.

**Why this priority**: families are the second audience. The owner's youth-safeguard decision must hold on every family surface, not only on one table.

**Independent Test**: sign in as a parent of an athlete with results and approved analyses, open «Carreras» on a mid-tier Android over simulated 3G, and walk every view. There is no winner or podium gap anywhere, no pending analysis, statuses are in words, and first paint stays within budget.

**Acceptance Scenarios**:

1. **Given** a parent, **When** they open «Carreras › Progresión», **Then** the default metric is «Brecha vs. mediana» and neither «Brecha vs. 1.ª posición» nor «Brecha vs. podio» is offered.
2. **Given** a championship result, **When** the parent views its card, **Then** it shows puesto, parrilla, percentil and brecha vs. mediana, and no winner or podium gap.
3. **Given** an analysis awaiting approval, **When** the parent opens «Análisis IA», **Then** it is not visible; only approved analyses are listed, each marked as AI-generated and reviewed by the coach.
4. **Given** a DNF result, **When** a parent sees it, **Then** it reads «No terminó» (never "DNF").
5. **Given** a parent with two children, **When** they open either child's «Carreras», **Then** only that child's data is shown, and requests for another athlete are denied.
6. **Given** the old address `…?tab=ai-analysis` from an email already sent, **When** the parent opens it, **Then** it resolves to «Carreras › Análisis IA».

---

### User Story 5 - Home tells the coach what is pending and takes them there (Priority: P2)

The coach's Home «Pendientes» lists:
- results to import;
- identity decisions to make;
- analyses awaiting approval;
- analyses that went stale after a corrected PDF.

Every row lands on a screen that shows exactly the items it counted.

**Why this priority**: "what do I still have to do?" is the coach's third question. Today one row lands on a page that does not show stale analyses, and two kinds of pending work have no signal at all.

**Independent Test**: create one item of each kind, follow each Home row, and verify that the destination lists exactly that item.

**Acceptance Scenarios**:

1. **Given** 2 analyses awaiting approval, **When** the coach opens Home, **Then** «Pendientes» shows a row with count 2, and following it lists those 2 analyses.
2. **Given** an analysis that became stale because its competition's results were revised, **When** the coach follows the «análisis desactualizados» row, **Then** the destination lists that analysis with an action to re-run or dismiss it.
3. **Given** no pending work of a kind, **When** Home loads, **Then** that row is omitted or shows zero consistently, never an error.

---

### User Story 6 - One area, one vocabulary (Priority: P3)

The menu entry reads «Competencias» and has three sections: the competitions list with each competition's detail, «Temporada», and «Cargas e identidades». The competition detail has the tabs Información · Resultados · Clasificación · «Circuito y condiciones» · Análisis IA.
- Every label follows one glossary.
- Jargon is gone.
- Interactive targets in the area header and on the approval card are at least 48 px.
- Every old address keeps working.

**Why this priority**: this matters for learnability and trust, but it is mostly naming and layout. The stories above deliver the value, and this one makes it coherent.

**Independent Test**: from the menu, reach every race-related coach task in at most two steps; audit labels against the glossary; open every legacy address in the compatibility list.

**Acceptance Scenarios**:

1. **Given** the coach menu, **When** it renders, **Then** it shows «Competencias» (not «Válidas») and the three sections are reachable from it.
2. **Given** the address `/competitions/insights/season/2025`, **When** it is opened, **Then** it redirects to «Temporada» 2025.
3. **Given** the old identity-review, historical-load or unlinked-competitors addresses, **When** they are opened, **Then** they land on the matching part of «Cargas e identidades».
4. **Given** a competition's detail, **When** the coach opens it, **Then** course profile and conditions appear together in «Circuito y condiciones».

---

### Edge Cases

- An athlete with no race results: «Carreras» shows an empty state that explains why, with no chart and no error.
- An athlete with only championships: «Progresión» shows only cards and no line.
- An athlete with a single season.
- A category with fewer than 5 timed finishers: percentile and median gap read «sin dato» on every screen.
- Ties in time: tied athletes get the same percentile.
- One very slow finisher stretches the time range, so everyone else's percentile moves toward 100. This is expected with the owner's chosen formula; the median gap is the metric that resists outliers.
- The winner: «Brecha vs. 1.ª posición» is 0.0 %. The median gap is still shown for them.
- An athlete who lost laps: counted in «Parrilla», excluded from time-based percentile and median, and shown with a plain-words status.
- DNS, DNF and DSQ: no metrics; statuses in words for families.
- A candidate that involves a competitor of this import and also one of another import: it blocks this import.
- A new candidate that appears while the coach is inside an import: the gate is evaluated at commit time, and the coach is told.
- An import left in progress for a long time: it stays resumable until the coach commits or discards it.
- Stale analyses when the corrected PDF changes nothing the analysis used: they are still listed, and the coach can dismiss them.
- A parent following a coach-only link (for example «Comparar»): they get the default family view, never an error or coach data.
- Old links in emails already sent, bookmarks, and navigation in the end-to-end test suites: all resolve.
- Family figures that change because percentile becomes time-based: families are told through the bitácora, as described under Communication below.

## Requirements *(mandatory)*

### Functional Requirements

**Area and vocabulary**

- **FR-001**: The race area MUST be named «Competencias» in the main menu, page titles, breadcrumbs and Home shortcuts. «Válidas» MUST NOT be used as an area name.
- **FR-002**: UI copy in the area, the athlete tab and family race surfaces MUST follow one glossary.
  - «Competencia» = any race event.
  - «Válida» = a numbered round of a cup.
  - «Campeonato» = a standalone race that is not compared with válidas.
  - «Parrilla», «Puesto», «Percentil», «Brecha vs. mediana», «Brecha vs. 1.ª posición» and «Brecha vs. podio» each have exactly one meaning (FR-020).
  - Synonyms currently in use («Gap al P1», «Diferencia al podio», «Pelotón») MUST be removed.
- **FR-003**: Race statuses shown to families MUST be in plain Spanish («No terminó», «No salió», «Descalificado», «Perdió vueltas»), never as raw codes. Priority codes MUST be spelled out or explained wherever they are shown.
- **FR-004**: Technical jargon MUST be removed from coach-facing copy in the area (for example «Editar metadata» → «Editar datos»; internal AI stage names replaced with a plain description of what the coach must decide).
- **FR-005**: «Competencias» MUST contain exactly three sections: the competitions list with each competition's detail, «Temporada» (season panorama), and «Cargas e identidades». Every race-related coach page MUST be reachable from the menu through these sections; no orphan pages.
- **FR-006**: The competition detail MUST offer these tabs:
  - Información;
  - Resultados;
  - Clasificación, only for cup válidas;
  - «Circuito y condiciones», one tab combining course profile and conditions;
  - Análisis IA, coach only.

**Athlete «Carreras» tab**

- **FR-010**: The athlete record MUST have exactly one race tab, «Carreras», for coach and family, replacing «Insights IA» and the current «Carreras».
- **FR-011**: «Carreras» MUST open on «Progresión» unless the address asks for another view.
- **FR-012**: «Progresión» MUST show all loaded seasons:
  - cup results as a continuous line with category-change markers;
  - championships as separate stat cards;
  - the ability to narrow to one competition group.
  
  The default metric MUST be «Brecha vs. mediana» for both roles. Coaches MAY switch to Percentil, Puesto, «Brecha vs. 1.ª posición» and «Brecha vs. podio». Families MAY switch only among «Brecha vs. mediana», Percentil and Puesto.
- **FR-013**: «Análisis IA» for the coach MUST list analyses awaiting approval first, then the latest approved analysis, then the history. Launching an analysis, the analyst chat and the season summary MUST live in this view.
- **FR-014**: «Análisis IA» for families MUST show only coach-approved analyses. Each one MUST be marked as generated with AI and reviewed by the coach. Pending, rejected, flagged or fallback analyses MUST never be shown to families.
- **FR-015**: «Comparar» (distribution and comparator) MUST be coach-only and MUST NOT be reachable by families, including by direct address.
- **FR-016**: Each view MUST be addressable. A link that names an analysis MUST open «Análisis IA» with that analysis expanded, for either role, within that role's permissions.
- **FR-017**: Every progression point, championship card and result row MUST link to its competition: the competition detail for coaches, the family results page for families.
- **FR-018**: A family MUST be able to reach their child's «Carreras» tab in at most two taps from the family home.

**Metrics — one definition, one source**

- **FR-020**: Each metric MUST have a single definition used on every surface: the athlete tab, the championship card, the competition detail, «Temporada», family newsletters and family PDFs, and the metrics context given to the AI analyst.

  | Metric | Definition | Shown when |
  |---|---|---|
  | **Parrilla** | Classified finishers of the category, including those who lost laps | — |
  | **Percentil** (time-based) | Where the athlete's time falls between the fastest and the slowest full-distance times of the category: 100 × (1 − (own time − fastest) ÷ (slowest − fastest)). 100 = fastest, 0 = slowest; equal times get equal values. This is the formula the coach requested on 2026-05-25 for the evolution chart, now applied everywhere | ≥ 5 full-distance timed finishers, for an athlete who finished the full distance with a time |
  | **Brecha vs. mediana** | Percentage difference between the athlete's time and the median time of the category's full-distance timed finishers; negative = faster | Same condition as percentile |
  | **Brecha vs. 1.ª posición** | Percentage over the category winner's time | Coach only |
  | **Brecha vs. podio** | Difference to the third-placed time | Coach only |
- **FR-021**: These values MUST be produced once, server-side, from a single calculation. No screen MAY compute its own version.
- **FR-022**: Families MUST NOT see the gap to the winner or to the podium on any structured surface: in-app views, cards, charts, tables, newsletters, family PDFs or notifications. For approved AI analyses shown to families (owner decision 2026-09-23), the family view MUST hide the analysis's structured gap-to-winner and gap-to-podium fields. When the family-visible text of an analysis mentions the gap to the leader, the winner, third place or the podium, the coach MUST see a warning before approving it and MUST be able to request a revision instead. The analyst prompts are not changed.
- **FR-023**: When unifying the definitions changes a figure that families have already seen (mainly percentile), families MUST be told in plain language through the next bitácora. The note is drafted for the coach, who reviews it; it is never sent automatically.

**Loads and identities**

- **FR-030**: At commit time, an import MUST be blocked only by pending identity decisions that involve at least one competitor of that import. Pending decisions about other imports MUST NOT block it. Every commit MUST remain gated by coach-reviewed identity for its own competitors.
- **FR-031**: When an import is blocked, the coach MUST see how many decisions are pending for that import and a direct path to them, instead of a generic error.
- **FR-032**: An import in progress MUST be resumable at the step where it was left, with its uploaded file and choices intact, until the coach commits or discards it. Leaving the import (for example to resolve identities) MUST NOT lose work.
- **FR-033**: «Cargas e identidades» MUST be one inbox that shows imports in progress, identity decisions and unlinked competitors, for current and historical seasons alike. The menu entry MUST carry a badge with the number of items needing action.

**Pending work**

- **FR-040**: Home «Pendientes» MUST show counts for:
  - results to import;
  - identity decisions to make;
  - analyses awaiting approval;
  - stale analyses.
- **FR-041**: Each «Pendientes» row MUST land on a screen that lists exactly the items it counted. The stale-analyses destination MUST offer re-running or dismissing each item.
- **FR-042**: Approving an analysis MUST NOT send any email or other automatic message to families. The approval control MUST state that approval makes the analysis visible to the family in the app. (Behaviour delivered in phase 0; this feature keeps it in the new structure.)

**Compatibility**

- **FR-050**: Every previous address MUST keep working through a permanent redirect or alias to its new place:
  - the athlete tabs `?tab=ai_analysis` (coach) and `?tab=ai-analysis` (family);
  - the email route for a specific analysis;
  - the old season-panorama address;
  - the old identity-review, historical-load and unlinked-competitors addresses.
- **FR-051**: Addresses under `/competitions` MUST keep their current form. Only the new sections gain addresses.

**Access, privacy and performance**

- **FR-060**: Parents MUST only ever see data about their own athletes in every view of «Carreras», and requests for other athletes MUST be denied. Every changed server access path MUST have at least one denied-path test.
- **FR-061**: No identifiable data of a minor MAY appear in logs, error messages, fixtures committed to the repository, or AI prompts introduced by this feature.
- **FR-062**: The family «Carreras» tab MUST paint its first view without loading the other views. Charts and the analysis list MUST load only when their view is opened.
- **FR-063**: Every interactive target in the «Competencias» header, the «Carreras» tab and the approval card MUST be at least 48 × 48 px. The new and changed surfaces MUST meet WCAG 2.1 AA.

### Key Entities

- **Competition (competencia)**: a race event on a date with categories and results. It is either a **válida** (a numbered round of a cup series) or a **campeonato** (a standalone race). It may be linked to a calendar event.
- **Result**: one competitor's outcome in one category of one competition: status, position, time, points. It is the input to every metric.
- **Metric set**: for one result, the parrilla, time-based percentile, median gap, gap to the winner and gap to the podium, each with its visibility rule by role and its minimum-field condition.
- **Import**: an official results file going through upload → review → commit. It can be in progress (resumable), committed or discarded.
- **Identity decision**: a coach-reviewed question of whether two competitor records are the same person. It is linked to the competitors, and through them to the imports it affects.
- **AI analysis**: a generated reading of one athlete's race or season, with a lifecycle: pending approval → approved or rejected; approved → stale when the underlying results are revised. Families see only approved analyses.
- **Pending item**: anything that needs the coach's action (results to import, identity decision, analysis awaiting approval, stale analysis). It is counted on Home and listed at its destination.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coach can reach every race-related task from the menu in at most 2 navigation steps. Zero race-related coach pages lack a menu path.
- **SC-002**: A cross-screen audit of every athlete result in 2024–2026 finds 0 mismatches in parrilla, percentile or any gap between the screens that show it.
- **SC-003**: A válida whose competitors have no pending identity decisions is committed successfully in 100 % of trials while other imports keep pending decisions. 0 re-uploads are needed after leaving an import to resolve identities.
- **SC-004**: An audit of every family-facing surface finds 0 occurrences of the gap to the winner or to the podium. That includes every view of «Carreras», the championship cards, the family competition page, newsletters and family PDFs, with the AI text scope set by FR-022.
- **SC-005**: 100 % of Home «Pendientes» rows land on a screen that lists exactly the counted items.
- **SC-006**: 100 % of the legacy addresses listed in FR-050 resolve to their intended view, including links in emails already sent.
- **SC-007**: On a mid-tier Android device over simulated 3G, the family «Carreras» tab reaches its largest content paint in ≤ 3.5 s. No other view's data is requested before that view is opened.
- **SC-008**: The blocking AI analysis quality evaluation still passes its threshold (composite ≥ 0.75) and does not fall more than 0.03 below its last recorded baseline after the metric unification.
- **SC-009**: In a hands-on check with the coach on a tablet, at least 4 of 5 representative tasks are completed on the first attempt without guidance: load a válida, resolve an identity decision, find an athlete's progression, approve an analysis, and open the season view.
- **SC-010**: An automated accessibility audit of the new and changed screens reports zero WCAG 2.1 AA violations. A measurement of the targets named in FR-063 finds 0 smaller than 48 px.

## Communication

Families will notice two changes: the merged «Carreras» tab, and percentile figures that move because percentile becomes time-based. The coach announces both in the next bitácora with a short, plain-language note that this feature drafts (FR-023). The coach reviews the note before it goes out. This should be coordinated with the still-pending feature-044 announcement to families, so they receive one message rather than two.

## Assumptions

- The phase-0 fixes listed in Context are in place. This feature preserves them and does not rebuild them.
- The AI pipeline, its prompts and the golden-eval dataset are out of scope. The analyst receives its metrics from the unified definitions (FR-020), and SC-008 guards against regression. The FR-022 approval warning inspects the text the family would see; it does not change generation.
- «Comparar» and the competition-level «Análisis IA» remain coach-only, as they are today.
- «Clasificación» (cup standings) applies only to cup válidas. Championships have no standings tab.
- «Temporada» keeps today's season-panorama content. Only its name, place and address change, and the old address redirects.
- The minimum field of 5 timed finishers, already used for percentile and median gap, applies to every surface.
- An import in progress is kept until it is committed or discarded. No automatic expiry is introduced.
- Addresses for the three sections are user-visible bookmarks. The old ones redirect permanently, and API addresses are not affected.
- The coach and admin roles see the same race surfaces. Parents see the family variant. Athletes have no race surface.
- The data-privacy audit is mandatory before implementation closes, because the feature reads athlete-identifiable race data.

## Out of Scope

- API address prefixes.
- AI prompts and the analysis pipeline. FR-022 adds only a view filter and an approval-time warning.
- The golden-eval dataset.
- New metrics beyond the glossary.
- Average speed.
- Course-profile computation.
- Standings rules.
- Anything about sending emails; after phase 0 no race email is sent automatically.
