# Research — Newsletter Audit Fixes (024)

**Date**: 2026-07-08
**Sources**: 3 parallel codebase exploration agents + Context7 (WeasyPrint official docs) + `docs/01-marco-teorico.md`.

All Technical Context unknowns resolved. Findings below drive the design in `plan.md` / `data-model.md`.

## R1. Championship label bug (A1)

**Decision**: Template-only fix. The compact KPI card at `backend/templates/documents/pdf/athlete_monthly_newsletter.html:245` renders `V{{ last_race.valida_num or "—" }}`; championships carry `sequence_number=1` (spec 014) so they collide with Válida I. The snapshot already serializes `label` (readable) per result (`newsletter_builder.py:512`) and `progression_history` items carry short labels via `_race_short_label` (`newsletter_builder.py:57-74`). Add a `short_label` field to month results (same helper) and render `{{ last_race.short_label }}` in the card; tables already use `r.label` correctly (`:519`, `:552`). Email template fallback `('Válida ' ~ r.valida_num)` at `templates/email/athlete_monthly_newsletter.html:196` is safe because `r.label` is always set for new snapshots, but keep the fallback for old snapshots (FR-015).

**Rationale**: Reuses existing, tested labeling helpers; zero data-model risk.
**Alternatives considered**: Recomputing label in template Jinja (rejected: duplicates spec-014 logic in a second language).

## R2. AI narrative gender (A2)

**Decision**: Pass a *grammatical-gender hint* into the prompt context — not the raw enum. `Athlete.sex` exists (`models/athlete.py:31-34,54`, enum `M`/`F`) but is nullable-in-practice for older rows; the AI context (`use_cases/athlete_monthly_newsletter.py:263-280`) contains no sex today. Add `athlete_reference: "su hijo" | "su hija" | "su hijo/a"` (derived in `build_context_from_metrics`) and instruct the template (`prompts/athlete_monthly_newsletter_v1.j2`) to use that exact form and matching agreement. Static fallback (`newsletter_static_copy.py`) is already gender-neutral by design — keep neutral. The support-block "hijo/a" (`newsletter_builder.py:701`) also becomes gender-aware via the same derived string.

**Rationale**: Sending a pre-derived Spanish reference string keeps the prompt simple, avoids the LLM inferring gender, and adds no PII beyond a single pronoun class (no name, no DOB — consistent with `test_newsletter_privacy.py` invariants, which do not forbid sex).
**Alternatives considered**: (a) Post-processing regex swap of "hijo"→"hija" (rejected: fragile agreement — "comprometido", "él"); (b) always neutral "su hijo/a" (rejected: user explicitly wants correct gender when known; neutral only as fallback).

## R3. Gallery empty in PDF (A3)

**Decision**: Embed thumbnails as base64 data URIs, reusing the spec-022 pattern. Root cause confirmed: `document_generator.py:143-146` renders with `HTML(string=..., base_url=templates_root)` and **no custom url_fetcher**; `<img src="{{ photo.thumbnail_url }}">` (`athlete_monthly_newsletter.html:767-769`) points at Hostinger URLs WeasyPrint cannot fetch from Render. Per WeasyPrint official docs (Context7): fetch errors on images are caught and logged as warnings — the img silently renders empty, which is exactly the observed symptom (section header + consent text, no images). `reports.py:430-550` (`build_report_photo_evidence`) already solves this: SFTP `download_to_tempfile` → base64 → `data_uri`, with a 2 MB total budget and graceful degradation. Extract/reuse that download-and-encode step at **PDF render time** (not snapshot time — data URIs must never be persisted into `metrics_snapshot`, it would bloat the DB row). Section gate becomes three-state: no eligible photos → omit section; eligible but zero embeddable → placeholder with count; ≥1 embeddable → render images (skip failed ones).

**Rationale**: Proven in-repo pattern; respects Render free-tier memory via existing byte budget; keeps snapshot slim.
**Alternatives considered**: (a) custom `URLFetcher` with Hostinger auth (rejected: WeasyPrint fetches over HTTP, media is SFTP-backed; also leaks credentials into render path); (b) persisting data URIs in snapshot (rejected: multi-MB JSON rows, dispatcher email-privacy pop lists would need widening).

## R4. RPE reference text (A4)

**Decision**: Replace static "1-10 (ideal 6-7 para entrenamiento base)" (`athlete_monthly_newsletter.html:455-457`) with "0-10 (base: 3-5 · alta intensidad: 6-8)". Marco teórico: OMNI 0-10, base = Z1-Z2 conversational (`docs/01-marco-teorico.md:59,251-253`); frontend `RPE_LABELS` (`RubricSliders.tsx:9-21`) confirms 6="Algo duro", 7="Duro" (Z3-Z4). Also fix the scale floor: OMNI is 0-10, not 1-10.

