# Agent report 03 — Information architecture & navigation

> Panel: coach UX audit 2026-07-11 · Agent: general-purpose, senior IA/navigation lens (Sonnet) · Read-only static analysis of `AppShell.tsx`, `App.tsx`, all `routes/**` pages, `docs/05-design-system/design.md`, `lib/landing.ts`.

## Current-state IA map & critique

### The flat list today

`AppShell.tsx:37-192` renders one un-grouped `<nav>` with sequential `NavLink`s. Twelve items are visible to coach/admin (lines 40-146): Dashboard, Atletas, Padres, Calendario, Entrenamientos, Reportes mensuales, Boletines Mensuales, Competencias, Ansiedad competitiva, Actividades, Técnica, Fuerza — plus header actions "Mi perfil" (`:279-285`) and "Cerrar sesión" (`:286-293`), and admin-only "Salud IA" (`:183-191`). No visual grouping, no collapsible sections, no secondary nav pattern — every item competes at the same depth regardless of how often it's touched (daily field work vs. monthly reporting are visually identical list rows).

`App.tsx` defines **46 distinct coach/admin-scoped route entries** (plus 2 legacy 301 redirect shims at `App.tsx:521-524` and `:667-670`, both slated for 410 per existing code comments — "Wave F sustituirá esto por GonePage"). Only 12 of those 46 have a sidebar entry point.

### Orphaned routes (verified by grep — zero inbound `<Link>`/`navigate()` anywhere in `frontend/src`)

| Route | App.tsx | Verified orphan? |
|---|---|---|
| `/training/sessions/assistant` | 344-359 | **Yes.** `SessionsListPage.tsx` only has "+ Nueva sesión" → `/training/sessions/new` (`:48-54`); no button anywhere links to the assistant. |
| `/competitions/insights` + `/insights/club` + `/insights/season/:year` | 578-593, 615-646 | **Yes, as a subtree.** `CompetitionsListPage.tsx` (full file read) links only to `/competitions/import`, `/competitions/unlinked`, `/competitions/new`, and per-row actions — never to `/competitions/insights*`. The three pages link to each other and down to `/competitions/insights/athletes/:id`, but nothing outside the subtree points in. Only entry: the legacy `/coach/race-analysis` redirect (`App.tsx:667-670`), itself unlinked from any nav. |
| `/competitions/insights/athletes/:id` | 647-662 | **Reachable only from inside the orphaned subtree.** The per-race "Insights IA" tab's `AnalyzeAthleteButton` ("Ver progreso en Insights") does **not** navigate here — it just sets `?tab=insights` on the *current* competition (`AnalyzeAthleteButton.tsx:131-136`). |
| `/technique/sessions/new` | 705-720 | **Yes.** `technique/CatalogPage.tsx` has only a "Nuevo ejercicio" button that opens a create/edit *dialog* (`:92-101`), no session-assembly entry point. |
| `/technique/composer` | 737-753 | **Yes.** Same catalog page, no link. |
| `/strength/blocks/new` | 788-803 | **Partially.** Not in any catalog/list, but *is* linked from `SessionDetailPage.tsx:774-779` ("Armar bloque de fuerza"). Reachable only via an existing session's detail page. |
| `/intervals/templates` | 855-871 | **Yes, fully.** The page's own docstring admits it (`TemplateLibraryPage.tsx:1-13`): attaching a template happens through an *embedded* `TemplatePicker` inside `SessionDetailPage.tsx:1022-1031`, which never links out to the standalone library. |
| `/training/reports/project-profile` | 408-415 | **Not an orphan** — reachable via "Datos del proyecto" in `ReportsListPage.tsx:397-404`. Buried inside a page whose h1 says "Reportes Mensuales" — a settings-like page mixed into a document-generation list. |
| `/technique/athletes/:athleteId/progress` | 721-736 | **Yes** — zero inbound links anywhere. The page itself only links *back* to `/athletes/:id` (`technique/AthleteProgressPage.tsx:108-115`). `AthleteDetailPage.tsx` has 6 tabs (`:53`) — none link to technique progress. |
| `/strength/athletes/:athleteId/progress` | 820-835 | **Yes** — same pattern exactly (`strength/AthleteProgressPage.tsx:111-118`); same absence from `AthleteDetailPage.tsx`. |

