# Agent report 01 — UX heuristics & field workflows

> Panel: coach UX audit 2026-07-11 · Agent: `ux-researcher` (Sonnet) · Read-only static code audit.
> Traced the 5 core coach workflows end-to-end through `frontend/src/`. Severities: High/Med/Low.

---

## Workflow findings

### Flow 1 — Plan the week (session wizard + attach technique/strength/intervals)

Traced: `SessionsListPage.tsx` → `SessionFormPage.tsx` → `SessionWizard.tsx` (4 steps: General/Atletas/Ruta y notas/Revisar) → on success, redirect straight to `SessionDetailPage.tsx` (create mode skips an intermediate screen — good, `SessionWizard.tsx:324-332`).

| Friction | Evidence | Severity |
|---|---|---|
| The wizard's 4 steps never include technique exercises, strength blocks, or interval structure — "attaching" a training plan to a session is **three different flows with three different mental models**, all happening only *after* the session already exists, on `SessionDetailPage.tsx`. | See breakdown below | **High** |
| → Interval structure: created **inline** on the session page, plus a "choose from club templates" picker — no navigation away. Best pattern of the three. | `frontend/src/routes/training/SessionDetailPage.tsx:1001-1036` (`TemplatePicker`) | — (positive) |
| → Strength blocks: built on a **separate page** (`/strength/blocks/new`), saved standalone, then the coach must search/select the target session from a plain radio list. When launched from a specific session via "Armar bloque de fuerza", the originating session is **not preselected** — the coach must re-find the session they just came from. | `frontend/src/routes/training/SessionDetailPage.tsx:774-779` (link out, no `sessionId` passed) → `frontend/src/routes/strength/BlockBuilderPage.tsx:80-113` (no query param/state read for a preselected session), `:355-377` (plain searchable radio list) | **Med** |
| → Technique exercises: `SessionBuilderPage.tsx` ("Armar sesión técnica", route `/technique/sessions/new`) does not attach to an existing session at all — it **creates a brand-new training session** via `useAssembleTechniqueSession` (`POST /api/technique/sessions`). A coach who already built a session in the wizard cannot add technique drills to it; they'd end up with two session rows for one workout. | `frontend/src/routes/technique/SessionBuilderPage.tsx:1-19` (docstring self-describes this), `:63-74`, confirmation copy at `:139-143` ("Se crearon N ejercicios en la sesión... Puedes verla... desde la lista de sesiones") | **High** |
| `DurationPicker` (Step 1, used on every session create/edit) has no `min-h` on its hour/minute inputs, unlike the sibling `inputClass` in the same step file which explicitly sets `min-h-[48px]`. Effective height ≈ 36-38px, under the club's 44px minimum. | `frontend/src/components/training/DurationPicker.tsx:24-25` (no min-height) vs. `frontend/src/components/training/session-wizard/StepGeneral.tsx:16-17` (`min-h-[48px]`) | **Med** |
| Advancing wizard steps (`goNext()`) never moves focus or announces the new step to assistive tech — only *validation failure* moves focus (`trigger(fields, {shouldFocus:true})`). A screen-reader user gets no cue that step content changed. | `frontend/src/components/training/session-wizard/SessionWizard.tsx:234-248` (no `.focus()`/live region on success path) | **Med** |

### Flow 2 — Field day on tablet (find session, attendance, rubric, media)

Traced: no dashboard shortcut → `SessionsListPage.tsx` (current-month filter) → `SessionDetailPage.tsx` → `AttendanceTable.tsx` / `RubricSliders.tsx` → `MediaUploadZone.tsx`.

