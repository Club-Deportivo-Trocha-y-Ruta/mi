# Phase 0 Research: Cup vs Championship Series

**Feature**: 014-cup-vs-championship-series
**Date**: 2026-06-15

This document records the technical decisions that resolve the open design
questions for separating cup series (with numbered rounds + cumulative ranking)
from championship series (single annual event, no rounds, no season points).

All four product-level questions were resolved with the coach before planning
(standalone championships with no points, multiple championships per season,
include reclassification of the existing event, "Liga Departamental" is only an
example). The decisions below are the remaining *technical* choices.

---

## D1 — How to model the series type

**Decision**: Add a `kind` discriminator column to `race_series`
(`RaceSeriesKind` enum: `cup` | `championship`), NOT NULL, default `cup`.
Each championship is its **own series** holding exactly one event.

**Rationale**:
- `race_series` is already a generic grouping keyed by `UNIQUE(name, season_year)`,
  which already supports multiple parallel series per season at zero schema cost.
- Reuses the entire existing pipeline — `race_results`, `race_imports`,
  `standings`, analytics, AI insights — with **one** new column and no changes to
  `race_events`.
- Matches the project's established enum convention (`values_callable` storing the
  string value, used by `RaceEventStatus`, `SurfaceCondition`, `MaturationStatus`).

**Alternatives considered**:
- *New `championships` table*: rejected — duplicates results/imports/analytics and
  forces every read path to branch on two storage shapes. Over-engineering.
- *`series_id` nullable + standalone championship events*: rejected — breaks the
  `RESTRICT` FK and forces rewrites of every join and the season aggregation.

**Reference**: SQLAlchemy `mapped_column(Enum(..., values_callable=...))`; project
precedent `app/models/race_event.py` (`RaceEventStatus`, `SurfaceCondition`).

---

## D2 — `race_events` stays unchanged

**Decision**: Do not alter `race_events`. For a championship series the single
event carries `sequence_number = 1` (never surfaced in UI) and
`is_championship = true`.

**Rationale**:
- `is_championship` already exists and the list/detail badge logic
  (`CompetitionsListPage`, `InfoTab`, `CompetitionDetailPage`) already keys on it —
  preserving it avoids a frontend regression (FR-009 / SC-005).
- `sequence_number` is `NOT NULL` with `UNIQUE(series_id, sequence_number)`; using
  `1` for the lone championship event satisfies the constraint without inventing a
  "99" sentinel. Because each championship is its own series, `1` never collides.
- The legacy "`sequence_number = 99` = CD" convention is **retired**; the
  data-migration (D6) rewrites the one existing row that used it.

---

## D3 — Enforcing "a championship has exactly one event" (FR-005)

**Decision**: Enforce in the **application/service layer**, not the database.
On every event-creation path (`POST /race-events` and the import-first commit in
`race_imports`), if the target series is `kind=championship` and already has ≥1
event → reject with HTTP 409 and an explanatory message. Also server-side force
`sequence_number=1` + `is_championship=true` for championship series regardless of
client input.

**Rationale**:
- "At most one row per `series_id` where the parent series is a championship" is a
  cross-table partial constraint that is not portably expressible across MySQL 8.4
  (prod) and SQLite (tests). A service guard is portable, testable, and yields a
  friendly message (UX requirement of FR-005).
- Centralizing the guard in a small helper keeps both entry paths consistent.

**Alternatives considered**:
- *DB trigger / generated column + unique index*: rejected — not portable to the
  SQLite test engine; the constitution requires deterministic `aiosqlite` tests.

---

## D4 — Keeping championships out of the season ranking (FR-010 / FR-013)

**Decision**: Two complementary filters keyed on `series.kind`:
1. **Season panorama** (`season_panorama.py::fetch_season_panorama`): add
   `AND rs.kind = 'cup'` to the aggregate. This query sums points and counts
   races/wins/podiums **across all series of a season**, so without the filter a
   championship would contaminate the cumulative ranking. This is the primary
   ranking-integrity fix.
2. **Event standings** (`standings.py::get_event_standings`): add a guard so that
   when the resolved series is **not** `kind=cup`, the function returns `None`
   (the router then yields an empty/404 standings payload). A championship is a
   single event with no cumulative season standing, so offering one is misleading.

**Rationale**:
- `standings.py` already aggregates per `series_id`, so a *correctly reclassified*
  championship in its own series can no longer leak into the Copa Valle standings.
  The remaining risk is (a) the season-wide panorama, fixed by filter #1, and
  (b) presenting a meaningless "season standing" for a 1-event championship, fixed
  by guard #2.
- Driving exclusion off `series.kind` (not off `points_scheme_code`) keeps the
  rule explicit and independent of points configuration.

---

## D5 — `points_scheme_code` for championship series

