# Contract — Retention and purge of `audit_log`

**Scope**: FR-030 (US8). The 24-month retention horizon for `audit_log`, the
preview-then-confirm purge procedure (`app/services/retention.py` +
`backend/scripts/retention_audit_log.py`), its monthly schedule
(`.github/workflows/audit-retention.yml`), the operator runbook, and the automated proof
of FR-004 — *the application never issues `UPDATE` or `DELETE` against `audit_log`*.

**Out of scope, contracted elsewhere**: the `record_audit` signature and the request
context (`contracts/audit-recording.md`); the shape of the history read endpoints and the
Spanish sentence catalogue that renders the purge row (`contracts/audit-log-api.md` §7.5);
the `audit_log` columns, indexes and catalogues (`data-model.md` §1, §2). Permanent purge
of *archived athletes* is out of scope for the whole feature (spec.md:283) — this contract
removes audit rows and nothing else.

**Not built here**: no in-app purge endpoint, no admin UI, no background worker. §4
records why.

---

## 0. Reconciliation with the sibling artifacts

Three details are fixed differently here than in the earlier artifacts. Each divergence is
deliberate; the earlier wording is superseded.

| Item | Earlier wording | This contract | Why |
|---|---|---|---|
| Retention flag | `--days`, default `730` (`research.md` R-25) | `--months`, default `24` | 730 days is not 24 calendar months — it drifts by one to two days and by a leap day, so the boundary the coach was told about ("dos temporadas") and the boundary the job enforces would differ. FR-030 and `data-model.md` §1.3 both state the horizon in **months**; the flag now states it in the same unit. |
| `actor_kind` of the purge row | `purge_job` (`research.md` R-25); "`cron` when scheduled or `user` when an admin runs it interactively" (`data-model.md` §1.3 and `contracts/audit-recording.md` §3.3 — **both since corrected to `system`/`cron`**, so this row is now history, not a live divergence) | `system` by default, `cron` when the scheduled workflow passes `--actor-kind cron` | `purge_job` is not a member of the enum — `data-model.md` §2.2 collapsed it into `system`/`cron` and that enum is what reaches the DDL. `user` is impossible for a CLI: there is no authenticated session, and writing `actor_user_id` from a `--user-id` flag would fabricate an attribution nobody verified (the same posture that makes backfill B2 refuse to invent `approved_by_user_id`, `data-model.md` §6.3). The two remaining values map exactly onto the two real invocations, and both already have a label in `contracts/audit-log-api.md` §6.2 (`system` → "Sistema", `cron` → "Tarea programada"). |
| Number of purge rows | "exactly one new row", `club_id` unspecified (`data-model.md` §1.3) | one row **per distinct `club_id` present in the deleted set**, each carrying that club's own count | A row with `club_id = NULL` is invisible to the club history by construction (`data-model.md` §8.4), which would make the purge sentence in `contracts/audit-log-api.md` §7.5 (`{actor} purgó {conteo} registros del historial ({motivo}).`) unreachable and FR-030's "records the purge as a history entry" true only in the raw table. On today's single-club deployment (`data-model.md` §9) this **is** exactly one row, so §1.3's count is unchanged in practice; it degrades correctly when a second club is onboarded. |

Unchanged from `data-model.md` §1.3 and reasserted below: the horizon is 24 months on
`occurred_at`; the cutoff is computed **once** and reused verbatim by the confirming step;
the purge row uses `reason_code=retention_24m`, `entity_type=audit_log`, `entity_id=0`;
the purge is additive (one `INSERT`) and is therefore not a violation of the append-only
rule, which forbids `UPDATE`/`DELETE` of *existing* rows by the app.

Unchanged from `contracts/audit-log-api.md`: `meta_json.removed_count` is the key the
sentence renderer reads for `{conteo}` (`audit-log-api.md:447`) and is one of the
known meta keys the response filter allows (`audit-log-api.md:669`). The CLI's JSON
field for the same number is called `deleted` (§2.3) — the mapping
`stdout.deleted → meta_json.removed_count` is stated once here and nowhere else.

---

## 1. Service — `backend/app/services/retention.py` (new)

The service owns the only `DELETE` against `audit_log` in the entire application
(`data-model.md` §1.2 item 3). The CLI is a thin wrapper: it resolves an engine, calls
these two functions, prints, and exits.

### 1.1 Signatures

```python
async def preview_purge(
    db: AsyncSession,
    *,
    cutoff: datetime,          # naive UTC
) -> PurgePreview: ...

async def apply_purge(
    db: AsyncSession,
    *,
    cutoff: datetime,          # naive UTC — the SAME value preview_purge received
    actor_kind: AuditActorKind,   # system | cron only
    request_id: str,           # one uuid4().hex per invocation, shared by every row written
) -> PurgeResult: ...
```

```python
@dataclass(frozen=True)
class PurgePreview:
    cutoff: datetime
    candidates: int                    # total rows with occurred_at < cutoff
    by_entity_type: dict[str, int]     # operator breakdown, never printed as JSON
    by_club_id: dict[int | None, int]  # drives the purge rows of §1.4

@dataclass(frozen=True)
class PurgeResult:
    cutoff: datetime
    candidates: int
    deleted: int                       # rowcount of the DELETE
    audit_row_ids: list[int]           # empty when deleted == 0
```

Neither function commits, opens a session, or creates an engine — the same rule
`record_audit` follows (`research.md` R-03). `apply_purge` leaves the transaction open for
its caller to commit, so a failure anywhere in the sequence rolls back the delete **and**
the purge row together.

