# Quickstart — validating feature 041 (multi-coach governance)

**Feature**: `specs/041-multi-coach-governance/` · **Branch**: `feat/041-multi-coach-governance`

This is the **validation** guide, not an implementation guide. Every schema, RBAC rule, Spanish
string, column and test-file name it refers to is fixed in [`spec.md`](spec.md),
[`data-model.md`](data-model.md) and [`contracts/`](contracts/). Nothing is duplicated here — this
document only says **what to run, in what order, and what proves the story is done**.

Three rules apply while running it:

- **No credentials in the transcript.** Never open, print or paste `.env`, `.env.production` or any
  credential file. Refer to variables by name (`TEST_DATABASE_URL`, `AUDIT_RETENTION_DATABASE_URL`,
  `RACE_AI_BUDGET_USD_30D`), never by value. The purge CLI is itself required never to echo its
  database URL — `contracts/retention-purge.md` §2.2.
- **No minor's data in the transcript.** Scenarios 1, 2 and 4 are written as **counts and
  identifiers**, never as row dumps, for exactly that reason. Do not paste an athlete's name, birth
  date or measurement into a terminal log, a bug report or a commit message.
- **Synthetic identities only.** Coach A = "Ana Coach", coach B = "Beto Coach", "Admin Club", one
  parent, one demo athlete — the fixture identities of `research.md` R-32 and
  `contracts/audit-log-api.md` §7.5. Every fixture and seed account in this feature is a synthetic
  adult.

---

## 1. Prerequisites

### 1.1 Backend

```bash
cd backend && source .venv/bin/activate
```

Invoke pytest as `.venv/bin/python -m pytest` (the `pytest` shim on PATH is broken in this
environment — same note as `specs/040-growth-module-redesign/quickstart.md`).

| Lane | Command | Notes |
|---|---|---|
| default (offline) | `.venv/bin/python -m pytest` | aiosqlite in memory; everything except the rows marked `mysql`. `audit_log` must be created by the subset harnesses too — `contracts/audit-recording.md` §8. |
| `mysql` (opt-in) | `TEST_DATABASE_URL="mysql+aiomysql://<user>:<pass>@127.0.0.1:3306/trocha_ruta_test" .venv/bin/python -m pytest -m mysql` | The database name **must** end in `_test`; the guard is `backend/tests/conftest.py:44-53`. Export the URL from your password manager into the shell, never into a file. |
| migration | `alembic upgrade head` | One revision for the whole feature, `down_revision = 2a8baa967cc6` (`plan.md` → `data-model.md` §6). |

### 1.2 Frontend

```bash
cd frontend && npm ci && npm run typecheck
```

### 1.3 Dev stack (needed for e-mail, PDF and every manual scenario)

