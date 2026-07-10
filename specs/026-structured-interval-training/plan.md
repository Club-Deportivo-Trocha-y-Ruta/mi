# Implementation Plan: Structured Interval Training with Strava Correlation

**Branch**: `026-structured-interval-training` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/026-structured-interval-training/spec.md`

## Summary

The coach designs an interval structure (warmup / repeatable work-recovery groups / cooldown, each block with duration + HR zone + cadence target) as an **attached entity** on a training session — replicating the attached-block pattern of features 018/021. From that structure the coach can: (a) download a brand-specific PDF instructivo (iGPSport / Magene / Garmin) generated through the existing WeasyPrint/Jinja pipeline, and (b) once a Strava activity is linked to the session (existing feature-025 flow), get an **automatic plan-vs-actual comparison** computed by sequential order-based matching of the activity's **persisted laps** (new table, never GPS) against the planned blocks, with a manual recalculation trigger. A tagged template library provides reuse via copy-on-attach. Age-gating is hybrid: hard block for Z3+ on 10-12 structures, confirm-and-record for the rest. Everything (comparison, detail view, laps) is coach/admin-only in v1.

Technical approach: two new model modules (`intervals.py`, laps on the Strava side), one Alembic migration on head `a4b5c6d7e8f9`, a new `/api/intervals` router + `services/intervals/` package (structures, templates, matching, instructivo PDF), one new `StravaClient.get_activity_laps()` method, matching computed **deferred** via the existing `TaskDispatcher` pattern (link endpoint stays fast), and a frontend `components/intervals/` + `hooks/intervals/` + lazy routes mirroring the strength feature's structure.

## Technical Context

**Language/Version**: Python 3.12+ (backend), TypeScript / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql), Alembic, Pydantic v2, WeasyPrint ≥62.3 + Jinja2 (PDF, already in use), httpx (Strava client, already in use); React 19 + Vite, shadcn/ui + Tailwind, TanStack Query, React Hook Form + Zod. **No new runtime dependency.**

**Storage**: MySQL 8.4 (Hostinger prod / Docker dev). New tables: `interval_structures`, `interval_structure_blocks`, `interval_templates`, `interval_template_blocks`, `strava_activity_laps`, `interval_match_results`. One migration, `down_revision = "a4b5c6d7e8f9"` (verified current head).

**Testing**: pytest + httpx.AsyncClient + aiosqlite (backend), vitest + Testing Library + jest-axe (frontend). Mirrors `backend/tests/strength/` and `frontend/src/components/strength/__tests__/` suites.

**Target Platform**: Linux server (Render free tier, Docker) + web SPA (coach: tablet; parents: Android 3G/4G — parents excluded from this feature's views in v1)

**Project Type**: Web application (existing `backend/` + `frontend/` monorepo)

**Performance Goals**: Link endpoint (`PATCH /api/activities/{id}/link`) keeps p95 ≤ 1500 ms by deferring lap fetch + matching to `TaskDispatcher` (same pattern as webhook ingest). Matching itself is O(blocks + laps) in-memory — trivial. Structure/template list endpoints eager-load blocks via `selectinload` (no N+1).

**Constraints**: Never persist/expose GPS, polyline, map, or free-text location (Ley 1581, minors) — laps table stores duration/HR/speed only, **no cadence in v1 (FR-013), no watts, no geo**. Numeric-only logging (pattern 025). Strava rate limits (100 req/15 min): one extra `GET /activities/{id}/laps` call per link/recalculate event only — negligible volume (club scale: tens of activities/week). Coach/admin-only visibility enforced server-side (FR-018).

**Scale/Scope**: One club, ~10-30 athletes, a few sessions/week, ≤ a few hundred structures/season. Scale is not a concern; correctness of guardrails and privacy invariants is.

## Constitution Check

*GATE: evaluated against Constitution v1.2.0 — PASS, no violations. Re-checked after Phase 1 design: still PASS.*

| Principle | Compliance |
|---|---|
| **I. Code Quality** | New `services/intervals/` package with docstrings (inputs/outputs/side effects) as required for public service modules; `ruff`+`mypy` / `eslint`+`tsc` gates apply; no duplication introduced — reuses `DocumentGenerator`, `TaskDispatcher`, `AgeBand` enum, permission helpers, `triggerBlobDownload`. |
| **II. Testing (NON-NEGOTIABLE)** | Each router/service gets happy-path + negative-path pytest coverage (403 parent access, 422 cadence <60, 422 Z3+ on 10-12, laps mismatch handling). Frontend: vitest for editor/dialog/table logic + jest-axe on the new page-level views (match detail, template library) and the age-gate dialog. Privacy invariants tested explicitly: `strava_activity_laps` and every response schema assert absence of geo fields (mirrors `tests/privacy/test_strava_privacy.py`). |
| **III. UX Consistency** | All product copy in español neutro (Colombia); components from shared shadcn/ui system (age-gate dialog mirrors `AgeBandGuardrailDialog`); forms RHF+Zod with inline localized errors; compliance badges use the canonical semantics (green=cumplido, amber=fuera de tolerancia, gray=sin dato); WCAG 2.1 AA + 48px targets; loading/empty/error states designed for match view (incl. "aún no hay actividad enlazada" and "calculando comparación…" states). |
| **IV. Performance** | Outbound Strava call moved off the request path (deferred dispatch); `selectinload` on blocks for list endpoints with a query-count test; frontend: match detail view + template library are `React.lazy` routes (≤150 KB gzip each); PDF generation runs in executor (existing `DocumentGenerator` behavior). |
| **V. Youth Psych. Assessment Safeguards** | Not applicable — no psychological instrument administered, scored, stored, or interpreted. Stated explicitly per gate requirement. |
| **Quality Gates — Privacy (Ley 1581)** | Laps: duration/avg HR/avg speed only; no geo columns exist by construction; logs numeric IDs only; `data-privacy-guard` audit is mandatory before merge (feature reads athlete-linked activity data). |
| **Quality Gates — Stack discipline** | No new runtime dependency; agreed stack only. |
| **Quality Gates — Security** | RBAC via `require_role([admin, coach])` DI + club-scoping (`user_club_role`) on every `/api/intervals` route, exercised by tests; no file uploads in this feature. |

## Project Structure

### Documentation (this feature)

```text
specs/026-structured-interval-training/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.md           # Phase 1 output — /api/intervals + laps/instructivo contracts
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   ├── interval_structure.py        # NEW — IntervalStructure, IntervalStructureBlock,
│   │   │                                #       IntervalTemplate, IntervalTemplateBlock, enums
│   │   └── strava_activity_lap.py       # NEW — StravaActivityLap (no geo, no cadence v1)
│   │                                    #       + IntervalMatchResult
│   ├── schemas/
│   │   └── intervals.py                 # NEW — Structure/Template/Block/Match/Lap schemas
│   ├── routers/
│   │   ├── intervals.py                 # NEW — /api/intervals (structures, templates,
│   │   │                                #       match, recalculate, instructivo PDF)
│   │   └── activities.py                # EDIT — link_activity dispatches deferred matching
│   ├── services/
│   │   ├── intervals/
│   │   │   ├── __init__.py              # NEW
│   │   │   ├── structures.py            # NEW — CRUD + age-gate + cadence validation
│   │   │   ├── templates.py             # NEW — template CRUD + copy-on-attach
│   │   │   ├── matching.py              # NEW — pure order-based matching engine
│   │   │   ├── match_runner.py          # NEW — fetch laps → persist → compute (deferred)
│   │   │   └── instructivo_pdf.py       # NEW — brand-specific PDF wrapper
│   │   └── strava/
│   │       └── client.py                # EDIT — add get_activity_laps(activity_id)
│   └── main.py                          # EDIT — include intervals router
├── templates/documents/pdf/
│   └── session_instructivo.html         # NEW — extends base/layout.html, per-brand blocks
├── alembic/versions/
│   └── b5c6d7e8f9a0_interval_training.py  # NEW — down_revision = a4b5c6d7e8f9
└── tests/
    ├── intervals/                       # NEW — test_structures, test_guardrail,
    │                                    #       test_templates, test_matching,
    │                                    #       test_instructivo_pdf, test_rbac, conftest
    └── privacy/
        └── test_laps_privacy.py         # NEW — no-geo invariants on laps + match schemas

