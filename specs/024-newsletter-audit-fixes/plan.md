# Implementation Plan: Newsletter Audit Fixes — Boletín Mensual Individual

**Branch**: `024-newsletter-audit-fixes` | **Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/024-newsletter-audit-fixes/spec.md`

## Summary

Fix 5 confirmed data/correctness bugs (championship mislabeled as "V1", wrong grammatical gender in AI narrative, empty gallery section, misleading RPE reference, monthly-vs-weekly LTAD comparison) and 9 presentation improvements (grouped technical foci, readable category labels, Spanish dates, page-1 reflow, SVG label clipping, anthro table headers, streak dedup/rename, championship no-points note, age-banded rotating support tips) in the individual monthly newsletter (parent-facing PDF + email). Approach: builder-side additive snapshot fields + template fixes + one new pure helper (focus grouping) + reuse of the spec-022 base64 photo-embedding pattern at PDF render time. No DB migration; full backward compatibility with persisted snapshots.

## Technical Context

**Language/Version**: Python 3.14 (backend); TypeScript / React 19 (frontend preview, minor)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Jinja2, WeasyPrint (PDF), pandas (race analytics), Gemini via AI service layer (optional, consent-gated)

**Storage**: MySQL 8.4 — no schema change; additive JSON fields inside existing `metrics_snapshot` / `ai_narrative` columns

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend); vitest + Testing Library + jest-axe (frontend preview)

**Target Platform**: Render free tier (Docker, Oregon) backend; parent email clients + PDF readers

**Project Type**: Web application (backend service + templates; small frontend touch)

**Performance Goals**: Newsletter generation stays within current envelope; photo embedding bounded by existing 2 MB total budget (spec-022 pattern) to respect Render free-tier memory

**Constraints**: No Alembic migration; persisted snapshots (pre-024) must render without error; email must never receive anthropometry or data URIs; deterministic regeneration (same month+athlete → same document)

**Scale/Scope**: ~15 athletes/club, monthly batch generation; 2 Jinja templates, 1 builder service, 1 AI prompt, 1 new pure helper, 3 SVG macros

## Constitution Check

*GATE: evaluated pre-Phase 0 and re-checked post-Phase 1 design — PASS (no violations).*

| Principle | Assessment |
|---|---|
| I. Code Quality | New helper is a pure documented function; duplicated `_compute_streak` removed (rule of three inverse); ruff/mypy gates apply. PASS |
| II. Testing (NON-NEGOTIABLE) | Every bug fix lands with a regression test that fails pre-fix (A1 label, A2 gender, A3 gallery gate, A4/A5 reference strings, B12 key rename). Privacy invariants extended (no data URIs in snapshot/email). Frontend preview change covered by existing vitest suites + updated msw mocks. PASS |
| III. UX Consistency | All copy in español neutro (Colombia) with diacritics; ✓/⚠ status colors follow green/amber semantics; parent-facing dates localized. English corpus untouched. PASS |
| IV. Performance | Photo embedding reuses bounded SFTP→base64 budget (2 MB); no new endpoints; batch generation unchanged. PASS |
| V. Youth Psych Safeguards | Not applicable (no psychological instruments). Minors-privacy quality gates honored via R16 invariants. PASS |

**Complexity Tracking**: empty — no violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/024-newsletter-audit-fixes/
├── plan.md              # This file
├── research.md          # Phase 0 — 16 resolved research items (R1–R16)
├── data-model.md        # Phase 1 — snapshot field additions + entities
├── quickstart.md        # Phase 1 — validation guide
├── contracts/
│   └── metrics-snapshot.md  # Snapshot/JSON contract deltas (internal interface)
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── services/
│   │   ├── training/
│   │   │   ├── newsletter_builder.py        # A1 short_label, A5 LTAD fields, B6 focus_groups,
│   │   │   │                                # B7 category_label, B12 streak rename, B14 support(age, month)
│   │   │   ├── newsletter_static_copy.py    # B14 tip variants; neutral fallback unchanged
│   │   │   ├── focus_grouping.py            # NEW — pure keyword → skill-family mapper (B6)
│   │   │   └── badge_evaluator.py           # B12 single _compute_streak source
│   │   ├── ai/
│   │   │   ├── use_cases/athlete_monthly_newsletter.py  # A2 athlete_reference in context
│   │   │   └── prompts/athlete_monthly_newsletter_v1.j2 # A2 gender instruction; B12 key
│   │   ├── notification/
│   │   │   ├── athlete_newsletter_pdf.py    # A3 render-time photo embedding (reuse 022 pattern)
│   │   │   └── race_insight_dispatcher.py   # B8 source of _format_date_es → promote to shared util
│   │   └── utils/dates_es.py                # NEW (small) — format_date_es shared helper (B8)
│   └── data/technique_catalog.py            # read-only source of A–H family names (B6)
├── templates/
│   ├── documents/pdf/
│   │   ├── athlete_monthly_newsletter.html  # A1, A3, A4, A5, B7-B13 template fixes
│   │   └── charts/*.svg.jinja               # B10 pad_top + label clamp
│   └── email/athlete_monthly_newsletter.html # B7/B8 label+date consistency (no photos/anthro)
└── tests/
    ├── test_newsletter_builder_024.py       # NEW — builder fields, LTAD, grouping, rotation
    ├── test_newsletter_privacy.py           # EXTEND — no data URIs in snapshot/email
    └── routers/test_athlete_monthly_newsletters_router.py  # EXTEND — regression fixtures

frontend/
└── src/components/training/NewsletterPreviewBlocks.tsx  # B12 — already reads streak_sessions;
    └── (+ msw mocks/tests)                               # verify contract now aligns
```

