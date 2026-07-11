# Coach Experience — UX/UI Audit & Redesign Proposal

> **Date:** 2026-07-11 · **Branch:** `claude/coach-profile-ux-analysis-kaar7d` · **Status:** Proposal (no code changed)
>
> Produced by a panel of 5 specialized read-only agents (Sonnet), each auditing the coach-facing frontend from a different modern-frontend lens: UX heuristics & field workflows, component architecture, information architecture, modern product design (with the `dataviz` design skill loaded), and product simplification/subtraction. Full per-agent evidence lives in [`agent-reports/`](agent-reports/). Every claim below carries `file:line` evidence in those reports.
>
> **Purpose:** input for building an implementation plan (e.g., one speckit spec per phase in §13). Nothing has been implemented.

---

## 1. Executive summary

The coach experience grew feature-by-feature (26 features in ~6 months) into:

- a **flat 12-item sidebar** fronting **46 coach/admin routes**, with **9 fully-built features unreachable** from any navigation (AI session assistant, AI insights hub + 3 subpages, technique session builder, gymkhana composer, interval template library, technique/strength per-athlete progress);
- **~3,500 production LOC + ~1,560 test LOC of confirmed dead or duplicated surface** (incl. 2 npm deps: `konva`, `react-konva`);
- **four divergent color systems** (docs say monochrome; `style.css` ships a teal/lime "cycling kit" with the lime never used; charts hardcode a fourth ad-hoc set; badges use raw Tailwind utilities) and a **display font (Cal Sans) referenced inline 115 times but never actually loaded**;
- a component layer where the most common patterns were **hand-rolled per module instead of shared**: 151 raw `<input>`, 82 raw `<select>`, 59 hand-rolled page headers, 81 retry blocks, 37 empty states, 6 status-badge implementations, 5 modal chromes, 4 file dropzones, 3 steppers, 3 tab implementations, no toast system;
- **10 concrete bugs** found along the way (§3), including one that affects the admin role on every dashboard visit.

**Nothing requires a rewrite.** The audit's most encouraging result is that the *good* patterns already exist in-repo — the Competitions list page (responsive table/cards, retry, empty states, kebab menus), `ResultsTable`'s responsive column-hiding, attendance autosave with per-row save state, the `AnalysisRunTimeline` agent-transparency component, the low-sample table fallback in charts. The redesign is mostly: **promote the existing best patterns to standards, regroup navigation around the coach's real cadence, delete confirmed dead surface, and build one mission-control home.**

Six proposals: **(A)** regroup nav into 6 areas + user menu + mobile bottom tabs · **(B)** "Hoy / Esta semana" coach home · **(C)** one attach model for session content · **(D)** shared component foundation + shadcn adoption · **(E)** one visual system · **(F)** field-day usability. Plus a subtraction plan (§10) and a phased roadmap (§13).

---

## 2. Current state in numbers

