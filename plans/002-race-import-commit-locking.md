# Plan 002: Serialize race-import commits — row lock on the pending import to eliminate the double-submit IntegrityError

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 9871c99..HEAD -- backend/app/routers/race_imports.py backend/app/services/race/ingestor.py backend/tests/routers/test_race_imports.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S–M
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `9871c99`, 2026-06-11

## Why this matters

Committing a race-results import is check-then-act today: the router loads the
`RaceImport` row, checks `status == pending`, then runs a multi-second ingest
(downloads PDFs from FTPS, parses, inserts `race_results`). Two concurrent
commits of the same import — a coach double-clicking the commit button on a
slow connection is enough — both pass the status check and both ingest. The
second one then violates the `race_result` UNIQUE constraint
(`event_id, category_id, competitor_id`), crashes with an `IntegrityError`
mid-transaction, and surfaces as a 500 with the import in an ambiguous state.
A `SELECT ... FOR UPDATE` on the import row serializes commits: the second
request waits, re-reads `status = committed`, and gets a clean 404/409.

## Current state

- `backend/app/routers/race_imports.py`:
  - `_load_pending_import` (lines 595–625) — shared loader used by BOTH
    `POST /{parse_id}/dry-run` (line 761) and `POST /{parse_id}/commit`
    (line 913). It does a plain SELECT with no lock:

    ```python
    # backend/app/routers/race_imports.py:595-615 (abridged)
    async def _load_pending_import(
        db: AsyncSession, parse_id: int, current_user: User
    ) -> RaceImport:
        """Carga un RaceImport pending por id + verifica ownership (admin bypass)."""
        result = await db.execute(
            select(RaceImport).where(RaceImport.id == parse_id)
        )
        imp = result.scalar_one_or_none()
        if imp is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, ...)
        if imp.status != RaceImportStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"parse_id={parse_id} no está en estado pending "
                    f"(actual: {imp.status.value}). No se puede dry-run/commit."
                ),
            )
        # ... ownership check (admin bypass; coach solo sus propios parses)
    ```

  - `commit_import` (line 905–913) calls
    `imp = await _load_pending_import(db, parse_id, current_user)` and later
    `await ingestor.ingest_event(...)` which commits internally, then
    `await db.refresh(imp)` (line 988).

- `backend/app/services/race/ingestor.py` — per category, duplicate detection
  is a snapshot taken before the row loop:

  ```python
  # backend/app/services/race/ingestor.py:319-323
  # Index de race_results existentes para idempotencia por UNIQUE
  # (no consultamos en el loop por performance; un solo select por categoría)
  existing_pairs = await self._existing_competitor_ids_for(
      event_id=event.id, category_id=category.id
  )
  ```

  and `self.db.add(race_result)` at line 397 with `existing_pairs.add(...)` at
  line 400 defending only against duplicates *within the same PDF*. The
  cross-request race is what this plan fixes — at the router, not here.

- **Critical nuance**: dry-run must NOT take the lock. Dry-run also goes
  through `_load_pending_import`, and both dry-run and commit hold the DB
  session open across FTPS download + PDF parsing (seconds, up to the 30s
  parse timeout). Locking on dry-run would let a stuck dry-run block a commit.
  Commit-only locking is the design.

- MySQL (prod, aiomysql) honors `FOR UPDATE`. SQLite (tests, aiosqlite)
  parses and ignores it — so tests verify plumbing and behavior, not actual
  lock contention. That is acceptable; note it in the test docstring.

- Test conventions: `backend/tests/routers/test_race_imports.py` is the
  existing suite for this router — follow its fixture style (it builds an
  aiosqlite engine and overrides `get_db` / `get_current_user` dependencies).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Setup venv + deps | `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -e ".[dev]" aiosqlite` | exit 0 |
| Router suite | `cd backend && .venv/bin/python -m pytest tests/routers/test_race_imports.py -q` | all pass |
| Full backend suite | `cd backend && .venv/bin/python -m pytest -q` | all pass |

## Scope

**In scope** (the only files you should modify):
- `backend/app/routers/race_imports.py`
- `backend/tests/routers/test_race_imports.py` (add tests)
- `plans/README.md` (status row)

**Out of scope** (do NOT touch, even though they look related):
- `backend/app/services/race/ingestor.py` — the in-PDF dedup logic is correct;
  the race is serialized at the router. Do not add IntegrityError swallowing
  inside the ingestor (it would mask real data bugs).
- `backend/app/models/race_import.py` / migrations — no schema change.
- The dry-run endpoint's locking behavior (must remain lock-free).

## Git workflow

- Branch: follow operator instructions; if none, `advisor/002-race-import-commit-locking`.
- Conventional commits, e.g. `fix(race): serializa commits de import con SELECT FOR UPDATE (doble submit)`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add an opt-in lock to `_load_pending_import`

Change the signature to:

```python
async def _load_pending_import(
    db: AsyncSession,
    parse_id: int,
    current_user: User,
    *,
    for_update: bool = False,
) -> RaceImport:
```

and build the statement conditionally:

```python
stmt = select(RaceImport).where(RaceImport.id == parse_id)
if for_update:
    # Serializa commits concurrentes del mismo parse_id (MySQL InnoDB).
    # SQLite (tests) ignora FOR UPDATE — no-op inofensivo.
    stmt = stmt.with_for_update()
result = await db.execute(stmt)
```