### 1.2 The cutoff

```python
def retention_cutoff(now: datetime, months: int = 24) -> datetime:
    """now (naive UTC) minus `months` calendar months, clamping the day of month."""
```

- Pure function, no I/O, computed by the caller and passed in — so the tests can pin it
  and the two GitHub Actions jobs can share one value (§3.3).
- Calendar-month arithmetic with day clamping (31 Mar − 1 month → 28/29 Feb). Implemented
  in ~6 lines with `calendar.monthrange`; **no new dependency** — `python-dateutil` is
  only a transitive dependency of `pandas` and the constitution's stack-discipline gate
  makes promoting a transitive dependency to a direct import a written-justification
  event for no benefit here.
- Naive UTC, matching every other timestamp in the schema (`data-model.md`, Conventions).

**The candidate set for a fixed cutoff is stable.** `occurred_at` is written once with
`now()` and never updated (FR-004), so rows only ever *enter* the table above the cutoff.
A preview taken at 05:00 and an apply run at 05:04 with the same cutoff therefore delete
exactly the rows that were counted — this is what makes the two-job split of §3 safe, and
it is the whole reason the cutoff is handed over instead of recomputed.

### 1.3 `apply_purge` — statement order (one transaction)

| # | Statement | Note |
|---|---|---|
| 1 | `SELECT club_id, COUNT(*) FROM audit_log WHERE occurred_at < :cutoff GROUP BY club_id` | Feeds §1.4. A second `GROUP BY entity_type` runs in `preview_purge` only (operator log). |
| 2 | `DELETE FROM audit_log WHERE occurred_at < :cutoff` | Strict `<`: a row whose `occurred_at` equals the cutoff to the microsecond is **kept**. Core `sa.delete(AuditLog)`, one statement — see §7 for why no batching. |
| 3 | `record_audit(...)` once per key of step 1 | Rows built with `occurred_at = now()`, which is ≫ cutoff, so they can never be caught by step 2 — which has already run in any case. |
| 4 | `await db.commit()` — in the **caller** (`retention_audit_log.py`) | Steps 1–3 are one unit of work. |

`preview_purge` executes step 1 and the `entity_type` breakdown and nothing else. It is
called on every run, including `--apply`, so the count always precedes the delete in the
log.

### 1.4 The purge audit row

One row per distinct `club_id` in the deleted set (§0), written through `record_audit`
(signature owned by `contracts/audit-recording.md`):

| Field | Value |
|---|---|
| `actor_user_id` | `NULL` |
| `actor_kind` | `system` (manual run) or `cron` (scheduled workflow) — §2.1 |
| `actor_role` | `NULL` |
| `club_id` | the club whose rows were removed; `NULL` for the club-less rows, if any |
| `athlete_id` | `NULL` |
| `entity_type` | `audit_log` |
| `entity_id` | `0` |
| `action` | `purge` |
| `changed_fields` | `[]` |
| `diff_json` | `NULL` |
| `reason_code` | `retention_24m` (mandatory for `(audit_log, purge)`, `data-model.md` §2.4) |
| `request_id` | one `uuid4().hex` for the whole invocation, shared by every purge row of the run (FR-002 correlation) |
| `meta_json` | `{"removed_count": <rows removed for this club_id>, "cutoff": "<ISO-8601>", "job": "audit_retention"}` |

Renders in the club history as (`contracts/audit-log-api.md:629`):

> Tarea programada purgó 143 registros del historial (Retención: 24 meses cumplidos).

`meta_json` carries no name, no e-mail, no athlete identifier and no free text — the three
keys are all in the known-key set of `audit-log-api.md:669`, so the same privacy scan that
covers every other row covers these (`backend/tests/test_audit_privacy.py`).

### 1.5 Idempotency and the zero case

- `deleted == 0` → **no purge row is written**. Re-running the job on a table with nothing
  older than the cutoff must leave the table byte-identical, otherwise a monthly schedule
  would accumulate a decade of "purgó 0 registros" noise in the coach's history.
- Running `--apply` twice with the same cutoff: the second run finds `candidates == 0`
  (the first deleted them) and writes nothing. Idempotent by the data, not by a guard
  column.
- The purge rows themselves age out 24 months later, and are then removed by a future run
  like any other row. The durable external record of a purge is the GitHub Actions run log
  (§3), not the table.

---

## 2. CLI — `backend/scripts/retention_audit_log.py` (new)

Typer app, module-level `app = typer.Typer(add_completion=False, help=__doc__)`, one
`@app.command()`, mirroring `backend/scripts/retention_ai_insights.py:55` in structure and
in flag polarity — **safety comes from dry-run being the default, not from remembering to
type a flag** (`research.md` R-25).

Invocation (matches the documented shape of `docs/10-race-results/runbook-v2.md:104-133`):

```bash
cd backend && source .venv/bin/activate

python -m scripts.retention_audit_log                      # preview (default, safe)
python -m scripts.retention_audit_log --apply              # purge
python -m scripts.retention_audit_log --apply \
    --cutoff 2024-09-09T05:00:12 --actor-kind cron         # what the workflow runs
```

### 2.1 Options

