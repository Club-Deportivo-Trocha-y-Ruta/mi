# Monthly Technical Report — Workflow

**Date:** 2026-06-03
**Status:** Implemented (backend + frontend + tests). Deployment to Render pending approval.
**Origin:** Refactor of the "Monthly Club Report" module (Phase 1.5) into a funder/financier-style report document.

---

## Context

The sports club already generated a "monthly report" with a single AI summary (`ai_summary` field) and aggregated metrics. That format did not serve as a deliverable to a funder or institutional partner (in the style of the "Pedaleando por un Sueño" project report): it is a standalone paragraph, without a management report structure, without an institutional cover page or a competition section with podiums.

This refactor converts the monthly report into a **Monthly Technical Report**: a document structured by chapters, with institutional project metadata, AI pre-drafted narrative edited by the coach, monthly competition results, and a photo record. The final deliverable is a restricted-distribution PDF (coach/admin).

The concrete operational goal: by **closing June 2026** the coach has all inputs captured during the month and, with just a few clicks, generates a director-style PDF — including the qualitative "chapter" of the high-performance group that the director will add to the consolidated report.

## Agreed Scope with the User

**In scope:**
- Document limited to the **High-Performance Group**. No segmentation by program ("Teteros" and other formative programs are not documented).
- "Population Served" section **OMITTED** from the report (explicit user decision).
- **AI pre-drafted** narrative block by block; the **coach edits** each block before approving. The AI never emits the final document without human review.
- **Complete delivery**: data layer (model + migration), AI block engine, competition helper, endpoints, frontend block editor, project profile page, and PDF template.
- Monthly competition results: the club's podiums drawn from the Copa Valle results module (Phase 1.7).

**Out of scope:**
- Segmentation by program / "Population Served".
- Automatic email sending of the report (coach downloads the PDF and distributes manually).
- Individual athlete metrics in the narrative body (the AI works only with aggregated data).
- Changes to the individual newsletter to parents (Phase 1.8), which is a separate module.

## New Data Models

Three changes in the data layer, all in Alembic migration `d4e5f6a7b8c9` (chained to head `c6d7e8f9a0b1`). Field details and rationale in [`design.md`](design.md) §2.

| Change | Table / object | Summary |
|---|---|---|
| New table | `club_project_profiles` | Static project metadata for the sports club (1:1 with `clubs`). Heads each report. |
| New columns | `monthly_reports` | `narrative_blocks` (JSON), `competition_results` (JSON), `status` (enum `draft`/`approved`). |
| New columns | `training_sessions` | `session_kind` (enum `entrenamiento`/`actividad_conjunta`/`salida`/`otro`), `objectives` (text). |

All new columns are backward-safe: `narrative_blocks` and `competition_results` are `NULL` by default; `status` and `session_kind` have `server_default` (`draft` and `entrenamiento` respectively), so legacy records remain in coherent values without backfill.

## Narrative Blocks

The report is structured in blocks with a fixed key. The AI drafts six narrative blocks; `competencia` is structured (not narrative, filled by the competition helper).

| Key | Chapter | Generation |
|---|---|---|
| `objetivo` | Period goal | AI |
| `desarrollo` | Activity development | AI |
| `resultados` | Results obtained (aggregated indicators) | AI |
| `conclusiones` | Conclusions and recommendations | AI |
| `apoyos_materiales` | Material support and resources | AI |
| `analisis_grupo` | Qualitative analysis of the high-performance group | AI |
| `competencia` | Competition participation (podiums) | Structured (helper) |

The `analisis_grupo` block is the **qualitative chapter of the group** — the "chapter" that the director will add to the consolidated June report.

## Implementation Steps

