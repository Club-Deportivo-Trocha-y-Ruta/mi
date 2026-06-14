# Implementation Plan: Coach Per-Athlete Qualitative Notes on Competition Results

**Branch**: `claude/athlete-notes-race-results-zjdesm` | **Date**: 2026-06-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-race-result-athlete-notes/spec.md`

## Summary

Give the coach/admin a short, free-text qualitative note per club rider per válida, captured in the
competition's Results view (e.g. "falla mecánica vuelta 2", "no alcanzó a calentar", "solo una vuelta, no
se sintió bien"). The note is coach/admin-only, persists across result re-imports, and is fed — after the
existing real-name scrub + pseudonymization used for `weather_notes` — as grounding context to BOTH the
automatic per-athlete/per-válida AI insight and the coach-only competition chat, so the analysis reasons
about the "why" behind a placing, not just the numbers. When no note exists, both AI surfaces behave exactly
as today (no fabricated context).

**Technical approach** (from Phase 0 research): add a dedicated `coach_note` field plus authorship/timestamp
metadata (`coach_note_author_id`, `coach_note_updated_at`) to the existing per-athlete `race_results` row —
leaving the importer's legacy `notes` column untouched to avoid semantic collision; expose an upsert (`PUT`)
+ clear (`DELETE`) endpoint guarded by the existing `require_role([coach, admin])` dependency; embed the
note (coach/admin only) in the `ResultRow` read schema; extend the race-analyst per-athlete serializer
(`_serialize_result`) and the coach-only chat per-athlete tool to carry the **scrubbed** note via the
existing `anonymize` path; build the editor in the Results tab mirroring `EditConditionsDialog` with shared
shadcn/ui + React Hook Form + Zod + an optimistic TanStack Query mutation.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async) + aiomysql, Alembic, PyJWT + bcrypt (backend);
React 19 + Vite, shadcn/ui + Tailwind, TanStack Query, Zustand, React Hook Form + Zod, axios (frontend);
existing race-analyst AI graph (LangGraph-style nodes, Gemini via the project AI provider).

**Storage**: MySQL 8.4 (prod Hostinger); `race_results` extended with `coach_note`, `coach_note_author_id`,
`coach_note_updated_at`.

**Testing**: `pytest` + `httpx.AsyncClient` + `aiosqlite` (backend); `vitest` + Testing Library + `jest-axe`
(frontend).

**Target Platform**: Linux server (Render, Docker, Oregon free tier); coach on tablet, parents on Android /
intermittent 3G-4G.

**Project Type**: Web application (FastAPI backend + React SPA frontend) — modular monolith.

**Performance Goals**: Note capture under 1 minute (SC-001); note embedded in the existing results read (no
N+1); honest save/failure feedback over flaky connectivity (FR-011/SC-006).

**Constraints**: Minors-privacy NON-NEGOTIABLE — note scrubbed of real names + pseudonymized before any AI
prompt (reuse `anonymize` / `_scrub_event_conditions` path); never in logs or AI prompt logs
(`AI_LOG_PROMPTS=false` in prod); never in any parent/athlete-facing output. español neutro (Colombia) for
all product copy; English for code/docs/instruction corpus.

**Scale/Scope**: ~30-60 club athletes, 7 válidas/season; one note per (rider, válida). Backend: 1 migration,
1 model change, 2 schema additions, 2 endpoints, AI serializer + chat tool + anonymize edits. Frontend: 1
editor component + 1 mutation hook + Results-tab wiring + types.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Code Quality & Maintainability
- [x] New field named for intent (`coach_note`), not reusing the ambiguous importer `notes` column → avoids
  semantic collision and importer-overwrite-on-reimport. Service/schema additions get docstrings.
- [x] `ruff` + `mypy` (backend), `eslint` + `tsc --noEmit` (frontend) must pass — blockers, not follow-ups.
- [x] No premature abstraction: 1:1 columns on `race_results` instead of a new table (rule-of-three honored).
  Human review required before any merge to `main`.

### II. Testing Standards (NON-NEGOTIABLE)
- [x] Backend: happy + negative (403 parent/athlete, 422 empty/over-length, 404/4xx on non-club competitor)
  per router & permission; AI serializer / chat-tool unit tests.
- [x] **Privacy invariant tests** (mandatory for minors' data): note scrubbed of real names before AI
  serialization; note absent from parent-facing serializers; no PII in logs; note absent → AI context
  unchanged (mirrors `test_race_analysis_privacy.py`).
- [x] Frontend: `vitest` + Testing Library for editor branching + hidden-for-parent; `jest-axe` zero
  violations on the dialog. Bug fixes land with a regression test.

### III. User Experience Consistency
- [x] Product copy (labels, validation, empty/error states) in español neutro (Colombia); code/docs English.
- [x] Shared shadcn/ui (`Sheet`/Dialog/Textarea); React Hook Form + Zod with inline localized errors (no
  competing HTML5 validation), mirroring `EditConditionsDialog`. 48×48px targets; dialog traps focus,
  Escape-dismissible.
- [x] Explicit loading/empty/error/save-failure states; status color tokens reused (green/amber/red/gray).
  WCAG 2.1 AA floor.

### IV. Performance
- [x] Note embedded in existing `ResultRow` read (no extra round-trip); optimistic mutation for instant
  feedback; invalidate-on-settled keeps cache truthful over 3G.

**Result**: PASS — no violations; Complexity Tracking table not required.

## Project Structure

### Documentation (this feature)

```text
specs/013-race-result-athlete-notes/
├── plan.md              # This file (/speckit-plan output) ✅
├── research.md          # Phase 0 output ✅
├── data-model.md        # Phase 1 output ✅
├── quickstart.md        # Phase 1 output ✅
├── contracts/           # Phase 1 output ✅
│   └── coach-note.md
├── checklists/
│   └── requirements.md  # spec quality checklist ✅
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

