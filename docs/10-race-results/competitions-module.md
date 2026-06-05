# Competitions Module — Technical Design

**Project:** Club Deportivo Trocha y Ruta — Youth XCO
**Module:** `routers/race_events.py` + `services/race_events.py` + `frontend/src/routes/competitions/`
**Date:** 2026-05-27
**Audience:** coach (UX), architect/dev (maintenance), QA
**Authoritative prior input:** `docs/10-race-results/upload-design.md` (Phase 1.7 — PDF ingestion) and `docs/10-race-results/upload-design.md §14` (Phase 1.7+ — race conditions).

---

## 0. Executive Summary

The **Competitions** module is the **management** layer for Copa Valle XCO rounds. It allows the coach and administrator to plan rounds before having official PDFs (pre-tapering, call-up, calendar), associate them with calendar events, and trigger the results import workflow.

Until this phase, a round was only created when the official PDF was ingested (`scripts/ingest_race.py` → `RaceIngestor`). The coach could not plan a future round or edit metadata after ingestion. This release opens the full lifecycle of `RaceEvent`: create empty → plan → import PDF → analyze → eventually cancel.

**Architectural bet:** thin HTTP CRUD layer over `RaceEvent`, reusing the existing model and enums. No schema changes in MySQL: the columns and the `RaceEventStatus.CANCELLED` enum already existed from migration `64c263edd07f`.

- **Backend:** 5 new CRUD endpoints + 1 pre-existing conditions endpoint, 1 new service, 5 new schemas, 32 tests, 0 Alembic migration.
- **Frontend:** 4 pages (List/Form/Detail/Import), 5 reusable components (FiltersBar/StatusBadges + 5 URL-driven tabs), relocated import wizard, 69 new vitest tests.
- **Privacy:** `race_events` are federation public metadata; they contain no PII of minors.

**Does not do:** create/edit individual results (`PATCH /race-results/{id}`), manage `race_series` from UI (the coach assumes Copa Valle), type A/B/C periodization rounds in the model (field only in `Plan_Entrenamiento_XCO_Copa_Valle_2026.docx`).

---

## 1. Competitions vs Results — functional separation

| Aspect | **Competitions** (this module) | **Results** (Phase 1.7) |
|---|---|---|
| Dominant verb | Manage | Analyze |
| Sidebar | "Competitions" | "AI Insights" (post-ingest insights) |
| Use cases | Create empty round, edit date/venue, associate with calendar, trigger import wizard, cancel | Position tables, podium gap, athlete evolution, club ranking, projection |
| Primary persistence | `race_events` (metadata) | `race_results`, `riders`, `race_competitors` |
| Endpoints | `/api/race-analysis/race-events/*` (CRUD) | `/api/race-analysis/imports/*` (ingestion) + `/api/race-analysis/athletes/*` (analytics) |
| Creates data | Yes (the container event) | Yes (results + competitors) but conditioned on an existing `race_event` |
| Deletes data | Yes (admin only, if no dependencies) | No — the coach does not delete results; re-ingests the PDF |
| Audience | Coach + admin | Coach + admin (parents see only their own data through newsletters / parent portal) |

**Junction point:** from the competition detail, the coach clicks "Import results" and starts the Phase 1.7 wizard with `race_event_id` pre-loaded. The import attaches `race_results` to the already-created `race_event`, instead of inferring it from the PDF.

---

## 2. Architecture

### 2.1 New components

