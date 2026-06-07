# Phase 0 Research: Password Reset from Login Page

**Feature**: `specs/003-password-reset-login` · **Date**: 2026-06-07

This document resolves the open technical questions for the password-reset feature and
records the rationale. Sources: OWASP Forgot Password Cheat Sheet, OWASP Authentication
Cheat Sheet, FastAPI Users reset-password reference flow, and the existing Trocha y Ruta
codebase (parent-invite token flow).

## Existing patterns reused (codebase findings)

| Concern | Existing asset | Reuse decision |
|---|---|---|
| Token-by-email flow | `ParentInvite` model + `services/invitations.py` (`secrets.token_urlsafe(32)`, `expires_at`, `used`, `used_by`) | Mirror the shape in a new `PasswordResetToken` model and `services/password_reset.py`. |
| Auth primitives | `services/auth.py` (`hash_password`, `verify_password` via bcrypt) | Reuse `hash_password` to set the new password. |
| Email sending | `NotificationService` + `TemplateRegistry` + Jinja templates in `backend/templates/email/` | Add a new `password_reset` email template + registry entry; send via existing service (supports `send_async`). |
| Frontend auth pages | `routes/auth/LoginPage.tsx`, `OnboardingPage.tsx`, `ParentRegisterPage.tsx`; routes in `App.tsx`; `api/auth.ts`; RHF+Zod | Add `ForgotPasswordPage` + `ResetPasswordPage`, a link on `LoginPage`, and API client functions. |
| Password policy | `ParentRegisterRequest.password_strength` → min 8 chars | Reuse the exact rule (min 8 chars) for the new password. |
| Frontend base URL for links | `settings.frontend_base_url` | Build the reset link with it (never from request Host header). |

## Decision 1 — Delivery mechanism: URL token via email

- **Decision**: Email a single-use URL containing a high-entropy token (not a PIN/code).
- **Rationale**: Email is the only transactional channel configured (Resend in prod,
  MailHog in dev). URL tokens are the simplest secure approach per OWASP and match the
  existing parent-invite flow. SMS/PIN is out of scope (no SMS provider).
- **Alternatives considered**: 6–12 digit PIN over SMS (rejected — no SMS provider,
  added cost, no benefit here); security questions (rejected — OWASP advises against as
  sole mechanism).

## Decision 2 — Token entropy and storage (hashed at rest)

- **Decision**: Generate the token with `secrets.token_urlsafe(32)` (256 bits). Store
  only a SHA-256 hash of the token in the DB (`token_hash`, unique). The raw token
  exists only inside the emailed link. Lookup hashes the incoming token and matches.
- **Rationale**: OWASP requires cryptographically secure generation and storing reset
  tokens **hashed, as with passwords**. SHA-256 is appropriate for a 256-bit random
  token (unlike user passwords, the token is not low-entropy, so a fast hash is fine and
  enables an indexed exact-match lookup). This is a deliberate improvement over
  `ParentInvite`, which stores the token in plaintext.
- **Alternatives considered**: Plaintext token like `ParentInvite` (rejected — a DB leak
  would expose live reset links); bcrypt of the token (rejected — bcrypt's per-row salt
  prevents an indexed lookup and adds no value for a 256-bit random secret).

## Decision 3 — Expiry: 1 hour, single-use

- **Decision**: `expires_at = now + 1 hour`. Token is single-use; mark `used_at` on
  successful reset. A new request invalidates prior outstanding tokens for that user.
- **Rationale**: OWASP: links "should rarely exceed one hour" and must be single-use and
  invalidated after use. Configurable via a new setting `password_reset_token_ttl_minutes`
  (default 60).

## Decision 4 — Account-enumeration prevention (message + timing)

- **Decision**: `POST .../request` ALWAYS returns HTTP 200 with the same neutral body
  regardless of whether the email maps to an account, is inactive, or cannot log in.
  Email delivery is dispatched **asynchronously** (`send_async=True` via `TaskDispatcher`)
  so request latency does not depend on whether an email was actually sent.
- **Rationale**: OWASP requires consistent message **and** consistent timing. Background
  dispatch neutralizes the timing side-channel (the expensive send happens off the
  request path identically in both branches).
- **Alternatives considered**: Synchronous send with a dummy delay for the no-account
  branch (rejected — fragile, still leaks under load); returning 404 for unknown email
  (rejected — classic enumeration leak).

## Decision 5 — Rate limiting / abuse throttling

- **Decision**: Throttle in the service layer using the tokens table: cap the number of
  reset requests per email within a rolling window (default: 3 per 15 min) and a coarser
  per-window global guard. When exceeded, still return the same neutral 200 but skip
  creating/sending a new token. Configurable via `password_reset_max_per_window` and
  `password_reset_window_minutes`.
- **Rationale**: OWASP recommends per-account rate limiting to prevent inbox flooding,
  without revealing account existence. A DB-count approach needs no new infrastructure
  (no Redis) and fits the Render free tier. Account lockout is explicitly avoided (OWASP:
  do not lock accounts during reset).
- **Alternatives considered**: CAPTCHA (rejected for v1 — added UX friction and a new
  dependency; can be added later); Redis token bucket (rejected — no Redis in stack).

## Decision 6 — After reset: no auto-login, invalidate tokens, notify

- **Decision**: On success: update `hashed_password`, mark token `used_at`, invalidate
  all other outstanding tokens for that user, and return a neutral success that directs
  the user to log in (NO auto-login, no JWT issued). Send a "tu contraseña fue
  modificada" confirmation email (no credentials in it).
- **Rationale**: OWASP: do not auto-login after reset; notify the user their password
  changed (never email credentials). Session invalidation: the platform uses stateless
  JWTs with short access-token lifetimes (30 min) and no server-side session store, so
  there is nothing to revoke server-side; the short TTL bounds exposure. Documented as an
  accepted limitation (a JWT denylist is out of scope for v1).
- **Alternatives considered**: Auto-login for convenience (rejected — OWASP anti-pattern);
  building a refresh-token denylist (rejected for v1 — disproportionate; noted as future
  work).

## Decision 7 — Token validation endpoint for UX

- **Decision**: Add `GET .../validate?token=...` returning 200 (valid) / 410 (expired or
  used) / 404 (unknown), mirroring `get_valid_invite`. The reset page calls it on load to
  render the "link expired — request a new one" state before showing the form.
- **Rationale**: Tokens are secret, so disclosing validity to the link holder is not an
  enumeration risk and produces a clean UX (constitution UX: design expired/invalid
  states). 

## Decision 8 — Privacy (Ley 1581, minors)

- **Decision**: The email, the neutral messages, and all logs contain no minor data and
  do not reveal the recipient's role or linked athletes. Logs use the user id / token id
  only (never the email or raw token). The `password_reset` email addresses the user
  generically; subject contains no name.
- **Rationale**: Constitution + project privacy rules. `data-privacy-guard` audit applies
  because these accounts are linked to minors' data.

## Open questions

None. All spec assumptions are satisfied by the decisions above; defaults are
configurable via settings without scope change.

## Sources

- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [FastAPI Users — reset password flow](https://fastapi-users.github.io/fastapi-users/) (Context7 `/fastapi-users/fastapi-users`)
- Codebase: `backend/app/services/invitations.py`, `backend/app/models/parent_invite.py`, `backend/app/services/notification/*`
