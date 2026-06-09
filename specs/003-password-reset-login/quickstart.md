# Quickstart: Password Reset from Login Page

**Feature**: `specs/003-password-reset-login`

## Manual end-to-end (dev)

Prereqs: backend running (`cd backend && uvicorn app.main:app --reload`), frontend
running (`cd frontend && npm run dev`), MailHog up (Docker) to capture emails at
http://localhost:8025.

1. Go to `/login`, click **¿Olvidaste tu contraseña?**.
2. Enter `entrenador@trochyruta.com` (seed coach). You see the neutral confirmation.
3. Open MailHog → the `password_reset` email → click the link
   (`/restablecer-contrasena?token=…`).
4. Enter a new password (≥ 8 chars), confirm it, submit. See success → go to `/login`.
5. Log in with the **new** password (works) and the **old** password (fails).
6. Re-open the same reset link → "el enlace ya fue utilizado" state.

## Enumeration / abuse checks

- Submit an unknown email → identical neutral confirmation, no email in MailHog.
- Submit the same email 4× within 15 min → 4th produces no new email (rate-limited),
  response still neutral 200.

## Automated tests to run

```bash
cd backend && pytest tests/ -k "password_reset"        # backend service + router + privacy
cd frontend && npm run test -- password-reset           # vitest pages + api
```

## Key files (created/changed)

- Backend: `app/models/password_reset_token.py`, `app/schemas/password_reset.py`,
  `app/services/password_reset.py`, routes in `app/routers/auth.py`, settings in
  `app/config.py`, Alembic migration, templates
  `templates/email/password_reset.html` + `password_changed.html`, registry entries.
- Frontend: `routes/auth/ForgotPasswordPage.tsx`, `routes/auth/ResetPasswordPage.tsx`,
  link in `LoginPage.tsx`, routes in `App.tsx`, `api/auth.ts` functions, types.
