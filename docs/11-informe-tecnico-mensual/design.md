# Monthly Technical Report — Technical Design

**Date:** 2026-06-03
**Status:** Implemented (backend + frontend + tests). Deployment to Render pending approval.
**Migration:** Alembic `d4e5f6a7b8c9` (down_revision `c6d7e8f9a0b1`).

This document details the technical design of the refactor of the "Monthly Club Report" module (Phase 1.5) into a **Monthly Technical Report** styled as a funder/financier report. The overall vision, agreed scope, and implementation steps are in [`workflow.md`](workflow.md). The operational guide for the coach is in [`runbook.md`](runbook.md).

---

## 1. Solution Summary

The monthly report is no longer a single AI paragraph (`ai_summary`, intact and preserved) and becomes a document structured by chapters, with:

- **Institutional metadata** of the sports club's project (1:1 profile, configured once).
- **Narrative blocks**: the AI pre-drafts six blocks; the coach edits each one before approving.
- **Monthly competition results**: the club's podiums drawn from the Copa Valle results module (Phase 1.7).
- **Restricted-distribution PDF** (coach/admin), with a DRAFT banner while in `draft` status and a Ley 1581 notice.

The AI never emits real names of minors. Parents do not receive `narrative_blocks` or `competition_results`.

---

## 2. Data Models

All changes live in migration `d4e5f6a7b8c9`. Pattern `batch_alter_table` + lowercase enums + `server_default`, so it works in MySQL (native ALTER) and SQLite (recreates table) and legacy records remain in coherent values without backfill.

### 2.1 New Table: `club_project_profiles`

**1:1 relationship with `clubs`** (UNIQUE on `club_id`, FK `ON DELETE RESTRICT`). Static project metadata that heads each report.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | Integer PK | no | autoincrement |
| `club_id` | Integer FK → `clubs.id` | no | UNIQUE `uq_club_project_profile_club`, `ON DELETE RESTRICT` |
| `project_name` | String(200) | yes | Project name (e.g. "Pedaleando por un Sueño") |
| `executing_entity` | String(200) | yes | Executing entity |
| `report_responsible` | String(200) | yes | Report responsible person |
| `purpose` | Text | yes | Project purpose |
| `general_objective` | Text | yes | General goal |
| `specific_objectives` | JSON | yes | List of strings (specific goals) |
| `territory_location` | String(200) | yes | Location (municipality/venue) |
| `territory_description` | Text | yes | Territory description |
| `created_at` / `updated_at` | DateTime | no | UTC, `onupdate` on `updated_at` |

All content fields are optional to allow incremental upsert. The model contains no minors' data; the router applies RBAC (coach/admin of the sports club).

Model: `backend/app/models/club_project_profile.py`.

### 2.2 New Columns in `monthly_reports`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `narrative_blocks` | JSON | yes | NULL | Map `{block_key: {ai_draft, final_text, ai_model, ai_generated_at}}` |
| `competition_results` | JSON | yes | NULL | Snapshot of monthly podiums (list of `CompetitionResultItem`) |
| `status` | Enum(`draft`, `approved`) | no | `'draft'` | `server_default`; legacy reports remain in `draft` |

`ai_summary` (v1 report) **is not migrated or removed**: it stays intact for compatibility.

### 2.3 New Columns in `training_sessions`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `session_kind` | Enum(`entrenamiento`, `actividad_conjunta`, `salida`, `otro`) | no | `'entrenamiento'` | `server_default`; legacy sessions remain as `entrenamiento` |
| `objectives` | Text | yes | NULL | Training session goals (free text) |

Enums persisted in lowercase (consistent with `values_callable` of `SessionKind` / `MonthlyReportStatus`).

### 2.4 Reversibility

`downgrade()` removes the 5 columns, the `club_project_profiles` table, and the native enum types `sessionkind` / `monthlyreportstatus` (MySQL only; in SQLite these are VARCHAR + CHECK that disappear with the column/table).

---

## 3. Narrative Blocks

The report is structured in blocks with a fixed key. The AI drafts six blocks; `competencia` is structured (filled by the competition helper, not the AI).

