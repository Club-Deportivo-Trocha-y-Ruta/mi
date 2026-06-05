# Workflow — Training Sessions Module Implementation

**Date:** 2026-05-06
**Base design:** [`design.md`](./design.md)
**Status:** Pending kickoff

---

## Quick map

```
STEP 1   Data model + Alembic migration
STEP 2   Pydantic schemas + permissions
STEP 3   Service layer (TrainingSessionService, AttendanceService)
STEP 4   Routers + session CRUD endpoints
STEP 5   Attendance routers + .gpx upload endpoint
STEP 6   Backend tests (unit + integration)
STEP 7   Parent notification when planning (template + flow)
STEP 8   AI monthly report use case
STEP 9   Monthly report endpoint + email send
STEP 10  Coach frontend: session list + form
STEP 11  Coach frontend: detail + attendance + rubric
STEP 12  Coach frontend: monthly report UI
STEP 13  Parent frontend: session reading + report
STEP 14  Frontend tests (vitest + RTL)
STEP 15  E2E + deploy + docs
```

---

## Cross-cutting principles (DO NOT violate)

Taken from `CLAUDE.md` and theoretical framework:

1. API response language → error messages in Spanish.
2. Minors privacy: NEVER expose individual feedback in club aggregated report.
3. Reuse `services/notification/` and `services/ai/` (do not duplicate plumbing).
4. RBAC with exhaustive tests per endpoint.
5. Git convention: Conventional Commits (`feat(training):`, `fix(training):`, etc).
6. Do not introduce unnecessary abstractions. Three similar lines > premature abstraction.
7. Backend design before frontend. One layer at a time.

---

## STEP 1 — Data model + migration

**Goal:** Create tables `training_sessions`, `session_attendance`, `monthly_reports` with enums.

### Tasks

1.1. Create `backend/app/models/training_session.py`:
- `class AgeGroup(str, Enum)`: `U12`, `U15`
- `class SessionStatus(str, Enum)`: `PLANNED`, `EXECUTED`, `CANCELLED`
- `class AttendanceStatus(str, Enum)`: `PRESENTE`, `AUSENTE`, `JUSTIFICADO`, `TARDE`, `LESIONADO`
- `class TrainingSession(Base)` — fields per `design.md §3.1`
- `class SessionAttendance(Base)` — N:N relationship with metadata
- `class MonthlyReport(Base)` — club/month aggregate
- Use `values_callable` for enums (consistent with `MaturationStatus`).
- SQLAlchemy relationships with `back_populates` (not `backref`).

1.2. Register models in `backend/app/models/__init__.py`.

1.3. Generate migration:
```bash
cd backend && alembic revision --autogenerate -m "agrega tablas training_session, session_attendance, monthly_report"
```

1.4. Review migration manually:
- Indexes: `idx_training_session_club_date`, `idx_training_session_club_age_date`, `uq_session_attendance_session_athlete`, `uq_monthly_report_club_year_month`
- Check constraints for `rpe_omni 0-10`, `rubric_* 1-5`, `duration_min 15-240`.

1.5. Apply locally:
```bash
alembic upgrade head
```

### Acceptance criteria
- [ ] Three tables created with correct FKs.
- [ ] Indexes and unique constraints present.
- [ ] Model CRUD tests pass (STEP 6 covers them).

---

## STEP 2 — Pydantic schemas + permissions

**Goal:** API contract layer + RBAC extension.

### Tasks

2.1. Create `backend/app/schemas/training_session.py`:
- `TrainingSessionCreate`, `TrainingSessionUpdate`, `TrainingSessionRead`
- `AttendanceCreate` (bulk call-up), `AttendanceUpdate`, `AttendanceRead`
- `MonthlyReportCreate`, `MonthlyReportRead`
- Validators: `_validate_consistency` in `AttendanceUpdate` (rubric only if present/late, reason if absent).
- `route_file_path` read-only — upload via dedicated endpoint.

2.2. Extend `backend/app/services/permissions.py`:
- `can_view_session(user, session) -> bool`
- `can_edit_session(user, session) -> bool`
- `can_view_athlete_feedback(user, athlete) -> bool`
- `can_view_monthly_report(user, club, individual: bool) -> bool`
- Helper `parent_athlete_ids(user) -> list[int]` (cached).