**Rationale**: Aligns with validated OMNI mapping and 80/20 principle; static template string, no logic.
**Alternatives considered**: Phase-aware dynamic reference by mesocycle (rejected for this feature: mesocycle not in snapshot; noted as future idea).

## R5. LTAD weekly-hours compliance (A5)

**Decision**: Compute in builder (`_build_technical_block`): `weekly_hours_avg = total_hours / (days_in_month / 7)` (≈4.33 weeks), `ltad_limit_hours = age_decimal at generation date` via `compute_age_decimal(athlete.birth_date, generation_date)` (`services/category.py:6`), `ltad_status = "ok" | "review"` (`weekly_hours_avg ≤ ltad_limit`). Template shows "X,X h/sem (límite personal: ≤Y h/sem) ✓". Zero-session months: fields null, template falls back to current display without comparison.

**Rationale**: Age helper exists and takes explicit reference date; spec assumption already fixes the 4.33 constant; presentation-only compliance state (green/amber per constitution color semantics).
**Alternatives considered**: Weeks-with-sessions denominator (rejected: unstable for sparse months; spec edge case pins calendar weeks).

## R6. Focus grouping by skill family (B6)

**Decision**: New pure helper `backend/app/services/training/focus_grouping.py`: keyword mapping from free-text `technical_focus` to presentation families. Families = the 8 canonical A–H skills from `technique_catalog.SKILLS` (`app/data/technique_catalog.py:88-145`: posicion, vision, frenado, control_baja_velocidad, curvas, separacion, presion_terreno, cambios_cadencia) **plus** two presentation-only buckets: "Resistencia y acondicionamiento" (Zona 2, Vo2, intervalos, fuerza) and "Otros". No structured link exists today — `technical_focus` is a raw string counted literally (`metrics.py:79-81`); mapping must be keyword-based (accent-insensitive, lowercase substring sets per family). Builder emits `focus_groups: [{slug, name, session_count}]` alongside the existing `focos_tecnicos` (kept for backward compat / AI prompt).

**Rationale**: A–H taxonomy is seeded and canonical; physiological foci (Zona 2, Vo2) are not bike skills, so they need a conditioning bucket — forcing them into A–H would be wrong. Pure function = trivially testable.
**Alternatives considered**: (a) LLM classification (rejected: determinism required, AI optional per consent); (b) retagging sessions with FK to skills (rejected: schema migration + backfill, out of scope).

## R7. Category code labels (B7)

**Decision**: Resolve labels from the existing `race_categories.label` column (model `race_category.py:63`, seeded with 26 official codes in `scripts/seed_race_categories.py:39-68`, e.g. `PJUV_A_F` → its seeded label). The progression DataFrame already carries `category_code`; extend the analytics join (or a builder-side lookup) to fetch `label`; serialize `category_label` per result. Unmapped/missing → show raw code (FR-007).

**Rationale**: DB is the source of truth — no hardcoded dict to drift. Note: `services/category.py:22` `get_category` is the FCC *club* category (different labels); do not confuse the two.
**Alternatives considered**: Hardcoded backend dict (rejected: seed already exists; duplication).

## R8. Spanish date formatting (B8)

**Decision**: Promote a shared helper `format_date_es(d) -> "1 de agosto de 2026"` into a small util (source pattern: `race_insight_dispatcher.py:135-151` `_MONTHS_ES` dict — locale-independent). Use it in the newsletter PDF/email contexts for: next válida, planned sessions, race result dates, anthropometry dates. `babel` is NOT a dependency and `strftime("%B")` is locale-fragile (seen in `calendar/notifications.py:67-72`) — avoid both.

**Rationale**: Existing proven pattern; no new dependency (Render free tier, minimal image).
**Alternatives considered**: Adding `babel` (rejected: dependency for one function).

## R9. Page-1 reflow (B9)

**Decision**: Root cause is not a page-break rule but atomic `break-inside: avoid` on the whole coach-assessment card (`athlete_monthly_newsletter.html:331`) — if the full card doesn't fit after the badges strip, WeasyPrint pushes it entirely to page 2. Fix: drop `break-inside: avoid` from the card wrapper, keep `break-after: avoid` on its `h2` (title never orphaned) and `break-inside: avoid` only on each of the three inner subsections (fortalezas/área/hito).

**Rationale**: Preserves "no orphaned heading" while letting content flow into page 1.
**Alternatives considered**: Reordering sections (rejected: approved document order).

## R10. SVG label clipping (B10)

