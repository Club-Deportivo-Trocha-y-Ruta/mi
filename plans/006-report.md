# Plan 006 — Race Domain Consolidation Audit

**Investigation date**: 2026-06-11  
**Worktree**: agent-a5474be4a36800bf8 (main branch state)  
**Reviewer note**: Plan 002 recently added two-phase FOR UPDATE locking to
`race_imports.py`'s commit endpoint; this is **not present** in this worktree
(no `with_for_update` in `race_imports.py`). The locking exists only in
`revision.py:_acquire_event_lock` and `insights_history.py`. The inventory
reflects what is in this worktree; the reviewer should add "(locking added
2026-06-11)" to the commit endpoint row in their copy.

---

## Section 1 — Endpoint Inventory

### `race_imports.py` (prefix `/api/race-analysis/imports`)

| Method | Path | Responsibility | Service calls |
|--------|------|---------------|--------------|
| POST | `/parse` | Upload PDF/CSV, validate magic bytes, SHA256, store to SFTP pending path, parse with pdfplumber, create `RaceImport(status=pending)` | `pdf_parser`, `storage_sftp`, `matcher.match_athletes`, `revision.detect_revision` |
| POST | `/{parse_id}/dry-run` | Re-load parsed data from SFTP, run `ingestor.ingest_event(dry_run=True)`, return match previews | `ingestor.RaceIngestor.ingest_event` |
| POST | `/{parse_id}/commit` | Re-load parsed, validate resolved matches, run `ingestor.ingest_event(dry_run=False)`, move PDFs to committed SFTP path, link `imp.event_id` | `ingestor.RaceIngestor.ingest_event`, `run_staleness.invalidate_runs_for_event`, `storage_sftp.move_object` |
| GET | `/` | Paginated list of imports with status filter | direct SQL |
| GET | `/revision-reasons` | Closed catalog of revision reason codes | none |
| GET | `/{race_event_id}/diff` | Read-only last-revision diff for a race event | `revision_diff_view.build_event_diff_view` |

### `race_events.py` (prefix `/api/race-analysis/race-events`)

| Method | Path | Responsibility | Service calls |
|--------|------|---------------|--------------|
| GET | `/` | Filtered list of RaceEvents with derived flags (`has_results`, `has_calendar_event`, `conditions_completeness`) | `race_events_svc.list_race_events` |
| GET | `/{race_event_id}/results` | Per-event finishing order by category | `results_svc.get_event_results` |
| GET | `/{race_event_id}/standings` | Season cumulative standings | `standings_svc.get_event_standings` |
| GET | `/{race_event_id}/roster` | Call-up roster with reconciliation | `roster_svc.get_roster` |
| GET | `/{race_event_id}` | Full event detail (+ `has_calendar_event` flag) | direct SQL |
| POST | `/` | Create empty RaceEvent (+ optional auto-calendar) | `race_events_svc.create_race_event`, `calendar_sync.create_linked_calendar_event` |
| POST | `/{race_event_id}/roster` | Add athlete to call-up roster | `roster_svc.add_roster_entry` |
| POST | `/{race_event_id}/calendar-link` | Associate existing CalendarEvent 1:1 | `calendar_sync.link_existing_calendar_event` |
| POST | `/{race_event_id}/calendar-event` | One-click create-and-link all-day CalendarEvent | `calendar_sync.create_linked_calendar_event` |
| PATCH | `/{race_event_id}` | Edit event metadata; propagates to calendar | `race_events_svc.update_race_event`, `calendar_sync.propagate_to_calendar` |
| PATCH | `/{race_event_id}/roster/{entry_id}` | Update roster entry status/note | `roster_svc.update_roster_entry` |
| PATCH | `/{race_event_id}/conditions` | Update race conditions (5 climate fields) | direct ORM setattr |
| DELETE | `/{race_event_id}` | Hard delete (admin only; blocked if results or calendar) | `race_events_svc.delete_race_event` |
| DELETE | `/{race_event_id}/cleanup` | Coach cleanup of no-results duplicate + its calendar | `race_events_svc.cleanup_duplicate_race_event` |
| DELETE | `/{race_event_id}/roster/{entry_id}` | Remove roster entry | `roster_svc.delete_roster_entry` |