A coach cannot get from an athlete's profile to that athlete's technique-skill or strength progress at all today — both boards exist, are fully built, and are simply unplugged from the athlete they describe.

### Flagship finding: a confirmed dead-click bug for admin (IA/RBAC mismatch)

Four separate admin-visible surfaces link into a route that **excludes admin**:

- `App.tsx:280-287` — `/athletes/:id` is gated `allowedRoles={[UserRole.coach]}` — **admin is not in the list.**
- `components/dashboard/MeasurementAlerts.tsx:121,147` — links `to={/athletes/${a.athlete_id}}`, rendered on `/dashboard`, which **is** admin-visible (`App.tsx:256-263`).
- `components/competitions/tabs/AthletesTab.tsx:183` and `components/competitions/tabs/InsightsTab.tsx:303` — both `navigate(/athletes/${athleteId}?tab=...)`, rendered inside `CompetitionDetailPage` (`[coach, admin]`, `App.tsx:551-558`).
- `routes/training/AthleteNewsletterDetailPage.tsx:423` — same pattern, page is `[coach, admin]` (`App.tsx:432-439`).
- `ProtectedRoute.tsx:45-54` — on a role mismatch it **silently** `<Navigate>`s to the role's fallback (`/dashboard` for admin) with no toast, no message.

Net effect: an admin browsing the Dashboard, a competition's Atletas/Insights tab, or a newsletter detail page can click an athlete's name and simply bounce back to where they started, with no explanation. A real, reproducible UX defect.

### Naming inconsistency (same feature, three different words)

- Sidebar: **"Reportes mensuales"** (`AppShell.tsx:90`)
- List page h1: **"Reportes Mensuales"** (`ReportsListPage.tsx:390`)
- Detail breadcrumb: **"← Informes mensuales"** (`ReportDetailPage.tsx:465`)
- Detail h1: **"Informe Técnico — {month} {year}"** (`ReportDetailPage.tsx:472`)

Three labels (Reportes / Informes / Informe Técnico) for one artifact, one hop from the *visually near-identical but functionally distinct* **"Boletines Mensuales"** (`AppShell.tsx:99`, per-athlete parent newsletter). A coach cannot tell from the sidebar alone that "Reportes" = club-wide funder PDF/DOCX and "Boletines" = individual parent email.

### Duplicate concept: Calendario vs. Competencias

`CalendarPage.tsx:80` subtitle: "Eventos, entrenamientos y competencias del club" — the calendar is explicitly a cross-cutting aggregation, yet it sits as a sibling top-level item next to Competencias. They have an explicit bridge (feature 008): `CompetitionDetailPage.tsx:504-559` "Asociar a calendario" split button; `CompetitionsListPage.tsx:626-636` same from the row kebab. Good UX papering over an IA question the sidebar never answers.

### Visual/design-system fragmentation (reinforces the grouping)

Grepping `text-slate-900|text-charcoal` across `routes/` shows a hard split: **every route file under `technique/*`, `strength/*`, `intervals/*`, and `anxiety/*`** uses generic Tailwind `slate-900`/`slate-500` (e.g. `technique/ComposerPage.tsx` ×5, `strength/BlockBuilderPage.tsx` ×3, `anxiety/AnxietyDashboardPage.tsx` ×1), while every other module uses `text-charcoal` + Cal Sans consistently. These four modules (specs 017/018/021/026, all built later) visually read as a bolted-on app — independently confirming they belong together as one deliberately-scoped area due for a shared design pass.

### No shared navigation primitives exist