| Friction | Evidence | Severity |
|---|---|---|
| **No "today's session" affordance anywhere.** `DashboardPage.tsx` shows only 3 static stat cards (total atletas / última evaluación / estado PHV) — nothing about upcoming/today's training. `SessionFiltersBar.tsx` defaults to "current month" with no "Hoy" quick filter, and `SessionsTable.tsx` renders every row identically with no "today" highlight. On a tablet in the field, the coach must open the sidebar, then visually scan a month of sessions to find the right one — under time pressure, in sunlight, this is exactly the friction the persona is supposed to be optimized against. | `frontend/src/routes/dashboard/DashboardPage.tsx:1-73`, `frontend/src/components/training/SessionFiltersBar.tsx:1-77`, `frontend/src/components/training/SessionsTable.tsx:126-230` | **High** |
| Rubric sliders (RPE OMNI + Esfuerzo/Actitud/Técnica — the core "fill effort rubric" action) are native `<input type="range">` with a **20×20px thumb** (`h-5 w-5`), well under the 44×44px minimum, and range inputs are inherently hard to hit precisely with gloved fingers. This is the single most-used control in the field-day flow. | `frontend/src/components/training/RubricSliders.tsx:76`, `:131` (`[&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5`) | **High** |
| `MediaUploadZone`'s file input has no `capture="environment"` hint, so on a tablet it opens the generic file/gallery picker instead of jumping straight to the camera — a missed shortcut for "quick photo during the session". | `frontend/src/components/training/MediaUploadZone.tsx:145-153` | **Low** |
| Good patterns worth preserving: debounced autosave (500ms) per attendance row with a saved-check icon and an explicit retry-on-error affordance; keyboard shortcuts P/A/J/T/L with `aria-keyshortcuts`; consent checkbox + GPS-strip disclosure on media upload. | `frontend/src/components/training/useAttendanceForm.ts:63-108`, `frontend/src/components/training/AttendanceTable.tsx:80-91,460-472`, `frontend/src/components/training/MediaUploadZone.tsx:231-255` | — (positive) |
| `NotifyParentsDialog` (used for the "cancel session, notify parents" step — a common field-day action) is a hand-rolled `<div role="alertdialog">` with **no focus trap, no Escape-to-close, no focus restoration** — unlike `ConfirmModal` used one screen over, which correctly wraps Radix `Dialog` (focus trap + Escape are automatic). Same session-cancel flow, two different accessibility guarantees. | `frontend/src/components/training/NotifyParentsDialog.tsx:124-133` (plain div, no Radix) vs. `frontend/src/components/common/ConfirmModal.tsx:36-42` (Radix `Dialog`) | **Med-High** |

### Flow 3 — Post-race (import PDF, review results, AI insights, notes, chat)

Traced: `CompetitionsListPage.tsx` ("Cargar resultados"/"Sin enlazar" buttons) → `CompetitionImportPage.tsx` → `ImportWizard.tsx` (3 steps) → `CompetitionDetailPage.tsx` (tabs) → `ResultsTable.tsx` (per-row "Analizar con IA" + notes) → `CompetitionChatPanel.tsx`.

| Friction | Evidence | Severity |
|---|---|---|
| Correction to task framing: `/competitions/import` and `/competitions/unlinked` are **not actually buried** — both have first-class buttons on `CompetitionsListPage`, one click from the "Competencias" sidebar item. Good discoverability. | `frontend/src/routes/competitions/CompetitionsListPage.tsx:193-211` | — (positive, noted for accuracy) |
| `/competitions/insights` (the cross-race "Análisis IA carreras" hub — season panorama + per-race club grid, `InsightsHubPage.tsx`) is **confirmed orphaned**: a repo-wide search for any `<Link>`/`navigate()` to `/competitions/insights` found zero in-app references outside test files and the route declaration itself. A test in `AppShell.test.tsx` documents the sidebar link was deliberately removed with the comment "el coach llega desde /competitions" — but neither `CompetitionsListPage.tsx` nor `CompetitionDetailPage.tsx` actually links to it. Two full pages (`SeasonInsightsPage`, `ClubInsightsPage`) plus their shared entry are effectively invisible. | `frontend/src/routes/competitions/insights/InsightsHubPage.tsx` (real, working page), `frontend/src/components/layout/__tests__/AppShell.test.tsx:113-141` (comment vs. reality), verified via grep across `frontend/src` for `competitions/insights` — no non-test in-app link | **High** |
| `InsightsHubPage.tsx:18` hardcodes `CURRENT_SEASON = 2026` — will silently point at the wrong season every January without a code change/deploy. Minor, but compounds the discoverability issue above (even if you find the page, it needs yearly maintenance). | `frontend/src/routes/competitions/insights/InsightsHubPage.tsx:18` | **Low** |
| `ImportWizard.tsx` (3-step, well structured — prefill-from-competition mode, revision-diff detection, good HTTP-status-to-copy mapping for 413/409/422/500) has the **same missing focus-management gap** as the session wizard: `setStep(...)` calls throughout never move focus to the new step. | `frontend/src/components/competitions/import/ImportWizard.tsx` — grepped for `.focus()`/`autoFocus`, zero matches; step transitions at e.g. `:696`, `:792`, `:821` | **Med** |
| `ResultsTable` row actions ("Editar/Agregar nota", "Analizar con IA") are undersized for touch: the note button is explicitly `min-h-[36px] min-w-[36px]`, and `AnalyzeAthleteButton` has no min-height class at all (`px-2 py-1 text-xs` only). | `frontend/src/components/competitions/results/ResultsTable.tsx:640` (`min-h-[36px] min-w-[36px]`); `frontend/src/components/competitions/insights/AnalyzeAthleteButton.tsx:181-186` | **Med** |
| `CompetitionChatPanel` keeps its whole conversation in local component state only — no persistence. Any navigation away, refresh, or tablet memory-reclaim reload during a 3G session silently discards the entire Q&A with no warning, well before the server's 1h TTL would matter. | `frontend/src/components/competitions/chat/CompetitionChatPanel.tsx:143-149` (`useState`, `useRef` only, no persistence) | **Low-Med** |
| Positive contrast case: `EditResultNoteDialog` (coach note editing) properly uses the Radix `Sheet`, has 48px targets, character counter, and inline toast — proves the good pattern exists in-repo, it's just not applied everywhere (see Flow 2 `NotifyParentsDialog` finding). | `frontend/src/components/race/EditResultNoteDialog.tsx:1-23` | — (positive) |

