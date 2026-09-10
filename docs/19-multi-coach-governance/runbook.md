# Multi-coach governance — Operational Runbook

> **Audience**: coach, admin, on-call.
> **Scope**: the club history/audit trail, the athlete archive/restore path, staff
> administration, and the 24-month `audit_log` retention purge.
> Design and rationale: [`design.md`](design.md). Full contracts:
> `specs/041-multi-coach-governance/contracts/`.

---

## 1. Club history (`audit_log`)

### 1.1 Reading it

- Coach/admin UI: club history page, filterable by actor, period, record type and
  athlete, newest first, rendered as a plain-Spanish sentence per entry with an
  expandable detail block.
- API: `GET /api/clubs/{club_id}/audit-log`, `GET /api/athletes/{athlete_id}/audit-log`.
  Parents and coaches of another club are refused (`403`).
- Every entry carries `request_id` — group by it to see every row of one logical
  operation (a bulk roster save, a batch newsletter generation).

### 1.2 What is never in a row

No minor's name, birth date, sex, measurement value, medical detail, consent text,
feedback text, coach note, narrative block, or AI output. Only identifiers, column names,
and a catalogue reason code. If a coach reports seeing something that looks like PII in
the history UI, treat it as a P1 privacy incident — see `docs/qa` privacy-audit process —
and check `VALUE_ALLOWLIST[entity_type]` in `backend/app/services/audit.py` for the entity
type in question before assuming it is a rendering bug.

### 1.3 It never updates or deletes on its own

If a row looks wrong, it is not editable — the only ways a row disappears are the
retention purge (§5) or a bug. Do not attempt to "fix" a row by hand in MySQL; that
breaks the append-only invariant this feature exists to guarantee, and the append-only
test suite (`backend/tests/test_audit_append_only.py`) will not tell you it happened.

## 2. Athlete archive and restore

### 2.1 Archiving

A coach removes an athlete from the app UI, picks a reason from the fixed catalogue, and
the athlete disappears from every active surface (coach, parent, dashboard, reports,
newsletters, AI). Nothing is destroyed — consent evidence, measurements, attendance and
history stay intact for an administrator.

### 2.2 Restoring

Administrator-only, from the archived-athletes admin view or `POST
/api/athletes/{id}/restore`. The athlete reappears everywhere in one action; the
restoration is itself recorded.

### 2.3 If an archived athlete's data seems to be missing for an admin

Consent evidence, measurements, attendance, and history must remain readable by an
administrator even while the athlete is archived. If any of those come back empty or
`404` for an admin account, that is the regression `contracts/athlete-archive.md` and its
test suite (`G17`–`G19` in the integration review) exist to catch — check
`verify_athlete_access_allow_archived` in `backend/app/dependencies.py` first.

## 3. Staff administration

`/admin/usuarios`, administrator-only.

- **Create a coach**: name, email, club (mandatory). The account is created active, with
  the coach role, in the club chosen — there is no path to a coach signed in with no club
  membership. The new coach gets the standard "set your password" email; no password is
  ever shown or sent in clear.
- **Deactivate / reactivate**: the account can no longer sign in once deactivated; its
  name stays resolvable on every past history entry.
- **Deleting** a coach or administrator with any recorded activity is refused (`409`),
  pointing at deactivation instead. There is no override — if a staff account truly must
  be removed from the database, that is a manual DB operation outside this feature's
  scope, done only with the owner's explicit sign-off.

## 4. Co-coached sessions

A session always has at least one coach; the UI refuses to remove the last one (`409`
from the API if attempted directly). Family notifications name whichever coach performed
the action being emailed (invite, update, cancel), not necessarily the session's original
creator — this is intentional (FR-025), not a bug if two different names appear across a
session's emails.

---

## 5. Retention purge of `audit_log` (24 months)

Source of truth: `specs/041-multi-coach-governance/contracts/retention-purge.md` §6. This
section restates it for the operator, in English per the `docs/**` language rule.

### 5.1 Policy

- History entries are kept **24 months** on `occurred_at`.
- Nothing inside the running application ever removes a row on its own. The only removal
  path is the procedure below.
- The purge is itself audited: it writes one `audit_log` row per affected club
  (`action=purge`, `reason_code=retention_24m`), visible in the club history as e.g.
  *"Tarea programada purgó 143 registros del historial (Retención: 24 meses cumplidos)."*
