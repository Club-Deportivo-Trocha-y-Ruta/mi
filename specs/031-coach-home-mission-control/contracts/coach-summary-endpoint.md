# Contract — Coach Summary (read-only)

**Endpoint**: `GET /api/dashboard/coach-summary`

**Purpose**: Provide the three coach-home read-models with no existing source — consent-pending count, stale-insight count, and weekly planned load per age band — in a single grouped read (research.md R2). Everything else on the landing (next session, next race, results-to-import, activities-unlinked, newsletters-due, measurement alerts) is served by existing/reused endpoints and is **not** part of this contract.

Written in the style of, and consistent with, `specs/028-frontend-design-foundation/contracts/newsletter-status-summary.md`.

## Request

No query parameters. The endpoint is club-scoped implicitly from the authenticated user, mirroring `GET /api/athletes/alerts` (`backend/app/routers/alerts.py:37-40` takes an optional admin-only `club_id` override; this endpoint follows the same pattern — see RBAC below).

| Param | In | Type | Required | Notes |
|---|---|---|---|---|
| `club_id` | query | int | no | **Admin only**, identical semantics to `GET /api/athletes/alerts` (`alerts.py:39,47-49`): coach always resolves to their own club membership(s), regardless of any `club_id` passed (a coach-supplied `club_id` for a club they don't belong to is a 403, matching `alerts.py:57-62`'s equivalent check); admin **with** `club_id` scopes to that club; admin with **no** `club_id` gets the unscoped, all-clubs view (`alerts.py:47-49`'s exact precedent — no filter applied at all) — this endpoint deliberately does not diverge from that precedent. |

Auth: Bearer JWT.

## Response `200 application/json`

```json
{
  "generated_at": "2026-07-11T20:03:00Z",
  "consents_pending": 3,
  "insights_stale": 1,
  "weekly_load": [
    { "age_band": "10-12", "planned_minutes": 240, "cap_minutes": 600, "athlete_count": 8 },
    { "age_band": "13-15", "planned_minutes": 810, "cap_minutes": 780, "athlete_count": 6 }
  ]
}
```

Field-by-field semantics: `data-model.md` §1. Key points repeated here because they are load-bearing for RBAC/error behavior:

- `consents_pending` / `insights_stale`: non-negative integers, or `null` if that specific sub-computation failed server-side (logged; does not fail the request — see Partial failure below). **Not** `null` for "zero pending" — that case is `0`.
- `weekly_load`: array of 0–2 entries (one per age band that has at least one athlete in the club roster), or `null` if that sub-computation failed. An empty array is a valid, non-error response (club has no 10-15-year-olds yet).
- No athlete ids, names, or session content anywhere in this payload (Constitution Quality Gates; FR-010). This is verified by a dedicated privacy test (`quickstart.md`).

## Partial failure (graceful degradation, FR-004)

Each of the three fields is computed by an independent try/except in the service layer. If one sub-computation raises, that field is set to `null` in the response, the error is logged with a correlation id and **only** numeric ids/counts (never PII), and the endpoint still returns `200` for the other two fields. A total failure to reach the database is not special-cased — it surfaces as the normal 5xx any endpoint would produce on a DB outage.

## RBAC

Roles: `coach`, `admin` (403 otherwise) — identical gate to `GET /api/athletes/alerts` (`require_role([UserRole.admin, UserRole.coach])`, `alerts.py:41`). Club scoping follows the same `_coach_club_ids(user)` pattern already used by `alerts.py:33-34` and `athletes.py:50-51` — this is this helper's **third** duplication; the implementation should extract it to `app/services/permissions.py` rather than add a third inline copy (research.md R12). A coach with zero club memberships gets the same shape `alerts.py:52-56` returns for that case (all-zero/empty counts, `200`, not an error), for consistency.

## Errors

| Code | Condition | Body |
|---|---|---|
| 401 | missing/invalid token | standard error envelope |
| 403 | role not coach/admin, or coach passing a foreign `club_id` | standard error envelope |
| 422 | malformed `club_id` (non-integer) | validation detail |

No 404 case — the endpoint always returns a (possibly all-null/all-zero) summary for an authenticated coach/admin, never "not found."

## Non-functional

- **p95 ≤ 500 ms** (Constitution IV). Justified by query shape, not aspiration: all three sub-queries are bounded by the requesting club's own roster size (~20-40 athletes for this club; see research.md R3-R5 for each query's join shape), never by a global table scan. None fan out per-athlete (no N+1) — each is one grouped/joined SQL statement.
- **Query-count regression test required** (Constitution II + the codebase's established `count_selects` pattern, research.md R13): assert the endpoint issues a small, fixed ceiling of `SELECT` statements independent of how many athletes/sessions/insights exist in the seed (mirrors `backend/tests/routers/test_activities.py:865-891`'s pattern). Ceiling target: ≤ 12 SELECTs (club-scope resolution + 3 sub-aggregates, each 1-3 statements, plus driver bookkeeping headroom).
- Logged with correlation id; log lines carry only counts/ids, never names (Quality Gates).
- No caching server-side (`generated_at` is purely informational) — freshness is managed client-side (research.md R8: `staleTime: 60s`, `refetchOnMount: "always"`).

## Frontend consumer

`useCoachSummary()` (TanStack Query; key `["dashboard", "coach-summary"]`), `staleTime: 60_000`, `refetchOnMount: "always"` (research.md R8). Consumed by the weekly-load meter and the two new pending-inbox rows (`consentsPending`, `insightsStale`) on `DashboardPage`. Recommended (not required for this contract) addition to `frontend/src/lib/persistAllowList.ts`'s `PERSIST_ALLOWLIST_PREFIXES` (research.md R9) — subject to a `data-privacy-guard` review per that file's own header rule, since the payload is counts-only.

## Backend home (natural-home decision)

New router `backend/app/routers/dashboard.py`, registered `app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])` in `main.py` alongside the other coach-facing routers (near `alerts`/`athletes`, `main.py:68-71`). No existing router owns all three source tables (consents, insights/agent-runs, sessions/attendance/athletes) jointly — `alerts.py` is the closest precedent (a coach-facing landing aggregate) but is scoped to anthropometry, not this feature's concerns, so a new small file is the correct home rather than growing `alerts.py` into a second, unrelated responsibility. New schema `backend/app/schemas/dashboard.py` (`CoachSummaryOut`, `WeeklyLoadBandOut`). New service `backend/app/services/dashboard_summary.py` — flat single-purpose module, matching the precedent of `services/measurement_alerts.py` (the module backing `alerts.py`) rather than a sub-package (this feature's aggregation logic is small enough not to warrant `services/dashboard/*`).
