# Research: User Profile & Account Settings (004-user-profile)

Phase 0 output. Resolves the Technical Context unknowns and records the design
decisions, grounded in the existing codebase, OWASP guidance (web research), and
Context7 docs for FastAPI / FastAPI-Users patterns.

## Decision 1 — Email change: verify-new-email-before-apply

- **Decision**: The account email switches **only after** the user clicks a
  confirmation link sent to the **new** address. A single-use, time-limited,
  SHA-256-hashed token (raw token only in the link) ties the request to the
  account, mirroring the existing `PasswordResetToken` design.
- **Rationale**: OWASP "Changing a User's Registered Email Address" prescribes
  storing the value as a *proposed* email (not the live one), confirming via a
  link to the new address with a time limit, and sending a *notification-only*
  message to the **old** address. This proves ownership of the new mailbox and
  alerts the original owner to takeover attempts. Confirmed by the user during
  `/speckit-specify`.
- **Alternatives considered**: Immediate change after re-auth (simpler, but a
  typo locks the user out and gives no ownership proof) — rejected. MFA step-up
  (OWASP-ideal) — out of scope; the project has no MFA factor yet, so
  current-password re-auth is the available equivalent.

## Decision 2 — Re-authentication with current password for sensitive changes

- **Decision**: Both *change password* and *request email change* require the
  user's **current password** in the request body, verified with the existing
  `verify_password`. Basic-info edits do **not** require it.
- **Rationale**: OWASP Authentication Cheat Sheet — a logged-in user changing
  password or the primary identifier (email) MUST re-authenticate to defend
  against unattended-session / CSRF takeover. The project has no MFA, so the
  current password is the re-auth factor.
- **Alternatives considered**: No re-auth (rejected: CWE-620 Unverified Password
  Change). Separate step-up endpoint (rejected: unnecessary complexity for a
  single factor).

## Decision 3 — Session invalidation after credential change

- **Decision**: Document the limitation; do not add token revocation in this
  feature. After a password change the confirmation email is sent; access tokens
  are short-lived (30 min) and refresh tokens 7 days. We will **not** silently
  log the user out, but we record this as a known gap.
- **Rationale**: Auth is stateless JWT (`PyJWT`), with no server-side session or
  refresh-token store to revoke. OWASP recommends invalidating other sessions,
  but implementing a token denylist is a cross-cutting change beyond this
  feature's scope and would need its own design. Short access-token TTL bounds
  the exposure.
- **Alternatives considered**: Build a refresh-token denylist now (rejected:
  scope creep, new storage + middleware). Rotate a per-user token "version"
  claim (rejected: touches the global auth path and every protected route;
  warrants its own spec). Captured in plan Complexity Tracking as a deferred gap.

## Decision 4 — Enumeration-safe email-conflict handling

- **Decision**: When the requested new email already belongs to another account,
  respond with the **same neutral message** as the success path and send **no**
  confirmation email. Internally short-circuit silently.