- That purge row ages out 24 months later like any other row. The durable external record
  of a purge beyond that window is the GitHub Actions run log (§5.4), not the table.

### 5.2 Preview (always safe)

```bash
cd backend && source .venv/bin/activate
python -m scripts.retention_audit_log            # preview, default — never deletes
```

Expected stdout — exactly one JSON line, always:

```json
{"candidates": 143, "deleted": 143, "cutoff": "2024-09-09T05:00:12"}
```

`deleted` is always `0` on a preview run — it reflects rows actually removed, not
candidates. Read the `ROW` breakdown on stderr for a per-entity-type count:

```text
[2026-09-09T05:00:12Z] INFO    modo = SIMULACIÓN (usa --apply para ejecutar)
[2026-09-09T05:00:12Z] INFO    ventana de retención = 24 meses (cutoff = 2024-09-09T05:00:12)
[2026-09-09T05:00:12Z] INFO    base de datos = srv-xxx.hostinger.com/trocha_ruta
[2026-09-09T05:00:13Z] INFO    candidatos a purgar: 143
[2026-09-09T05:00:13Z] ROW     entity_type=session_attendance candidatos=88
[2026-09-09T05:00:13Z] ROW     entity_type=calendar_event candidatos=31
[2026-09-09T05:00:13Z] ROW     entity_type=training_session candidatos=24
[2026-09-09T05:00:13Z] DRY     no se ejecuta DELETE. Usa --apply para aplicar.
[2026-09-09T05:00:13Z] EXIT    candidates=143 deleted=0 apply=false
```

A preview is always safe to run against production — it never opens a write transaction
against `audit_log`.

### 5.3 Apply

```bash
python -m scripts.retention_audit_log --apply
```

Rules:

- **Always reuse the cutoff from a preview you just ran**, rather than letting `--apply`
  compute its own — pass `--cutoff <value from the preview JSON>` when running by hand so
  the count you approved is exactly the set that gets deleted. The scheduled workflow
  (§5.4) does this automatically.
- **`--months` must never be lowered against production.** It is a debugging affordance
  for a local database only; the default (`24`) is what the runbook and FR-030 promise.
- A `--cutoff` that falls **inside** the 24-month window is refused before any connection
  opens — this is the safety rail against a fat-fingered value ever reaching live data.

Successful apply, last two log lines:

```text
[2026-09-09T05:00:14Z] DONE    143 filas eliminadas; registro de purga creado (club_id=1, removed_count=143)
[2026-09-09T05:00:14Z] EXIT    candidates=143 deleted=143 apply=true
```

Zero case (nothing older than the cutoff) writes **no** purge row and leaves the table
byte-identical — this is intentional idempotency, not a bug to investigate.

### 5.4 Scheduled run

`.github/workflows/audit-retention.yml`, two jobs:

- **`preview`** — runs monthly (`0 5 1 * *` UTC, i.e. 00:00 Colombia on the 1st) and on
  every manual dispatch. Always a dry-run; publishes `cutoff` and `candidates` as job
  outputs and in the run's step summary. Never touches data.
- **`apply`** — runs **only** on manual `workflow_dispatch` with `confirm` typed exactly
  `true`, and only after `preview` has finished in the same run — it reuses `preview`'s
  published cutoff verbatim, so the count an operator approved is what gets deleted.

To run it: Actions tab → "Audit Retention" → **Run workflow** → set `confirm` to `true`
only when you intend to actually purge (any other value, including leaving the default,
only simulates). The `apply` job requires approval from the `production` GitHub
Environment's reviewer list (§5.5).

Where to read the count: the `preview` job's step summary in that run.
Where to read the apply result: the `apply` job's log, last two lines as in §5.3.

**Not yet exercised**: this workflow has never actually run against production or a real
`_test` database in this environment — see §5.6 for why, and confirm connectivity before
relying on the schedule.

### 5.5 Secret and access

- `AUDIT_RETENTION_DATABASE_URL` — a GitHub repository secret (Settings → Secrets and
  variables → Actions), **not** a Render env var. Referred to by name only, here and
  everywhere else — never by value, in a log line, a commit message, or a doc. Recommended
  (not yet enforced): a dedicated MySQL user with `SELECT, INSERT, DELETE` on `audit_log`
  only, nothing on any other table.
