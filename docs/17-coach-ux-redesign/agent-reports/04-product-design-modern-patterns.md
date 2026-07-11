# Agent report 04 — Modern product design (dataviz skill applied)

> Panel: coach UX audit 2026-07-11 · Agent: general-purpose, senior product-design lens (Sonnet) · Read-only.
> The `dataviz` design skill (`choosing-a-form.md`, `color-formula.md`, `marks-and-anatomy.md`, `interaction.md`, `anti-patterns.md`, `palette.md`) was loaded and applied throughout — cited inline wherever it drives a recommendation. `docs/05-design-system/design.md` treated as the base visual language.

## What exists today (per surface)

### 0. The elephant in the room: three unreconciled color systems

- **Documented system** (`docs/05-design-system/design.md:24-42`): pure grayscale — charcoal `#242424`, mid-gray `#898989`, white, one link-blue accent. "Color is treated as a foreign substance."
- **Implemented tokens** (`frontend/src/style.css:22-46`): a *different* charcoal (`#2f2f2f`), a *different* mid-gray (`#717171`), plus an entire brand kit the design doc never mentions — `--color-primary: #20b7c9` (teal), `--color-accent: #8be000` (lime). The comment literally labels it "Trocha y Ruta Cycling Kit" (`style.css:22`) — a brand palette deliberately layered on top of the Cal.com monochrome spec without updating the spec.
- **The lime accent is dead code.** `grep -r "bg-accent|text-accent|accent-dark|accent-light"` across `frontend/src` returns **zero** matches outside `style.css` itself.
- **Chart colors are a fourth, ad hoc system**, hardcoded per-chart in `DistributionChart.tsx` and `EvolutionChart.tsx` — matching none of the above.
- **Badge semantic colors** (`components/ui/badge.tsx:26-35`) are literal Tailwind utilities (`bg-green-100 text-green-800`, `bg-amber-100 text-amber-900`, `bg-blue-100 text-blue-900`) with **no** corresponding `--color-success/-warning/-danger` custom properties — the semantic layer doesn't exist as tokens, only implicit and scattered.

**Cal Sans is never actually loaded.** `style.css:6-11` only registers `Inter Variable`; no Cal Sans file anywhere in the repo (confirmed via filesystem search for `*.woff*`). Yet **~30+ components** hardcode `style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}` inline on every H1/H2/card title — e.g. `DashboardPage.tsx:13`, `SessionsListPage.tsx:40`, `AthletesListPage.tsx:76`, `CompetitionsListPage.tsx:184`, `CalendarPage.tsx:73`, `AthleteDetailPage.tsx:481,681,733,752`, `SessionDetailPage.tsx:561`, `CompetitionDetailPage.tsx:443`, `InsightsHubPage.tsx:40,68,103`, `SessionAssistantPage.tsx:89`, `AthleteAIAnalysisTab.tsx:228`, `GroupAnalysisPanel.tsx:134`, `CompetitionChatPanel.tsx:233`. Every one silently falls back to `system-ui` at weight 600. The app has run its entire life without its signature display face and nobody noticed.

### 1. Coach home today (`/dashboard`)

`DashboardPage.tsx:5-72` is the entire landing experience: an H1, an error line, an empty-state line, **exactly 3 stat cards** (`:28-67`: "Total atletas", "Última evaluación", "Estado PHV" — plain values, no delta, no trend, no links), then `<MeasurementAlerts />` — the one genuinely good piece: status chips (`:90-113`), growth-spurt alert block (`:116-128`), sorted capped list (`MAX_VISIBLE = 8`, `:72`) linking to `/athletes/{id}`.

No next session, no race calendar/countdown, no pending imports, no AI status, no newsletter/consent inbox. For a coach who plans around the Copa Valle calendar, the home page has **zero awareness of the calendar, sessions, competitions, or AI subsystem**. Every stat card hand-types the identical triple-layer boxShadow string (`:32,41,55`; `MeasurementAlerts.tsx:134`) instead of the `<Card>` primitive that bakes it in (`ui/card.tsx:17-26`) — the exact string is duplicated in **13 files** app-wide.

### 2. Sessions

List page (`SessionsListPage.tsx:34-160`): header + filters + `animate-pulse` skeleton divs (not the `<Skeleton>` primitive) + inline red-text error with **no retry button** (`:70-74`) + dashed empty state + table. Zero icons — contrast with Competitions below.

