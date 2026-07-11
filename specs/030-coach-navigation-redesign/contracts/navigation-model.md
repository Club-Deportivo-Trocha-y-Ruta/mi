# Contract — Navigation Model (area → routes mapping)

Consumed by `SidebarNav`, `BottomNav`, `MoreSheet`. Backing data model: `../data-model.md`. Every `to` below is an existing `App.tsx` route, copied verbatim — **no URL changes** (FR-009).

## Inicio

| Route | Page | Entry point | Roles |
|---|---|---|---|
| `/dashboard` | `DashboardPage` | Nav item (sole link, no disclosure) | coach, admin |

## Entrenamiento (`defaultTo /calendar`)

| Route | Page | Entry point | Roles |
|---|---|---|---|
| `/calendar` | `CalendarPage` | Nav item — default; sibling pill "Calendario" | coach, admin |
| `/calendar/events/new` | `EventFormPage` (create) | Via Calendario "+" or header quick-create | coach, admin |
| `/calendar/events/:id/edit` | `EventFormPage` (edit) | Via a calendar event | coach, admin |
| `/training/sessions` | `SessionsListPage` | Sibling pill "Sesiones" | coach, admin |
| `/training/sessions/assistant` | `SessionAssistantPage` | Via "Crear con IA" button on Sesiones list (FR-007 — new) | coach, admin |
| `/training/sessions/new` | `SessionFormPage` (create) | Via Sesiones "+" or header quick-create | coach, admin |
| `/training/sessions/:id` | `SessionDetailPage` | Via a Sesiones list row | coach, admin |
| `/training/sessions/:id/edit` | `SessionFormPage` (edit) | Via session detail | coach, admin |
| `/training/sessions/:id/activity-match/:activityId` | `ActivityMatchPage` | Via session detail | coach, admin |
| `/activities` | `ActivityReviewPage` | Sibling pill "Actividades" | coach, admin |

## Competencias (`defaultTo /competitions`)

| Route | Page | Entry point | Roles |
|---|---|---|---|
| `/competitions` | `CompetitionsListPage` | Nav item — default; sibling pill "Válidas" | coach, admin |
| `/competitions/new` | `CompetitionFormPage` (create) | Via Válidas "+" or header quick-create | coach, admin |
| `/competitions/import` | `CompetitionImportPage` | Via Válidas action row | coach, admin |
| `/competitions/:id` | `CompetitionDetailPage` | Via a Válidas list row (6 tabs incl. "Insights IA") | coach, admin |
| `/competitions/:id/edit` | `CompetitionFormPage` (edit) | Via competition detail | coach, admin |
| `/competitions/:id/import` | `CompetitionImportPage` (prefill) | Via competition detail | coach, admin |
| `/competitions/unlinked` | `UnlinkedCompetitorsPage` | Sibling pill "Sin enlazar" | coach, admin |
| `` /competitions/insights/season/${year} `` | `SeasonInsightsPage` | Sibling pill "Panorama de temporada" (year via `currentSeason()`) | coach, admin |

## Atletas — coach-only area (`defaultTo /athletes`)

| Route | Page | Entry point | Roles |
|---|---|---|---|
| `/athletes` | `AthletesListPage` | Nav item — default "Todos" | coach |
| `/athletes/new` | `AthleteFormPage` (create) | Via Todos "+" or header quick-create | coach |
| `/athletes/:id` | `AthleteDetailPage` | Via a Todos list row (7 tabs incl. "Progreso" from 029) | coach |
| `/athletes/:id/edit` | `AthleteFormPage` (edit) | Via athlete detail | coach |
| `/anxiety` | `AnxietyDashboardPage` | Nav item — "Ansiedad competitiva" (demoted, same URL) | coach in nav; route RBAC still `[admin, coach]` — see `research.md` R7 for the admin nav-visibility trade-off |

## Familias (`defaultTo /parents` for coach; falls back to Boletines for admin — see below)

