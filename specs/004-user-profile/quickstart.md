# Quickstart: User Profile & Account Settings (004-user-profile)

## What this delivers
A self-service "Mi perfil / Ajustes de cuenta" area for every login-capable user
(admin, coach, parent) to: (1) edit basic info, (2) change password, (3) change
email with new-address verification.

## Backend — run & verify
```bash
cd backend && source .venv/bin/activate
alembic upgrade head            # applies the email_change_requests + merge migration
uvicorn app.main:app --reload
```
Manual smoke (logged-in token in $T):
```bash
# View profile
curl -H "Authorization: Bearer $T" localhost:8000/api/profile/me
# Edit basic info
curl -X PATCH -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"phone":"+57 300 111 2222"}' localhost:8000/api/profile/basic
# Change password
curl -X POST -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"current_password":"Parent2026!","new_password":"NuevaClave123"}' \
  localhost:8000/api/profile/change-password
# Request email change (link goes to the NEW address)
curl -X POST -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"current_password":"NuevaClave123","new_email":"nuevo@x.com"}' \
  localhost:8000/api/profile/change-email/request
# Confirm (token from the email link)
curl -X POST -H 'Content-Type: application/json' \
  -d '{"token":"<RAW_TOKEN>"}' localhost:8000/api/profile/change-email/confirm
```

## Frontend
- `/perfil` — profile page (basic info, change password, change email sections).
- `/confirmar-correo?token=...` — public confirm page hit from the email link.
- "Mi perfil" entry in the user menu.

## Tests
```bash
cd backend && pytest tests/ -k "profile or email_change"     # backend
cd frontend && npx vitest run src/**/profile*                # frontend + a11y
```

## Acceptance (maps to spec)
- Basic info persists and shows immediately (US1 / SC-001).
- Wrong current password → password unchanged (US2 / SC-002).
- Email already in use → neutral reject, no change (US3 / SC-003).
- Confirmation/alert emails sent on success (SC-004).
- No cross-account access; no secrets/PII in logs (SC-005, SC-006).
- Loading/error states on every async surface (SC-007).