Detail page (`SessionDetailPage.tsx:548-1157`) is the densest page in the app and has **no tabs at all**: header → Detalles → Recorrido (GPX) → Asistencia → Bloques de fuerza → Estructura de intervalos (with its own create/edit/template sub-flow, `:855-1037`) → Fotos y videos — seven stacked card sections in one continuous scroll (`sectionHeading` constant, `:115`, reused 7×). The opposite failure mode from the other detail pages: where Athlete/Competition reach for tabs, SessionDetail never does, despite being at least as dense.

### 3. Athletes

List page mirrors Sessions: same skeleton pattern, no-icon empty state (`:149-165`), no retry-on-error. Filters (`:94-128`) are plain `<select>`/`<input>`.

Detail page (`AthleteDetailPage.tsx:378-837`) has **6 tabs** (`VALID_TABS`, `:55-62`) — hand-rolled `<button>` elements (`:570-674`) with manual `tabClasses`/`tabStyle` helpers (`:504-515`): not Radix `Tabs`, no `role="tablist"`, no arrow-key navigation. The "Análisis IA" tab then mounts `AthleteAIAnalysisTab`, which has **its own internal 5-tab bar** (`panorama | history | evolution | distribution | launch`, `AthleteAIAnalysisTab.tsx:73,311-345`) — this time correctly built on the shared `<Tabs>` primitive. Two stacked tab levels, two different tab implementations, on one path.

### 4. Competitions — the most polished surface; the template for the rest

List page: lucide icons throughout (`:19-29`), responsive **table (≥md) / card (<md) split** (`:295-368`), real retry-on-error with spinner (`:241-265`), proper empty state with icon (`:268-292`), `DropdownMenu` kebab with disabled-state tooltips (`:580-687`), result count footer (`:372-376`).

Detail page (`CompetitionDetailPage.tsx:213-713`): **6 tabs** (`:87-111`) built on raw `TabsPrimitive` from `@radix-ui/react-tabs` (`:21,625-692`) — but with its **own** hand-rolled `TabTrigger` (`:158-173`) instead of the existing `ui/tabs.tsx` wrapper. Three tab bars in the app, three implementations.

This page also contains a **hand-rolled local toast** (`ToastBanner`, `:719-761`) whose own comment says it's a "patrón establecido en UnlinkedCompetitorsTab" — a copy-pasted ad hoc toast in at least two places because there's no toast library. `sonner` confirmed absent.

### 5. Calendar

`CalendarShell.tsx` (FullCalendar wrapper) is clean and correctly plumbs `dateClick` → `onDateClick(dateStr)` (`:71-73,97`). But `CalendarPage.tsx:55-57` receives it and does **nothing**:

```ts
const handleDateClick = useCallback((_dateStr: string) => {
  // Navigation happens via Link with query param — handled by EventFormPage
}, []);
```

The comment is aspirational — the body is empty. `EventFormPage.tsx:16` already reads `searchParams.get("date")` and prefills (the exact mechanism already consumed elsewhere for `race_event_id`, e.g. `CompetitionsListPage.tsx:629`). **Clicking a day is fully wired end-to-end except one line.**

### 6. AI surfaces — five+ entry points, five+ names

| Surface | File | Coach-facing name |
|---|---|---|
| Session-planning assistant | `SessionAssistantPage.tsx:87-92` | "Asistente IA" |
| Cross-race hub | `InsightsHubPage.tsx:38-46` | "Análisis IA carreras" |
| → Season card | `InsightsHubPage.tsx:65-71` | "Panorama de temporada" |
| → Club-by-race card | `InsightsHubPage.tsx:100-106` | "Análisis por válida" |
| Per-race tab | `CompetitionDetailPage.tsx:110` | "Insights IA" |
| Per-race group launch | `GroupAnalysisPanel.tsx:132-137` | "Análisis con IA" |
| Per-athlete tab | `AthleteAIAnalysisTab.tsx:230-231` | "Análisis IA del deportista" / "Análisis del coach" |
| Per-athlete launch button | `AnalyzeAthleteButton.tsx:90,199` | "Analizar" / "Re-ejecutar" |
| Race chat | `CompetitionChatPanel.tsx:235` | "Preguntar a la IA" |
| Live agent trace | `components/ai/AnalysisRunTimeline.tsx` (13-node LangGraph timeline) | *(unlabeled)* |
| HITL approval | `components/ai/HITLApprovalCard.tsx:1-15` | *(unlabeled)* |
| Competitive-anxiety assessment | `AnxietyDashboardPage.tsx` (nav "Ansiedad competitiva") | *(separate LLM surface)* |

