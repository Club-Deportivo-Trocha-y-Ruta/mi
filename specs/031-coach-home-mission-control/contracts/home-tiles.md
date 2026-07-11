# Contract — Coach Home Tiles & Rows (UI)

UI contract for every tile/row on the redesigned `/dashboard` ("Inicio") landing, in the style of `specs/028-frontend-design-foundation/contracts/shared-components.md`. Components here are presentational and consume the hooks named in `data-model.md`; none fetch data themselves beyond the named hook. All: es-CO copy, WCAG 2.1 AA, ≥48×48 px interactive targets, jest-axe-clean, built on 028's `StatCard` (additive slots)/`EmptyState`/`ErrorState`/`StatusBadge` per the consumption map in `specs/028-frontend-design-foundation/contracts/shared-components.md`.

Page order (per `docs/17-coach-ux-redesign/proposal.md` §5, unchanged by this contract): Row 1 hero strip (3 tiles) → Row 2 pending-work inbox (1 card, list rows) → Row 3 `MeasurementAlerts` (unchanged, FR-006).

## Row 1, Tile 1 — Próxima sesión

| | |
|---|---|
| **Data source** | `useTrainingSessions({from_date: today, to_date: today+14d, status: "planned"})` (existing hook, `data-model.md` `NextSessionTile`) |
| **Value (leads)** | `technical_focus` or a short session name — whichever the existing `TrainingSession` shape uses as its display title (match `SessionsListPage`/`SessionsTable`'s existing convention for row title, so the tile doesn't invent a new naming rule) |
| **Hint (caption)** | relative day + time + `location` — e.g. "Mañana · 4:00 p. m. · Cancha Ginebra." Relative-day wording ("hoy"/"mañana"/"en N días") needs a **new** small helper — `formatRelativeDay` (`lib/datetime.ts:164-199`) only returns `"Hoy"/"Ayer"/"Mañana"` or falls back to an absolute date for anything further out; it does **not** produce "en N días." Add a sibling helper (or extend the tile's own logic) that returns `"en N días"` for `diffDays > 1`, reusing `formatRelativeDay`'s club-timezone day-diff math rather than re-deriving it. |
| **Loading** | `StatCard isLoading` skeleton (028 primitive) |
| **Empty** | No planned future session (or all today's sessions already finished — see Same-day rule below) → `EmptyState`: "Sin sesiones planificadas" + action "+ Planificar" → `/training/sessions/new` |
| **Error** | Query error (not cold-start) → tile-local `ErrorState` with retry; cold-start (`isColdStart`) → skeleton, not an error tone (FR-008, edge case) |
| **Link target** | Whole-card link (028 `StatCard.href`) → `/training/sessions/{id}` |
| **Same-day rule** (Edge Case) | A session scheduled today whose `scheduled_start_time` + `duration_min` has already elapsed (club tz) is excluded from "next session" — it must not render as today's pending item once it's over. Requires combining `scheduled_date` + `scheduled_start_time` in `America/Bogota`, not a date-only comparison. |
| **Privacy** | Session `location`/name only — no athlete names (the roster isn't shown on this tile). |

## Row 1, Tile 2 — Próxima carrera Copa Valle

| | |
|---|---|
| **Data source** | `useRaceEventsList({season: currentSeason()})` (existing hook; `currentSeason()` per 028 R11's club-timezone helper — FR-009) |
| **Value (leads)** | Race `name` |
| **Hint (caption)** | "en N días" + `location` + taper guidance label (`TaperGuidance.label`, `data-model.md`) |
| **Urgency treatment** | Three states, driven by `tier` + `daysUntil` vs. `taperDays`: **neutral** (outside the taper window, or tier C with no taper window at all) → default card styling; **upcoming** (within the taper window's outer bound but not yet its tightest) → `--color-warning` accent (left border or badge, icon + label per Constitution III "never color alone"); **in_window** (inside the tier's full taper window, i.e. `daysUntil ≤ taperDays[1]`) → `--color-danger`-toned accent + label "En ventana de tapering." Exact day thresholds per tier: A/CD → warning at `daysUntil ≤ 10`, danger/in-window at `daysUntil ≤ 7`; B → warning at `daysUntil ≤ 6`, in-window at `daysUntil ≤ 4`; C → always neutral (no taper window exists for a diagnostic race). |
| **Loading** | `StatCard isLoading` skeleton |
| **Empty (season over)** | No event with `event_date >= today` in the current season → states plainly, e.g. "Temporada finalizada — sin próximas carreras" (FR-002's "states plainly," not a blank/empty-state-with-CTA, since there's no create action here — the calendar is fixed) |
| **Error** | Same pattern as Tile 1 |
| **Link target** | Whole-card link → `/competitions/{id}` |
| **Privacy** | Race name/date/location only — no results, no athlete names. |

## Row 1, Tile 3 — Carga semanal (meter)

| | |
|---|---|
| **Data source** | `useCoachSummary().weekly_load` (new endpoint; `data-model.md` §1) |
| **Form** | **Meter**, not a chart (dataviz `choosing-a-form.md`: "a single ratio against a limit → meter"). Two independent small-multiple meters, one per age band present in the response — never a single shared-axis bar chart (research.md R6). |
| **Per-meter value (leads)** | Headline: planned minutes/hours for the band, e.g. "4 h planificadas" (proportional figures, not `tabular-nums` — dataviz figures rule) |
| **Per-meter caption** | Band + cap, e.g. "10-12 años · tope 10 h/semana" |
| **Meter states** | See table below |
| **Over-cap copy** | Advisory, process-framed, never alarmist (US3 acceptance #2): e.g. "10.5 h planificadas — 30 min sobre el tope de 10-12 años. Revisa el plan de la semana." Never "¡Exceso!" / warning-siren tone. |
| **Link target** | "Ver sesiones de esta semana" → `/training/sessions` with the current week's `from_date`/`to_date` pre-applied (existing `useTrainingFiltersStore`/query-param convention on `SessionsListPage`) — links to the week's sessions, not filtered by age band (the sessions list has no per-athlete-age filter today; out of scope to add one for this tile). |
| **Loading** | Skeleton bars (both bands) |
| **Absent (aggregate unavailable, `weekly_load: null`)** | Tile omitted entirely — never blocks the rest of the home (FR-005 acceptance #3, US3 acceptance #3). Never shown as an error tone. |
| **Empty (club has zero athletes 10-15)** | `weekly_load: []` → tile shows a single neutral line, "Sin atletas en edad de seguimiento (10-15 años)," not an error. |
| **Privacy** | Aggregate minutes/counts only — no athlete ids or names (FR-010). |

### Meter state table (dataviz skill applied — research.md R6)

| State | Threshold (% of `cap_minutes`) | Fill | Track | Copy tone |
|---|---|---|---|---|
| Comfortable | ≤ 80% | `--color-primary` (teal accent) | pale tint of `--color-primary` | Neutral / no callout needed beyond the value |
| Near-cap | > 80%, ≤ 100% | `--color-warning` | pale tint of `--color-warning` | "Cerca del tope — revisa antes de agregar más sesiones." |
| Over-cap | > 100% | `--color-danger` (bar renders full-width; numeric label carries the overage) | pale tint of `--color-danger` | Advisory over-cap copy above, never blocking |

## Row 2 — Pending-work inbox (one card, list rows)

Rows render in this fixed order; each independently shows/hides per its own resolution state (`RowState`, `data-model.md` §2). A row never renders a raw `0` with an implied "nothing to do here" meaning distinct from the all-clear state — see All-clear below.

| Row | Data source | Count semantics | Link target |
|---|---|---|---|
| Resultados por importar | `useRaceEventsList` result (same fetch as Tile 2), filtered `!has_results && event_date < today` | Past events still missing results | `/competitions?filter=needs-results` or the equivalent existing filtered view (reuse whatever `CompetitionsListPage`'s own `hasResults` toggle already targets — no new route) |
| Actividades sin enlazar | `useActivityReview({linked:"false", page:1, page_size:1}).total` | Unlinked Strava activities, club-wide | `/activities` (existing `ActivityReviewPage`, pre-filtered `linked=false` via the same query params) |
| Boletines pendientes del mes | 028's `useNewsletterStatusSummary(currentYear, currentMonth)` | Count of items where `status !== "sent"` | `/training/athlete-newsletters` |
| Consentimientos pendientes | `useCoachSummary().consents_pending` | See `data-model.md`/contract for `consents_pending` | Parent/consent management screen (existing route — coach-facing consent view; if none exists yet as a standalone coach screen, link to the athlete list with a `?filter=consent-pending` the athlete list may need to support, else fall back to `/athletes` unfiltered — implementer's call within existing routes, no new page for this feature) |
| Insights IA desactualizados | `useCoachSummary().insights_stale` | See `data-model.md`/contract for `insights_stale` | `/competitions/insights/season/{currentSeason}` (the season panorama — the one surviving cross-race insights view per 029's subtraction plan) or the competitions list — whichever is the coach's actual entry point for finding *which* athletes are stale (this row is a count-only signal per FR-010; it does not deep-link to a specific athlete) |

Each row: icon + count + short label + chevron/arrow, ≥48 px tall tap target (Constitution III), one link. Never a raw number with no label (Constitution III: color/status never the only carrier — same principle extends to bare counts).

### All-clear state (US2 acceptance #3, FR-004)

Renders when **every row that has resolved** (i.e., none are `undefined`/loading) reports `count === 0`, **and** at least one row has actually resolved (never show "all clear" while every row is still `undefined` — that's the loading state, not a real all-clear). Positive framing, e.g. "Todo al día — sin pendientes esta semana," with a subtle success accent (icon + label, not color alone).

### Degraded state (rows absent)

When one or more rows are `null` (unavailable), the list renders the remaining resolved rows plus the all-clear check only among those — an absent row never renders as a placeholder line, spinner-forever, or error banner (US2 acceptance #2, FR-004). No error surfaces to the coach for a merely-unavailable aggregate; that is a silent degrade, not a page-level error.

## Row 3 — Mediciones pendientes (`MeasurementAlerts`)

Unchanged. No new contract — `frontend/src/components/dashboard/MeasurementAlerts.tsx` ships byte-identical in behavior (FR-006, SC-006). Included here only to fix the page order.

## Admin variant (FR-007, US4)

- All three hero tiles and the meter render identically for admin (none link into coach-only routes: session detail, competition detail, and the sessions-filtered-by-week link are all admin-openable per `App.tsx`'s existing `ProtectedRoute` gates).
- Pending-inbox rows: identical counts/links for admin, **except** any row whose link target would land on a coach-only page must instead point at an admin-openable equivalent or be a non-interactive count (mirrors `AthleteLink`'s pattern from 028 — plain text instead of a dead link). Concretely: none of this feature's five inbox rows target `/athletes/:id` directly (that gate only affects `MeasurementAlerts`, already handled unchanged), so no row-level admin branching is expected to be needed — verified per-row at implementation time against the actual link targets chosen above.
- `MeasurementAlerts` keeps its own existing (028-fixed) admin behavior unchanged.

## Cold start (all tiles/rows)

Every tile/row shows a `Skeleton`-based loading state during the ~50 s Render wake-up, never an error tone, per FR-008 and the edge case. Per research.md R9, the "Próxima carrera" tile and "Resultados por importar" row can paint from the `persistAllowList`-cached `raceEvents` query before the live network call resolves; "Próxima sesión" and "Actividades sin enlazar" cannot (privacy-excluded queries) and always show a skeleton first on a cold cache. This difference is expected and correct, not a bug to fix uniformly.