| Dimension | Measured | Evidence |
|---|---|---|
| Coach/admin route entries | 46 (68 total `<Route>` elements, 22 lazy) | `App.tsx` |
| Sidebar items (coach) | 12, flat, ungrouped | `AppShell.tsx:37-192` |
| Orphaned routes (zero inbound links, verified by grep) | 9 | reports 01, 03, 05 |
| Raw `<input>` (no Input primitive) | 151 across 60 files (+17 duplicated `inputClass` consts) | report 02 |
| Raw `<select>` (no Select primitive) | 82 across 40 files | report 02 |
| Inline `boxShadow` style objects | 368 across 117 files; **177 are the exact literal already registered as the unused `--shadow-ring` token** | report 02 |
| "Cal Sans" inline references | 115 across 84 files — **font never loaded** (`public/fonts/` has only Inter) | reports 02, 04 |
| Hand-rolled page headers / back links | 59 `<h1>` blocks / 16 `ArrowLeft` links | report 02 |
| Retry-button blocks / empty-state blocks | 81 files / 37 files | report 02 |
| Status-badge implementations | 6 independent (2 bypass the `Badge` primitive) | report 04 |
| Tab-bar implementations | 3 (plain buttons / `ui/tabs` / raw Radix) | report 04 |
| Confirm/modal chromes | 5 copy-pasted hand-rolled + `ConfirmModal` + `window.confirm()` ×2 | reports 01, 02, 05 |
| File dropzones | 4 implementations, 761 LOC | report 02 |
| Steppers | 3 implementations | report 02 |
| Toast system | none — ad-hoc `useState`+`setTimeout` toasts duplicated per page | reports 02, 04 |
| Color systems in tension | 4 (design.md monochrome / style.css cycling-kit / chart hexes / badge utilities) | report 04 |
| Off-brand modules (`slate-*` instead of `charcoal` tokens) | technique, strength, intervals, anxiety (specs 017/018/021/026) | report 03 |
| Deletable surface (kill+merge lists) | ≈3,500 production LOC, ≈1,560 test LOC, 6–8 routes, 2 npm deps | report 05 |
| Dead component files | **0** — duplication is the problem, not dead files | report 02 |

---

## 3. Bugs found (fix regardless of any redesign)

1. **Admin dead-click loop.** Four admin-visible surfaces link to `/athletes/:id`, which is gated `coach`-only, and `ProtectedRoute` silently bounces to `/dashboard`: `MeasurementAlerts.tsx:121,147` (on the dashboard), `competitions/tabs/AthletesTab.tsx:183`, `competitions/tabs/InsightsTab.tsx:303`, `AthleteNewsletterDetailPage.tsx:423`; gate at `App.tsx:280-287`, silent redirect at `ProtectedRoute.tsx:45-54`. Fix: shared `<AthleteLink>` that renders plain text for admin, or admit admin to the route.
2. **Calendar day-click is dead in the middle.** `CalendarShell` correctly emits `dateClick` and `EventFormPage` already reads `?date=` to prefill — but `CalendarPage.tsx:55-57`'s `handleDateClick` body is empty. One line (`navigate(\`/calendar/events/new?date=${dateStr}\`)`) completes a whole feature.
3. **`ConfirmModal.tsx:66`** sets `autoFocus` on the **confirm** button even when `confirmDanger` — destructive dialogs should focus Cancel.
4. **Broken/no-op Tailwind classes:** `text-foreground`/`bg-muted`/`text-muted-foreground`/`border-muted-foreground` in `OnboardingStepper.tsx` and `AnthropometricRecordExplanationCard.tsx:100` reference tokens never defined under this project's `cssVariables:false` config; `text-light-gray-dark` in `RubricSliders.tsx:78` references a token that doesn't exist.
5. **`InsightsHubPage.tsx:18`** hardcodes `CURRENT_SEASON = 2026` — silently wrong every January.
6. **Newsletter dashboard N+1:** `AthleteNewslettersDashboardPage.tsx:71-84,720` fires one HTTP request per athlete card (20–30 requests on 3G/cold-start). Needs a batch/summary endpoint.
7. **Anxiety interpretation is a forgotten integration:** `AnalyzeButton.tsx` + `InterpretationPanel.tsx` + `useInterpretation` are fully built (with complete backend support per spec 017) but never imported by any page. Wire into `IndividualPanel` (~1 day) or delete frontend+backend together.
8. **`NotifyParentsDialog.tsx:124-133`** is a hand-rolled `role="alertdialog"` with no focus trap/Escape/restore, in the parent-notification flow; `window.confirm()` used for destructive actions in `MediaGallery.tsx:133` and `CompetitionFormPage.tsx:471`.
9. **Cal Sans never loads** (see §8) — 115 inline styles silently falling back to `system-ui` since day one, including inside the shared `DialogTitle` primitive (`ui/dialog.tsx:102-105`).
10. **Retired `sequence_number === 99` sentinel still checked in 4 frontend spots** (`lib/insights.ts:107-112`, `lib/raceCalendar.ts:149-159`, `AthleteAIAnalysisTab.tsx:89-94`, `MiniSparkline.tsx:38` + `InsightsTimeline.tsx:195`) despite CLAUDE.md's feature-014 retirement note; also 3 duplicated `validaLabel` helpers to consolidate.

