# Research: Guided anthropometric capture (feature 048)

All decisions below resolve the plan's open technical points. Code references are as of 2026-09-29 (single Alembic head `448f7dfbca14`).

## R1 — Derivation logic must be extracted before PUT exists

- **Decision**: Move the inline derivation in `backend/app/routers/anthropometry.py::create_anthropometry` (:131-205 — Mirwald offset, WHO percentiles with LMS-empty fallback, `weight_over_who_range` nulling, BMI, nutritional status, training implication) into a new service `backend/app/services/anthropometry.py::derive_record_fields(db, athlete, inputs) -> DerivedFields`, and an `apply_derived_fields(record, derived)` helper. Both POST and the new PUT call it.
- **Rationale**: FR-002 requires identical rules on create and edit; a second inline copy would drift (Principle I, rule of three is already at two).
- **Alternatives**: Recompute via a SQL trigger/column defaults (rejected: logic is Python, needs LMS tables); calling the POST handler internally (rejected: side effects — notifications, audit `create`).

## R2 — Author-or-admin permission

- **Decision**: New helper `can_modify_anthropometric_record(user, record) -> bool` in `backend/app/services/permissions.py`: `user.role == admin or record.evaluated_by == user.id`. PUT/DELETE first run `verify_athlete_access` (club scope, archived → 404), then this helper → `403 {"detail": "not_record_author"}`. The GET list exposes `can_modify: bool` per record so the UI hides the actions (FR-005).
- **Rationale**: Feature 041 has no per-coach assignment; club scope is the only access rule (`permissions.py:104-105`). No author-or-admin helper exists yet (`can_edit_session` is club-based), so this is new and must live in `permissions.py` per the RBAC quality gate. `evaluated_by` is already stored and exposed.
- **Alternatives**: Frontend-only hiding (rejected: FR-005 requires refusal server-side).

## R3 — No second approaching-circa notification on edit

- **Decision**: Only POST sends the approaching-circa-PHV parent notification (unchanged). PUT never sends it, even if the edit newly crosses the threshold.
- **Rationale**: FR-008 forbids a second notification; there is no persisted "notification sent" marker (no notification-log table), and adding one needs a migration for a rare case. An edit is a correction of a measurement already taken; if the corrected value crosses the threshold, the coach sees it immediately on the review and in the growth tab and can talk to the family.
- **Alternatives**: New `circa_alert_sent_at` column (rejected: migration + state for an edge case); resend on crossing (rejected: violates FR-008 when the original already notified).
- **Spec note**: this narrows the edge case "an edit that newly crosses the threshold must not send a second notification" to "edits never notify"; strictly compliant.

## R4 — Duplicate prevention without an idempotency key