Web application (existing modular monolith). Concrete files this feature touches (from code mapping):

```text
backend/
├── app/
│   ├── models/race_result.py                         # + coach_note, coach_note_author_id, coach_note_updated_at
│   ├── schemas/race_results.py                        # ResultRow gains coach_note(+updated_at); new CoachNoteUpdate
│   ├── routers/race_events.py                         # PUT + DELETE /race-results/{result_id}/coach-note (RBAC)
│   ├── dependencies.py                                # reuse require_role([coach, admin])
│   └── services/race/ai/
│       ├── grounding.py                               # + load_per_result_note(db, athlete_id, event_id)
│       ├── nodes/load_race_data.py                    # _serialize_result carries coach_note
│       ├── nodes/anonymize.py                         # scrub coach_note (like _scrub_event_conditions)
│       └── nodes/analyst_agent.py + chat per-athlete tool  # scrubbed note in prompt/tool output
├── alembic/versions/                                  # new migration, revises f9a0b1c2d3e4
└── tests/routers/                                     # test_race_result_coach_note*.py + privacy + AI node tests

frontend/
├── src/
│   ├── types/raceResults.types.ts                     # RaceResultRow gains coach_note
│   ├── api/raceResults.ts                             # setCoachNote / clearCoachNote
│   ├── hooks/race/useRaceResults.ts                   # useSetResultCoachNote (optimistic) + invalidation
│   ├── hooks/race/invalidation.ts                     # (reuse byEventFiltered key for invalidation)
│   ├── components/race/EditResultNoteDialog.tsx        # new editor (mirror EditConditionsDialog)
│   └── components/competitions/results/ResultsTable.tsx # note affordance per club row (coach/admin only)
└── src/components/race/__tests__/ + results __tests__/ # vitest + jest-axe
```

**Structure Decision**: Web application (backend + frontend), extending the existing Competitions / Race
Results module (`race_events.py` results endpoints, `ResultsTable.tsx`) and the race-analyst AI graph
(`services/race/ai/nodes/*`). No new top-level structure; all changes land in established directories,
reusing the `update_race_event_conditions` endpoint pattern and the `EditConditionsDialog` UI pattern.

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations.
