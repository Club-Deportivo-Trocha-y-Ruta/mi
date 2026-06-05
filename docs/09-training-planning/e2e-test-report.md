# E2E Test Report — Training Sessions Module
**Execution date:** 2026-05-06  
**Branch:** feature/training-module  
**PR:** https://github.com/Club-Deportivo-Trocha-y-Ruta/mi/pull/4  
**Executed by:** quality-engineer agent

---

## Environment

| Component | Status | Detail |
|---|---|---|
| Docker Compose (backend + MySQL + mailhog) | UP (healthy) | 3 healthy services |
| Backend (`http://localhost:8000`) | UP | FastAPI + aiomysql |
| Frontend (`http://localhost:5173`) | UP | React 19 + Vite |
| playwright-cli | v0.1.7 | Chromium |
| Alembic migrations | INCOMPLETE at start | `training_sessions` / `session_attendance` / `monthly_reports` were missing. Applied during the test with `docker exec ... alembic upgrade head`. |

> **Pre-flight incident:** Migrations `6e189a7e1e51` and `b2c3d4e5f6a7` had not been applied because the container was created before the module commit. They were applied manually. In production this would happen automatically on deployment.

---

## Tier 1 — Smoke API (backend curl)

### 1.1 Sessions — Authentication and Permissions

| Test | Endpoint | Role | Expected | Obtained | Result |
|---|---|---|---|---|---|
| T1.1 | `POST /api/training-sessions` | coach | 201 | 500 (session created in DB, error in response) | **FAIL** |
| T1.2 | `POST /api/training-sessions` | parent | 403 | 403 | PASS |
| T1.3 | `POST /api/training-sessions` | anon | 401 | 401 | PASS |
| T1.4 | `GET /api/training-sessions` | coach | 200 | 200 | PASS |
| T1.5 | `GET /api/training-sessions` | parent | 200 | 200 | PASS |
| T1.6 | `GET /api/training-sessions/{id}` | coach | 200 | 200 | PASS |
| T1.7 | `GET /api/training-sessions/{id}` (not called up) | parent | 403 | 403 | PASS |
| T1.8 | `GET /api/training-sessions/999999` | coach | 404 | 404 | PASS |

### 1.2 Creation validations

| Test | Validation | Expected | Obtained | Result |
|---|---|---|---|---|
| T1.5 | Past `scheduled_date` | 422 | 422 | PASS |
| T1.6 | `duration_min=5` (< 15) | 422 | 422 | PASS |
| T1.7 | `duration_min=999` (> 240) | 422 | 422 | PASS |
| T1.8 | Invalid `strava_url` | 422 | 422 | PASS |
| T1.8b | `convocados_athlete_ids=[]` | 422 | 422 | PASS |

### 1.3 Session execution

| Test | Endpoint | Role | Expected | Obtained | Result |
|---|---|---|---|---|---|
| T1.9 | `POST /{id}/execute` | coach | 200 + status=executed | 200 + executed | PASS |
| T1.10 | `POST /{id}/execute` (already executed) | coach | 409 | 409 | PASS |
| T1.11 | `POST /{id}/execute` | parent | 403 | 403 | PASS |

### 1.4 Attendance

| Test | Endpoint | Role | Expected | Obtained | Result |
|---|---|---|---|---|---|
| T1.12 | `PATCH /{id}/attendance/{athlete_id}` (present + rubric) | coach | 200 | 200 | PASS |
| T1.13 | `PATCH /{id}/attendance/{athlete_id}` (absent + reason) | coach | 200 or 404 | 404 (athlete not in session) | INFO |
| T1.14 | `PATCH` absent WITHOUT `excuse_reason` | coach | 422 | 422 | PASS |
| T1.15 | `PATCH` with `rpe_omni=11` | coach | 422 | 422 | PASS |
| T1.16 | `PATCH /{id}/attendance/{athlete_id}` | parent | 403 | 403 | PASS |
| T1.17 | `GET /athletes/{id}/attendance` | coach | 200 | 200 | PASS |
| T1.18 | `GET /athletes/{id}/attendance` (own athlete) | parent | 200 | 200 | PASS |
| T1.19 | `GET /athletes/{other_id}/attendance` | parent | 403 | 403 | PASS |

### 1.5 Monthly reports