---

## 4. Proposal A — Information architecture: 12 flat items → 6 areas

### 4.1 Before → after

```
BEFORE (flat, 12 items)                    AFTER (6 groups + header menu)

├─ Dashboard                               📍 Inicio                    /dashboard  (mission control, §5)
├─ Atletas          [coach]                🚴 Entrenamiento             → /calendar (default)
├─ Padres           [coach]                   ├─ Calendario             /calendar
├─ Calendario                                 ├─ Sesiones               /training/sessions  (+ "Crear con IA" visible)
├─ Entrenamientos                             └─ Actividades            /activities (Strava review)
├─ Reportes mensuales                      🏆 Competencias              → /competitions (default)
├─ Boletines Mensuales                        ├─ Válidas                /competitions
├─ Competencias                               ├─ Sin enlazar            /competitions/unlinked
├─ Ansiedad competitiva                       └─ Panorama de temporada  /competitions/insights/season/:year
├─ Actividades                             🧑‍🤝‍🧑 Atletas    [coach]        → /athletes (default)
├─ Técnica                                    ├─ Todos                  /athletes  (+ new "Progreso" tab, §6)
└─ Fuerza                                     └─ Ansiedad competitiva   /anxiety
                                           👪 Familias                  → /parents (default)
Header: Mi perfil · Cerrar sesión             ├─ Padres     [coach]     /parents
Admin extra in main list: Salud IA            ├─ Boletines              /training/athlete-newsletters
                                              └─ Informes del club      /training/reports (⚙ → project-profile)
9 orphaned routes                          📚 Biblioteca                → /technique (default)
                                              ├─ Técnica y gymkhana     /technique
                                              └─ Fuerza                 /strength

                                           Header: [+ Crear ▾]  [User name ▾: Mi perfil · Salud IA (admin) · Cerrar sesión]
```

**No URL changes.** Every existing route keeps its path — this is a grouping/labeling change only. The `/competitions/insights` hub and 2 of its subpages are *deleted* rather than surfaced (§10), because they self-document as duplicates of views already reachable via Competencias → race → "Insights IA" tab and Atletas → athlete → "Análisis IA" tab; only `SeasonInsightsPage` (genuinely unique season table) survives and gets a real entry point.

### 4.2 Navigation mechanics

- **Desktop:** keep the existing `aside` mechanics; wrap the 6 areas in collapsible groups (Radix `Collapsible`/`<details>`), auto-expand the group matching the current route. Clicking a group label navigates to its default sub-view — *no hub interstitials*, so today's 1-click cost to Calendario/Atletas is preserved.
- **Secondary nav:** a segmented control under the page `<h1>` for sibling views (Calendario ↔ Sesiones ↔ Actividades) — reuse the pill pattern from `CompetitionDetailPage.tsx:633-643`. Per-record tab bars (athlete detail, competition detail) stay as-is visually, but migrate to the shared `ui/tabs` primitive (§7).
- **Header:** consolidate `Mi perfil` + `Salud IA` (admin) + `Cerrar sesión` into one user-menu dropdown; add a `+` quick-create dropdown (Nueva sesión / Nueva competencia / Nuevo evento / Nuevo atleta, role-filtered).
- **Tablet/mobile:** replace the drawer-replica with a **bottom tab bar** — Inicio · Entrenamiento · Competencias · Atletas + **"Más"** opening a `Sheet` (already installed, unused for nav) with Familias, Biblioteca, profile, logout. One-thumb reach for the field tools.
- **Command palette (cmdk):** *deferred* deliberately. Two agents split on this; the resolution: grouped nav + quick-create solves today's discoverability problem at 46 routes without a new dependency. Revisit at ~70 routes or on demand. (P2, optional.)
- **Naming:** settle `Reportes/Informes/Boletines` → **"Informes del club"** (funder report) vs **"Boletines"** (parent newsletters), applied in nav, `ReportsListPage.tsx:390`, `ReportDetailPage.tsx:465,472`. Unify "Insights IA" vs "Análisis IA" (§9.5).

