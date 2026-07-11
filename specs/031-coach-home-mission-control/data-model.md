# Data Model — 031 Coach Home Mission Control

**No schema changes. No Alembic migration.** Every entity below is a **read-model** — a shape assembled at request/render time from existing tables (`training_sessions`, `session_attendances`, `athletes`, `race_events`, `parental_consents`, `athlete_ai_insights`, `agent_runs`) or, for two rows, from an existing endpoint queried with different parameters. This file documents (1) the one new backend read-model (`CoachSummary`) and (2) the frontend-only composed view-model that assembles all tiles/rows, since the two together are what "the data model" means for a feature with no new tables.

## 1. `CoachSummary` (backend read-model — new)

Backing `GET /api/dashboard/coach-summary` (full contract: `contracts/coach-summary-endpoint.md`). Computed fresh on every request from existing tables; nothing is persisted under this shape.

```
CoachSummary
├── generated_at: datetime (UTC)             — when this snapshot was computed; not cached server-side
├── consents_pending: int | null             — count of club athletes with no current-policy, non-withdrawn consent
├── insights_stale: int | null                — count of club athletes whose active insight's run is stale
└── weekly_load: WeeklyLoadBand[] | null      — one entry per age band with ≥1 athlete in the club roster
```

| Field | Type | Null semantics | Validation |
|---|---|---|---|
| `generated_at` | `datetime` (ISO 8601, UTC) | Never null | Server clock; informational only, not used for cache-busting |
| `consents_pending` | `int \| null` | `null` **only** if the sub-query raised (logged, isolated per R2/contract) — never null for "zero pending," which is `0` | `>= 0` when present |
| `insights_stale` | `int \| null` | Same isolation rule as `consents_pending` | `>= 0` when present |
| `weekly_load` | `WeeklyLoadBand[] \| null` | `null` if the sub-query raised. An **empty array** (`[]`) is valid and distinct from `null` — it means the computation succeeded but the club has no athletes in either tracked band (e.g., a brand-new club with no 10-15-year-olds yet), which the frontend renders as the tile's own empty state, not an error | Array length ∈ {0, 1, 2} — never more than the two defined bands |

### `WeeklyLoadBand`

```
WeeklyLoadBand
├── age_band: "10-12" | "13-15"
├── planned_minutes: int        — sum of duration_min for this week's planned sessions attributable to the band (R3)
├── cap_minutes: int            — band's conservative cap (band-minimum-age × 60; R3) — 600 for "10-12", 780 for "13-15"
└── athlete_count: int          — number of distinct club athletes currently in this band (context for the tile's caption; NOT how many attended any specific session)
```

| Field | Type | Null semantics | Validation |
|---|---|---|---|
| `age_band` | enum string | Never null | One of the two literal values; never a third band |
| `planned_minutes` | `int` | Never null within a present entry | `>= 0`. May legitimately be `0` (no planned sessions this week) |
| `cap_minutes` | `int` | Never null | Fixed per `age_band`: `600` for `"10-12"`, `780` for `"13-15"` — server-computed constant, not stored, so it cannot drift from CLAUDE.md's rule without a code change |
| `athlete_count` | `int` | Never null | `>= 0` |

A band is **omitted from the array** (not present with zero values) when the club has zero athletes in that band — distinguishes "no one to track" from "tracked, currently at zero load," per FR-005 acceptance #3's degrade-gracefully requirement.

### Partial-failure isolation (contract detail, restated here for the model)

Each of the three fields is computed by its own try/except at the service layer (`backend/app/services/dashboard_summary.py`, per `plan.md` Project Structure). A failure in one computation nulls only that field and logs a correlation-id'd error (Constitution Quality Gates: no PII in the log line — ids/counts only). The endpoint still returns `200` as long as at least the request itself is well-formed (RBAC/validation errors still return their normal 401/403 — see the endpoint contract); a total DB-connectivity failure naturally still surfaces as a 5xx, same as any other endpoint.

## 2. `CoachHomeViewModel` (frontend-only composition — new, no backend shape)

Not a network payload — this is the shape the landing page's rendering logic reasons about, assembled client-side from **four independent query results** (three existing/reused, one new). Documented so implementers don't need to reverse-engineer the composition from component code.

```
CoachHomeViewModel
├── nextSession: NextSessionTile | null | undefined
├── nextRace: NextRaceTile | null | undefined
├── pending: PendingInbox
└── weeklyLoad: WeeklyLoadBand[] | null | undefined     — see §1; undefined while loading, null on aggregate failure
```

