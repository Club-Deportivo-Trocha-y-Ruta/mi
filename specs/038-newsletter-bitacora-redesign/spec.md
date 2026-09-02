# Feature Specification: Bitácora de etapa — family newsletter redesign (web + email + PDF)

**Feature**: `038-newsletter-bitacora-redesign` · **Created**: 2026-09-02 · **Status**: direction approved by coach (interview 2026-09-02), spec draft
**Supersedes the presentation contract of** `specs/003-improve-individual-newsletter-pdf` (US3–US4) and `specs/024-newsletter-audit-fixes` (FR-006..FR-014). Keeps their data fixes, privacy rules (anthropometry PDF-only, no names to the provider, static fallback when AI consent is missing, gender from `Athlete.sex`) and the batch → approve → send lifecycle.

## Problem statement

Coach verdict on `/training/athlete-newsletters/2/6` and the June 2026 deliverable: "no me está aportando valor agregado". Evidence (2026-09-02, screenshot + code):

1. **The preview is not the deliverable.** The coach page stacks seven flat cards (`NewsletterPreviewBlocks.tsx`) that resemble neither the email nor the PDF the family receives. The narrative editor is three textareas (`NewsletterNarrativeEditor.tsx`: Fortalezas / Área a desarrollar / Hito del mes), each preceded by a read-only copy of the same AI text.
2. **Generic narrative.** `prompts/athlete_monthly_newsletter_v1.j2` is ~20 lines of prohibitions and zero method; output = 3 blocks of 2–3 sentences ("compromiso excepcional… base sólida para su progreso") plus a `month_highlights` sentence that is boilerplate ("Este mes combinó entrenamiento y competencia: una gran oportunidad…"). Same diagnosis as 037 §2.
3. **Empty and raw blocks ship.** "Calendario: Sin información de calendario disponible" and "Fotos: Sin fotos etiquetadas este mes" render as sections; badges show codes (`attendance_100`, `top10`).
4. **"Cómo apoyar desde casa" is static.** Four tips rotated deterministically per month (024 FR-014); nothing in them comes from this athlete's month.
5. **The best analysis never reaches families.** `POST …/monthly-newsletters/attach-insights` (036) persists `selected_race_insight_ids`, but no builder, template or prompt reads it (only the router and its schema reference the column). The 037 InsightV3 (headline, grounded observations, catalog-linked actions) is invisible to parents.
6. **The PDF is a technical report, not a newsletter.** 11 sections in a 902-line template: coach narrative, attendance, technical, race table, three season charts, anthropometry table with z-scores, percentile curves, gallery, upcoming activities. The email is a wrapper for the attachment. Parents have **no web surface**: all routes in `routers/athlete_monthly_newsletters.py` are `require_role([admin, coach])`; the parent portal (`/my-athletes`, `/parents/*`) has no newsletter entry.
7. **No feedback loop.** After `send`, the only trace is `sent_to` (emails). The coach cannot tell whether a family opened or read it.

## Coach decisions (interview 2026-09-02)

| Question | Decision |
|---|---|
| Primary surface | **Web mobile view in the parent portal + short email + PDF**, one shared design and one shared content model |
| Creative concept | **Bitácora de ruta**: the month is a stage ("etapa") of the season route — waypoints, effort profile, summit, next segment |
| New content | (a) the 037 analyst finding translated to family language; (b) "Rincón de la familia" (question to talk about at home, monthly challenge, what to watch at the next válida) replacing generic tips |
| Declined content | Technique-skill map (A–H) and athlete's own voice — out of scope for 038 |
| Coach pain to solve | Live preview of what the family sees; per-block editing/regeneration instead of three textareas; delivery/read feedback per family |
| Not requested | Review queue ("next athlete") — out of scope |

## Vocabulary (product copy, español neutro)

| Term | Meaning |
|---|---|
| **Bitácora de etapa** | The monthly newsletter itself |
| **Etapa** | The month ("Etapa 6 · Junio 2026"; number = months since the first session of the season) |
| **Ruta del mes** | Trail visual with waypoints (hitos) |
| **Perfil de esfuerzo** | Weekly attendance/RPE bars (the "altimetría") |
| **Cima del mes** | The single highlight (race result or training milestone) |
| **Lo que vio el entrenador** | Three grounded observations (replaces Fortalezas / Área / Hito) |
| **Lectura del analista** | Family-safe translation of the attached InsightV3 |
| **Próximo tramo** | Next weeks: planned technical foci + next race |
| **Brújula de la familia** | Rincón de la familia: pregunta para conversar, reto del mes, qué observar |
| **Nota del entrenador** | Optional first-person note typed by the coach |
| **Anexo de crecimiento** | Anthropometry annex (PDF only, only when measured in the month) |

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A family reads the month as a stage of a route (P1)

As a parent, from my phone, I open "Bitácora" in the portal and in under a minute I understand what my child did this month, what stood out and what comes next.

