# Plan 001: Harden production configuration — fail fast on default JWT secret, warn on CORS wildcard, stop leaking parser exceptions

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 9871c99..HEAD -- backend/app/config.py backend/app/routers/race_imports.py backend/tests/test_ai_config.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `9871c99`, 2026-06-11

## Why this matters

This app stores sensitive data of minors (ages 10–15). Three production
hardening gaps exist today: (1) if the `JWT_SECRET_KEY` env var is ever missed
on a deploy, the app boots with the well-known default `"cambiar-en-produccion"`
and only emits a Python *warning* — every JWT becomes forgeable, which is a
total auth bypass; (2) `CORS_ORIGINS=*` is the documented production default
combined with `allow_credentials=True` — low actual risk today because auth
uses Bearer tokens (not cookies), but it should be loudly flagged until the
frontend ships with a real domain; (3) the race PDF import endpoints return raw
exception class names and messages to the client on parse failure, leaking
internal library/path details. All three fixes follow validation patterns that
already exist in `backend/app/config.py`.

## Current state

- `backend/app/config.py` — pydantic-settings `Settings` class. Field order
  matters: `jwt_secret_key` is declared at line 14, **before** `app_env`
  (line 20). The existing field validator at lines 171–181 therefore CANNOT
  see `app_env` (pydantic field validators only see previously-validated
  fields in `info.data`). It currently only warns:

  ```python
  # backend/app/config.py:171-181
  @field_validator("jwt_secret_key")
  @classmethod
  def validate_jwt_secret(cls, v: str, info) -> str:
      if v == "cambiar-en-produccion":
          import warnings
          warnings.warn(
              "JWT_SECRET_KEY usa valor por defecto. "
              "Generar con: python -c \"import secrets; print(secrets.token_hex(32))\"",
              stacklevel=2,
          )
      return v
  ```

  The file imports only `from pydantic import field_validator` (line 1). It
  already contains hard-fail prod validators to model after, e.g.
  `forbid_ai_log_prompts_in_prod` (lines 229–238) which raises `ValueError`
  when `app_env == "production"`. CORS parsing is the `cors_origin_list`
  property (lines 254–256): splits `cors_origins` (line 22, default
  `"http://localhost:5173"`) on commas.

- `backend/app/routers/race_imports.py` — two exception handlers return the
  raw exception to the client:

  ```python
  # backend/app/routers/race_imports.py:258-262 (inside _parse_resultados_with_timeout)
  except Exception as exc:  # noqa: BLE001
      raise HTTPException(
          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
          detail=f"Error parseando RESULTADOS: {type(exc).__name__}: {exc}",
      )
  ```

  ```python
  # backend/app/routers/race_imports.py:280-284 (inside _parse_general_with_timeout)
  except Exception as exc:  # noqa: BLE001
      raise HTTPException(
          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
          detail=f"Error parseando GENERAL: {type(exc).__name__}: {exc}",
      )
  ```

  The module already has `logger = logging.getLogger(...)` available (it logs
  `race_import_commit move_object failed ...` warnings around line 1003).

- `backend/tests/test_ai_config.py` — the exemplar for config-validator tests.
  It instantiates `Settings(...)` directly with kwargs and uses a
  `_prod_kwargs()` helper (lines 17–26) that supplies
  `app_env="production"`, `jwt_secret_key="0" * 64`,
  `email_provider="resend"`, `resend_api_key="re_xxx"` so prior validators
  pass. **Match this pattern.** Its docstring notes validators run in field
  declaration order — that is exactly why Step 1 uses a model validator, not a
  field validator.

- Repo conventions: backend code comments and user-facing strings are in
  Spanish; error `detail` strings shown to users must stay in **español
  neutro (Colombia)**. Commit style is conventional commits (e.g.
  `fix(security): ...`).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Setup venv + deps | `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -e ".[dev]" aiosqlite` | exit 0 |
| Run config tests | `cd backend && .venv/bin/python -m pytest tests/test_ai_config.py tests/test_security.py -q` | all pass |
| Full backend suite | `cd backend && .venv/bin/python -m pytest -q` | all pass (integration/golden markers are excluded by default) |

(Note: this container had no pre-built venv at planning time; the setup
command above is required once. `aiosqlite` is needed by the test suite and is
not in `requirements.txt`.)

## Scope

**In scope** (the only files you should modify):
- `backend/app/config.py`
- `backend/app/routers/race_imports.py` (ONLY the two `detail=` strings cited above)
- `backend/tests/test_ai_config.py` (add tests) or a new `backend/tests/test_prod_config_hardening.py`
- `plans/README.md` (status row)

**Out of scope** (do NOT touch, even though they look related):
- `.env.production.example`, `CLAUDE.md`, Render env vars — operator-owned.
- `backend/app/main.py` CORS middleware wiring — the fix is at config level.
- Any other `except Exception` handler in `race_imports.py` (e.g. the SFTP
  move handlers near line 1003) — those intentionally degrade gracefully.
- Do NOT make CORS wildcard a hard failure (see Step 2 rationale).

## Git workflow

- Branch: follow operator instructions; if none, `advisor/001-prod-config-hardening`.
- Conventional commits, e.g. `fix(security): endurece config de producción (JWT default, CORS *, detalle de excepciones)`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Hard-fail on default JWT secret in production

In `backend/app/config.py`:
1. Change line 1 to `from pydantic import field_validator, model_validator`.
2. Keep the existing `validate_jwt_secret` warning (it covers dev).
3. Add a model validator at the end of the validator section (after
   `forbid_ai_log_prompts_in_prod`, before the `database_url` property):

