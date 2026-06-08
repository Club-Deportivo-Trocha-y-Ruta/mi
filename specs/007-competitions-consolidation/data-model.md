# Phase 1 Data Model: Unified Competitions Module

**Feature**: 007-competitions-consolidation
**Date**: 2026-06-08

> Almost all entities already exist. This document states what is **reused as-is**,
> what is **read-only projected**, and the **single net-new table** plus the one
> nullable column already present. Names below are the real schema names.

## Reused as-is (no change)

### RaceEvent (`race_events`)
The competition/round. Key fields: `id`, `series_id`, `sequence_number` (= válida_num; 99 = Departmental Championship), `name`, `event_date`, `location`, `is_championship`, `status` (`scheduled|completed|cancelled`), conditions (`climate`, `temperature_c`, `surface_condition`, `altitude_msnm`, `weather_notes`), `pdf_results_filename`, `pdf_general_filename`, `calendar_event_id` (FK→calendar_events, SET NULL).
Relationships: `series`, `creator`, `calendar_event`, `results`, `imports`.

### RaceResult (`race_results`)
One rider's result per `(event_id, category_id, competitor_id)` (unique). Fields used by the results table: `position`, `status` (`finished|dnf|dns|dsq|minus_laps`), `race_time_ms`, `laps_behind`, `points_awarded`, `bib_number`, `competitor_id`, `athlete_id` (NOT NULL ⇒ confirmed club athlete = "our club" highlight), `category_id`, `deleted_at` (soft-delete — exclude from reads).

### RaceCompetitor (`race_competitors`)
A person in results. `athlete_id` (nullable) is the **only** link marking a competitor as a club athlete; set on coach-confirmed match with `linked_at`/`linked_by_user_id`. Reused for auto-match + confirm/fix.

### RaceSeries / RacePointsScheme / RaceCategory
Season grouping, points rules (`copa_valle_2026`), and the 26 categories. Drive standings and category filtering.

### RaceImport / RaceResultRevision
Ingestion audit (SHA256 idempotency, `parent_import_id`, `revision_reason` closed catalog) and per-result revision history. Reused for reload/fix.

### CalendarEvent (`calendar_events`)
`event_type=competition` rows carry `race_event_id` (FK→race_events, RESTRICT) with CHECK `event_type != 'competition' OR race_event_id IS NOT NULL`. The 1:1 partner of a competition.

### AgentRun (`agent_runs`)
AI analysis run; already has `stale_since` (nullable) — set when a re-ingest detects a different SHA256. Reused for the "outdated analysis" badge.

## Read-only projection (no storage)

### SeasonStanding (VIEW `season_standings`)
Existing SQL view aggregating points by competitor/category across a series/season. Exposed by a new read endpoint; rows with a linked club athlete are highlighted. `analytics.club_ranking(season)` complements with club-scoped aggregates.

## NET-NEW

### RaceEventRoster (`race_event_roster`) — call-up
The single new table. Independent of results and calendar so it can exist for a planned round.

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `race_event_id` | FK→race_events (CASCADE) | the competition |
| `athlete_id` | FK→athletes (RESTRICT) | club athlete called up |
| `status` | enum `called_up\|confirmed\|withdrawn` | default `called_up` |
| `note` | str(300) nullable | non-identifying note |
| `created_by_user_id` | FK→users (RESTRICT) | coach/admin |
| `created_at` / `updated_at` | datetime | |

Constraints: `UNIQUE(race_event_id, athlete_id)`; index on `race_event_id`.
Migration: new table + enum `raceeventrosterstatus` (values_callable lowercase), chained to current head.

**Reconciliation (computed, not stored)**: for a competition,
- *called up, no result* = roster athletes with no `race_results.athlete_id` for the event.
- *result, not called up* = `race_results.athlete_id` (distinct) for the event not in roster.

## State transitions

- **RaceEvent.status**: `scheduled` → `completed` (after results) / `cancelled`. Cancellation propagates to the linked calendar event (`EventStatus.CANCELLED`).
- **RaceEventRoster.status**: `called_up` → `confirmed` / `withdrawn`.
- **AgentRun**: gains `stale_since` (vigente→stale) on re-ingest with changed SHA256; cleared on manual re-execute.

## Validation rules (from requirements)

- Results read excludes `deleted_at IS NOT NULL` (FR-010).
- "Our club" filter = `RaceResult.athlete_id IS NOT NULL` resolved to the coach's club (FR-012).
- Parent results read filtered to `athlete_id ∈ {their children}` only (FR-030).
- Roster unique per `(event, athlete)`; cannot add a non-club athlete (FR-022).
- Calendar link strictly 1:1; metadata edits propagate (FR-024–026).
- Revision requires closed-catalog reason on deletes; identical SHA256 = no-op (FR-016/017).
