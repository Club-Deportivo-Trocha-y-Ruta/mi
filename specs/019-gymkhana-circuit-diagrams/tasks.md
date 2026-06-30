---
description: "Task list for feature 019 — Gymkhana Circuit Diagrams & Joint Session Authoring"
---

# Tasks: Gymkhana Circuit Diagrams & Joint Session Authoring

**Input**: Design documents from `specs/019-gymkhana-circuit-diagrams/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/rest-api.md ✅, research.md ✅, quickstart.md ✅

**Tests**: INCLUDED — Constitution Principle II (Testing) is NON-NEGOTIABLE for this project and the plan enumerates a required test set (schema validation, cross-renderer SVG equivalence, backfill idempotency, ASCII fallback, a11y, Phase B round-trip).

**Organization**: Tasks are grouped by phase then user story. **Phase A (US1 + US2) is the deployable MVP** and MUST be complete and shippable before any Phase B (US3) task starts.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `[US1]`/`[US2]`/`[US3]` — user-story phases only (Setup/Foundational/Polish carry no story label)
- Each task names exact file path(s). Suggested specialized subagent in *(parens)* per plan Appendix A.

## Path Conventions

Web app, extending feature 018: `backend/app/...`, `backend/tests/...`, `backend/templates/...`, `backend/alembic/versions/...`, `frontend/src/...`. Frontend tests colocated as `*.test.tsx` per repo convention.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Pre-flight verification before authoring the migration and schema. No new runtime dependency in Phase A.

- [x] T001 Confirm Alembic single head before authoring the migration: run `cd backend && alembic heads` and verify it reports exactly `e1f2a3b4c5d6 (head)`; abort and escalate (merge migration needed) if more than one head is reported *(database-architect)*
- [x] T002 [P] Enumerate the seeded gymkhana slugs that have an existing `layout_ascii` croquis needing backfill, by reading `backend/app/data/technique_catalog.py` (the `LAYOUT_*` constants) and `docs/14-tecnica-gymkana-7-15/research.md §4`; produce the working list of `slug → croquis` to transcribe *(data-analyst + technique-coach)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The keystone `GymkhanaLayout` schema (Pydantic + Zod), the additive `layout_json` column + migration, and the idempotent backfill. **Both US1 and US2 depend on all of this.**

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [x] T003 [P] Add `layout_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)` to `TechniqueExercise` in `backend/app/models/technique_exercise.py` (additive; `layout_ascii`/`layout_alt` untouched) *(database-architect)*
- [x] T004 [P] Define `GymkhanaLayout` + `CircuitElement` Pydantic models in `backend/app/schemas/technique.py` with validation: `width>0`, `height>0`, known `kind` only, `0≤x≤width` / `0≤y≤height`, finite `rotation`/coords, `style` meaningful on `line` only, empty `elements` accepted, **Phase A free-text `label` rejected/stripped (controlled set only, FR-023)** *(fastapi-architect)*
- [x] T005 [P] Define `gymkhanaLayoutSchema` + `circuitElementSchema` (Zod) in `frontend/src/schemas/technique.schemas.ts` and the mirrored `GymkhanaLayout`/`CircuitElement` types + `layout_json` on `ExerciseDetail` in `frontend/src/types/technique.types.ts` (mirror T004 rules) *(react-ui-engineer)*
- [x] T006 Create Alembic revision `backend/alembic/versions/f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py` with `down_revision='e1f2a3b4c5d6'`; `upgrade()` = `op.add_column('technique_exercises', sa.Column('layout_json', sa.JSON(), nullable=True))`; `downgrade()` = `op.drop_column(...)` — single resulting head (depends on T003; use next free hex id if `f1a2b3c4d5e6` collides) *(database-architect)*
- [x] T007 Build the backfill map `slug → GymkhanaLayout` in `backend/app/data/technique_catalog.py`, transcribing each seeded gymkhana croquis (meaning-preserving, not pixel-perfect) — content reviewed by `technique-coach` for vocabulary/fidelity (depends on T002, T004) *(data-analyst + technique-coach)*
- [x] T008 Add the idempotent data step into revision `f1a2b3c4d5e6`: `UPDATE` each seeded gymkhana row matched by stable `slug`, setting `layout_json` **only where `layout_json IS NULL`**, leaving `layout_ascii`/`layout_alt` intact; re-runnable on partially-seeded DBs (depends on T006, T007) *(database-architect)*

### Foundational tests

- [x] T009 [P] Pydantic `GymkhanaLayout` validation tests (reject unknown `kind`, out-of-bounds/non-finite coords, `width`/`height`≤0, reject free-text `label`; accept empty `elements`) in `backend/tests/test_gymkhana_layout_schema.py` *(qa-engineer)*
- [x] T010 [P] Zod `gymkhanaLayoutSchema` validation tests (mirror T009 cases) in `frontend/src/schemas/technique.schemas.test.ts` *(qa-engineer)*
- [x] T011 [P] Backfill idempotency test: run the data step twice → identical `layout_json`, `layout_ascii`/`layout_alt` untouched, only-where-NULL respected, in `backend/tests/test_layout_backfill.py` *(qa-engineer)*

**Checkpoint**: Schema (both sides), column, migration, and backfill exist and are validated — US1 and US2 can now begin.

---

## Phase 3: User Story 1 — Graphical circuit diagram in-app (Priority: P1) 🎯 MVP — Phase A

**Goal**: Coach opens a gymkhana exercise and sees a crisp 2D inline-SVG diagram (cones, paths, gates, minas, beam, ring, direction arrows) with a Spanish legend, instead of an ASCII `<pre>`; ASCII fallback when no `layout_json`.

**Independent Test**: Sign in as coach → open a seeded gymkhana → a vector diagram renders from `layout_json` with the Spanish legend, stays crisp on zoom; a non-gymkhana exercise shows no diagram; an un-backfilled exercise falls back to ASCII.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL before implementation)

- [x] T012 [P] [US1] `CircuitDiagram` render test — each `kind` (cone/line+style/gate/mine/beam/ring/arrow) draws its distinct SVG primitive; rotation applied — in `frontend/src/components/technique/CircuitDiagram.test.tsx` *(qa-engineer)*
- [x] T013 [P] [US1] a11y test (`jest-axe`): diagram exposes `role="img"` + `<title>`/`<desc>` derived from `layout_alt`, distinguishes kinds by shape/pattern not color alone, zero AA violations — in `frontend/src/components/technique/CircuitDiagram.a11y.test.tsx` *(qa-engineer + ux-researcher)*
- [x] T014 [P] [US1] ASCII-fallback test — `layout_json` absent + `layout_ascii` present → legacy `<pre>` renders, no blank/error — in `frontend/src/components/technique/CircuitLayout.test.tsx` *(qa-engineer)*
- [x] T015 [P] [US1] Backend test — `GET /api/technique/exercises/{id}` returns `layout_json` round-tripped on `ExerciseDetail`; `null` for non-gymkhana; `ExerciseListItem` not extended — in `backend/tests/test_technique_exercise_layout_json.py` *(qa-engineer)*

### Implementation for User Story 1

- [x] T016 [US1] Round-trip `layout_json` on the exercise endpoints in `backend/app/routers/technique.py` (detail GET) and persist it on create/update; expose `layout_json: GymkhanaLayout | None` on `ExerciseDetail` and accept it on `ExerciseCreate`/`ExerciseUpdate` in `backend/app/schemas/technique.py` (keep `ExerciseListItem` lean) — depends on T004 *(fastapi-architect)*
- [x] T017 [P] [US1] Create presentational `frontend/src/components/technique/CircuitDiagram.tsx` — inline-SVG renderer for a `GymkhanaLayout` (palette cone/line(`dashed`|`solid`)/gate/mine/beam/ring/arrow), Spanish legend strings ("Cono", "Trayecto libre", "Trayecto técnico", "Puerta", "Mina", "Equilibrio", "Círculo de la muerte", "Dirección de recorrido"), `role="img"` + `<title>`/`<desc>`, responsive `viewBox`, no canvas/no new dep *(react-ui-engineer)*
- [x] T018 [US1] Wire `frontend/src/components/technique/CircuitLayout.tsx` to render `<CircuitDiagram>` when `layout_json` is present, else the legacy ASCII `<pre>` fallback; keep the section shell + legend (depends on T017) *(react-ui-engineer)*
- [x] T019 [US1] Ensure `layout_json` flows through the exercise-detail TanStack Query hook + typing so the detail page passes it to `CircuitLayout` in `frontend/src/...` technique detail hook/page (depends on T005, T016) *(react-ui-engineer)*

**Checkpoint**: US1 fully functional and independently testable — in-app graphical diagrams live with ASCII fallback.

---

## Phase 4: User Story 2 — Circuit diagrams in the PDF/email pipeline (Priority: P1) — Phase A

**Goal**: The **same** `GymkhanaLayout` renders server-side as inline SVG in the **printable session sheet** (O-1), print-clean, accessible, with zero external image fetch — visually equivalent to the in-app diagram.

**Independent Test**: Render the printable session sheet for a gymkhana with a `GymkhanaLayout` → the circuit appears as inline-SVG vector, visually equivalent to in-app, with a text alternative in the markup; an exercise without a layout omits the section gracefully.

### Tests for User Story 2 ⚠️ (write first)

- [x] T020 [P] [US2] Cross-renderer equivalence test — same `GymkhanaLayout` fixture → **structurally equivalent** SVG from `CircuitDiagram.tsx` and from the Jinja partial (criterion: same set/kind/position/rotation/order of primitives, not byte-identical) — in `backend/tests/test_circuit_renderer_equivalence.py` (or a shared fixture harness) *(qa-engineer)*
- [x] T021 [P] [US2] Jinja partial render test — inline SVG, `role="img"`, no external `<image>`/fetch, graceful omission when `layout_json` absent — in `backend/tests/test_circuit_diagram_partial.py` *(qa-engineer)*

### Implementation for User Story 2

- [x] T022 [US2] Create `backend/templates/documents/pdf/charts/circuit_diagram.svg.jinja` mirroring the `line_positions.svg.jinja` macro pattern (`viewBox`, `role="img"`, `aria-label` from `layout_alt`, inline-only, no external fetch); Spanish legend parity with `CircuitDiagram.tsx` *(fastapi-architect + technical-writer for caption copy)*
- [x] T023 [US2] **RESOLVED (coach/PM 2026-06-30): no per-session sheet existed → created a new one.** New `backend/templates/documents/pdf/training_session_sheet.html` (extends `documents/pdf/base/layout.html`, groups by Calentamiento/Parte principal/Vuelta a la calma, embeds `circuit_diagram.svg.jinja` per gymkhana exercise with `layout_json`, graceful omit otherwise, español neutro) + render fn `render_training_session_sheet(session_id, db, *, club_name)` in `backend/app/services/technique/session_sheet.py` (mirrors `DocumentGenerator`'s Jinja env, standalone). Test `backend/tests/test_training_session_sheet.py` (14 passed). *(fastapi-architect)*
- [x] T024 [US2] Verify legend/caption copy in the partial is español neutro and matches the in-app legend exactly (no divergent second format, FR-006) in `backend/templates/documents/pdf/charts/circuit_diagram.svg.jinja` *(technical-writer)*

**Checkpoint**: US2 functional → **Phase A is feature-complete and independently deployable** (migration + schema + both renderers + backfill + tests).

---

## Phase 5: User Story 3 — Compose a combined gymkhana session by dragging elements (Priority: P2) — Phase B

**Goal**: Coach drags circuit elements onto a canvas to lay out a combined circuit, assembles ≥2 catalog exercises into one **normal club training session** via the existing Training Sessions flow (no parallel store), with a round-trippable combined `GymkhanaLayout`.

**Independent Test**: Open `/technique/composer` → drag ≥3 element kinds + add ≥2 exercises → save → a single `TrainingSession` appears in the calendar/list, supports attendance/rubric, and the combined layout round-trips back into the editor.

**⚠️ Gate**: Do NOT start Phase B until Phase A (US1 + US2) is shipped/validated.

### Phase B setup

- [ ] T025 [US3] Add `react-konva` + `konva` (MIT, peer `react ^19.2.0`) as client deps and ensure the composer route is a **lazy chunk** (budget ≤150 KB gz, out of the shared bundle) in `frontend/package.json` + Vite route config *(react-ui-engineer)*

### Tests for User Story 3 ⚠️ (write first)

- [ ] T026 [P] [US3] Composer round-trip test — build layout → save → reopen → re-render in `<CircuitDiagram>` equivalent (no loss of elements/positions/rotations/labels, SC-006) — in `frontend/src/components/technique/composer/Composer.roundtrip.test.tsx` *(qa-engineer)*
- [ ] T027 [P] [US3] Keyboard/SR non-drag path test (`jest-axe`) — add/position(nudge)/remove elements without pointer-drag, AA-operable on tablet — in `frontend/src/components/technique/composer/Composer.a11y.test.tsx` *(qa-engineer + ux-researcher)*
- [ ] T028 [P] [US3] Assemble-creates-real-`TrainingSession` test — saving creates one session via the existing assembler (no parallel/duplicate store), references chosen exercises, re-save updates same session — reuse feature 018's assertion in `backend/tests/test_technique_assemble_combined_gymkhana.py` *(qa-engineer)*

### Implementation for User Story 3

- [ ] T029 [US3] Build the composer subtree `frontend/src/components/technique/composer/` — element palette + `react-konva` canvas with `draggable` nodes + `Transformer` (position/rotate/remove), capturing canvas state as `GymkhanaLayout` (same schema) *(react-ui-engineer)*
- [ ] T030 [US3] Create the lazy `/technique/composer` route `frontend/src/routes/technique/ComposerPage.tsx` (coach/admin RBAC inherited, cold-start state from feature 012) *(react-ui-engineer)*
- [ ] T031 [US3] Implement the keyboard/screen-reader accessible non-drag fallback (add element + nudge + remove controls) in the composer (FR-018) *(react-ui-engineer + ux-researcher)*
- [ ] T032 [US3] Wire composer save → existing `POST /api/technique/sessions/assemble` (reuse `SessionAssembler.tsx` + `services/technique/assembler.py`); arrange exercises into calentamiento/principal/vuelta_calma; surface 018's mixed-age-band notice; edit-updates-same-session (FR-014/015/016) *(react-ui-engineer)*
- [ ] T033 [US3] Relax the Phase A no-free-text rule for the composer with anti-PII guard — allow `label` but block athlete name/DOB prompts; client validation in composer + server guard in `backend/app/schemas/technique.py` (FR-019/023 Phase B) *(react-ui-engineer + fastapi-architect)*
- [ ] T034 [US3] Derive the combined circuit at view time from the linked exercises' `layout_json` (no new persistence, no new column, O-3) in the composer/detail view *(react-ui-engineer)*

**Checkpoint**: US3 functional — joint gymkhana authoring live, reusing the existing session module.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T035 [P] `data-privacy-guard` audit — no minor PII via diagram labels, logs, or PDF captions; Phase A no-free-text-label enforced; Phase B anti-PII guard verified (SC-007) *(data-privacy-guard)*
- [ ] T036 [P] `ux-researcher` review — tablet-width legibility, zoom/print crispness, color-not-sole-channel, cold-start/loading/empty states on diagram + composer surfaces (SC-003/SC-004) *(ux-researcher)*
- [ ] T037 [P] `technique-coach` sign-off — element vocabulary matches the club's real circuit materials and the backfill preserves each croquis's meaning *(technique-coach)*
- [ ] T038 [P] Docs — new module doc in `docs/`, update `CLAUDE.md` implementation-status row (019) and `docs/implementation-status.md` *(technical-writer)*
- [ ] T039 Run `specs/019-gymkhana-circuit-diagrams/quickstart.md` validation scenarios end-to-end (in-app diagram, PDF diagram, cross-renderer equivalence, ASCII fallback, Phase-B round-trip) *(qa-engineer)*
- [ ] T040 Deploy Phase A — run migration `f1a2b3c4d5e6` on Render (`alembic upgrade head` via `entrypoint.sh`), post-deploy smoke test, ~50 s cold-start mitigation *(devops-engineer / release-manager)*

### Phase A follow-ups (surfaced during T023 — wire-up to fully expose the printable sheet)

- [ ] T041 [US2] Add `GET /api/technique/sessions/{id}/sheet` endpoint (coach|admin RBAC) returning `text/html` (or `application/pdf` via WeasyPrint) by calling `render_training_session_sheet(...)` in `backend/app/routers/technique.py` *(fastapi-architect)*
- [ ] T042 [US2] Frontend "Imprimir hoja de sesión" action on the technique session detail page (opens/downloads the sheet URL) *(react-ui-engineer)*
- [ ] T043 `technique-coach` review of the `busqueda-del-tesoro-relevo` backfill layout (flagged ILLUSTRATIVE — `layout_alt` says "no requiere layout fijo"); confirm or replace before deploy in `backend/app/data/technique_catalog.py` *(technique-coach)*

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (P1)** → no deps; start immediately.
- **Foundational (P2)** → after Setup; **BLOCKS US1, US2, US3**.
- **US1 (P3)** & **US2 (P4)** → after Foundational; both P1, both Phase A; can run in parallel (different files) but share T016's schema round-trip.
- **US3 (P5)** → after Foundational **AND** after Phase A (US1+US2) is shipped/validated (explicit gate; depends on the Phase A schema + renderer).
- **Polish (P6)** → after the targeted stories complete (T035–T039 after US-work; T040 after Phase A code-complete).

### User-story dependencies

- **US1** — independent of US2/US3 after Foundational.
- **US2** — depends on Foundational (schema + backfill) and shares the renderer-equivalence contract with US1; independently testable.
- **US3** — depends on Foundational schema and on Phase A being shipped; reuses 018's assembler.

### Within each story

- Tests written first and FAIL before implementation (Constitution II).
- Backend schema/round-trip (T016) before frontend hook wiring (T019).
- Renderer component (T017) before fallback wiring (T018).
- Composer canvas (T029) before assemble wiring (T032).

### Parallel opportunities

- **Setup**: T002 ∥ T001.
- **Foundational**: T003 ∥ T004 ∥ T005 (model / Pydantic / Zod — different files), then T006→T008 sequential; tests T009 ∥ T010 ∥ T011.
- **US1**: tests T012 ∥ T013 ∥ T014 ∥ T015; impl T017 ∥ (T016 backend); then T018→T019.
- **US2**: tests T020 ∥ T021; then T022→T023→T024.
- **US3**: tests T026 ∥ T027 ∥ T028; impl T029→T030→T031→T032, with T033/T034 alongside.
- **Polish**: T035 ∥ T036 ∥ T037 ∥ T038.

---

## Parallel Example: Foundational schema

```bash
# Different files, no inter-dependency — launch together:
Task: "Add layout_json column to TechniqueExercise in backend/app/models/technique_exercise.py"   # T003
Task: "Define GymkhanaLayout/CircuitElement Pydantic models in backend/app/schemas/technique.py"   # T004
Task: "Define gymkhanaLayoutSchema/circuitElementSchema Zod + types in frontend/src/schemas+types"  # T005
```

## Parallel Example: User Story 1 tests

```bash
Task: "CircuitDiagram render test in frontend/src/components/technique/CircuitDiagram.test.tsx"        # T012
Task: "jest-axe a11y test in frontend/src/components/technique/CircuitDiagram.a11y.test.tsx"           # T013
Task: "ASCII fallback test in frontend/src/components/technique/CircuitLayout.test.tsx"                # T014
Task: "Backend layout_json round-trip test in backend/tests/test_technique_exercise_layout_json.py"   # T015
```

---

## Implementation Strategy

### MVP first = Phase A (US1 + US2)

1. Phase 1 Setup → Phase 2 Foundational (schema + column + migration + backfill).
2. Phase 3 US1 (in-app diagram) → **STOP & VALIDATE** independently.
3. Phase 4 US2 (PDF/email diagram) → **STOP & VALIDATE**.
4. T040 deploy Phase A — this is a complete, shippable increment. Halt here if Phase B is deferred.

### Incremental delivery

- Foundational → US1 (demo: graphical diagrams in-app) → US2 (demo: same diagram in the printable session sheet) → **deploy Phase A** → US3 (demo: drag-and-drop combined session) → deploy Phase B.
- Each slice adds value without breaking the previous.

### MVP scope

**User Story 1** alone is a coherent demo (graphical diagrams replace ASCII in-app). The recommended deployable MVP is **US1 + US2 together (all of Phase A)**, since the document pipeline is part of the coach's real field workflow (printouts).

---

## Notes

- `[P]` = different files, no dependency on an incomplete task.
- `[Story]` label maps each task to US1/US2/US3 for traceability; Setup/Foundational/Polish carry no story label.
- Tests precede implementation and must fail first (Constitution II, NON-NEGOTIABLE).
- **Phase A adds no new runtime dependency** (inline SVG only); **Phase B adds `react-konva` + `konva`** (lazy chunk).
- **Migration hard constraint**: `down_revision='e1f2a3b4c5d6'` + a single resulting head; pick the next free hex id only if `f1a2b3c4d5e6` collides.
- **No AI/LLM** anywhere in this feature; **no minor PII** in any diagram, label, log, or document caption.
- Commit/branch policy for this work: stay on the current session branch — no new branch/worktree (per user instruction).