frontend/
├── src/
│   ├── api/intervals.ts                 # NEW — API fns + error mapping (age-gate extract)
│   ├── hooks/intervals/useIntervals.ts  # NEW — TanStack Query hooks + key factory
│   ├── schemas/intervals.schema.ts      # NEW — Zod schemas (cadence ≥60, repeat groups)
│   ├── types/intervals.types.ts         # NEW
│   ├── components/intervals/
│   │   ├── StructureEditor.tsx          # NEW — RHF+Zod block editor w/ repeat groups
│   │   ├── AgeGateDialog.tsx            # NEW — mirrors AgeBandGuardrailDialog
│   │   ├── BlockRow.tsx                 # NEW
│   │   ├── PlanVsActualTable.tsx        # NEW — lap↔block pairing + compliance badges
│   │   ├── InstructivoDownloadButton.tsx# NEW — brand select + blob download
│   │   └── TemplatePicker.tsx           # NEW — browse/filter + attach (copy)
│   ├── routes/
│   │   ├── intervals/TemplateLibraryPage.tsx   # NEW — lazy, coach/admin
│   │   ├── training/SessionDetailPage.tsx      # EDIT — "Estructura de intervalos" section
│   │   └── training/ActivityMatchPage.tsx      # NEW — lazy, coach/admin detail view
│   └── App.tsx                          # EDIT — lazy routes + ProtectedRoute guards
└── src/components/intervals/__tests__/  # NEW — component + a11y tests
```

**Structure Decision**: Web application (existing `backend/` + `frontend/`). The feature replicates the strength-library (021) file topology one-to-one — separate router prefix, dedicated services package, per-domain frontend dirs — because the interview locked the "attached entity, not wizard step" decision and 021 is the proven in-repo reference for exactly that shape, including the override/confirm guardrail flow.

## Complexity Tracking

> No constitution violations. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