### Acceptance criteria
- [ ] Schemas serialize/deserialize correctly.
- [ ] Validators reject invalid combinations.
- [ ] Tests `test_permissions_training.py` cover the matrix in design §6.

---

## STEP 3 — Service layer

**Goal:** Business logic outside of routers (same pattern as `services/phv.py`).

### Tasks

3.1. `backend/app/services/training/__init__.py` (new package).

3.2. `backend/app/services/training/sessions.py`:
- `create_session(db, payload, coach_id) -> TrainingSession` — creates session + attendance rows for called-up athletes.
- `update_session(...)`
- `execute_session(db, session_id)` — set `status=executed`, `executed_at=now`.
- `cancel_session(...)` — soft delete.
- `list_sessions(db, filters: SessionFilters)` — query with efficient joins.

3.3. `backend/app/services/training/attendance.py`:
- `bulk_upsert_convocatoria(db, session_id, athlete_ids)`
- `update_attendance(db, session_id, athlete_id, payload)` — validates coach same club.
- `athlete_attendance_history(db, athlete_id, from_, to_)`.

3.4. `backend/app/services/training/metrics.py`:
- `compute_monthly_metrics(db, club_id, year, month) -> MonthlyMetrics` (dataclass):
  - Total planned / executed / cancelled sessions
  - Per athlete: % attendance, # sessions present
  - Technical focuses covered (unique list)
  - Average RPE / rubric (aggregated, no individuals)
  - Sessions by age group

3.5. `backend/app/services/training/route_files.py`:
- `save_route_file(file: UploadFile, session_id) -> str` — validates extension, size, parses with `gpxpy`+`defusedxml` to detect XXE, returns relative path.
- Storage at `static/uploads/routes/{session_id}/{uuid}.gpx`.

### Acceptance criteria
- [ ] Services do not touch FastAPI directly (testable without TestClient).
- [ ] DB injection via parameter, not global.

---

## STEP 4 — Session CRUD routers

**Goal:** REST endpoints `/training-sessions/*`.

### Tasks

4.1. Create `backend/app/routers/training_sessions.py` with the endpoints from design §4.1.

4.2. Register router in `backend/app/main.py`.

4.3. Each endpoint:
- Depends on `get_db`, `get_current_user`.
- Applies corresponding permission (STEP 2).
- Error messages in Spanish.
- Responses use `*Read` schemas.

4.4. Error handling:
- 403 if no permissions.
- 404 if not found.
- 409 if conflict (e.g. execute already executed).
- 422 if Pydantic validation.

### Acceptance criteria
- [ ] Swagger `/docs` shows endpoints with schemas.
- [ ] Manual smoke test with `Admin2026!` token.

---

## STEP 5 — Attendance routers + `.gpx` upload

**Goal:** Endpoints from design §4.2 + multipart upload.

### Tasks

5.1. In `backend/app/routers/training_sessions.py` add:
- `PUT /training-sessions/{id}/attendance` (bulk)
- `PATCH /training-sessions/{id}/attendance/{athlete_id}`
- `POST /training-sessions/{id}/route-file` (multipart)

5.2. In `backend/app/routers/athletes.py` add:
- `GET /athletes/{id}/attendance` (delegated to service).

5.3. File validation:
- `Content-Type` ∈ `application/gpx+xml`, `application/octet-stream`, `application/vnd.garmin.fit`.
- Extension `.gpx`, `.fit`.
- Max size 5 MB (use `Settings.MAX_UPLOAD_SIZE_BYTES`).
- If `.fit` in MVP: save as-is, **do not parse** (parser phase 2).

### Acceptance criteria
- [ ] Correct upload saves file and updates `route_file_path`.
- [ ] Malicious file upload (`<!DOCTYPE [...XXE...]>`) rejected.
- [ ] Permissions validated (parent CANNOT upload).

---

## STEP 6 — Backend tests

**Goal:** Coverage ≥80% on services + routers.

### Tasks

6.1. `backend/tests/test_training_session_models.py`:
- Basic CRUD, FK, check constraints.
- Soft delete cascade behavior.

6.2. `backend/tests/test_training_session_service.py`:
- `create_session` creates attendance rows.
- `execute_session` rejects if already executed.
- `compute_monthly_metrics` with fixture dataset.

6.3. `backend/tests/test_training_session_router.py`:
- Each endpoint × each role (admin, coach same club, coach other club, parent, anonymous).
- Expected 200 / 403 / 404.

