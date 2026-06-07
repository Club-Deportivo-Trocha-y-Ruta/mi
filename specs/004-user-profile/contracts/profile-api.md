# API Contract: Profile & Account Settings (004-user-profile)

Base path: `/api/profile`. All endpoints except **confirm** require a valid JWT
(`get_current_user`: active + `can_login`). Operations act on the authenticated
user only — there is no `{user_id}` parameter. End-user messages: español neutro.

---

## GET /api/profile/me
Return the signed-in user's own profile.

- **Auth**: required.
- **200** `ProfileOut`:
  ```json
  { "id": 12, "email": "padre@x.com", "first_name": "Carlos",
    "last_name": "García", "phone": "+57 300 000 0000", "role": "parent" }
  ```
- **401** if unauthenticated.

---

## PATCH /api/profile/basic
Update own basic information.

- **Auth**: required. **Body** `ProfileBasicUpdate` (≥1 field):
  ```json
  { "first_name": "Carlos", "last_name": "García P.", "phone": "+57 301 ..." }
  ```
- **200** `ProfileOut` (updated).
- **422** validation error (empty required name, phone too long, no fields).

---

## POST /api/profile/change-password
Change own password after re-authentication.

- **Auth**: required. **Body** `PasswordChangeRequest`:
  ```json
  { "current_password": "Old123!", "new_password": "NewSecret456" }
  ```
- **200** `ProfileMessage` → `"Tu contraseña fue actualizada."` Sends
  `PASSWORD_CHANGED` email (no password in body).
- **400** current password incorrect → `"La contraseña actual no es correcta."`
- **422** new password fails policy (< 8) or equals current.

---

## POST /api/profile/change-email/request
Request an email change (verify-new-email-before-apply).

- **Auth**: required. **Body** `EmailChangeRequestBody`:
  ```json
  { "current_password": "Secret123", "new_email": "nuevo@x.com" }
  ```
- **200** `ProfileMessage` (neutral) → `"Si el correo es válido y está
  disponible, te enviamos un enlace de confirmación a la nueva dirección."`
  - On eligible request: stores a `PENDING` `EmailChangeRequest`, sends
    `EMAIL_CHANGE_VERIFY` to the **new** address (background). Account email
    **unchanged** until confirmed.
  - On conflict (email already used by another account), own-current-email, or
    rate-limit exceeded: **same neutral 200**, no email sent (anti-enumeration).
- **400** current password incorrect → `"La contraseña actual no es correcta."`
- **422** `new_email` syntactically invalid.

---

## POST /api/profile/change-email/confirm
Apply a pending email change using the token from the link. **Public** (reachable
from the email link; the token is the secret).

- **Body** `EmailChangeConfirm`: `{ "token": "<raw token>" }`
- **200** `ProfileMessage` → `"Tu correo fue actualizado. Inicia sesión con tu
  nueva dirección."` Applies `users.email = new_email`, marks token used,
  invalidates siblings, sends `EMAIL_CHANGED_NOTICE` to the **old** address.
- **404** unknown token → `"Enlace no válido."`
- **410** used/expired token → `"El enlace ha expirado o ya fue utilizado.
  Solicita el cambio nuevamente."`
- **409** the target email was taken by someone else between request and confirm
  → neutral `"No se pudo aplicar el cambio. Solicita el cambio nuevamente."`

---

## Invariants (asserted by tests)
1. No response, log, or error contains a password, `token_hash`, raw token, or
   any other account's data.
2. Email-conflict on *request* is indistinguishable from success (status, body,
   timing via background dispatch).
3. `users.email` never changes on *request*; only on successful *confirm*.
4. A token is single-use and time-limited; reuse/expiry → 410.
5. All sensitive changes (password, email request) require the correct current
   password; wrong password → 400 with the password unchanged / no token issued.
6. Endpoints operate solely on `current_user`; cross-account modification is
   impossible (no id parameter).