| Key | Chapter | Generation | Max words |
|---|---|---|---|
| `objetivo` | Period goal | AI | 150 |
| `desarrollo` | Activity development | AI | 200 |
| `resultados` | Results obtained (aggregated indicators) | AI | 180 |
| `conclusiones` | Conclusions and recommendations | AI | 150 |
| `apoyos_materiales` | Material support and resources | AI | 120 |
| `analisis_grupo` | Qualitative analysis of the high-performance group | AI | 220 |
| `competencia` | Competition participation (podiums) | Structured (helper) | — |

Allowed keys are validated against `ALLOWED_BLOCK_KEYS` in `backend/app/schemas/training_session.py`.

The `analisis_grupo` block is the **qualitative chapter of the high-performance group** — the "chapter" that the director will add to the consolidated June report. Its prompt requires a reflective coach tone, without individual judgments and without mentioning athlete pseudonyms.

### 3.1 Block Structure (`NarrativeBlock`)

```json
{
  "ai_draft": "anonymized draft generated by the AI",
  "final_text": "text approved/edited by the coach",
  "ai_model": "<model>",
  "ai_generated_at": "2026-06-03T..."
}
```

- `ai_draft`: AI draft, already passed through privacy guardrails.
- `final_text`: initialized equal to `ai_draft`; the coach edits it before approving. This is the text that goes into the PDF.
- `ai_model` / `ai_generated_at`: generation traceability.

### 3.2 AI Use Case: `MonthlyReportBlocksUseCase`

File: `backend/app/services/ai/use_cases/monthly_report_blocks.py`. Inherits from `MonthlyReportUseCase` (v1 report) to **reuse** athlete anonymization, guardrails, and the LLM client. No privacy logic is duplicated.

- `run_block(ctx, block_key)`: generates the draft for one block. On timeout, network error, or guardrail rejection, returns `BlockDraft` with `ai_draft=None` and a descriptive `error` instead of raising an exception. This way a failed block does not bring down the rest.
- `run_all_blocks(ctx, block_keys=None)`: generates the six narrative blocks in parallel (`asyncio.gather`); excludes `competencia`. Each block fails independently.

Prompt: `backend/app/services/ai/prompts/monthly_report_blocks.j2` (registered in `backend/app/services/ai/prompts/registry.py` with id `monthly_report_blocks`). Each block injects `block_title`, `block_prompt` (specific instruction), and `block_max_words` into the context. The context sent to the LLM contains only aggregated data and deterministic pseudonyms — **never** real names or `competition_results`.

Guardrails: `MonthlyReportGuardrails(forbidden_names=ctx.forbidden_names)`, the same as the v1 report: no real names (dynamic list from DB), no medical terms or supplement references. Output passes through `_scrub()`; if the guardrail rejects, the block is marked with `error="guardrail: ..."`.

---

## 4. Competition Helper

File: `backend/app/services/training/competition_results.py`.

`build_competition_results(db, club_id, year, month) -> list[CompetitionResultItem]`:

- Joins `RaceResult` → `RaceEvent` (event within the month) → `RaceCategory` → `Athlete` (of the club), with `deleted_at IS NULL` and `position IS NOT NULL`.
- Orders by `event_date ASC, position ASC`.
- Returns `CompetitionResultItem` with `athlete_name`, `category`, `position`, `points`, `event_name`, `event_date`.
- **Degrades cleanly**: any DB error returns `[]` without breaking the report.

Athlete names here are **intentional**: they feed the PDF (a controlled document), not the AI. The AI never receives this object.

---

## 5. Endpoints