### `race_analysis.py` (prefix `/api/race-analysis`)

| Method | Path | Responsibility | Service calls |
|--------|------|---------------|--------------|
| POST | `/runs` | Launch per-athlete agentic analysis run | `group_launch` infrastructure, `agent_runs` insert |
| GET | `/runs/{run_id}/status` | Poll run status with ETag/304 support | direct SQL on `agent_runs` + `agent_run_events` |
| POST | `/runs/{run_id}/hitl/{step_id}` | Submit HITL (approve/edit/reject) decision | direct SQL event insert + LangGraph resume |
| GET | `/runs/{run_id}/result` | Retrieve final `AnalysisOutput` JSON | direct SQL |
| GET | `/runs/{run_id}/pdf` | Render analysis markdown to PDF (weasyprint) | none |
| POST | `/chat` | Event-scoped or global AI chat turn | LLM chat service |
| GET | `/admin/ai-usage` | Aggregate AI usage metrics (admin only) | direct SQL on `athlete_ai_insights` + `agent_runs` |
| GET | `/insights/season/{year}` | Season panorama per athlete | `season_panorama.fetch_season_panorama` |
| POST | `/runs/{run_id}/invalidate` | Mark run as stale | `run_staleness.mark_run_stale` |
| POST | `/runs/{run_id}/re-execute` | Re-launch stale run (delegates to `start_run`) | `start_run` endpoint |
| POST | `/race-events/{race_event_id}/runs` | Launch group analysis for all/subset athletes in an event | `group_launch.launch_group` |
| GET | `/race-events/{race_event_id}/runs` | List runs for an event (refresh recovery) | `group_launch.list_event_runs` |

**Flagged cross-router overlap**: `GET /api/race-analysis/race-events/{id}/results`
and `GET /api/race-analysis/race-events/{id}/standings` in `race_events.py` read
`RaceResult` rows (the same table that `race_analysis.py` agents query). No
mutation overlap — `race_analysis.py` never writes `RaceResult`. The only
mutation of `RaceResult` happens through the import pipeline
(`race_imports.py` → `ingestor.py` → `revision.py`).

---

## Section 2 — Field-Ownership Matrix (RaceEvent fields)

The two creation/update paths are:
- **Import path (A)**: `POST /parse` → `POST /{id}/dry-run` → `POST /{id}/commit` → `ingestor._upsert_event` (`ingestor.py:497–556`)
- **CRUD path (B)**: `POST /api/race-analysis/race-events/` → `race_events_svc.create_race_event` (`race_events.py:98–137`); `PATCH /{id}` → `race_events_svc.update_race_event` (`race_events.py:140–186`); `PATCH /{id}/conditions` (`race_events.py router:709–786`)

