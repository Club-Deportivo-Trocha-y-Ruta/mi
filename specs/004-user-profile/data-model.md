# Data Model: User Profile & Account Settings (004-user-profile)

Phase 1 output.

## Existing entity (reused, not modified structurally)

### User (`users`)
Self-managed in this feature: `first_name`, `last_name`, `phone`, `email`,
`hashed_password`. Read-only here: `role`, `is_active`, `can_login`, `created_by`,
club membership, athlete linkage. Only `can_login = true` users reach this module.

| Field | Notes |
|---|---|
| `email` | `String(255)`, unique, nullable. Changed only via verify-new-email flow. |
| `hashed_password` | `String(255)`, nullable. Changed via change-password flow. |
| `first_name` / `last_name` | `String(100)`, required. Editable. |
| `phone` | `String(20)`, nullable. Editable. |

No column changes to `users`.

## New entity

### EmailChangeRequest (`email_change_requests`)
Pending email-change confirmation. Mirrors `PasswordResetToken`: the raw token
travels only in the link to the **new** address; only its SHA-256 hash is stored.
Valid while `used_at IS NULL AND expires_at > now`. Creating or consuming one
invalidates the user's other pending requests. Privacy: holds the *target* email
(the user's own new address, not a minor's) plus `user_id`; never logged with PII.

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | autoincrement |
| `user_id` | int FK → `users.id` | indexed |
| `new_email` | `String(255)` | proposed new address (normalized, lower-cased) |
| `token_hash` | `String(64)` unique | SHA-256 hex of raw token |
| `expires_at` | `DateTime` | now + `email_change_token_ttl_minutes` (default 60) |
| `used_at` | `DateTime` nullable | set when consumed/invalidated |
| `created_at` | `DateTime` | default now (UTC) |
| `requested_ip` | `String(45)` nullable | abuse forensics; never logged with PII |

Indexes: `ix_email_change_requests_user_id` on `user_id`; unique on `token_hash`.

#### Validation rules
- `new_email` must be a syntactically valid email and **not equal** to the user's
  current email (no-op) and **not in use** by any other account (neutral reject).
- Rate-limit: ≤ `email_change_max_per_window` (default 3) created per
  `email_change_window_minutes` (default 15) per user.

#### State transitions
```
(none) --request(valid current pw, free new_email)--> PENDING (token issued, email sent to new addr)
PENDING --confirm(token, before expiry)--> APPLIED (users.email updated; notice to old addr) [terminal]
PENDING --expire / superseded by new request--> INVALID (used_at set) [terminal]
```

## Schemas (Pydantic v2) — `app/schemas/profile.py`

- `ProfileOut` — `id, email, first_name, last_name, phone, role` (read view; from MeResponse subset).
- `ProfileBasicUpdate` — `first_name?, last_name?, phone?` (all optional; at least one; non-empty trimmed names; phone length ≤ 20).
- `PasswordChangeRequest` — `current_password, new_password` (new_password ≥ 8, must differ from current).
- `EmailChangeRequestBody` — `current_password, new_email` (valid email).
- `EmailChangeConfirm` — `token`.
- `ProfileMessage` — `message` (neutral string; reused shape from password reset).

Privacy contract: responses never include `hashed_password`, `token_hash`, raw
tokens, `requested_ip`, or any other account's data.

## Config additions — `app/config.py`

| Setting | Default |
|---|---|
| `email_change_token_ttl_minutes` | 60 |
| `email_change_max_per_window` | 3 |
| `email_change_window_minutes` | 15 |

## Notification templates — `NotificationTemplate`

| Value | To | Purpose |
|---|---|---|
| `EMAIL_CHANGE_VERIFY` = `"email_change_verify"` | new address | confirm link + TTL |
| `EMAIL_CHANGED_NOTICE` = `"email_changed_notice"` | old address | "your email was changed" alert |
| `PASSWORD_CHANGED` (existing) | account email | "your password was changed" |

Email bodies in español neutro (Colombia); no secrets, no minor PII.