Router: `backend/app/routers/monthly_reports.py`. Mounted in `main.py` with prefix `/api/clubs` (coach/admin router) and `/api/parents` (parent read-only router).

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/api/clubs/{id}/project-profile` | coach/admin | Read the sports club's project profile |
| PUT | `/api/clubs/{id}/project-profile` | coach/admin | Create or replace the profile (upsert) |
| PATCH | `/api/clubs/{id}/project-profile` | coach/admin | Partial update (`exclude_unset`) |
| POST | `/api/clubs/{id}/monthly-reports` | coach/admin | Generate/regenerate the period report (includes AI blocks + competition) |
| GET | `/api/clubs/{id}/monthly-reports` | coach/admin | List sports club reports |
| GET | `/api/clubs/{id}/monthly-reports/{year}/{month}` | coach/admin | Report detail (with blocks and competition) |
| PATCH | `/api/clubs/{id}/monthly-reports/{year}/{month}/blocks` | coach/admin | Update `final_text` of blocks and/or transition `draft → approved` |
| POST | `/api/clubs/{id}/monthly-reports/{year}/{month}/blocks/{block_key}/regenerate` | coach/admin | Regenerate the `ai_draft` of an individual block |
| GET | `/api/clubs/{id}/monthly-reports/{year}/{month}/pdf` | coach/admin | Download the PDF (technical template) |
| GET | `/api/parents/.../monthly-summary` | parent | Filtered summary, without blocks or competition |

Contract notes:

- `PATCH .../blocks` (`MonthlyReportBlocksUpdate`): only accepts keys in `ALLOWED_BLOCK_KEYS`; the state transition is only `draft → approved` (no reversion to draft). Returns `MonthlyReportRead` with `athlete_names` resolved for the coach/admin role.
- `POST .../regenerate`: preserves the `final_text` edited by the coach if it already differed from the previous `ai_draft`.
- `GET .../pdf`: uses the template `DocumentTemplate.TRAINING_MONTHLY_TECHNICAL_REPORT` (registered in `backend/app/services/notification/template_registry.py`, path `documents/pdf/training_monthly_technical_report.html`). The v1 report (`TRAINING_MONTHLY_REPORT`) still exists.

---

## 6. PDF — `training_monthly_technical_report.html`

Template: `backend/templates/documents/pdf/training_monthly_technical_report.html`. Variable `is_draft: bool` controls the DRAFT banner.

Sections in order:

1. Institutional cover page / project data (from `ClubProjectProfile`).
2. Project context.
3. Territorial location.
4. Period goal (block `objetivo`).
5. Executed activities — High-Performance Group (block `desarrollo` + sessions table).
6. Competition participation (`competition_results`, with podiums).
7. Joint activities and outings (sessions with `session_kind` `actividad_conjunta` / `salida`).
8. Material support and resources (block `apoyos_materiales`).
9. Results (block `resultados`).
10. High-performance group analysis (block `analisis_grupo`).
11. Conclusions and recommendations (block `conclusiones`).
12. Photo record (consented media).

> The **"Population Served" section is OMITTED** by explicit user decision; the document is limited to the high-performance group, without segmentation by program ("Teteros" and other formative programs are not documented).

Legal notices:

- **DRAFT banner** visible only if `is_draft=True` ("pending approval by the responsible coach").
- **Ley 1581/2012 notice** (+ Decreto 1377/2013): **restricted distribution** document, contains minors' data, for exclusive use by the technical team, do not distribute externally.

---

## 7. Privacy

Summary of the privacy contract (audit reuses the framework from the v1 report and the Phase 1.8 newsletter):

| Rule | Mechanism |
|---|---|
| AI never receives or emits real names | Anonymization with deterministic pseudonyms + `MonthlyReportGuardrails(forbidden_names)` + `_scrub()`; `competition_results` is not passed to the LLM |
| Parents do not receive `narrative_blocks` | Router forces `narrative_blocks=None` for the `parent` role |
| Parents do not receive `competition_results` | Router forces `competition_results=None` for the `parent` role (contains names of other minors) |
| `athlete_names` only for coach/admin | Populated only in coach/admin endpoints; absent in the parent view |
| Minors' names in the PDF | **Deliberate exception**: the report is a controlled external document. Gated by: RBAC coach/admin + approval + Ley 1581 notice in the document. No names in `draft` distributed without approval → DRAFT banner |

Minors' names appear in the PDF only in podiums (`competition_results`) and attendance tables. This is a conscious exception to the general "no names in artifacts" principle, justified because the PDF is a restricted-distribution document under coach/admin control.

---

## 8. Frontend

- **`ReportDetailPage`** (`frontend/src/routes/training/ReportDetailPage.tsx`): rewritten as a **block-by-block editor**. Per block: generate/regenerate with AI, edit `final_text`, view model traceability. Global actions: approve (`draft → approved`), download PDF. Read-only view for parents (without internal blocks or competition).
- **`ProjectProfilePage`** (`frontend/src/routes/training/ProjectProfilePage.tsx`): project profile editing (RHF + Zod; specific goals as a list). Configured once per sports club.
- **`ReportsListPage`**: status badge (`draft` / `approved`) + link to project data.
- **`SessionFormPage`**: new fields `session_kind` (selector) and `objectives` (text).
- **Types / API / hooks**: `useProjectProfile`, `useUpsertProjectProfile`, `useUpdateReportBlocks`, `useRegenerateBlock` + MSW handlers. Zod schemas in `frontend/src/schemas/trainingSession.schema.ts`.

---

## 9. Tests

- **Backend**: 52 targeted green tests (includes `backend/tests/models/test_monthly_report_refactor_columns.py` for the new columns/enums).
- **Frontend**: 1742 green vitest tests + clean `tsc`.
- Migration chained to head `c6d7e8f9a0b1` → `d4e5f6a7b8c9`, verified in SQLite via tests.

---

## 10. Format-Alignment Update (Feature 022, 2026-07-03)

`specs/022-align-monthly-report-format/` closes the remaining gaps between the generated report and the approved institutional format. **No Alembic migration** — all changes are additive keys inside the existing JSON columns (`metrics_snapshot`, `narrative_blocks`, `competition_results` of `monthly_reports`); no new screens, no changes to session creation or media upload.

- **New narrative block `plan_entrenamiento`** ("Plan de entrenamiento") added to `ALLOWED_BLOCK_KEYS` and to the AI use case's block config; `competencia` gains auto-generation fed by the grouped competition summary (pseudonyms only, never passed as free text to the LLM).
- **Per-session detail table**: `MonthlyMetrics.session_detail` (new, additive) lists each session of the period, computed in `compute_monthly_metrics` (`backend/app/services/training/metrics.py`), ordered `session_date, start_time` ASC.
- **Per-athlete rubric columns**: `AthleteAttendanceStats.avg_rubric_{effort,attitude,technique}` (nullable when no rubric was recorded) added alongside existing attendance stats.
- **Competition breakdown by jornada**: `CompetitionResultItem` gains `event_id`, `series_kind`, `awards_points` (`awards_points = series_kind == 'cup'`, per feature 014's cup-vs-championship distinction) so the PDF/DOCX can group results by `event_id` then category, with a points/no-points note per jornada.
- **Photo register grouped by section**: `build_report_photo_evidence` now attaches a derived `section` per photo (`entrenamiento`/`otro` → "Grupo de Alto Rendimiento", `actividad_conjunta`/`salida` → "Actividades Conjuntas", session date matching a `RaceEvent` date → "Competencia", with a default fallback), rendered as titled sections with reserved placeholders for empty groups. Existing consent/thumbnail/6-photo/2MB filters are unchanged.
- **DOCX export**: new `GET /api/clubs/{club_id}/monthly-reports/{year}/{month}/docx` (coach/admin only, same RBAC as `/pdf`) renders `backend/templates/documents/docx/training_monthly_technical_report.docx` via `docxtpl` (already a dependency — no new package). Both PDF and DOCX now consume a single shared context builder, `build_report_document_context()` (`backend/app/services/training/reports.py`), to avoid duplicating section/table/photo assembly logic.
- **Backward compatibility**: `build_report_document_context()` guards every new key; a pre-feature snapshot (no `session_detail`, flat competition items) renders without error, showing "Pendiente — regenerar informe" instead of crashing.
- **Privacy**: unchanged contract — parents still never receive `narrative_blocks`, `competition_results`, `session_detail`, or the PDF/DOCX; the new AI block prompt uses the same pseudonym pipeline and forbidden-names guardrail as the other blocks.

See `specs/022-align-monthly-report-format/plan.md` and `data-model.md` for the full design record.

## 11. References

- [`workflow.md`](workflow.md) — overall vision, scope, steps.
- [`runbook.md`](runbook.md) — coach operational guide.
- [`../09-training-planning/`](../09-training-planning/) — base training session and v1 monthly report module.
- [`../10-race-results/`](../10-race-results/) — source of competition results.
- `backend/app/models/club_project_profile.py`
- `backend/alembic/versions/d4e5f6a7b8c9_informe_tecnico_mensual.py`
- `backend/app/services/ai/use_cases/monthly_report_blocks.py`
- `backend/app/services/ai/prompts/monthly_report_blocks.j2`
- `backend/app/services/training/competition_results.py`
- `backend/app/routers/monthly_reports.py`
- `backend/templates/documents/pdf/training_monthly_technical_report.html`
