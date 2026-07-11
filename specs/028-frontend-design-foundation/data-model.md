# Data Model — 028 Frontend Design Foundation & Everyday Reliability

No new persisted entities and no schema changes. This feature introduces two presentation-level models and one read-model:

## 1. Status vocabulary (presentation enum)

Shared by `StatusBadge` (and consumed app-wide in 033):

| Status | Token | Meaning (constitution III) | Presentation |
|---|---|---|---|
| `success` | `--color-success` | complete / active / current | green + icon/label |
| `warning` | `--color-warning` | partial / attention / stale | amber + icon/label |
| `danger` | `--color-danger` | error / blocking / revoked | red + icon/label |
| `neutral` | (existing grays) | informational / not started | gray + icon/label |

Domain mappings (initial set, extended in 033): session `planned→neutral / executed→success / cancelled→danger`; consent `current→success / outdated→warning / revoked→danger / never→neutral`; sync `active→success / expired→warning / disconnected→neutral / error→danger`; analysis freshness `fresh→success / stale→warning / none→neutral`; newsletter `sent→success / draft→warning / none→neutral`.

Rule: color is never the only carrier — every badge pairs an icon or text label.

## 2. Shared component prop models

Defined as TypeScript interfaces in `frontend/src/components/shared/` — full contracts in [`contracts/shared-components.md`](contracts/shared-components.md). They carry no domain state; all data arrives via props.

## 3. Newsletter status summary (read-model, backend)

One aggregate over existing newsletter/athlete data — contract in [`contracts/newsletter-status-summary.md`](contracts/newsletter-status-summary.md):

- **NewsletterStatusSummaryItem**: `athlete_id` (int), `newsletter_id` (int | null), `status` (`none | draft | sent`), `generated_at` (datetime | null), `sent_at` (datetime | null)
- **NewsletterStatusSummary**: `year` (int), `month` (int 1–12), `items` (list of the above, one per active club athlete)

Validation: `year` within plausible seasons (2020–2100), `month` 1–12; RBAC coach/admin; response contains athlete IDs only — no names or PII beyond what the requesting coach already accesses on the same page (list join happens client-side against the already-authorized athletes query).

State transitions: none introduced — the summary reads existing newsletter states (`none → draft → sent`) produced by the existing generation/send flows.