| RaceEvent field | Import path writes? | CRUD path writes? | Overlap? | Winner on conflict |
|---|---|---|---|---|
| `series_id` | Yes (upsert by `(series_id, sequence_number)`) | Yes (FK ref to existing series) | Both set at create, never update | N/A — key-matched, no overwrite |
| `sequence_number` | Yes (create + always overwrite `is_championship`) | Yes (create; PATCH allows change with uniqueness check) | Both set | CRUD PATCH wins if coach changes it; import re-upsert by this key will find the row again |
| `name` | Yes — always overwritten on re-ingest (`ingestor.py:536`) | Yes (create, PATCH) | **YES — both overwrite** | Import wins on commit (unconditional); CRUD PATCH wins if done after |
| `event_date` | Yes — always overwritten (`ingestor.py:537`) | Yes (create, PATCH) | **YES — both overwrite** | Same: last writer wins |
| `location` | Yes — always overwritten (`ingestor.py:538`) | Yes (create, PATCH) | **YES — both overwrite** | Same: last writer wins |
| `is_championship` | Yes — derived `(valida_num == 99)`, always set (`ingestor.py:539`) | Yes (create, PATCH) | **YES — ingestor overwrites coach** | Import always wins (no guard): `is_championship` cannot be manually set to `True` for a non-99 valida if the import overrides it |
| `status` | Yes — always set to `COMPLETED` on create and re-ingest (`ingestor.py:540`) | Yes (create with default `SCHEDULED`; PATCH allows any value) | **YES — import force-sets COMPLETED** | Import always wins on commit; coach PATCH after import can override |
| `climate` | Yes — only if `meta.climate is not None` (`ingestor.py:541–542`) | Yes (create optional, `PATCH /conditions`) | YES (conditional) | Import only overwrites when provided; coach changes via `PATCH /conditions` are NOT overwritten on re-ingest unless new import also provides the field |
| `temperature_c` | Yes — only if not None (`ingestor.py:543–544`) | Yes | YES (conditional) | Same as `climate` |
| `surface_condition` | Yes — only if not None (`ingestor.py:545–546`) | Yes | YES (conditional) | Same |
| `altitude_msnm` | Yes — only if not None (`ingestor.py:547–548`) | Yes | YES (conditional) | Same |
| `weather_notes` | Yes — only if not None (`ingestor.py:549–550`) | Yes | YES (conditional) | Same |
| `pdf_results_filename` | Yes — only if not None (`ingestor.py:551–552`) | **NO** (not in `RaceEventCreate`/`RaceEventUpdate` schemas — `race_event.py:74–153`) | No — import owns this field exclusively | Import only |
| `pdf_general_filename` | Yes — only if not None (`ingestor.py:553–554`) | **NO** | No | Import only |
| `calendar_event_id` | **NO** | Yes (via `calendar_sync.create_linked_calendar_event` / `link_existing_calendar_event`) | No | CRUD only |
| `created_by_user_id` | Yes (on create) | Yes (on create) | N/A — create-only |

### Concrete data-corruption risk

When a coach does **both** of the following:

1. Creates a `RaceEvent` via CRUD with a custom name/date/location (e.g., translating a pre-existing paper record).
2. Later imports the official PDF for the same `(series_id, sequence_number)`.

The ingestor's `_upsert_event` (called by the commit endpoint) **unconditionally overwrites** `name`, `event_date`, `location`, `is_championship`, and `status` with whatever metadata was entered at import time (`ingestor.py:536–540`). The coach has no way to prevent this.

The race-conditions fields (`climate`, `temperature_c`, `surface_condition`, `altitude_msnm`, `weather_notes`) are **only overwritten when the import form provides a non-None value** (`ingestor.py:541–554`). If the coach fills conditions via `PATCH /conditions` *before* a re-import that also supplies conditions, the import wins silently. If the import form fields are left empty (None), the coach's values survive.

This is the **most actionable gap**: there is no last-write guard or merge strategy — both paths write the same columns, last caller wins, and the import path's overwrite is silent and unconditional for the 4 core metadata fields.

---

## Section 3 — Spec 007/008/009 Verification

### Spec 007 — Unified Competitions Module

