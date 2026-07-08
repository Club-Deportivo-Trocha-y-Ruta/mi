# Quickstart — 022-align-monthly-report-format

Validation guide. Contracts: [contracts/monthly-report-api.md](contracts/monthly-report-api.md) · Data: [data-model.md](data-model.md).

## Prerequisites

```bash
source backend/.venv/bin/activate
docker compose up -d          # MySQL + seed (dev creds in CLAUDE.md)
cd backend && uvicorn app.main:app --reload
```

Seed data must include: sessions with attendance/rubrics in the target month, ≥1 competition with results (one `cup` and, ideally, one `championship` event), photos with `consent_ack`, and a complete ClubProjectProfile.

## Scenario 1 — Approved structure & header (US1 / SC-001, SC-002)

1. Login coach → `POST /api/auth/login` (`entrenador@trochyruta.com`).
2. `POST /api/clubs/1/monthly-reports {"year":2026,"month":6,"force_regenerate":true}`.
3. `GET /api/clubs/1/monthly-reports/2026/6/pdf` → open PDF.
   - Expect header: Nombre del proyecto, Entidad ejecutora, Período, Responsable — no "—" (profile complete).
   - Expect section order: Objetivo → Plan de entrenamiento → Desarrollo de actividades → Participación en competencia → Resultados obtenidos → Conclusiones.
   - Draft banner "BORRADOR" present until approved; banner lists any missing sections.

## Scenario 2 — Enriched detail (US2 / SC-004)

Same report JSON (`GET .../monthly-reports/2026/6`):
- `metrics_snapshot.session_detail[]` — one row per session (fecha, hora, foco, lugar, asistencia).
- `metrics_snapshot.attendance_by_athlete[*].avg_rubric_*` present.
- `competition_results[]` — items carry `event_id`, `series_kind`, `awards_points`; PDF groups by jornada (evento) + categoría with "otorga/no otorga puntos" note (championship → no otorga).

## Scenario 3 — Photo register grouped (US3)

PDF final section "Registro Fotográfico": groups Grupo de Alto Rendimiento / Competencia / Actividades Conjuntas derived automatically; empty group → reserved placeholder. Month without photos → all placeholders, no error.

## Scenario 4 — DOCX editable (FR-011)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/clubs/1/monthly-reports/2026/6/docx" -o informe.docx
```
Opens in Word/LibreOffice, editable, same content as PDF.

## Scenario 5 — Regeneration isolation (FR-009) & privacy (FR-010, SC-005)

1. Edit a block (`PATCH .../blocks`), then `POST .../blocks/objetivo/regenerate` → other blocks and tables unchanged.
2. Login parent → `GET /api/clubs/1/monthly-reports/2026/6` → no `narrative_blocks`, no `competition_results`, no `session_detail`, no athlete names. `/pdf` and `/docx` → 403.

## Scenario 6 — Backward compatibility

`GET .../pdf` on a report generated BEFORE this feature (old snapshot) → 200, new sections show "Pendiente — regenerar informe", no 500.

## Test commands

```bash
cd backend && pytest tests/ -k "monthly_report or report" -q
cd frontend && npx vitest run src/routes/training src/api --silent
```

Expected: all green, incl. new tests (session_detail aggregation, competition grouping/points note, photo section derivation, DOCX endpoint 200/403, parent privacy invariants, regenerate isolation, old-snapshot render, jest-axe on ReportDetailPage).
