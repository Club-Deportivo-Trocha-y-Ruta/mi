# Phase 1 Data Model: Coach Dashboard — Phase A

**No persisted entities are created or changed.** Phase A is a frontend view-model refactor over the existing `AlertsSummary` contract. This document maps the dashboard's derived view-model to the existing `/api/alerts` payload.

## Source (existing) — `AlertsSummary` (`frontend/src/types/alerts.types.ts`)

```
AlertsSummary {
  overdue: number; due_soon: number; ok: number; never_measured: number;
  rapid_growth_count: number;
  athletes: AthleteAlert[];
}
AthleteAlert {
  athlete_id; athlete_name; sex; age_decimal; category;
  measurement_status: "overdue" | "due_soon" | "ok" | "never";
  last_measurement_date: string | null; next_due_date; days_overdue;
  current_phv_status; measurement_interval_days;
  growth_velocity_cm_month; growth_alerts: (...)[]; training_implications: string | null;
}
```

## Derived view-model — `DashboardStats` (rewritten `useDashboardStats`)

| Field | Type | Derivation from `AlertsSummary` |
|---|---|---|
| `total` | `number \| null` | `athletes.length` (null while loading) |
| `lastEvaluation` | `string \| null` | max of non-null `athletes[].last_measurement_date` (lexicographic on ISO date); null if none |
| `phvVigentes` (V) | `number` | count of `athletes` where `measurement_status ∉ {overdue, never}` |
| `phvTotal` (A) | `number` | `athletes.length` |
| `isLoading` | `boolean` | `alertsQuery.isPending` |
| `isError` | `boolean` | `alertsQuery.isError` |

**Removed**: `evaluatedCount`/`totalCount` computed from `AthleteDetailOut.latest_anthropometry` via `getAthlete` per id (the N+1). No component may import `getAthlete` for dashboard stats after this change.

## Derived — actionable list (in `MeasurementAlerts`)

- `actionable` = `athletes.filter(a => a.measurement_status !== "ok")`.
- `sorted` = `actionable` ordered by: `overdue` (desc `days_overdue`) → `due_soon` (asc days-to-due) → `never`.
- `visible` = `sorted.slice(0, 8)`.
- `overflowCount` (M) = `actionable.length`; "Ver todas (M)" shown iff `M > 8`, linking to `/athletes`.

## State model (DashboardPage)

Distinct, mutually exclusive render states (FR-006):
`loading` (alertsQuery pending) → `error` (alertsQuery error) → `empty-no-club` (coach has no clubs → `/alerts` returns empty `athletes`) → `empty-no-athletes` (club(s) with 0 athletes) → `ready`.

Note: with the current `/alerts` contract, both "0 clubs" and "0 athletes" surface as `athletes.length === 0`. Phase A renders a single explicit empty state copy covering both; distinguishing them requires no new data and is optional.

## Validation rules

- `lastEvaluation` must ignore null dates; "--" shown when all null.
- PHV card shows "--" when A = 0 (never "0 de 0").
- No field outside `AlertsSummary` may be surfaced (NFR-003).
