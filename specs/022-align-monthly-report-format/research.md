# Research — Alinear el Informe Técnico Mensual al formato institucional aprobado

**Feature**: `022-align-monthly-report-format` | **Date**: 2026-07-03

Sources: codebase exploration (Explore agent, full module map), Context7 MCP (docxtpl official docs `/websites/docxtpl_readthedocs_io_en`), shadcn MCP (installed component check), spec clarifications session 2026-07-03.

## R1. Output format for "descargable y editable" (FR-011)

- **Decision**: Keep the existing PDF endpoint and add a **DOCX** variant rendered with `docxtpl`, reusing the existing `DocumentGenerator` DOCX path (`backend/app/services/notification/document_generator.py:163`) and `DocumentTemplate` registry (an editable DOCX template already exists as precedent: medical authorization, `template_registry.py:418`).
- **Rationale**: `docxtpl>=0.16.7` is already in `backend/requirements.txt` — zero new dependencies (constitution: stack discipline). Word is the institutional editing format; PDF stays for read-only distribution. Context7 confirms the needed primitives: `{%tr %}` tags for dynamic table rows (per-session table, per-athlete table, competition breakdown), `{%p if %}` for conditional sections, and `InlineImage(tpl, descriptor, width=Mm(...))` for the photo register (JPEG/PNG from bytes via file-like descriptor).
- **Alternatives considered**: (a) HTML export — rejected: not an institutional editing format; (b) PDF with editable form fields — rejected: WeasyPrint has no AcroForm support and the reference document is a Word-style report; (c) only DOCX replacing PDF — rejected: breaks existing parent/coach flows and print distribution.

## R2. Per-session detail table (FR-004) — where to compute and store

- **Decision**: Add a `session_detail` list to `MonthlyMetrics` (`backend/app/services/training/metrics.py`), one row per non-cancelled session of the period: `{date, start_time, technical_focus, location, present_count, attendee_total, status}`. Persist inside the existing `metrics_snapshot` JSON column of `MonthlyReport`. Cancelled sessions listed with status marker (they support the "ejecutadas/canceladas" summary).
- **Rationale**: `TrainingSession` already stores every needed field as NOT NULL (`session_date`, `scheduled_start_time`, `technical_focus`, `location`) — confirmed in `training_session.py:86-89`; attendance rows exist per session. Persisting in the JSON snapshot keeps report immutability (regeneration recomputes) and **requires no Alembic migration**.
- **Alternatives considered**: computing at PDF-render time — rejected: document must be reproducible after period data changes; a new relational table — rejected: duplicates source of truth, no query need beyond the report.

## R3. Per-athlete rubric columns (FR-005)

- **Decision**: Extend `AthleteAttendanceStats` with `avg_rubric_effort`, `avg_rubric_attitude`, `avg_rubric_technique` (nullable floats), computed in `compute_monthly_metrics` from the same rubric rows already aggregated at club level.
- **Rationale**: Data already loaded by the metrics query; adding per-athlete averages is an aggregation change only (JSON snapshot — no migration). Pseudonymization for AI prompts unchanged (A1/A2… mapping already in place).
- **Alternatives considered**: separate endpoint — rejected: report is a snapshot document, not a live view.

## R4. Competition breakdown by jornada + points/no-points note (FR-006)

- **Decision**: Extend `CompetitionResultItem` (`backend/app/schemas/training_session.py:352`) with `event_id`, `event_date`, `series_kind` (`cup|championship|null`), `awards_points` (bool). `build_competition_results` joins `RaceEvent → RaceSeries` to read `RaceSeries.kind` / `RaceEvent.is_championship`. Templates group rows by `event_id` (= jornada, per clarification) and, within each event, by category; each event header carries the "otorga puntos / no otorga puntos" note (`awards_points = series_kind == 'cup'`).
- **Rationale**: The cup-vs-championship distinction exists upstream since feature 014 (`race_series.kind`); the report query simply never selected it. Stored `competition_results` is JSON — additive fields, no migration. Grouping is presentation-layer (Jinja `groupby`), aligned with clarification "jornada = evento del período".
- **Alternatives considered**: new "jornada" data field captured at import — rejected in clarification session (no import changes); narrative-only description — rejected (spec demands structured breakdown).

