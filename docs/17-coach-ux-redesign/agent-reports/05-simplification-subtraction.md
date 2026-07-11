# Agent report 05 — Simplification / subtraction audit

> Panel: coach UX audit 2026-07-11 · Agent: general-purpose, product-subtraction lens (Sonnet) · Read-only (grep/glob/read only).
> Baseline: `App.tsx` has 68 `<Route>` elements (22 lazy chunks); `AppShell.tsx:37-192` renders 12 flat coach nav items; 412 non-test `.ts/.tsx` files under `src/`.

---

## Kill list (REMOVE, ranked by confidence)

### 1. Gymkhana circuit composer — `/technique/composer` + `components/technique/composer/*`
- **Evidence**: Zero in-app links anywhere. `grep -rn "composer"` over `technique/CatalogPage.tsx` and `components/technique/{CatalogGrid,ExerciseCard,FilterBar,SessionAssembler,ExerciseFormDialog}.tsx` → no matches. The only `to="/technique/composer..."` reference is the page linking to **itself** for a re-edit round-trip (`ComposerPage.tsx:322`). Route at `App.tsx:130-135,737-753`.
- **User-visible impact**: None — nobody can reach it today.
- **Code deleted**: `ComposerPage.tsx` (461L), `composer/AccessibleControls.tsx` (385L), `KonvaCanvas.tsx` (502L), `piiGuard.ts` (68L) = **1,416 LOC** + tests (`Composer.a11y.test.tsx` 195L, `Composer.roundtrip.test.tsx` 206L) = 401L. Also drops **`konva` + `react-konva`** from `package.json:71,79` — a canvas-rendering dependency pair carried for an unreachable feature.
- **Risk**: Low. `AssembleSessionInput.combined_layout`/`combined_exercise_id` (`types/technique.types.ts:159-170`) are optional fields — removing the composer doesn't break session assembly, it removes an optional enhancement nobody can trigger.
- **Migration**: Delete route + lazy import + dir. No redirect needed (never linked).

