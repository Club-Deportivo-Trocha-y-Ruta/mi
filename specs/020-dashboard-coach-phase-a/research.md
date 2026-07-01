# Phase 0 Research: Coach Dashboard — Phase A

All questions resolved by code review of the existing frontend/backend. No web/MCP research required.

## Decision 1 — Single data source: `GET /api/alerts`

**Decision**: Re-derive all dashboard athlete data from the existing `GET /api/alerts` query (`useAlerts`), and delete the `getAthletes` + `getAthlete`-per-id fan-out in `useDashboardStats`.

**Rationale**:
- `backend/app/routers/alerts.py` already scopes to the coach's clubs via `_coach_club_ids(user)` and returns, per athlete: `athlete_id`, `athlete_name`, `age_decimal`, `category`, `measurement_status`, `last_measurement_date`, `next_due_date`, `days_overdue`, `current_phv_status`, `measurement_interval_days`, `growth_velocity_cm_month`, `growth_alerts`, `training_implications` — plus summary counts `overdue/due_soon/ok/never_measured/rapid_growth_count` (`frontend/src/types/alerts.types.ts`).
- "Total atletas" = `athletes.length`; "Última evaluación" = max `last_measurement_date`; "Estado PHV" = derived (Decision 2). All available in one payload.
- `MeasurementAlerts` already calls `useAlerts`; sharing the `["alerts"]` query cache means the whole dashboard loads from **one** round-trip.

**Alternatives considered**:
- *New `GET /dashboard/summary` endpoint* — rejected for Phase A: adds backend work/migration risk for zero extra data; `/alerts` already suffices. Revisit only if Phase B/C bands need cross-module aggregation.
- *Keep `getAthletes` for `total`* — rejected: redundant second request; `/alerts` already returns the scoped athlete set.

## Decision 2 — PHV metric formula (OQ-2 resolved)

**Decision**: "Estado PHV" card shows **"V de A con medición vigente"** where:
- A = number of active-club athletes (`athletes.length`).
- V = athletes with `measurement_status` **not** in `{overdue, never}` (i.e. `ok` or `due_soon` — measured within the interval window).
- Renders "--" when A = 0.

**Rationale**: The old "V / total evaluados" mixed test data and was alarmist. Vigency reuses the already-computed `measurement_status`, so no new threshold/magic number is introduced; the window is exactly `measurement_interval_days` as the backend already applies it.

**Alternatives considered**: percentage ("X% al día") — rejected as less concrete for a small roster; absolute "V de A" is clearer for the coach.

## Decision 3 — List truncation & sort (OQ-3 resolved)

**Decision**: Actionable list caps at **8** rows, sorted by urgency: `overdue` first (largest `days_overdue` first) → `due_soon` (smallest days-to-due first) → `never`. When M > 8, show **"Ver todas (M)"** linking to **`/athletes`** (plain list). No status filter/URL param added to `AthletesListPage` (deferred).

**Rationale**: `AthletesListPage` (`frontend/src/routes/athletes/AthletesListPage.tsx`) has only client-side search + PHV filters and no measurement-status filter or URL params. Adding one is out of Phase A's minimal scope; a plain link satisfies FR-003 today.

## Decision 4 — Club scope for multi-club coach (OQ-1 resolved)

**Decision**: Call `/alerts` with **no `club_id`**. `MeResponse.club_ids: number[]` allows >1 club, but no active-club selector exists in `auth.store.ts`. The backend already returns the **union of the coach's own clubs** and never other clubs, so FR-005 holds without a selector. "Active club" in this spec = the coach's club(s).

**Rationale**: Simplest safe design; matches current app behavior (`useDashboardStats`/`useAlerts` pass no `club_id` today). A per-club selector is a Phase B+ concern.

**Privacy note**: FR-005/NFR-003 require an automated **cross-club isolation** test — a coach of club X must see zero club Y / seed athletes anywhere on the dashboard. This is treated as an access-control test, not cosmetic.

## Open items

None. All OQ resolved; no NEEDS CLARIFICATION remain. No backend change.