## R5. Section structure: "Plan de entrenamiento" block + approved order (FR-002)

- **Decision**: Add narrative block key `plan_entrenamiento` to `ALLOWED_BLOCK_KEYS` and to the auto-generation config (`_BLOCK_MAX_WORDS/_TITLES/_PROMPTS` in `monthly_report_blocks.py`), and add `competencia` to auto-generation (currently manual-only) feeding it the period's competition summary context. Rework the PDF template (and mirror in DOCX) to the approved section order for the Grupo de Alto Rendimiento: **Objetivo → Plan de entrenamiento → Desarrollo de actividades → Participación en competencia → Resultados obtenidos → Conclusiones**, keeping header + numbering of the institutional format; director-level sections (Contexto, Territorio) stay as the existing conditional blocks per the spec assumption (out of coach scope but header/numbering preserved).
- **Rationale**: The approved format names "Plan de entrenamiento" as a mandatory section; today no such block exists (hard gap). `competencia` auto-generation closes US1-scenario-2 ("ninguna sección obligatoria queda vacía") without manual typing. Regeneration semantics (preserve coach-edited `final_text`) already implemented — reused as-is (FR-009).
- **Alternatives considered**: renaming existing blocks only — insufficient (missing section); free-form template reorder without new block — rejected: section would render permanently "pendiente".

## R6. Photo register grouped by section (FR-007, clarification: automatic derivation)

- **Decision**: Extend `build_report_photo_evidence` to attach a derived `section` per photo from existing data: `session_kind == entrenamiento|otro` → "Grupo de Alto Rendimiento"; `actividad_conjunta|salida` → "Actividades Conjuntas"; **Competencia heuristic**: session whose `session_date` equals a `RaceEvent.event_date` of the period for the club's athletes → "Competencia". Template renders one titled group per section, with reserved placeholder slots ("Espacio reservado — sin fotografías del período") for empty groups.
- **Rationale**: Clarification mandates automatic derivation with no manual tagging and no upload-screen changes. There is no session↔race_event FK; the date-match heuristic is deterministic, cheap, and errs to "Alto Rendimiento" (safe default). Existing privacy filters (consent_ack, thumbnail, 6-photo/2 MB cap) preserved; cap applied per report, ordered to keep at least one photo per non-empty group.
- **Alternatives considered**: new `section` column on `SessionMedia` — rejected by clarification (manual tagging, upload-screen change); AI classification — rejected: non-deterministic, privacy surface.

## R7. Missing-input signaling (FR-012, clarification: inline only)

- **Decision**: Keep inline "—" for header fields; add explicit "**Pendiente de completar**" markers for empty mandatory narrative sections; extend the draft banner to list missing sections (US1 scenario 3). No pre-generation checklist, no blocking, no changes to other screens.
- **Rationale**: Direct clarification decision. Template-only change.

## R8. Frontend surface

- **Decision**: Minimal: (a) `ReportDetailPage` `BLOCK_ORDER` gains `plan_entrenamiento` (and keeps `competencia`, now auto-draftable); (b) download control becomes a `DropdownMenu` (already installed at `frontend/src/components/ui/dropdown-menu.tsx` — verified via shadcn MCP + repo) with "Descargar PDF" / "Descargar DOCX"; (c) types/zod schemas updated for new metric fields. No new routes, no new screens (per clarifications).
- **Rationale**: All input screens already capture the necessary data (sessions wizard verified: fields NOT NULL; ProjectProfilePage covers header fields). UI copy in español neutro.
- **Alternatives considered**: report preview redesign — out of scope; readiness checklist screen — rejected in clarification.

## R9. Migration & deploy impact

- **Decision**: **No Alembic migration.** All persisted changes ride existing JSON columns (`metrics_snapshot`, `narrative_blocks`, `competition_results`). New `DocumentTemplate` enum member + DOCX template file are code/assets. Existing stored reports keep rendering: templates guard new keys with defaults (old snapshots lack `session_detail` → section renders "Pendiente — regenerar informe").
- **Rationale**: Lowest-risk deploy on Render free tier; backward compatibility explicit.