### Flow 4 — Monthly close (technical report + individual newsletters)

Traced: `ReportsListPage.tsx` → `ReportDetailPage.tsx` (narrative blocks, approve, PDF/DOCX) and separately `AthleteNewslettersDashboardPage.tsx` → `AthleteNewsletterDetailPage.tsx`.

| Friction | Evidence | Severity |
|---|---|---|
| `AthleteNewslettersDashboardPage` resolves each athlete card's newsletter status with its **own independent query per athlete** (`useNewsletterForAthlete` → `useAthleteNewsletters(athleteId)`), i.e. one HTTP request per athlete rendered on the page, with no batch/summary endpoint. For a club with 20-30 athletes this is an N-request waterfall on first load — a real risk on 3G/cold-start, which is explicitly a project constraint. | `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx:71-84` (hook), `:103`, `:720` (called once per card) | **Med** |
| The single-athlete "Generar" button shows no pending affordance (no spinner, no text change) while the mutation is in flight — only `disabled` toggles — inconsistent with every other mutation button in the app (`Loader2` + "Guardando…"/"Enviando…" pattern used everywhere else, e.g. `ReportDetailPage.tsx:487-489`, `SessionWizard.tsx:571`). Since this triggers an LLM narrative generation (several seconds), the button can look unresponsive. | `frontend/src/routes/training/AthleteNewslettersDashboardPage.tsx:189-200` | **Low** |
| Reasonably solid overall: report approval **locks further block editing** (`disabled={isApproved}`), AI-draft banner clearly marks unreviewed text, per-block regenerate is isolated from the rest of the form, PDF/DOCX both available. | `frontend/src/routes/training/ReportDetailPage.tsx:479-489, 552-566` | — (positive) |
| IA note: "Reportes mensuales" (internal, funder-style PDF/DOCX) and "Boletines Mensuales" (per-athlete, parent-facing) sit as two visually identical, adjacent, unsectioned sidebar items — the names are distinguishable in Spanish, but nothing in the nav signals "internal document" vs. "goes to parents." | `frontend/src/components/layout/AppShell.tsx:84-101` | **Low** |

### Flow 5 — Athlete 360 review

Traced: `AthleteDetailPage.tsx` (6 URL-synced tabs: info / anthropometry / growth / ai_analysis / newsletters / activities).