### 4.3 Role handling

- Atletas group and Padres sub-item hidden for admin (matches current RBAC exactly) — **after** fixing bug §3.1 so admin never receives links into coach-only routes.
- `Salud IA` moves out of the main list into the user menu (diagnostic, not daily-use).

---

## 5. Proposal B — Coach home: "Hoy / Esta semana" mission control

Replace `DashboardPage.tsx`'s 3 static stat cards (total athletes / last evaluation / PHV status — no links, no trends) with a mission-control layout. Keep `MeasurementAlerts` untouched (it's already the best part). Tile spec follows the `dataviz` skill (single current values = stat tiles; only weekly load earns a meter).

**Row 1 — hero strip (3 tiles):**

| Tile | Content | Data |
|---|---|---|
| **Próxima sesión** | name + "en N días" + date/place; empty state → "+ Planificar" | `useTrainingSessions` (exists; same hook as `SessionsListPage.tsx:25`) |
| **Próxima carrera** | race + countdown + taper guidance colored by urgency (A: 5–7d, B: 3–4d, C: none) | `useRaceEventsList` (exists) + `CARRERA_TIER` map already in `lib/insights.ts:145-154` — never surfaced on any dashboard |
| **Carga semanal** | meter: planned hours vs the "weekly hours ≤ age" cap per age band | **needs one small backend aggregate** |

**Row 2 — pending-work inbox** (list rows, not KPIs): Resultados por importar (client logic exists in `CompetitionsListPage.tsx:88-94`) · Actividades sin enlazar (`useActivityReview` exists; needs count-only variant) · Boletines pendientes del mes (exists but N+1 — fix with the batch endpoint from §3.6) · Consentimientos pendientes (**needs new club-wide aggregate**) · Insights IA desactualizados (**needs new aggregate**; per-item staleness exists).

**Row 3 —** keep `<MeasurementAlerts />` as-is. **Row 4 (optional, P2):** season snapshot card linking to Panorama de temporada.

Ship in two waves: tiles with existing data first; the 2–3 aggregate endpoints as a small backend addendum.

---

## 6. Proposal C — One attach model for session content

Today "attach a training plan to a session" has **three different mental models** (report 01):

| Content | Today | Verdict |
|---|---|---|
| Intervals | inline create + template picker on `SessionDetailPage.tsx:1001-1036` | ✅ **the pattern to standardize on** |
| Strength blocks | separate page, saved standalone, then search-a-session radio list; originating session not preselected (`BlockBuilderPage.tsx:80-113,355-377`) | pass session id via `location.state`; preselect |
| Technique drills | `SessionBuilderPage` **creates a brand-new session** via a *second* creation endpoint (`POST /api/technique/sessions`), duplicating the wizard's metadata form and drifting from it (no route upload, no AI assistant) — and it's unreachable anyway | **delete the standalone builder** (§10) and add an inline "Agregar ejercicios de técnica" attach on `SessionDetailPage`, mirroring intervals |

Target: `SessionDetailPage` offers three parallel inline attach actions (técnica / fuerza / intervalos). At the same time, restructure `SessionDetailPage` — currently 7 stacked full-width sections with no tabs, the longest page in the app — into 3–4 tabs (Resumen · Asistencia · Plan · Media) on the shared tabs primitive. Also add a **"Hoy" quick filter** on the sessions list + the home tile (§5), removing the "scan a month to find today" field friction.

---

## 7. Proposal D — Component foundation (new components / consolidations)

