# Plan 003: Make password-reset token consumption atomic (single-use under concurrency)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 9871c99..HEAD -- backend/app/services/password_reset.py backend/tests/services/test_password_reset_service.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `9871c99`, 2026-06-11

## Why this matters

`consume_token()` validates the token (checks `used_at IS NULL` and expiry)
and only *afterwards* marks it used. Two concurrent requests with the same
token — a double-clicked confirm button, or an attacker racing a victim's
click — both pass validation and both update the password. Impact is modest
(both requests carry the same token, and whoever has the token can reset
anyway), but single-use enforcement is the OWASP norm for reset tokens and the
fix is a few lines: claim the token with an atomic conditional UPDATE before
touching the password.

## Current state

- `backend/app/services/password_reset.py`:
  - `_now()` (line 38) — tz-aware UTC now helper.
  - `validate_token(raw_token, db)` (lines 130–147) — returns the row; raises
    404 if missing, 410 if `row.used_at is not None or expired`.
  - `consume_token` (lines 150–175), the function this plan changes:

    ```python
    # backend/app/services/password_reset.py:150-175
    async def consume_token(
        raw_token: str,
        new_password: str,
        db: AsyncSession,
    ) -> User:
        """Aplica la nueva contraseña y consume el token (un solo uso). ..."""
        row = await validate_token(raw_token, db)

        user = await db.get(User, row.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="El enlace ha expirado o ya fue utilizado. Solicita uno nuevo.",
            )

        user.hashed_password = hash_password(new_password)
        row.used_at = _now()
        await _invalidate_user_tokens(user.id, db)
        await db.flush()
        logger.info("password_reset: contraseña actualizada | user_id=%s", user.id)
        return user
    ```

- Caller: `backend/app/routers/auth.py` — `POST /password-reset/confirm`
  (line 337) calls `password_reset_service.consume_token(...)` (line 349).
  Do not modify the router.

- Existing tests: `backend/tests/services/test_password_reset_service.py`
  (service-level, the structural pattern to follow) and
  `backend/tests/test_password_reset_privacy.py` (logging/privacy invariants —
  must stay green: logs may contain user_id but never email/name/raw token).

- This module is one of the six mutation-tested modules
  (`docs/qa/mutation-testing-2026-06.md`); keep changes minimal and fully
  covered so the mutation score doesn't regress.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Setup venv + deps | `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -e ".[dev]" aiosqlite` | exit 0 |
| Focused tests | `cd backend && .venv/bin/python -m pytest tests/services/test_password_reset_service.py tests/test_password_reset_privacy.py -q` | all pass |
| Full backend suite | `cd backend && .venv/bin/python -m pytest -q` | all pass |

## Scope

**In scope** (the only files you should modify):
- `backend/app/services/password_reset.py` (only `consume_token`)
- `backend/tests/services/test_password_reset_service.py` (add tests)
- `plans/README.md` (status row)

**Out of scope** (do NOT touch, even though they look related):
- `backend/app/routers/auth.py` — contract unchanged (same status codes/messages).
- `validate_token`, `request_reset`, `_invalidate_user_tokens` — unchanged.
- `backend/app/models/password_reset_token.py` / migrations — no schema change.
- Email-change flow in `backend/app/services/profile.py` — different feature,
  already rate-limited.

## Git workflow

- Branch: follow operator instructions; if none, `advisor/003-password-reset-atomic-consume`.
- Conventional commit, e.g. `fix(auth): consumo atómico del token de password reset (un solo uso bajo concurrencia)`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Claim the token atomically before updating the password

In `consume_token`, after `row = await validate_token(raw_token, db)` and
before loading the user, atomically claim the token with a conditional UPDATE
(works identically on MySQL and SQLite):

```python
from sqlalchemy import update  # add to the existing sqlalchemy imports

claim = await db.execute(
    update(PasswordResetToken)
    .where(
        PasswordResetToken.id == row.id,
        PasswordResetToken.used_at.is_(None),
    )
    .values(used_at=_now())
)
if claim.rowcount != 1:
    # Otro request consumió el token entre validate y claim (doble submit).
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="El enlace ha expirado o ya fue utilizado. Solicita uno nuevo.",
    )
```

Then remove the now-redundant `row.used_at = _now()` line. Keep everything
else (user load, `hash_password`, `_invalidate_user_tokens`, `flush`, log)
in the same order. Note: `PasswordResetToken` is already imported in this
module (used by `_get_token_row`); reuse that import.

If the ORM `row` object is reused after the raw UPDATE, its `used_at`
attribute is stale — that's fine; nothing reads it afterwards. Do not add an
extra refresh.

**Verify**: `cd backend && .venv/bin/python -m pytest tests/services/test_password_reset_service.py tests/test_password_reset_privacy.py -q` → all pass.

### Step 2: Tests

Add to `backend/tests/services/test_password_reset_service.py`, following its
existing fixture style:

1. `test_consume_token_is_single_use` — request a reset, consume the token
   once (succeeds), call `consume_token` again with the same raw token →
   `HTTPException` with status 410.
2. `test_consume_claim_race_returns_410` — simulate the interleaving: after
   `validate_token` would pass, set `used_at` directly on the row in the DB
   (emulating the concurrent winner), then call `consume_token` → 410, and
   assert the user's `hashed_password` was NOT changed. Implementation hint:
   monkeypatch `validate_token` in the service module to return the row while
   a pre-step already stamped `used_at` via a direct
   `update(PasswordResetToken)...` — this exercises the `rowcount != 1`
   branch deterministically.
3. `test_consume_success_path_unchanged` — happy path still returns the user,
   password verifies with the new value, sibling tokens invalidated (assert
   `used_at` set on a second outstanding token for the same user).

**Verify**: `cd backend && .venv/bin/python -m pytest tests/services/test_password_reset_service.py -q` → all pass, including 3 new tests.

### Step 3: Full suite

**Verify**: `cd backend && .venv/bin/python -m pytest -q` → all pass.

## Test plan

Covered in Step 2; pattern file `backend/tests/services/test_password_reset_service.py`.
Privacy invariant: new code logs nothing new — the only added branch raises
the same generic 410; `tests/test_password_reset_privacy.py` must stay green.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd backend && .venv/bin/python -m pytest -q` exits 0
- [ ] `grep -n "rowcount" backend/app/services/password_reset.py` → ≥1 match in `consume_token`
- [ ] `grep -n "row.used_at = _now()" backend/app/services/password_reset.py` → no matches
- [ ] 3 new tests exist and pass
- [ ] `git status` shows no modified files outside the in-scope list
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `consume_token` doesn't match the "Current state" excerpt (drift).
- `claim.rowcount` is `-1` or unsupported under aiosqlite in the test run
  (rowcount support differs by driver) — report with the observed value; the
  fallback design (SELECT...FOR UPDATE) needs an advisor decision.
- Any privacy test in `tests/test_password_reset_privacy.py` fails.

## Maintenance notes

- If a "reset link preview" feature is ever added (e.g. email clients
  prefetching the confirm URL via GET), the single-use claim must remain on
  the POST confirm only — never claim on GET.
- Reviewer focus: the claim happens BEFORE `hash_password`/user mutation, and
  the 410 message is byte-identical to the existing one (no enumeration delta).