| Friction | Evidence | Severity |
|---|---|---|
| **Confirmed orphaned routes**: `/technique/athletes/:athleteId/progress` and `/strength/athletes/:athleteId/progress` (per-athlete skill/strength progress — real, tested, backend-complete features per `CLAUDE.md`) have **zero in-app navigation entry points anywhere in the repository.** Verified by grepping the entire `frontend/src` tree for both path segments and for any `Link`/`navigate` referencing "progress" near an athlete id — the only hits are the route declarations in `App.tsx` and each feature's own test file. `AthleteDetailPage.tsx`'s 6 tabs never mention technique or strength, and `technique/CatalogPage.tsx` has no outbound navigation at all. A coach can only reach either page by typing the URL. | `frontend/src/App.tsx:722,821`; confirmed absent from `frontend/src/routes/athletes/AthleteDetailPage.tsx` (full file read, tabs at `:53-62, 570-634`); confirmed absent from `frontend/src/routes/technique/CatalogPage.tsx` (no `Link`/`navigate` at all) | **High** |
| Competitive anxiety data has no cross-link from `AthleteDetailPage` either — it lives exclusively behind the separate `/anxiety` dashboard, a fourth disconnected "place that holds athlete info" (alongside the 6-tab detail page, technique progress, strength progress). | Grep of `AthleteDetailPage.tsx` for "anxiety" → 0 matches | **Med** |
| Positive: the 6 tabs that *are* wired up are genuinely well consolidated — URL-synced (`?tab=`), so back/forward and refresh preserve context; race analysis, PHV/growth, Strava activities and newsletters all live under one roof with one set of tab buttons. | `frontend/src/routes/athletes/AthleteDetailPage.tsx:390-426, 570-634` | — (positive) |

---

## Heuristic violations

1. **#6 Recognition rather than recall / #7 Flexibility & efficiency** — Three fully-built views (`/competitions/insights` hub, `/technique/athletes/:id/progress`, `/strength/athletes/:id/progress`) are unreachable through any click path; the coach would have to recall/guess a URL. `frontend/src/routes/competitions/insights/InsightsHubPage.tsx`, `frontend/src/routes/technique/AthleteProgressPage.tsx:4`, `frontend/src/routes/strength/AthleteProgressPage.tsx:5`.
2. **#4 Consistency and standards** — Three distinct UX patterns for the same underlying action ("attach training content to a session"): inline create (intervals, `SessionDetailPage.tsx:1001-1036`), build-elsewhere-then-search-and-attach (strength, `BlockBuilderPage.tsx:355-395`), and build-a-whole-new-session (technique, `SessionBuilderPage.tsx:63-74`).
3. **#4 Consistency and standards** — Two confirmation-dialog implementations for equally destructive actions: `ConfirmModal.tsx` (Radix, focus-trapped) vs. `NotifyParentsDialog.tsx:124-133` (hand-rolled, no trap) vs. `window.confirm()` in `MediaGallery.tsx:132-136` for deleting session media — three different mechanisms in one app.
4. **#1 Visibility of system status** — Wizard step transitions (`SessionWizard.tsx:234-248`, `ImportWizard.tsx` throughout) don't move focus or announce the new step; newsletter "Generar" button (`AthleteNewslettersDashboardPage.tsx:189-200`) gives no in-flight feedback while every comparable button elsewhere shows a spinner.
5. **#6 Recognition rather than recall (information architecture)** — `AppShell.tsx:37-192` renders 12 flat, unsectioned sidebar items mixing roster (Atletas/Padres), day-to-day ops (Calendario/Entrenamientos), monthly admin (Reportes mensuales/Boletines Mensuales) and specialized libraries (Técnica/Fuerza/Ansiedad/Actividades) with no visual grouping — scanning cost grows with every new module added.
6. **#7 Flexibility and efficiency of use** — No "today's session" shortcut anywhere (`DashboardPage.tsx`, `SessionFiltersBar.tsx`), forcing a full-list scan for the single highest-frequency field task.
7. **Minor naming inconsistency** — the same AI-insights concept is labeled "Insights IA" (`CompetitionDetailPage.tsx:110`) in one module and "Análisis IA" (`AthleteDetailPage.tsx:607-608`, `InsightsHubPage.tsx:42`) in another.

---

## Accessibility & field-usability risks