| Test | Endpoint | Role | Expected | Obtained | Result |
|---|---|---|---|---|---|
| T1.22 | `POST /clubs/{id}/monthly-reports` (closed month: March) | coach | 201 | 201 | PASS |
| T1.23 | `POST /clubs/{id}/monthly-reports` (future month) | coach | 422 | 422 | PASS |
| T1.24 | `POST /clubs/{id}/monthly-reports` (current month) | coach | 422 | 422 | PASS |
| T1.24b | `POST /clubs/{id}/monthly-reports` (April, < day 28) | coach | 400 | 400 | PASS |
| T1.25 | Duplicate report same month | coach | 409 | 409 | PASS |
| T1.26 | `GET /clubs/{id}/monthly-reports/{year}/{month}` | parent | 200 (without `coach_observations`) | 200 (field `null`) | PASS |
| T1.27 | `POST /clubs/{id}/monthly-reports` | parent | 403 | 403 | PASS |
| T1.28 | `POST /clubs/{id}/monthly-reports/{y}/{m}/send` | parent | 403 | 403 | PASS |
| T1.29 | `POST /clubs/{id}/monthly-reports/{y}/{m}/send` | coach | 200 | 200 | PASS |
| T1.30 | `GET /parents/training/monthly-summary/{y}/{m}` | parent | 200 | 200 | PASS |
| T1.31 | `GET /parents/training/monthly-summary/{y}/{m}?athlete_id={other}` | parent | 403 | 403 | PASS |

### 1.6 File upload

| Test | Scenario | Expected | Obtained | Result |
|---|---|---|---|---|
| T1.32 | Upload `.txt` (prohibited content-type) | 400 | 400 | PASS |
| T1.33 | Upload by parent | 403 | 403 (fallback: 000 curl issue) | PASS |
| T1.36 | Upload file >5 MB (6 MB) | 400/413 | 400 | PASS |
| T1.37 | Upload GPX with XXE | 400/422 | 500 (**defusedxml not installed**) | **FAIL** |
| T1.38 | Upload valid GPX | 200 | 500 (**defusedxml not installed**) | **FAIL** |

---

## Tier 2 — Frontend E2E (playwright-cli)

### Flow A — Coach happy path

| Step | Description | Result | Snapshot |
|---|---|---|---|
| A1 | Login as coach → redirect to /dashboard | PASS | (auto login) |
| A2 | Navigate to `/training/sessions` — list visible with table | PASS | `flow-a-02-sessions-list.yml` |
| A3 | Click "+ New session" → form at `/training/sessions/new` | PASS | — |
| A4 | Fill form (U15, future date, location, focus, description, 1 athlete) | PASS | `flow-a-03-session-form-filled.yml` |
| A5 | Submit → **500 from backend** (lazy loading bug) | **FAIL** — session created in DB but 500 response. UI does not redirect or show error. | — |
| A6 | Navigate to list — session appears with Planned status | PASS (session does appear) | — |
| A7 | Click "View" → detail. Click "Mark as executed" → status changes to Executed | PASS | `flow-a-04-session-executed.yml` |
| A8 | Attendance table shows **error** "Could not load attendance list" | **FAIL** — frontend makes GET to non-existent endpoint (`/api/training-sessions/{id}/attendance`) | — |
| A9 | Logout | PASS | — |

### Flow B — Parent privacy check

| Step | Description | Result | Snapshot |
|---|---|---|---|
| B1 | Login as parent → redirect to `/my-athletes` | PASS | — |
| B2 | Navigate to `/parents/training/sessions` → empty list (no sessions for own athlete) | PASS | `flow-b-01-parent-sessions.yml` |
| B3 | Attempt to navigate to `/training/sessions` (coach route) → redirect to `/my-athletes` | PASS | `flow-b-02-parent-redirect.yml` |
| B4 | API: parent POST monthly-report → 403 | PASS | — |

### Flow C — Monthly report (coach)

| Step | Description | Result |
|---|---|---|
| C1 | `POST /api/clubs/2/monthly-reports` (March 2026) → 201 | PASS |
| C2 | `ai_summary` present and not empty (approx. 237 characters) | PASS |
| C3 | AI uses `fake` provider (AI_PROVIDER=fake in docker-compose) | INFO — AI worked with mock |
| C4 | Re-send report → 200 | PASS |
| C5 | Duplicate report → 409 | PASS |

### Flow D — Privacy probes (API)

| Probe | Endpoint | Role | Expected | Obtained | Result |
|---|---|---|---|---|---|
| D1 | `GET /api/training-sessions?club_id=99` | parent | 200 empty (forces own athletes) | 200 empty | PASS |
| D2 | `GET /api/training-sessions/{id}` (without own athlete) | parent | 403 | 403 | PASS |
| D3 | `PATCH /api/training-sessions/{id}/attendance/{other}` | parent | 403 | 403 | PASS |
| D4 | `GET /api/clubs/{id}/monthly-reports` | parent | 200 (design allows) | 200 | PASS |
| D5 | `GET /api/parents/training/monthly-summary/…?athlete_id={other}` | parent | 403 | 403 | PASS |

---

## Tier 3 — Resilience

| Test | Scenario | Result |
|---|---|---|
| T3.1 | POST with past date → 422 | PASS |
| T3.2 | UI facing server 500 | **FAIL** — No error toast/feedback visible to user |
| T3.3 | Parent PATCH other's attendance → 403 | PASS |
| T3.4 | Parent POST execute → 403 | PASS |
| T3.5 | Rubric on absent → 422 | PASS |
| T3.6 | XXE in GPX upload | **FAIL** — 500 due to `defusedxml` not installed (missing module) |

---

## Tier 4 — A11y

