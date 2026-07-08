# Data Model — 022-align-monthly-report-format

**No Alembic migration.** All changes are additive keys inside existing JSON columns of `MonthlyReport` (`backend/app/models/training_session.py:225`) plus Pydantic schema extensions.

## 1. MonthlyReport (existing table — unchanged DDL)

| Column | Type | Change |
|---|---|---|
| `metrics_snapshot` | JSON | + `session_detail`, per-athlete rubric fields (see §2) |
| `narrative_blocks` | JSON | + block key `plan_entrenamiento`; `competencia` now auto-draftable (see §3) |
| `competition_results` | JSON | items gain `event_id`, `series_kind`, `awards_points` (see §4) |
| `status` | Enum(draft, approved) | unchanged — lifecycle as today (draft→approved, no reversion; regenerate resets to draft) |

## 2. MonthlyMetrics (Pydantic — `backend/app/schemas/training_session.py`)

New fields:

```
session_detail: list[SessionDetailItem] = []   # NEW

SessionDetailItem:
  session_date: date
  start_time: time              # scheduled_start_time
  technical_focus: str
  location: str
  status: "executed" | "cancelled" | "planned"
  present_count: int            # attendance rows with presente/tarde
  attendee_total: int           # athletes expected that session
```

`AthleteAttendanceStats` gains (nullable — sessions without rubric):

```
avg_rubric_effort: float | None
avg_rubric_attitude: float | None
avg_rubric_technique: float | None
```

Validation: `session_detail` ordered by `session_date, start_time` ASC. Old snapshots without the key deserialize to `[]` (template shows "Pendiente — regenerar informe").

## 3. NarrativeBlock keys (`ALLOWED_BLOCK_KEYS`)

```
objetivo, plan_entrenamiento (NEW), desarrollo, competencia, resultados,
conclusiones, apoyos_materiales, analisis_grupo
```

- Auto-generated set (`_BLOCK_MAX_WORDS/_TITLES/_PROMPTS`): adds `plan_entrenamiento` and `competencia` (context: grouped competition summary, pseudonyms only).
- Block shape unchanged: `{ai_draft, final_text, ai_model, ai_generated_at}`.
- Regeneration invariant (FR-009): a regenerate of one key MUST NOT mutate any other key nor `metrics_snapshot`/`competition_results` (already enforced by `regenerate_block`; covered by regression test).

## 4. CompetitionResultItem (Pydantic)

```
athlete_name: str        # existing — coach/admin only (parents get nulled field)
category: str | None     # existing
position: int | None     # existing
points: int | None       # existing
event_name: str | None   # existing
event_date: date | None  # existing
event_id: int            # NEW — jornada identity (clarification: 1 evento = 1 jornada)
series_kind: "cup" | "championship" | None   # NEW — from RaceSeries.kind
awards_points: bool      # NEW — series_kind == "cup"
```

Grouping is presentation-only: templates `groupby event_id` (ordered `event_date ASC`), then by `category`.

## 5. Photo evidence item (in-memory shape from `build_report_photo_evidence`)

```
data_uri: str            # existing (base64 thumbnail)
session_date: date       # existing
caption: str | None      # existing
section: str             # NEW — derived, one of:
                         #   "Grupo de Alto Rendimiento" (session_kind entrenamiento|otro)
                         #   "Actividades Conjuntas"      (actividad_conjunta|salida)
                         #   "Competencia"                (session_date matches a RaceEvent.event_date of the period)
```

Derivation is deterministic; default section = "Grupo de Alto Rendimiento". Existing filters preserved: `consent_ack=True`, PHOTO, not deleted, thumbnail present, ≤6 photos / ≤2 MB. Empty groups render reserved placeholders.

## 6. DocumentTemplate registry

New member `TRAINING_MONTHLY_TECHNICAL_REPORT_DOCX` → asset `backend/templates/documents/docx/training_monthly_technical_report.docx` (docxtpl; `{%tr %}` row loops, `{%p if %}` conditionals, `InlineImage` photos). PDF template `training_monthly_technical_report.html` restructured to approved section order (both templates share the same context dict built by one context-builder function).

## 7. Entities NOT changed

`ClubProjectProfile` (all header fields already exist incl. `report_responsible`), `TrainingSession` (wizard already captures all report inputs — clarification), `SessionMedia` (no manual section attribute — clarification), `RaceResult`/`RaceEvent`/`RaceSeries` (read-only sources), parent privacy filtering in `_build_report_read` (unchanged behavior, extended to new fields: parents never receive `session_detail` athlete-level data, `competition_results`, photos).