6.4. `backend/tests/test_training_session_privacy.py`:
- **Critical:** parent A does NOT see sessions for athlete B (another parent).
- Parent does NOT see individual feedback from athletes that are not theirs.
- Aggregated monthly report does NOT include names or individual feedback.

6.5. `backend/tests/test_attendance_validation.py`:
- Rubric + status=ausente → 422.
- Rubric + status=presente without reason → 200.
- Status=justificado without reason → 422.

### Acceptance criteria
- [ ] `pytest backend/tests -k training` all green.
- [ ] Coverage `services/training/` ≥80%.

---

## STEP 7 — Parent notification when planning (Q7)

**Goal:** When coach creates a `planned` session, parents of called-up athletes receive an email.

### Tasks

7.1. New template:
- `backend/app/templates/notifications/training_session_invite.html` (HTML)
- `backend/app/templates/notifications/training_session_invite.txt` (fallback)
- Variables: `parent_name`, `athlete_name`, `session_date`, `session_time`, `location`, `technical_focus`, `duration_min`, `coach_name`.

7.2. Register in `template_registry.py` with kind `training_session_invite`.

7.3. In `services/training/sessions.py::create_session` after commit:
- For each called-up athlete → find parents (`parent_athlete`).
- For each parent → `notification_service.send(NotificationRequest(...))` async via dispatcher.
- Structured log, NO PII in logs (CLAUDE.md `NOTIFICATION_LOG_BODIES=false`).

7.4. Throttle:
- Helper `should_throttle(parent_id, athlete_id, kind)` querying `notification_log` (if it exists). Skip if same email sent <60min ago.

7.5. Tests:
- Mock `NotificationService` and verify calls.
- Verify that coach planning a cancelled session → NO email.
- Verify that parent with `notification_opt_out=true` does NOT receive.

### Acceptance criteria
- [ ] Email arrives with correct rendering in a real client (manual test with padre@trochyruta.com locally).
- [ ] Does not send if `APP_ENV=production` and `NOTIFICATION_SEND_EMAILS=false`.

---

## STEP 8 — AI monthly report use case

**Goal:** `monthly_report` use case following the `phv_explainer.py` pattern.

### Tasks

8.1. `backend/app/services/ai/use_cases/monthly_report.py`:
- `class MonthlyReportContext(BaseModel)` — `MonthlyMetrics` aggregates + meta (club_name, period, coach_name).
- `class MonthlyReportUseCase(BaseUseCase)`:
  - `build_context(...)` (privacy-safe: no athlete names, only initials or ID).
  - `render_prompt(context)` with `monthly_report.j2`.
  - `parse_output(raw)` validates structure.
  - Inherits guardrails from `BaseUseCase`.

8.2. `backend/app/services/ai/prompts/monthly_report.j2`:
- Prologue with `system_principles.md`.
- Explicit instructions:
  - "Generate aggregated summary, no individual judgments."
  - "Maximum 500 words, 3 paragraphs."
  - "No medical or nutritional recommendations."
  - "Do not mention specific names."
- Structured input data.

8.3. Extend `services/ai/guardrails.py`:
- Validate output without names ∈ called-up list (regex protection).
- Validate length and sections.

8.4. Tests:
- `backend/tests/test_ai_monthly_report.py`:
  - Prompt snapshot with example data.
  - Mock provider with dummy response.
  - Guardrails reject output with a name.

### Acceptance criteria
- [ ] Use case integrated in `factory.py`.
- [ ] Prompt does not contain PII.

---

## STEP 9 — Monthly report endpoint + email send

**Goal:** Endpoints from design §4.3 + send to club admin.

### Tasks

9.1. `backend/app/routers/monthly_reports.py`:
- `POST /clubs/{id}/monthly-reports` — body `{year, month}`.
  - Validates year/month not in future and month already closed.
  - 409 if already exists (optional reuse via `force_regenerate=true`).
  - Service: `compute_monthly_metrics` → `MonthlyReportUseCase.run` → persist.
- `GET /clubs/{id}/monthly-reports` — list.
- `GET /clubs/{id}/monthly-reports/{year}/{month}` — detail.
- `POST /clubs/{id}/monthly-reports/{report_id}/send` — re-send email.