`components/layout/` contains only `AppShell.tsx` and `ServerWakingBanner.tsx`. No `PageHeader`, `Breadcrumb`, or `SidebarGroup` — the same "← Back" + Cal-Sans-h1 JSX block is hand-copied in essentially every route file (dozens of near-identical copies). Mobile nav (`AppShell.tsx:206-234`) is a slide-in drawer replicating the desktop list verbatim — no bottom tab bar, no tailored mobile IA. `sheet.tsx` is installed and unused for navigation. Stack: `react-router-dom ^7.14.1`, `react ^19.2.5`, `tailwindcss ^4.2.2`, no `cmdk`/`vaul`.

### Landing behavior

`lib/landing.ts:14-26` sends both `admin` and `coach` to `/dashboard`, which is entirely athletes-data-driven (`useDashboardStats` from `useAlerts()`: athlete count, last evaluation, PHV ratio, `MeasurementAlerts`). No session/competition/communication content on the one page everyone sees on every login.

---

## Proposed sitemap (before → after)

### Before (current reachability)

```
Sidebar (flat, 12 items, coach+admin unless noted)
├─ Dashboard                     (PHV/anthropometry stats only)
├─ Atletas                       [coach only]
├─ Padres                        [coach only]
├─ Calendario
├─ Entrenamientos                → /training/sessions
│    ⚠ orphan: /training/sessions/assistant (AI draft)
├─ Reportes mensuales            (buried: project-profile)
├─ Boletines Mensuales
├─ Competencias                  (buried-but-linked: import, unlinked)
│    ⚠ orphan subtree: /competitions/insights{,/club,/season/:year}
├─ Ansiedad competitiva          (no deep link from athlete profile)
├─ Actividades                   (Strava review)
├─ Técnica                       ⚠ orphans: sessions/new, composer, athletes/:id/progress
└─ Fuerza                        ⚠ orphan: athletes/:id/progress (blocks/new via session detail only)

Header: Mi perfil · Cerrar sesión      Admin extra in main list: Salud IA
```

### After (proposed — 6 top-level areas + header menu)

```
📍 Inicio                                        /dashboard
     Redesigned hub: this week's sessions, next competition + taper
     countdown, pending-action strip (measurements, unlinked activities,
     newsletters, report drafts), quick-create. [coach+admin, content
     branches by role — fixes the admin dead-click at the source]

🚴 Entrenamiento                                 index → /calendar
   ├─ Calendario (default)                       /calendar, /calendar/events/new|:id/edit
   ├─ Sesiones                                   /training/sessions (+ visible "Crear con IA" →
   │                                             /training/sessions/assistant), /:id, /:id/edit,
   │                                             /:id/activity-match/:activityId
   └─ Actividades                                /activities (Strava — stays paired with Sesiones:
                                                  its only mutation targets a training session)

🏆 Competencias                                  index → /competitions
   ├─ Válidas (default)                          /competitions, /new, /:id (6 tabs), /:id/edit,
   │                                             /:id/import, /import
   ├─ Sin enlazar                                /competitions/unlinked
   └─ Análisis IA                                /competitions/insights* — orphan fixed
                                                  (see synthesis: subtraction plan keeps only the
                                                  season page and relinks it)

🧑‍🤝‍🧑 Atletas   [coach only]                      index → /athletes
   ├─ Todos (default)                            /athletes, /new, /:id — 6 existing tabs
   │                                             + technique/strength progress integrated
   └─ Ansiedad competitiva                       /anxiety (unchanged internal tabs); athlete page
                                                  gains a "Bienestar" pointer with athleteId prefilled

👪 Familias                                      index → /parents
   ├─ Padres (default)   [coach only]            /parents, /parents/:id
   ├─ Boletines                                  /training/athlete-newsletters, …/:athleteId/:newsletterId
   └─ Informes del club                          /training/reports, /:year/:month,
                                                  ⚙ "Datos del proyecto" → project-profile

📚 Biblioteca                                    index → /technique
   ├─ Técnica y gymkhana (default)               /technique, /exercises/:id (+ session-assembly and
   │                                             composer entry points per subtraction decisions)
   ├─ Fuerza                                     /strength, /exercises/:id, "Armar bloque" →
   │                                             /strength/blocks/new (now discoverable), /blocks/:id
   └─ Intervalos                                 /intervals/templates (or embedded-only per
                                                  subtraction decision)

Header user-menu (▾ next to user name, all roles)
   ├─ Mi perfil                                  /perfil
   ├─ Salud IA                                   /admin/ai   [admin only]
   └─ Cerrar sesión
```

