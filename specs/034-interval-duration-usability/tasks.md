---
description: "Task list — Interval Block Duration Usability (034)"
---

# Tasks: Interval Block Duration Usability — mm:ss Entry and Open-Ended "Until Lap Button" Blocks

**Input**: Design documents from `/specs/034-interval-duration-usability/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-delta.md, quickstart.md

**Tests**: INCLUDED — Constitution II (Testing NON-NEGOTIABLE) requires happy + negative backend tests and frontend component/hook/axe tests per change.

**Branch**: `main` (no dedicated branch, per user request)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1–US4 for story phases; none for Setup/Foundational/Polish
- **Agent**: suggested specialized agent (`Asignando a agentes especializados`)

## Agent legend

| Agent | Scope |
|---|---|
| `database-architect` | Alembic migration, enum, nullable column, model deltas |
| `fastapi-architect` | Pydantic schemas, service validators, matching engine, PDF context |
| `react-ui-engineer` | React components, Zod schema, hooks, total label, comparison table |
| `qa-engineer` | pytest + vitest + jest-axe tasks |
| `technical-writer` | CLAUDE.md implementation-note, docs |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: confirm baseline before edits — no new tooling needed (delta on existing feature 026).

- [ ] T001 Verify Alembic head is `b5c6d7e8f9a0` and feature-026 interval tests green as baseline: `cd backend && source .venv/bin/activate && alembic heads && pytest tests/test_interval_structures.py tests/test_interval_matching.py -q` — Agent: `qa-engineer`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: DB + enum foundation every story depends on. **⚠️ BLOCKS all user stories.**

- [ ] T002 Add `IntervalDurationType` enum (`fixed` | `open_lap`, `values_callable` per project convention) and duration-type columns to both block models in `backend/app/models/interval_structure.py`: `duration_type` (SAEnum, NOT NULL, default `fixed`) on `IntervalStructureBlock` and `IntervalTemplateBlock`; change `duration_s` to `Mapped[int | None]` (nullable) on both — Agent: `database-architect`
- [ ] T003 Create Alembic migration `c7d8e9f0a1b2_interval_block_duration_type` (down_revision `b5c6d7e8f9a0`) in `backend/alembic/versions/`: upgrade adds `duration_type` with `server_default='fixed'` to `interval_structure_blocks` + `interval_template_blocks` and alters `duration_s` to nullable on both; downgrade deletes `open_lap` rows (documented destructive step) then restores `duration_s` NOT NULL and drops the column — Agent: `database-architect`
- [ ] T004 Apply migration locally and verify schema + existing rows default to `fixed`: `cd backend && alembic upgrade head` then spot-check a seeded structure — Agent: `database-architect`

**Checkpoint**: schema ready; user stories can begin.

---

## Phase 3: User Story 1 — mm:ss duration entry (Priority: P1) 🎯 MVP

**Goal**: coach enters block durations as minutes:seconds; raw-seconds input gone; storage stays integer seconds.

**Independent Test**: create a structure with several fixed blocks via Min/Seg fields; stored seconds and total are correct; existing 90 s block hydrates as `1:30`.

### Tests for User Story 1 ⚠️

- [ ] T005 [P] [US1] Vitest for `MmSsInput` in `frontend/src/components/intervals/__tests__/MmSsInput.test.tsx`: seconds↔(min,sec) round-trip, Seg constrained 0–59, total>0 rule, null value handling — Agent: `qa-engineer`
- [ ] T006 [P] [US1] Vitest for `BlockRow` fixed-duration path + `StructureEditor` total in `frontend/src/components/intervals/__tests__/`: entering 5:00/1:30 yields duration_s 300/90 and total `6:30`; jest-axe on editor — Agent: `qa-engineer`

### Implementation for User Story 1

- [ ] T007 [P] [US1] Create reusable `MmSsInput` component in `frontend/src/components/intervals/MmSsInput.tsx`: two numeric fields (Min ≥ 0, Seg 0–59, 48px targets, numeric keyboard, per-field labels) ⇄ seconds value; controlled, null-aware — Agent: `react-ui-engineer`
- [ ] T008 [US1] Replace raw-seconds input in `frontend/src/components/intervals/BlockRow.tsx` with `MmSsInput` (fixed blocks); remove "Duración (segundos)" label; wire to RHF `duration_s` — Agent: `react-ui-engineer` (depends on T007)
- [ ] T009 [US1] Ensure `StructureEditor.tsx` totals + `formatMmSs` unchanged in behavior with new input; hydrate existing `duration_s` into Min/Seg on edit — Agent: `react-ui-engineer` (depends on T008)
- [ ] T010 [US1] Apply `MmSsInput` in the template library block editor (same `BlockRow` path — verify reuse; if a separate editor exists, wire it there) — Agent: `react-ui-engineer` (depends on T008)

**Checkpoint**: US1 fully functional — mm:ss entry everywhere, no raw seconds; storage unchanged.

---

## Phase 4: User Story 2 — open-ended warmup/cooldown (Priority: P2)

**Goal**: mark warmup/cooldown as "Libre — hasta botón de vuelta"; guardrails (warmup/cooldown only, never in repeat group); total shows partial.

**Independent Test**: structure with open warmup + fixed blocks saves, shows "Libre", requires no duration; work block has no open option; open+repeat blocked; total reads "20:00 + calentamiento libre".

### Tests for User Story 2 ⚠️

- [ ] T011 [P] [US2] pytest for `BlockIn`/`validate_structure_blocks` in `backend/tests/test_interval_structures.py`: open→warmup/cooldown only (422 on work/recovery), open→no repeat group (422), open→duration_s must be null (422), fixed→duration_s>0 still enforced, default `fixed` when omitted — happy + negative each — Agent: `qa-engineer`
- [ ] T012 [P] [US2] Vitest for `BlockRow` duration-type select + Zod refinements + `StructureEditor` open-total label in `frontend/src/components/intervals/__tests__/` and `frontend/src/schemas/`: option hidden for work/recovery, disabled in repeat group, order-independent block, "+ calentamiento libre" suffix; jest-axe — Agent: `qa-engineer`

### Implementation for User Story 2

- [ ] T013 [US2] Extend `BlockIn`/`BlockOut` in `backend/app/schemas/intervals.py`: add `duration_type` Literal (default `"fixed"`), make `duration_s` `int | None`; model-level cross-field validation deferred to service layer — Agent: `fastapi-architect` (depends on T002)
- [ ] T014 [US2] Extend `validate_structure_blocks` in `backend/app/services/intervals/structures.py`: enforce open→{warmup,cooldown}, open→repeat_group is None, open→duration_s is None, fixed→duration_s>0; español-neutro messages per contracts/api-delta.md; keep existing cadence/age-gate/repeat rules — Agent: `fastapi-architect` (depends on T013)
- [ ] T015 [US2] Update `total_planned_duration_s` computation (fixed-only sum, repeat-expanded) in `StructureOut` path — Agent: `fastapi-architect` (depends on T013)
- [ ] T016 [US2] Add `duration_type` literal + nullable `duration_s` + open-rule refinements to `frontend/src/schemas/intervals.schema.ts` (open→warmup/cooldown, open→no repeat group, open→no duration) — Agent: `react-ui-engineer`
- [ ] T017 [US2] Add duration-type select to `frontend/src/components/intervals/BlockRow.tsx`: "Tiempo fijo" / "Libre — hasta botón de vuelta"; render only for warmup/cooldown; disable when in repeat group; hide MmSsInput when open; keep zone+cadence required — Agent: `react-ui-engineer` (depends on T008, T016)
- [ ] T018 [US2] Update `StructureEditor.tsx` total label: fixed sum + "+ calentamiento libre" / "+ enfriamiento libre" / "+ bloques libres"; "Duración libre" when no fixed blocks — Agent: `react-ui-engineer` (depends on T017)

**Checkpoint**: US1 + US2 work; open blocks authorable and validated both sides.

---

## Phase 5: User Story 3 — plan-vs-actual understands open blocks (Priority: P3)

**Goal**: matching consumes a lap for open blocks positionally with informational `libre` status, never `fuera_tolerancia`; stored comparisons unchanged.

**Independent Test**: activity with laps linked to structure w/ open warmup → row 1 `libre` (actual shown), rows 2+ judged ±30%; missing first lap → `sin_dato`; old stored comparison renders unchanged.

### Tests for User Story 3 ⚠️

- [ ] T019 [P] [US3] pytest for matching engine v2 in `backend/tests/test_interval_matching.py`: open+lap→`libre` (no tolerance math), open no-lap→`sin_dato`, open never `fuera_tolerancia`, mixed structure positional shift, `ENGINE_VERSION == 2`, <10s lap noise filter unchanged — Agent: `qa-engineer`

### Implementation for User Story 3

- [ ] T020 [US3] Carry `duration_type` through `flatten_blocks`/`_to_step` in `backend/app/services/intervals/structures.py`: open steps get `planned_duration_s=None`, appear once — Agent: `fastapi-architect` (depends on T002)
- [ ] T021 [US3] Update `backend/app/services/intervals/matching.py`: bump `ENGINE_VERSION` 1→2; add `libre` status; skip `_is_within_tolerance` for open steps (guard `planned_duration_s is None`); open+lap→`libre` with actual elapsed, open no-lap→`sin_dato` — Agent: `fastapi-architect` (depends on T020)
- [ ] T022 [US3] Verify `match_runner.py` passes flattened open steps through without regression; confirm stored v1 comparisons served verbatim (no recompute) — Agent: `fastapi-architect` (depends on T021)
- [ ] T023 [US3] Update `frontend/src/components/intervals/PlanVsActualTable.tsx`: planned cell "Libre" for open rows, neutral-gray `libre` badge (informational per color semantics), actual duration shown — Agent: `react-ui-engineer`
- [ ] T024 [P] [US3] Vitest for `PlanVsActualTable` open-row rendering + jest-axe in `frontend/src/components/intervals/__tests__/` — Agent: `qa-engineer` (depends on T023)

**Checkpoint**: comparison correct for open blocks; no false out-of-tolerance; backward compatible.

---

## Phase 6: User Story 4 — PDF instructivo + templates (Priority: P3)

**Goal**: open blocks render "Libre — hasta botón de vuelta" in PDF per brand; templates preserve type on copy-on-attach.

**Independent Test**: instructivo for open-warmup structure shows the open text + zone/cadence; template with open cooldown keeps type after attach.

### Tests for User Story 4 ⚠️

- [ ] T025 [P] [US4] pytest for instructivo context + template copy in `backend/tests/test_interval_instructivo.py` and template test: open block context flag renders open text (all brands), copy-on-attach preserves `duration_type` — Agent: `qa-engineer`

### Implementation for User Story 4

- [ ] T026 [US4] Pass `duration_type` per block in `_build_blocks_context` of `backend/app/services/intervals/instructivo_pdf.py` — Agent: `fastapi-architect` (depends on T002)
- [ ] T027 [US4] Update `backend/templates/documents/pdf/session_instructivo.html`: `{% if b.duration_type == 'open_lap' %}Libre — hasta botón de vuelta{% else %}{{mins}} min {{secs}} s{% endif %}`, keep zone/cadence — Agent: `fastapi-architect` (depends on T026)
- [ ] T028 [US4] Ensure copy-on-attach in `backend/app/services/intervals/templates.py` copies `duration_type` + nullable `duration_s`; template validation parity with structure validators — Agent: `fastapi-architect` (depends on T014)

**Checkpoint**: all four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting

- [ ] T029 [P] Add implementation note for feature 034 to `CLAUDE.md` (duration_type discriminator, engine v2, MmSsInput, migration c7d8e9f0a1b2) and status row to implementation table — Agent: `technical-writer`
- [ ] T030 Run full interval suites + quickstart.md scenarios: `cd backend && pytest tests/test_interval_*.py` and `cd frontend && pnpm vitest run src/components/intervals src/schemas`; confirm all-fixed structures produce identical outputs (regression) — Agent: `qa-engineer`
- [ ] T031 Lint/type gates: `cd backend && ruff check . && mypy app/services/intervals` + `cd frontend && pnpm eslint src/components/intervals && pnpm tsc --noEmit` — Agent: `qa-engineer`

---

## Dependencies & Execution Order

### Phase dependencies

- Setup (T001) → Foundational (T002–T004) **BLOCKS all stories** → Stories → Polish.
- **Model/migration (T002–T004) is the hard gate**: every story touches `duration_type`.

### Story dependencies

- **US1 (P1)**: needs only frontend (T007–T010) — but schema `duration_s` nullability (T013) helps; US1 can ship with `duration_type` defaulted server-side. MVP.
- **US2 (P2)**: backend schema+validators (T013–T015) + frontend type select (T016–T018). Depends on T002.
- **US3 (P3)**: matching (T020–T022) + table (T023). Depends on T002; independent of US2 UI.
- **US4 (P3)**: PDF + templates (T026–T028). Depends on T002 (and T014 for template validation parity).

### Within stories

- Tests written first (should fail), then implementation (Constitution II TDD-leaning).
- Models → schemas → services → endpoints/UI.

### Parallel opportunities

- T005, T006 [P] (US1 tests) parallel.
- T011, T012 [P] (US2 tests) parallel.
- After T002–T004: US1 (react-ui-engineer), US3 backend (fastapi-architect), US4 backend (fastapi-architect) can proceed by different agents in parallel; US2 spans both.

---

## Parallel Example: post-Foundational fan-out

```text
# After T004 (migration applied), dispatch in parallel:
react-ui-engineer:  T007 MmSsInput  (US1)
fastapi-architect:  T020→T021 matching engine v2  (US3)
fastapi-architect:  T026→T027 PDF instructivo  (US4)
qa-engineer:        T005/T006/T011/T019/T025 test scaffolding
```

---

## Implementation Strategy

### MVP (US1 only)

1. T001 → T002–T004 (foundational) → T005–T010 (US1) → validate mm:ss entry → demo.
   - Note: US1 alone delivers the biggest pain relief (raw-seconds gone).

### Incremental

1. Foundation → US1 (mm:ss) → US2 (open blocks) → US3 (matching) → US4 (PDF/templates).
2. Each story independently testable; all-fixed structures never regress.

### Agent assignment summary

| Agent | Tasks |
|---|---|
| `database-architect` | T002, T003, T004 |
| `fastapi-architect` | T013, T014, T015, T020, T021, T022, T026, T027, T028 |
| `react-ui-engineer` | T007, T008, T009, T010, T016, T017, T018, T023 |
| `qa-engineer` | T001, T005, T006, T011, T012, T019, T024, T025, T030, T031 |
| `technical-writer` | T029 |

---

## Notes

- [P] = different files, no incomplete-task dependency.
- Storage unit stays seconds; `duration_type` is the only new semantic axis.
- Backward compatibility is a hard gate: old rows/drafts = `fixed`; stored v1 comparisons served verbatim.
- Commit per logical group (regla git del proyecto: no auto-commit; mostrar mensaje).
- Coach/admin-only surface unchanged (parents/athletes 403).