9.2. Email + PDF template:
- `backend/app/templates/notifications/monthly_report.html`.
- Reuse `DocumentGenerator` (already generates PDF) for attachment.
- Email includes: AI narrative + metrics table (from `metrics_snapshot`).

9.3. Parent variant:
- `GET /parents/training/monthly-summary/{year}/{month}` — returns only THEIR athletes' sessions (not the club aggregate).

9.4. Tests:
- `test_monthly_report_router.py` — happy path + errors.
- `test_monthly_report_privacy.py` — parent does NOT see club aggregate, does see own athlete summary.

### Acceptance criteria
- [ ] Report generated for a past month with seed data visible in Swagger `/docs`.
- [ ] Email + PDF arrive at the club's admin@.

---

## STEP 10 — Coach frontend: session list + form

**Goal:** Coach UI for session CRUD (routes `/training/sessions`, `/new`, `/:id/edit`).

### Tasks

10.1. API client:
- `frontend/src/api/trainingSessions.ts` — typed functions + TanStack Query hooks (`useSessions`, `useCreateSession`, etc).

10.2. Types:
- `frontend/src/types/trainingSession.types.ts` — mirror of Pydantic schemas.

10.3. Zod schemas:
- `frontend/src/schemas/trainingSession.schema.ts` — for RHF.

10.4. Pages:
- `frontend/src/routes/training/SessionsListPage.tsx` — table with filters (month, age_group, status).
- `frontend/src/routes/training/SessionFormPage.tsx` — RHF + Zod + multi-athlete call-up selector (filtered by club age_group).

10.5. Components:
- `components/training/SessionsTable.tsx`
- `components/training/AthletesMultiSelect.tsx` (filtered by age_group)
- `components/training/SessionStatusBadge.tsx`

10.6. State:
- TanStack Query cache invalidate on mutations.
- Zustand for UI filters persisted in browser session.

### Acceptance criteria
- [ ] Coach creates planned session in <30s.
- [ ] List loads <500ms with 100 sessions.
- [ ] Athletes correctly filtered by age_group.

---

## STEP 11 — Coach frontend: detail + attendance + rubric

**Goal:** Session execution UI (route `/training/sessions/:id`).

### Tasks

11.1. `routes/training/SessionDetailPage.tsx`:
- Header: date, location, technical focus, duration, status, "Mark as executed" button.
- Route section: render `route_text`, Strava link, `.gpx` viewer (leaflet).
- Editable attendance table (one row per called-up athlete).

11.2. `components/training/AttendanceTable.tsx`:
- Columns: athlete | status select | reason (if not present) | RPE 0-10 | effort/attitude/technique rubric | comment.
- Inline editing, debounced autosave 500ms.
- Keyboard shortcuts: `P/A/J/T/L` for quick status.

11.3. `components/training/RubricSliders.tsx`:
- 3 sliders 1-5 with labels (1=Very low, 5=Excellent).
- OMNI RPE 0-10 with visual emoji or faces.
- 500-char textarea with counter.

11.4. `components/training/RouteViewer.tsx`:
- Loads `.gpx` with `leaflet-gpx`. Fallback "not available" if only `.fit`.

11.5. Vitest + RTL tests:
- `AttendanceTable` allows editing and autosave calls API.
- `RubricSliders` rejects out-of-range values.
- `SessionDetailPage` shows "Mark as executed" only if planned.

### Acceptance criteria
- [ ] Coach completes attendance for 10 athletes in <2 min.
- [ ] No data loss when changing rows (autosave).

---

## STEP 12 — Coach frontend: monthly report UI

**Goal:** Generate and view monthly report (route `/training/reports`).

### Tasks

12.1. `routes/training/ReportsListPage.tsx`:
- List existing reports by month.
- "Generate report" button with month/year selector.

12.2. `routes/training/ReportDetailPage.tsx`:
- "AI Summary" section (narrative).
- Metrics table: # sessions, % attendance per athlete, focuses covered.
- "Re-send to club" button.
- Warning banner: "Summary generated by AI — review before sending."

12.3. Reusable `MonthlyMetricsTable.tsx` component.

### Acceptance criteria
- [ ] Coach generates monthly report in <10s (mock LLM).
- [ ] Narrative editing NOT allowed (read-only from AI, coach override via additional comment in phase 2).

---

## STEP 13 — Parent frontend: reading

**Goal:** Parents view their athlete's sessions.

