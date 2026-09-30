# Implementation Plan: IMDERTY monthly attendance sheet (FO-GDD-057 v006)

**Branch**: `main` (owner decision: no dedicated branch, no auto-commits) | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/047-imderty-attendance-sheet/spec.md`

## Summary

Admin and coach can fill in an IMDERTY section on each athlete record and generate IMDERTY's official monthly attendance workbook (FO-GDD-057 v006) from attendance the platform already records.

The IMDERTY section holds:
- separate surnames;
- document, address, barrio from a Yumbo catalog, school, grade and EPS;
- an optional phone, plus a "contacto principal" guardian;
- a separately authorized block for ethnicity, disability and armed-conflict victim status (never sexual orientation).

The workbook is produced by filling a sanitized, committed copy of the official template with `openpyxl`. Attendance comes from a new per-day attendance grid over executed sessions, club outings and joint trainings, and competitions (A > E > F). A readiness panel lists data gaps first. The screens are desktop-primary and adapt to phones.

## Technical Context

**Language/Version**: Python 3.13 (backend venv reports 3.14-compatible packages), TypeScript / React 19

**Primary Dependencies**:
- **Backend**: FastAPI, SQLAlchemy 2 async, Pydantic v2, Alembic, **`openpyxl>=3.1.5`** (new; research R1).
- **Frontend**: TanStack Query, React Hook Form + Zod, shadcn/ui + Tailwind v4.

**Storage**: MySQL 8.4 in production and aiosqlite in tests. The migration adds 5 tables and 1 column. The committed template is `backend/templates/documents/imderty/fo_gdd_057_v006.xlsx`.

**Testing**:
- **Backend**: pytest with `httpx.AsyncClient` in the default lane; the `mysql` lane covers the migration.
- **Frontend**: vitest, Testing Library, MSW and jest-axe.
- **E2E**: Playwright, with one desktop spec for the download flow.

**Target Platform**: Render (backend) and the Hostinger SPA. Users are admin and coach on desktop (primary), tablet or phone.

**Project Type**: Web application (backend and frontend).

**Performance Goals**: Once the server is awake, a single month for 40 athletes in ≤ 10 s and 5 months in ≤ 30 s (SC-007). Other endpoints stay at p95 ≤ 500 ms.

**Constraints**:
- **Ley 1581**: the new data is minors' identifying and sensitive data. It is never logged, sent to AI or placed in fixtures.
- **Files**: the generated file is not stored; the uploaded workbook is not used (no import).
- **Template**: it changes only through a platform update.

**Scale/Scope**: About 20–40 athletes and one club in practice; the format caps at 480 rows per month. There are 5 new screens or sections.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How the plan satisfies it | Status |
|---|---|---|
| I. Code quality | New code sits in its own domain package, `app/services/imderty/` (grid, workbook, readiness, surnames, barrio seed). It reuses the RBAC, audit, settings and download patterns (research R10) and passes `ruff check` + `tsc --noEmit`. It adds no parallel mechanism. | ✅ |
| II. Testing (NON-NEGOTIABLE) | Every endpoint gets allowed-path and denied-path tests. Backend tests cover every grid rule and the workbook structure. Privacy invariants are tested: no sexual orientation anywhere, sensitive fields blank without authorization, no new keys in parent views, template sanitized, no imports from AI/race/newsletter modules, audit meta without personal data. The migration upgrades and downgrades cleanly (`mysql` lane; reported as pending if not run). No AI pipeline changes, so no golden eval is required. | ✅ |
| III. UX consistency and responsive | All copy is in español neutro (Colombia). The screens use shadcn/ui, and forms use RHF + Zod. Loading, empty and error states are designed, including the cold-start "iniciando servidor" state on generation. Semantic colors: green = ready, amber = gaps. WCAG AA with jest-axe. Each screen's layout at each width is listed below. | ✅ |
| IV. Performance | Three range queries per request. No N+1: athletes, profiles, guardians and sensitive rows are batch-loaded with `selectinload`, with a query-count test. The workbook is built in memory, and new routes are lazy-loaded. | ✅ |
| V. Youth psychological safeguards | Not applicable: no psychological instrument is involved. | N/A |
| Minors' privacy (quality gate) | Sensitive data lives in separate tables and is erased on withdrawal. There is no orientation column. Access is limited to admin and coach. The audit carries only counts. The `data-privacy-guard` audit is mandatory before completion. | ✅ |

**Responsive layout per screen** (primary device: desktop; Principle III):

| Screen | ≥1280 px | 768 px | 360 px |
|---|---|---|---|
| Athlete "Datos IMDERTY" section (info tab) | two-column card | two-column card | single column; `inputmode="numeric"` for document and phone; searchable barrio combobox; sticky save bar |
| Sensitive data block | inline card | inline card | stacked, full-height sheet for edits |
| Planilla IMDERTY page (period picker, header, readiness, download) | picker and header side by side; gaps as a table | stacked; gaps as a table | stacked; gaps as cards with a link per athlete; download button full width |
| Club IMDERTY settings | form card | form card | single column |
| Barrio catalog (admin) | table with inline edit | table | cards; edit in a sheet |

**E2E**: a desktop Playwright spec covers the download flow. It is not a phone-primary (parent) screen, so a mobile run is recommended but not mandatory.

**Re-check after Phase 1**: ✅. There are no violations and the Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/047-imderty-attendance-sheet/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R11
├── data-model.md
├── quickstart.md
├── contracts/api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/<rev>_imderty_attendance_sheet.py   # 5 tables + parent_athlete.primary_contact_key + barrio seed
├── app/models/imderty.py                                # AthleteImdertyProfile, AthleteSensitiveAuthorization,
│                                                        # AthleteSensitiveData, ImdertyBarrio, ClubImdertySettings, enums
├── app/models/athlete.py                                # ParentAthlete.primary_contact_key
├── app/schemas/imderty.py
├── app/services/imderty/
│   ├── __init__.py
│   ├── barrios_seed.py          # 82 public SECTOR entries (duplicates collapsed)
│   ├── surnames.py              # split proposal + rebuild invariant (R7)
│   ├── profile.py               # profile/primary-contact/sensitive services (R8, R9)
│   ├── attendance_grid.py       # per-day marks (R4, R5)
│   ├── readiness.py             # gap codes
│   └── workbook.py              # openpyxl writer over the template (R1–R3, R6)
├── app/routers/imderty.py                               # all routes in contracts/api.md
├── app/routers/athletes.py                              # PATCH clears split confirmation
├── app/services/audit.py                                # new entity types + document kind
├── app/main.py                                          # mount router
├── scripts/build_imderty_template.py                    # dev-only sanitizer/cloner (R2)
├── templates/documents/imderty/fo_gdd_057_v006.xlsx     # sanitized, 12 month sheets + SECTOR
├── requirements.txt                                     # + openpyxl
└── tests/imderty/
    ├── test_surnames.py  test_attendance_grid.py  test_readiness.py
    ├── test_workbook.py  test_template_sanitized.py
    ├── test_imderty_profile_api.py  test_sensitive_api.py  test_barrios_api.py
    ├── test_settings_api.py  test_sheet_api.py
    └── test_imderty_privacy.py   # no imports from ai/llm/race/newsletter; parent views; logs; audit meta

frontend/
├── src/api/imderty.ts
├── src/hooks/useImderty.ts
├── src/schemas/imderty.ts
├── src/components/imderty/
│   ├── ImdertyProfileCard.tsx   ImdertyProfileForm.tsx   SurnameSplitConfirm.tsx
│   ├── SensitiveDataCard.tsx    PrimaryContactSelect.tsx BarrioCombobox.tsx
│   └── ReadinessPanel.tsx       HeaderOverridesForm.tsx
├── src/components/athletes/AthleteInfoCard.tsx          # mounts ImdertyProfileCard (coach/admin only)
├── src/routes/imderty/ImdertySheetPage.tsx              # + settings section
├── src/routes/imderty/BarrioCatalogPage.tsx             # admin
├── src/routes/… (router + nav entry, lazy)
└── e2e/imderty-sheet.spec.ts
```

**Structure Decision**: The web-application layout, with a new `imderty` domain package on each side. Existing files receive only small hooks: an athlete PATCH side effect, the audit catalogue, the router mount, an info-card slot and a nav entry.

## Complexity Tracking

There are no constitution violations to justify.