```
backend/
├── app/
│   ├── routers/race_events.py          # NEW — 5 CRUD endpoints + 1 pre-existing
│   ├── services/race_events.py         # NEW — business logic + guards
│   └── schemas/race_event.py           # NEW — 5 Pydantic v2 schemas
└── tests/routers/test_race_events_crud.py  # NEW — 32 tests

frontend/
├── src/
│   ├── api/raceEvents.ts                       # EXTENDED — get/create/update/delete/list
│   ├── hooks/race/useRaceEvents.ts             # NEW — query keys + cross invalidations
│   ├── routes/competitions/
│   │   ├── CompetitionsListPage.tsx            # NEW
│   │   ├── CompetitionFormPage.tsx             # NEW (create + edit)
│   │   ├── CompetitionDetailPage.tsx           # NEW (header + 5 URL-driven tabs)
│   │   └── CompetitionImportPage.tsx           # NEW (mounts wizard, with/without :id)
│   ├── components/competitions/
│   │   ├── CompetitionFiltersBar.tsx           # NEW
│   │   ├── CompetitionStatusBadges.tsx         # NEW
│   │   ├── tabs/{InfoTab,ResultsTab,           # NEW — 5 extractable tabs
│   │   │       ConditionsTab,AthletesTab,
│   │   │       InsightsTab}.tsx
│   │   └── import/{ImportWizard,RaceUploadZone,DiffTable}.tsx
│   │                                           # MOVED from components/ai/
│   └── test/msw/raceEventsHandlers.ts          # EXTENDED
```

### 2.2 Backend endpoints

All under prefix `/api/race-analysis/race-events/`.

| Method | Route | Purpose | RBAC | Codes |
|---|---|---|---|---|
| `GET` | `/` | Listing with filters `season`, `status`, `is_championship`, `location`. Returns `RaceEventListItem[]` with derived flags `has_results`, `has_calendar_event`, `conditions_completeness`. | coach + admin | 200, 403 |
| `GET` | `/{race_event_id}` | Full detail with `has_calendar_event` flag calculated via EXISTS. | coach + admin | 200, 404, 403 |
| `POST` | `/` | Creates empty event (without results). Validates FK `series_id` (422) and uniqueness `(series_id, sequence_number)` (409). | coach + admin | 201, 404, 409, 422, 403 |
| `PATCH` | `/{race_event_id}` | Partial metadata update (`name`, `event_date`, `location`, `sequence_number`, `status`, `is_championship`). **Does not touch conditions.** | coach + admin | 200, 404, 409, 422, 403 |
| `DELETE` | `/{race_event_id}` | Deletes event without dependencies. Checks `race_results` and `calendar_events` first to return 409 with readable message before MySQL rejects with RESTRICT. | **admin only** | 204, 404, 409, 403 |
| `PATCH` | `/{race_event_id}/conditions` | **Pre-existing (Phase 1.7+)** — updates weather, temperature, surface, altitude, notes. | coach + admin | 200, 404, 422, 403 |

**409 convention on DELETE:** the coach who needs to "hide" a past round uses `PATCH /{id}` with `status=cancelled`, not DELETE. DELETE is for events created by mistake that have no history yet.

### 2.3 Pydantic v2 schemas (`backend/app/schemas/race_event.py`)

| Schema | Use | Notes |
|---|---|---|
| `_ConditionsFields` | Mixin with the 5 conditions fields | Reused by `RaceEventCreate` to allow capturing conditions from the creation form if the coach already knows them. |
| `RaceEventCreate` | Body of `POST /` | `extra="forbid"`, `str_strip_whitespace=True`. Requires `series_id`, `sequence_number` (1-99, 99 = CD by convention), `name`, `event_date`. |
| `RaceEventUpdate` | Body of `PATCH /` | All optional fields; `exclude_unset=True` to distinguish "not sent" from "sent null". |
| `RaceEventRead` | Response of POST/PATCH/GET | Includes `has_calendar_event` calculated in the endpoint (not a column). |
| `RaceEventListItem` | Listing item | Includes `has_results`, `has_calendar_event`, `conditions_completeness: Literal["complete", "partial", "empty"]`. |
| `RaceEventListResponse` | Wrapper of `GET /` | `{items: [...], total: N}` — total = `len(items)` (no pagination: 7 rounds/year × few seasons). |

### 2.4 Service (`backend/app/services/race_events.py`)

| Function | Responsibility | Guards |
|---|---|---|
| `create_race_event` | INSERT with default value `status=SCHEDULED`. | `_check_series_exists` (422) + `_check_sequence_unique` (409). |
| `update_race_event` | Partial UPDATE via `setattr`. | If `sequence_number` changes, re-checks uniqueness excluding its own id. Empty body → no-op (returns current state). |
| `delete_race_event` | DELETE + flush. | Checks `RaceResult.event_id` and `CalendarEvent.race_event_id` with EXISTS before executing. |
| `list_race_events` | SELECT with correlated scalar subqueries for `has_results` and `has_calendar_event`. | `season` filter via JOIN to `race_series.season_year`. `location` with partial `ILIKE`. Order by `event_date ASC`. |
| `_completeness(event)` | Private helper | Counts how many of the 5 `_CONDICIONES_CAMPOS` are not `None`: 0=empty, 5=complete, other=partial. |

