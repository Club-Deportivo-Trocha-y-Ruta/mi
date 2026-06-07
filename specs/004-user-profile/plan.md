# Implementation Plan: User Profile & Account Settings

**Branch**: `claude/branch-cloning-ok0PF` | **Date**: 2026-06-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-user-profile/spec.md`

## Summary

Add a self-service profile/account-settings module for every login-capable user
(admin, coach, parent): edit basic info (first/last name, phone), change password
(current-password re-auth + confirmation email), and change email using
**verify-new-email-before-apply** (single-use hashed token sent to the new
address, alert to the old address on success). Reuses the existing OWASP-aligned
token, notification, and migration infrastructure from the password-reset feature;
no new runtime dependency. A merge Alembic migration also unifies the three
current heads so deploys can `alembic upgrade head`.

## Technical Context

**Language/Version**: Python 3.14 (backend); TypeScript 5 / React 19 (frontend).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async + aiomysql, Alembic, PyJWT,
bcrypt; React 19 + Vite, shadcn/ui + Tailwind, TanStack Query, Zustand, RHF + Zod.
**No new runtime dependency.**

**Storage**: MySQL 8.4 (prod) / SQLite (tests). New table `email_change_requests`.

**Testing**: pytest + httpx.AsyncClient + aiosqlite; vitest + Testing Library + jest-axe.

**Target Platform**: Linux server (Render free tier); modern browsers, mid-tier Android.

**Project Type**: Web application (backend + frontend).

**Performance Goals**: Constitution IV — writes p95 ≤ 1500 ms; lazy route ≤ 150 KB gzip.

**Constraints**: Ley 1581 (no minor PII in logs/responses); español-neutro end-user copy; WCAG AA.

**Scale/Scope**: Single-club platform; 5 backend endpoints + 2 frontend routes.

## Constitution Check

*GATE: passed pre-Phase 0; re-checked post-design — still passing.*

- **I. Code Quality**: New service/router/schema follow existing module shape;
  public service functions get docstrings; `ruff` + `tsc` clean. Reuses the
  proven password-reset pattern (no duplication beyond rule-of-three). ✅
- **II. Testing (NON-NEGOTIABLE)**: Backend happy + negative paths (wrong
  password 400, conflict-neutral, expired/used token 410, validation 422) and
  privacy invariants (no secrets/PII in responses or logs). Frontend vitest for
  the three forms + confirm page + jest-axe (0 violations). ✅
- **III. UX Consistency**: shadcn/ui + RHF + Zod + `noValidate`; loading/empty/
  error states; ≥48px targets; status color tokens; español neutro; public
  confirm page mirrors reset page. ✅
- **IV. Performance**: profile routes lazy-loaded; single-row indexed queries (no
  N+1); background email dispatch; cold-start state surfaced. ✅
- **Quality gates**: JWT + bcrypt reused; RBAC = self-only by construction;
  anti-enumeration on email request; `AI_LOG_PROMPTS` unaffected; ids-only logs;
  `data-privacy-guard` audit included as a task. ✅

## Project Structure

### Documentation (this feature)
```text
specs/004-user-profile/
├── plan.md           # this file
├── spec.md
├── research.md       # Phase 0
├── data-model.md     # Phase 1
├── quickstart.md     # Phase 1
├── contracts/
│   └── profile-api.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)
```text
backend/
├── app/
│   ├── models/email_change_request.py        # NEW
│   ├── schemas/profile.py                     # NEW
│   ├── services/profile.py                    # NEW
│   ├── routers/profile.py                     # NEW (mounted /api/profile)
│   ├── schemas/notification.py                # EDIT (2 enum values)
│   ├── services/notification/template_registry.py  # EDIT (2 specs)
│   ├── config.py                              # EDIT (3 settings)
│   └── main.py                                # EDIT (include profile router)
├── templates/email/
│   ├── email_change_verify.html              # NEW
│   └── email_changed_notice.html             # NEW
├── alembic/versions/xxxx_email_change_requests.py  # NEW (merge 3 heads + table)
└── tests/
    ├── routers/test_profile.py               # NEW
    ├── services/test_profile_service.py      # NEW
    └── test_profile_privacy.py               # NEW

frontend/
├── src/
│   ├── routes/profile/ProfilePage.tsx               # NEW
│   ├── routes/profile/ConfirmEmailChangePage.tsx    # NEW
│   ├── routes/profile/__tests__/*.test.tsx          # NEW
│   ├── api/profile.ts                               # NEW
│   ├── hooks/profile/useProfile.ts                  # NEW
│   ├── types/profile.types.ts                       # NEW
│   ├── App.tsx                                      # EDIT (2 routes)
│   └── components/layout/* (user menu)             # EDIT ("Mi perfil" link)
```

**Structure Decision**: Web-app layout. Backend follows the established
model/schema/service/router separation; frontend follows the feature-folder
convention used by `routes/auth/*`.

## Complexity Tracking

| Violation / Deferred gap | Why | Simpler Alternative Rejected Because |
|---|---|---|
| No session/refresh-token revocation after credential change | OWASP recommends invalidating other sessions, but auth is stateless JWT with no server-side store. Short access TTL (30 min) bounds exposure; documented as a known gap for a future auth-revocation spec. | Building a token denylist or per-user token-version now touches the global auth path and every protected route — disproportionate to this feature and warrants its own design. |
| Merge migration unifies 3 pre-existing Alembic heads | `alembic upgrade head` errors with multiple heads; deploy is already blocked. | A standalone empty merge migration is an extra file for the same logical step; chaining to one head leaves `upgrade head` broken. |