**Genuine strengths to preserve, not replace:**
- `AnalysisRunTimeline.tsx` — best-in-class agent transparency: 13 named LangGraph nodes live as pending/running/done/error with per-node duration, `aria-live="polite"`, semantic `<ol><li>` (`:1-18`). Invisible outside the athlete "Lanzar" sub-tab.
- `HITLApprovalCard.tsx` (draft → critic feedback → Approve/Edit/Reject) — mature human-in-the-loop pattern.
- `StaleAnalysisBadge.tsx:38-77` + `AnalyzeAthleteButton.tsx:83-213` — well-designed freshness/re-run unit honoring the "D5: re-execution is MANUAL" rule (`:7-9`).
- `AnalyzeAthleteButton`'s freshness state model (`undefined`→launch, `null`→confirm, `string`→stale-relaunch, `:66-70`) — the state model to standardize on.

**Gaps:**
- **Six independent status-badge implementations**: `ConnectionStatusBadge.tsx:30-51` (Strava), `CompetitionStatusBadges.tsx:37-99`, `SessionStatusBadge.tsx:7-20` (hand-rolls a `<span>`, bypasses `Badge`), `lib/insights.ts:114-126` `confidenceVariant`/`confidenceLabel` **duplicated verbatim** in `AthleteAIAnalysisTab.tsx:75-87`, `AthleteNewslettersDashboardPage.tsx:47-56` `STATUS_CONFIG` (bypasses `Badge`), `ConsentStatusPanel.tsx:52-70` `STATE_CONFIG`. Six copies of one idea.
- **No proactive cost/latency signal.** The 503 ("Presupuesto mensual de IA agotado…") and 429 ("Límite de análisis simultáneos…") messages (`AnalyzeAthleteButton.tsx:34-37`, `GroupAnalysisPanel.tsx:47-52`) are purely *reactive*. Nothing hints expected wait or remaining budget before clicking, despite `AnalysisRunTimeline` already tracking per-node timing.
- **Chat has no persistent history** (`CompetitionChatPanel.tsx:143,147`, by design per docstring `:6`).
- No command palette / global search — confirmed absent; `AthleteCombobox.tsx:8-12` deliberately avoids Popover/cmdk for bundle size (a scoped single-field search, not a palette).

### 7. Charts — Recharts, evaluated against the dataviz skill

- **Dashed gridlines — direct anti-pattern hit.** Both charts: `<CartesianGrid stroke="rgba(34,42,53,0.08)" strokeDasharray="3 3" />` (`DistributionChart.tsx:304`, `EvolutionChart.tsx:213`). Skill: "❌ Dashed gridlines… reads as 'projection' or 'threshold'… ✅ solid hairlines."
- **Ad hoc, unvalidated hex everywhere**: ink `#131316` (main series), self-marker `#0ea5e9`, best-rider `#16a34a`/`#15803d`, worst-rider `#dc2626`/`#b91c1c`, other-riders `#94a3b8`/`#64748b` (`DistributionChart.tsx:493-494`), axis ink `#5a6172` — none traceable to tokens, none validated, and the app now has *two* different "mid-gray" hexes (`#717171` in style.css, `#5a6172` in charts).
- **Status meaning encoded as ad hoc categorical color** — best/worst rider reference lines (`DistributionChart.tsx:489-496`) encode good/bad, a **status** job per `color-formula.md`'s collision rule: they should use fixed status tokens, not hand-picked green/red.
- **Direct-labeling every non-self rider** (`RiderReferenceLines`, `:482-519`) risks the "number on every point" anti-pattern in 10–15-rider categories; only mitigated by alternating label position.
- **Championship point not marked on the plot**: `EvolutionChart.tsx` colors the championship label amber in the text legend (`:263-267`) but the `<Line dot={{r:4, fill:"#131316"}}>` (`:246`) paints every point identically. The distinguishing information lives only in secondary text.
- **Genuinely good, keep:** the `n<5` low-confidence fallback to a plain table instead of a fitted curve (`DistributionChart.tsx:286-293,406-463`) — exactly the skill's "Is it even a chart?" heuristic; same for the `n<3` disclaimer (`EvolutionChart.tsx:276-290`). Working custom tooltips with value-leads-label hierarchy; loading/error/empty states via `<Skeleton>`.
- **Missing table-view twin** for the n≥5 distribution path (anti-pattern: "No table view / color-only encoding").