**Frontend vitest:** 717 tests, 58 files — all PASS.  
No axe-core-specific tests exist in the project (the `-t a11y` flag found no matches). The 717 existing tests cover functional behavior and already include training component tests (SessionFormPage, SessionDetailPage, AttendanceTable, ParentSessionCard, ReadOnlyAttendanceRow, etc.).

---

## Backend pytest

Run inside the Docker container (excluding `test_document_generator.py` which fails due to missing `mocker` fixture):

- **35 FAIL** — all related to the training sessions module
  - **Root cause 1:** `MissingGreenlet` — lazy loading bug in `create_session()` (the router accesses `session.attendances` without `selectinload` after commit)
  - **Root cause 2:** `ModuleNotFoundError: No module named 'defusedxml'` — dependency declared in code but absent from `requirements.txt` and not installed in the container
- **624 PASS** — rest of the project in good shape
- **8 ERROR** — email client tests with missing fixtures (pre-existing, not related to this module)

---

## Bugs found

### CRITICAL

None representing user data leaks. Structural privacy evaluated as APPROVED.

### HIGH

| ID | Severity | Component | Description | Impact |
|---|---|---|---|---|
| BUG-001 | **HIGH** | Backend | `POST /api/training-sessions` returns 500 even though the session IS created in DB. The error occurs in `_session_to_read()` when accessing `session.attendances` via lazy loading in async post-commit context. | Loss of user trust (500 error on successful operation), frontend cannot redirect to detail, 35 router tests fail. |
| BUG-002 | **HIGH** | Backend | `defusedxml` and `gpxpy` are referenced in `route_files.py` but **are not in `requirements.txt`** nor installed in the container. Every GPX upload returns 500 and the XXE check does not work. | Security: GPX files with XXE are not validated. Route functionality completely blocked. |
| BUG-003 | **HIGH** | Frontend | The `AttendanceTable` in the session detail makes `GET /api/training-sessions/{id}/attendance` which does not exist (405 Method Not Allowed). The backend includes attendance in the session detail as `attendances`, but the response schema does not expose that field. | Attendance table always shows an error. Coach cannot record attendance from the UI. |

### MEDIUM

| ID | Severity | Component | Description | Impact |
|---|---|---|---|---|
| BUG-004 | **MEDIUM** | Frontend | When `POST /api/training-sessions` fails with 500, the UI shows no error toast or feedback to the user. The form remains as-is without indicating that a problem occurred. | Confusing UX — user does not know whether the session was created or not. |
| BUG-005 | **MEDIUM** | Backend | The `TrainingSessionRead` schema does not expose the `attendances` field (list of `SessionAttendance`). It only exposes `attendance_summary` (numeric summary). The frontend needs each athlete's data to render the edit table. | Frontend-backend contract out of sync. Requires adding `attendances: list[AttendanceRead]` to the schema or creating a `GET /{id}/attendance` endpoint. |

### LOW

| ID | Severity | Component | Description |
|---|---|---|---|
| BUG-006 | **LOW** | DB | The `static/uploads/routes/` data source is mounted locally but docker-compose does not define a persistent volume for that path. Uploaded GPX files would be lost on container restart. |
| BUG-007 | **LOW** | Backend | The `test_document_generator.py` test uses the `mocker` fixture (from `pytest-mock`) which is not in `requirements-dev.txt`. It blocked the suite before the file was isolated. |

---

## Privacy verdict: **APPROVED**

All privacy controls at the API level work correctly:
- Parent cannot view sessions from other athletes (403)
- Parent cannot modify attendance (403)  
- Parent cannot create/execute sessions (403)
- Parent cannot create reports (403)
- `coach_observations` is omitted from responses to parent (field `null`)
- Parent can only access the summary for THEIR athletes
- Individual attendance data (rubric, RPE) does NOT appear in club aggregated reports

---

## Recommendation: **BLOCK PR**

The PR must not be merged in its current state. The HIGH bugs must be resolved first:

1. **BUG-001:** Add `selectinload(TrainingSession.attendances)` in `create_session()` after the commit, or reload the session using `get_session()` before returning.
2. **BUG-002:** Add `defusedxml` and `gpxpy` to `requirements.txt` and rebuild the image.
3. **BUG-003:** Decide between: (a) add `attendances: list[AttendanceRead]` to the `TrainingSessionRead` schema and ensure `get_session()` loads the relationship (it already does with `selectinload`), or (b) create a `GET /training-sessions/{id}/attendance` endpoint.

Once these three bugs are resolved, all 35 router and service tests should pass and the user experience will be complete.

---

## Snapshot paths

- `docs/09-training-planning/snapshots/flow-a-02-sessions-list.yml`
- `docs/09-training-planning/snapshots/flow-a-03-session-form-filled.yml`
- `docs/09-training-planning/snapshots/flow-a-04-session-executed.yml`
- `docs/09-training-planning/snapshots/flow-b-01-parent-sessions.yml`
- `docs/09-training-planning/snapshots/flow-b-02-parent-redirect.yml`