| Option | Type | Default | Notes |
|---|---|---|---|
| `--apply` / `--dry-run` | bool flag pair | `False` (dry-run) | A single Click boolean pair, so job 1 of the workflow can spell `--dry-run` explicitly while the default stays safe. `research.md` R-25 rejects a `--dry-run` flag with a destructive default; a *pair* keeps that rejection intact. |
| `--months` | int, `min=1` | `24` | Retention window. Lowering it is a debugging affordance, exactly like `retention_ai_insights.py:131-139`; the runbook forbids it against production. The scheduled workflow never passes it. |
| `--cutoff` | ISO-8601 naive UTC string | `None` | Overrides the computed cutoff so the confirming job reuses the previewed one verbatim (`data-model.md` §1.3). When both are given, `--cutoff` wins, a `WARN` line is emitted, and `--months` still defines the validation window of §2.6. |
| `--actor-kind` | choice `system` \| `cron` | `system` | §0. Any other value is a Typer-level error (exit 2). |
| `--database-url` | str | `None`, `envvar="AUDIT_RETENTION_DATABASE_URL"` | Precedent for `envvar=` on a Typer option: `backend/scripts/smoke_test_prod.py:205-218`. When absent, falls back to `settings.database_url`. |

### 2.2 Engine, session and the deferred imports

```python
async def _run(...) -> int:
    # Deferred inside the command, like retention_ai_insights.py:74-75, so `--help`
    # works without a venv and without loading SQLAlchemy or Settings.
    from app.models.audit_log import AuditLog          # noqa: F401 — mapper registration
    from app.services import retention
```

The CLI **must not** import `AsyncSessionLocal` from `app.database`. That module builds
its engine at import time from `settings.database_url`
(`backend/app/database.py:27-37`, session factory at `:49-52`), so a `--database-url`
would be silently ignored. The CLI creates its own:

```python
engine = create_async_engine(url, pool_pre_ping=True)
factory = async_sessionmaker(engine, expire_on_commit=False)
```

and disposes it in a `finally`. `app.config` is imported **only** when no URL was supplied
(`--database-url` absent and `AUDIT_RETENTION_DATABASE_URL` unset), so a CI run that
passes an explicit URL never constructs `Settings()` and never needs a `.env`
(`backend/app/config.py:452-456` points `env_file` at `.env`; the composed fallback lives
at `backend/app/config.py:433-437` over the `MYSQL_*` settings at `:7-12`).

**The URL is never echoed.** Neither `_emit` nor the JSON ever contains it. The operator
log prints `host/database` only, derived with
`sqlalchemy.engine.make_url(url)` → `f"{u.host}/{u.database}"`. Never
`render_as_string(hide_password=False)`; never the raw string. GitHub Actions logs are
readable by every repository collaborator, and the production MySQL password lives in that
URL.

### 2.3 stdout — the machine contract

Exactly one line on **stdout**, always, on every successful run (preview, apply, and the
zero case):

```json
{"candidates": 143, "deleted": 143, "cutoff": "2024-09-09T05:00:12"}
```

| Key | Type | Meaning |
|---|---|---|
| `candidates` | int | rows with `occurred_at < cutoff` at the moment of the count |
| `deleted` | int | rows actually removed; **always `0` in dry-run** |
| `cutoff` | string | the effective cutoff, ISO-8601, naive UTC, no `Z` suffix (it is not offset-aware) |

Three keys, nothing else. No database identity, no host, no per-club or per-entity
breakdown — those are operator context and belong in the log, not in a payload another job
parses. Nothing is printed to stdout on a failing run (§2.5), so a consumer must use
`set -o pipefail` and check the exit code before parsing.

### 2.4 stderr — the operator log

`_emit(label, msg)` with the timestamp prefix of `retention_ai_insights.py:62-65`, but
writing to **stderr** (`typer.echo(..., err=True)`) so that stdout stays a clean JSON
channel for §2.3. This is the one deliberate deviation from the precedent script, and it
is what lets the workflow do `... > preview.json` and still show a readable log.

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

With `--apply`, the last two lines become:

```text
[2026-09-09T05:00:14Z] DONE    143 filas eliminadas; registro de purga creado (club_id=1, removed_count=143)
[2026-09-09T05:00:14Z] EXIT    candidates=143 deleted=143 apply=true
```

Zero case:

```text
[2026-09-09T05:00:13Z] OK      0 filas anteriores al cutoff. No hay nada que purgar.
```