### 2. Anxiety on-demand interpretation UI — `AnalyzeButton.tsx` + `InterpretationPanel.tsx` + `useInterpretation`
- **Evidence**: `components/anxiety/AnalyzeButton.tsx` (54L) and `InterpretationPanel.tsx` (90L) have **zero references anywhere** — not imported by any page, no test file. `hooks/anxiety/useAnxietyAssessments.ts:84-93` (`useInterpretation`) is consumed only by `AnalyzeButton.tsx:4,19`. The rendered dashboard components (`IndividualPanel`, `GroupPanel`, `AnxietyDashboardPage`) contain no "Interpretación"/"Analizar" text at all.
- **Corroboration**: `docs/implementation-status.md:445-446` lists both as delivered for spec 017 — a **forgotten integration**, not deliberate orphaning.
- **User-visible impact**: None currently — the "on-demand LLM interpretation" acceptance criterion is invisible to the coach today either way.
- **Code deleted**: 144 LOC (components) + `useInterpretation` (~10L) + `interpretAssessment` in `api/anxiety.ts:85-94` if nothing else needs it.
- **Risk**: None to tests. **Caveat**: real backend investment exists behind it (`app/services/ai/use_cases/anxiety_interpretation.py`, guardrail scrub, rule fallback, part of spec 017's 51 backend tests). The team should explicitly choose: **wire it into `IndividualPanel`** (~1 day, all pieces exist) **or** delete frontend+backend together. Don't leave it half-built.

### 3. `components/ai/UploadZone.tsx` — superseded upload widget
- **Evidence**: Only reference is its own test. The reachable import flow (`ImportWizard` → `/competitions/import`) uses `components/competitions/import/RaceUploadZone.tsx` (imported `ImportWizard.tsx:38`, used `:1299,1310`). `docs/implementation-status.md:102` documents the 007-consolidation codemod that created the replacement — the old file was never deleted.
- **Code deleted**: 165L + 84L test. **Risk**: None. **Migration**: straight delete.

### 4. `/intervals/templates` (`TemplateLibraryPage.tsx`) — unreachable, zero unique capability
- **Evidence**: `grep -rn "/intervals/templates"` → only `App.tsx` and the page's own docblock. The page (36L) renders `TemplatePicker` in browse-only mode (`TemplatePicker.tsx:155-165`) — no create/edit/archive actions; everything it can do, the embedded `TemplatePicker` (with `trainingSessionId`) already does from session detail (`TemplatePicker.tsx:6-12`).
- **Code deleted**: 36L; `routes/intervals/` contains *only* this file, so the directory disappears. No dedicated test.
- **Risk**: None. **Migration**: delete route + lazy import (`App.tsx:173-177,856-871`) + dir.

### 5. AI Insights Hub duplicate pages — `InsightsHubPage`, `ClubInsightsPage`, `AthleteInsightsPage`
- **Unreachable by design, not accident**: two tests explicitly *assert the absence* of any sidebar link (`__tests__/competitions-routing.test.tsx:139` — "NO hay ningún enlace al sidebar que apunte directamente a /competitions/insights"; `AppShell.test.tsx:133`). `CompetitionsListPage.tsx` (688 lines, full read) never mentions "insights". Only inbound path: the legacy `/coach/race-analysis` 301 (`App.tsx:664-670`), itself unlinked.
- **The surviving content duplicates already-reachable homes**:
  - `ClubInsightsPage.tsx:7` — "Absorbe la antigua `ClubInsightsByRacePage`"; but `components/competitions/tabs/InsightsTab.tsx:5-6` says of itself: **"Es la misma vista que ClubInsightsByRacePage pero incrustada dentro de un tab"** (reachable via Competencias → race → "Insights IA" tab). Both independently reimplement a near-identical `InsightCard` (`ClubInsightsPage.tsx:34-122` vs `InsightsTab.tsx:57-207`).
  - `AthleteInsightsPage.tsx:7-8` — "Reutiliza `AthleteAIAnalysisTab` en modo coach" — the same component `AthleteDetailPage.tsx:790` mounts for the reachable `ai_analysis` tab.
- **Code deleted**: 504L pages + 317L tests. **Risk**: Medium on test/routing bookkeeping only (`competitions-routing.test.tsx`, `competitionsRedirects.test.tsx`, `T049-wave-f-cleanup.test.tsx` assert `/competitions/insights*` behavior). No coach-workflow risk.
- **Migration**: Retarget `/coach/race-analysis` → `/competitions` (or the relocated season page). **`SeasonInsightsPage` is NOT part of this kill** — see Merge #4.

### 6. Technique session builder — `/technique/sessions/new` (borderline: remove or fold into wizard)
- **Evidence**: `grep -rn "technique/sessions/new"` outside tests/App.tsx → **zero matches**. `technique/CatalogPage.tsx` has no `Link`/`to=` at all. `SessionAssembler.tsx` (682L) independently re-implements the session-metadata form the wizard owns (`scheduled_date`, `scheduled_start_time`, `duration_min`, `location`, `technical_focus`, `objectives`, roster — `:38-51`) and calls a **different** creation endpoint (`POST /api/technique/sessions`) — a second, drifting way to create the same `training_sessions` row (no route-file upload, no AI-assistant path).
- **Code deleted**: `SessionBuilderPage.tsx` (185L) + `SessionAssembler.tsx` (682L) = 867L + `SessionAssembler.test.tsx` (759L).
- **Risk**: Low to delete (nothing points at it). Medium if merged instead.
- **Migration**: (a) delete outright, or (b) if "compose a session from drill segments" is genuinely valued, fold into the wizard as an alternate mode, then delete the standalone route. The current state (built, tested, unreachable, schema-duplicating) is not tenable.

---

## Merge list

### 1. `ConfirmDeleteDialog` → `ConfirmModal`
- **Survives**: `ConfirmModal.tsx` (79L, Radix `Dialog`, has `confirmDanger` at `:31`). **Removed**: `ConfirmDeleteDialog.tsx` (134L) — hand-rolled overlay (`:47-55`), **no Escape handler, no backdrop-click dismissal** — a real a11y gap, not just duplication.
- **Call sites**: `ConfirmDeleteDialog` ×5 (`ParentDetailPage`, `CompetitionsListPage`, `CompetitionDetailPage`, `AthleteDetailPage`, `AthleteFormPage`); `ConfirmModal` ×6. Add an optional `subject` highlight-box prop, repoint the 5.
- **Risk**: Low-medium (test selectors).

### 2. "Reportes mensuales" + "Boletines Mensuales" → one nav entry
- **Genuinely different content, verified**: `ReportsListPage`(488L)/`ReportDetailPage`(712L) = club-level institutional funder report (`BLOCK_LABELS`, `ReportDetailPage.tsx:65-74`); `AthleteNewslettersDashboardPage`(737L)/`AthleteNewsletterDetailPage`(706L) = per-athlete parent newsletters. Not redundant content — only the **nav entry points** merge (`AppShell.tsx:85-92` + `:93-101` are adjacent, confusingly similar items). Sidebar 12 → 11; zero functional loss.
- **Risk**: Low — one thin hub/grouping + sidebar edit.

### 3. Technique/Strength per-athlete progress pages → `AthleteDetailPage` tabs
- **Intended-but-missing integration**: both pages render a "← Volver al perfil del deportista" breadcrumb to `/athletes/${athleteId}` (`technique/AthleteProgressPage.tsx:108-115`, `strength/AthleteProgressPage.tsx:111-118`) — their own design assumes arrival *from* the athlete profile. **No forward link exists**: `grep -n "Progreso|progress" routes/athletes/AthleteDetailPage.tsx` → zero hits; neither catalog links them either. Confirmed via `docs/implementation-status.md:477` (F006) with no linking mentioned.
- **Survives**: `SkillProgressBoard` + `ProgressNotesBoard` — both **already `React.lazy`-loaded** by their pages, so embedding as tabs costs nothing on the initial bundle. **Removed**: the two wrapper routes (267L combined).
- **Caution**: `AthleteDetailPage`'s `Tab` type already has 6 values rendered as a flat wrapped button row (`:570-634`). Adding 2 more → 8 is too many. Recommend **one** combined "Progreso" tab with an internal Técnica/Fuerza toggle.
- **Risk**: Low functionally; tab-crowding is the design risk to manage.

### 4. Season Insights — relocate entry point, delete the now-empty hub shell
- Companion to Kill #5: `SeasonInsightsPage.tsx` (196L) is the **one genuinely unique** view in the hub (season-long per-athlete table: races run, podiums, best position, points — available nowhere else). Don't leave its only entry point behind a deleted hub.
- **New home**: a "Panorama de temporada" link on `CompetitionsListPage.tsx`'s header (next to "Cargar resultados"/"Sin enlazar", `:193-211`), keeping the existing route path; relocate the file out of `routes/competitions/insights/` (dir then deletable) to `routes/competitions/SeasonInsightsPage.tsx`.
- **Risk**: Low — one link, one file move, one test import-path update (`SeasonInsightsPage.test.tsx`, 94L).

### 5. `components/race/*` → `components/competitions/`
- `components/race/` holds only 4 actively-used files (`EditConditionsDialog`, `EditResultNoteDialog`, `RaceConditionsCard`, `UnlinkedCompetitorsTab`) — split from `components/competitions/` purely for historical naming (backend "race" vs product "Competencias", 007 consolidation). Move, update imports, delete the dir. Zero behavior change.

### 6. `components/shared/PHVBadge.tsx` → `components/athletes/`
- `components/shared/` contains exactly one component + test — a whole directory for one file, no documented distinction from `common/`. `PHVBadge` is an athlete/PHV domain concept used by 5 athlete-domain files. Move, fix imports, delete `components/shared/`.

### 7. Duplicated `validaLabel` helper + stale `sequence_number===99` checks
- The same "válida N / Cto. Departamental" label logic is independently reimplemented in ≥4 places, all still branching on the **retired** `sequence_number===99` sentinel (CLAUDE.md feature-014: "Do not use `sequence_number=99` in new code" — replaced by `race_series.kind`):
  - `lib/insights.ts:107-112` (`validaLabel`, exported, used by insights surfaces)
  - `AthleteAIAnalysisTab.tsx:89-94` (private near-identical copy)
  - `lib/raceCalendar.ts:149-159` (`getValidaLabel`, roman-numeral variant)
  - `MiniSparkline.tsx:38` and `InsightsTimeline.tsx:195` (inline `=== 99` checks)
- **Migration**: consolidate on the exported `validaLabel`; prefer `series_kind === "championship"` (available since feature 016) over the magic number. Pure hygiene.

---

## Demote list

### 1. "Ansiedad competitiva" — flat top-level → grouped/secondary placement
- Episodic (pre-competition, consent-gated, age-gated ≥13), not a daily workflow; legitimate club-wide entry (group triage) so it can't be removed. Group under a secondary section rather than the flat list. **Repositioning only — do not touch reachability**; the feature is consent-gated and psychologically sensitive.

### 2. `ProjectProfilePage` — already well-demoted; optional further step
- Correctly off-sidebar, reachable via `ReportsListPage.tsx:398`. Optional: convert the single settings form (445L) to a modal/dialog from `ReportsListPage`; current placement is not a problem.

### 3. (Lower confidence) "Técnica" + "Fuerza" → single "Bibliotecas" nav entry
- Structurally identical catalog-browse pages supporting session-building rather than independent daily destinations; much of each module's sub-surface is unreachable anyway. Sidebar 12 → 11 (→ 9 with the other demotes). **Lower confidence** — a nav-taste call, not reachability-evidenced; Skills>fitness is a non-negotiable principle, so don't undersell either library's visibility if adopted.

---

## Keep-but-flagged (checked, justified — not removed)

| Item | Verdict | Evidence |
|---|---|---|
| Calendario vs Competencias | **Not a duplicate.** Deliberate FK link (feature 008) — calendar "competition" events carry `race_event_id`, hydrate from `race_events`, never re-entered. | `components/calendar/EventForm.tsx:37-38,189-191,257-316`; `CompetitionsListPage.tsx:625-636` |
| Padres pages vs athlete-detail guardian info | **Not a duplicate.** `LinkedParentsCard` is a collapsed peek (masked contact) + deep link to the full CRUD record; nothing independently re-editable. | `components/athletes/LinkedParentsCard.tsx:69-74,94-99,163-176` |
| Actividades review page vs per-athlete Strava tab | **Legitimate dual entry.** Global = weekly batch triage (~30-60 activities, docblock target <10 min); per-athlete = spot-check. Same `ActivityCard` with `canLink`, no logic duplication. | `ActivityReviewPage.tsx:1-16`; `AthleteDetailPage.tsx:137-145,352` |
| Onboarding module | **Actively wired.** Parent creation triggers an email invite consumed by the token-gated `/onboarding` flow. | `ParentFormDialog.tsx:147`; `ParentDetailPage.tsx:9` |
| `AIHealthPage` (admin-only) | Fine as-is — small, single-purpose, correctly scoped. | `routes/admin/AIHealthPage.tsx` |
| `BlockBuilderPage` (strength) | **Positive contrast case** — its docblock explicitly rejects duplicating session-creation UI, linking to the wizard instead (the opposite of technique's SessionBuilder problem). | `BlockBuilderPage.tsx:14-20` |
| Wave B/F legacy redirects + unused `GonePage.tsx` | **Working as designed.** Explicit test policy (`T049-wave-f-cleanup.test.tsx:4-18`) keeps them as 301s because external Spond/email deep links must keep working; the 410 flip is a documented future step. `GonePage` (52L) pre-built, harmless. | `App.tsx:202-210,521-524,664-670` |
| Manual "Enviar informe" button | Self-documented temporary state; the only TODO in the whole frontend. Low priority. | `AthleteDetailPage.tsx:428,635` |
| Multi-club surface | **None found.** No club-switcher, nothing requiring N-clubs infra in the frontend. | grep `selectedClub\|ClubSwitcher\|multiClub` → none |

---

## Estimated total reduction

| Dimension | Current | Kill list | Kill + Merge |
|---|---|---|---|
| Routes (`<Route>` in App.tsx) | 68 | 62 (−6) | 60 (−8, incl. 2 progress routes folded to tabs) |
| Sidebar items (coach) | 12 | 12 | 11 (Reportes+Boletines); 9 with optional demotes |
| Dirs removed/merged | — | `technique/composer/`, `routes/intervals/` | + `routes/competitions/insights/`, `components/shared/`, `components/race/` ≈ 5-6 |
| npm deps dropped | — | `konva`, `react-konva` | same |
| Production LOC removed | — | ≈3,100 | ≈**3,500** |
| Test LOC removed | — | ≈1,560 | similar + routing-guard test edits |

Directional, not exact — per the file-by-file figures above.

---

## Quick wins (≤1 day, do regardless of the bigger calls)

1. **Delete `/intervals/templates`** — route, lazy import, `routes/intervals/` dir. ~30 min.
2. **Delete `components/ai/UploadZone.tsx` + test** — superseded. ~15 min.
3. **Anxiety dead code** — delete `AnalyzeButton`/`InterpretationPanel`/`useInterpretation`/`interpretAssessment`, **or** spend the same day wiring `AnalyzeButton` into `IndividualPanel` (backend ready). Either beats half-built. ~30 min / ~1 day.
4. **Move `PHVBadge` → `components/athletes/`**, delete `components/shared/`. ~1 h.
5. **Move `components/race/*` → `components/competitions/`**. ~2 h.
6. **Dedupe `validaLabel`/`getValidaLabel` + drop `=== 99` checks** per the CLAUDE.md retirement note. ~half day.