`| null | undefined` throughout: `undefined` = still loading (render skeleton); `null` = query resolved but the aggregate/tile has nothing to show (render the tile's own defined empty/unavailable state, never a generic error) — this mirrors the `undefined`/`null`/`string` three-state idiom the codebase already uses for insight freshness (`AnalyzeAthleteButton.tsx:66-70`), reused here for consistency rather than inventing a fresh convention.

### `NextSessionTile` (derived from `useTrainingSessions`, no new type — reads existing `TrainingSession`)

```
NextSessionTile
├── session: TrainingSession           — the earliest item with status="planned" and scheduled_date/time >= now (club tz)
└── daysUntil: number                  — 0 = "hoy", 1 = "mañana", >1 = "en N días" (see plan.md Technical Context re: new helper)
```

Selection rule: filter `status === "planned"`, combine `scheduled_date` + `scheduled_start_time` in club timezone, exclude anything already in the past **by time**, not just by date (Edge Case: "a session today but already finished... should not show as hoy pending"), sort ascending, take index 0. `null` when the filtered set is empty (purposeful empty state, FR-001).

### `NextRaceTile` (derived from `useRaceEventsList`, no new type — reads existing `RaceEventListItem`)

```
NextRaceTile
├── event: RaceEventListItem           — earliest item with event_date >= today (club tz)
├── daysUntil: number
├── tier: "A" | "B" | "C" | "CD" | null    — from getCarreraTier(event.event_date); null if the date isn't in the CARRERA_TIER map
└── taperGuidance: TaperGuidance | null    — new frontend-only lookup, keyed by tier (R7); null when tier is null
```

`TaperGuidance` (new, frontend-only constant map — not fetched, not persisted):
```
TaperGuidance
├── label: string          — "A — Tapering completo", "B — Mini-tapering", "C — Diagnóstica", "CD — Campeonato Departamental"
├── taperDays: [number, number] | null   — [5,7] for A/CD, [3,4] for B, null for C (no tapering)
└── urgency: "none" | "upcoming" | "in_window"   — derived from daysUntil vs taperDays at render time, not stored
```

`null` (whole tile) when the filtered set is empty — the season-over empty state (FR-002, "states plainly when the season has no future race"), distinct from a loading `undefined`.

### `PendingInbox`

```
PendingInbox
├── resultsToImport: RowState        — from the SAME useRaceEventsList result as nextRace; filter !has_results && event_date < today
├── activitiesUnlinked: RowState     — from useActivityReview({linked:"false", page_size:1}).total
├── newslettersDue: RowState         — from 028's useNewsletterStatusSummary; count status !== "sent"
├── consentsPending: RowState        — from CoachSummary.consents_pending
└── insightsStale: RowState          — from CoachSummary.insights_stale
```

`RowState = { count: number; href: string } | null | undefined` — `undefined` while its source query is loading, `null` when the source is unavailable (query error, or — for `activitiesUnlinked` specifically — the endpoint isn't mounted because Strava is disabled club-wide) and the row is **omitted from the list**, never rendered as a zero or an error line (FR-004). All five `RowState | null | undefined` rows are independent; the "all-clear" positive empty state (FR-004, US2 acceptance #3) renders only when **every** row that resolved (i.e., is not `undefined`/`null`) has `count === 0` — a row still loading or unavailable does not by itself block the all-clear state from eventually showing once it resolves to zero, but a row that resolves to a **non-zero** count always suppresses the all-clear render for the list as a whole.

## 3. Explicitly out of scope for this data model

- No new database tables, columns, enums, or indexes. All aggregation reads existing columns (`training_sessions.duration_min/status/scheduled_date`, `session_attendances.athlete_id/session_id`, `athletes.birth_date`, `parental_consents.withdrawn_at/policy_id`, `athlete_ai_insights.is_active`, `agent_runs.stale_since`).
- No changes to `AlertsSummary`/`AthleteAlert` (`backend/app/schemas/alerts.py`) — `MeasurementAlerts` is preserved byte-for-byte in behavior (FR-006).
- No changes to the 028 `newsletter-status-summary` response shape — consumed as-is.
- No changes to `RaceEventListItem`/`TrainingSession`/`ActivityOut` types — consumed as-is, filtered/read client-side.