- **Touch targets below 44×44px** (club's own non-negotiable, also WCAG 2.2 SC 2.5.8 territory): `RubricSliders.tsx:76,131` (20px slider thumbs — High, most-used field control), `ResultsTable.tsx:640` (36px note button), `AnalyzeAthleteButton.tsx:181-186` (no min-height), `DurationPicker.tsx:24-25` (no min-height on Step-1 hour/minute inputs).
- **Contrast on the coach's sunlight-exposed tablet UI**: the design system's actual `--color-mid-gray` is `#717171` (not `#898989` as assumed in the brief) — `frontend/src/style.css:41,118`. Computed against white: ≈4.88:1, which **clears bare WCAG AA (4.5:1) for normal text but fails the club's own stricter "AA + 1 level" sunlight bar**. Notably, the team already engineered the fix: `--color-text-disclaimer: #5a5a5a` (`style.css:47-50`, ratio ≈6.9-7.4:1, comment explicitly says it exists to "superar WCAG AA en tamaño chico"). But it's used in only 5 files, and **all 5 are in the parent-facing module** (`components/parents/…`, `routes/parents/…`) — zero coach-facing files adopt it, despite the coach being the persona explicitly called out for direct sunlight. `text-mid-gray` appears in 166 coach-facing files, 35 of which also use 10-11px text sizes where contrast matters most (e.g. `RubricSliders.tsx:78-84` slider-tick labels).
- **Broken/dead Tailwind class**: `text-light-gray-dark` (`RubricSliders.tsx:78`) references a token that does not exist anywhere in `style.css` or any config — it resolves to no color at all (likely a copy/typo of `mid-gray`). Low severity (falls back to inherited dark text, so no visible harm), but a design-system integrity bug worth a one-line fix.
- **Focus management gap, not a "violation" the current test suite can catch**: `RubricSliders.a11y.test.tsx` and `AttendanceTable.a11y.test.tsx` run `jest-axe` inside jsdom, which correctly verifies ARIA roles/names/ranges (and they do — 4/4 sliders have accessible names and valuemin/max/now) but **structurally cannot measure rendered pixel dimensions**, since jsdom has no layout engine. This is why "0 a11y violations" (axe-clean) and the 20px-thumb finding above can both be true at once — recommend a manual/real-device pass (or Playwright + real Chromium) specifically for target-size, which axe-in-jsdom will never surface.
- **Positive, worth protecting**: `style.css:216-231` has a comprehensive, correctly-scoped `@media (prefers-reduced-motion: reduce)` block that neutralizes all animations/transitions app-wide, including inline styles — this is exactly right and should be a template for any future addition.
- **`window.confirm()` for destructive media deletion** (`MediaGallery.tsx:132-136`) bypasses the app's design system entirely — unstyled, unbranded, and inconsistent with the Radix-based confirm pattern used everywhere else.

---

## Prioritized recommendations

**P0**

1. **Convert the 4 rubric sliders to a segmented/stepper control (1-5 or 0-10 discrete buttons), not a range input.** Why: single highest-severity touch-target violation, on the single most-used field-day control, for a gloved-hands persona. The pattern to copy already exists in-repo (`ToggleGroup`/`ToggleGroupItem`, used for `session_kind` in `StepGeneral.tsx:190-210` and `surface_condition` in `ImportWizard.tsx:1151-1180`). Affected: `frontend/src/components/training/RubricSliders.tsx`. Effort: **M**.
2. **Wire up the three orphaned routes.** Add a link/button to `/competitions/insights` from `CompetitionsListPage.tsx`'s action row and/or `CompetitionDetailPage.tsx`'s insights tab; add "Ver progreso técnico" / "Ver progreso de fuerza" links from `AthleteDetailPage.tsx`'s tab bar (or from within the ai_analysis tab) to `/technique/athletes/:id/progress` and `/strength/athletes/:id/progress`. Why: three complete, tested features are currently invisible to the only user who needs them. Affected: `CompetitionsListPage.tsx`, `CompetitionDetailPage.tsx`, `AthleteDetailPage.tsx`. Effort: **S** (pure navigation wiring, no new UI). *(Synthesis note: superseded in part by the subtraction plan — see proposal §10/K3/M2.)*
3. **Reconcile the "attach training content" mental model.** At minimum, make `SessionBuilderPage.tsx` ("Armar sesión técnica") support attaching drills to an *existing* session (mirroring the strength-block attach pattern) rather than only spawning a new one; longer-term, consider surfacing "attach technique / attach strength / attach intervals" as three parallel, equally-inline actions on `SessionDetailPage.tsx` (intervals already sets the bar). Why: this is the core "plan the week" workflow and currently has the least consistent UX of anything audited. Affected: `frontend/src/routes/technique/SessionBuilderPage.tsx`, `frontend/src/components/technique/SessionAssembler.tsx`, `frontend/src/routes/training/SessionDetailPage.tsx`. Effort: **L**.

**P1**

4. **Wrap `NotifyParentsDialog` in the existing Radix `Dialog` primitive** (same as `ConfirmModal.tsx`) to get focus trap + Escape + focus restoration for free. Why: this dialog gates real parent-facing emails and session cancellation — a keyboard/AT user currently has no reliable way to dismiss or navigate it safely. Affected: `frontend/src/components/training/NotifyParentsDialog.tsx`. Effort: **S**.
5. **Add a per-step heading + `.focus()` call on step change** in both `SessionWizard.tsx` and `ImportWizard.tsx`. Why: multi-step forms with no focus/announcement on step change are a recurring, cross-cutting screen-reader gap; fixing the shared pattern once benefits both wizards. Effort: **M**.
6. **Adopt `--color-text-disclaimer` (or raise `--color-mid-gray`) in coach-facing small text**, starting with the highest-traffic files (rubric/slider labels, table timestamps, form hints). Why: the club's own stricter "AA+1/near-AAA in direct sunlight" bar currently applies only to the parent module; the coach is the persona actually named for sunlight exposure. Affected: `frontend/src/style.css`, plus the ~35 coach-facing files using 10-11px `text-mid-gray`. Effort: **S-M** (token swap, no layout change).
7. **Add a "Hoy" quick filter or a dashboard "next session" card.** Why: removes the highest-frequency field-day friction (finding today's session in a full-month list). Affected: `frontend/src/components/training/SessionFiltersBar.tsx`, `frontend/src/routes/dashboard/DashboardPage.tsx`. Effort: **S-M**.
8. **Bump `ResultsTable` note button and `AnalyzeAthleteButton` to 44px min-height/width.** Effort: **S**.
9. **Replace `window.confirm()` in `MediaGallery.tsx` with `ConfirmModal`.** Affected: `frontend/src/components/training/MediaGallery.tsx:127-153`. Effort: **S**.

**P2**

10. Preselect the originating session when "Armar bloque de fuerza" is launched from `SessionDetailPage.tsx` (pass session id via `location.state`, read it in `BlockBuilderPage.tsx`). Effort: **S**.
11. Add `capture="environment"` to `MediaUploadZone`'s file input for direct camera capture on tablet. Effort: **S**.
12. Batch the newsletter-status lookup in `AthleteNewslettersDashboardPage.tsx` (one endpoint for the whole club/month instead of per-athlete) to reduce request fan-out on 3G/cold-start. Effort: **M** (needs a small backend endpoint + frontend hook change).
13. Group the 12 sidebar items into visually distinct sections in `AppShell.tsx:37-192`. Effort: **S**.
14. Unify "Insights IA" / "Análisis IA" labeling. Effort: **S**.
15. Give `CompetitionChatPanel` a lightweight `sessionStorage` persistence (keyed by `raceEventId`) so a refresh doesn't silently discard the conversation. Effort: **S-M**.

---

## Quick wins (≤1 day each)

- Fix the dead `text-light-gray-dark` class in `frontend/src/components/training/RubricSliders.tsx:78` (typo for an existing token).
- Add `min-h-11`/`min-w-11` to `DurationPicker.tsx`'s hour/minute inputs.
- Add `min-h-11`/`min-w-11` to the `ResultsTable` note button and `AnalyzeAthleteButton`.
- Swap `window.confirm()` for `ConfirmModal` in `MediaGallery.tsx`.
- Add a link to `/competitions/insights` from `CompetitionsListPage.tsx`'s action bar. *(See proposal §10 — the surviving link target is the season page.)*
- Add "Ver progreso técnico"/"Ver progreso de fuerza" links from `AthleteDetailPage.tsx`.
- Pass the originating session id into the strength-block attach flow so it's preselected.
- Give the newsletter "Generar" button a spinner + "Generando…" text while pending.
- Replace the hardcoded `CURRENT_SEASON = 2026` in `InsightsHubPage.tsx:18` with a derived current year.
- Add a visual section divider in the sidebar between operational and admin/library items.

---

**Cross-cutting observations:** touch-target regressions cluster around native `<input type="range">` and icon-only action buttons in dense tables; newly-added features repeatedly ship without a nav entry point (3 confirmed this pass — worth a standing definition-of-done checklist item); confirm-dialog implementation is inconsistent (Radix `Dialog`/`Sheet` vs. hand-rolled vs. `window.confirm()`) — standardize on the Radix wrapper as the only allowed pattern going forward.
