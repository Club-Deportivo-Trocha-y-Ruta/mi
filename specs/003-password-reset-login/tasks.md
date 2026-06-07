# Tasks: Password Reset from Login Page

**Input**: Design documents from `specs/003-password-reset-login/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/password-reset-api.md

**Tests**: INCLUDED — mandatory per Constitution Principle II (backend pytest + frontend
vitest + jest-axe + privacy invariants).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- Web app paths: `backend/`, `frontend/`

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Add settings `password_reset_token_ttl_minutes=60`, `password_reset_max_per_window=3`, `password_reset_window_minutes=15` to `backend/app/config.py` (with comments).

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ Must complete before user-story phases.**

- [x] T002 Create `PasswordResetToken` model in `backend/app/models/password_reset_token.py` (fields + indexes per data-model.md) and register it where models are imported (`backend/app/models/__init__.py` if applicable).
- [x] T003 Create Alembic migration `add_password_reset_tokens` in `backend/alembic/versions/` chained to the true current head `d4e5f6a7b8c9` (verified single-head; `f9a0b1c2d3e4` was an older superseded head) (table + `ix_password_reset_tokens_user_id` + unique `token_hash`).
- [x] T004 [P] Create Pydantic schemas in `backend/app/schemas/password_reset.py`: `PasswordResetRequest{email}`, `PasswordResetConfirm{token, new_password}` (min 8 chars validator reused from parent-invite), `PasswordResetMessage{message}`, `PasswordResetValidate{valid}`.
- [x] T005 [P] Create email templates `backend/templates/email/password_reset.html` and `backend/templates/email/password_changed.html` (español neutro, no names, reset_url/ttl_minutes/club_name context) extending the shared base template.
- [x] T006 Register `PASSWORD_RESET` and `PASSWORD_CHANGED` in `NotificationTemplate` enum (`backend/app/schemas/notification.py`) and add their `EmailTemplateSpec` entries in `backend/app/services/notification/template_registry.py`.

**Checkpoint**: model, migration, schemas, templates, and email specs exist.

---

## Phase 3: User Story 1 — Request a reset link (P1) 🎯 MVP

**Goal**: From the login page a user can request a reset and (if eligible) receive an email; response is always neutral.

- [x] T007 [US1] In `backend/app/services/password_reset.py` implement `request_reset(email, db, ip)`: look up eligible user, enforce rate limit (count tokens for email in window), invalidate prior tokens, create token (`secrets.token_urlsafe(32)` → store SHA-256), build `reset_url` from `settings.frontend_base_url`. Returns nothing observable to the caller (helper returns the optional token+user for the dispatcher). Log with ids only.
- [x] T008 [US1] Add `POST /api/auth/password-reset/request` to `backend/app/routers/auth.py`: validate body, call service, dispatch `password_reset` email **async** via NotificationService, ALWAYS return 200 neutral message.
- [x] T009 [P] [US1] Frontend `frontend/src/api/auth.ts` `requestPasswordReset(email)` + types in `frontend/src/types/auth.types.ts`.
- [x] T010 [P] [US1] Frontend `frontend/src/routes/auth/ForgotPasswordPage.tsx` (RHF+Zod email form, `noValidate`, loading/success/error states, neutral confirmation), route `/recuperar-contrasena` in `frontend/src/App.tsx`, and "¿Olvidaste tu contraseña?" link in `frontend/src/routes/auth/LoginPage.tsx`.
- [x] T011 [US1] Backend tests `backend/tests/routers/test_password_reset.py`: known email → 200 + email dispatched; unknown email → identical 200 + no dispatch; inactive/can_login=false → neutral 200 + no usable token; rate limit → neutral 200 + no new token.
- [x] T012 [P] [US1] Frontend tests for `ForgotPasswordPage` (vitest + jest-axe): renders, validation error, submits, shows neutral confirmation.

**Checkpoint**: requesting a reset works end-to-end and is enumeration-safe.

---

## Phase 4: User Story 2 — Set a new password via the link (P1)

**Goal**: A valid link lets the user set a new password and then log in; old password stops working.

- [x] T013 [US2] In `backend/app/services/password_reset.py` add `validate_token(token, db)` (404/410 like `get_valid_invite`) and `consume_token(token, new_password, db)`: update `hashed_password`, set `used_at`, invalidate sibling tokens, return user (no JWT).
- [x] T014 [US2] Add `GET /api/auth/password-reset/validate` and `POST /api/auth/password-reset/confirm` to `backend/app/routers/auth.py`; on confirm success dispatch `password_changed` email async; return neutral success (no token).
- [x] T015 [P] [US2] Frontend `frontend/src/api/auth.ts` `validateResetToken(token)` + `confirmPasswordReset(token, newPassword)` + types.
- [x] T016 [P] [US2] Frontend `frontend/src/routes/auth/ResetPasswordPage.tsx` (reads `?token`, validates on mount, shows form or expired state, password+confirm RHF+Zod, success → link to `/login`), route `/restablecer-contrasena` in `frontend/src/App.tsx`.
- [x] T017 [US2] Backend tests in `backend/tests/routers/test_password_reset.py` + `backend/tests/services/test_password_reset_service.py`: valid token → password changed, old password fails, new works; expired → 410; used → 410; unknown → 404; weak password → 422; sibling tokens invalidated.
- [x] T018 [P] [US2] Frontend tests for `ResetPasswordPage` (vitest + jest-axe): valid token shows form, expired token shows "request new" state, submit success, weak-password inline error.

**Checkpoint**: full recovery flow works; US1+US2 = shippable MVP.

---

## Phase 5: User Story 3 — Resist abuse and enumeration (P2)

**Goal**: Harden against enumeration and inbox flooding (most logic landed in US1; this phase verifies and tightens).

- [x] T019 [US3] Confirm async dispatch makes request timing independent of account existence (both branches return before send); add a brief docstring note in the router. Ensure rate-limit helper is covered by `backend/tests/services/test_password_reset_service.py` (window boundary: 3 allowed, 4th skipped; window reset).
- [x] T020 [US3] Privacy invariants test `backend/tests/test_password_reset_privacy.py`: responses never contain email/name/role/raw-token; logs (caplog) never contain email or raw token; emails carry no minor data; `validate`/`confirm` error bodies are generic.

**Checkpoint**: enumeration + abuse protections verified by tests.

---

## Phase 6: Polish & Cross-Cutting

- [x] T021 [P] Run `ruff` + `mypy` (backend) and `eslint` + `tsc --noEmit` (frontend); fix issues.
- [x] T022 [P] Run full `cd backend && pytest -k password_reset` and `cd frontend && npm run test -- password-reset` (+ a11y) green.
- [x] T023 [P] Add `.env.example` entries for the 3 new settings and a short note in `docs/` if an auth doc exists; update `quickstart.md` if anything drifted.
- [x] T024 Privacy audit pass (data-privacy-guard checklist) over the new files.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T006)** → user stories.
- T003 depends on T002. T006 depends on T005 existing.
- **US1 (T007–T012)** then **US2 (T013–T018)**: US2's service/router build on US1's service module and router file (sequential within `password_reset.py` / `auth.py`); frontend tasks marked [P] touch different files.
- **US3 (T019–T020)** after US1+US2.
- **Polish (T021–T024)** last.

## Parallel opportunities

- T004 + T005 in parallel (different files).
- Within each story, backend service/router are sequential (same files), but frontend `api`/page/tests ([P]) run alongside backend.
- T009/T010 (US1 frontend) parallel to T007/T008 (US1 backend).

## MVP scope

US1 + US2 (T001–T018) deliver the complete, shippable recovery flow. US3 + Polish harden
and verify it for production.