### Tasks

13.1. `routes/parents/training/SessionsPage.tsx`:
- List sessions where their athlete was called up.
- No editing buttons.

13.2. `routes/parents/training/SessionDetailPage.tsx`:
- General description visible.
- Attendance: only THEIR athlete's row (status, rubric, feedback).
- Does NOT see other athletes.

13.3. `routes/parents/training/MonthlyOverviewPage.tsx`:
- Personalized monthly summary: % athlete attendance, # sessions, focuses covered.
- Does NOT see club aggregated narrative.

13.4. Reusable component `ParentSessionCard.tsx`.

### Acceptance criteria
- [ ] Parent A never sees athlete B's data in the network tab.
- [ ] RTL tests verify correct filtered rendering.

---

## STEP 14 — Frontend tests

**Goal:** vitest coverage ≥75% on new components and routes.

### Tasks

14.1. Component tests for each new component (`*.test.tsx`).

14.2. Hook tests for TanStack queries (`useSessions`, `useAttendance`, `useMonthlyReport`).

14.3. Route integration tests with MSW mocks.

14.4. Accessibility tests:
- `AttendanceTable` accessible via keyboard (axe-core).
- Correct labels and aria attributes.

### Acceptance criteria
- [ ] `pnpm test` green.
- [ ] Coverage report exceeds 75%.

---

## STEP 15 — E2E + deploy + docs

**Goal:** Verify complete flow and production deployment.

### Tasks

15.1. E2E manual checklist (`docs/09-training-planning/qa.md`):
- Coach creates session → parent receives email → parent opens portal → views detail → coach executes → coach adds rubric → parent views their athlete's rubric → coach generates monthly report → admin receives PDF → parent views own monthly summary.

15.2. Deployment:
- PR with all changes → review → merge to `main`.
- Render auto-deploy.
- Verify `alembic upgrade head` runs OK on startup.
- Production smoke test `https://mi-2yzi.onrender.com/docs`.

15.3. Update docs:
- `docs/README.md` add entry `09 — training-planning`.
- `CLAUDE.md` update "Phase 1 implementation status" table with training module.
- Project memory: `~/.claude/projects/.../memory/training_module_done.md` with summary of decisions.

### Acceptance criteria
- [ ] Production functional with seed coach + athlete + dummy parent.
- [ ] Docs table updated.
- [ ] Project memory saved.

---

## Useful commands during development

```bash
# Backend
source backend/.venv/bin/activate
cd backend && uvicorn app.main:app --reload
cd backend && pytest -k training -v
cd backend && alembic revision --autogenerate -m "agrega <X>"
cd backend && alembic upgrade head

# Frontend
cd frontend && pnpm dev
cd frontend && pnpm test
cd frontend && pnpm test --coverage

# Full stack
docker compose up

# Pre-commit lint
cd backend && ruff check . && black --check .
cd frontend && pnpm lint
```

---

## Module success metrics

At the close of STEP 15, we should see:

- **Coach adoption:** ≥1 session registered per week from the real coach.
- **Parent attendance:** ≥40% of parents open at least one invitation email.
- **Privacy:** 0 cross-athlete data leak incidents (verifiable with logs).
- **Performance:** Monthly listing <300ms, AI report generation <15s.
- **Testing:** Backend ≥80% coverage on services, frontend ≥75% on routes.

---

## Deferred decisions (module sprint 2)

Note for later:
- `.fit` → `.gpx` server-side conversion.
- Recurring sessions (coach cron: "every Tuesday 5pm").
- Reusable templates ("Short interval technique session").
- Mobile push notifications (PWA notification).
- Intervals.icu integration for GPS data from athletes with their own device.
- Session photo/video upload.
- Calendar view (month/week) agenda-style.
- Parent can confirm advance attendance ("my child will NOT be able to go on Tuesday").
- Comparative statistics (athlete vs club average, aggregated, anonymized).

---

## References

- Design: [`design.md`](./design.md)
- Theoretical framework: [`../01-marco-teorico.md`](../01-marco-teorico.md) §2, §5, §6
- AI use case pattern: `backend/app/services/ai/use_cases/phv_explainer.py`
- Notification pattern: `backend/app/services/notification/service.py`
- RBAC: `backend/app/services/permissions.py`
- Strava research: see prior brainstorm (Nov 2024 ToS blocking coach reading athletes).
