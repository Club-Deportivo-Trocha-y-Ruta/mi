# Contract — Newsletter Status Summary (read-only)

**Endpoint**: `GET /api/training/athlete-newsletters/summary`

**Purpose**: Replace the per-athlete newsletter-status fan-out (one request per athlete) on the monthly newsletter overview with a single constant-size response. (Constitution IV: no N+1 list patterns.)

## Request

| Param | In | Type | Required | Notes |
|---|---|---|---|---|
| `year` | query | int | yes | 2020–2100 |
| `month` | query | int | yes | 1–12 |

Auth: Bearer JWT. Roles: `coach`, `admin` (403 otherwise — RBAC via the existing permissions service). Club scoping identical to the existing newsletter list endpoints.

## Response `200 application/json`

```json
{
  "year": 2026,
  "month": 7,
  "items": [
    {
      "athlete_id": 12,
      "newsletter_id": 345,
      "status": "sent",
      "generated_at": "2026-07-02T14:03:00Z",
      "sent_at": "2026-07-02T14:10:00Z"
    },
    {
      "athlete_id": 13,
      "newsletter_id": null,
      "status": "none",
      "generated_at": null,
      "sent_at": null
    }
  ]
}
```

- Exactly one item per **active** club athlete (athletes with no newsletter for the period appear with `status: "none"`), so the client renders the full roster without extra lookups.
- `status` ∈ `none | draft | sent` — same states the existing per-athlete endpoints expose; no new states invented.
- No athlete names or PII in the payload (IDs only; the page already holds the authorized roster).

## Errors

| Code | Condition | Body |
|---|---|---|
| 401 | missing/invalid token | standard error envelope |
| 403 | role not coach/admin | standard error envelope |
| 422 | year/month out of range | validation detail |

## Non-functional

- p95 ≤ 500 ms (single grouped query; eager-load or aggregate — no per-athlete queries server-side either).
- Logged with correlation ID; no request/response bodies in logs (minors privacy).
- Test obligations (constitution II): happy path; RBAC-negative (parent → 403); validation-negative (month 13 → 422); a query-count or timing assertion protecting against reintroduced N+1.

## Frontend consumer

`useNewsletterStatusSummary(year, month)` (TanStack Query; key `["newsletter-status-summary", year, month]`), consumed by `AthleteNewslettersDashboardPage`. The existing per-athlete hooks remain for the detail page; the dashboard stops issuing per-athlete status queries entirely.