---

## 3. Coach workflows

### 3.1 Pre-PDF workflow: planning a future round

1. The coach opens **Sidebar → Competitions**.
2. Clicks **"New competition"** → `CompetitionFormPage` in create mode.
3. Selects `sequence_number` (1-7 or 99 if CD), enters name, date, venue.
4. Altitude auto-fills from `VENUE_ALTITUDES` (`frontend/src/types/raceEvents.types.ts`) — catalog of 7 Copa Valle venues (Sevilla, Ginebra, La Cumbre, Cali, Palmira, Roldanillo, Yumbo).
5. `POST /api/race-analysis/race-events/` with `series_id=1` (Copa Valle hardcoded — see §6 TODOs).
6. Redirect to `CompetitionDetailPage` with `status=SCHEDULED`, no results tabs yet.
7. (Optional) Clicks **"Associate with calendar"** → navigates to `/calendar/events/new?race_event_id={id}` and fills out pre-loaded `CalendarEvent` form.

### 3.2 Post-PDF workflow: importing results

1. From the list, the coach opens the detail of the already-created competition (or creates a new one inline from the wizard if it doesn't exist).
2. Clicks **"Import results"** → `CompetitionImportPage` loads `ImportWizard` with `race_event_id` pre-loaded (without requiring wizard step 2 if metadata is already complete).
3. The wizard follows the Phase 1.7 flow (parse → dry-run → commit), saving PDF in Hostinger SFTP.
4. On commit, cross invalidations (`useRaceEvents` + `useImports`) refresh the detail: **Results**, **Athletes** and **Insights** tabs appear.
5. The coach captures race conditions via the **Conditions** tab (PATCH `/{id}/conditions`).

### 3.3 Cancellation or deletion workflow

| Case | Action | Endpoint |
|---|---|---|
| Round postponed or suspended with history | Coach edits status → `cancelled` | `PATCH /{id}` |
| Round created by error with no results or calendar | Admin deletes | `DELETE /{id}` → 204 |
| Round has ingested results | Deletion blocked | `DELETE /{id}` → 409 |

---

## 4. Frontend — routes and RBAC

| Route | Component | RBAC | Notes |
|---|---|---|---|
| `/competitions` | `CompetitionsListPage` | coach + admin | Dense table on desktop, cards on mobile. Season/status/venue/championship filters. Row kebab: edit, import, associate calendar, delete (admin). |
| `/competitions/new` | `CompetitionFormPage` (create) | coach + admin | RHF + Zod. Auto-altitude. Handles 409 inline. Supports `?returnTo` query. |
| `/competitions/:id` | `CompetitionDetailPage` | coach + admin | Header + 5 URL-driven tabs (`?tab=info|results|conditions|athletes|insights`). Athletes and Insights tabs load lazy. |
| `/competitions/:id/edit` | `CompetitionFormPage` (edit) | coach + admin | Form reuse in edit mode with `useRaceEvent(id)`. |
| `/competitions/import` | `CompetitionImportPage` (without id) | coach + admin | Wizard to create new round from PDF. |
| `/competitions/:id/import` | `CompetitionImportPage` (with id) | coach + admin | Wizard pre-loaded with existing `race_event` metadata. |

**Parent guard:** all 6 paths use `<ProtectedRoute allowedRoles={[UserRole.coach, UserRole.admin]}>` in `frontend/src/App.tsx`. A parent who pastes the URL receives 403.

**Sidebar:** **"Competitions"** item between **Newsletters** and **AI Insights** (`frontend/src/components/layout/*.tsx`).

---

## 5. Reusable tabs — `components/competitions/tabs/`

Extracted from `CompetitionDetailPage` into separate files to facilitate reuse and isolated testing. Each tab receives `raceEventId` and consumes its own TanStack Query hooks.

| Tab | File | Load | Consumes |
|---|---|---|---|
| `InfoTab` | `tabs/InfoTab.tsx` | Immediate | `useRaceEvent(id)` |
| `ResultsTab` | `tabs/ResultsTab.tsx` | Immediate | Embeds `RaceAnalysisPage` filtered by `race_event_id` (mechanical refactor, without touching the logic). |
| `ConditionsTab` | `tabs/ConditionsTab.tsx` | Immediate | `useRaceEventConditions(id)` + `EditConditionsDialog` (side sheet). |
| `AthletesTab` | `tabs/AthletesTab.tsx` | Lazy | `useAthleteRaceAnalysis` filtered by event. |
| `InsightsTab` | `tabs/InsightsTab.tsx` | Lazy | Embeds `ClubInsightsByRacePage` (mechanical refactor). |

**URL-driven selector:** the active tab lives in `?tab=...` (not local state) to allow sharing deep links and respecting the browser's back/forward.

---

## 6. Relevant design decisions

| Decision | Discarded alternative | Reason |
|---|---|---|
| **Pre-create rounds without PDF** (`POST /race-events` accepts empty body of conditions) | Only create via PDF ingestion (Phase 1.7) | The coach needs to plan tapering, call up athletes and associate `calendar_events` weeks before the event. Blocking this until having a PDF breaks the planning flow. |
| **DELETE admin only** | Coach can delete | The coach has `PATCH status=cancelled` to "hide" events; DELETE is definitive and breaks traceability. Concentrating the privilege in admin reduces the blast radius. |
| **No `PATCH /race-results/{id}` individual** | Dedicated endpoint to correct a time or position | PDF re-ingestion is idempotent (`RaceIngestor.ingest_event` uses SHA256 + UNIQUE constraints). Correcting data in the PDF and re-uploading is more auditable than patching individual rows. **Out of scope** documented. |
| **No "A/B/C type" field** in `race_events` | Add `priority` enum column | A/B/C periodization lives in `Plan_Entrenamiento_XCO_Copa_Valle_2026.docx` and depends on the full year calendar. Modeling it here would duplicate the source of truth. Covered in the future with `is_championship: bool` for CD. |
| **ToggleGroup vs select** in filters and form | Classic `<Select>` | Copa Valle venues are 7 fixed + statuses are 4 enums — they fit as ≥48px chips (touch-friendly on mobile, aligned with accessibility). |
| **Auto-altitude from `VENUE_ALTITUDES`** | Request altitude manually | The coach shouldn't have to know 1485 m vs 1024 m. When they choose a venue from the catalog, the form fills altitude; if edited afterwards, the value is respected. |
| **`series_id=1` hardcoded in frontend** | GET `/api/race-analysis/race-series` | No endpoint exposed yet. The club only participates in Copa Valle. Documented as TODO (see §9). |
| **URL-driven tabs** | Local state + non-shareable tabs | Allows deep links (`/competitions/12?tab=results`), respects back/forward, simplifies E2E QA. |
| **Lazy load `AthletesTab` and `InsightsTab`** | Eager load | Both make heavy requests (`race_competitors` + club ranking). Lazy reduces initial detail TTI. |

---

## 7. Cross integrations

### 7.1 Calendar

- **"Associate with calendar"** button in `CompetitionDetailPage` appears only if `has_calendar_event=false`.
- Click → navigates to `/calendar/events/new?race_event_id={id}`.
- `EventFormPage` reads `?race_event_id` and pre-loads the form with `prefillRaceEventId`.
- The backend already supports the FK `calendar_events.race_event_id` (Phase 1.5).
- Cross invalidations in `useRaceEvents.ts`: when creating/editing a `CalendarEvent` that points to a `race_event_id`, also invalidate `raceEvents.detail(id)` to refresh the `has_calendar_event` flag.

### 7.2 Import wizard (CF1 relocation)

- **Before (Phase 1.7):** `frontend/src/components/ai/ImportWizard.tsx` + helpers in `components/ai/`.
- **Now:** `frontend/src/components/competitions/import/{ImportWizard,RaceUploadZone,DiffTable}.tsx`.
- Codemod applied over 4 imports in consumers; tests moved with adjacent `__tests__`.
- The route `/competitions/import` allows creating a new round from the wizard without pre-creating the `race_event` (the commit creates it).
- The route `/competitions/:id/import` mounts the wizard with pre-loaded `race_event_id` and hides step 2 if the event already has complete metadata.

### 7.3 Inline create from the wizard

The internal `EventForm` of the wizard has a **"Create new round"** link that opens `/competitions/new?returnTo=/competitions/import`. On save, it returns to the wizard with `?race_event_id={id}` just created.

---

## 8. Tests

| Layer | Count | Location | Coverage |
|---|---|---|---|
| Backend functional | **32** | `backend/tests/routers/test_race_events_crud.py` | The 5 CRUD endpoints + RBAC matrix (admin/coach/parent) + 404/409/422 cases + DELETE guards. |
| Backend race regression | 802 | `backend/tests/` (complete race module) | 0 regressions after this release (834 total race including the 32 new). |
| Frontend unit + integration | **69** | `frontend/src/{routes,components,hooks,api}/**/__tests__/` | List/Form/Detail/Import pages, FiltersBar, StatusBadges, tabs, TanStack Query hooks with MSW. |
| Frontend a11y axe | **4** | (included in the 69) | `CompetitionsListPage`, `CompetitionFormPage`, `CompetitionDetailPage`, `CompetitionImportPage` — 0 violations. |
| Frontend total post-release | 1682 | `frontend/src/**/__tests__/` | No regressions. |

**Backend fixtures** (`backend/tests/routers/test_race_events_crud.py`): factory of `RaceSeries` + `RaceEvent` with synthetic data (no real athlete names). Uses real `AsyncSession` over in-memory SQLite.

**MSW frontend:** `frontend/src/test/msw/raceEventsHandlers.ts` with handlers for the 5 endpoints + error cases (409 uniqueness, 409 dependencies, 422 invalid sequence).

---

## 9. Known limitations and TODOs

| Topic | Status | Future issue |
|---|---|---|
| `PATCH /api/race-results/{id}` | **Out of scope.** The coach corrects the PDF at source and re-ingests. | If needed for Federation correction, evaluate endpoint with `race_result_revision` audit. |
| `GET /api/race-analysis/race-series` | Not exposed. Frontend hardcodes `series_id=1`. | When another series is incorporated (National Championship, Copa Pacífico), add endpoint and `<Select>` in `CompetitionFormPage`. |
| A/B/C periodization typing | Not modeled. Only `is_championship: bool` for CD. | Evaluate adding `RacePriority` enum if coach needs to filter by type in analytics. |
| List pagination | Not implemented (returns `total = len(items)`). | At scale of 7 rounds × N seasons not necessary; review if it exceeds 100 events. |
| `parse` endpoint receives pre-loaded `race_event_id` | Wizard still fully re-parsed on route `/competitions/:id/import`. | Optimization: skip wizard step 2 if `race_event_id` is present and metadata matches. |
| CX1 audit (privacy review) | In progress at close of this release. | Reflect result in CLAUDE.md and this doc when the final report is ready. |

---

## 10. References

- `backend/app/routers/race_events.py` — implementation of the 5 endpoints.
- `backend/app/services/race_events.py` — business logic + guards.
- `backend/app/schemas/race_event.py` — Pydantic v2 DTOs.
- `backend/tests/routers/test_race_events_crud.py` — 32 functional tests + RBAC.
- `backend/app/models/race_event.py` — pre-existing SQLAlchemy model (Phase 1.7).
- `frontend/src/routes/competitions/` — 4 pages.
- `frontend/src/components/competitions/` — module-specific components.
- `frontend/src/api/raceEvents.ts` — axios wrappers.
- `frontend/src/hooks/race/useRaceEvents.ts` — query keys + invalidations.
- `frontend/src/types/raceEvents.types.ts` — TS types + `VENUE_ALTITUDES`.
- `docs/10-race-results/upload-design.md` — ingestion technical design (Phase 1.7) + conditions extension (§14).
- `docs/10-race-results/runbook-ops.md` — CLI `scripts/ingest_race.py` operation.
