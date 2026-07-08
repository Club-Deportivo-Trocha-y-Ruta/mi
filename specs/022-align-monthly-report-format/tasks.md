---
description: "Task list — Alinear el Informe Técnico Mensual al formato institucional aprobado"
---

# Tasks: Alinear el Informe Técnico Mensual al formato institucional aprobado

**Input**: Design documents from `/specs/022-align-monthly-report-format/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: REQUIRED — Constitution II (Testing NON-NEGOTIABLE). Every backend change ships happy + negative path; every branching frontend component ships vitest + jest-axe.

**Organization**: grouped by user story (P1→P3) for independent implementation/testing. **No Alembic migration** — all persistence is additive JSON keys.

## Format: `[ID] [P?] [Story] Description` — 🤖 `agent` · `model`

- **[P]**: parallelizable (different file, no incomplete deps)
- **[Story]**: US1 / US2 / US3 (setup/foundational/polish carry none)
- **🤖 agent · model**: recommended specialized agent + model tier. Backend logic → `fastapi-architect`; frontend → `react-ui-engineer`; tests → `qa-engineer`; privacy audit → `data-privacy-guard`; DOCX/PDF asset + template → `integration-engineer`; docs → `technical-writer`. Model: **opus** for cross-cutting/design-heavy or privacy-critical, **sonnet** for scoped implementation, **haiku** for mechanical edits.

## MCP usage (per user request)

- **Context7 MCP** (`resolve-library-id` → `query-docs`) — pull docxtpl syntax (`{%tr%}`, `{%p if%}`, `InlineImage`, `groupby`) before authoring the DOCX asset (T024) and Jinja `groupby` in templates (T016, T022).
- **shadcn MCP** (`search_items_in_registries`, `get_item_examples_from_registries`) — confirm `dropdown-menu` usage examples before T030 (already installed; no `add` needed).
- **filesystem / serena MCP** — symbol navigation while editing services/schemas.
- **IDE MCP** (`getDiagnostics`) — after each backend/frontend edit, verify `mypy`/`tsc` clean.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: confirm environment; no scaffolding needed (feature is a vertical enrichment of an existing module).

- [X] T001 Verify dev stack boots and current report renders baseline: `docker compose up -d` + `cd backend && uvicorn app.main:app --reload`, generate a report for a seeded month, download existing `/pdf`. Capture current section order as regression baseline. 🤖 `devops-engineer` · haiku
- [X] T002 [P] Confirm `docxtpl>=0.16.7` + `weasyprint>=62.3` resolve in the venv (`pip check`); confirm `frontend/src/components/ui/dropdown-menu.tsx` present (shadcn MCP examples fetched). No installs expected. 🤖 `devops-engineer` · haiku

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: schema + shared context builder that ALL stories render from. **⚠️ Blocks US1–US3.**

- [X] T003 [P] Extend Pydantic schemas in `backend/app/schemas/training_session.py`: add `SessionDetailItem`; `MonthlyMetrics.session_detail: list[SessionDetailItem] = []`; `AthleteAttendanceStats.avg_rubric_{effort,attitude,technique}: float | None`; `CompetitionResultItem.{event_id:int, series_kind: str|None, awards_points: bool}`; add `plan_entrenamiento` to `ALLOWED_BLOCK_KEYS`. All additive/optional (backward-compatible deserialization). 🤖 `fastapi-architect` · sonnet
- [X] T004 [P] Add `TRAINING_MONTHLY_TECHNICAL_REPORT_DOCX` member to `DocumentTemplate` registry in `backend/app/services/notification/template_registry.py`, pointing at `backend/templates/documents/docx/training_monthly_technical_report.docx`. 🤖 `integration-engineer` · sonnet
- [X] T005 Create shared document-context builder in `backend/app/services/training/reports.py` (`build_report_document_context(report, profile) -> dict`) consumed by BOTH PDF and DOCX renderers — single source for header, sections, tables, photos, draft-missing-list. Guards missing JSON keys → "Pendiente — regenerar informe" (backward-compat, FR-012). 🤖 `fastapi-architect` · opus
- [X] T006 [P] [Foundational test] Unit test old-snapshot backward compatibility in `backend/tests/test_monthly_report_context.py`: context builder on a pre-feature snapshot (no `session_detail`, flat competition items) returns without error and marks new sections "Pendiente". 🤖 `qa-engineer` · sonnet

**Checkpoint**: schemas + shared context ready — stories can proceed in parallel.

---

## Phase 3: User Story 1 — Informe que coincide con el formato aprobado (P1) 🎯 MVP

**Goal**: generated document matches approved section order/names, full project header, no empty mandatory narrative; draft/approved visibly reflected; missing sections flagged inline.

**Independent Test**: generate report for a period with complete profile + sessions → header populated (no "—"), sections in approved order (Objetivo → Plan de entrenamiento → Desarrollo → Participación en competencia → Resultados → Conclusiones), no mandatory section empty; draft banner lists missing sections.

### Tests for US1 (write first, must fail)

- [X] T007 [P] [US1] Test `plan_entrenamiento` auto-generates and unknown-key rejection in `backend/tests/test_monthly_report_blocks.py` (happy: block drafted; negative: 422 on bad `block_key`). 🤖 `qa-engineer` · sonnet
- [X] T008 [P] [US1] Test approved section order + header population + draft "missing sections" banner via rendered context in `backend/tests/test_monthly_report_structure.py`. 🤖 `qa-engineer` · sonnet

### Implementation for US1

- [X] T009 [US1] Add `plan_entrenamiento` and `competencia` to auto-generation config (`_BLOCK_MAX_WORDS/_TITLES/_PROMPTS`) in `backend/app/services/ai/use_cases/monthly_report_blocks.py`; feed `competencia` the grouped competition summary context (pseudonyms only). 🤖 `fastapi-architect` · opus
- [X] T010 [P] [US1] Update AI prompt `backend/app/services/ai/prompts/monthly_report_blocks.j2` to support the two new block keys (Spanish management tone, max-words, NEVER real names). 🤖 `prompt-engineer` · opus
- [X] T011 [US1] Restructure PDF template `backend/templates/documents/pdf/training_monthly_technical_report.html` to approved section order + "Plan de entrenamiento" section; header labels (Nombre del proyecto, Entidad ejecutora, Período, Responsable); draft banner enumerates missing mandatory sections; inline "Pendiente de completar" markers (FR-002, FR-008, FR-012). Consume T005 context. 🤖 `integration-engineer` · sonnet
- [X] T012 [US1] Ensure generation flow persists `plan_entrenamiento` and never blocks on missing inputs in `backend/app/services/training/reports.py` (`generate_monthly_report` orchestration). 🤖 `fastapi-architect` · sonnet

**Checkpoint**: US1 independently generates an approved-format document. MVP deliverable.

---

## Phase 4: User Story 2 — Contenido enriquecido de sesiones, asistencia y competencia (P2)

**Goal**: per-session detail table (fecha, hora, foco, lugar, asistencia); per-athlete attendance+rubric table with club totals; competition broken down by jornada (evento) + categoría with points/no-points note.

**Independent Test**: period with sessions + one competition → report shows per-session table, per-athlete attendance+rubric table, competition grouped by evento with "otorga/no otorga puntos".

### Tests for US2 (write first, must fail)

- [X] T013 [P] [US2] Test `session_detail` aggregation (happy incl. cancelled-session status rows; edge: attendance 0 / injured athlete keeps totals) in `backend/tests/test_monthly_metrics_session_detail.py`. 🤖 `qa-engineer` · sonnet
- [X] T014 [P] [US2] Test per-athlete rubric averages (nullable when no rubric) in `backend/tests/test_monthly_metrics_rubric.py`. 🤖 `qa-engineer` · sonnet
- [X] T015 [P] [US2] Test competition grouping by `event_id` + `awards_points` (cup → true, championship → false; no-competition period → section omitted/"sin competencias") in `backend/tests/test_competition_results_grouping.py`. 🤖 `qa-engineer` · sonnet

### Implementation for US2

- [X] T016 [US2] Compute `session_detail` + per-athlete rubric averages in `backend/app/services/training/metrics.py` (`compute_monthly_metrics`), ordered `session_date, start_time` ASC; no N+1 (batch/eager load). 🤖 `fastapi-architect` · opus
- [X] T017 [US2] Join `RaceEvent → RaceSeries` in `backend/app/services/training/competition_results.py` (`build_competition_results`); populate `event_id`, `series_kind`, `awards_points` (`series_kind=='cup'`); single query, no N+1. 🤖 `sql-pro` · sonnet
- [X] T018 [US2] Add per-session table, per-athlete attendance+rubric table, and competition-by-jornada grouping (Jinja `groupby event_id` then `category`, event header with points note) to PDF template. Consume T005 context. 🤖 `integration-engineer` · sonnet

**Checkpoint**: US1 + US2 both work independently.

---

## Phase 5: User Story 3 — Registro fotográfico agrupado (P3)

**Goal**: photo register grouped automatically by section (Grupo de Alto Rendimiento / Competencia / Actividades Conjuntas) derived from `session_kind` + race-date heuristic; reserved placeholders for empty groups.

**Independent Test**: attach photos to a period → grouped register by section; period with no photos → all reserved placeholders, no error; no minor PII exposed.

### Tests for US3 (write first, must fail)

- [X] T019 [P] [US3] Test section derivation (`entrenamiento|otro`→Alto Rendimiento; `actividad_conjunta|salida`→Actividades Conjuntas; session date == RaceEvent date → Competencia; default fallback) + empty-group placeholders + 6-photo/2 MB cap preserved, in `backend/tests/test_report_photo_evidence_sections.py`. 🤖 `qa-engineer` · sonnet

### Implementation for US3

- [X] T020 [US3] Extend `build_report_photo_evidence` in `backend/app/services/training/reports.py`: attach derived `section` per photo (deterministic; default "Grupo de Alto Rendimiento"); keep `consent_ack`/PHOTO/not-deleted/thumbnail filters + cap; ensure ≥1 photo retained per non-empty group under cap. 🤖 `fastapi-architect` · sonnet
- [X] T021 [US3] Render grouped "Registro Fotográfico" with titled sections + reserved placeholders in PDF template. Consume T005 context. 🤖 `integration-engineer` · sonnet

**Checkpoint**: all three stories independently functional (PDF path complete).

---

## Phase 6: DOCX export + Frontend (cross-story, FR-011)

**Goal**: editable DOCX download parity + minimal frontend surface. Depends on T005 context and US1–US3 template structure.

- [X] T022 [P] Author DOCX asset `backend/templates/documents/docx/training_monthly_technical_report.docx` with docxtpl tags (`{%tr%}` for the 3 tables, `{%p if%}` conditionals, `InlineImage` photo groups) mirroring approved sections. Use Context7 docxtpl docs. 🤖 `integration-engineer` · opus
- [X] T023 [P] Add `GET /api/clubs/{club_id}/monthly-reports/{year}/{month}/docx` in `backend/app/routers/monthly_reports.py` (coach/admin dep same as `/pdf`; correct MIME + Content-Disposition; 404/403). 🤖 `fastapi-architect` · sonnet
- [X] T024 [P] Test DOCX endpoint (200 coach, 403 parent, 404 missing) + content parity smoke in `backend/tests/test_monthly_report_docx.py`. 🤖 `qa-engineer` · sonnet
- [X] T025 [P] Add `useDownloadMonthlyReportDocx` in `frontend/src/api/trainingSessions.ts`; extend `frontend/src/schemas/monthlyReport.schema.ts` + `frontend/src/types/trainingSession.types.ts` with additive optional fields. 🤖 `react-ui-engineer` · sonnet
- [X] T026 [US1] Update `frontend/src/routes/training/ReportDetailPage.tsx`: `BLOCK_ORDER` to approved order incl. `plan_entrenamiento`; replace download button with shadcn `DropdownMenu` (PDF/DOCX); español neutro copy. 🤖 `react-ui-engineer` · sonnet
- [X] T027 [P] Frontend tests in `frontend/src/routes/training/ReportDetailPage.test.tsx`: BLOCK_ORDER incl. new block, download dropdown (both options), additive-field schema parse, jest-axe zero violations. 🤖 `qa-engineer` · sonnet

**Checkpoint**: full deliverable — PDF + DOCX + UI.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T028 [P] Privacy invariants test: parents never receive `session_detail`, `narrative_blocks`, `competition_results`, athlete names, or `/pdf`+`/docx` (403); AI prompt for new blocks contains no real names — in `backend/tests/test_monthly_report_privacy.py`. 🤖 `qa-engineer` · opus
- [X] T029 [P] `data-privacy-guard` audit of the whole diff (logs, AI prompts, template output, new DOCX endpoint) — mandatory pre-merge gate (Constitution Quality Gates). 🤖 `data-privacy-guard` · opus
- [X] T030 Regenerate-isolation regression test: regenerating one block leaves other blocks + `metrics_snapshot` + `competition_results` untouched, in `backend/tests/test_monthly_report_regenerate.py` (FR-009). 🤖 `qa-engineer` · sonnet
- [X] T031 [P] Run full suites + lint/type gates: `cd backend && pytest -k "monthly or report or competition or metrics" && ruff check && mypy app`; `cd frontend && npx vitest run src/routes/training src/api && npx eslint . && npx tsc --noEmit`. 🤖 `qa-engineer` · sonnet
- [X] T032 Execute `quickstart.md` scenarios 1–6 end-to-end against local stack (incl. backward-compat scenario 6). 🤖 `qa-engineer` · sonnet
- [X] T033 [P] Update `docs/11-informe-tecnico-mensual/` (design/workflow) + CLAUDE.md implementation-status row for feature 022; note "no migration". 🤖 `technical-writer` · sonnet

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)** → no deps.
- **Foundational (P2)** → after Setup; **blocks all stories**. T005 (shared context) blocks all template tasks (T011, T018, T021, T022).
- **US1 (P3)** → after Foundational. MVP.
- **US2 (P4)**, **US3 (P5)** → after Foundational; independent of US1 and of each other (different service functions + separate template sections).
- **Phase 6 (DOCX+FE)** → after T005 + story template structure exists (T011/T018/T021).
- **Polish (P7)** → after all desired stories.

### Within a story

Tests (fail first) → schema/service → template render. Models/schemas (T003) before services (T009, T016, T017, T020) before templates (T011, T018, T021).

### Parallel opportunities

- T003 ∥ T004 (schemas vs registry).
- All `[P]` test tasks across a story run together (T007∥T008; T013∥T014∥T015; T019).
- After Foundational: **US1, US2, US3 in parallel** by different agents.
- Phase 6: T022 ∥ T023 ∥ T025 (asset vs endpoint vs FE api), then T024/T026/T027.
- Polish `[P]`: T028 ∥ T029 ∥ T031 ∥ T033.

---

## Parallel Example: post-Foundational fan-out

```bash
# Three specialized agents, one per story, concurrently:
Agent(fastapi-architect, opus):  US1 → T009, T012 + template T011
Agent(fastapi-architect, opus):  US2 → T016 (+ sql-pro T017) + template T018
Agent(fastapi-architect, sonnet):US3 → T020 + template T021
# QA agent writes failing tests up front in parallel:
Agent(qa-engineer, sonnet): T007,T008,T013,T014,T015,T019
```

---

## Implementation Strategy

### MVP first (US1)

1. Phase 1 Setup → 2. Phase 2 Foundational (T003–T006, CRITICAL) → 3. Phase 3 US1 → 4. STOP & validate quickstart Scenario 1 → 5. Demo approved-format PDF.

### Incremental delivery

Foundational → US1 (approved structure, MVP) → US2 (enriched tables) → US3 (photo register) → Phase 6 (DOCX + UI) → Polish. Each story deploys without breaking prior ones. **No migration** at any step.

---

## Notes

- Agent/model annotations are recommendations for the executing orchestrator (e.g. `engineering-lead`); adjust to availability.
- Constitution II: verify each test FAILS before implementing.
- Conventional Commits (type in English, description español latino); no AI-tool mention; commit after each logical group.
- `data-privacy-guard` audit (T029) is a hard pre-merge gate.
