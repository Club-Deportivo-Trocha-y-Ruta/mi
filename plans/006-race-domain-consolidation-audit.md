# Plan 006: Investigate (don't fix) the race-domain split — map RaceImport vs RaceEvent responsibilities and verify the 007–009 consolidation actually completed

> **Executor instructions**: This is an INVESTIGATION plan. The deliverable is
> a written report, not code. Read-only on all source files. Follow the steps,
> answer every question in the report template, and stop there. When done,
> update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 9871c99..HEAD -- backend/app/routers/race_imports.py backend/app/routers/race_events.py backend/app/routers/race_analysis.py backend/app/models/race_import.py backend/app/models/race_event.py`
> Drift here is acceptable (this plan only reads) but note any drifted file in
> the report.

## Status

- **Priority**: P3
- **Effort**: M (investigation only)
- **Risk**: LOW (no code changes)
- **Depends on**: none
- **Category**: tech-debt (investigation)
- **Planned at**: commit `9871c99`, 2026-06-11

## Why this matters

The race/competitions domain is served by three large routers —
`race_imports.py` (1,186 lines), `race_events.py` (786 lines),
`race_analysis.py` (1,789 lines) — plus ~25 service modules under
`backend/app/services/race/`. Specs 007 ("Unified Competitions Module"),
008 and 009 are all marked "Complete — deploy pending" in `CLAUDE.md`, and the
audit could not determine from the outside whether the consolidation those
specs promised actually finished, or whether two parallel create/update paths
for competitions still exist. Before anyone writes a (HIGH-risk, multi-day)
consolidation refactor plan, the cheap move is a precise map: what each
router/service owns, where the overlap really is, and whether the specs match
the code. **Important prior**: the data models themselves look complementary,
not duplicated — `RaceImport` is an ingestion/audit record (sha256, storage
paths, parse_meta_json, revision lineage) that links to `RaceEvent` via its
`event_id` FK; `RaceEvent` is the domain entity (date, location, climate,
status, calendar link). The suspected duplication is at the **router/schema/
service** layer. The investigation must confirm or refute that.

## Current state (verified facts to build on)

- `backend/app/models/race_import.py` — `RaceImport` (lines 81+): `filename`,
  `sha256`, `series_id`, `status` (pending/committed/...), `stats_json`,
  `event_id` FK → race_events (line 131), `kind`, storage paths/urls,
  `parse_meta_json`, revision fields (`parent_import_id`,
  `revision_reason`).
- `backend/app/models/race_event.py` — `RaceEvent` (lines 71+): `series_id`,
  `sequence_number`, `name`, `event_date`, `location`, `is_championship`,
  `calendar_event_id` FK, `status`, race-condition fields (climate,
  temperature_c, surface_condition, altitude_msnm, weather_notes),
  `pdf_results_filename`/`pdf_general_filename` (note: filename strings here
  AND storage paths on RaceImport — one concrete overlap lead),
  relationships: `results`, `imports`, `roster_entries`.
- Routers: `backend/app/routers/race_imports.py` (PDF parse → dry-run →
  commit pipeline; commit CREATES the RaceEvent via
  `services/race/ingestor.py`), `backend/app/routers/race_events.py` (CRUD +
  results read, 15 endpoints), `backend/app/routers/race_analysis.py`
  (standings/analytics/AI, 12 endpoints), plus `race_competitors.py`,
  `club_race_insights.py`, `athlete_race_analysis.py`.
- Specs to audit against: `specs/007-competitions-consolidation/spec.md`,
  `specs/008-associate-competition-calendar/spec.md`,
  `specs/009-cleanup-duplicate-competition/spec.md` (+ their `plan.md`/
  `tasks.md`).
- Frontend entry points: `frontend/src/routes/competitions/` and
  `frontend/src/api/raceEvents.ts`, `raceImports.ts`, `raceResults.ts`,
  `raceStandings.ts`, `raceRoster.ts`, `raceCompetitors.ts`,
  `raceAnalysis.ts` — seven API modules over the same domain.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Endpoint inventory | `grep -n "@router\." backend/app/routers/race_imports.py backend/app/routers/race_events.py backend/app/routers/race_analysis.py` | full route list |
| Event-creation sites | `grep -rn "RaceEvent(" backend/app --include="*.py"` | every constructor call |
| Event-mutation sites | `grep -rn "event_date\s*=\|location\s*=" backend/app/services/race/` | leads on parallel update paths |
| Spec reading | open the three spec dirs listed above | — |

## Scope

**In scope** (files you may CREATE/modify):
- `plans/006-report.md` (create — the deliverable)
- `plans/README.md` (status row)

**Out of scope**: every source file (read-only investigation). Do not refactor
anything, however obvious it looks.

## Steps

### Step 1: Endpoint and responsibility inventory

Produce a table of every route across the three routers (method, path,
one-line responsibility, which service functions it calls). Flag any pair of
endpoints in different routers that read or mutate the same fields of
`RaceEvent`/`RaceResult`.

### Step 2: Trace the two suspected create/update paths

1. Path A: `POST /race-imports/{id}/commit` → `ingestor.ingest_event` —
   document exactly which `RaceEvent` fields it sets/updates on create AND on
   re-ingest (revision flow in `services/race/revision.py`).
2. Path B: `race_events.py` CRUD — which fields its create/update schemas
   accept (`backend/app/schemas/` race-event schemas).
3. Answer precisely: **for which fields can both paths write?** What happens
   when a coach edits an event manually and then commits a revision import —
   who wins? Cite file:line for the overwrite behavior or its absence.

### Step 3: Verify specs 007–009 against the code

For each spec: list its stated end-state ("unified X", "single flow Y",
"deleted Z"), then mark each item CONFIRMED (cite code), PARTIAL (cite the
gap), or NOT FOUND. Pay attention to anything spec 007 promised to delete or
merge that still exists.

### Step 4: Frontend duplication check

In `frontend/src/routes/competitions/` and the seven API modules: is there one
competition-creation UX or two? Does any UI still hit a route the specs
declared superseded? List dead/unused exported API functions
(grep each exported function name for call sites).

### Step 5: Write the report

Create `plans/006-report.md` with sections: (1) endpoint inventory table;
(2) field-ownership matrix (field × {import path, CRUD path, winner-on-conflict});
(3) spec 007/008/009 verification tables; (4) frontend findings; (5) a
**verdict**: one of "consolidation complete — close the finding",
"bounded gap — list of ≤5 concrete fixes worth a small plan", or
"structural duplication — full consolidation plan justified", with the
evidence for whichever verdict you reach; (6) explicitly out-of-scope
observations encountered along the way (do not act on them).

## Done criteria

- [ ] `plans/006-report.md` exists with all six sections and a single clear verdict
- [ ] Every claim in the report carries a `file:line` or spec citation
- [ ] `git status` shows changes ONLY in `plans/`
- [ ] `plans/README.md` status row updated (DONE links the report)

## STOP conditions

- If during Step 2 you find that the two paths can silently corrupt data
  TODAY (e.g. revision import wipes coach-entered race conditions), put it at
  the TOP of the report under "urgent finding" — still no code changes.
- If specs 007–009 turn out to describe a different model generation
  (pre-`race_events` table) making Step 3 unanswerable as posed, say so in
  the report and answer the spirit: "is there one competition flow or two?"

## Maintenance notes

- The report feeds a future advisor cycle: a consolidation plan (if justified)
  must depend on plan 004's standings characterization tests and a similar
  test for the ingestor before any router merge.
- The `pdf_results_filename` (RaceEvent) vs storage paths (RaceImport) overlap
  noted above is a concrete lead — confirm which one the frontend actually
  reads.