**Decision**: Championship series reuse the existing default scheme code
(`copa_valle_2026`) — **no new seed row required**. Exclusion from rankings is
driven entirely by `series.kind`, so the scheme code is never consulted for a
championship.

**Rationale**:
- `points_scheme_code` is `NOT NULL`. Introducing a `championship_no_points` code
  would require a new `race_points_schemes` seed row and migration for zero
  behavioral benefit, because the ranking filters already exclude championships by
  `kind`. Reusing the default is the lowest-risk choice.
- Documented explicitly so a future reader does not mistake the shared scheme code
  for "championships award Copa Valle points" — they do not (D4).

**Alternatives considered**:
- *Add `championship_no_points` scheme*: deferred as unnecessary; can be added
  later if championships ever need their own points table (currently out of scope
  per the spec's non-goals).

---

## D6 — Reclassifying the existing Departmental Championship (FR-012)

**Decision**: Perform the reclassification as an **idempotent data step inside the
same Alembic revision** that adds the `kind` column.

Steps (guarded, idempotent):
1. Backfill `race_series.kind = 'cup'` for all existing rows.
2. Create (if absent) a standalone series row:
   `name='Campeonato Departamental 2026'`, `season_year=2026`,
   `organizer='Liga Vallecaucana de Ciclismo'`, `points_scheme_code='copa_valle_2026'`,
   `kind='championship'`.
3. Repoint the existing Departmental event — identified by its
   `is_championship=true` (legacy `sequence_number=99`) row under the Copa Valle
   series for season 2026 — to the new series, setting `sequence_number=1`.
4. Use `UNIQUE(name, season_year)` to make step 2 a no-op on re-run, and a
   `WHERE`-guarded `UPDATE` so step 3 only fires when a matching legacy row exists.

**Rationale**:
- Keeps schema change and the one-row data correction atomic and reproducible
  across environments (prod auto-runs `alembic upgrade head` on deploy).
- Idempotency tolerates re-runs and environments where the event does not exist
  (fresh DBs / tests) without failing the migration.
- Results rows reference the event by `event_id`, so repointing the event's
  `series_id` preserves **all** results untouched (FR-012 "no result loss").

**Reference**: Alembic `op.add_column(..., server_default=...)` then
`op.execute(...)` for the bulk backfill + guarded data step; for MySQL, the later
`op.alter_column` to drop the server_default (if desired) must pass
`existing_type` / `existing_nullable` (Context7: Alembic "Alter Column — MySQL
Specifics").

---

## D7 — Breaking the hardcoded "Copa Valle" coupling

**Decision**: Replace the hardcoded series with explicit selection on every entry
path.

Backend:
- Fix `race_imports.py::_get_or_create_series` to resolve/create by
  `(series_name, season_year, kind)` from the request instead of the hardcoded
  `_SERIES_NAME` constant (this also fixes a **latent bug**: the function currently
  ignores the `series_name` the client already sends).
- Thread the real `series_name` into `detect_revision` (today it passes the
  `_SERIES_NAME` literal).
- Add `series_kind` to the parse Form (default `cup`, backward-compatible).
- Add a minimal **series read/create API** (`GET /race-series?season=&kind=`,
  `POST /race-series`) so the frontend can list/create series instead of relying on
  a hardcoded `id`.

Frontend:
- Add a "competition type" selector (cup vs championship) to the import wizard and
  the create/edit form; hide the round-number field for championships.
- Replace `COPA_VALLE_SERIES = { id: 2 }` with data from `GET /race-series`.

**Rationale**:
- Removing the default is mandated by FR-006 / SC-004 ("no screen assumes Copa
  Valle"). Fixing `_get_or_create_series` is required for any non-Copa series to be
  created at all, and removes a silent data-integrity bug.

**Backward compatibility**: Older clients that omit `series_kind` default to `cup`,
so the existing Copa Valle import flow is unchanged.

---

## Cross-cutting: testing & privacy

- **Testing (constitution NON-NEGOTIABLE)**: every new router/service gets happy +
  negative pytest coverage (`httpx.AsyncClient` + `aiosqlite`); the migration's
  data step gets an idempotency test; frontend gets `vitest` + Testing Library for
  the type selector, conditional round field, series picker, and badge preservation,
  plus `jest-axe` on changed pages.
- **Privacy**: this feature touches only series/competition classification, not
  athlete records. New endpoints expose no minor PII; tests assert no name leakage
  in series/competition responses (Ley 1581 invariant preserved).

## Migration chaining

- Current single Alembic head: **`a3b4c5d6e7f8`** (`add_coach_note_to_race_results`).
- The new revision **MUST** set `down_revision = "a3b4c5d6e7f8"` to keep a single
  head (the repo previously had a two-heads incident; avoid reintroducing it).