- **Rationale**: Matches the project's existing anti-enumeration posture in the
  password-reset flow and OWASP Authentication guidance (no oracle for "is this
  email registered?"). Email is dispatched in a background task so response
  timing does not leak existence.
- **Alternatives considered**: Return 409 on conflict (rejected: leaks that the
  email exists). The own-current-email case is treated as a neutral no-op.

## Decision 5 — Endpoint surface & RBAC

- **Decision**: New router `app/routers/profile.py` mounted at `/api/profile`,
  operating **only on the authenticated `current_user`** (no `{user_id}` path
  param), so cross-account access is structurally impossible. Email-change
  *confirm* is a public token endpoint (reachable from the email link), like
  `/auth/password-reset/confirm`.
  - `GET  /api/profile/me` — current profile (basic info + email).
  - `PATCH /api/profile/basic` — update first_name/last_name/phone.
  - `POST /api/profile/change-password` — current + new password.
  - `POST /api/profile/change-email/request` — current password + new email.
  - `POST /api/profile/change-email/confirm` — token (public).
- **Rationale**: FastAPI-Users exposes a single `PATCH /users/me`; we split into
  explicit verbs because the credential flows need different validation,
  re-auth, and notifications, which is clearer and testable. `get_current_user`
  already enforces auth + active + can_login. Administrative editing of *other*
  users stays in the existing `/api/users` router (unchanged).
- **Alternatives considered**: Extend `/auth/me` with PATCH (rejected: mixes auth
  with account management and crowds one module). One generic PATCH like
  FastAPI-Users (rejected: can't cleanly enforce per-field re-auth + verify
  flow).

## Decision 6 — Reuse token/notification/migration infrastructure

- **Decision**: New `EmailChangeRequest` model mirrors `PasswordResetToken`
  (hashed token, expiry, single-use, sibling invalidation, rate-limit, ids-only
  logging) and **adds** the `new_email` column. New notification templates
  `EMAIL_CHANGE_VERIFY` (to new address) and `EMAIL_CHANGED_NOTICE` (to old
  address); reuse `PASSWORD_CHANGED` for password changes. New config knobs
  `email_change_token_ttl_minutes` / `_max_per_window` / `_window_minutes`.
- **Rationale**: Rule-of-three is satisfied (reset + email-change both need the
  hashed-token lifecycle); the established pattern is OWASP-aligned and already
  tested. No new runtime dependency.
- **Alternatives considered**: Generic polymorphic "token" table (rejected:
  premature abstraction over two concrete cases; harder to index/validate).

## Decision 7 — Alembic multi-head merge

- **Decision**: This branch currently has **three** Alembic heads
  (`8c1d2e3f4a5b`, `a1b2c3d4e5f7`, `a1b2c3d4e5f8`). The new migration will set
  `down_revision = ("8c1d2e3f4a5b", "a1b2c3d4e5f7", "a1b2c3d4e5f8")`, acting as a
  **merge point** *and* creating the `email_change_requests` table, leaving a
  single head so `alembic upgrade head` works on deploy.
- **Rationale**: `entrypoint.sh` runs `alembic upgrade head`, which errors with
  multiple heads. A merge migration is the canonical Alembic resolution and lets
  this feature unblock deploys.
- **Alternatives considered**: Separate empty merge migration + table migration
  (rejected: two files for one logical step). Chain to a single head and ignore
  the fork (rejected: leaves `upgrade head` broken).

## Decision 8 — Frontend structure

- **Decision**: New `frontend/src/routes/profile/` with `ProfilePage.tsx`
  (sections: basic info, change password, change email) and a public
  `ConfirmEmailChangePage.tsx` (reads `token` from URL, calls confirm). New
  `api/profile.ts`, `hooks/profile/useProfile.ts`, `types/profile.types.ts`. A
  "Mi perfil" entry in the user menu. Forms use RHF + Zod + `noValidate`; shadcn
  components; loading/empty/error states; ≥48px targets; jest-axe clean. On
  success of basic-info edit, refresh `auth.store.user`.
- **Rationale**: Matches the existing `routes/auth/*` and feature-folder
  conventions; honors Constitution Principle III (UX consistency, español
  neutro, a11y) and IV (lazy-load, clear cold-start states).
- **Alternatives considered**: A modal-only settings panel (rejected: three
  distinct flows + a public confirm page need real routes).

## Technical Context resolved

- **Language/Version**: Python 3.14 (backend), TypeScript 5 / React 19 (frontend).
- **Primary deps**: FastAPI, SQLAlchemy 2 async + aiomysql, Alembic, PyJWT,
  bcrypt (backend); React 19 + Vite, shadcn/ui + Tailwind, TanStack Query,
  Zustand, RHF + Zod (frontend). **No new runtime dependency.**
- **Storage**: MySQL 8.4 (prod), SQLite for tests. New table
  `email_change_requests`.
- **Testing**: pytest + httpx.AsyncClient + aiosqlite; vitest + Testing Library
  + jest-axe.
- **Project type**: Web application (backend + frontend).
- **Performance**: within Constitution IV budgets (writes p95 ≤ 1500 ms; lazy
  routes ≤ 150 KB gzip).
- **Scale/Scope**: small (single-club platform); ~3 backend endpoints group + 2
  frontend routes.

## Sources

- [Changing a User's Registered Email Address — OWASP](https://owasp.org/www-community/pages/controls/Changing_Registered_Email_Address_For_An_Account)
- [Authentication Cheat Sheet — OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Forgot Password Cheat Sheet — OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [Testing for Weak Password Change or Reset Functionalities — OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/04-Authentication_Testing/09-Testing_for_Weak_Password_Change_or_Reset_Functionalities)
- [CWE-620: Unverified Password Change](https://cwe.mitre.org/data/definitions/620.html)
- Context7: `/fastapi-users/fastapi-users` (PATCH /users/me, current-user dependency), `/fastapi/fastapi` (auth dependencies).