| Spec promise | Status | Evidence |
|---|---|---|
| FR-001: Single "Competencias" navigation entry | CONFIRMED | `App.tsx:419–561` — all competition routes are under `/competitions/*`; the former `/coach/race-analysis` route is a `<Navigate>` redirect |
| FR-002: AI insights reachable only from within Competitions | CONFIRMED | `App.tsx:559–561` — `/coach/race-analysis` redirects to `/competitions/insights` |
| FR-003: Redirect old deep links during transition period, then 410 | PARTIAL | The `<Navigate>` redirect exists (`App.tsx:559`); the comment says "en Wave F se sustituirá por GonePage (410)". Wave F has not fired — the 410 replacement is pending |
| FR-004: No duplicate or orphaned race/competition pages | CONFIRMED | No second nav entry or standalone analysis page exists in routes |
| FR-005/006: Create/edit competition capturing all metadata | CONFIRMED | `RaceEventCreate` (`race_event.py:74`) + `PATCH /conditions` endpoint covers all fields |
| FR-007: Admin-only delete with guards on dependents | CONFIRMED | `race_events_svc.delete_race_event` (`race_events.py:189–233`) checks results and calendar |
| FR-009: Guided parse → preview → confirm import flow | CONFIRMED | Three-step wizard in `race_imports.py` |
| FR-010/011: Results and standings tables | CONFIRMED | `GET /{id}/results` and `GET /{id}/standings` in `race_events.py` |
| FR-012: Club athletes highlighted | CONFIRMED | `is_our_club` field derived from `athlete_id IS NOT NULL` in results |
| FR-014–FR-018: Revision detection, diff, atomic commit, audit trail | CONFIRMED | `revision.py`, `race_result_revisions` table, `invalidate_runs_for_event` |
| FR-021: Retroactive competitor linking | CONFIRMED | `race_competitors.py` router with `/link` and `/link` DELETE |
| FR-022/023: Manual call-up roster with reconciliation | CONFIRMED | `race_roster.py` service, `GET /roster` endpoint with reconciliation |
| FR-024: Default-on calendar event on create | CONFIRMED | `RaceEventCreate.create_calendar_event: bool = True` (`race_event.py:111`) |
| FR-025: Strict 1:1 calendar link | CONFIRMED | `calendar_sync.link_existing_calendar_event` enforces both sides |
| FR-026: Calendar propagation when name/date/venue changes | CONFIRMED | `propagate_to_calendar` called from `update_race_event` (`race_events.py:178`) |
| FR-027–029: AI insights at multiple scopes | CONFIRMED | `race_analysis.py` endpoints cover individual run, chat, group, season, club |
| FR-030: RBAC scoping (parents read-only, scoped to own children) | CONFIRMED | `allowed_athlete_ids_for` called in results/standings/roster |

**NOT FOUND / gaps**:
- No "spec 007 promised to delete" anything that is still around — the spec is additive. There was no pre-existing standalone route or router that spec 007 removed; it consolidated navigation, not backend code.

### Spec 008 — One-click Associate Competition to Calendar

| Spec promise | Status | Evidence |
|---|---|---|
| FR-001/002/003: One-click create all-day CalendarEvent from competition | CONFIRMED | `POST /{race_event_id}/calendar-event` (`race_events.py:642`), `create_linked_calendar_event(all_day=True)` |
| FR-004: 1:1 strict link | CONFIRMED | Both FK sides set in `calendar_sync.py:225` |
| FR-005: After creation, competition shows linked state | CONFIRMED | `CalendarAutoCreateRead.has_calendar_event = True` returned, frontend invalidates cache |
| FR-006/007: Pre-filled form path (edit details first) | PARTIAL | `raceEvents.ts:197` notes "navegar a `/calendar/events/new?race_event_id={raceEventId}`" — the pre-fill via query param is frontend-only and not independently verified in this audit |
| FR-008: Coach-only | CONFIRMED | `require_role([UserRole.coach])` on `POST /{id}/calendar-event` (`race_events.py:651`) |
| FR-009: No duplicate if already linked | CONFIRMED | `calendar_event_id is not None` guard at `race_events.py:675` |
| FR-010: Failure leaves competition unlinked | CONFIRMED | Exception propagates before FK is written |

### Spec 009 — Cleanup Duplicate Competition

| Spec promise | Status | Evidence |
|---|---|---|
| FR-001: Coach can remove no-results competition in single confirmed action | CONFIRMED | `DELETE /{id}/cleanup` (`race_events.py:549`), `cleanup_duplicate_race_event` |
| FR-002: Linked calendar event also removed | CONFIRMED | `race_events.py service:cleanup_duplicate_race_event:281–297` deletes CalendarEvent rows |
| FR-003: Only no-results competitions eligible | CONFIRMED | `RaceResult` EXISTS check re-evaluated at service layer (`race_events.py:270`) |
| FR-004: Requires explicit confirmation | PARTIAL — backend enforces nothing; confirmation is frontend UX only | No backend "confirm" token — relying on frontend confirm dialog |
| FR-005: Coach role only | CONFIRMED | `require_role([UserRole.coach])` on `DELETE /{id}/cleanup` (`race_events.py:557`) |
| FR-006: Results never removed by this flow | CONFIRMED | 409 guard blocks if results exist |
| FR-009: Stale state (competition already gone) → 404 | CONFIRMED | 404 raised at `race_events.py service:262` |
| FR-010: Existing admin-delete path unchanged | CONFIRMED | `DELETE /{id}` route still exists unchanged |

