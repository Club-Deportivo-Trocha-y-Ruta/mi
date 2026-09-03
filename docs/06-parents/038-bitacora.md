# Feature 038 — Bitácora de etapa (newsletter redesign)

**Branch**: `feat/038-bitacora` · **Date**: 2026-09-02
**Supersedes the presentation contract of** `specs/003-improve-individual-newsletter-pdf` (US3–US4) and `specs/024-newsletter-audit-fixes` (FR-006..FR-014). New tables/columns, new endpoints, new parent-facing surface.

Full spec in `specs/038-newsletter-bitacora-redesign/{spec.md,plan.md,data-model.md,contracts/api.md,research.md}`.

## What changed

The monthly newsletter (coach studio + email + PDF) is redesigned around a
"bitácora de etapa" (stage-log) metaphor: the month is a stage of the
season's route — waypoints (hitos), a weekly effort profile, a summit
(highlight), the next segment, and a "family compass" (conversation
question, monthly challenge, what to watch) replacing the old static
"support at home" tips. Existing newsletters keep `content_version=1`
(legacy templates); new ones default to `content_version=2` (bitácora,
`NEWSLETTER_CONTENT_VERSION` env var); a coach can convert a v1 draft
explicitly ("Convertir a bitácora") — never automatic (AC-7.1).

## US1 — Parent portal surface

- New parent router (`GET /api/parents/me/athletes/{athlete_id}/newsletters`,
  `.../{id}`, `.../{id}/pdf`, `POST .../{id}/read`), RBAC scoped to linked
  athletes only, `status == sent` only.
- New routes `/my-athletes/:athleteId/bitacora` (list) and
  `.../bitacora/:newsletterId` (detail) — `StageLogView mode="parent"`, PDF
  download, an idempotent read receipt fired once per session
  (`sessionStorage`).
- `ChildCard` gets an unread-bitácora chip; `GET /api/parents/my-athletes`
  gains `unread_newsletters` per athlete.

## US2 — Family-language analysis

- The 037 `InsightV3` (per-válida analysis) is translated to family-safe
  language by `family_translation.py`: `select_insight` picks the first
  eligible insight from the coach's `selected_race_insight_ids`,
  `filter_for_family` drops anything field-domain or low-priority and keeps
  only headline + one action + the válida label — never the raw
  `InsightV3` fields.
- New prompt `athlete_monthly_newsletter_v2.j2` (method + worked example)
  replaces the three-textarea narrative with `stage_title`, three grounded
  observations, `next_segment_text`, and the family compass; guardrails
  reuse v1's rules plus numeric grounding via `extract_numeric_tokens`
  (`app/services/race/insight_v3.py`).
- With or without AI consent, the bitácora always renders — a deterministic
  static fallback (`newsletter_static_copy.py` v2 functions) covers every
  narrative block when there is no AI narrative.

## US3/US4 — Coach studio

- `AthleteNewsletterStudioPage` (replaces the flat-card
  `AthleteNewsletterDetailPage` for `content_version == 2` newsletters,
  routed by `AthleteNewsletterStudioPage` itself): device preview (Móvil /
  Correo / PDF via a sandboxed iframe), per-block editing with a word
  counter and hide toggle, per-block regeneration (`POST
  .../regenerate-block`) with an instruction field, and a delivery panel
  showing masked recipient emails and per-event timestamps.
- `PATCH` gains `stage_overrides`, `hidden_blocks`, `coach_note` (≤ 60
  words, name-redacted), and `selected_race_insight_ids` (reorder only —
  must be a permutation of the stored list); any content-affecting PATCH
  re-derives `stage_log_json` and resets `pdf_sha256`.

## US5 — Email + PDF

- New templates `templates/email/athlete_stage_log.html` and
  `templates/documents/pdf/athlete_stage_log.html` (+ `_trail.svg.j2` for
  the route visualization); `generate_stage_log_pdf` keeps the anthropometry
  annex PDF-only and only when a record falls inside the month.
- `newsletter_dispatcher.py` picks the v1 or v2 template by
  `content_version`, links to the parent portal (or "Activa tu cuenta" when
  the parent has no account yet), and writes one `sent` delivery event per
  recipient.

## US6 — Delivery feedback (P3)

- New table `newsletter_delivery_events` (append-only, no PII —
  ids/timestamps/event type only) tracks `sent` / `delivered` / `opened` /
  `clicked` / `bounced` (via the opt-in Resend webhook,
  `POST /api/webhooks/resend`, off by default unless
  `RESEND_WEBHOOK_SECRET` is set) and `web_read` (parent portal read
  receipt). The studio's delivery panel resolves masked emails by joining
  `users` at read time — never persisted.

## Privacy (Ley 1581)

No real name, birth date, or medical detail reaches the AI provider — the
v2 prompt only ever sees `{{ athlete_reference }}` ("su hija"/"su
hijo"/"su deportista"). Parent DTOs (`to_parent_dto`) use an explicit
allow-list, never a deny-list, and always strip `block_states`,
`grounding_violations`, and `analyst_reading.source_insight_id`. Delivery
events never store emails, names, IPs, or user agents.

## Out of scope

Technique-skill map (A–H) and the athlete's own voice were explicitly
declined by the coach for this feature. A coach review queue ("next
athlete") was not requested.

## Known gaps

- T403 (Playwright e2e coach-studio→send→parent-read flow, LCP/a11y
  checks, Gmail-Android email checklist) has no artifacts in this working
  tree yet.
- SC-1 (regenerate June 2026 for the screenshot athlete + 5 others on the
  local DB) requires a live MySQL instance and has not been run in this
  environment.