**Acceptance**
- AC-1.1 New parent routes `/my-athletes/:athleteId/bitacora` (list) and `/my-athletes/:athleteId/bitacora/:newsletterId` (detail). The detail renders `StageLog` blocks in this order: stage header, ruta del mes, cima del mes, lo que vio el entrenador, lectura del analista (when present), perfil de esfuerzo, próximo tramo, brújula de la familia, insignias (when earned), fotos (when any), nota del entrenador (when present). Blocks without data are **not rendered** — no "sin información" placeholders on any parent surface.
- AC-1.2 Only newsletters in status `sent` are visible to parents; a parent sees only their linked athletes (existing `parent_athletes` link); any other athlete or newsletter → 404.
- AC-1.3 Ruta del mes shows 3–6 waypoints derived deterministically from the month (first session, race(s), streak milestone, badge, best-rubric session, next race) with icon + label + date; no AI involved.
- AC-1.4 Mobile-first (360 px), WCAG AA, jest-axe zero violations; status never conveyed by color alone; the trail visual has a text alternative (ordered list) for screen readers.
- AC-1.5 The parent dashboard child card shows a "Nueva bitácora" chip until the newsletter is read; `ParentSidebar` and `ParentBottomNav` gain a "Bitácora" entry.

### User Story 2 — The narrative is specific, grounded and short (P1)