---

## Section 4 — Frontend Findings

### Single competition UX

There is **one** competition-creation flow: `CompetitionFormPage` (`/competitions/new`), which calls `createRaceEvent` in `raceEvents.ts`. The import wizard is a distinct UX (`/competitions/import` or `/:id/import`) and hits `raceImports.ts` endpoints. No duplicate creation form exists.

### Old route redirect

`/coach/race-analysis` → `<Navigate to="/competitions/insights" replace />` at `App.tsx:559`. The route is still active; transition to 410 (GonePage) is pending (Wave F, not yet done).

### Dead/unused exported API functions

All seven API modules were checked for call sites in the frontend:

- **`raceEvents.ts`**: `updateRaceEventConditions`, `createRaceEvent`, `updateRaceEvent`, `deleteRaceEvent`, `cleanupDuplicateRaceEvent`, `getRaceEvent`, `linkCalendarEvent`, `createCalendarEventForRaceEvent`, `listRaceEvents` — all referenced in hooks/pages.
- **`raceImports.ts`**: `parseRaceImport`, `dryRunRaceImport`, `commitRaceImport`, `listRaceImports`, `getRevisionReasons`, `getRaceEventDiff` — `getRaceEventDiff` is declared and exported but not called from any page or hook found in this audit. This appears to be a dead export (the diff endpoint exists on the backend but the frontend has no UI that calls it yet).
- **`raceResults.ts`**: `getRaceResults` — used in `CompetitionDetailPage`.
- **`raceStandings.ts`**: `getRaceStandings` — used in `CompetitionDetailPage`.
- **`raceRoster.ts`**: all four functions used in roster components.
- **`raceCompetitors.ts`**: all four functions used in `UnlinkedCompetitorsPage`.
- **`raceAnalysis.ts`**: `startRun`, `getRunStatus`, `submitHITLDecision`, `getRunResult`, `chatTurn`, `downloadRunPdf`, `invalidateRun`, `reExecuteRun`, `launchGroupAnalysis`, `getRaceEventRuns` — all referenced.

**`pdf_results_filename` / `pdf_general_filename` overlap**: These two columns live on `RaceEvent` and are written exclusively by the import path (`ingestor.py:528–554`). They are **not** exposed in `RaceEventRead` or `RaceEventListItem` schemas (`race_event.py:161–229`) and are **not** read by any frontend API call. The frontend reads PDFs via the SFTP storage URLs on `RaceImport` objects (e.g., `storage_url`), not from `RaceEvent.pdf_results_filename`. The `pdf_results_filename` on `RaceEvent` appears to be legacy metadata from the CLI F1.7 era with no active frontend consumer.

---

## Section 5 — Verdict

**VERDICT: Bounded gap — list of ≤5 concrete fixes worth a small plan.**

The consolidation specs (007/008/009) are substantially complete. The competition module is unified with a single navigation entry, the AI analysis is integrated, CRUD/import/calendar/roster/cleanup flows are all present and non-duplicated at the API level. There is no structural duplication of routers or schemas.

The real gap is **narrower and well-bounded**:

### Gap 1 (DATA INTEGRITY — most urgent): Silent overwrite of coach-entered metadata on re-ingest

`ingestor._upsert_event` (`ingestor.py:535–556`) unconditionally overwrites `name`, `event_date`, `location`, `is_championship`, and `status` on every commit, including revisions. A coach who creates a competition via CRUD and manually sets these fields before the official PDF exists will silently lose those values on the first import commit. The five race-condition fields (`climate`, etc.) are safer — they are only overwritten when the import form provides a non-None value — but can still clobber a PATCH-entered value if the import supplies the same field.

**Concrete fix**: Add a "CRUD-owned fields" guard in `_upsert_event` — if the event already existed (non-None at fetch time), skip overwriting `name`/`event_date`/`location` when those fields were never provided via the import form meta (i.e., treat import metadata as advisory, not authoritative, for events created via CRUD). Alternatively, mark the import path's metadata fields as "set-only-on-create."

**Citation**: `ingestor.py:535–542` (the unconditional `event.name = meta.name` block).