### 8. Density patterns independently invented three times

`CompetitionsListPage.tsx:295-368`, `AthletesTable.tsx:17-51`, `SessionsTable.tsx:45,120-126` **each** implement the identical `<ul className="… md:hidden">` cards / `<table className="hidden … md:block">` convention with the identical hand-typed shadow string. Nobody extracted it despite writing it three times.

### 9. Iconography, motion, dark mode

- `lucide-react` used in 120 files but unevenly: Dashboard/Sessions/Athletes/Calendar pages use **zero** icons; Competitions/AthleteDetail use them heavily. One file hand-rolls a raw inline `<svg>` (`CompetitionDetailPage.tsx:766-783`, "lucide no tiene BarChart2Icon" — likely just a wrong name for this lucide version).
- `prefers-reduced-motion` respected globally (`style.css:222-231`) — real strength.
- Dark mode: `grep "dark:"` → 8 hits in 2 files, neither a real theme. **Zero dark-mode implementation exists.**
- No `cmdk` dependency; a command palette would be genuinely new infrastructure.

---

## Coach home proposal — "Hoy / Esta semana" mission control

Replace the 3-stat layout with a tile grid; keep `MeasurementAlerts` as-is. Per the dataviz form heuristic: single current values = **stat tiles**; only weekly load earns a **meter**.

**Row 1 — hero strip (2 stat tiles + 1 meter, `grid md:grid-cols-3`):**

1. **Próxima sesión** (stat tile). Session name + countdown ("en 2 días"); subtitle date/time/location. Data: `useTrainingSessions({from_date: today, to_date: +14d, status: 'planned'})` — the exact hook `SessionsListPage.tsx:25` already calls. Empty → "Sin sesiones planificadas" + "+ Planificar". Click → session detail.
2. **Próxima carrera Copa Valle** (stat tile + delta). Race name; "en N días" colored by taper urgency; subtitle from the *already-encoded* `CARRERA_TIER` map (`lib/insights.ts:145-154`: A = full taper 5–7d, B = mini 3–4d, C = none — data already in the frontend, never surfaced). Data: `useRaceEventsList({season})` (`hooks/race/useRaceEvents.ts:101`). Click → competition detail.
3. **Carga semanal** (**meter** per `marks-and-anatomy.md`: fill = accent→warning→danger by proximity to the CLAUDE.md "weekly hours ≤ athlete age" cap; unfilled track = lighter step of the *same* ramp). **Needs one small backend aggregate** (sum of planned `duration_min` per age band) — everything else is frontend-only.

**Row 2 — pending-work inbox (one card, list rows — a to-do list, not a KPI row):**

| Row | Data source | Status |
|---|---|---|
| Resultados por importar | `useRaceEventsList` filtered `!has_results && event_date < today` (logic exists client-side, `CompetitionsListPage.tsx:88-94`) | **exists today** |
| Actividades sin enlazar | `useActivityReview` count where `linked=false` (`ActivityReviewPage.tsx:21-23`) | **exists**, needs count-only variant |
| Boletines pendientes del mes | per-athlete status query, count `status ∈ {none, draft}` | **exists but N+1** (`useNewsletterForAthlete`, `:71-81`) |
| Consentimientos pendientes | mirrors `ConsentStatusPanel.tsx:45-50` `getConsentState`, today parent-side only | **needs new club-wide aggregate** |
| Insights IA desactualizados | mirrors `StaleAnalysisBadge` per-item `stale_run_id` | **needs new aggregate** |

Be explicit about "wire up now" vs "needs a small endpoint" — don't ship a tile that fetches 40 athletes × N queries for a badge count.

**Row 3:** keep `<MeasurementAlerts />` unchanged. **Row 4 (optional, P2):** season snapshot linking to the season insights page.

