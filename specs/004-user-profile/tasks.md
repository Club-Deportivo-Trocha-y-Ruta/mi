---
description: "Task list for 004-user-profile implementation"
---

# Tasks: User Profile & Account Settings

**Input**: Design documents from `specs/004-user-profile/`
**Tests**: Included (Constitution II — NON-NEGOTIABLE).
**Organization**: Grouped by user story (US1 basic info, US2 password, US3 email).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Add `email_change_token_ttl_minutes`/`_max_per_window`/`_window_minutes` to `backend/app/config.py`.
- [ ] T002 [P] Add `ProfileOut`, `ProfileBasicUpdate`, `PasswordChangeRequest`, `EmailChangeRequestBody`, `EmailChangeConfirm`, `ProfileMessage` to `backend/app/schemas/profile.py`.
- [ ] T003 [P] Add `EMAIL_CHANGE_VERIFY` + `EMAIL_CHANGED_NOTICE` to `NotificationTemplate` in `backend/app/schemas/notification.py`.

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ Blocks all user stories.**

- [ ] T004 Create `EmailChangeRequest` model in `backend/app/models/email_change_request.py` (mirror `PasswordResetToken` + `new_email`); register in `app/models/__init__.py`.
- [ ] T005 Create Alembic migration in `backend/alembic/versions/` that (a) merges the 3 heads `("8c1d2e3f4a5b","a1b2c3d4e5f7","a1b2c3d4e5f8")` and (b) creates `email_change_requests` (indexes + unique token_hash).
- [ ] T006 [P] Register `EMAIL_CHANGE_VERIFY` + `EMAIL_CHANGED_NOTICE` specs in `backend/app/services/notification/template_registry.py`; add `templates/email/email_change_verify.html` + `email_changed_notice.html` (español neutro, no secrets/PII).
- [ ] T007 Create `backend/app/services/profile.py` skeleton + `backend/app/routers/profile.py`; mount at `/api/profile` in `backend/app/main.py`.
- [ ] T008 [P] Frontend scaffolding: `frontend/src/types/profile.types.ts`, `frontend/src/api/profile.ts`, `frontend/src/hooks/profile/useProfile.ts` (query keys + mutations w/ invalidation).

**Checkpoint**: foundation ready.

---

## Phase 3: User Story 1 — Update basic information (P1) 🎯 MVP

### Tests
- [ ] T009 [P] [US1] `tests/routers/test_profile.py`: GET /me; PATCH /basic happy + 422 (empty name, no fields); cross-account impossible.

### Implementation
- [ ] T010 [US1] Implement `get_profile` + `update_basic_info` in `services/profile.py`.
- [ ] T011 [US1] Implement `GET /api/profile/me` + `PATCH /api/profile/basic` in `routers/profile.py` (uses `get_current_user`).
- [ ] T012 [P] [US1] Frontend `ProfilePage.tsx` basic-info section (RHF+Zod, `noValidate`, loading/error states); refresh `auth.store.user` on success; "Mi perfil" menu link + route in `App.tsx`.
- [ ] T013 [P] [US1] Frontend test `routes/profile/__tests__/ProfilePage.test.tsx` (render, edit+save, validation) + jest-axe.

**Checkpoint**: US1 independently functional.

---

## Phase 4: User Story 2 — Change password (P1)

### Tests
- [ ] T014 [P] [US2] `tests/routers/test_profile.py`: change-password happy (200 + email), wrong current (400, unchanged), weak/equal new (422).

### Implementation
- [ ] T015 [US2] Implement `change_password` in `services/profile.py` (verify current, hash new, send `PASSWORD_CHANGED`).
- [ ] T016 [US2] Implement `POST /api/profile/change-password` in `routers/profile.py` (background email dispatch).
- [ ] T017 [P] [US2] Frontend change-password section + hook mutation; success/error toasts.
- [ ] T018 [P] [US2] Frontend test for change-password form.

**Checkpoint**: US1 + US2 work.

---

## Phase 5: User Story 3 — Change email (verify-new-email-before-apply) (P2)

### Tests
- [ ] T019 [P] [US3] `tests/services/test_profile_service.py`: request (token issued, email unchanged), conflict→neutral no-token, rate-limit, confirm applies + sibling invalidation, expired/used→410.
- [ ] T020 [P] [US3] `tests/routers/test_profile.py`: request 200 neutral (success & conflict identical), wrong pw 400, confirm 200/404/410.

### Implementation
- [ ] T021 [US3] Implement `request_email_change` + `confirm_email_change` in `services/profile.py` (hashed token, expiry, single-use, rate-limit, anti-enumeration, ids-only logs).
- [ ] T022 [US3] Implement `POST /api/profile/change-email/request` (auth) + `POST /api/profile/change-email/confirm` (public) in `routers/profile.py`; verify email + notice email dispatch.
- [ ] T023 [P] [US3] Frontend change-email section + public `ConfirmEmailChangePage.tsx` (reads `?token=`), route in `App.tsx`.
- [ ] T024 [P] [US3] Frontend tests for change-email form + confirm page + jest-axe.

**Checkpoint**: all stories functional.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T025 [P] Privacy invariants test `tests/test_profile_privacy.py` (no password/token_hash/raw token/other-account data in responses or logs).
- [ ] T026 Run `data-privacy-guard` audit on the new code.
- [ ] T027 [P] `ruff` + `tsc --noEmit` + targeted `pytest` + `vitest` all green.
- [ ] T028 [P] Docs: short `docs/` note + update CLAUDE.md implementation-status table.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 (foundational, blocks all stories).
- US1, US2, US3 depend on Phase 2; can run in parallel by surface (backend vs frontend `[P]`).
- Within a story: tests → service → router → frontend.
- Phase 6 after stories.

## Parallel Opportunities

- T002/T003, T006/T008 in parallel (different files).
- Backend (T010/T011, T015/T016, T021/T022) and frontend (T012/T013, T017/T018, T023/T024) can proceed concurrently once Phase 2 is done.