Everything else in the function (404 on missing, 404 on non-pending,
403 ownership) stays byte-identical.

**Verify**: `cd backend && .venv/bin/python -m pytest tests/routers/test_race_imports.py -q` → all pass (no behavior change yet).

### Step 2: Use the lock in commit only

In `commit_import` (line ~913), change the call to:

```python
imp = await _load_pending_import(db, parse_id, current_user, for_update=True)
```

Leave the dry-run call site (line ~761) untouched.

**Verify**: `grep -n "for_update=True" backend/app/routers/race_imports.py` → exactly 1 match, inside `commit_import`.

### Step 3: Convert the "no longer pending" rejection into the correct status code for commit

When the second, previously-blocked commit acquires the lock, it re-reads the
row and `status` is now `committed`; `_load_pending_import` raises 404 with
"no está en estado pending". Semantically for a commit double-submit this is a
conflict, not a missing resource. Add `conflict_status: bool = False`? No —
keep it minimal: leave the 404 as-is. (It is the established contract; the
frontend already handles it, and dry-run shares the message.) This step is a
decision record, not a code change. Do nothing.

### Step 4: Defense-in-depth — catch `IntegrityError` at the commit endpoint

Even with the lock, an IntegrityError could still escape (e.g. two commits of
*different* imports for the same event/categories). In `commit_import`, wrap
the `await ingestor.ingest_event(...)` call:

```python
from sqlalchemy.exc import IntegrityError  # add to existing imports at top

try:
    report = await ingestor.ingest_event(...)  # existing call, unchanged args
except IntegrityError:
    await db.rollback()
    logger.warning(
        "race_import_commit integrity_conflict parse_id=%s", parse_id
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Los resultados de este evento ya fueron registrados por otra "
            "operación. Refresca la página para ver el estado actual."
        ),
    )
```

Keep the existing post-ingest code (refresh, SFTP moves, response building)
outside the `try` — only the ingest call is wrapped.

**Verify**: `cd backend && .venv/bin/python -m pytest tests/routers/test_race_imports.py -q` → all pass.

### Step 5: Tests

In `backend/tests/routers/test_race_imports.py`, following the file's existing
fixture/override style, add:

1. `test_commit_locks_import_row` — patch/spy the select to assert the commit
   path issues a `FOR UPDATE` statement. Practical approach on SQLite: register
   an event listener on the sync engine
   (`sa_event.listens_for(engine.sync_engine, "before_cursor_execute")`),
   collect SQL strings during the commit request, and assert one contains
   `FOR UPDATE` targeting `race_imports`. (See
   `tests/routers/test_race_standings_read.py` for an existing
   query-capturing listener to model after.)
2. `test_dry_run_does_not_lock` — same listener over the dry-run request;
   assert NO captured statement contains `FOR UPDATE`.
3. `test_commit_integrity_error_returns_409` — monkeypatch
   `RaceIngestor.ingest_event` to raise
   `sqlalchemy.exc.IntegrityError("stmt", {}, Exception("dup"))`; assert
   response is 409 and the detail is the Spanish conflict message.
4. `test_second_commit_after_committed_is_rejected` — commit once (happy
   path), commit again; assert 404 with "no está en estado pending" (existing
   contract preserved).

**Verify**: `cd backend && .venv/bin/python -m pytest tests/routers/test_race_imports.py -q` → all pass, including 4 new tests.

## Test plan

Covered in Step 5. Structural patterns: fixtures in
`tests/routers/test_race_imports.py` itself; SQL-capturing listener from
`tests/routers/test_race_standings_read.py`. Note in each new test's docstring
that SQLite ignores `FOR UPDATE`, so the lock's *contention* behavior is
exercised only in production MySQL (see plan 005 for the MySQL test lane).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd backend && .venv/bin/python -m pytest -q` exits 0
- [ ] `grep -n "with_for_update" backend/app/routers/race_imports.py` → ≥1 match
- [ ] `grep -n "for_update=True" backend/app/routers/race_imports.py` → exactly 1 match (commit path)
- [ ] `grep -n "IntegrityError" backend/app/routers/race_imports.py` → ≥2 matches (import + handler)
- [ ] 4 new tests from Step 5 exist and pass
- [ ] `git status` shows no modified files outside the in-scope list
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `_load_pending_import` or `commit_import` no longer match the "Current
  state" excerpts (drift).
- You find the ingestor opens its own session/transaction separate from the
  router's `db` (the lock would then not protect the ingest) — report; the fix
  design changes.
- The existing test suite fails on `with_for_update()` under aiosqlite
  (unexpected dialect error) — report rather than stripping the lock.

## Maintenance notes

- If commit work ever moves to a background queue, the FOR UPDATE lock scope
  ends when the request's transaction does — the serialization guarantee must
  be re-established in the worker.
- Reviewer focus: confirm dry-run path remains lock-free and that the
  `IntegrityError` handler does not swallow errors from the post-ingest code.
- Deferred on purpose: per-row `ON DUPLICATE KEY` upserts in the ingestor
  (MySQL-only syntax, complicates the SQLite test lane, and the router lock
  already closes the observed race).