### 7.1 New shared components (replace measured duplication)

| Component | Replaces | Effort |
|---|---|---|
| `PageHeader` (`title, subtitle?, backTo?, actions?`) | 59 hand-rolled `<h1>` + 16 back-links; centralizes the display-font decision | S |
| `EmptyState` / `ErrorState` (with retry + centralized cold-start detection) | 37 empty-state blocks / 81 retry blocks + per-module `resolveErrorMessage` clones | S–M |
| `StatCard` (thin wrapper over existing `Card`) | dashboard's hand-rolled `<article>`s + future home tiles | S |
| `ConfirmDialog` on **shadcn `alert-dialog`** (`tone: "default"\|"danger"`, focus-on-Cancel when danger) | `ConfirmModal` (9 sites) + `ConfirmDeleteDialog` (5 sites) + 5 copy-pasted modal chromes + 2 `window.confirm()` | M |
| `StatusBadge` (domain-mapped, consumes semantic tokens §8) | 6 independent status-badge implementations | S–M |
| `LibraryFilterBar`, `CatalogGrid`, `LibraryEntityCard` | técnica/fuerza mirror modules (self-documented clones: FilterBar 259/259 lines, CatalogGrid "Mirror de…", ExerciseCard, CatalogPage/DetailPage/ProgressPage shells) | M |
| `Stepper` (unified; `variant: compact\|detailed`) | 3 stepper implementations (`SessionStepper`, `ImportWizard` inline, `OnboardingStepper`) | S |
| `FileDropzone` (accept/size/hint; domain preview as slot) | 4 dropzones, 761 LOC | M–L |
| `DataTable` convention (wrap `ui/table` with `hidden sm/md/lg:table-cell` per `ResultsTable.tsx:395-431`) | 20 raw-`<table>` files + 3 hand-rolled mobile-card/desktop-table splits | M (S per file) |
| Route-level `Suspense` wrapper | 21 identical inline fallbacks in `App.tsx` | S |

### 7.2 shadcn/ui adoption (13 primitives today; forms are the gap)

Add: `input`, `label`, `select`, `form` (RHF wrapper), `checkbox`, `radio-group`, `switch`, `alert`, `alert-dialog`, `popover` + `calendar` (date-picker recipe for the 12 raw `type="date"` fields), `sonner` (toast — mount once in `App.tsx`, retire the duplicated hand-rolled `ToastBanner`/`setTimeout` toasts), `separator`. Later/optional: `sidebar` (AppShell rebuild, high blast radius — P2), `command` (palette, deferred). **Not** `breadcrumb` (all 16 back-links are single-level; `PageHeader.backTo` suffices). Respect the documented bundle-size decision in `AthleteCombobox.tsx:8-13` before migrating it.

### 7.3 Design tokens