**Structure Decision**: Existing web-application layout; changes concentrated in `backend/app/services/training/` + `backend/templates/`. Two small new files (`focus_grouping.py`, `dates_es.py`); everything else edits in place.

## Design decisions (from research.md)

| Item | Decision | Research |
|---|---|---|
| A1 etiqueta campeonato | `short_label` en resultados del mes vía `_race_short_label`; card usa `short_label` | R1 |
| A2 género narrativa | `athlete_reference` ("su hijo"/"su hija"/"su hijo/a") derivado de `Athlete.sex`, inyectado al prompt y al bloque de apoyo; fallback estático permanece neutro | R2 |
| A3 galería | Embebido base64 en render-time (patrón spec 022, presupuesto 2 MB); gate de 3 estados (omitir / placeholder con conteo / imágenes); data URIs jamás persisten | R3 |
| A4 referencia RPE | "0-10 (base: 3-5 · alta intensidad: 6-8)" — coherente con OMNI validado y 80/20 | R4 |
| A5 LTAD | `weekly_hours_avg = total/(días_mes/7)`, `ltad_limit = edad decimal a fecha de generación`, `ltad_status ok/review` | R5 |
| B6 focos | Nuevo `focus_grouping.py`: keywords → 8 familias A–H + "Resistencia y acondicionamiento" + "Otros"; emite `focus_groups` | R6 |
| B7 categoría | Label desde `race_categories.label` (seed oficial 26 códigos); crudo si no mapea | R7 |
| B8 fechas | `format_date_es` compartido (patrón `race_insight_dispatcher`), sin babel ni locale | R8 |
| B9 página 1 | Quitar `break-inside: avoid` del card completo de valoración; conservarlo por subsección | R9 |
| B10 SVG | `pad_top` 8→16 + clamp de `y` de labels | R10 |
| B11 tabla antro | Sin `overflow-wrap:anywhere` en th; colgroup reequilibrado; saltos de línea explícitos | R11 |
| B12 racha | Una sola aparición (KPI card); clave `streak_days`→`streak_sessions` (arregla mismatch real con frontend); un solo `_compute_streak` | R12 |
| B13 nota puntos | `has_championship` en charts_context + nota al pie (espejo spec 022) | R13 |
| B14 apoyo en casa | `_build_support_block(age_decimal, month, athlete_reference)`: banda etaria única + rotación determinista `month % variantes` | R14 |
| Compatibilidad | Campos aditivos + guards `is defined`; fixture pre-024 en tests | R15 |
| Privacidad | Invariantes R16; test nuevo: data URIs fuera de snapshot/email | R16 |

## Phase 1 artifacts

- [data-model.md](./data-model.md) — snapshot field deltas, entities, validation rules
- [contracts/metrics-snapshot.md](./contracts/metrics-snapshot.md) — internal JSON contract (builder → templates → frontend preview)
- [quickstart.md](./quickstart.md) — end-to-end validation guide
