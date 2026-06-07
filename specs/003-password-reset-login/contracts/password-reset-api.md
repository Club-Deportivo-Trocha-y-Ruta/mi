# API Contract: Password Reset

**Feature**: `specs/003-password-reset-login` · Base path: `/api/auth`

All user-facing strings are español neutro (Colombia). No endpoint reveals account
existence. Tokens travel only in the request body or query string over HTTPS.

## 1. Request a reset link

`POST /api/auth/password-reset/request`

Request body:
```json
{ "email": "persona@example.com" }
```

Behavior:
- Validates the email is non-empty / well-formed (inline error otherwise → 422).
- If an eligible account exists (`is_active AND can_login AND has password`) and the rate
  limit is not exceeded: create a `PasswordResetToken`, invalidate the user's prior
  outstanding tokens, and dispatch the `password_reset` email **asynchronously**.
- In ALL other cases (no account, inactive, cannot log in, rate-limited): do nothing
  observable.
- ALWAYS returns the same response:

Response `200 OK`:
```json
{ "message": "Si el correo está registrado, te enviamos un enlace para restablecer tu contraseña." }
```

Validation error `422`:
```json
{ "detail": "Ingresa un correo electrónico válido." }
```

## 2. Validate a reset token (for the reset page)

`GET /api/auth/password-reset/validate?token=<raw-token>`

- `200 OK` → `{ "valid": true }` when the token is unused and unexpired.
- `410 Gone` → `{ "detail": "El enlace ha expirado o ya fue utilizado. Solicita uno nuevo." }`
  when used or expired.
- `404 Not Found` → `{ "detail": "Enlace no válido." }` when no matching token.

(The frontend treats 404 and 410 identically: show the "request a new link" state.)

## 3. Confirm the reset (set new password)

`POST /api/auth/password-reset/confirm`

Request body:
```json
{ "token": "<raw-token>", "new_password": "nuevaClave123" }
```

Behavior:
- `new_password` must satisfy the platform policy (min 8 chars) → else `422` with an
  inline localized message.
- Token must be valid (unused, unexpired) → else `410`/`404` as in §2.
- On success: update `users.hashed_password`, set `used_at=now`, invalidate sibling
  tokens, dispatch a "contraseña modificada" confirmation email. **No JWT is issued.**

Response `200 OK`:
```json
{ "message": "Tu contraseña fue actualizada. Ya puedes iniciar sesión." }
```

Errors:
- `422` invalid password: `{ "detail": "La contraseña debe tener al menos 8 caracteres." }`
- `410` expired/used token: `{ "detail": "El enlace ha expirado o ya fue utilizado. Solicita uno nuevo." }`
- `404` unknown token: `{ "detail": "Enlace no válido." }`

## Email: `password_reset`

- Subject (no name): `Restablece tu contraseña — {{ club_name }}`.
- Body: brief Spanish text + a button/link to
  `{{ frontend_base_url }}/restablecer-contrasena?token=<raw-token>`, validity notice
  ("el enlace vence en 60 minutos"), and a "si no fuiste tú, ignora este mensaje" line.
- Required context keys: `reset_url`, `club_name`, `ttl_minutes`.

## Email: `password_changed` (confirmation)

- Subject (no name): `Tu contraseña fue actualizada — {{ club_name }}`.
- Body: confirmation + "si no fuiste tú, contacta al club". No credentials.
- Required context keys: `club_name`.

## Frontend routes

| Route | Page | Notes |
|---|---|---|
| `/login` | `LoginPage` (existing) | Add "¿Olvidaste tu contraseña?" link → `/recuperar-contrasena`. |
| `/recuperar-contrasena` | `ForgotPasswordPage` | Email form → calls §1; shows neutral confirmation state. |
| `/restablecer-contrasena?token=…` | `ResetPasswordPage` | On load calls §2; renders form or expired state; submits §3; on success links to `/login`. |