Every route keeps its existing URL — this is a nav/grouping change, not a routing change.

---

## Navigation model

**Desktop sidebar.** Keep the existing `aside`/`NavLink` mechanics but wrap each of the 6 areas in a disclosure (`<details>`/Radix `Collapsible`). Auto-expand the group matching the current route; collapse the rest. Additive to `navLinks` (`AppShell.tsx:37-193`) — no route or permission logic changes.

**Area index routes vs. hub pages.** Clicking a top-level label navigates straight to the area's **default sub-view** (`/calendar`, `/athletes`, `/parents`, `/technique`, `/competitions`) rather than an intermediate hub — preserves today's 1-click cost for the highest-frequency pages. Within-area switching (Calendario ↔ Sesiones ↔ Actividades) via a **segmented control** directly under the page h1 — reuse the pill pattern from `CompetitionDetailPage.tsx:633-643`, promoted one level to mean "sibling view". Two visually distinct nav levels: pill-tabs = area-level; per-record tab bars stay as-is.

**Tablet/mobile.** Replace the full-drawer replica (`AppShell.tsx:206-234`) with a bottom tab bar carrying the 4 highest-frequency areas — **Inicio, Entrenamiento, Competencias, Atletas** — plus a 5th **"Más"** tab opening a `Sheet` (already a dependency, unused for nav) listing Familias, Biblioteca, Mi perfil, Salud IA (admin), Cerrar sesión. One thumb-reach for the tools used mid-session. For admin (no Atletas), the 4th tab becomes Biblioteca or Familias; Salud IA stays in "Más".

**Breadcrumbs / back strategy.** Extract one `<PageHeader title breadcrumb={{ to, label }} actions={...} />` into `components/layout/` and swap incrementally per page — pure refactor, and it's what makes the naming fixes enforceable in one place. For multi-step flows keep the plain "← Volver a X" back-link — hierarchies are single-parent, 2–3 levels; a full breadcrumb component is over-engineering.

**Global actions.** Header quick-create "+" (dropdown: Nueva sesión / Nueva competencia / Nuevo evento / Nuevo atleta, role-filtered) using `dropdown-menu.tsx`. Do **not** build a command palette yet: no `cmdk` dependency today, 46 routes doesn't justify it, and the grouped sidebar + quick-create already solves "where do I find X". Revisit past ~70 routes or on explicit demand.

**Mi perfil / Salud IA / logout** move from two standalone header buttons into a single user-menu dropdown — reduces header clutter and gives admin-only "Salud IA" a clearly-scoped home instead of sitting visually equal to coach features.

---

## Merge/demote/kill decisions

