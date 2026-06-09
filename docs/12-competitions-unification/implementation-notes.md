# Unified Competitions Module — Implementation Notes

**Feature**: 007-competitions-consolidation
**Branch**: `claude/race-competition-consolidation-dqRZv`
**Completion date**: 2026-06-08
**Spec / plan / contracts**: `specs/007-competitions-consolidation/`

---

## Overview

Six independently shippable waves (A–F) consolidated the two overlapping race areas
(`/competitions` CRUD and `/coach/race-analysis` AI module) into one coherent
`/competitions` module and delivered the capabilities that were designed but not yet
shipped. All waves completed green (lint, type-check, pytest, vitest, axe).

---

## Wave A — Results & standings read endpoints

### New endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/race-events/{id}/results` | Per-event finishing order, grouped by category |
| `GET` | `/api/race-events/{id}/standings` | Season cumulative standings from the `season_standings` view |

Both endpoints live on the existing `race_events` router under the
`/api/race-analysis/race-events/` prefix (same router, same base path as the existing
`GET /api/race-events/{id}` detail endpoint).

**Query parameters (both):** `category_id` (filter), `club_only` (bool — keeps only rows
where `athlete_id` resolves to the requesting coach's club).

**Results response shape** (per category):
```json
{
  "race_event_id": 12,
  "categories": [
    {
      "category_id": 3,
      "code": "INF_M",
      "label": "Infantil Masculino",
      "rows": [
        {
          "position": 1,
          "competitor_id": 88,
          "display_name": "…",
          "club_text": "…",
          "athlete_id": null,
          "is_our_club": false,
          "status": "finished",
          "race_time_ms": 3540000,
          "laps_behind": null,
          "points_awarded": 25,
          "bib_number": 12
        }
      ]
    }
  ]
}
```

`is_our_club` is `true` when `athlete_id` resolves to an athlete belonging to the
requesting coach's club. Soft-deleted rows (`deleted_at IS NOT NULL`) are excluded.

**Standings response shape** (per category):
```json
{
  "race_event_id": 12,
  "series_id": 1,
  "categories": [
    {
      "category_id": 3,
      "code": "INF_M",
      "rows": [
        {
          "rank": 1,
          "competitor_id": 88,
          "display_name": "…",
          "club_text": "…",
          "athlete_id": null,
          "is_our_club": false,
          "total_points": 100,
          "events_count": 4,
          "best_position": 1
        }
      ]
    }
  ]
}
```

Standings data comes from the existing `season_standings` SQL VIEW; this endpoint is a
read-only projection with no storage.

**Parent access:** both endpoints apply row-level scoping — a parent receives only rows
where `athlete_id ∈ {their own children}`. No other minor's data is returned.

### Frontend

- `ResultsTab` and `StandingsTab` components use the shadcn `ui/table` primitive (added
  as a local component; no new runtime dependency).
- Category filter (select) and "solo mi club" toggle are client-side; data is
  already pre-filtered by the server when `club_only=true`.
- Empty state includes a call-to-action to import when no results exist.

---

## Wave B — Navigation consolidation

- Single "Competencias" sidebar entry. The formerly separate "AI Analysis" sidebar entry
  was removed.
- AI analysis pages (`RaceAnalysisPage`, `ClubInsightsByRacePage`) are reachable only
  from within `/competitions/*`.
- Legacy routes now serve `<Navigate>` redirects (HTTP 301 semantics in the SPA):
  - `/coach/race-analysis` → `/competitions/insights`
  - `/training/races/:id/club-insights` → `/competitions/:id?tab=insights`
- The 410 flip (removing the redirects) is deferred to a post-deploy follow-up (one
  release cycle, per decision D7 in `workflow.md`). No backend change in this wave.

---

## Wave C — Athlete call-up roster

### New table: `race_event_roster`

Migration: `e5f6a7b8c9d0` (chained to current head).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `race_event_id` | FK → `race_events` CASCADE | |
| `athlete_id` | FK → `athletes` RESTRICT | must be a club athlete |
| `status` | enum `called_up\|confirmed\|withdrawn` | default `called_up`; stored lowercase via `values_callable` |
| `note` | varchar(300) nullable | non-identifying notes only |
| `created_by_user_id` | FK → `users` RESTRICT | |
| `created_at` / `updated_at` | datetime | |

Constraint: `UNIQUE(race_event_id, athlete_id)`. Index on `race_event_id`.

### Roster endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/race-events/{id}/roster` | coach/admin; parent sees own child only | Returns entries + reconciliation |
| `POST` | `/api/race-events/{id}/roster` | coach/admin | Add athlete to roster; 409 if duplicate; 422 if not a club athlete |
| `PATCH` | `/api/race-events/{id}/roster/{entry_id}` | coach/admin | Update `status` or `note` |
| `DELETE` | `/api/race-events/{id}/roster/{entry_id}` | coach/admin | Remove entry |

**Reconciliation** is computed (not stored) and returned in the `GET` response:
- `called_up_no_result`: roster athletes with no matching `race_results.athlete_id` for
  the event.
- `result_not_called_up`: `race_results.athlete_id` values for the event not present in
  the roster.

### Frontend: `RosterPanel`

Displays the roster entries with status chips and the reconciliation discrepancy lists.
Integrated into the `AthletesTab` of `CompetitionDetailPage`.

---

## Wave D — Stale-analysis marking on re-ingest

When a changed PDF is re-ingested (different SHA256 for the same `race_event_id`):

1. The ingestor sets `agent_runs.stale_since = <now>` on all `AgentRun` rows linked to
   that `race_event_id`.
2. Any `AthleteMonthlyNewsletter` records whose data depend on that event's results are
   marked `outdated`.
3. **No automatic re-run or re-send occurs.** All re-execution is manual and
   coach-initiated (decision D5 in `workflow.md`).

The frontend surfaces a `StaleAnalysisBadge` on runs where `stale_since IS NOT NULL`.
The "Re-execute" button is manual and requires coach confirmation.

---

## Wave E — Bidirectional calendar sync

### Semantics

- `race_event` is the **source of truth**. Changes to its `event_date`, `name`,
  `location`, or `status` propagate to the linked `calendar_events` row.
- The link is strictly 1:1: a competition links to at most one calendar event; a calendar
  event links to at most one competition.
- If a competition is cancelled (`status=cancelled`), the linked calendar event is updated
  to `EventStatus.CANCELLED`.

### Service: `calendar_sync`

Three operations in `services/race/calendar_sync.py`:

| Function | Trigger |
|---|---|
| `create_linked(race_event, session)` | On `POST /api/race-events` when `create_calendar_event=true` (default) |
| `propagate(race_event, changed_fields, session)` | On `PATCH /api/race-events/{id}` when any of `event_date`, `name`, `location`, `status` changes and a calendar event is linked |
| `link_existing(race_event_id, calendar_event_id, session)` | On `POST /api/race-events/{id}/calendar-link` |

### Changed/new endpoints

| Method | Path | Change |
|---|---|---|
| `POST` | `/api/race-events` | Body gains `create_calendar_event: bool = true` (opt-out visible) |
| `PATCH` | `/api/race-events/{id}` | Triggers propagation when linked event exists and relevant fields change |
| `POST` | `/api/race-events/{id}/calendar-link` | **New** — associates an existing calendar event; 409 if either side already linked |

The reverse direction (`EventForm` with `?race_event_id`) already existed and is
preserved unchanged.

### SQLite / BigInteger fix

The `calendar_events` primary key uses `BigInteger.with_variant` to avoid SQLite
autoincrement incompatibility in tests. No MySQL schema change.

---

## Wave F — AI privacy invariants and insights placement

- Privacy invariant tests confirm no AI-generated narrative contains a minor athlete name.
- AI insight views (`RaceAnalysisPage`, `ClubInsightsByRacePage`) are confirmed to have
  no duplicate instances; they are mounted once within `/competitions/*`.
- No redundant `InsightsTab` pages.

---

## Privacy audit (T052) outcome

`data-privacy-guard` audited the 34 new/changed surfaces. Status: **APPROVED WITH CONDITIONS**.

- **HIGH — resolved.** The coach roster `note` (free text, could mention another
  athlete) is now stripped from parent-scoped roster reads (`services/race/roster.py`);
  parents already only receive their own child's entry. Covered by
  `test_get_roster_parent_note_stripped`.
- Checks passed: server-side parent scoping enforced on all three new read paths
  (results / standings / roster) via `allowed_athlete_ids_for`; reconciliation empty for
  parents; ids-only logs; no minor names to the AI model; `AI_LOG_PROMPTS` guard intact;
  fictional test fixtures; no PII in error messages or commit history.

## Deferred items

| Item | Reason | Follow-up |
|---|---|---|
| 410 flip for `/coach/race-analysis` and `/training/races/:id/club-insights` | Requires one full release cycle with redirects active before removing them (D7). | Post-deploy PR, after first deploy of 007. |
| Parent-facing results view (FR-030 / US1 scenario 5) | — | ✅ **Done.** `/parents/competitions/:raceEventId` shows results + standings scoped to the parent's own child; reachable from the parent calendar event detail. Backend reads now carry event header fields. |
| v1 AI insight persistence stores rehydrated names (MEDIUM, pre-existing) | Out of scope for 007; the v2 path already persists pseudonyms and `pii_scrubbed_at` retention exists. | Align v1 persist path to store the pseudonym draft. |
| Real MySQL ingest and deploy | Pending coach approval. | Same as all other pending deploys. |

---

## Reference documents

- Spec: `specs/007-competitions-consolidation/spec.md`
- Plan: `specs/007-competitions-consolidation/plan.md`
- API contracts: `specs/007-competitions-consolidation/contracts/api.md`
- Data model: `specs/007-competitions-consolidation/data-model.md`
- PRD / route map: `docs/12-competitions-unification/workflow.md`