```python
@model_validator(mode="after")
def _forbid_default_jwt_secret_in_prod(self) -> "Settings":
    if self.app_env == "production" and self.jwt_secret_key == "cambiar-en-produccion":
        raise ValueError(
            "JWT_SECRET_KEY usa el valor por defecto en producción. "
            "Generar con: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return self
```

A `model_validator(mode="after")` is required (not a `field_validator`)
because `app_env` is declared *after* `jwt_secret_key`.

**Verify**: `cd backend && .venv/bin/python -c "from app.config import Settings; import pytest; 
exec('try:\n Settings(app_env=\"production\", email_provider=\"resend\", resend_api_key=\"x\")\n print(\"FAIL: no error\")\nexcept Exception as e:\n print(\"OK raised:\", type(e).__name__)')"`
→ prints `OK raised: ValidationError`

### Step 2: Loud warning (not failure) on CORS wildcard in production

In the same model validator (extend `_forbid_default_jwt_secret_in_prod`, or
add a sibling `model_validator`), add:

```python
if self.app_env == "production" and "*" in self.cors_origin_list:
    import warnings
    warnings.warn(
        "CORS_ORIGINS='*' en producción. Restringir al dominio real del "
        "frontend (Cloudflare Pages) en cuanto exista.",
        stacklevel=2,
    )
```

Rationale for warning instead of raising: the live Render deployment currently
sets `CORS_ORIGINS=*` on purpose (frontend not yet deployed; documented in
CLAUDE.md). A hard failure would brick the next prod deploy. The warning keeps
the pressure visible in logs without breaking the running service.

**Verify**: `cd backend && .venv/bin/python -W error::UserWarning -c "from app.config import Settings; Settings(app_env='production', jwt_secret_key='0'*64, email_provider='resend', resend_api_key='x', cors_origins='*')"`
→ exits non-zero with `UserWarning` mentioning `CORS_ORIGINS`

### Step 3: Sanitize PDF-parse error details

In `backend/app/routers/race_imports.py`, in BOTH handlers cited in "Current
state" (lines 258–262 and 280–284):
1. Log the full exception server-side before raising, e.g.
   `logger.exception("race_import_parse RESULTADOS failed")` (and `GENERAL`
   in the second handler). Use the module's existing `logger`.
2. Replace the `detail` f-string with a generic Spanish message that keeps the
   document name but drops exception internals:
   - RESULTADOS: `"No se pudo procesar el PDF RESULTADOS. Verifique que sea el formato oficial de la Federación."`
   - GENERAL: `"No se pudo procesar el PDF GENERAL. Verifique que sea el formato oficial de la Federación."`

Do not change the `asyncio.TimeoutError` branches — they already return safe
messages.

**Verify**: `grep -n "type(exc).__name__" backend/app/routers/race_imports.py` → no matches.

### Step 4: Tests

Add tests (pattern: `backend/tests/test_ai_config.py`, reuse/copy its
`_prod_kwargs` helper):

1. `test_default_jwt_secret_rejected_in_prod` — `Settings(**_prod_kwargs(jwt_secret_key="cambiar-en-produccion"))` raises `ValidationError`.
2. `test_default_jwt_secret_allowed_in_dev` — `Settings(app_env="development")` constructs fine (still warns; assert with `pytest.warns(UserWarning)`).
3. `test_cors_wildcard_warns_in_prod` — `pytest.warns(UserWarning, match="CORS")` around `Settings(**_prod_kwargs(cors_origins="*"))`.
4. `test_cors_wildcard_silent_in_dev` — no CORS warning for `Settings(app_env="development", cors_origins="*")` (use `warnings.catch_warnings` and assert no match; the JWT dev warning may still fire — filter by message).

If env vars like `JWT_SECRET_KEY`/`CORS_ORIGINS` could leak in from the
environment, clear them with `monkeypatch.delenv(..., raising=False)` the way
`test_ai_defaults_disabled` does.

**Verify**: `cd backend && .venv/bin/python -m pytest tests/test_ai_config.py tests/test_prod_config_hardening.py -q` → all pass (adjust path if you added tests to an existing file).

### Step 5: Full suite

**Verify**: `cd backend && .venv/bin/python -m pytest -q` → all pass. Pay
attention to any existing test that asserted the old parser error format
(search first: `grep -rn "Error parseando" backend/tests/` — update those
assertions to the new generic messages if they exist).

## Test plan

- New tests listed in Step 4 (4 tests minimum), in
  `backend/tests/test_prod_config_hardening.py` (or appended to
  `test_ai_config.py`), modeled on `backend/tests/test_ai_config.py`.
- Existing suites must stay green, especially `tests/routers/test_race_imports.py`
  (the parse-failure path may assert on the detail message).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd backend && .venv/bin/python -m pytest -q` exits 0
- [ ] `grep -n "type(exc).__name__" backend/app/routers/race_imports.py` → no matches
- [ ] `grep -n "model_validator" backend/app/config.py` → at least one match
- [ ] New tests exist and pass (Step 4)
- [ ] `git status` shows no modified files outside the in-scope list
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The excerpts in "Current state" don't match the live code (drift).
- Existing tests assert the exact old error-detail format in ways that suggest
  the frontend parses it (search `frontend/src` for `"Error parseando"` — if
  found, the frontend depends on the string; report instead of changing).
- `Settings()` construction in `database.py`/`main.py` import order causes the
  new validator to fire during test collection (i.e., the test environment
  itself sets `APP_ENV=production`) — report; do not weaken the validator.

## Maintenance notes

- When the frontend ships on Cloudflare Pages, upgrade the CORS warning to a
  hard `ValueError` and update the Render env var first (deferred from this
  plan on purpose).
- Reviewers should confirm the new generic messages remain in español neutro
  and that no other handler regressed to leaking `{exc}`.
