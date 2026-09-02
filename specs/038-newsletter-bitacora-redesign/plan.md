# Implementation Plan: Bitácora de etapa (038)

**Feature**: `038-newsletter-bitacora-redesign` · **Spec**: `spec.md` · **Date**: 2026-09-02
**Branch**: `feat/038-bitacora` off `main`, created **after** the 037 working tree is committed (038 imports `InsightV3` / `extract_numeric_tokens` from `app/services/race/insight_v3.py` and reads `athlete_ai_insights.structured_json`).

## Technical context

- Backend: FastAPI, SQLAlchemy 2 async, Jinja (`templates/email`, `templates/documents/pdf`), WeasyPrint (inline SVG supported), Resend SDK (`notification/email_client.py::ResendEmailClient`), AI stack `app/services/ai/` (provider factory, default `google`; use case `use_cases/athlete_monthly_newsletter.py`, prompt `prompts/athlete_monthly_newsletter_v1.j2`, `AthleteNewsletterGuardrails` 80 words/block, static fallback `training/newsletter_static_copy.py`).
- Newsletter pipeline today: `training/newsletter_builder.py::build_newsletter_metrics` → `metrics_snapshot {email_blocks: attendance|technical|race_results|calendar|photos|badges|support_at_home, pdf_only_blocks: anthropometry|…}` → AI narrative (`strengths/area_to_develop/milestone/block_captions/month_highlights`) → `notification/athlete_newsletter_pdf.py` + `newsletter_dispatcher.py`.
- Frontend: React 19, shadcn/ui, Tailwind v4 tokens (`--color-primary #20b7c9`, `--font-display "Cal Sans"`, `--font-body "Inter Variable"`), recharts 3, TanStack Query, RHF + Zod, vitest + MSW + jest-axe, Playwright.
- Parent portal: routes `/my-athletes*`, `/parents/*`; nav in `components/parents/ParentSidebar.tsx` and `ParentBottomNav.tsx`; API `routers/parent_athletes.py` (`GET /my-athletes`).
- Constitution gates: tests mandatory; UX consistency (shadcn primitives, `mode="coach"|"parent"`, status = icon + label); performance budgets (LCP ≤ 2.5 s parent view, email ≤ 100 KB, PDF ≤ 3 pages); youth safeguards (no diagnosis, no ranking vs peers, no outcome goals, anthropometry PDF-only).
- Privacy: prompts anonymised (`athlete_reference`, club forbidden names); parent DTO built server-side through an allow-list; delivery events store provider ids only.

## Architecture

### One content model, three renderers

```
metrics_snapshot (builder v1, + weekly rows)  ─┐
ai_narrative v2 (StageNarrative)              ─┼─▶ stage_log_builder.build_stage_log() ─▶ stage_log_json (StageLog v2)
selected_race_insight_ids → InsightV3 (filtered)┤                                               │
coach: stage_overrides / coach_note / hidden_blocks ┘                                            ▼
                                        ┌────────────────────────────┬─────────────────────────────┐
                                        ▼                            ▼                             ▼
                    React <StageLogView mode=parent|coach>   Jinja email athlete_stage_log   Jinja PDF athlete_stage_log (+ annex)
```

`StageLog` (data-model.md §1) is persisted at generation and re-derived on every PATCH (pure function over snapshot + narrative + overrides). Parent endpoints return it through `to_parent_dto()` (allow-list). Coach endpoints return it plus per-block provenance.

### Deterministic blocks (no AI)