- **Decision**: POST rejects a second record for the same athlete and `evaluation_date` with `409 {"detail": "anthropometry_same_date_exists", "existing_record_id": <id>, "same_values": <bool>}`. `same_values` is true when weight, standing, sitting and arm span match the stored record exactly (after the schema's decimal rounding). The frontend treats `same_values=true` on a **retry** as a successful save (the first attempt reached the server) and otherwise shows "Ya existe una medición de esa fecha" with "Abrir la existente".
- **Rationale**: Satisfies FR-021 (same-date warning) and FR-029 (retries never duplicate) with one rule and no schema change. No endpoint in the codebase supports idempotency keys (the nearest is If-Match on newsletters). Two evaluations of the same child on the same day are never legitimate; a correction goes through PUT.
- **Alternatives**: `client_request_id` column with unique index (rejected: migration, extra state); DB unique constraint on (athlete_id, evaluation_date) (rejected: legacy data may already contain same-date pairs and the migration would fail on them — enforced at app level only, and PUT applies the same check when the date changes).

## R5 — Plausibility engine: one backend source

- **Decision**: New pure module `backend/app/services/anthropometry_plausibility.py::check_plausibility(current, previous | None) -> list[PlausibilityWarning]` used in two places:
  1. `POST /api/athletes/{id}/anthropometry/plausibility` (dry-run, no write) called by the review step and by the edit form before saving (with `record_id` to exclude the record being edited from "previous").
  2. `GET /api/athletes/{id}/anthropometry` adds `plausibility_flags: list[str]` per record for coach/admin (computed at read time by walking records in date order; omitted for parents) → the history's "Revisar" marker (clarification 4).
- **Rules** (codes are stable API; copy lives in the frontend):

  | Code | Measure | Rule | Needs previous |
  |---|---|---|---|
  | `height_decreased` | standing height | current < previous − 1.0 cm | yes |
  | `height_velocity_implausible` | standing height | interval ≥ 60 days and (gain / years) > 15 cm/yr | yes |
  | `weight_change_large` | weight | abs(current − previous) / previous > 10 % | yes |
  | `sitting_ratio_atypical` | sitting height | sitting / standing outside [0.47, 0.57] | no |
  | `arm_span_ratio_atypical` | arm span | arm span / standing outside [0.90, 1.10] (only when arm span present) | no |

- **Thresholds rationale**: peak height velocity in youth rarely exceeds ~10–12 cm/yr (boys), lower in girls; 15 cm/yr leaves room for measurement error so the warning only fires on typos. Below 60 days the annualization amplifies a few millimetres of error, so velocity is skipped (spec edge case). Sitting-height ratio (Cormic index) in 9–16-year-olds sits around 0.50–0.54; ±0.03 beyond covers normal variation and still catches "bench not subtracted" (≈ 0.75+) and swapped fields. Arm span ≈ stature ±5–6 cm in children; 0.90–1.10 only catches typos. `arm_span_ratio_atypical` extends FR-017's history-independent check to the fourth measure (same intent: catch typos); it never blocks.
- **Hard validation additions (FR-016)**: net sitting height / standing height outside [0.40, 0.65] is a 422 (physically impossible → wrong input), on top of the existing absolute ranges.
- **Rationale**: Capture is online-only (clarification 1), so a dry-run call costs nothing in availability, and a single engine avoids a TS/Python parity problem (the codebase already has one unsynced duplicate: skinfold site texts). The "Revisar" marker must use exactly the rules shown before saving.
- **Alternatives**: TS mirror + shared JSON fixtures (rejected: two engines); storing flags (rejected by clarification 4).

## R6 — AI explanation and skinfold side effects of an edit or delete

- **Decision**:
  - PUT deletes the `athlete_ai_explanations` rows for that record (all use cases) in the same transaction, with an audit row for each deletion (the table is in `AUDIT_STRICT`), so the explanation regenerates on demand (FR-006). Its unique key (athlete, record, use_case) assumed immutability, so explicit deletion is required.
  - PUT with a weight change calls `recompute_estimates_for_record(record)` (`body_composition.py:280`), as the comment at `anthropometry.py:342-352` already demands.
  - PUT with a date change on a record that has a skinfold set runs `check_min_age` and a new `check_interval_for_date(db, athlete_id, record, new_date, settings)` that excludes the record itself (the existing `check_interval` is a no-op once a set exists) → 409 with the same detail codes as the wizard (FR-007).
  - DELETE removes the skinfold set (ORM cascade + FK CASCADE) and AI explanations (explicit delete, not relying on SQLite FK enforcement), audits the record deletion with `meta={"had_skinfolds": bool}`.
- **Read-time derived data** (velocity, alerts, next-measurement date, growth-summary) needs no work: all computed at read time from `load_athlete_records` (`growth_summary.py`). Frontend invalidates the same query keys as create plus `["body-composition", id]` and `["ai", ...]`.

## R7 — Audit

- **Decision**: `AuditAction.update` / `AuditAction.delete` with `AuditEntityType.anthropometric_record` (both exist; no enum migration). `changed_fields` = names of edited fields; values only for `evaluation_date` (already in `VALUE_ALLOWLIST`). Register PUT, DELETE and the plausibility POST in the route-policy map (`audit.py:917-930`) — the route-walk test enforces it; the plausibility dry-run is registered as non-mutating.
- **Privacy**: no weights/heights in `meta`, `diff`, logs or error messages (FR-032); a privacy test asserts it.

## R8 — Frontend architecture

- **Decision**:
  - New page routes (coach/admin, lazy-loaded): `/athletes/:id/anthropometry/new` (single capture, guided/quick), `/athletes/:id/anthropometry/:recordId/edit` (quick layout pre-filled), `/anthropometry/session` (group session). The inline "+ Nueva medición" toggle on the athlete page becomes a link to the new page.
  - Components under `frontend/src/components/athletes/anthropometry-capture/`: `AnthropometryCapture` (mode switch + submit orchestration), `CapturePrecheckStep`, `MeasureStep`, `CaptureReviewStep` (values, warnings, plain-language PHV, save exits), `QuickCaptureForm` (the old grid, refactored; also used by edit), `BenchHeightField`, `PlausibilityWarnings`, `PhvPlainSummary`. Reuse `shared/Stepper.tsx` and `shared/ConfirmDialog.tsx` (delete).
  - **No `useFormDraft`** (clarification 1 overrides the input line). Values live in RHF state only; failed saves keep them on screen with "Reintentar".
  - Device preferences in `localStorage` (non-PII): `tyr.anthro.captureMode` (`guided|quick`, default `guided`) and `tyr.anthro.benchHeightCm` (number, default empty). Not added to the TanStack persisted-cache allow-list; not cleared on logout (not personal data).
  - Group session state in a new **non-persisted** Zustand store `store/measurementSession.store.ts` (selected athlete ids, date, per-athlete status). Survives in-app navigation (skinfold detour, FR-026) but not a reload — exactly clarification 1. Cleared on logout.
  - Measure guide texts in `frontend/src/lib/anthropometry/measureGuides.ts`; illustrations imported statically from `frontend/src/assets/anthropometry/{weight,standing_height,sitting_height,arm_span}.webp` (+ optional `precheck.webp`) via `lib/anthropometry/measureIllustrations.ts` (missing file → Vite build fails, FR-031).
  - PHV plain-language labels: `MaturationStatus.PrePHV` → "Aún no llega al estirón", `CircaPHV` → "Está en pleno estirón", `PostPHV` → "Ya pasó el estirón"; `trainingImplications` from `lib/phv.ts` below; maturity offset and age at PHV in a collapsible "Detalle técnico".
- **Alternatives**: Keep inline form on the athlete tab (rejected: a multi-step flow with illustrations needs the full width on a tablet; the skinfold wizard already uses a page).

## R9 — Group-session roster without N+1

- **Decision**: New endpoint `GET /api/anthropometry/roster?date=YYYY-MM-DD` returning, for every athlete the caller may access (non-archived), `{athlete_id, full_name, category, sex, birth_date, last_evaluation_date, has_record_on_date, skinfolds_eligible}` in one query (`max(evaluation_date)` grouped + an exists subquery), with a query-count test (Principle IV).
- **Rationale**: `AthletesListPage` fires one `getAthlete` per athlete to get `latest_anthropometry` (N+1); reusing that for a 20–40 athlete picker would violate Principle IV. `useAthletes` has no category filter; filtering by category is done client-side on the roster.
- **`skinfolds_eligible`**: age ≥ 9 at `date` and interval open (reuse `check_min_age` logic and `next_due_date` from body-composition service in batch) — lets the queue offer "Agregar pliegues" without extra calls.

## R10 — Field guide: single source for texts

- **Decision**: Basic-measure texts live in `backend/app/data/anthropometry_measures.json` (`key`, `label`, `donde`, `como`, `alt`) and the pre-check conditions in the same file. The PDF template `backend/templates/documents/pdf/skinfold_field_guide.html` gains a first section rendered from it, with PNG illustrations at `backend/templates/documents/pdf/diagrams/img/anthro_<key>.png`. The frontend `measureGuides.ts` holds the same texts and a vitest parity test reads the JSON from `../backend/app/data/` and asserts equality (FR-030 "single shared source" enforced by test).
- **Alternatives**: Serve texts from an API (rejected: guided steps must render instantly; extra call); import JSON across the repo boundary in the Vite build (rejected: breaks the frontend's standalone Hostinger build).

## R11 — Illustrations (clarification 5)

- **Decision**: Generated during implementation by the orchestrating session through Claude in Chrome driving the Gemini or ChatGPT web UI in the owner's logged-in browser. Style reference: `frontend/src/assets/skinfolds/triceps.webp` uploaded with the prompt. Prompts (in `research`-approved form, see quickstart §Illustrations) contain no athlete data. Output → 768×768, white background, no text → converted with `cwebp -q 82` for the frontend and resized PNG (Pillow in `backend/.venv`) for the PDF. Owner approves each image in chat before it is committed to `frontend/src/assets/anthropometry/`.
- **Stop rule**: if the web tool is unavailable, blocks, or output fails style/privacy (faces, text, recognizable person) after 3 attempts for one image, stop and ask the owner.
- **Not delegated to subagents**: browser automation needs the owner's interactive session and approvals.

## R12 — E2E in local (owner request for this plan)

- **Decision**: Run Playwright locally against the isolated stack (`docker-compose.e2e.yml` via `frontend/scripts/e2e-stack.sh up`, API :8001, MySQL :3307; `npm run test:e2e:isolated`). New specs:
  - `frontend/e2e/anthropometry-capture.spec.ts` — guided capture end to end (pre-check, 4 steps, bench subtraction, plausibility warning, review PHV, save) + quick mode + same-date 409 path.
  - `frontend/e2e/anthropometry-edit-delete.spec.ts` — evaluator edits and deletes; `coach2` (non-evaluator, `realTokens`) sees no actions and API returns 403; parent sees no actions.
  - `frontend/e2e/anthropometry-session.spec.ts` — select 3 athletes, measure 2, skip 1, summary; skinfold detour returns to the queue.
  - 360 px run: the capture and session specs repeat their main path under `test.use({ viewport: { width: 360, height: 780 }, hasTouch: true })` (no new Playwright project; the mobile project TODO stays open — these are coach screens, not parent routes).
  - Update `frontend/e2e/anthropometry.spec.ts` and `body-composition.spec.ts` for the new entry point ("Guardar y agregar pliegues" now on the review step).
- **Data hygiene**: specs create records on the demo athlete in the isolated DB and delete what they create; no real names in fixtures.
- **Reporting**: e2e results are reported explicitly; if the stack cannot start, say so (CLAUDE.md "deferred real-infra checks").
