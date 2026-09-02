# API contracts — feature 038

All coach routes live under the existing prefix `/api/athletes/{athlete_id}/monthly-newsletters` and keep `require_role([admin, coach])` + club check. Parent routes are a new router. Error vocabulary follows the project: 401 unauthenticated, 403 wrong role, 404 not found or not linked, 409 state conflict, 422 validation, 451 AI consent missing (only where AI is invoked).

## Coach

### `GET /{id}` (extended)
Response adds: `content_version`, `stage_log` (coach view, see data-model §1), `stage_overrides`, `hidden_blocks`, `coach_note`, `read_at`, `delivery[]`.

### `PATCH /{id}` (extended)
```json
{ "stage_overrides": {"stage_title": "…", "observations": [{"claim": "…", "evidence": "…", "block_ref": "attendance"}, …]},
  "hidden_blocks": ["photos"],
  "coach_note": "…",
  "selected_race_insight_ids": [42, 17] }
```
Rules: only `draft` / `approved` (approved → back to `draft`, existing behaviour); `coach_note` ≤ 60 words after redaction; `selected_race_insight_ids` must be a permutation of the stored list; response = full DTO with the re-derived `stage_log`; `pdf_sha256` reset.

### `POST /{id}/regenerate-block`
```json
{ "block": "stage_title | summit_caption | observations | next_segment_text | family_compass | analyst_reading",
  "instruction": "más corto y menciona la lluvia" }
```
200 → full DTO (block updated in `ai_narrative` v2 and `stage_log`; any override for that block cleared, `block_states[block] = "ai"`). 409 if status is `sent`; 451 when AI consent is missing; 503 when the provider fails (block untouched, `error_message` set to a neutral text).

### `POST /{id}/convert`
v1 draft → v2: rebuild `metrics_snapshot`, run narrative v2, write `stage_log_json`, set `content_version = 2`. 409 unless `status in {draft, outdated}` and `content_version == 1`.

### `GET /{id}/render?surface=email`
`text/html` of the email as the family will receive it (parent name replaced by "Familia", CTA pointing to the portal). Coach only, `Content-Security-Policy: sandbox` header; the studio loads it in an `<iframe sandbox>`.

### `POST /{id}/send` (unchanged contract)
Side effect added: one `newsletter_delivery_events(sent)` row per recipient with `provider_message_id` from Resend (null on SMTP).

## Parent (NEW router `parent_newsletters.py`, prefix `/api/parents/me/athletes/{athlete_id}/newsletters`)

RBAC: `require_role([parent])`; athlete must be linked to the caller through `parent_athletes` (else 404). Coach/admin → 403 (they use the coach routes).

### `GET /`
`200 → ParentNewsletterListItem[]` ordered by `(year, month)` desc; only `status == sent`.

### `GET /{newsletter_id}`
`200 → ParentNewsletterOut` (stage_log through `to_parent_dto`). 404 if not sent or not linked.

### `GET /{newsletter_id}/pdf`
`application/pdf`, regenerates when the hash is stale (same logic as the coach route). 404 rules as above.

### `POST /{newsletter_id}/read`
Idempotent. First call sets `read_at`, `read_by_user_id`, inserts `newsletter_delivery_events(web_read)`. `204` always (also when already read). Never called from coach surfaces.

### `GET /api/parents/my-athletes` (existing, extended)
Each item gains `unread_newsletters: int` (sent and `read_at is null`).

## Webhook (P3, NEW router `webhooks_resend.py`)

### `POST /api/webhooks/resend`
- 404 when `RESEND_WEBHOOK_SECRET` is empty.
- Verifies `svix-id`, `svix-timestamp`, `svix-signature` (HMAC-SHA256 over `{id}.{timestamp}.{body}` with the base64 secret; tolerance 5 min). 400 on bad signature.
- Body `{type: "email.delivered" | "email.opened" | "email.clicked" | "email.bounced", created_at, data: {email_id, …}}`. Maps `email_id` → `newsletter_delivery_events.provider_message_id`; unknown ids → 200 (ignored). Duplicate `svix-id` → 200 (idempotent). Other event types → 200 ignored.
- Never logs recipients or subjects.

## Frontend routes

| Route | Page | Guard |
|---|---|---|
| `/training/athlete-newsletters/:athleteId/:id` | `AthleteNewsletterStudioPage` when `content_version == 2`, else legacy `AthleteNewsletterDetailPage` | coach/admin |
| `/my-athletes/:athleteId/bitacora` | `ParentNewsletterListPage` | parent |
| `/my-athletes/:athleteId/bitacora/:newsletterId` | `ParentNewsletterPage` | parent |
