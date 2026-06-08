# API Contracts: Unified Competitions Module

**Feature**: 007-competitions-consolidation
All routes are coach/admin unless noted. Parent access is read-only and filtered to own child.
Base prefix follows existing convention (`/api`). Existing endpoints listed for context; **NEW**/**CHANGED** marked.

## Results & standings (NEW — fills the core gap)

### GET `/api/race-events/{id}/results`
Per-event finishing order.
- Query: `category_id?` (filter), `club_only?` (bool).
- 200 →
  ```json
  {
    "race_event_id": 12,
    "categories": [
      { "category_id": 3, "code": "INF_M", "label": "Infantil Masculino",
        "rows": [
          { "position": 1, "competitor_id": 88, "display_name": "…", "club_text": "…",
            "athlete_id": null, "is_our_club": false, "status": "finished",
            "race_time_ms": 3540000, "laps_behind": null, "points_awarded": 25, "bib_number": 12 }
        ] }
    ]
  }
  ```
- `is_our_club` = `athlete_id` resolves to the requesting coach's club.
- Excludes soft-deleted rows.
- 404 if event missing. Parent: rows filtered to own children only.

### GET `/api/race-events/{id}/standings` (and/or `/api/series/{series_id}/standings`)
Season cumulative points standings from the `season_standings` view, scoped to the event's series/season.
- Query: `category_id?`, `club_only?`.
- 200 → ranked rows `{ rank, competitor_id, display_name, club_text, athlete_id, is_our_club, total_points, events_count, best_position }` grouped by category.
- 404 if no series/standings. Parent: own children only.

## Roster / call-up (NEW)

### GET `/api/race-events/{id}/roster`
- 200 → `{ race_event_id, entries: [{ id, athlete_id, athlete_name, status, note }], reconciliation: { called_up_no_result: [athlete_id], result_not_called_up: [athlete_id] } }`.
- Parent: 403 (roster is coach planning data) OR filtered to own child — **decision: filtered to own child read-only** to match FR-030.

### POST `/api/race-events/{id}/roster`
- Body: `{ athlete_id, status?, note? }`. 201 → entry. 409 if duplicate. 422 if athlete not in club.

### PATCH `/api/race-events/{id}/roster/{entry_id}`
- Body: `{ status?, note? }`. 200 → entry.

### DELETE `/api/race-events/{id}/roster/{entry_id}`
- 204. Coach/admin only.

## Calendar sync (CHANGED — propagation)

### POST `/api/race-events` (CHANGED)
- Body gains optional `create_calendar_event: bool = true`.
- When true: creates a linked `calendar_events` row (`event_type=competition`) and sets both FK sides (1:1). When false: no calendar event.

### PATCH `/api/race-events/{id}` (CHANGED)
- When `event_date` / `name` / `location` / `status` change and a calendar event is linked → propagate (title/location/start_at/end_at/status). Race event is source of truth.

### POST `/api/race-events/{id}/calendar-link` (NEW, optional)
- Associate an existing calendar event (when `has_calendar_event=false`). Body `{ calendar_event_id }`. 409 if either side already linked (strict 1:1).

> Reverse direction (`EventForm` with `?race_event_id`) already exists and is preserved.

## Existing endpoints reused as-is (context, no change)

- Competition CRUD: `GET /api/race-events`, `GET /api/race-events/{id}`, `PATCH …/conditions`, `DELETE …` (admin, dependency-guarded).
- Import: `POST /api/race-analysis/imports/parse`, `…/{id}/dry-run`, `…/{id}/commit`, `GET …/imports`, `…/revision-reasons`, `…/{race_event_id}/diff`.
- Athlete link: `GET /api/race-competitors`, `…/{id}/suggestions`, `POST …/{id}/link`, `DELETE …/{id}/link`.
- AI analysis: `POST …/runs`, `GET …/runs/{id}/status|result`, `POST …/runs/{id}/invalidate|re-execute`, `…/chat`, `GET …/runs/{id}/pdf`, plus athlete/club/season insight reads.

## Frontend route contract (consolidation)

Single `/competitions/*` tree is the only race destination (per `docs/12-competitions-unification/workflow.md`):
```
/competitions                          list
/competitions/new | /:id/edit          create/edit metadata (+ calendar checkbox)
/competitions/import | /:id/import      ingest / re-ingest (diff)
/competitions/:id                      detail tabs: info | results | standings | conditions | athletes(roster) | insights
/competitions/insights[/athletes/:id | /club | /season/:year]   cross-round AI (coach/admin; parent 403)
```
Redirects (one release cycle, then 410): `/coach/race-analysis → /competitions/insights`; `/training/races/:id/club-insights → /competitions/:id?tab=insights`.

## RBAC matrix

| Endpoint group | coach/admin | parent |
|---|---|---|
| Competition CRUD | full | read list/detail (no edit) |
| Results / standings | full | own child rows only |
| Roster | full | own child read-only |
| Import / revision | full | 403 |
| Athlete link | full | 403 |
| AI insights (round) | full | own child only, no names |
| AI insights (athlete/club/season) | full | 403 |