- Hostinger's shared MySQL plan allowlists clients by IP; GitHub-hosted runners do not
  have a stable IP. Before relying on the schedule, one of the following must be true —
  see `docs/10-race-results/runbook-ops.md` §1.2 for the equivalent precondition on the
  sibling retention job:
  1. Remote MySQL access opened for the dedicated retention user from any host, accepting
     that the mitigation is the account's `audit_log`-only grant plus a strong password.
  2. The workflow runs on a self-hosted runner with a stable, allowlisted outgoing IP.
  3. **The schedule stays disabled and the purge is run by hand from the owner's own
     machine once a year** (`--apply`, same CLI, same cutoff rules as above), logged here
     each time it runs. This is the acceptable default — 24-month retention has an
     annual, not monthly, urgency, and the table is a few thousand rows at steady state.
- **Access control substitution**: FR-030 requires the purge procedure be "restricted to
  administrators." There is no in-app permission to grant here — this is held entirely by
  (a) the repository's write-access list (who can trigger `workflow_dispatch`) and (b) the
  `production` GitHub Environment's required-reviewer list (who can approve the `apply`
  job). **Both lists must be re-checked at every staff change** and kept equal to the
  club's real administrator set — there is nothing in the app itself enforcing this.

### 5.6 Post-run validation

```sql
-- Must be 0 immediately after --apply:
SELECT COUNT(*) FROM audit_log
WHERE occurred_at < DATE_SUB(NOW(), INTERVAL 24 MONTH);

-- The purge left its own trace (one row per affected club):
SELECT id, occurred_at, club_id, actor_kind, reason_code, meta_json
FROM audit_log
WHERE action = 'purge'
ORDER BY occurred_at DESC
LIMIT 5;
```

**The one mistake this procedure cannot prevent**: running the CLI against the wrong
database. The URL comes from a single job-scoped secret and the operator log always
prints `host/database` (never the credential) on every run — read that line before typing
`confirm = true`.

### 5.7 Failure modes

| Symptom | Likely cause | What to do |
|---|---|---|
| Connection refused | IP not allowlisted on Hostinger | See §5.5's three options. |
| `candidates` unexpectedly large | First run after roughly two seasons of accumulation (≈8,000 rows/year is the expected order of magnitude) | Expected, not a bug — proceed with `--apply` as normal. |
| `apply` job did not run | `confirm` was not exactly `true`, or it ran on a schedule trigger (structurally impossible — only `workflow_dispatch` can reach `apply`) | Re-dispatch with `confirm=true`. |
| `candidates` is non-zero right after a successful `--apply` | A row was written between preview and apply with an `occurred_at` older than the cutoff — should be impossible, since `occurred_at` is only ever set to "now" | Investigate a clock skew or a manual `INSERT` before assuming the tooling is broken. |

### 5.8 Not yet verified in this environment (say so, do not guess)

Every night run that built this feature (2026-09-09/10) had no Docker and no reachable
MySQL. As a direct consequence, **none of the following has actually been executed** —
they are contract-correct and offline-lane-tested, not live-verified:

- The GitHub Actions workflow itself, against production or any database.
- `alembic upgrade head` from empty against a live `_test` MySQL database for this
  feature's migration (`45cd705c6b54_multi_coach_governance.py`) — the `mysql` pytest
  lane that exercises this (`backend/tests/test_audit_mysql.py`,
  `backend/tests/test_retention.py`'s `mysql`-marked cases) was written but not run.
  See `qa.md` §2 for the complete list of what the `mysql` lane owns.
- The first real production purge — expect `candidates: 0` on the first post-deploy dry
  run, since the feature itself is brand new and nothing in `audit_log` is 24 months old
  yet. `tasks.md` T097 (post-deploy smoke) explicitly asks for this dry run from the
  owner's machine as its first verification step once deployed.

Whoever runs the first live preview should record the result here as a dated addendum,
the same way `docs/10-race-results/runbook-v2.md`'s sibling job is operated.

## 6. DB-level hardening — deferred, not built

`audit_log` has no `BEFORE UPDATE`/`BEFORE DELETE` trigger and no dedicated grant
restricting `UPDATE`/`DELETE`. This codebase has zero triggers anywhere and Hostinger
gives the app one DB user, so this is deferred rather than built now (`design.md` §9). If
a second MySQL account is ever provisioned for the retention job (§5.5), revoking
`UPDATE`/`DELETE` on `audit_log` from the *application's* own account becomes possible and
is the natural next hardening step.