### Gap 2 (FRONTEND DEAD CODE): `getRaceEventDiff` has no call site

`raceImports.ts:137–146` exports `getRaceEventDiff` but no frontend page or hook calls it. The backend endpoint `GET /api/race-analysis/imports/{race_event_id}/diff` exists and works. This gap means the "view last revision diff" capability visible on the backend has no UI surface.

**Concrete fix**: Wire `getRaceEventDiff` into `CompetitionDetailPage` (new tab or expandable section in the Import tab when `has_revisions === true`).

### Gap 3 (TRANSITION INCOMPLETE): `/coach/race-analysis` redirect not yet upgraded to 410

`App.tsx:559` still serves a redirect. Spec 007 FR-003 says: "after transition period, return a clear 'moved/gone' response." The Wave F upgrade to `GonePage` has not been done.

**Concrete fix**: Replace `<Navigate>` with `<GonePage>` (or equivalent) in `App.tsx:559`.

### Gap 4 (LOCKING — reviewer note): Commit endpoint missing FOR UPDATE locking in this worktree

Per reviewer notes, plan 002 added two-phase FOR UPDATE locking to the commit endpoint in `race_imports.py`. This is not present in this worktree copy. Without the lock, two concurrent commit calls for the same `(series_id, sequence_number)` could race in `_upsert_event`. The revision path has `_acquire_event_lock` in `revision.py:657–674` but the main ingest path does not independently lock the `RaceEvent` row before the upsert.

**Concrete fix**: Confirm plan 002's locking is deployed and covers both the dry-run and commit paths; verify the `_find_pending_import` order-by-desc workaround (`ingestor.py:600`) is sufficient or whether the upstream lock is needed here too.

### Gap 5 (DEAD FIELDS): `pdf_results_filename` / `pdf_general_filename` on `RaceEvent` are inert

These fields are written by the ingestor but exposed neither by `RaceEventRead` nor by any frontend API call. The frontend gets PDF access via `RaceImport.storage_url`. The fields exist as legacy from the pre-UI CLI era (F1.7).

**Concrete fix** (low priority): Either expose them in `RaceEventRead` (as a "download source PDF" link), or add a migration to drop them and use `RaceImport.storage_url` as the canonical path. Do not fix silently — document the decision.

---

## Section 6 — Out-of-scope Observations

These were encountered during the investigation but are not acted on here:

1. **`ingestor._find_pending_import` race condition** (`ingestor.py:599–610`): The comment "FIX F-UP-REV6 BUG-2" notes that `order_by id DESC + limit 1` works around a possible duplicate pending import with the same SHA. There is no UNIQUE constraint on `(sha256, status)` in `race_imports`. A future plan should add a DB-level constraint or ensure the FOR UPDATE lock from plan 002 closes this race entirely.

2. **`season_panorama` in `race_analysis.py` vs results in `race_events.py`**: Both read `RaceResult` rows for aggregate queries. They serve different use cases (cross-event season view vs. single-event view) and do not overlap in behavior — not a duplication issue, but they share no code. A shared query library under `services/race/queries.py` (which already exists) could consolidate this.

3. **`race_competitors.py` router not catalogued**: The plan mentions it but it is a separate service (retroactive link/unlink of `RaceCompetitor → Athlete`). It is not part of the import or CRUD path for `RaceEvent` and has no overlap. No action needed.

4. **FR-026 calendar sync does not propagate `status` changes from `PATCH /conditions`**: `update_race_event_conditions` (`race_events.py:709`) calls `setattr(event, campo, valor)` but never calls `propagate_to_calendar`. Race conditions (climate, temperature, etc.) are not synced to the calendar, which is correct — but `status` is also not propagated if only conditions are updated in the same call. This is not a real bug (conditions patch is explicitly separate from the metadata patch), but a future admin could be confused.

5. **`is_championship` computed from `valida_num == 99` in the ingestor** (`ingestor.py:539`): This means `POST /race-events/` lets the coach set `is_championship=True` for any `sequence_number`, but the ingestor will overwrite it to `False` for any `valida_num != 99` on first import. Covered by Gap 1 above, but worth calling out separately as a footgun for the Copa Valle use case.
