# Phase 1 Data Model: Password Reset from Login Page

**Feature**: `specs/003-password-reset-login` · **Date**: 2026-06-07

## New entity: `PasswordResetToken`

Table: `password_reset_tokens`. Mirrors the `ParentInvite` shape but stores the token
**hashed** and references a `User` (not an athlete).

| Field | Type | Notes |
|---|---|---|
| `id` | int PK autoincrement | |
| `user_id` | int FK → `users.id`, indexed | Owner of the account being reset. |
| `token_hash` | str(64), **unique** | SHA-256 hex of the raw token. Raw token never stored. |
| `expires_at` | datetime (UTC) | `created_at + ttl` (default 60 min). |
| `used_at` | datetime \| null | Set when the reset completes; null = unused. |
| `created_at` | datetime (UTC) | `default now(UTC)`. Used for rate-limit windowing. |
| `requested_ip` | str(45) \| null | Optional, for abuse forensics. Never logged with PII. |

Indexes:
- `ix_password_reset_tokens_user_id` on `user_id` (lookup + invalidation + rate window).
- unique on `token_hash` (exact-match lookup).

### Validation / invariants

- `token_hash` is the SHA-256 of a `secrets.token_urlsafe(32)` value (256-bit entropy).
- A token is **valid** iff `used_at IS NULL` AND `expires_at > now`.
- At most one token should be *consumable* per user at a time: creating a new token and
  completing a reset both invalidate the user's other outstanding tokens.
- No personal data (email, name, role) is stored on this row.

### State transitions

```
(created: used_at=null, expires_at>now)
        │  GET validate            → 200 valid
        │  POST confirm (valid)    → used_at=now (CONSUMED), password updated,
        │                            sibling tokens invalidated
        │  expires_at <= now       → EXPIRED (validate/confirm → 410)
        │  new request for user    → INVALIDATED (used_at=now or deleted)
```

Invalidation is implemented by setting `used_at = now` on sibling rows (keeps an audit
trail) rather than deleting.

## Reused entity: `User` (unchanged)

- Read by `email` (case-sensitive match consistent with existing `login`); eligible iff
  `is_active AND can_login AND hashed_password IS NOT NULL`.
- `hashed_password` is updated on successful reset via `hash_password()`.
- No schema change to `users`.

## Configuration (new settings in `app/config.py`)

| Setting | Default | Purpose |
|---|---|---|
| `password_reset_token_ttl_minutes` | 60 | Token lifetime. |
| `password_reset_max_per_window` | 3 | Max requests per email per window. |
| `password_reset_window_minutes` | 15 | Rolling window for the rate limit. |

## Migration

New Alembic migration chained to current head `f9a0b1c2d3e4` (revision id e.g.
`a1b2c3d4e5f8_add_password_reset_tokens`): create `password_reset_tokens` with the two
indexes. No data backfill. Verified in SQLite via tests (project convention).
