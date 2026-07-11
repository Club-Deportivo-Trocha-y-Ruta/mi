# Contract — Removal & Redirect Manifest

Authoritative table of every route/directory/dependency this feature removes or relocates, its redirect/tombstone behavior, and the surviving home of the capability. Evidence and rationale: `research.md` R1–R2, R6. Nothing in this table changes stored data (see `data-model.md`).

## Removed routes

| Route (`App.tsx`) | Page component | Surviving home of the capability | Redirect |
|---|---|---|---|
| `/technique/composer` | `ComposerPage` | None — zero coach-visible capability lost (audit: zero inbound links, ever) | None — never linked, so nothing to redirect |
| `/technique/sessions/new` | `SessionBuilderPage` | Session assembly stays available via session planning (interval/strength attach today; unified technique attach lands in feature 032) | None — zero inbound links |
| `/intervals/templates` | `TemplateLibraryPage` | `TemplatePicker` embedded in session detail (`components/intervals/TemplatePicker.tsx`, `trainingSessionId` mode) — already the same capability, already reachable | None — zero inbound links |
| `/competitions/insights` | `InsightsHubPage` | `/competitions` (Competencias list) | **`/coach/race-analysis` retargeted** from `/competitions/insights` → `/competitions` (`App.tsx:664-670`) |
| `/competitions/insights/club` | `ClubInsightsPage` | `InsightsTab` inside `/competitions/:id` (existing "Insights IA" tab — the audit confirms it is "la misma vista... incrustada dentro de un tab") | None — no external redirect pointed here |
| `/competitions/insights/athletes/:id` | `AthleteInsightsPage` | `/athletes/:id?tab=ai_analysis` (`AthleteAIAnalysisTab`, same component reused in coach mode) | None — no external redirect pointed here; **internal** links fixed instead (see below) |
| `/technique/athletes/:athleteId/progress` | `technique/AthleteProgressPage` | `/athletes/:id?tab=progreso` (Técnica side of the new toggle) | None — audit confirms zero forward links exist today (page's own breadcrumb only points away) |
| `/strength/athletes/:athleteId/progress` | `strength/AthleteProgressPage` | `/athletes/:id?tab=progreso` (Fuerza side of the new toggle) | None — same |

**Relocated, not removed**: `/competitions/insights/season/:year` (`SeasonInsightsPage`) — URL path unchanged; file moves from `routes/competitions/insights/SeasonInsightsPage.tsx` to `routes/competitions/SeasonInsightsPage.tsx`; new entry point added on `CompetitionsListPage`'s header action row. Its two internal links to now-dead routes are fixed as part of this same change (see below) — without this, the surviving page would self-break.

## Internal links fixed (within surviving code, not user-facing redirects)

| File : line | Old target | New target | Why |
|---|---|---|---|
| `SeasonInsightsPage.tsx:29-36` (back-link) | `/competitions/insights` | `/competitions` | Old target deleted in this feature |
| `SeasonInsightsPage.tsx:156-158` (row click) | `` `/competitions/insights/athletes/${id}` `` | `` `/athletes/${id}?tab=ai_analysis` `` | Old target deleted in this feature; this is the page's primary interaction |
| `routes/GonePage.tsx:14` (default prop, optional/low-priority) | `/competitions/insights` | `/competitions` | Cosmetic — `GonePage` is unwired into any route today either way |

## External-facing redirect (unchanged mechanism, new destination)

`/coach/race-analysis` (`App.tsx:664-670`) stays a `<Navigate replace>` (301-equivalent) per the existing Wave B/F policy (`T049-wave-f-cleanup.test.tsx` docblock — the 410 flip is a deliberate later step, not this feature's job). Only its destination changes: `/competitions/insights` → `/competitions`.

`/training/races/:raceEventId/club-insights` (`ClubInsightsRedirect`, `App.tsx:202-210`) is **untouched** — it targets `/competitions/:id?tab=insights`, the `InsightsTab` inside `CompetitionDetailPage`, which is not part of this removal.

## Directories removed entirely

| Directory | Reason |
|---|---|
| `components/technique/composer/` | Only consumer (`ComposerPage`) removed |
| `routes/intervals/` | Contains only `TemplateLibraryPage.tsx` |
| `routes/competitions/insights/` | All 4 files either removed (3) or relocated out (1 — `SeasonInsightsPage`) |

**Not removed / do not confuse with the above**: `components/competitions/insights/` (a *different* directory — `AnalyzeAthleteButton`, `GroupAnalysisPanel`, `GroupRunRow`, `StaleAnalysisBadge` — actively used by the surviving `InsightsTab`/`ResultsTable`). `components/shared/`, `components/race/`, and `components/anxiety/{AnalyzeButton,InterpretationPanel}.tsx` are also out of this removal (the anxiety pair is wired in, not deleted — see `contracts/anxiety-interpretation-ui.md`).

## Dependencies removed

| Package | `package.json` line (before removal) | Only consumer |
|---|---|---|
| `konva` | `:71` (dependencies) | `components/technique/composer/KonvaCanvas.tsx` |
| `react-konva` | `:79` (dependencies) | same |

Run `npm uninstall konva react-konva` after the `components/technique/composer/` directory is deleted, then confirm with `grep -rin "konva" frontend/src` (expect zero hits) and `npm run build` (bundle no longer contains a konva chunk).

## Capability-loss check (FR-010)

Every row above either has no coach-visible capability (never reachable) or an explicit surviving home. The only two *approved* capability changes in this feature are: (1) the gymkhana composer's drawing capability is gone with no replacement (decision D1, explicitly approved); (2) the standalone technique-session-assembly path is gone with no like-for-like replacement until feature 032 ships the unified attach flow (decision D4, explicitly approved, and the exercise catalog + session planning remain fully usable in the interim).