---

## Modern patterns to adopt

1. **Global command palette (Cmd/Ctrl+K)** — mount once in `AppShell`, lazy-loaded in its own chunk (respect the `AthleteCombobox` bundle precedent). shadcn `Command` (cmdk) — genuinely new. Actions: jump to athlete/session/race; "+ Nueva sesión/competencia"; "Análisis IA". **Effort: M.** *(Synthesis note: report 03 recommends deferring — see proposal §4.2/D5.)*
2. **Toast standard (`sonner`)** — one `<Toaster>` in `App.tsx`; replace the duplicated `ToastBanner` + inline red/green mutation text (dozens of instances, e.g. `SessionDetailPage.tsx:725-729`, `AthleteDetailPage.tsx:668-672`). **S** + **M** sweep.
3. **Persistent quick-create** "+" in the header (Nueva sesión / competencia / evento). **S.**
4. **Contextual creation from calendar day — a one-line fix**, not a feature: fill `handleDateClick` with `navigate(\`/calendar/events/new?date=${dateStr}\`)`. **S (<1 h).**
5. **Contextual creation from race taper window**: "Planificar sesión de afinamiento" on the home race tile + competition header when inside the tier's taper window, deep-linking `/training/sessions/new?race_event_id={id}` (mirrors the existing `?race_event_id=` prefill convention). **M** (session form must read the param, as `EventFormPage` already does).
6. **Optimistic UI for low-risk toggles**: attendance marks, "marcar ejecutada" (`SessionsListPage.tsx:99-102`) — TanStack `onMutate` + rollback toast. **S per mutation.**
7. **Keyboard shortcuts** for desktop planning (`g s`/`g c`/`g r`, `n`) — pairs with the palette. **S once #1 exists.**
8. **Global search** — fold into the palette; a second search surface would fragment the pattern.

---

## Visual system evolution

**Keep:** the monochrome charcoal/mid-gray/white base and shadow-ring elevation (visual result is right; the 13-file hand-typed duplication is the maintenance smell). Keep teal as **the** accent — it already functions as one (`--color-primary` drives every primary button; `--color-link-blue` is the same hex under a second name, `style.css:31,44` — merge the names).

**Retire** the lime `--color-accent` (`style.css:27-29,105-106`) — zero usages.

**Formalize a 4-step semantic layer as real tokens** (per the dataviz reserved status scale — steps distinct from any categorical slot, always icon+label, never color-alone):

```css
--color-success:  #0ca30c;  /* sync active, consent current, session executed */
--color-warning:  #fab219;  /* stale insight, consent outdated, partial condition */
--color-serious:  #ec835a;  /* reserve: "needs attention soon" tier */
--color-danger:   #d03b3b;  /* consent revoked, connection broken, cancelled */
```

Collapse the six ad hoc maps into **one** `<StatusBadge status domain="strava"|"session"|"consent"|"confidence"|"newsletter"|"competition-item">` consuming these tokens through `Badge` variants — colors already agree conceptually (green=good, amber=caution, red=bad); only the code paths differ.

**Categorical data palette for charts:** self/primary series = teal accent (single series needs no legend); best/worst reference lines = status tokens (status job, not identity); solid hairline grid (delete `strokeDasharray`); championship point gets a real distinct mark, not just colored text; run the final set through the skill's `validate_palette.js --mode light|dark`.

**Status conventions:** Strava sync = success/warning/secondary; sessions planned=neutral, executed=success, cancelled=danger; consent current=success, outdated=warning, revoked=danger, never=secondary. **Race classes A/B/C are ordinal** (taper intensity), not status — one-hue ramp, never good/bad colors.