**Acceptance**
- AC-2.1 AI use case v2 returns a structured `StageNarrative`: `stage_title` (≤ 20 words, never a template phrase), `observations[3]` each `{claim ≤ 35 words, evidence ≤ 20 words containing ≥ 1 number, block_ref}`, `summit_caption` (≤ 25 words), `next_segment_text` (≤ 40 words), `family_compass {conversation_question, monthly_challenge, what_to_watch}` (each ≤ 30 words, each referencing an observation or the next segment).
- AC-2.2 Deterministic grounding: every number in `evidence`, `stage_title` and `summit_caption` exists in the prompt context (reuse `race/insight_v3.py::extract_numeric_tokens`). A violation replaces that block with static copy and records `grounding_violations[]` on the newsletter for the coach.
- AC-2.3 Existing guardrails stay (club forbidden-names redaction, medical/supplement block, no negative comparatives, ≤ 80 words per block, gender from `Athlete.sex`). New: no percentile / ranking / expected-position language, no other minor, no outcome goals ("podio", "ganar").
- AC-2.4 Two consecutive months of the same athlete never share `stage_title` (exact) nor exceed 85 % token overlap in observations (checked against the previous newsletter's `stage_log_json`).
- AC-2.5 When AI consent is missing or the provider fails, `newsletter_static_copy` v2 fills every narrative block from the data (e.g. "Asistió a 14 de 14 sesiones") and the analyst block is omitted; generation still succeeds (003 decision preserved).

### User Story 3 — The analyst finding reaches families safely (P1)

**Acceptance**
- AC-3.1 When the newsletter has `selected_race_insight_ids` whose insight is approved (`is_active`, HITL approved), the athlete has AI-processing consent, the insight has `structured_json`, and its race event falls in the newsletter month, the builder derives `analyst_reading {headline_family, action_family, valida_label, source_insight_id}` from the **first** eligible selected insight; the coach can pick another one in the studio.
- AC-3.2 Deterministic filter before any LLM call (`family_translation.filter_for_family`): drop `field_reading`, `coach_question`, `watch_signals`, `data_gaps`, `derived_from`, every observation with domain `field`, every action with priority `low`. Only `headline` + the highest-priority remaining action reach the paraphrase step.
- AC-3.3 The paraphrase (part of the same v2 LLM call) rewrites headline + action for a parent — no jargon ("gap", "P3", "percentil"), ≤ 45 words total; US2 grounding and guardrails apply; on failure the block is omitted, never shown raw.
- AC-3.4 The parent DTO never contains `structured_json`, `source_insight_id`, other athletes' identifiers or field metrics (test asserts the exact key set).

### User Story 4 — The coach edits with the family's eyes (P1)

**Acceptance**
- AC-4.1 `/training/athlete-newsletters/:athleteId/:id` becomes the **studio**: left = live preview of the same `StageLogView` the parent sees, inside a phone frame, with a toggle Móvil / Correo / PDF (Correo = server-rendered email HTML in a sandboxed iframe; PDF = existing download); right = block panel.
- AC-4.2 Every narrative block is a card with state (`IA` / `Editado` / `Estático` / `Oculto` / `Vacío`), inline edit, word counter, "Regenerar" (per block, optional instruction ≤ 200 chars such as "más corto" or "menciona la lluvia") and "Ocultar" for optional blocks (analyst, photos, badges, coach note). Edits persist as `stage_overrides[block]`.
- AC-4.3 "Nota del entrenador": free text ≤ 60 words, first person, optional; passes the name-redaction guard before persisting.
- AC-4.4 Status stepper Borrador → Aprobado → Enviado → Leído; approve/send keep their current confirmations; `outdated` shows a "Regenerar datos" call to action.
- AC-4.5 Any edit marks the PDF hash stale (existing `pdf_sha256` logic) so "Descargar PDF" regenerates; the preview updates optimistically.

### User Story 5 — Email and PDF share the design (P2)

**Acceptance**
- AC-5.1 Email v2 (`templates/email/athlete_stage_log.html`): stage header, stage title, ruta del mes as a table-based waypoint list, cima del mes, first observation, CTA "Ver la bitácora completa" → portal deep link when the parent has an active account, else "Activa tu cuenta" (existing invite flow); PDF still attached. ≤ 100 KB, single column, no external fonts, dark-mode safe; existing multi-child grouping (`_group_by_parent`) preserved (one section and one PDF per child).
- AC-5.2 PDF v2 (`templates/documents/pdf/athlete_stage_log.html`): A4, ≤ 3 pages. Page 1: header + trail (inline SVG) + cima + observaciones. Page 2: analista + perfil de esfuerzo + próximo tramo + brújula + insignias/fotos + nota. Page 3 ("Anexo de crecimiento") **only** when an anthropometric record dated in the month exists (reusing the 003/024 table + pedagogy); the three season charts move to that annex and appear only when a race happened in the month. `break-inside: avoid` on every block; no page more than 30 % blank except the last.
- AC-5.3 Anthropometry and season charts never appear in email or web (003 decision; enforced by tests).

### User Story 6 — The coach knows who read it (P2)

**Acceptance**
- AC-6.1 `POST /api/parents/me/athletes/{athlete_id}/newsletters/{id}/read` (idempotent, parent role only) records `read_at` and `read_by_user_id`; the web view calls it on first successful render.
- AC-6.2 Studio "Entrega" panel lists each recipient family: Enviado (date), Leído en la web (date) or "Sin leer", "Sin cuenta web" when the parent has no active account, and "Reenviar" (existing `force_resend`). Emails are shown masked (`j***@gmail.com`).
- AC-6.3 (P3) Resend webhook `POST /api/webhooks/resend`, verified with the Svix signature, stores `email.delivered`, `email.opened`, `email.clicked`, `email.bounced` in `newsletter_delivery_events` keyed by the provider message id saved at send time; surfaced as "Correo entregado / abierto / rebotado". Open tracking is best-effort (pixel blocked by Apple Mail Privacy Protection) and never the only read signal. Disabled unless `RESEND_WEBHOOK_SECRET` is set.

### User Story 7 — Legacy newsletters keep working (P3)

- AC-7.1 Newsletters with `content_version = 1` (no `stage_log_json`) keep rendering with the v1 templates and the v1 detail page; the studio offers "Convertir a bitácora" (rebuild snapshot + narrative v2) for drafts only.

## Edge cases

- Month with no race → cima del mes = best training milestone (streak, badge, rubric peak); analyst block absent; próximo tramo still shows the next race from the Copa Valle calendar.
- Month with zero attendance → stage title from static copy ("Etapa de pausa"); trail shows only the next race; no shaming copy (024 principle).
- Parent without an active account (invite pending) → email + PDF only; CTA "Activa tu cuenta"; delivery panel shows "Sin cuenta web".
- Family with two athletes → two bitácoras, one email with two sections (existing grouping).
- Insight attached but rejected / pending HITL / event outside the month → analyst block omitted.
- Photos without consent or tag → block omitted (never a placeholder).
- Newsletter generated for the current month (batch flag) → header reads "Etapa en curso"; send behaviour unchanged.
- Coach opens the parent view → no read receipt (parent role only).

## Success Criteria *(mandatory)*

- SC-1 Regenerating the June 2026 newsletter of the screenshot athlete on the local DB yields: a non-template stage title, 3 observations each with ≥ 1 grounded number, a family compass whose three items reference an observation or the next segment, zero empty blocks, PDF ≤ 3 pages. Same holds for ≥ 5 other active athletes with ≥ 1 session in the month (aggregate report only, no names).
- SC-2 Parent web view LCP ≤ 2.5 s under "Fast 3G" throttling with a warm bundle; jest-axe zero violations on the parent page and the studio; email HTML ≤ 100 KB.
- SC-3 Coach path draft → sent for one athlete in ≤ 5 interactions in the studio (open, review preview, one edit, approve, send).
- SC-4 `data-privacy-guard` audit passes: parent DTOs and templates contain no other minor's data, no field-relative metrics, no anthropometry outside the PDF annex; prompts carry no names.
- SC-5 100 % of pre-existing newsletters (content_version 1) still render in preview, email and PDF (regression test with a v1 fixture).
- SC-6 A read receipt is recorded for a test family locally and the delivery panel reflects it after one refetch.

## Out of scope

- Technique-skill map and athlete self-report (declined 2026-09-02).
- Review queue / "next draft" navigation; push notifications; WhatsApp/SMS delivery.
- Public or social sharing of any bitácora (minors' privacy): no share buttons, no public links.
- Changes to anthropometry computation or to the AI-consent gate on generation (tracked separately).
- Season-end "bitácora de temporada" (natural follow-up once 038 ships).
