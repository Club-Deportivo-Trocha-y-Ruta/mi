# Implementation Plan: Password Reset from Login Page

**Branch**: `claude/password-restore-login-page-pvwwU` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-password-reset-login/spec.md`

## Summary

Add self-service password recovery launched from the login page. A user requests a reset
by email; the system emails a single-use, 1-hour, high-entropy URL token (stored hashed);
the user sets a new password and then logs in normally (no auto-login). The flow is
enumeration-safe (identical neutral response + async email so timing is constant) and
rate-limited per email. Implementation reuses existing assets: the parent-invite token
pattern, bcrypt auth helpers, the NotificationService/Jinja email pipeline, and the
React RHF+Zod auth pages. See [research.md](./research.md) for the OWASP-aligned design
decisions.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Alembic, PyJWT, bcrypt
(backend); React 19 + Vite, shadcn/ui + Tailwind, TanStack Query, React Hook Form + Zod
(frontend). No new runtime dependencies.

**Storage**: MySQL 8.4 (prod) / SQLite (tests). One new table `password_reset_tokens`.

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend); vitest + Testing Library +
jest-axe (frontend).

**Target Platform**: Linux server (Render free tier) + SPA on modest Android over 3G/4G.

**Project Type**: Web application (FastAPI backend + React frontend).

**Performance Goals**: Reset endpoints p95 ≤ 1500 ms (writes); email send off the request
path via background dispatch. No N+1 (single indexed lookups).

**Constraints**: Enumeration-safe (constant message + timing); tokens hashed at rest;
no minor PII in logs/emails/messages (Ley 1581); español neutro for all user copy; no
Redis / no SMS (free tier).

**Scale/Scope**: Small user base (coaches, admins, parents). ~3 backend endpoints, 1
table, 2 email templates, 2 new frontend pages + 1 link.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | How this plan satisfies it |
|---|---|
| **I. Code Quality** | Reuses existing patterns (invitations service, notification pipeline); new service has docstrings; passes `ruff`+`mypy` / `eslint`+`tsc`. No premature abstraction. |
| **II. Testing (NON-NEGOTIABLE)** | Backend: service + router tests (happy path + negative: unknown email neutrality, expired/used token, rate limit, invalid password) + **privacy invariants** (no email/name/raw-token in responses or logs). Frontend: vitest for both pages + api, jest-axe on each page. |
| **III. UX Consistency** | shadcn/ui + RHF+Zod with inline localized errors; no HTML5/Zod conflict (`noValidate`); loading/success/expired/error states designed; 48px targets; español neutro copy; status color semantics. |
| **IV. Performance** | Indexed single-row lookups; email dispatched async (off request path); new pages are light and lazy-loadable; assumes Render cold start (neutral states, no raw timeouts). |
| **Quality Gates — Privacy** | No minor PII anywhere in this flow; logs use ids only; `data-privacy-guard` audit in scope. |
| **Quality Gates — Security** | Token via `secrets` (256-bit), stored SHA-256-hashed; single-use + 1h expiry; no auto-login; enumeration-safe; rate-limited; bcrypt for the new password; no account lockout. |
| **Quality Gates — Stack discipline** | No new dependencies; agreed stack only. |

**Result**: PASS. No violations → Complexity Tracking left empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-password-reset-login/
├── plan.md              # This file
├── spec.md              # Feature spec
├── research.md          # Phase 0 decisions (OWASP-aligned)
├── data-model.md        # PasswordResetToken + settings
├── quickstart.md        # Manual + automated test walkthrough
├── contracts/
│   └── password-reset-api.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/password_reset_token.py        # NEW
│   ├── schemas/password_reset.py             # NEW
│   ├── services/password_reset.py            # NEW (create/validate/consume/rate-limit)
│   ├── routers/auth.py                        # CHANGED (+3 endpoints)
│   ├── config.py                              # CHANGED (+3 settings)
│   └── services/notification/
│       └── template_registry.py               # CHANGED (+2 email specs)
├── alembic/versions/xxxx_add_password_reset_tokens.py   # NEW (head f9a0b1c2d3e4)
├── templates/email/password_reset.html        # NEW
├── templates/email/password_changed.html      # NEW
└── tests/
    ├── services/test_password_reset_service.py     # NEW
    ├── routers/test_password_reset.py              # NEW
    └── test_password_reset_privacy.py              # NEW

frontend/
├── src/
│   ├── routes/auth/ForgotPasswordPage.tsx     # NEW
│   ├── routes/auth/ResetPasswordPage.tsx      # NEW
│   ├── routes/auth/LoginPage.tsx              # CHANGED (+link)
│   ├── api/auth.ts                            # CHANGED (+3 functions)
│   ├── types/auth.types.ts                    # CHANGED (+types)
│   └── App.tsx                                # CHANGED (+2 public routes)
└── src/routes/auth/__tests__/                 # NEW tests for both pages
```

**Structure Decision**: Existing web-app layout (`backend/` + `frontend/`). The feature
slots into the existing `auth` router and `routes/auth` directory; no new top-level
modules.

## Complexity Tracking

> No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