1. **Fold Reportes Mensuales + Boletines Mensuales + Datos del proyecto into one "Familias" area as three distinct, clearly-labeled destinations (not one blended list).** All three are outward-facing communication artifacts generated monthly; grouping by *audience/purpose* resolves the Reportes/Informes/Boletines naming collision by forcing one settled label per destination. Risk: **Low** — nav/label change only.
2. **Demote Ansiedad competitiva to a secondary destination under Atletas.** The "Individual" tab (`AnxietyDashboardPage.tsx:68-130`) is athlete-scoped wellness requiring re-selecting the athlete from a bare dropdown even when arriving from that athlete's profile. "Grupo" (event-level triage) keeps the same URL, unaffected. Risk: **Low-medium** (episodic use; URL unchanged).
3. **Keep Actividades (Strava review) under Entrenamiento, not Atletas.** Its only mutation links an activity to a *training session* (`ActivityReviewPage.tsx:1-16`), output consumed by session detail and `ActivityMatchPage`. The athlete-scoped read-only view already exists as an `AthleteDetailPage` tab. Risk: **Low**. (Also the one late module already on-brand token-wise.)
4. **Merge Técnica + Fuerza + Intervalos into one "Biblioteca" area with internal tabs.** All three are curated-catalog-then-attach-to-session tools sharing the same interaction pattern, the same orphan problem (5 orphaned routes between them), and the same off-brand `slate-*` styling — one place to fix discoverability + visual consistency in a single pass. Risk: **Medium** — pair the regroup with the design-token pass, otherwise "Biblioteca" becomes one area that visibly doesn't match the app.
5. **Absorb the orphaned `/competitions/insights*` subtree as a visible secondary destination inside Competencias** rather than leaving it disconnected. Highest-leverage fix in this audit: zero new code beyond an entry point, unlocks fully-built pages. Risk: **Very low.** *(Synthesis note: the subtraction audit refined this — delete the duplicated hub/club/athlete pages, keep + relink the season page; see proposal §10.)*
6. **Nest Calendario as the default sub-view of Entrenamiento — with the top-level click routing straight to `/calendar`** so its click-cost doesn't regress. Calendario becomes explicitly "the schedule that references Sesiones and Competencias". Risk: **Medium** if naively hub-paged; **low** with the direct index route.
7. **Complete the existing 410 migration for `/coach/race-analysis` and `/training/races/:id/club-insights`** on its already-documented Wave F schedule (`App.tsx:518-520,664-666`, `GonePage.tsx:1-12`) once the Análisis IA entry point ships and the destination is no longer an orphan.

---

## Migration notes

**No URL redirects are required by this proposal.** Suggested incremental waves (mirroring the repo's existing PR/Wave convention):

- **Wave 1 — surface the orphans** (frontend-only, no AppShell change): the Quick Wins below; fixes 7 of 9 orphans with no redesign.
- **Wave 2 — AppShell regroup**: 6 collapsible groups replacing the flat `navLinks`; `to=` targets unchanged; update `AppShell.test.tsx`.
- **Wave 3 — header user-menu** + quick-create "+".
- **Wave 4 — mobile bottom tab bar** (highest-effort wave; can ship last).
- **Wave 5 — shared `PageHeader` extraction**, opportunistically per page.
- **Wave 6 (separate track) — athlete-detail Técnica/Fuerza progress integration + design-token remediation** for technique/strength/intervals/anxiety.

---

## Quick wins (≤1 day)

1. **Surface the AI session assistant**: "Crear con IA" next to "+ Nueva sesión" in `SessionsListPage.tsx:48-54` → `/training/sessions/assistant` (~10 lines).
2. **Surface the insights**: "Análisis IA" entry in `CompetitionsListPage.tsx`'s action row (`:192-219`). *(Per synthesis: target the season page.)*
3. **Surface strength block creation**: "Armar bloque" button on `strength/CatalogPage.tsx` (mirrors `SessionDetailPage.tsx:774-779`).
4. **Surface technique session tools** on `technique/CatalogPage.tsx` (`:80-102`). *(Per synthesis: subject to the delete-vs-fold decision.)*
5. **Surface the interval template library** from the session-detail intervals section (near `TemplatePicker`, `~:1020`). *(Per synthesis: subject to the delete decision.)*
6. **Fix the admin dead-click bug**: wrap the 4 `/athletes/${id}` links in a role check (shared `<AthleteLink>` helper) — plain text for admin instead of a silent bounce.
7. **Settle Reportes/Informes/Boletines naming**: recommend "Informes del club" for the funder report, "Boletines" exclusively for parent newsletters; apply across `AppShell.tsx:90`, `ReportsListPage.tsx:390`, `ReportDetailPage.tsx:465,472`.
8. **Relabel "Datos del proyecto" as settings**: gear icon in the page header rather than a peer action next to "+ Generar reporte" (`ReportsListPage.tsx:397-404`).
