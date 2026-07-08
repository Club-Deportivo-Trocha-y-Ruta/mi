# Implementation Plan: Alinear el Informe Técnico Mensual al formato institucional aprobado

**Branch**: `022-align-monthly-report-format` | **Date**: 2026-07-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/022-align-monthly-report-format/spec.md`

## Summary

Close the gaps between the currently generated Monthly Technical Report and the approved institutional format, entirely within the existing report module: (1) restructure the PDF template to the approved section order and add the missing "Plan de entrenamiento" narrative block (plus auto-generation of `competencia`); (2) enrich the persisted snapshot with a per-session detail table, per-athlete rubric averages, and competition results carrying `event_id`/`series_kind`/`awards_points` for jornada grouping with a points/no-points note; (3) group photo evidence automatically by section derived from `session_kind` + race-date heuristic, with reserved placeholders; (4) add a DOCX download (docxtpl, already a dependency) for the "editable" requirement. **No Alembic migration** (JSON-column additive changes only), **no new screens**, **no changes to session creation or media upload** (per clarifications).

Research inputs: full module map (Explore agent), Context7 MCP (docxtpl `{%tr%}`/`{%p%}`/`InlineImage`), shadcn MCP + repo check (`dropdown-menu` already installed). See [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.13 (Docker image `python:3.13-slim`; local venv), TypeScript 5 / React 19

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async (aiomysql), Jinja2, WeasyPrint ≥62.3 (PDF), **docxtpl ≥0.16.7 (DOCX — already in requirements.txt, zero new deps)**, Pydantic v2; frontend: Vite, shadcn/ui + Tailwind, TanStack Query, RHF + Zod

**Storage**: MySQL 8.4 (Hostinger prod) — no DDL change; additive keys in existing JSON columns `metrics_snapshot`, `narrative_blocks`, `competition_results` of `monthly_reports`

**Testing**: backend `pytest` + `httpx.AsyncClient` + aiosqlite; frontend `vitest` + Testing Library + `jest-axe`

**Target Platform**: Render free tier (Docker, Oregon) + Cloudflare Pages frontend; SFTP Hostinger for media thumbnails

**Project Type**: Web application (FastAPI backend + React SPA frontend)

**Performance Goals**: report generation (POST) is a transactional write — p95 ≤ 1500 ms budget applies to the API call excluding AI drafting (AI calls already async-degradable to `ai_draft=None`); PDF/DOCX render ≤ existing PDF endpoint envelope (photo payload capped 6 photos / 2 MB)

**Constraints**: no new runtime dependency; backward-compatible rendering of pre-feature snapshots (missing keys → "Pendiente — regenerar informe"); minors privacy — parents never receive narrative, names, session_detail, photos, PDF/DOCX; AI prompts keep pseudonyms and `AI_LOG_PROMPTS=false`

**Scale/Scope**: 1 club, ≤ ~30 sessions/month, ≤ ~25 athletes, ≤ 3 competitions/month — grouping/aggregation trivially in-memory

## Constitution Check

*GATE: evaluated pre-Phase 0 and re-evaluated post-Phase 1 design — **PASS, no violations**.*

| Principle | Compliance |
|---|---|
| I. Code Quality | Changes concentrated in existing modules (`metrics.py`, `competition_results.py`, `reports.py`, templates, one router endpoint). Shared context-builder for PDF/DOCX avoids duplication. `ruff`/`mypy`/`eslint`/`tsc` gates apply. Docstrings for modified service functions. |
| II. Testing (NON-NEGOTIABLE) | New pytest coverage: session_detail aggregation (happy + cancelled sessions), per-athlete rubric averages, competition grouping + `awards_points` (cup vs championship), photo section derivation (incl. race-date heuristic + empty groups), DOCX endpoint (200 coach / 403 parent), regenerate isolation regression, old-snapshot backward-compat render, parent privacy invariants (no names, no session_detail). Frontend: vitest for ReportDetailPage (BLOCK_ORDER incl. `plan_entrenamiento`, download dropdown), schema parsing of additive fields, jest-axe on modified page. |
| III. UX Consistency | Product copy in español neutro (section titles per approved format, placeholders, banner). Download control uses installed shadcn `dropdown-menu` (48px targets). Loading/error states reuse existing report page patterns. No new component patterns. |
| IV. Performance | No N+1: metrics query already batch-loads; competition join adds `RaceSeries` via explicit join (single query); photo evidence keeps 6-photo/2 MB cap; DOCX render is in-process template fill (no external calls). No new frontend routes/bundles; dropdown is already-bundled primitive. |
| V. Youth Psych. Safeguards | N/A — no psychological instruments touched. Minors-privacy Quality Gates fully apply (see Constraints). |
| Quality Gates — Privacy | Parent filtering extended to new fields; photos remain consent-gated; AI prompt for new blocks uses existing pseudonym pipeline; no PII in logs. `data-privacy-guard` audit required before merge. |
| Stack discipline | Zero new dependencies (docxtpl/WeasyPrint already present). |

## Project Structure

### Documentation (this feature)

```text
specs/022-align-monthly-report-format/
├── plan.md              # This file
├── research.md          # Phase 0 — 9 resolved decisions (R1–R9)
├── data-model.md        # Phase 1 — JSON-schema deltas, no migration
├── quickstart.md        # Phase 1 — 6 validation scenarios
├── contracts/
│   └── monthly-report-api.md
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/monthly_reports.py            # + GET .../docx endpoint
│   ├── schemas/training_session.py           # MonthlyMetrics.session_detail, AthleteAttendanceStats.avg_rubric_*,
│   │                                         #   CompetitionResultItem.{event_id,series_kind,awards_points},
│   │                                         #   ALLOWED_BLOCK_KEYS + plan_entrenamiento
│   ├── services/
│   │   ├── training/metrics.py               # session_detail + per-athlete rubric aggregation
│   │   ├── training/competition_results.py   # join RaceSeries; kind/awards_points
│   │   ├── training/reports.py               # photo section derivation; shared doc-context builder
│   │   ├── ai/use_cases/monthly_report_blocks.py  # + plan_entrenamiento, + competencia auto-gen
│   │   └── notification/template_registry.py # + TRAINING_MONTHLY_TECHNICAL_REPORT_DOCX
│   └── ...
├── templates/documents/
│   ├── pdf/training_monthly_technical_report.html   # restructure to approved format
│   └── docx/training_monthly_technical_report.docx  # NEW docxtpl asset
└── tests/                                    # new/extended suites (see Constitution II)

frontend/src/
├── api/trainingSessions.ts                   # + useDownloadMonthlyReportDocx
├── schemas/monthlyReport.schema.ts           # additive optional fields
├── types/trainingSession.types.ts
└── routes/training/ReportDetailPage.tsx      # BLOCK_ORDER, download DropdownMenu
```

**Structure Decision**: Web application (existing `backend/` + `frontend/` split). No new modules, routes, or screens — the feature is a vertical enrichment of the existing monthly-report slice, honoring the clarifications (no changes to session wizard, media upload, or import).

## Complexity Tracking

> No constitution violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