Copy is español neutro with full diacritics (spec.md:286 — "all new product copy … in
español neutro (Colombia) with full diacritics"), unlike the un-accented precedent script.
The JSON **keys** stay English: they are a machine contract, not copy.

### 2.5 Exit codes

| Code | When | stdout |
|---|---|---|
| `0` | preview or apply completed (including the zero case) | the JSON of §2.3 |
| `1` | DB connection failure, validation refusal (§2.6), or any unhandled exception — `_emit("ERROR", f"{type(exc).__name__}: {exc}")` then `raise typer.Exit(code=1)`, as `retention_ai_insights.py:147-157` | nothing |
| `2` | Typer/Click argument error (unknown `--actor-kind`, `--months 0`) | nothing |

`KeyboardInterrupt` → `_emit("ABORT", …)` and exit `1`, before any commit.

### 2.6 Refusals

| Condition | Message (stderr, `ERROR`) | Exit |
|---|---|---|
| URL scheme is not `mysql+aiomysql://` or `sqlite+aiosqlite://` | `--database-url debe usar un driver async: 'mysql+aiomysql://' o 'sqlite+aiosqlite://'.` | 1 |
| No URL supplied and `Settings()` cannot be constructed | `No se pudo resolver la base de datos. Define AUDIT_RETENTION_DATABASE_URL o corre desde backend/ con .env.` | 1 |
| `--cutoff` is not parseable ISO-8601 | `--cutoff debe ser una marca de tiempo ISO-8601 en UTC (ej. 2024-09-09T05:00:12).` | 1 |
| `--cutoff` is in the future | `El cutoff solicitado está en el futuro. Se cancela la purga.` | 1 |
| `--cutoff` is **newer** than `now − months` | `El cutoff solicitado (…) está dentro de la ventana de retención de 24 meses. Se cancela la purga.` | 1 |

The last rule is what protects the handover of §3.3: a fat-fingered or stale `--cutoff`
dispatched by hand can only ever move the boundary **further into the past**, never into
live data. It is deliberately checked against `--months`, not against a hardcoded 24, so a
debugging `--months 3 --cutoff <4 months ago>` still works on a local database while the
workflow — which never passes `--months` — is pinned to the 24-month floor.

A refusal happens **before** any engine is created, so an invalid invocation never opens a
connection to production.

---

## 3. Schedule — `.github/workflows/audit-retention.yml` (new)

Modelled on `.github/workflows/strava-reconcile.yml:1-25` (the project's only "act on
production on a schedule" precedent: cron + `workflow_dispatch` + a named secret + a job
timeout) and on `.github/workflows/race-eval.yml:36-49` for the Python setup. It replaces
the "to be defined" placeholder of `docs/10-race-results/runbook-v2.md:136-150` option A.

### 3.1 Triggers, jobs and the guarantee

| Job | Runs on | Guard | Effect |
|---|---|---|---|
| `preview` | monthly `schedule` **and** every `workflow_dispatch` | none | Always runs `--dry-run`. Publishes `candidates` and `cutoff` as job outputs. Never touches data. |
| `apply` | `workflow_dispatch` only | `needs: preview` **and** `github.event_name == 'workflow_dispatch'` **and** `github.event.inputs.confirm == 'true'` | Runs `--apply --cutoff <preview output> --actor-kind cron`. |

The guarantee FR-030 asks for — "previews the count to remove, removes only on explicit
confirmation" — is structural: `apply` cannot start before `preview` has finished and
printed its count into the same run's log, and the scheduled path has no way to reach
`apply` at all.

### 3.2 The file

```yaml
name: Audit Retention

# Purga de `audit_log` a 24 meses (FR-030 / specs/041-multi-coach-governance).
# Job 1 (preview) corre siempre — mensual y en cada dispatch — y NO toca datos.
# Job 2 (apply) sólo corre en dispatch manual con confirm=true, reusando el
# cutoff que el preview ya publicó.
# Runbook: docs/19-multi-coach-governance/runbook.md §5.

on:
  schedule:
    - cron: "0 5 1 * *"        # día 1 de cada mes, 05:00 UTC (00:00 Colombia)
  workflow_dispatch:
    inputs:
      confirm:
        description: 'Escribe exactamente "true" para EJECUTAR la purga. Cualquier otro valor sólo simula.'
        required: true
        default: "false"
        type: string

jobs:
  preview:
    name: Preview (dry-run)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    defaults:
      run:
        working-directory: backend
    outputs:
      cutoff: ${{ steps.run.outputs.cutoff }}
      candidates: ${{ steps.run.outputs.candidates }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - name: Install backend deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Preview purge
        id: run
        env:
          AUDIT_RETENTION_DATABASE_URL: ${{ secrets.AUDIT_RETENTION_DATABASE_URL }}
        run: |
          set -euo pipefail
          if [ -z "${AUDIT_RETENTION_DATABASE_URL:-}" ]; then
            echo "::error::AUDIT_RETENTION_DATABASE_URL no configurado en secrets del repo."
            exit 1
          fi
          python -m scripts.retention_audit_log --dry-run > preview.json
          cat preview.json
          echo "cutoff=$(jq -r .cutoff preview.json)" >> "$GITHUB_OUTPUT"
          echo "candidates=$(jq -r .candidates preview.json)" >> "$GITHUB_OUTPUT"
      - name: Summary
        run: |
          echo "### Purga de audit_log — simulación" >> "$GITHUB_STEP_SUMMARY"
          echo "- cutoff: \`${{ steps.run.outputs.cutoff }}\`" >> "$GITHUB_STEP_SUMMARY"
          echo "- candidatos: **${{ steps.run.outputs.candidates }}**" >> "$GITHUB_STEP_SUMMARY"

  apply:
    name: Apply purge (manual, confirm=true)
    needs: preview
    if: github.event_name == 'workflow_dispatch' && github.event.inputs.confirm == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    environment: production          # OBLIGATORIO: exige revisor en Settings → Environments (§4.1 A3)
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - name: Install backend deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Apply purge
        env:
          AUDIT_RETENTION_DATABASE_URL: ${{ secrets.AUDIT_RETENTION_DATABASE_URL }}
          CUTOFF: ${{ needs.preview.outputs.cutoff }}
        run: |
          set -euo pipefail
          # Segunda barrera, en el shell: el `if:` del job ya filtró, pero un
          # cambio futuro en la expresión no debe poder borrar datos en silencio.
          # Mismo estilo de guard in-shell que race-eval.yml:96-99.
          if [ "${{ github.event.inputs.confirm }}" != "true" ]; then
            echo "::error::confirm != true — se aborta la purga."
            exit 1
          fi
          if [ -z "${CUTOFF:-}" ]; then
            echo "::error::El job preview no publicó un cutoff."
            exit 1
          fi
          python -m scripts.retention_audit_log \
            --apply --cutoff "$CUTOFF" --actor-kind cron > applied.json
          cat applied.json
```

`pip install -r requirements.txt` is deliberately the whole file rather than a hand-picked
subset (`typer[all]` lives at `backend/requirements.txt:32` and is **not** in
`pyproject.toml`'s `dependencies`, so `pip install -e .` alone would not install the CLI's
own runtime). A curated subset drifts silently the day `services/retention.py` grows an
import; `cache: pip` makes the cost irrelevant for a monthly job.

### 3.3 The cutoff handover

`preview` writes `cutoff` to `$GITHUB_OUTPUT`; `apply` reads it through
`needs.preview.outputs.cutoff` and passes it as `--cutoff`. This is the mechanism
`data-model.md` §1.3 requires ("computed once in the preview step and passed verbatim to
the confirm step"). Without it the two jobs would each call `now()` minutes apart and
delete a set the operator never saw counted — the failure §1.2's stability argument exists
to rule out.

### 3.4 Secrets and variables, by name

| Name | Kind | Where it must also exist | Notes |
|---|---|---|---|
| `AUDIT_RETENTION_DATABASE_URL` | GitHub repository secret (Settings → Secrets and variables → Actions) | nowhere else — it is **not** a Render env var | A full async SQLAlchemy URL (`mysql+aiomysql://…`). Job-scoped on purpose: not the app's `DATABASE_URL`, so the credential inside it can be a dedicated, least-privileged MySQL account. |

Never referenced by value anywhere — not in this contract, not in the runbook, not in a
log line, not in a commit message. `.env` and `.env.production` remain the only places the
production credentials live, and they stay gitignored.

**Least-privilege recommendation** (operator decision, not enforced by this contract): give
the workflow its own MySQL user with `SELECT, INSERT, DELETE` on `audit_log` **only**, and
no privilege on any other table. That is a strictly smaller blast radius than reusing the
application account, and it is the natural first half of the DB-level hardening
`data-model.md` §1.2 item 5 defers (the second half — revoking `UPDATE`/`DELETE` on
`audit_log` from the *application's* user — becomes possible the moment a second MySQL
account exists on the Hostinger plan).

### 3.5 Precondition — network reachability

Hostinger Shared plans allowlist MySQL clients by IP
(`docs/10-race-results/runbook-ops.md:33-35`, restated for this stack in
`docs/16-strava-sync/runbook-ops.md:222-227`). GitHub-hosted runners draw from a large,
rotating public range, so a per-IP allowlist entry is not workable. Before enabling the
schedule, one of these must be true, in order of preference:

1. Remote MySQL access is opened for the dedicated retention user from any host
   (hPanel → MySQL Remote), accepting that the mitigation is the account's
   `audit_log`-only grant plus a strong password (§3.4).
2. The workflow runs on a self-hosted runner with a stable outgoing IP that is
   allowlisted.
3. The schedule stays disabled and the purge is run by hand from the maintainer's machine
   once a year (`--apply`, same CLI, same cutoff rules), logged in the runbook. Acceptable
   because 24-month retention has an annual, not monthly, urgency and the table is
   ≈16 000 rows at steady state (`data-model.md` §9).

Option 3 is the honest default until option 1 is granted; the workflow file ships either
way, since the scheduled job is a harmless dry-run that simply fails to connect.

---

## 4. Alternative considered and rejected — a protected admin endpoint

`docs/10-race-results/runbook-v2.md:152-157` lists "protected admin endpoint (RBAC admin)
triggered from an external cron" as option B for the sibling retention job. For
`audit_log` it is **rejected**:

- **It does not remove the external trigger.** Render's free tier has no scheduler and no
  worker process (`plan.md` Constraints; spec.md:284), so an endpoint still needs GitHub
  Actions — or cron-job.org — to call it. The endpoint buys no scheduling; it only moves
  where the code runs.
- **It adds an internet-reachable destructive surface.** The endpoint would be the single
  HTTP route in the product capable of removing audit evidence — precisely the evidence
  Ley 1581 and FR-004 exist to protect. A shared-secret header or an RBAC check is a
  weaker control than "the code path is not reachable over the network at all".
- **It weakens the FR-004 proof.** The grep test of §5.2 can assert that no module under
  `backend/app/` deletes from `audit_log` except `app/services/retention.py`. Wiring a
  router to that service keeps the assertion true but makes the invariant depend on an
  RBAC dependency rather than on unreachability.
- **The preview/confirm shape would have to be re-invented in HTTP** (two calls, a
  server-side pending-cutoff token or a client-supplied one) for no gain over two CI jobs.

Recorded, not adopted: exposing an **admin-only, read-only** preview
(`GET /api/admin/retention/audit-log/preview`, returning `{candidates, cutoff}`) would be
safe and would let an administrator see the pending count from the app. FR-030 does not
require it and no user story asks for the screen, so it stays out of scope; if it is ever
added it must call `preview_purge` and nothing else.

The remaining alternatives are dismissed by `research.md` R-25 and are not re-litigated
here: a `--dry-run` flag with a destructive default, and automatic deletion with no
preview.

### 4.1 How FR-030's "restricted to administrators" is discharged

Rejecting the endpoint removes the only place a runtime `403` could live, so the
restriction is met **by construction rather than by a check**. FR-030's clause and the
spec's edge case *"The purge preview is run by someone without administrator rights:
refused"* (spec.md:178) are satisfied by four controls, none of which is code on this
application's request path:

| # | Control | What it stops | Configured at |
|---|---|---|---|
| A1 | **No network-reachable path.** Neither `preview_purge` nor `apply_purge` is mounted on a router; the only entry point is `python -m scripts.retention_audit_log` on a machine that already holds a database URL. | A non-administrator cannot reach the code at all — there is no URL to call, with or without a token. | This contract (§4 above), and held by **human review, not by a test**: §5.2's grep still passes for a router that merely *calls* the service, as §4's third bullet already notes. The reviewable signal is the import — a new `from app.services import retention` under `backend/app/routers/`. |
| A2 | **Repository write access gates `workflow_dispatch`.** GitHub offers "Run workflow" only to collaborators with write permission; the monthly `schedule` trigger can reach `preview` and never `apply` (§3.1). | A parent, a coach, or any reader of the repository can neither run the preview nor start the purge. | GitHub → Settings → Collaborators. The write-access set **is** the administrator set for this procedure. |
| A3 | **Required-reviewer gate on `apply`.** The destructive job is pinned to the `production` GitHub Environment with required reviewers, so it waits for a named approver even when it was dispatched with `confirm=true`. | A collaborator with write access who is not an approved operator cannot complete a purge unilaterally. | GitHub → Settings → Environments → `production` → Required reviewers. This is why the `environment:` key of §3.2 is **not** optional. |
| A4 | **Job-scoped credential.** `AUDIT_RETENTION_DATABASE_URL` exists only as an Actions secret exposed to these two jobs, and is deliberately not a Render env var (§3.4). | A local checkout of the repository purges nothing by itself: the operator must also hold a production database credential obtained out of band. | GitHub → Settings → Secrets and variables → Actions. |

**Stated plainly, because §8 would otherwise look incomplete**: the CLI performs **no
authorisation check of its own**, and T1–T15 contain no authorisation case, because there
is nothing in-process to test. `--actor-kind` is a label, not an identity; validating it
would fabricate exactly the attribution §0 refuses to invent. The edge case of
spec.md:178 is therefore recorded as satisfied by *"no non-administrator can trigger the
workflow"* (A2 + A3), **not** by a runtime `403` — and anyone who can invoke the CLI
directly already holds the production credential and could issue the same `DELETE` from a
MySQL client, which an in-CLI role check would not stop.

**The residual risk, named**: A2 and A3 are GitHub account controls, not application
controls, so the restriction is exactly as strong as the repository's collaborator list
and the `production` environment's reviewer list. Keeping both aligned with the club's
real administrator set is an operator duty, recorded in §6 5.5. If a future release wants
the restriction expressed in application code, the admin-only **read-only** preview
sketched above is the intended shape; the destructive half stays out of HTTP.

---

## 5. Append-only invariant (FR-004) — the automated proof

### 5.1 Rule

> The application never issues `UPDATE` or `DELETE` against `audit_log`. The single
> exception is `backend/app/services/retention.py`, which implements FR-030.

Restates `data-model.md` §1.2 items 3–4. Two tests enforce it, plus one behavioural check.
Both live in `backend/tests/test_audit_append_only.py`.

### 5.2 The static (grep) test

Scans source text, so it fails at merge time even for a code path no test exercises — the
merge-time requirement of the spec's edge case "a record type is added in the future
without being wired to the history" (spec.md:177), applied to its mirror image.

**Roots scanned**: every `*.py` under `backend/app/` and `backend/scripts/`.
**Exempt**: `backend/app/services/retention.py`, `backend/scripts/retention_audit_log.py`.
**Not scanned**: `backend/alembic/versions/` (a `downgrade()` legitimately drops the
table) and `backend/tests/` (fixtures need to reset state).

Path resolution uses the by-path idiom already in the suite —
`Path(__file__).resolve().parents[1]` from `backend/tests/` is `backend/`, the same
construction as
`backend/tests/models/test_newsletter_content_version_removal_migration.py:24-30`.

| # | Pattern | Catches |
|---|---|---|
| P1 | `\bdelete\s*\(\s*AuditLog\b` | `sa.delete(AuditLog)` |
| P2 | `\bupdate\s*\(\s*AuditLog\b` | `sa.update(AuditLog)` |
| P3 | `(?i)\.delete\(\s*\w*audit\w*\s*\)` | `await db.delete(audit_row)` / `session.delete(audit_entry)` |
| P4 | ``(?i)\b(delete\s+from\|update)\s+`?audit_log`?\b`` | raw SQL inside `text("…")` |
| P5 | `\bAuditLog\b.*\.(delete\|update)\(` on one line | fluent misuse |

The failure message lists `path:line` for every hit and names the exemption, so a future
author who genuinely needs a second exception has to edit the test and therefore has to
justify it in review — which is the point.

Known limits, accepted (same posture as `data-model.md` §8.4): the scan is textual, so an
alias (`from app.models.audit_log import AuditLog as AL`) or a fully dynamic
`sa.table("audit_log")` slips through. The behavioural test of §5.4 and the human review
gate of the constitution are the backstops; a DB-level trigger or grant is the real fix and
is deferred with a written reason in `data-model.md` §1.2 item 5.

### 5.3 The model test

Asserts the shape that makes an accidental update impossible, rather than the absence of a
call:

| # | Assertion |
|---|---|
| M1 | `set(AuditLog.__table__.columns.keys())` contains no `updated_at`, `updated_by_user_id`, `modified_at`, `deleted_at` |
| M2 | No column on `AuditLog.__table__` has a non-`None` `onupdate` or `server_onupdate` |
| M3 | Every relationship on `inspect(AuditLog).relationships` has `viewonly is True` (so no cascade can write through `actor`, `club` or `athlete`) |
| M4 | `AuditLog` does not inherit `ActorTimestampMixin` (`data-model.md` §5) — `issubclass` check |
| M5 | The `actor_user_id` foreign key has `ondelete == "RESTRICT"`, so an actor's name stays resolvable forever (FR-013 / FR-018) |
| M6 | `occurred_at` and `id` are `nullable=False` and `occurred_at` carries the MySQL `DATETIME(fsp=6)` variant (`data-model.md` §1) |

### 5.4 The behavioural check

Runs a realistic multi-action scenario against the offline app (two coaches, one club),
snapshots `(id, occurred_at, entity_type, action, diff_json)` for every row, runs a second
batch of actions including an athlete archive and a newsletter approval, and asserts the
first snapshot is present **unchanged and complete** in the second read — rows were only
appended. Then runs `apply_purge` with a cutoff older than everything and asserts the
snapshot is *still* unchanged (nothing is old enough), proving the purge is bounded by its
cutoff and not by its existence.

---

## 6. Runbook — `docs/19-multi-coach-governance/runbook.md` §5 (new)

English, per the instruction-corpus language rule (`docs/**`). Structure mirrors
`docs/10-race-results/runbook-v2.md:92-183` §3, which is the reference an operator already
knows. The CLI docstring ends with a pointer to it, exactly as
`backend/scripts/retention_ai_insights.py:43` does.

Required content:

| § | Content |
|---|---|
| 5.1 Policy | 24 months on `occurred_at`; nothing inside the app removes a row; the purge is itself audited; the purge row ages out like any other row and the GitHub Actions run log is the durable external record. |
| 5.2 Preview | The command, the expected JSON, how to read the `ROW` breakdown, and the statement that a preview is always safe to run against production. |
| 5.3 Apply | The command; the requirement to reuse the cutoff from the preview; the fact that `--months` must never be lowered against production. |
| 5.4 Scheduled run | How to trigger the workflow (Actions tab → "Audit Retention" → Run workflow → `confirm = true`), where the count appears (job summary of `preview`), and how to read the `apply` log. |
| 5.5 Secret and access | `AUDIT_RETENTION_DATABASE_URL` — by name only, never by value; the least-privilege grant recommendation of §3.4; the Hostinger remote-access precondition of §3.5 with a link to `docs/10-race-results/runbook-ops.md` §1.2. Plus the access-control substitution of §4.1: FR-030's "restricted to administrators" is held by the repository's write-access list (A2) and the `production` environment's required-reviewer list (A3), so **both lists MUST be re-checked at every staff change** and MUST match the club's real administrator set. There is no in-app permission to grant or revoke here. |
| 5.6 Post-run validation | The two SQL checks below. |
| 5.7 Failure modes | Table: connection refused (IP allowlist) → §3.5; `candidates` unexpectedly large (first run after two seasons — expected, ≈8 000 rows/year per `data-model.md` §9); `apply` skipped (confirm ≠ `true`); non-zero `candidates` after a successful apply (a row was written between preview and apply with an older `occurred_at` — impossible by §1.2, so investigate a clock or a manual insert). |

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

The runbook must also state the one thing an operator can get wrong that this contract
cannot prevent: running the CLI against the **wrong database**. The mitigation is that the
URL comes from a single job-scoped secret and that the log prints `host/database` on every
run (§2.4) — the operator is expected to read that line before confirming.

---

## 7. Performance and volume

- Steady state is ≈16 000 rows (≈8 000/year over 24 months, `data-model.md` §9), so the
  first real purge removes ≈8 000 rows and every subsequent monthly run removes ≈650.
- `occurred_at` is **deliberately not indexed** (`data-model.md` §1.1): the purge is the
  only query that filters on it without a club, it runs monthly, and a sixth index on a
  write-hot table is not worth paying for. The `COUNT(*)` and the `DELETE` are full scans
  of a ≈16 MB table — milliseconds on Hostinger, and off the request path entirely, so the
  p95 budgets of Principle IV do not apply.
- **No batching.** One `DELETE` statement, one transaction. Chunking would either break the
  atomicity of "delete + record the purge" or require committing mid-way, leaving a window
  where rows are gone and no purge row exists. `data-model.md` §9 already names the trigger
  for revisiting this: if the table ever passes ~1 M rows, add `ix_audit_occurred_at`
  first, and only then consider a `--batch-size` loop.
- The job holds no MySQL connection outside its own run and uses `pool_pre_ping=True`,
  so it cannot contribute to the `max_connections_per_hour` ceiling that motivated the
  pooling comments in `backend/app/database.py:11-26`.

---

## 8. Required tests

### 8.1 `backend/tests/test_retention.py` (new) — service + CLI

Offline lane. Harness: a `sqlite+aiosqlite:///:memory:` engine with `StaticPool` created
per test and `Base.metadata.create_all` restricted to the tables needed
(`audit_log`, `users`, `clubs`), following
`backend/tests/test_password_reset_privacy.py:32-45`. Seeded rows are audit rows only — no
athlete fixture, no names, no birth dates.

| # | Test | Asserts |
|---|---|---|
| T1 | **Preview deletes nothing** — seed rows at 25 and 23 months, call `preview_purge` | `candidates == 1`; the row count in the table is unchanged; `by_entity_type` sums to `candidates`; no row with `action='purge'` exists. This is US8 AS1 and half of SC-010. |
| T2 | **Apply removes only what is older than the cutoff** | after `apply_purge` + commit: the 25-month row is gone, the 23-month row is present, `deleted == 1`. |
| T3 | **Boundary is strict `<`** — a row whose `occurred_at` equals the cutoff to the microsecond | survives the purge. |
| T4 | **The purge is recorded** | exactly one new row with `action='purge'`, `entity_type='audit_log'`, `entity_id == 0`, `actor_user_id is None`, `actor_kind in {system, cron}`, `reason_code == 'retention_24m'`, `meta_json == {"removed_count": 1, "cutoff": <iso>, "job": "audit_retention"}`; its `occurred_at` is greater than the cutoff, so it is not self-deleted. US8 AS2. |
| T5 | **One purge row per club** — seed old rows for club 1, club 2 and one with `club_id IS NULL` | three purge rows, each with its own `removed_count`, all sharing one `request_id`. |
| T6 | **Zero case writes nothing** — nothing older than the cutoff | `deleted == 0`, no purge row, table byte-identical. §1.5. |
| T7 | **Idempotent** — run `apply_purge` twice with the same cutoff | second run: `candidates == 0`, `deleted == 0`, still exactly one purge row from the first run. |
| T8 | **Atomicity** — force an exception between the `DELETE` and the commit | rollback leaves both the rows and the absence of the purge row, i.e. nothing happened. |
| T9 | **`retention_cutoff` calendar arithmetic** — parametrised: `2026-03-31 − 1 month → 2026-02-28`; `2028-02-29` leap handling; `2026-09-09 − 24 months → 2024-09-09` | pure-function assertions, no DB. |
| T10 | **CLI dry-run is the default** — invoke via `typer.testing.CliRunner` with no flags | exit 0; stdout parses as JSON with `deleted == 0`; the table is unchanged. |
| T11 | **CLI JSON contract** | stdout is exactly one line; `json.loads` yields exactly the keys `{"candidates", "deleted", "cutoff"}`; `cutoff` round-trips through `datetime.fromisoformat`. |
| T12 | **CLI never prints the URL** — run with a URL containing a password-shaped token | that token appears nowhere in stdout or stderr. Privacy invariant, sibling of the constitution's "no credential in logs" gate. |
| T13 | **`--cutoff` inside the retention window is refused** | exit 1, no connection opened, message names the window; and a future `--cutoff` is refused the same way. §2.6. |
| T14 | **Non-async URL is refused** | `mysql+pymysql://…` → exit 1 with the driver message, before any engine is created. |
| T15 | **`--cutoff` wins over `--months`** and the effective value appears in the JSON. |

### 8.2 `backend/tests/test_audit_append_only.py` (new) — FR-004

| # | Test | Asserts |
|---|---|---|
| T16 | **Grep test** | patterns P1–P5 of §5.2 over `backend/app/**/*.py` and `backend/scripts/**/*.py` produce zero hits outside the two exempt files; failure output lists `path:line`. |
| T17 | **Grep test self-check** | the exempt `app/services/retention.py` *does* match P1 — otherwise the test would pass vacuously if the service were ever renamed or emptied. |
| T18 | **Model test** | M1–M6 of §5.3. |
| T19 | **Behavioural append-only** | §5.4: the snapshot of every row survives a second batch of actions unchanged; US8 AS3 and the second half of SC-010. |

### 8.3 `mysql` lane (`pytest -m mysql`, DB name must end in `_test` — enforced by `backend/tests/conftest.py:44-53`)

| # | Test | Asserts |
|---|---|---|
| T20 | **Microsecond boundary survives MySQL** | two rows one microsecond apart across the cutoff: the older is deleted, the newer kept. This is the test that would have caught the `fsp=0` truncation `data-model.md` §1 warns about; it is meaningless on SQLite, which is why it belongs to this lane. |
| T21 | **The `DELETE` plan is acceptable** | `EXPLAIN DELETE FROM audit_log WHERE occurred_at < ?` on a seeded table completes and the test records the access type in the assertion message — documenting the accepted full scan of §7 rather than asserting an index that deliberately does not exist. |

### 8.4 Not covered here

The privacy scan of the purge row's `meta_json` belongs to
`backend/tests/test_audit_privacy.py` (`data-model.md` §2.5) — it scans **every** produced
row, including these, so duplicating it here would be a second copy to keep in sync. The
rendering of the purge sentence is covered by `contracts/audit-log-api.md` §7.5. The
GitHub Actions workflow itself has no automated test; its first scheduled dry-run against
production is the smoke check, and it is listed in the feature's post-deploy checklist.

**No authorisation test exists, deliberately.** FR-030's "restricted to administrators"
and the edge case of spec.md:178 are discharged by §4.1's A1–A4 — repository write
access, a required-reviewer environment, a job-scoped secret and the absence of any
network-reachable path — none of which is in-process behaviour a `pytest` case could
exercise. Adding one would only assert that a flag the caller chose has the value the
caller gave it. The controls are verified by inspecting two GitHub settings pages, which
§6 5.5 makes a recurring operator duty rather than a one-off.