- Adopt the **already-registered** `shadow-ring` utility at the 177 exact-literal call sites; collapse the duplicate `--shadow-ring-soft` / `--shadow-card` definitions into one name; wire or delete `--shadow-ambient`/`--shadow-button-highlight` (0 usages). This cleanup is also the **prerequisite for dark mode** (inline styles can't respond to `prefers-color-scheme`).
- Register `--color-border-gray` in `@theme` so `border-border-gray` replaces the repeated `border-[rgba(34,42,53,0.08)]` arbitrary values.
- Fix the two files using undefined shadcn semantic tokens (§3.4) — or register the semantic token set once if the `sidebar` block is adopted later.
- Bring the four off-brand modules (technique/strength/intervals/anxiety, all on `slate-*`) onto the charcoal/mid-gray vocabulary — pair this with the Biblioteca regroup so the new group ships visually coherent.

---

## 8. Proposal E — One visual system

1. **Reconcile the three declared color systems.** Decide: the app is *monochrome + one teal accent*. `--color-primary` (#20b7c9) already drives every primary button and link (`--color-link-blue` is the same hex under a second name — merge the names). **Delete the never-used lime `--color-accent`.** Update `docs/05-design-system/design.md` to match reality (it currently documents a pure-grayscale system the app doesn't ship, with hex values that differ from `style.css`).
2. **Formalize a semantic status layer as tokens** (today it's implicit in 6 scattered badge maps): `--color-success #0ca30c` · `--color-warning #fab219` · `--color-danger #d03b3b` (+ optional `--color-serious #ec835a`), consumed only through `StatusBadge`/`Badge` variants — always icon+label, never color-alone. Race classes A/B/C are **ordinal** (taper intensity), not status — one-hue ramp, not arbitrary colors.
3. **Chart palette (per dataviz skill):** primary series = teal accent; best/worst reference lines = status tokens (they encode good/bad, not identity); remove `strokeDasharray="3 3"` gridlines (`DistributionChart.tsx:304`, `EvolutionChart.tsx:213` — dashed reads as "projection"); mark the championship point on the mark itself (distinct dot), not only in text below (`EvolutionChart.tsx:246,263-267`); unify the two competing gray-ink hexes; cap direct labels on crowded reference lines; add a table-view twin for the n≥5 distribution path. Keep the excellent `n<5 → table` fallback.
4. **Cal Sans decision (pick one, stop the accidental state):** (a) *drop* — delete the 115 dead inline styles, headings keep rendering exactly as they always have (zero visual change), or (b) *ship it* — self-host the woff2 + `@font-face` + point `--font-display` at it (2 files) and get the documented brand look. Recommendation: decide inside `PageHeader`/token, not inline; (b) is cheap and delivers the documented intent, (a) is the zero-risk default.
5. **Dark mode:** feasible and genuinely useful (dusk field sessions), but sequence *after* the shadow-token cleanup (§7.3); currently zero dark styles exist.

---

## 9. Proposal F — Field-day usability (tablet, sun, gloves, 3G)

1. **Rubric sliders → discrete segmented steppers.** The 4 most-used field controls are native ranges with 20×20px thumbs (`RubricSliders.tsx:76,131`); replace with `ToggleGroup` steps (pattern already in `StepGeneral.tsx:190-210`). Highest-impact touch fix in the app.
2. **44px minimum everywhere:** `ResultsTable.tsx:640` note button (36px), `AnalyzeAthleteButton` (no min-height), `DurationPicker.tsx:24-25` inputs. Note: jsdom+axe cannot catch target-size — add a Playwright/real-device pass for this class of bug.
3. **Contrast for sunlight:** the stricter `--color-text-disclaimer` token (≈7:1) exists but is used *only* in the parent portal; adopt it (or raise `--color-mid-gray`) for coach-facing small text (~35 files with 10–11px `text-mid-gray`).
4. **Dialog integrity:** migrate `NotifyParentsDialog` + the 5 copy-pasted modal chromes onto the Radix-backed `ConfirmDialog`/`Dialog` (focus trap, Escape, restore); kill `window.confirm()`.
5. **Wizard focus management:** on step change, move focus to the new step heading + announce (`SessionWizard.tsx:234-248`, `ImportWizard` step transitions) — fix once in the shared wizard/stepper shell.
6. **Feedback standards:** `sonner` toasts for mutations; spinner + label on the newsletter "Generar" button (`AthleteNewslettersDashboardPage.tsx:189-200`); retry buttons on the 4 list pages missing them (copy `CompetitionsListPage.tsx:250-264`); `capture="environment"` on media upload for direct camera; optional `sessionStorage` persistence (or an explicit "no se guarda" caption) for the race chat.
7. **Offline/slow-network:** keep and extend the existing strengths — query persist, `ServerWakingBanner`, attendance autosave with per-row retry.

---

## 10. Subtraction plan (kill / merge / demote)

### Kill (delete code; ~3,100 LOC production + ~1,560 test; drops `konva` + `react-konva`)

| # | What | Why (evidence) | LOC |
|---|---|---|---|
| K1 | Gymkhana composer (`/technique/composer`, `components/technique/composer/`) | zero inbound links; only self-reference; heavy canvas deps for an unreachable page | 1,416 + 401 test |
| K2 | Technique session builder (`/technique/sessions/new`, `SessionBuilderPage` + `SessionAssembler`) | unreachable; duplicates session creation via a second endpoint and drifts from the wizard; replaced by inline attach (§6) | 867 + 759 test |
| K3 | Insights hub duplicates (`InsightsHubPage`, `ClubInsightsPage`, `AthleteInsightsPage`) | deliberately unlinked (tests assert absence); self-documented duplicates of the reachable per-race Insights tab and per-athlete Análisis IA tab | 504 + 317 test |
| K4 | `/intervals/templates` (`TemplateLibraryPage`) | unreachable; browse-only wrapper with zero unique capability vs the embedded `TemplatePicker` | 36 |
| K5 | `components/ai/UploadZone.tsx` | superseded by `RaceUploadZone` in the 007 consolidation; only its own test references it | 165 + 84 test |
| K6 | Anxiety `AnalyzeButton`/`InterpretationPanel`/`useInterpretation` | zero references — **decision required**: wire into `IndividualPanel` (~1 day, backend complete) **or** delete frontend+backend; don't leave half-built | 144 |

Migration notes: retarget the legacy `/coach/race-analysis` redirect to `/competitions`; update the 3 routing-guard tests; keep `SeasonInsightsPage` (unique season table) and link it from `CompetitionsListPage` ("Panorama de temporada"). K1/K2/K6 need a product sign-off (see §12); everything else is mechanical.

### Merge

| # | What → into | Notes |
|---|---|---|
| M1 | `ConfirmDeleteDialog` → `ConfirmDialog` (§7.1) | 5 call sites; net a11y improvement |
| M2 | Técnica/fuerza progress pages → `AthleteDetailPage` **"Progreso"** tab (internal Técnica/Fuerza toggle — don't grow the tab bar 6→8) | boards (`SkillProgressBoard`, `ProgressNotesBoard`) already lazy; delete the 2 wrapper routes (267 LOC); fixes 2 orphans at the athlete, where their own breadcrumbs say they belong |
| M3 | Reportes + Boletines nav entries → "Familias" group (§4) | pages unchanged; naming settled |
| M4 | `components/race/*` (4 files) → `components/competitions/`; `components/shared/PHVBadge` → `components/athletes/`; merge `common/`+`shared/` | folder hygiene, zero behavior |
| M5 | 3 `validaLabel` helpers + `=== 99` checks → one exported helper on `series_kind` | per CLAUDE.md feature-014 retirement |

### Demote

- **Ansiedad competitiva**: top-level → under Atletas (episodic, consent-gated; URL unchanged). Do not reduce reachability, only visual priority.
- **Datos del proyecto**: already off-nav; relabel as settings (gear icon in `ReportsListPage` header) rather than a peer document action.

### Explicitly keep (checked, justified)

Calendario↔Competencias FK link (feature 008 — not a duplicate) · Actividades page vs athlete Strava tab (batch triage vs spot-check, shared `ActivityCard`) · Padres pages vs athlete guardian card (peek + deep link, no dup editing) · onboarding flow (actively wired to parent invites) · `AIHealthPage` · Wave B/F 301 redirects + `GonePage` (explicit test-documented policy for external deep links) · `BlockBuilderPage` (positive contrast case — reuses the wizard instead of duplicating it).

### Protect list (don't regress during redesign)

`AnalysisRunTimeline` (live agent trace) · `HITLApprovalCard` · `AnalyzeAthleteButton`/`StaleAnalysisBadge` freshness model · attendance autosave + keyboard shortcuts + consent/EXIF flow · `MeasurementAlerts` · charts' low-n table fallback · `ResultsTable` responsive pattern · `prefers-reduced-motion` support · `lib/datetime.ts` · `CompetitionsListPage` as the quality template.

---

## 11. AI surface unification

Seven-plus AI entry points ship under five different names ("Asistente IA", "Análisis IA carreras", "Insights IA", "Analizar/Re-ejecutar/Lanzar", "Preguntar a la IA") and mixed icons. Standardize: **"Insights IA"** as the noun, **"Analizar con IA"** as the only verb, `Sparkles` as the only icon; promote the existing 3-state freshness model (`AnalyzeAthleteButton`) as the *only* freshness vocabulary (including the future home-inbox rollup); render `AnalysisRunTimeline` (or its compact variant) wherever a run is in flight; make cost/latency proactive ("~20–30 s" hint from recorded node durations; surface remaining AI budget near launch buttons instead of only reactive 503/429 copy); keep chat non-persistence as a deliberate privacy choice but say so in the UI.

---

## 12. Decisions required from the coach (before planning)

| # | Decision | Options (recommended first) |
|---|---|---|
| D1 | Gymkhana composer (K1) | **Delete** (unreachable, 2 deps, 1.4k LOC) / surface it in Biblioteca and commit to maintaining it |
| D2 | Anxiety interpretation (K6) | **Wire into IndividualPanel** (~1 day, backend already built) / delete both sides |
| D3 | Cal Sans | **Self-host the font** (2 files, delivers documented brand) / formally drop it and amend design.md |
| D4 | Technique session builder (K2) | **Delete + inline attach on session detail** (§6) / fold as a wizard mode |
| D5 | Command palette | **Defer** (grouped nav + quick-create first) / build now with `cmdk` |
| D6 | Insights hub (K3) | **Delete duplicates, keep + relink season page** / surface the whole hub as-is |

---

## 13. Phased roadmap → how to build the plan

Each phase is one plannable unit (e.g., a speckit spec). Order matters: foundation before redesign, subtraction before new surface.

| Phase | Scope | Size | Suggested spec |
|---|---|---|---|
| **0. Bugs & quick wins** | §3 fixes; retry buttons; touch-target bumps; calendar date-click; naming unification; orphan-fix links that survive §10; dead-code deletes K4/K5 + M4/M5; chart gridlines | 2–4 days, no migration | `027-coach-ux-bugfixes-quick-wins` |
| **1. Component & token foundation** | §7 + §8.1–8.3: shadcn form primitives, sonner, PageHeader/EmptyState/ErrorState/StatCard/ConfirmDialog/StatusBadge/Stepper, shadow-token adoption, semantic tokens, chart palette, Cal Sans decision (D3) | 1–2 weeks | `028-frontend-design-foundation` |
| **2. Subtraction** | §10 kill/merge list per decisions D1/D2/D4/D6; Biblioteca token remediation | 3–5 days | `029-coach-surface-subtraction` |
| **3. Navigation regroup** | §4: AppShell groups, user menu, quick-create, secondary-nav pattern, mobile bottom tabs | ~1 week | `030-coach-navigation-redesign` |
| **4. Coach home** | §5 mission control (incl. 2–3 small backend aggregates + newsletter batch endpoint) | 1–2 weeks | `031-coach-home-mission-control` |
| **5. Flow redesigns** | §6 one attach model + SessionDetailPage tabs; técnica/fuerza onto shared library components; athlete "Progreso" tab (M2); wizard focus management; AI naming pass (§11) | 2–3 weeks | `032-session-content-unification` (+ optionally split) |
| **6. Polish (optional)** | dark mode; command palette (D5); keyboard shortcuts; optimistic-UI sweep; proactive AI cost hints; motivational streak/PR tiles (coach-only, privacy-safe) | as capacity allows | `033-…` |

**Suggested next step:** review §12 decisions, then run `/speckit-specify` for Phase 0 (or Phases 0+1 together) using this document and the relevant `agent-reports/` as source material.