- **Ruta del mes** (`trail_waypoints`): candidates in date order — first session of the month, each race (label "Válida 3 · P2" / "Cto. Departamental · P5"), streak reaching 5 / 10 / 15 consecutive sessions, each badge earned, the session with the highest rubric mean, the next race after month end (`is_future=True`). Keep ≤ 6 by priority race > badge > streak > best session > first session; the next race is always kept last. Each: `{kind, date, label, sublabel, icon}` (lucide icon names).
- **Perfil de esfuerzo** (`effort_profile`): ISO weeks overlapping the month → `{week_label, sessions_planned, sessions_attended, mean_rpe}`; tone sentence from the RPE band (base ≈ 3–5 OMNI, 024 FR-004). Needs per-session rows → builder v1 adds `pdf_only_blocks.weekly` (dates, attended flag, rpe) — no names.
- **Cima del mes** (`summit`): best race result of the month (position, series label, the athlete's own gap % only) else best training milestone; caption from AI (`summit_caption`) or static copy.
- **Próximo tramo**: technical foci of planned sessions in the next 4 weeks grouped by skill family (reuse the 024 grouping) + next race (date, venue, priority label from the calendar).
- **Insignias**: `BADGE_LABELS` map (`attendance_100 → "Asistencia 100 %"`, `attendance_90 → "Asistencia 90 %"`, `attendance_75 → "Asistencia 75 %"`, `top10 → "Top 10"`, `mtp → "Mejor tiempo personal"`, `first_podium → "Primer podio"`) + icon; codes never rendered.

### AI v2 — `athlete_monthly_newsletter_v2`

- Prompt `prompts/athlete_monthly_newsletter_v2.j2` (≈ 700 tokens of instructions): role (the club's coach writing to one family) → **method** (read the data blocks; pick the single strongest fact for `stage_title`; three observations each pinned to a number copied verbatim; summit caption; next segment from planned foci; family compass tied to observations) → 8-line rules → data blocks (attendance, weekly profile, technical foci, races of the month with own gap only, badges, streak, planned foci, next race, previous month's title, analyst headline + action when present) → one fictional worked example → JSON output = `StageNarrative` (data-model.md §2) via structured output when the provider supports it, else JSON parse + one repair retry.
- Guardrails v2 (`StageNarrativeGuardrails`) = v1 (names, medical, comparatives, length) + grounding (`extract_numeric_tokens`) + forbidden phrases (`percentil`, `esperado`, `ranking`, `mejor que`, `por debajo`, `podio`, `ganar`) + overlap with the previous month + `conversation_question` must end with `?`.
- Per-block regeneration: same prompt with `only_block=<name>` and an optional `instruction`; returns only that key; guardrails apply to that block.
- Analyst reading: `family_translation.filter_for_family(InsightV3) -> FamilyInsightInput | None` (deterministic drop list, AC-3.2); the paraphrase is one more key of the same v2 call (`analyst_reading`) → one LLM call per newsletter (two with a repair).
- Static copy v2: one function per block, gender-aware, data-driven sentences; v1 functions stay for legacy rows.

### Coach studio (frontend)

```
┌ Etapa 6 · Junio 2026 · Atleta #2 ── [● Borrador  ○ Aprobado  ○ Enviado  ○ Leído] ── Descargar PDF · Aprobar · Enviar ─┐
│ ┌──── Vista previa ────┐  ┌───────────── Bloques ─────────────────────────────────────┐ │
│ │ [Móvil] Correo  PDF   │  │ ▸ Título de la etapa            IA · 14 palabras     ✎ ↻   │ │
│ │ ┌─────────────────┐  │  │ ▸ Cima del mes                  IA                   ✎ ↻   │ │
│ │ │ 📱 StageLogView  │  │  │ ▸ Lo que vio el entrenador (3)  Editado              ✎ ↻   │ │
│ │ │ mode="coach"     │  │  │ ▸ Lectura del analista [V3 ▾]   IA                   ✎ ↻ 👁 │ │
│ │ │ scrolls          │  │  │ ▸ Próximo tramo                 Estático             ✎ ↻   │ │
│ │ │                  │  │  │ ▸ Brújula de la familia (3)     IA                   ✎ ↻   │ │
│ │ └─────────────────┘  │  │ ▸ Nota del entrenador           Vacío                ✎   👁 │ │
│ └──────────────────────┘  │ ▸ Fotos (0) · Insignias (2)                              👁 │ │
│                           └────────────────────────────────────────────────────────────┘ │
│ ┌ Entrega ── Familia 1 · j***@gmail.com · enviado 3 jul · leído 4 jul 08:12 ── Familia 2 · sin leer · [Reenviar] ┐ │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Clicking a block card scrolls the preview to that block (shared `data-block` anchors); editing merges `stage_overrides` into the `StageLog` client-side (optimistic), then PATCHes; the server re-derives and returns the canonical `stage_log`.
- Tablet-first (coach on the field): ≥ 768 px two columns; narrower → tabs Vista previa / Bloques / Entrega.
- `AnalystPicker`: lists the approved insights attached (label + date); choosing one reorders `selected_race_insight_ids` via PATCH; a note explains what is hidden for families.

### Parent portal

- `ParentNewsletterListPage` (`/my-athletes/:athleteId/bitacora`): one card per stage (period, title, "Nueva" chip).
- `ParentNewsletterPage` (`/my-athletes/:athleteId/bitacora/:newsletterId`): `StageLogView mode="parent"` + "Descargar PDF" + read receipt on mount (once per newsletter, `sessionStorage` guard).
- `TrailRoute.tsx`: responsive inline SVG (horizontal ≥ 480 px, vertical below), `<title>`/`<desc>` plus a visually hidden `<ol>` of waypoints. The same path builder is ported to a Jinja macro (`_trail.svg.j2`) for the PDF; the email uses a table-based list (no SVG).

### Visual language

- Base: existing tokens — teal accent, charcoal / mid-gray text, Cal Sans for the stage title, Inter body, status vocabulary via `StatusBadge`.
- Bitácora layer (newsletter surfaces only, `data-surface="bitacora"`): topographic-line background at ~4 % opacity, dashed trail stroke in `--color-primary`, waypoint discs in charcoal with a teal ring, "cima" waypoint drawn as a triangle. One warm earth tone `--color-trail-earth` (`#b86b3c`, AA for large text on white) is proposed **only** for the trail terrain and the summit chip; it is a documented exception to design-system §2 to be validated by `ux-researcher` in T301 — fall back to teal tints if rejected.
- Never color-only: every waypoint and status carries icon + label.

### Modules

| Module | Responsibility |
|---|---|
| `app/services/training/stage_log.py` (NEW) | `StageLog`, `StageNarrative`, block models, `BlockState`; `to_parent_dto()` allow-list; `BADGE_LABELS`. |
| `app/services/training/stage_log_builder.py` (NEW) | `build_stage_log(snapshot, narrative, family_input, overrides, coach_note, hidden_blocks, athlete_sex, athlete_first_name) -> StageLog`; pure helpers `trail_waypoints()`, `effort_profile()`, `summit()`, `next_segment()`, `stage_number()`. |
| `app/services/training/newsletter_builder.py` | Adds `pdf_only_blocks.weekly` (per-session date / attended / rpe) and `next_focus_groups` (planned sessions, 4 weeks). No other change. |
| `app/services/training/family_translation.py` (NEW) | `filter_for_family(InsightV3) -> FamilyInsightInput | None`; `select_insight(db, newsletter, consent) -> tuple[int, InsightV3] | None` (approved, active, `structured_json`, event in month, first in `selected_race_insight_ids`). |
| `app/services/ai/use_cases/athlete_monthly_newsletter_v2.py` + `prompts/athlete_monthly_newsletter_v2.j2` (NEW) | Structured narrative, `regenerate_block()`, `StageNarrativeGuardrails`, grounding via `race.insight_v3.extract_numeric_tokens`. Registry entry `athlete_monthly_newsletter_v2`. |
| `app/services/training/newsletter_static_copy.py` | v2 functions (`static_stage_title`, `static_observations`, `static_summit_caption`, `static_next_segment`, `static_family_compass`); v1 kept. |
| `app/services/notification/athlete_newsletter_pdf.py` | `generate_stage_log_pdf(...)`; annex rule (anthropometry only if measured in the month; season charts only if a race in the month); v1 path untouched. |
| `templates/email/athlete_stage_log.html`, `templates/documents/pdf/athlete_stage_log.html`, `templates/documents/pdf/_trail.svg.j2` (NEW) | Renderers; registered in `template_registry.py`. |
| `app/services/notification/newsletter_dispatcher.py` | Picks v2 templates when `content_version == 2`; deep link when the parent user is active; writes a `sent` row per recipient in `newsletter_delivery_events` with `provider_message_id` (Resend response id; SMTP → null). |
| `app/routers/athlete_monthly_newsletters.py` | DTO + PATCH extensions; `POST …/{id}/regenerate-block`; `GET …/{id}/render?surface=email` (HTML, coach only); `POST …/{id}/convert` (v1 draft → v2); generation writes v2 when `NEWSLETTER_CONTENT_VERSION == 2`. |
| `app/routers/parent_newsletters.py` (NEW) | Mounted at `/api/parents/me/athletes/{athlete_id}/newsletters`: list, detail, pdf, read. Parent role + link check; coach/admin → 403. |
| `app/routers/webhooks_resend.py` (NEW, P3) | Svix signature verification (`RESEND_WEBHOOK_SECRET`), idempotent on `svix-id`, maps `data.email_id` → events. 404 when the secret is empty. |
| `alembic/versions/<rev>_newsletter_stage_log.py` | Columns + `newsletter_delivery_events`; `down_revision = "f7a8b9c0d1e3"`. |
| `app/config.py` | `newsletter_content_version: int = 2`, `resend_webhook_secret: str = ""`; deep links reuse the existing frontend base URL setting used by the invite flow. |
| Frontend `types/stageLog.types.ts`, `schemas/stageLog.ts` (Zod), `api/athleteNewsletters.ts`, `api/parentNewsletters.ts` (NEW), hooks `useRegenerateBlock`, `useUpdateStageLog`, `useParentNewsletters`, `useParentNewsletter`, `useMarkNewsletterRead` | Contract mirror + data layer; MSW handlers + `fixtures/stageLog.ts` (3 fixtures: full month, no-race month, zero-attendance month). |
| Frontend `components/newsletter/StageLogView.tsx` + blocks (`StageHeader`, `TrailRoute`, `SummitCard`, `ObservationsList`, `AnalystReading`, `EffortProfile`, `NextSegment`, `FamilyCompass`, `BadgesRow`, `PhotosGrid`, `CoachNote`) (NEW) | Shared renderer, `mode` prop, `data-block` anchors, `EffortProfile` on recharts (dataviz skill palette rules). |
| Frontend `routes/training/AthleteNewsletterStudioPage.tsx` + `components/newsletter/studio/*` (`DevicePreview`, `EmailPreviewFrame`, `BlockPanel`, `BlockCard`, `RegenerateDialog`, `AnalystPicker`, `DeliveryPanel`, `StatusStepper`) (NEW) | Replaces `AthleteNewsletterDetailPage` for v2; v1 rows keep the old page (route decides by `content_version`). |
| Frontend `routes/parents/newsletters/ParentNewsletterListPage.tsx`, `ParentNewsletterPage.tsx` (NEW); `ParentSidebar.tsx`, `ParentBottomNav.tsx`, `ChildCard` | Parent surfaces, nav entry, "Nueva bitácora" chip (from `GET /my-athletes` gaining `unread_newsletters: int`). |

### Compatibility & rollout

- `content_version` defaults to 1 for existing rows; new generations write 2; templates, DTOs and pages branch on it. `NEWSLETTER_CONTENT_VERSION=1` is the rollback switch.
- `POST /batch` unchanged (produces v2). `attach-insights` unchanged; the studio reorders `selected_race_insight_ids`.
- `outdated` handling unchanged; "Convertir a bitácora" only for `draft` v1 rows.

## Risks & mitigations

- WeasyPrint SVG text/fonts → trail labels are HTML positioned over the SVG path (no `<text>` in SVG); snapshot test asserts page count ≤ 3 and no empty page.
- Email clients strip `<svg>` → table-based waypoint list; manual checklist in MailHog + Gmail Android.
- Gemini structured output rejects nested schema → JSON parse + one repair retry → static copy per block; generation never fails.
- Read-receipt false positives → receipt only when `current_user.role == parent`; coach preview never calls it.
- Open-tracking privacy → webhook P3, off by default; if enabled, the parents' privacy text mentions delivery tracking.
- 037 uncommitted on `main` → 038 branch after 037 lands; `family_translation.py` depends on `InsightV3`.
- Free-tier RPM → one LLM call per newsletter; batch keeps the existing sequential loop.

## Phases

1. **Wave 1 — content model & data** (parallel, disjoint files): `stage_log.py` + builder + weekly rows + badge labels; migration + model + DTO/PATCH; `family_translation.py`; static copy v2.
2. **Wave 2 — AI v2 + delivery** (parallel): prompt/use case v2 + guardrails + regenerate/convert endpoints; parent router + read receipt + `unread_newsletters`; email v2 + PDF v2 + dispatcher; frontend contract (types, Zod, api, hooks, MSW, fixtures).
3. **Wave 3 — UI** (parallel): `StageLogView` + blocks + `TrailRoute`; coach studio; parent pages + nav + chip.
4. **Wave 4 — quality**: Resend webhook (P3); `data-privacy-guard` audit; a11y + perf checks; docs (`docs/06-parents/038-bitacora.md`, `docs/implementation-status.md`, `docs/technical-notes.md`, CLAUDE.md "most recent feature" block); SC-1 regeneration on the local DB (aggregate report).

## Verification (quickstart)

```bash
cd backend && source .venv/bin/activate && pytest && ruff check
cd frontend && npm run typecheck && npm test
# manual: docker compose up → generate June for one athlete → studio → approve → send → MailHog (:8025) shows v2 email
# parent: log in as a linked parent → /my-athletes/<id>/bitacora → read receipt visible in the studio's Entrega panel
```