`docker compose up` → API on `:8000`, MySQL on `:3306`, **MailHog UI on http://localhost:8025**
(`docker-compose.yml:54-59`). WeasyPrint on macOS needs `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.

### 1.4 Isolated e2e stack

```bash
frontend/scripts/e2e-stack.sh up
cd frontend && npm run test:e2e:isolated        # frontend/package.json:17
```

API `:8001`, MySQL `:3307`, **MailHog `:8026`** (`frontend/scripts/e2e-stack.sh:36-38`,
`docker-compose.e2e.yml:38-40`). It never touches the developer's `me` stack.

> **Blocked today.** The isolated stack cannot boot on a fresh MySQL volume because three
> migrations import deleted `app.data.*` modules (`research.md` R-34, same blocker that deferred
> feature 040's specs). Until that one-task fix lands, every Playwright step below is marked
> **[e2e blocked]** and has a manual fallback. Carry it as a deferred task — Principle II forbids a
> silent skip.

### 1.5 The two-coach seed — how to create the second coach

Pick the path that matches the lane:

**A · Product path (preferred; this *is* scenario 6).** Sign in as admin → **`/admin/usuarios`** →
**"+ Nuevo entrenador"** → nombre, apellido, correo and **club (obligatorio)** → submit. There is no
password field; the account receives the set-password e-mail. Fields, validation order and copy:
`contracts/staff-admin.md` §9 and §11.

**B · API path (fastest when a token is already in hand).**

```bash
ADMIN_TOKEN=$(curl -sS -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' -d '{"email":"admin@trochyruta.com","password":"'"$ADMIN_PASS"'"}' | jq -r .access_token)

curl -sS -X POST http://localhost:8000/api/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"first_name":"Beto","last_name":"Coach","email":"entrenador2@trochyruta.com","role":"coach","club_id":1}'
```

`201` plus one `club_members` row with `role_in_club="coach"`. Omitting `club_id` is a `422`, and
sending `password` is a `422` — `contracts/staff-admin.md` §1.2 rows 4 and 6. Read `$ADMIN_PASS`
from your password manager; never hardcode it in a file that can be committed.

**C · Test lanes.**

- pytest: the shared two-coach fixture module under `backend/tests/fixtures/`, registered as a
  pytest plugin next to the existing one at `backend/tests/conftest.py:15` (`research.md` R-32).
  No test in this feature builds its own users.
- Playwright: a `coach2` identity added to `SeedRole` / `CREDENTIALS` at
  `frontend/e2e/helpers/session.ts:17-23`, plus the matching account in `backend/scripts/seed.py`
  next to the existing coach at `backend/scripts/seed.py:160-177` (`research.md` R-34). The
  credentials live in that helper; they are not restated here.

**Seed sanity check — run this before any scenario.** Sign in as coach B and confirm
`GET /api/athletes`, `GET /api/training-sessions` and `GET /api/calendar/events` return the **same
counts** as coach A. A zero count means the membership was not created and every scenario below will
fail for the wrong reason (US3 AC3 — the "empty app" regression).

---

## 2. Command index

### 2.1 Backend, by user story

| Story | Command |
|---|---|
| Setup / helper | `.venv/bin/python -m pytest tests/services/test_audit_helper.py tests/services/test_compute_changed_fields.py tests/services/test_request_context.py -q` |
| US1 recording | `.venv/bin/python -m pytest tests/test_audit_coverage.py tests/test_audit_actors.py tests/test_audit_privacy.py tests/test_audit_query_count.py -q` |
| US1 read API | `.venv/bin/python -m pytest tests/routers/test_audit_log_api.py -q` |
| US2 archive | `.venv/bin/python -m pytest tests/routers/test_athlete_archive.py tests/test_archived_athlete_absent.py tests/test_parent_archived_only.py tests/test_users_delete_deactivate.py tests/test_archive_scope_gate.py -q` |
| US3 staff | `.venv/bin/python -m pytest tests/test_staff_admin.py tests/test_users.py -q` |
| US4 sessions | `.venv/bin/python -m pytest tests/test_session_coaches.py tests/test_training_session_service.py tests/test_training_session_notifications.py tests/test_attendance_validation.py tests/test_training_session_privacy.py -q` |
| US5 concurrency | `.venv/bin/python -m pytest tests/routers/test_newsletter_concurrency.py tests/routers/test_newsletter_coach_note_author.py tests/test_monthly_report_approval_evidence.py tests/test_cors_etag.py -q` |
| US6 scope / spend | `.venv/bin/python -m pytest tests/routers/test_race_analysis_club_scope.py tests/routers/test_race_imports_club_scope.py tests/services/race/ai/test_spend_by_user.py tests/routers/test_race_analysis.py -q` |
| US7 reporting | `.venv/bin/python -m pytest tests/test_coach_activity.py tests/test_monthly_report_unchanged.py -q` |
| US8 retention | `.venv/bin/python -m pytest tests/test_retention.py tests/test_audit_append_only.py -q` |
| mysql lane | `.venv/bin/python -m pytest -m mysql -q` (adds `tests/test_audit_mysql.py`, the migration/backfill cases of `data-model.md` §6.5, T20–T21 of `contracts/retention-purge.md` §8.3) |
| whole suite | `.venv/bin/python -m pytest -q` · lint: `ruff check` |

### 2.2 Frontend

```bash
npx vitest run src/routes/admin src/components/admin src/schemas/staff.schema.test.ts
npx vitest run src/routes/training/CoachActivityPage.test.tsx src/components/audit src/components/athletes/__tests__/AthleteHistoryPanel.test.tsx
npx vitest run src/routes/training/AthleteNewsletterStudioPage.test.tsx src/routes/training/ReportDetailPage.test.tsx
npx vitest run src/components/training src/routes/athletes/__tests__/AthleteFormPage.archive.test.tsx
npx vitest run src/lib/__tests__/navigation.test.ts src/lib/__tests__/persistAllowList.test.ts
npx vitest run -t "a11y"          # jest-axe: StaffPage, ClubHistoryPage, CoachActivityPage, archive + conflict dialogs
npm run typecheck && npm run build && npm run check:chunks
```

### 2.3 e2e — **[e2e blocked, R-34]**

```bash
npm run test:e2e:isolated -- e2e/staff-admin.spec.ts e2e/athlete-archive.spec.ts \
  e2e/session-co-coaches.spec.ts e2e/newsletter-conflict.spec.ts e2e/coach-activity.spec.ts
```

Owners: `contracts/staff-admin.md` §14.3, `contracts/athlete-archive.md` §12.7,
`contracts/session-coaches.md` §12, `contracts/concurrency-and-approvals.md` §9,
`contracts/coach-activity-report.md` §9.4.

---

## 3. Scenarios

Each scenario states its steps, the expected result and the success criterion it discharges. Run
them in order; scenario 1 leaves the athlete archived and restores it at the end.

### Scenario 1 — Twenty mixed actions, every one attributed (US1 · SC-001, first half)

**Setup**: dev stack up, coach A, coach B and admin signed in (three browsers or three tokens).

Run this script, then open **`/club/historial`** as coach A.

| # | Actor | Action | Expected entry (`entity_type` / `action`) |
|---|---|---|---|
| 1 | Coach A | Create a training session with A **and** B as coaches | `training_session/create` + 2 × `training_session_coach/create`, one `request_id` |
| 2 | Coach B | Edit the session (change the location) | `training_session/update`, `changed_fields` = `["location"]` |
| 3 | Coach B | Cancel it choosing a reason | `training_session/cancel` with `reason_code` |
| 4 | Coach A | Create a calendar event | `calendar_event/create` |
| 5 | Coach B | Cancel that event with a reason | `calendar_event/cancel` |
| 6 | Admin | Permanently delete a second calendar event | `calendar_event/delete` |
| 7 | Coach A | Record attendance + ratings + feedback for one athlete | `session_attendance/create` |
| 8 | Coach B | Edit that same attendance entry | `session_attendance/update` |
| 9 | Coach A | Create an anthropometric record | `anthropometric_record/create` |
| 10 | Coach A | Download that athlete's growth PDF | `athlete/export`, `meta.document_kind = growth_pdf` |
| 11 | Coach A | Generate the monthly technical report | `monthly_report/create` |
| 12 | Coach A | Approve it | `monthly_report/approve` |
| 13 | Coach B | Regenerate it (`force_regenerate=true`) | `monthly_report/update` + `monthly_report/unapprove`, one `request_id` |
| 14 | Coach A | Generate the family newsletter | `athlete_monthly_newsletter/create` |
| 15 | Coach B | Edit the newsletter's coach note | `athlete_monthly_newsletter/update` |
| 16 | Coach A | Approve the newsletter | `.../approve` |
| 17 | Coach A | Send it to the family | `.../send` |
| 18 | Coach B | Launch a race-analysis run | `agent_run/create` |
| 19 | Admin | Deactivate the parent account | `user/deactivate` with `reason_code` |
| 20 | Coach A | Archive the demo athlete with a reason | `athlete/archive` |
| 21 | Admin | **Restore** the athlete (cleanup for the rest of the guide) | `athlete/restore` |

**Expected**

- Every row shows the right actor, action and record: **0 misattributions** over the whole set.
  Note that some single user actions legitimately emit more than one row (steps 1 and 13, and staff
  creation in scenario 6) — the assertion is "0 misattributed rows", not "exactly 20 rows".
- Each row renders as a plain-Spanish sentence — e.g. *"Beto Coach canceló la sesión de
  entrenamiento del 15 de marzo de 2026 (Clima adverso)."* The catalogue is
  `contracts/audit-log-api.md` §7.5; the reader never sees a raw identifier outside the expandable
  "Ver detalle".
- Filtering by coach B returns **only** B's rows (steps 2, 3, 5, 8, 13, 15, 18); by
  `entity_type=training_session`; by athlete; by `from`/`to` — both bounds day-inclusive
  (`contracts/audit-log-api.md` §2.1).
- **Correlation (US1 AS5)**: save a session roster over 5 athletes → 5 rows sharing one
  `request_id`; pasting that token into the `request_id` filter returns exactly those 5.
- **Automated actor (US1 AS4)**: POST the Resend delivery webhook (or run the Strava reconcile) →
  the row has `actor_kind` = `webhook` / `cron`, `actor_user_id` = `NULL`, `actor_display_name` =
  the fixed label of `contracts/audit-log-api.md` §6.2 — **never** the last signed-in user.
- **Failed request writes nothing**: force an error after the business write in one endpoint →
  neither the data change nor the audit row exists (`spec.md:168`).

**Automated equivalent**: `tests/test_audit_actors.py`, `tests/test_audit_coverage.py` (items 5–7),
`tests/routers/test_audit_log_api.py` T1/T12.

---

### Scenario 2 — The history holds no minor's data (US1 · SC-001, second half · FR-003)

Run **after** scenario 1, against the same dev database. Every check below returns a **count**;
never select the rows themselves.

```sql
-- 1. Nothing but allow-listed keys reached diff_json / meta_json.
SELECT COUNT(*) AS forbidden_keys FROM audit_log
WHERE COALESCE(diff_json, '') REGEXP '"(first_name|last_name|birth_date|sex|email|phone|individual_feedback|excuse_reason|coach_note|coach_notes|notes|description|objectives|summary_text|ai_narrative|stage_overrides|consent_[a-z_]+)"'
   OR COALESCE(meta_json, '') REGEXP '"(first_name|last_name|birth_date|sex|email|phone)"';
-- expected: 0

-- 2. No athlete name leaked as a value (counts only — no name is printed).
SELECT COUNT(*) AS name_hits
FROM audit_log a JOIN athletes t
WHERE CONCAT(COALESCE(a.diff_json,''), COALESCE(a.meta_json,'')) LIKE CONCAT('%', t.first_name, '%')
   OR CONCAT(COALESCE(a.diff_json,''), COALESCE(a.meta_json,'')) LIKE CONCAT('%', t.last_name,  '%');
-- expected: 0

-- 3. No measurement-shaped value.
SELECT COUNT(*) AS measurement_hits FROM audit_log
WHERE COALESCE(diff_json,'') REGEXP '"[a-z_]*_(cm|kg|z_score|percentile)"';
-- expected: 0
```

Then the response side: open `/club/historial` and `/athletes/{id}` → "Historial", and confirm no
name of a minor, no birth date and no free text appears — only actors (adults), actions, record
labels and catalogue reasons. The allow-list itself is `data-model.md` §2.5.

**Logs**: `docker compose logs backend | grep -c '"first_name"'` → `0`; every `app.*` record carries
a `request_id` (`contracts/audit-recording.md` §6). `AI_LOG_PROMPTS` stays `false`.

**Automated equivalent**: `tests/test_audit_privacy.py` (items 1–7) and
`tests/routers/test_audit_log_api.py` T8. Sign-off goes in `checklists/privacy.md`, produced by the
mandatory `data-privacy-guard` audit.

---

### Scenario 3 — Who may read the history (US1 AS6/AS7 · FR-006)

| Step | Caller | Request | Expected |
|---|---|---|---|
| 3.1 | Coach A (member) | `GET /api/clubs/1/audit-log` | `200`, newest first |
| 3.2 | Admin | `GET /api/clubs/1/audit-log` on a club they are not a member of | `200` |
| 3.3 | Parent | `GET /api/clubs/1/audit-log` | `403`, body `{"detail": "No tienes permisos para esta acción"}` |
| 3.4 | Parent | `GET /api/athletes/{their own child}/audit-log` | `403` — the regression `verify_athlete_access` alone would let through (`contracts/audit-log-api.md` §4.3) |
| 3.5 | Coach of another club | both endpoints | `403`, and the body reveals nothing about existence |
| 3.6 | Coach A | 10 consecutive reads | `SELECT COUNT(*), MAX(id) FROM audit_log` unchanged — reads are never recorded (FR-005) |

Also confirm the `X-Request-Id` header is present on `200`, `403` and `404`, is 32 hex chars, and is
listed in `Access-Control-Expose-Headers` cross-origin.

**Automated equivalent**: `tests/routers/test_audit_log_api.py` T4–T6, T11, T17.

---

### Scenario 4 — An archived athlete is invisible, and the parent stays calm (US2 · SC-003)

1. As coach A, open the athlete detail page → **"Archivar atleta"**. The confirm button stays
   disabled until a reason is chosen; submitting without one shows *"Selecciona un motivo para
   archivar."* Choose *"Se retiró del club"* → *"Atleta archivado."* and a redirect to `/athletes`.
   Copy and reason catalogue: `contracts/athlete-archive.md` §3 and §10.
2. Confirm the athlete is **absent** from: athlete list, dashboard counters, alerts, monthly-report
   roster and metrics, newsletter list and club batch, the AI athlete picker (launch → `404`),
   calendar audiences and birthdays, session convocatoria (`400`), race roster (`422`), competitor
   and import candidates, Strava lists, and `GET /api/athletes/{id}` as coach (`404`). The full
   enumeration is `contracts/athlete-archive.md` §5 — do not shorten it.
3. Sign in as the linked parent whose only athlete this is: `my-athletes` → `200 []`, a calm *"no
   athletes linked"* empty state, **no error and no blocking consent modal**;
   `GET /api/athletes/{archived_id}` → `403`.
4. As **admin**, `GET /api/athletes?include_archived=true` → the athlete is returned with
   `deleted_at`, `deleted_reason_code` and a resolved `deleted_by` name, at
   `/admin/atletas-archivados`. Verify by count that the parental consent, anthropometric records,
   attendance, results and audit rows all still exist (`contracts/athlete-archive.md` §6). A coach
   sending `include_archived=true` → `403`.
5. As admin, **restore** with a reason → the athlete reappears in every surface in one action, and
   `/athletes/{id}` → "Historial" shows the archive and the restore entries in order.

**Expected**: 100 % of consent/measurement/attendance/result records readable by the admin; the
athlete in **0** active surfaces; restore in one action. Archiving an athlete that has attendance,
event and race history succeeds cleanly (US2 AS4 — today it fails half-way on `RESTRICT` FKs).

**Automated equivalent**: `tests/test_archived_athlete_absent.py`,
`tests/test_parent_archived_only.py`, `tests/routers/test_athlete_archive.py`.
**[e2e blocked]** `e2e/athlete-archive.spec.ts`.

---

### Scenario 5 — Accounts are deactivated, never destroyed (US2 AS6/AS7 · FR-018)

1. As admin, `DELETE /api/users/{coach B}` → **`409`** with the guidance to deactivate
   (`contracts/athlete-archive.md` §8.3). Nothing is deleted.
2. `PATCH /api/users/{coach B}` `{"is_active": false, "reason_code": "account_staff_rotation"}` →
   `200`; audit row `user/deactivate` with `diff_json = {"is_active": {"before": true, "after":
   false}}`.
3. Coach B signs in → `401` **"Usuario desactivado"**; a previously issued access token → `401`.
4. Re-read the club history: coach B's **name still resolves** on every past entry, and on
   `deleted_by` of the athlete they archived (FR-013).
5. As admin, delete a parent account that granted a parental consent → `409`; delete a parent with
   no activity → `204`, and **no other record loses its `created_by`** (the regression of US2 AS7).
6. An admin cannot deactivate themselves → `403`.

**Automated equivalent**: `tests/test_users_delete_deactivate.py`, `tests/test_audit_actors.py` (4).

---

### Scenario 6 — Onboarding the second coach from the app (US3 · SC-004)

Target: **under 2 minutes**, start to first sign-in.

1. As admin, open `/admin/usuarios` → the staff list shows name, role, active state, creation date
   and creator, filterable by state.
2. **"+ Nuevo entrenador"** → submit **without** a club → inline error on the club field and **no
   network request fired** (US3 AS1).
3. Fill the club → `201`. The row appears as **activo**, with today's date and the admin as creator.
4. Open MailHog (`:8025`) → exactly one set-password e-mail for the new address; **no password in
   the response body and none in the message**. Follow the link and set a password.
5. Sign in as coach B → athletes, sessions, calendar, reports and competitions show **the same
   counts** the existing coach sees: **0 discrepancies** (US3 AC3).
6. Sign in as coach A (a coach, not an admin): the `Administración` navigation entry is absent and
   navigating straight to `/admin/usuarios` redirects to `/dashboard` (FR-021).
7. As admin, deactivate coach B with a reason → sign-in refused with **"Usuario desactivado"** and
   the state change recorded.
8. Membership coherence: `POST /api/clubs/1/members` with `role_in_club="coach"` on a **parent**
   account → `422` (FR-022).

**Automated equivalent**: `tests/test_staff_admin.py` (1–35), `StaffPage` / `StaffCreateSheet` /
`StaffStateDialog` vitest + a11y suites. **[e2e blocked]** `e2e/staff-admin.spec.ts`.

---

### Scenario 7 — Co-coached session and the acting coach in the family e-mail (US4 · SC-005)

**MailHog is the oracle**: `:8025` on the dev stack, `:8026` on the isolated stack.

1. Coach A creates a session and adds coach B in the wizard's **"Entrenadores a cargo"** field, with
   notifications on. The invitation e-mail body names **A** (*"El entrenador Ana Coach del …
   ha planificado…"*) and the highlight box shows **"Entrenadores a cargo: Ana Coach y Beto Coach"**;
   the signature block reads **"Ana Coach y Beto Coach — <club>"**.
2. Coach B edits the session with notifications on → the update e-mail names **B** as the actor and
   still lists both coaches.
3. Coach B **cancels** the session with a reason → the cancellation e-mail reads *"El entrenador
   **Beto Coach** del … ha **cancelado** la sesión…"* plus *"La sesión estaba a cargo de Ana Coach y
   Beto Coach."* This is the regression: today the mail names the **creator**, coach A.
   Exact copy and template lines: `contracts/session-coaches.md` §5.2.
4. Try to remove the last remaining coach from a session → refused, *"Una sesión debe tener al menos
   un entrenador."*
5. Filter the session list and the calendar by coach (`?coach_user_id=`) → only that coach's
   sessions / created events; birthdays never appear.
6. Deactivate the only coach of a future session → the listing flags it (`Entrenador inactivo`) so
   the other coach can take it over.

**SC-005**: repeat steps 2–3 over a scripted set of **10 changes split between the two coaches** →
the acting coach is named correctly in **10/10**.

**Automated equivalent**: `tests/test_session_coaches.py` B-01…B-07/B-15,
`tests/test_training_session_notifications.py` B-08/B-09, `tests/test_training_session_router.py`
B-13. **[e2e blocked]** `e2e/session-co-coaches.spec.ts`.

---

### Scenario 8 — Attendance attribution and roster shrink (US4 AS4/AS5 · FR-011, FR-016)

1. Coach A records attendance, ratings and individual feedback for one athlete; coach B edits the
   same entry. The coach surface shows **"Registrado por Ana Coach · Editado por Beto Coach"**;
   `recorded_by_user_id` is unchanged by B's edit.
2. Remove that athlete from the session roster and save → the entry is **archived, not deleted**:
   ratings and feedback intact, `archived_at` set, an `session_attendance/archive` audit row. An
   admin reading with `include_archived=true` still sees it; a coach or parent sending that flag
   → `403`.
3. Re-add the athlete → the row un-archives with no unique-constraint error.
4. **Privacy**: the parent-facing session and attendance payloads contain no `coaches`, no
   `recorded_by_display_name` and no `last_edited_by_display_name`.

**Automated equivalent**: `tests/test_attendance_validation.py` B-10…B-12,
`tests/test_training_session_privacy.py` B-14.

---

### Scenario 9 — Two coaches cannot overwrite each other in the newsletter studio (US5 · SC-006)

Two browsers (or two tokens), same newsletter, `edit_version = 4`.

```bash
# Coach A saves first — succeeds and bumps the version.
curl -sS -i -X PATCH .../api/athletes/2/monthly-newsletters/812 \
  -H "Authorization: Bearer $TOKEN_A" -H 'If-Match: "4"' -H 'Content-Type: application/json' \
  -d '{"coach_note":"Nos vemos en la próxima válida."}'
# → 200, ETag: W/"5"

# Coach B saves a stale version — refused.
curl -sS -i -X PATCH .../api/athletes/2/monthly-newsletters/812 \
  -H "Authorization: Bearer $TOKEN_B" -H 'If-Match: "4"' -H 'Content-Type: application/json' \
  -d '{"stage_overrides":{"observations":["…"]}}'
# → 409 {"detail":"Otro entrenador guardó cambios en este boletín. Recarga para ver la última versión.","current_version":5}
```

**In the UI** (`contracts/concurrency-and-approvals.md` §6):

1. Coach B's save raises `newsletter-conflict-dialog` with that exact Spanish copy.
2. **The draft is not lost** — the edited text is still in the textarea, no refetch fired.
3. "Seguir editando" closes the dialog and keeps the banner; "Recargar" invalidates once, clears the
   banner, and the reseeded draft matches the server payload, now **showing coach A's note with A's
   name and time**.
4. Saving with no precondition at all → `428` and a toast, not the conflict dialog.
5. A `sent` newsletter → `409` with the terminal-state message and **no** `current_version` key.
6. The coach note byline (*"Nota escrita por … · …"*) is visible to coaches and admins; the **parent
   payload, the family e-mail and the family PDF contain no coach name at all** (FR-012) — verify by
   searching the rendered PDF text for the coach's surname: **0 occurrences**.

**Expected (SC-006)**: 0 edits lost; the second coach always gets a conflict message before their
save would overwrite the first coach's work.

**Automated equivalent**: `tests/routers/test_newsletter_concurrency.py` (1–8),
`tests/routers/test_newsletter_coach_note_author.py` (9–13), `tests/test_cors_etag.py` (21),
`AthleteNewsletterStudioPage.test.tsx` (22–29). **[e2e blocked]** `e2e/newsletter-conflict.spec.ts`.

---

### Scenario 10 — Approval evidence survives regeneration (US5 AS4 · FR-010)

1. Coach A approves the monthly report of a month → `approved_by_user_id = A`, `approved_at` set.
2. Coach B regenerates it with `force_regenerate=true`.
3. Expected: `generated_by_user_id = B`, `status = draft`, `approved_by_user_id = NULL`, and
   `previous_approved_by_user_id = A` with A's original timestamp. The report page shows
   **"Aprobado anteriormente por Ana Coach el 03 abr 2026"**.
4. Approve → regenerate → approve → regenerate: `previous_approved_*` always holds the **most
   recent** superseded approval.
5. The parent projection of the report contains **no** `previous_approved_*` key.
6. Both events appear in the history sharing one `request_id` (`monthly_report/update` +
   `monthly_report/unapprove`).

**Automated equivalent**: `tests/test_monthly_report_approval_evidence.py` (14–20),
`ReportDetailPage.test.tsx` (30–31).

---

### Scenario 11 — Either coach can act on the club's runs and imports (US6 · SC-007)

1. Coach A launches a race-analysis run that stops at **awaiting decision**.
2. Coach B opens `GET /api/race-analysis/runs/{id}/status` → **`200`** (today: "sin acceso"), takes
   the decision → `200`, and `agent_runs.decided_by_user_id` = B with `decided_at` set.
3. The run header renders **"Lanzado por Ana Coach · Decidido por Beto Coach"** — never a raw id.
4. Coach A starts an import parse; coach B reviews and **commits** it → `imported_by_user_id` stays
   A, `committed_by_user_id` = B with `committed_at`.
5. A coach of **another club** → `403` on all seven run endpoints and on the parse; a parent → `403`;
   an admin is unaffected.
6. `GET /api/race-analysis/admin/ai-usage?days=30` as coach **or** admin → `200` with `by_coach`;
   the per-coach `cost_usd_total` values **sum to the total** (within `1e-6`). The admin AI page
   renders one row per coach plus the total row.
7. Budget refusal: with `RACE_AI_BUDGET_USD_30D` set low **in a dev stack only** (by variable name —
   do not open `.env`), launch a run → `503` whose message names the **30-day window** and says
   in-flight runs finish (`contracts/scope-ai-imports.md` §8).

**Expected (SC-007)**: the handover works **5/5** times with no administrator intervention.

**Automated equivalent**: `tests/routers/test_race_analysis_club_scope.py` (1–9),
`tests/routers/test_race_imports_club_scope.py` (10–13),
`tests/services/race/ai/test_spend_by_user.py` (14–16), `AIHealthPage.test.tsx`.

---

### Scenario 12 — Per-coach activity reconciles, club-wide reports do not move (US7 · SC-008, SC-009)

**Seed a test month**: coach A leads 3 sessions and co-leads 1; coach B leads 2 and co-leads that
same 1; coach A launches 2 AI runs; coach B approves 1 monthly report.

1. Open `/training/reports/actividad-entrenadores` for that month.
2. Expected: **A → 4 sessions, 2 runs, 0 approvals; B → 3 sessions, 0 runs, 1 approval**. The
   co-led session counts for **each** coach.
3. `club_totals.sessions.total` = **6** — the size of the union, not the sum of the per-coach
   buckets (`contracts/coach-activity-report.md` §2). `club_totals` is never narrowed by the
   `coach_user_id` filter.
4. **SC-008**: `club_totals.sessions.{planned,executed,cancelled}` equals
   `compute_monthly_metrics(...)` for the same period, exactly.
5. **SC-009**: regenerate the club-wide monthly technical report, the dashboard summary, the race
   insights and the season panorama for a fixed month **before and after** the feature → identical
   sections, figures and institutional signature. Diff the DOCX/PDF headings and the signature block.
6. A parent requesting the per-coach view → `403`; a coach of another club → `403`; an unknown club
   → `404`; `from > to` or a 400-day window → `422`.
7. A **deactivated** coach with activity in the window is still listed, `is_active: false`, name
   resolved.
8. **Privacy**: the serialised response has no athlete name, no `athlete_id`, no birth date and no
   free-text key — its key set is closed.

**Automated equivalent**: `tests/test_coach_activity.py` (1–18),
`tests/test_monthly_report_unchanged.py`. **[e2e blocked]** `e2e/coach-activity.spec.ts`.

---

### Scenario 13 — A name on every author, and the athlete's own history (US7 AS4/AS6 · SC-002)

1. Walk the surfaces that display an author — created by, evaluated by, generated by, approved by,
   imported by, launched by, decided by — and confirm each shows a **display name**. In particular
   the competition info tab no longer prints *"Creado por usuario ID …"*
   (`contracts/coach-activity-report.md` §7.3).
2. A **deactivated** person's name still resolves; an unknown id renders *"Usuario no disponible"*;
   an automated actor renders *"Proceso automático"*. A bare numeric id renders **nowhere**.
3. Open an athlete detail page → **"Historial"**: entries about that athlete, newest first, same
   privacy rules as the club history, with an expandable detail.
4. **SC-002 (moderated, manual — not automatable)**: with the club's coach, ask 5 questions of the
   form *"¿quién cambió este registro y cuándo?"* directly from the athlete page. Target: **5/5
   answered in under 30 seconds each, without leaving the page.** Record the result in
   `docs/19-multi-coach-governance/qa.md`.

**Automated equivalent**: `ActorChip.test.tsx`, `InfoTab.test.tsx`,
`AthleteHistoryPanel.test.tsx` + `.a11y.test.tsx`, `ClubHistoryPage.test.tsx` + `.a11y.test.tsx`.

---

### Scenario 14 — Retention: preview first, purge only on confirmation (US8 · SC-010)

Seed two audit rows dated **25** and **23** months ago (the test helper of
`contracts/retention-purge.md` §8.1, or `--months` against a scratch database — never against
production).

```bash
cd backend && source .venv/bin/activate

python -m scripts.retention_audit_log                    # preview — the DEFAULT is dry-run
# stdout: {"candidates": 1, "deleted": 0, "cutoff": "2024-09-09T05:00:12"}

python -m scripts.retention_audit_log --apply
# stdout: {"candidates": 1, "deleted": 1, "cutoff": "2024-09-09T05:00:12"}

python -m scripts.retention_audit_log --apply            # idempotent
# stdout: {"candidates": 0, "deleted": 0, "cutoff": "…"}
```

**Expected**

- The preview **removes nothing**: the row count is unchanged and no `purge` row is written.
- After `--apply`: the 25-month row is gone, the **23-month row remains**, and exactly one new row
  per club records the purge (`audit_log/purge`, `reason_code = retention_24m`,
  `meta_json.removed_count`), rendered as *"Tarea programada purgó 1 registro del historial
  (Retención: 24 meses cumplidos)."* — singular, via the `{conteo}` pluraliser of
  `contracts/audit-log-api.md` §7.3.
- **Nothing is printed to stdout on a failing run**, and the database URL never appears in stdout or
  stderr — the operator log shows `host/database` only (`contracts/retention-purge.md` §2.2).
- Refusals: `--cutoff` inside the 24-month window → exit `1`; a future `--cutoff` → exit `1`; a
  non-async driver (`mysql+pymysql://`) → exit `1` **before any connection is opened**;
  `--actor-kind bogus` → exit `2`.
- **Append-only**: over a full test run of normal app use, no existing row is ever altered or
  removed. Snapshot every row, run a second batch of actions, re-read → the snapshot is present
  unchanged.
- The scheduled path is `.github/workflows/audit-retention.yml`: job 1 (preview) runs monthly and on
  every dispatch and touches nothing; job 2 (apply) runs **only** on a manual dispatch with
  `confirm=true`, reusing the cutoff job 1 published. Operator steps live in
  `docs/19-multi-coach-governance/runbook.md` §5.

**Automated equivalent**: `tests/test_retention.py` (T1–T15), `tests/test_audit_append_only.py`
(T16–T19), and T20–T21 in the `mysql` lane.

---

## 4. Cross-cutting gates

| Gate | Command / check |
|---|---|
| Audit coverage (FR-009) | `tests/test_audit_coverage.py` — every mutating route is registered as audited or exempt-with-reason; a new write path cannot ship unaudited |
| Append-only (FR-004) | `tests/test_audit_append_only.py` — static scan + model shape + behavioural |
| Privacy (FR-003) | `tests/test_audit_privacy.py` + the `data-privacy-guard` audit → `checklists/privacy.md` |
| Two-coach coverage (FR-034) | every new backend test uses the R-32 fixture and asserts both coaches' perspectives **and** the refused paths (parent, other-club coach, coach on staff actions) |
| Lint / types | `ruff check` · `npm run typecheck` |
| Accessibility | jest-axe with **zero** violations on `StaffPage`, `ClubHistoryPage`, `CoachActivityPage`, `ArchivedAthletesPage`, and the archive + conflict dialogs |
| Performance | query-count tests (`tests/test_audit_query_count.py`: one audited write = one extra INSERT, no extra SELECT; history read = 2 statements regardless of page size); `npm run build && npm run check:chunks` — each new lazy route ≤ 150 KB gzip, entry chunk not regressed |
| Copy | all new product strings in español neutro with full diacritics; `specs/` artifacts in English (constitution III) |

---

## 5. Post-deploy smoke

1. `GET /health` → `200`.
2. `GET /api/clubs/1/audit-log?limit=5` with a **coach** token → `200`, sentences render, actor names
   resolved; with a **parent** token → `403`.
3. `GET /api/clubs/1/coach-activity?from=…&to=…` with a coach token → `200`.
4. `/admin/usuarios` loads for the admin and is unreachable for a coach.
5. `X-Request-Id` present on the responses above.
6. First scheduled run of `.github/workflows/audit-retention.yml` (job 1 only) is green and reports
   `deleted: 0`.
7. Dashboard route loads on a real Android device within the LCP budget; Render cold start shows the
   "starting server" state, never a bare spinner.

---

## 6. Traceability

| Story | Scenario | Success criterion |
|---|---|---|
| US1 — every change has a name on it | 1, 2, 3 | SC-001 |
| US2 — deleting an athlete keeps the evidence | 4, 5 | SC-003 |
| US3 — the second coach is onboarded from the app | 6 | SC-004 |
| US4 — co-coached sessions, right name to families | 7, 8 | SC-005 |
| US5 — no silent overwrite | 9, 10 | SC-006 |
| US6 — either coach acts on runs and imports | 11 | SC-007 |
| US7 — club-wide and per-coach reports | 12, 13 | SC-008, SC-009, SC-002 |
| US8 — 24-month retention, deliberate purge | 14 | SC-010 |

| Contract | Scenarios |
|---|---|
| `contracts/audit-recording.md` | 1, 2 |
| `contracts/audit-log-api.md` | 1, 2, 3, 13 |
| `contracts/athlete-archive.md` | 4, 5 |
| `contracts/staff-admin.md` | 5, 6 |
| `contracts/session-coaches.md` | 7, 8 |
| `contracts/concurrency-and-approvals.md` | 9, 10 |
| `contracts/scope-ai-imports.md` | 11 |
| `contracts/coach-activity-report.md` | 12, 13 |
| `contracts/retention-purge.md` | 14 |

---

## 7. Known blockers and manual-only items

1. **Playwright is blocked** by the pre-existing migration bug of `research.md` R-34 (three
   migrations import deleted `app.data.*` modules) — five specs are deferred, not skipped. The
   `coach2` seed identity is a second prerequisite.
2. **SC-002 is a moderated usability test**, not an automated assertion; record it in
   `docs/19-multi-coach-governance/qa.md`.
3. **The `mysql` lane is required** for the migration/backfill cases, the microsecond boundary of the
   purge and the real-dialect concurrency test; the offline lane alone does not discharge them.
4. **The privacy policy wording of FR-033 ships with the next policy version**, not with this
   feature; there is nothing to validate here beyond the drafted text.
