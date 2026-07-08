# API Contracts — 022-align-monthly-report-format

Base: existing routers in `backend/app/routers/monthly_reports.py`. RBAC unchanged: coach/admin of the club for everything below; parents keep only the restricted summary endpoint.

## Modified (response shape only — additive)

### POST `/api/clubs/{club_id}/monthly-reports`  → 201 `MonthlyReportRead`
Behavior additions:
- `metrics_snapshot.session_detail[]` populated (see data-model §2).
- `metrics_snapshot.attendance_by_athlete[*]` gains `avg_rubric_effort|attitude|technique`.
- `narrative_blocks` includes auto-drafts for `plan_entrenamiento` and `competencia` (AI degradation → `ai_draft=null`, unchanged).
- `competition_results[]` items gain `event_id`, `series_kind`, `awards_points`.
- Errors unchanged: 409 existing period without `force_regenerate`; 503 AI unavailable; 403 role.

### GET `/api/clubs/{club_id}/monthly-reports/{year}/{month}` → 200 `MonthlyReportRead`
Same additive fields. Parent-role filtering: `session_detail` stripped along with `attendance_by_athlete`; `narrative_blocks`, `competition_results` remain nulled (existing rule extended — privacy test required).

### PATCH `.../blocks` / POST `.../blocks/{block_key}/regenerate`
- `block_key` domain now includes `plan_entrenamiento` (422 on unknown key, unchanged mechanism).
- Regenerating one block MUST NOT alter other blocks/snapshot (regression test).
- Status transition rules unchanged (draft→approved only).

### GET `.../pdf` → 200 `application/pdf`
- Document restructured to approved format (header + section order Objetivo, Plan de entrenamiento, Desarrollo de actividades, Participación en competencia, Resultados obtenidos, Conclusiones; per-session table; per-athlete attendance+rubric table; competition grouped by jornada with points note; photo register grouped by section with placeholders; draft banner lists missing sections).
- Old reports (pre-feature snapshots) MUST render without 500: missing keys → "Pendiente — regenerar informe".

## New

### GET `/api/clubs/{club_id}/monthly-reports/{year}/{month}/docx`
- **Auth**: coach/admin of club (same dependency as `/pdf`).
- **200**: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `Content-Disposition: attachment; filename="informe-tecnico-{year}-{month:02d}.docx"`.
- **404**: report not found. **403**: role/club. 
- Content parity contract: same context dict as PDF (single shared context builder) — sections, tables, photos (InlineImage), draft banner.

## Frontend contract (consumers)

- `frontend/src/api/trainingSessions.ts`: new `useDownloadMonthlyReportDocx` mirroring the PDF hook.
- `monthlyReport.schema.ts` / `trainingSession.types.ts`: additive fields above (zod: optional with defaults for backward compatibility).
- `ReportDetailPage`: `BLOCK_ORDER` = approved order incl. `plan_entrenamiento`; download `DropdownMenu` (PDF/DOCX). Copy in español neutro.