| # | Task | Owner | Status | Date |
|---|---|---|---|---|
| 1 | `ClubProjectProfile` model + new columns in `MonthlyReport` and `TrainingSession` + enums `SessionKind`/`MonthlyReportStatus` + migration `d4e5f6a7b8c9` | backend-dev | ✅ Complete | 2026-06-03 |
| 2 | Pydantic schemas (`ClubProjectProfile*`, `NarrativeBlock`, `CompetitionResultItem`, `MonthlyReportBlocksUpdate`) + services `reports.py` (update/regenerate blocks) | backend-dev | ✅ Complete | 2026-06-03 |
| 3 | AI use case `MonthlyReportBlocksUseCase` + prompt `monthly_report_blocks.j2` with per-block word limits and reused privacy guardrails | backend-dev | ✅ Complete | 2026-06-03 |
| 4 | Helper `competition_results.py` (club podiums in month's rounds) | backend-dev | ✅ Complete | 2026-06-03 |
| 5 | Endpoints: CRUD `project-profile`, `PATCH .../blocks`, `POST .../blocks/{key}/regenerate`, `GET .../pdf` with technical template | backend-dev | ✅ Complete | 2026-06-03 |
| 6 | PDF template `training_monthly_technical_report.html` + registration in `template_registry.py` (`TRAINING_MONTHLY_TECHNICAL_REPORT`) | backend-dev | ✅ Complete | 2026-06-03 |
| 7 | Frontend: `ReportDetailPage` as block-by-block editor, `ProjectProfilePage`, status badges, `session_kind`/`objectives` fields in session form | frontend-dev | ✅ Complete | 2026-06-03 |
| 8 | Tests: 52 backend targeted green; 1742 frontend vitest green + clean `tsc` | qa | ✅ Complete | 2026-06-03 |
| 9 | Documentation (this module) | technical-writer | ✅ Complete | 2026-06-03 |
| 10 | Deployment to Render | ops | ⏳ Pending | — |

## Acceptance Criteria

- [x] The coach can record training sessions classified by `session_kind` and with `objectives`.
- [x] The coach configures the sports club project profile once only.
- [x] The AI pre-drafts the six narrative blocks without emitting real minors' names.
- [x] The coach edits and approves each block; the PDF in `draft` carries a DRAFT banner.
- [x] The month's podiums are automatically drawn from Copa Valle results.
- [x] Parents do NOT receive `narrative_blocks` or `competition_results`.
- [x] The report omits the "Population Served" section and is limited to the high-performance group.
- [ ] Deployment to Render approved and applied.

## Format-Alignment Update (Feature 022, 2026-07-03)

Follow-up refactor (`specs/022-align-monthly-report-format/`) that aligns the generated report with the approved institutional format, entirely inside the existing module — **no Alembic migration** (additive keys inside `metrics_snapshot`/`narrative_blocks`/`competition_results`), no new screens, no changes to session creation or media upload:

- New narrative block **`plan_entrenamiento`**; `competencia` is now auto-generated from the grouped competition summary.
- New **per-session detail table** and **per-athlete rubric averages** in the persisted metrics snapshot.
- **Competition results grouped by jornada** (`event_id`/`series_kind`/`awards_points`), with a points/no-points note per jornada.
- **Photo register grouped by section** (Alto Rendimiento / Actividades Conjuntas / Competencia), derived from `session_kind` + race-date heuristic, with reserved placeholders for empty groups.
- New **DOCX export** (`GET .../monthly-reports/{year}/{month}/docx`, docxtpl — already a dependency) alongside the existing PDF; both share one context builder for backward-compatible rendering of pre-feature report snapshots.

Full design record in [`design.md`](design.md) §10.

## Coach Runbook

The step-by-step operational guide for capturing inputs during the month and closing the report is in [`runbook.md`](runbook.md).

## References

- [`design.md`](design.md) — detailed technical design.
- [`runbook.md`](runbook.md) — operational guide for the coach.
- `backend/app/models/club_project_profile.py`
- `backend/app/models/training_session.py`
- `backend/alembic/versions/d4e5f6a7b8c9_informe_tecnico_mensual.py`
- `backend/app/services/ai/use_cases/monthly_report_blocks.py`
- `backend/app/services/training/competition_results.py`
- `backend/app/routers/monthly_reports.py`
- `backend/templates/documents/pdf/training_monthly_technical_report.html`
- `frontend/src/routes/training/ReportDetailPage.tsx`
- `frontend/src/routes/training/ProjectProfilePage.tsx`
- [`../09-training-planning/design.md`](../09-training-planning/design.md) — base training session and v1 monthly report module.
- [`../10-race-results/`](../10-race-results/) — source of competition results.
