# Contract: Warm-Up Use of GET /health

**Feature**: 012-perceived-performance-cache

The existing health endpoint (`backend/app/main.py:71`) gains a new consumer.
**No backend change** — this documents how the frontend may use it so the
endpoint's behavior is treated as a stable contract.

## Endpoint (existing, unchanged)

| Property | Value |
|---|---|
| Method / Path | `GET {VITE_API_BASE_URL}/health` |
| Auth | None |
| Success | `200` with a small JSON body (content irrelevant to the consumer) |
| Side effects | None server-side; the request itself wakes a sleeping Render Free instance (~50 s worst case) |

## Frontend usage rules

1. Fired **at most once per app load**, from `LoginPage` mount and/or the
   authenticated `AppShell` mount (deduplicated by a module-level flag).
2. **Fire-and-forget**: no retries, no exponential backoff, response body
   ignored, all errors swallowed (the ping must never surface a user-facing
   error or feed the waking-banner state on its own).
3. Must **not** carry the Authorization header (pre-login usage) — sent
   outside the authenticated axios instance or with auth interception
   bypassed.
4. Must not be scheduled on an interval (no keep-alive polling) — protects
   Render free-tier instance hours and stays clear of platform ToS concerns.

## Rationale

Wakes the backend while the user types credentials (FR-009), shrinking the
perceived cold start from ~50 s after submit to near-zero in the common path.