**Dark mode feasibility:** cheaper than most apps thanks to the monochrome base (near-1:1 dark mapping per the skill's reference tokens), but the ~13 files with inline shadow styles are the blocker — **inline styles can't respond to `prefers-color-scheme`**; consolidate onto the token/utility first, or every file gets patched twice. Genuinely useful for dusk field use; sequence after the token cleanup.

**Cal Sans decision, pick one:** (a) formally drop — delete the ~30+ dead inline overrides; zero visual regression since nothing changes on screen (cheapest, correct P0), or (b) self-host the open-source Cal Sans (2 files) for the differentiated look design.md describes (legitimate P2 brand investment).

---

## Density & hierarchy fixes

- **Extract the responsive table/card split** into one shared `ResponsiveList`/`DataTable` primitive (3 independent copies).
- **One tab primitive everywhere**: migrate `CompetitionDetailPage`'s hand-rolled `TabTrigger` (`:158-173`) and `AthleteDetailPage`'s plain-button tab bar (`:570-674`, no keyboard nav/tablist semantics) onto `ui/tabs.tsx` (already correct in `AthleteAIAnalysisTab.tsx:311-345`). Same visuals, real a11y for free.
- **`SessionDetailPage` needs tabs, not more scroll**: group its 7 stacked sections into 3–4 tabs (Resumen / Asistencia / Plan de intervalos / Media). Single biggest page-length reduction available.
- **Retry-on-error everywhere**: `SessionsListPage.tsx:70-74`, `AthletesListPage.tsx:143-147`, `DashboardPage.tsx:18-22`, `CalendarPage.tsx:118-122` show static red text with no retry — copy the `CompetitionsListPage.tsx:250-264` pattern. Transient failures are the *common* case on field 3G.
- **Progressive disclosure for AI**: `GroupAnalysisPanel.tsx:103` already computes `launchDisabled = !hasResults || isInProgress` for the group button; extend the same gate to hide the per-card button when `hasResults` is false (one prop thread away, `InsightsTab`'s `InsightCard` `:83-207`).
- **Motivational touches, minors-privacy-safe:** build on `getCarreraTier`/`CARRERA_TIER` (`lib/insights.ts:145-173`) and the pseudonymized percentile badges (`DistributionChart.tsx:553-567`): coach-only streak tile (consecutive sessions attended), PR vs own prior best — shown only inside the athlete's own detail page, respecting the pseudonymization boundary in `DistributionChart.tsx:8-11`.

---

## AI surface unification

1. **One name, one icon, always.** "Insights IA" as the noun (retire "Análisis IA carreras" as a page title; keep "Panorama de temporada" as a card *label*); **"Analizar con IA"** as the one verb (rename the `AthleteAIAnalysisTab.tsx:340-343` "Lanzar" sub-tab to match); one lucide icon (`Sparkles`, already the majority) instead of `Sparkles`/`BrainCircuit`/`MessageSquare`/custom svg.
2. **One freshness vocabulary**: promote `AnalyzeAthleteButton`'s 3-state model + `StaleAnalysisBadge`'s amber-badge-plus-manual-confirm as the *only* way freshness is shown (including a future club-wide "N insights stale" rollup).
3. **Surface `AnalysisRunTimeline` wherever a run is in flight** — treat `GroupRunRow` as a compact variant of the same component, not a parallel implementation.
4. **Make cost/latency proactive**: "~20–30 s" hint from recorded node durations; a lightweight remaining-budget indicator near launch buttons (the coach currently has zero visibility — budget lives only in admin-only `/admin/ai`).
5. **Chat persistence: decide deliberately.** In-memory-only is a reasonable privacy-conscious default for a minors' product — keep it, but add a small "esta conversación no se guarda" caption so it isn't a surprise.

---

## Prioritized plan

**P0 (cheap, high-leverage, cleanup/wiring):** calendar date-click one-liner; delete dead Cal Sans inline overrides (or ship the font); fix the `--color-link-blue`/`--color-primary` name collision; delete unused lime tokens; remove dashed gridlines; add retry buttons to the 4 pages missing them.

**P1 (real design/build):** coach home (tiles with existing data first; 2 aggregate endpoints as backend addendum); `sonner`; one `StatusBadge` + token set; one responsive-table component; all tab bars on `ui/tabs` + `SessionDetailPage` tabs; command palette + quick-create *(see synthesis on palette timing)*.

**P2:** dark mode (after shadow cleanup); self-hosted Cal Sans (if brand investment wanted); keyboard shortcuts; optimistic-UI sweep; proactive AI cost indicator; motivational tiles.

**Quick wins (≤1 day):** 1) calendar date-click; 2) delete dead Cal Sans styles; 3) remove dashed gridlines (2 lines); 4) retire lime tokens; 5) "Reintentar" on 4 pages; 6) swap `SessionStatusBadge`'s hand-rolled `<span>` for `Badge`.
