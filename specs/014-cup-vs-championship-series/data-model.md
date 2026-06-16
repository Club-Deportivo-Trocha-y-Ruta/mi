# Phase 1 Data Model: Cup vs Championship Series

**Feature**: 014-cup-vs-championship-series
**Date**: 2026-06-15

## Overview

One new enum column on `race_series`. No change to `race_events`,
`race_results`, or any other table. Existing rows backfilled to `cup`; one
existing event reclassified into a new championship series.

---

## Entity: RaceSeries (modified)

Table: `race_series`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id | INT PK | no | auto | unchanged |
| name | VARCHAR(150) | no | — | unchanged |
| season_year | INT | no | — | unchanged |
| organizer | VARCHAR(150) | yes | NULL | unchanged |
| points_scheme_code | VARCHAR(50) | no | — | unchanged; championships reuse `copa_valle_2026` (D5) |
| **kind** | **ENUM('cup','championship')** | **no** | **'cup'** | **NEW** — series type discriminator |
| created_at | DATETIME | no | now | unchanged |
| updated_at | DATETIME | no | now | unchanged |

Constraints:
- `UNIQUE(name, season_year)` — unchanged; already allows multiple series per
  season (multiple cups and/or championships).

New enum (Python):
```python
class RaceSeriesKind(str, enum.Enum):
    cup = "cup"
    championship = "championship"
```
Mapped with `values_callable=lambda e: [x.value for x in e]` (project convention),
MySQL type name `raceserieskind`.

Validation / invariants:
- **INV-1 (FR-001/FR-014)**: `kind` is exactly one of `cup` | `championship`.
- **INV-2 (FR-005)**: a series with `kind=championship` has **at most one**
  `race_events` row. Enforced in the service layer (D3), not the DB.
- **INV-3 (FR-002/FR-003)**: for `kind=cup`, each event's `sequence_number` is the
  user-meaningful round number, unique within the series. For
  `kind=championship`, the single event's `sequence_number` is fixed to `1` and is
  never displayed.

---

## Entity: RaceEvent (unchanged schema, new behavioral rules)

Table: `race_events` — **no DDL change**.

Behavioral rules derived from the parent series' `kind`:

| Field | Cup series | Championship series |
|---|---|---|
| sequence_number | user-supplied round (1..N), unique in series | forced to `1`, hidden in UI |
| is_championship | `false` | `true` |
| name, event_date, location, conditions | as today | as today |

- `is_championship` remains the field the list/detail badges read (FR-009).
- Derivation happens server-side on create/import: the client does not need to set
  `is_championship` or `sequence_number` for championships.

---

## Entity: Result (unchanged)

Table: `race_results` — **no change**.

- Results exist for both cup rounds and championship events.
- Only results whose event belongs to a `kind=cup` series contribute to the season
  cumulative points ranking (enforced at read time — see Ranking rules).

---

## Ranking rules (read-time, no schema change)

| Read path | File | Change |
|---|---|---|
| Season cumulative panorama | `services/race/season_panorama.py` | add `AND rs.kind = 'cup'` to the aggregate SQL (excludes all championship results from season points/podiums/wins) |
| Per-event season standings | `services/race/standings.py` | guard: if resolved `series.kind != 'cup'` → return `None` (no cumulative standing for a single-event championship) |

---

## State / lifecycle

- A series' `kind` is set at creation and is not part of normal edit flows. Changing
  a series' `kind` after it has events is out of scope; the edit form changes a
  *competition's series membership*, not a series' kind. Edge case from the spec
  (cup↔championship conversion) is handled by validation: the resulting state must
  remain valid for the target series' kind (round numbering / ranking stay
  consistent), otherwise the operation is rejected.

---

## Data migration (one-time, in the schema revision)

Revision `down_revision = "a3b4c5d6e7f8"`.

1. `ALTER TABLE race_series ADD COLUMN kind ENUM('cup','championship') NOT NULL DEFAULT 'cup'`.
2. Backfill: existing rows already default to `cup` (no-op, but assert).
3. Upsert championship series (idempotent via `UNIQUE(name, season_year)`):
   `('Campeonato Departamental 2026', 2026, 'Liga Vallecaucana de Ciclismo', 'copa_valle_2026', 'championship')`.
4. Repoint the legacy Departmental event (guarded `UPDATE ... WHERE is_championship=1
   AND series_id = <Copa Valle 2026> AND season matches`) to the new series, set
   `sequence_number = 1`.
5. Downgrade: repoint the event back to Copa Valle with `sequence_number=99`, delete
   the championship series if it has no other events, then drop the column.

Idempotency: steps 3–4 are guarded so re-runs and championship-free environments
(fresh test DBs) succeed without error and without duplicating rows.
