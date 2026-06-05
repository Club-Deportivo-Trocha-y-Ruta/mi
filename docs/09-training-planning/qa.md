# QA E2E — Training Sessions Module

**Date:** 2026-05-06
**Module:** Training Sessions (Phase 1.5)
**Target environment:** Local with Docker Compose / Production (https://mi-2yzi.onrender.com)

---

## Prerequisites

- [ ] `docker compose up` executed and stable (all services healthy)
- [ ] Seed data applied (`APP_ENV=development` → `python -m scripts.seed`)
- [ ] Correct `.env` environment variables (EMAIL_PROVIDER, RESEND_API_KEY, etc.)
- [ ] At least one athlete assigned to the club with age in u12 (10-12) or u15 (13-15) range
- [ ] Parent linked to the athlete (`parent_athlete` table) with a valid email
- [ ] Admin account: `admin@trochyruta.com` / `Admin2026!`
- [ ] Coach account: `entrenador@trochyruta.com` / `Coach2026!`
- [ ] Parent account: `padre@trochyruta.com` / `Parent2026!`
- [ ] Endpoint `/api/v1/docs` accessible and showing new tags `training-sessions` and `monthly-reports`

---

## 1. Coach flow — Plan session

### 1.1 Create planned session
- [ ] Login as coach → valid JWT token
- [ ] `POST /api/v1/training-sessions` with future date, age_group=u15, convocados_athlete_ids=[athlete_id]
- [ ] Response 201 with session id and status=planned
- [ ] Verify in DB: row in `training_sessions` with status='planned'
- [ ] Verify in DB: row in `session_attendance` with athlete_id and empty status (called up)

### 1.2 Parent notification
- [ ] In server logs: message "Notification sent to parent X for session Y" (no PII in the log body)
- [ ] If `NOTIFICATION_SEND_EMAILS=true`: email arrived at the parent's inbox with subject containing date and location
- [ ] If `NOTIFICATION_SEND_EMAILS=false`: structured log only (no error)
- [ ] Email contains: date/time, location, technical focus, coach name, no data from other athletes

### 1.3 Creation validations
- [ ] `POST` with past `scheduled_date` → 422 with message in Spanish
- [ ] `POST` without `convocados_athlete_ids` (empty list) → 422
- [ ] `POST` with invalid `strava_url` (not matching regex `strava.com/activities/\d+`) → 422
- [ ] `POST` with `duration_min=5` (< 15) → 422
- [ ] `POST` with `duration_min=300` (> 240) → 422

---

## 2. Coach flow — Execute session and record attendance

### 2.1 Mark session as executed
- [ ] `POST /api/v1/training-sessions/{id}/execute` → 200, status=executed, executed_at populated
- [ ] Attempt to execute an already executed session → 409
- [ ] Attempt to execute a cancelled session → 409

### 2.2 Record attendance with rubric + RPE
- [ ] `PATCH /api/v1/training-sessions/{id}/attendance/{athlete_id}` with status=presente, rpe_omni=7, rubric_effort=4, rubric_attitude=5, rubric_technique=3, individual_feedback="Good work on descents"
- [ ] Response 200, fields persisted correctly
- [ ] Athlete with status=ausente + excuse_reason="Illness" → 200
- [ ] Athlete with status=ausente WITHOUT excuse_reason → 422
- [ ] Athlete with status=presente + rpe_omni out of range (11 or -1) → 422
- [ ] Athlete with status=ausente + rubric_effort → 422 (rubric only if attended)

### 2.3 Upload .gpx file
- [ ] `POST /api/v1/training-sessions/{id}/route-file` with valid .gpx file (multipart) → 200, route_file_path populated
- [ ] Upload with file > 5 MB → 413
- [ ] Upload with `.txt` extension → 422
- [ ] .gpx file with XXE payload (`<!DOCTYPE [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>`) → 422 rejected
- [ ] Parent attempts upload → 403

### 2.4 View attendance history by athlete
- [ ] `GET /api/v1/athletes/{id}/attendance` as coach → 200 with list of records
- [ ] `GET /api/v1/athletes/{id}/attendance` as parent (their athlete) → 200 with filtered list
- [ ] `GET /api/v1/athletes/{other_id}/attendance` as parent (other's athlete) → 403

---

## 3. Coach flow — Generate monthly report with AI

### 3.1 Report generation
- [ ] `POST /api/v1/clubs/{id}/monthly-reports` body `{year: 2026, month: 4}` → 201
- [ ] Response includes `ai_summary` with 2-3 paragraphs (not empty)
- [ ] `ai_summary` does NOT contain full athlete names
- [ ] `metrics_snapshot` contains: total sessions, % attendance per athlete (initials), technical focuses
- [ ] Repeat POST for same month → 409 (unique per club/year/month)
- [ ] POST for future month → 400
- [ ] POST for current month before day 28 → 400 with message "The month has not closed yet"

### 3.2 Report re-send
- [ ] `POST /api/v1/clubs/{id}/monthly-reports/{report_id}/send` → 200
- [ ] Log shows sending to club admin (no PII)
- [ ] Parent attempts this endpoint → 403

### 3.3 List and view reports
- [ ] `GET /api/v1/clubs/{id}/monthly-reports` as coach → list of reports with year/month
- [ ] `GET /api/v1/clubs/{id}/monthly-reports/{year}/{month}` as coach → full detail

---

## 4. Parent flow — Read sessions

### 4.1 View own athlete's sessions
- [ ] Login as parent → valid JWT token
- [ ] `GET /api/v1/training-sessions?athlete_id={own_id}` → 200, only sessions where their athlete was called up
- [ ] `GET /api/v1/training-sessions/{id}` (session with their athlete) → 200 with general session info
- [ ] `GET /api/v1/training-sessions/{id}` (session WITHOUT their athlete) → 403 or 404

### 4.2 View own attendance (their athlete only)
- [ ] Session detail as parent shows ONLY their athlete's attendance row
- [ ] Verify in JSON response: attendance field contains only entries for their athlete
- [ ] Verify in browser Network tab: no data from other athletes appears in any response

### 4.3 View own monthly summary
- [ ] `GET /api/v1/parents/training/monthly-summary/{year}/{month}` → 200 with % attendance for THEIR athlete
- [ ] Response does NOT include aggregated AI narrative from the club
- [ ] Response does NOT include data from other athletes

---

## 5. Privacy tests (parent attempting coach URLs)

### 5.1 Access to other sessions
- [ ] Parent A attempts `GET /api/v1/training-sessions/{id}` of a session where NONE of their athletes was called up → **expected: 403 or 404**
- [ ] Parent A attempts `GET /api/v1/training-sessions` without filter → list must be forced to their athletes only; if not forced, they receive only their own

### 5.2 Modification of other's attendance
- [ ] Parent A attempts `PATCH /api/v1/training-sessions/{id}/attendance/{other_athlete_id}` → **expected: 403**
- [ ] Parent A attempts `POST /api/v1/training-sessions/{id}/execute` → **expected: 403**
- [ ] Parent A attempts `POST /api/v1/training-sessions` → **expected: 403**

### 5.3 Access to aggregated club report
- [ ] Parent A attempts `GET /api/v1/clubs/{id}/monthly-reports` → **expected: 403**
- [ ] Parent A attempts `GET /api/v1/clubs/{id}/monthly-reports/{year}/{month}` → **expected: 403**
- [ ] Parent A attempts `POST /api/v1/clubs/{id}/monthly-reports` → **expected: 403**

### 5.4 Access to other athletes' data
- [ ] Parent A attempts `GET /api/v1/athletes/{other_athlete_id}/attendance` → **expected: 403**
- [ ] Verify that the prompt sent to the AI (in DEBUG-level logs, if enabled) does not contain full names

---

## 6. Edge cases

### 6.1 Session in the past
- [ ] Coach attempts to create session with past `scheduled_date` and `status=planned` → 422
- [ ] Coach can create past session with `status=executed` directly (for retroactive logging) → verify if design allows it; if not, 422

### 6.2 Cancelled session
- [ ] `DELETE /api/v1/training-sessions/{id}` → 200, status=cancelled
- [ ] Attempt to execute cancelled session → 409
- [ ] Attempt to modify attendance on cancelled session → defined behavior (403 or 409)
- [ ] Cancelled session does NOT count in monthly report metrics

### 6.3 Session with no called-up athletes
- [ ] `POST /api/v1/training-sessions/{id}/execute` with no athletes called up → should execute without error (coach forgot to add call-ups; do not block flow)

### 6.4 Monthly report for month with no sessions
- [ ] `POST /api/v1/clubs/{id}/monthly-reports` for a month with no executed sessions → 200 or 204 with empty ai_summary or note "No sessions in the period"

---

## 7. Performance (smoke tests)

- [ ] `GET /api/v1/training-sessions?from=2026-01-01&to=2026-01-31` with 50 sessions in DB → response < 300ms (measure with `time curl`)
- [ ] `POST /api/v1/clubs/{id}/monthly-reports` with mock LLM (APP_ENV=development) → completed < 15s
- [ ] Frontend: `/training/sessions` page loads < 500ms with 100 sessions (Network tab Slow 3G simulated)
- [ ] Frontend: `AttendanceTable` with 20 athletes, 500ms debounce autosave does not cause double submit

---

## 8. Accessibility (smoke tests)

- [ ] Navigate `AttendanceTable` fully with Tab key: all controls reachable
- [ ] Focus ring visible on all interactive elements of `AttendanceTable`
- [ ] Screen reader (VoiceOver/NVDA) correctly announces the status of each attendance row
- [ ] `RubricSliders` have associated labels (not just placeholders)
- [ ] Session form (`SessionFormPage`) with no axe-core errors in console
- [ ] `MonthlyReportView` with AI narrative marked as `aria-live="polite"` if async loading

---

## 9. Final verification in production (post-deployment)

- [ ] `https://mi-2yzi.onrender.com/docs` shows tags `training-sessions` and `monthly-reports`
- [ ] Login with coach seed works (if seed was applied in dev, NOT in production)
- [ ] `GET /api/v1/training-sessions` with valid token returns 200 (empty list is OK)
- [ ] Migrations `6e189a7e1e51` and `b2c3d4e5f6a7` appear in `alembic_version` of the DB
- [ ] Render logs show "Applying migrations..." and "Starting server..." without errors