| Route | Page | Entry point | Roles |
|---|---|---|---|
| `/parents` | `ParentsListPage` | Nav item — default "Padres" (coach) | coach |
| `/parents/:id` | `ParentDetailPage` | Via a Padres list row | coach |
| `/training/athlete-newsletters` | `AthleteNewslettersDashboardPage` | Nav item "Boletines" (admin's resolved default) | coach, admin |
| `/training/athlete-newsletters/:athleteId/:newsletterId` | `AthleteNewsletterDetailPage` | Via Boletines dashboard | coach, admin |
| `/training/reports` | `ReportsListPage` | Nav item "Informes del club" | coach, admin |
| `/training/reports/project-profile` | `ProjectProfilePage` | Via Informes del club ⚙ settings affordance (not a peer nav item) | coach, admin |
| `/training/reports/:year/:month` | `ReportDetailPage` | Via Informes del club list row | coach, admin |

## Biblioteca (`defaultTo /technique`)

| Route | Page | Entry point | Roles |
|---|---|---|---|
| `/technique` | `technique/CatalogPage` | Nav item — default "Técnica y gymkhana" | coach, admin |
| `/technique/exercises/:id` | `technique/ExerciseDetailPage` | Via Técnica catalog | coach, admin |
| `/strength` | `strength/CatalogPage` | Nav item "Fuerza" | coach, admin |
| `/strength/exercises/:id` | `strength/ExerciseDetailPage` | Via Fuerza catalog | coach, admin |
| `/strength/blocks/new` | `strength/BlockBuilderPage` (create) | Via Fuerza "Armar bloque" (FR-007 — new catalog entry point) or session detail | coach, admin |
| `/strength/blocks/:id` | `strength/BlockBuilderPage` (edit) | Via Fuerza catalog or session detail | coach, admin |

## Header (not a `NavArea`)

| Route | Page | Entry point | Roles |
|---|---|---|---|
| `/perfil` | `ProfilePage` | User menu — "Mi perfil" | all authenticated roles |
| `/admin/ai` | `AIHealthPage` | User menu — "Salud IA" | admin |

**Total: 39 surviving coach/admin-nav-relevant routes** (the "~40" figure in the assignment; parent-only routes, legacy redirects, and public routes are excluded from this count).

## Excluded — removed by 029 (not 030's concern; nav must not reference these)

| Route | Reason |
|---|---|
| `/competitions/insights` | K3 hub — deleted (029 FR-001) |
| `/competitions/insights/club` | K3 — deleted (029 FR-001) |
| `/competitions/insights/athletes/:id` | K3 — deleted (029 FR-001) |
| `/technique/sessions/new` | K2 standalone builder — deleted (029 FR-004) |
| `/technique/composer` | K1 gymkhana composer — deleted (029 FR-005) |
| `/technique/athletes/:athleteId/progress` | M2 — folded into `AthleteDetailPage` "Progreso" tab (029 FR-007) |
| `/strength/athletes/:athleteId/progress` | M2 — folded into `AthleteDetailPage` "Progreso" tab (029 FR-007) |
| `/intervals/templates` | K4 — deleted (029 FR-003); template picker stays embedded in session detail |

## Excluded — legacy redirects / public routes (untouched)

| Route | Behavior | Note |
|---|---|---|
| `/training/races/:raceEventId/club-insights` | 301 → `/competitions/:id?tab=insights` (`App.tsx:521-524`) | Wave F replaces with `GonePage` later — out of scope here |
| `/coach/race-analysis` | 301 → `/competitions/insights` (`App.tsx:667-670`) | Target is the hub 029 deletes; 029/Wave-F must repoint it — not a 030 change |
| `/anxiety/responder/:token`, `/onboarding`, `/privacidad`, `/confirmar-correo`, `/login`, password-reset routes | Public/pre-auth | Not part of authenticated nav |

## Active-state / auto-expand rule

```
isAreaActive(area, pathname) =
  area.matchPrefixes.some(p => pathname === p || pathname.startsWith(p + "/"))
```

`matchPrefixes` per area = the static portion of every item's `to`. Evaluated across all 6 areas on every render; the containing area is expanded and visually indicated (FR-004). No two areas' prefixes overlap in the surviving route set, so no tie-break case exists today — longest-prefix priority is specified for forward compatibility only.

## Guarantee

No screen address changes (FR-009): every `to` above is copied verbatim from the current `App.tsx`. Both legacy redirects keep their existing source and target under this feature; bookmarks, parent emails, and Spond links resolve exactly as before.

## Role matrix

See `../data-model.md` §3 for the full area/item × role table (not duplicated here).