**Decision**: In the three chart macros (`templates/documents/pdf/charts/{gap_pct,points_accumulated,line_positions}.svg.jinja`): raise `pad_top` from 8 to ~16 and clamp label `y` to `max(pad_top - 2, cy - 6)`. Labels are drawn at fixed `cy-5/6` offsets which exit the viewBox for points near the top edge (position 1, max points, low gap).

**Rationale**: Two-line change per macro; no data change; SVG privacy test (no title/desc/metadata) untouched.

## R11. Anthropometric table headers (B11)

**Decision**: In the anthro table CSS (`athlete_monthly_newsletter.html:620-655`): remove `overflow-wrap: anywhere; word-break: break-word` from `th`, widen the narrow `<colgroup>` columns (IMC 7%→9%, Z/P 9%→10%, compensating from Fecha/Maduración), and use explicit two-line headers (`Z-<br>Talla`) where wrap is intended.

**Rationale**: `table-layout: fixed` + anywhere-wrap is what produces "IM C"/"ZTallaPTalla"; controlled breaks restore legibility at 7.5pt.

## R12. Streak dedup + naming (B12)

**Decision**: PDF shows streak once — keep the KPI card, drop the duplicated "Racha de asistencia consecutiva" line; label "sesiones seguidas". Rename snapshot key `streak_days` → `streak_sessions` with template-side backward-compat read (`streak_sessions if defined else streak_days`) for old snapshots (FR-015). **Contract note found**: frontend `NewsletterPreviewBlocks.tsx:95-146` already consumes `streak_sessions` while backend emits `streak_days` — today's preview reads a missing key; the rename FIXES a live frontend/backend mismatch. AI prompt context key (`registry.py:143`, `.j2:38`) updates in the same pass. Also delete the duplicated `_compute_streak` in `newsletter_builder.py:366` in favor of the badge evaluator's (`badge_evaluator.py:75`) if signatures align; otherwise document why two exist.

**Rationale**: One render site, one key, one helper; fixes an existing latent bug.

## R13. Championship no-points note (B13)

**Decision**: Mirror spec-022's implementation: the report groups jornadas with an `awards_points` flag and renders "(No otorga puntos)" (`reports.py:586-610`, `training_monthly_report.html:445`, rationale in `competition_results.py:21`). For the newsletter: `_build_charts_context` already receives `series_kind` per history row — set `has_championship = any(kind == 'championship')` and render a one-line footnote under the points chart: "Los campeonatos no otorgan puntos de Copa; la línea se mantiene en esas fechas."

**Rationale**: Same domain rule, same wording family, presentation-only.

## R14. Age-banded, month-rotated support tips (B14)

**Decision**: `_build_support_block(age_decimal, month, athlete_reference)`: (a) select band 10-12 vs 13-15 by `age_decimal` (cutoff <13 → 10-12 band; matches project age-group definitions); (b) per category keep a small list of 2-3 tip variants and pick `variants[month % len]` — deterministic, same month+athlete → same text (spec assumption); (c) reuse the R2 `athlete_reference` for "hijo/a" occurrences. All variants preserve non-negotiables: zero supplements, no calorie counting, food-first. Support block renders in PDF only (email has no support section — confirmed), so email templates unchanged for this item.

**Rationale**: Builder already loads the full Athlete (birth_date available); pure-function rotation keeps regeneration reproducible.
**Alternatives considered**: Random rotation (rejected: breaks determinism/regeneration equality), AI-generated tips (rejected: static content is a privacy-safe, review-once surface).

## R15. Backward compatibility of persisted snapshots (FR-015)

**Decision**: All new snapshot fields are additive and optional; templates guard with `is defined` / `get(...)` fallbacks (existing house style, e.g. `narrative.get('block_captions') or eb.get(...)`). No Alembic migration. `ai_narrative` remains its own JSON column (router `athlete_monthly_newsletters.py:285,302`) — unchanged shape plus nothing removed. Regression guard: render one pre-024 snapshot fixture through both templates in tests.

## R16. Privacy invariants that constrain this feature

From `test_newsletter_privacy.py` + `test_newsletter_ai_captions.py` (must keep green):
- No real names in AI prompt/captions; `forbidden_names` scrub stays.
- Anthropometry & `pdf_only_blocks` never in email/schema; dispatcher pops stay.
- SVG charts carry no `title/desc/metadata/data-*`.
- Email subject without athlete name; batch errors without "@".
- New: data URIs must not enter `metrics_snapshot` or email blocks (render-time only) — add explicit test.
- Sex-derived `athlete_reference` is a pronoun class, not PII beyond existing PDF content; still: never log it with athlete id + name.
