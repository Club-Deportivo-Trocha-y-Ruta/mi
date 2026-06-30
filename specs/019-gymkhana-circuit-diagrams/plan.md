# Implementation Plan: Gymkhana Circuit Diagrams & Joint Session Authoring

**Branch**: `claude/spec-kit-agent-setup-poepvz` (session branch; feature dir `019-gymkhana-circuit-diagrams`) | **Date**: 2026-06-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/019-gymkhana-circuit-diagrams/spec.md`

## Summary

Upgrade feature 018's illustrative gymkhana layouts from monospace **ASCII** to proper **2D graphical diagrams**, and (later) let the coach **compose a combined gymkhana session** by dragging circuit elements onto a canvas — without forking the catalog or the Training Sessions session-assembly flow already built in 018.

The keystone is one project-owned, library-agnostic **`GymkhanaLayout`** JSON schema (`{ width, height, elements:[{ kind, x, y, rotation?, style?, label? }] }`) that is the single persisted source of truth and drives **three** renderers: a presentational React inline-SVG `<CircuitDiagram>` (in-app), a server-side Jinja inline-SVG partial (printable session sheet), and — Phase B — a `react-konva` drag-and-drop editor. Konva's own `toJSON()` is deliberately **not** the persisted format.

Delivery is split into two independently shippable phases:

- **Phase A (MVP / priority)**: `GymkhanaLayout` Zod + Pydantic schemas; the `<CircuitDiagram>` React component; the Jinja inline-SVG partial reusing the `templates/documents/pdf/charts/*.svg.jinja` pattern; an **additive nullable `layout_json` column** on `technique_exercises` (one Alembic revision, single head); and an **idempotent backfill** of the ~24 seeded gymkhana croquis into `GymkhanaLayout` JSON, keeping `layout_ascii`/`layout_alt` as the a11y/fallback source.
- **Phase B (later)**: a `react-konva` `/technique/composer` editor reading/writing the same schema, binding several catalog exercises into one combined gymkhana session through the existing `TechniqueSessionExercise` link; the combined circuit is **derived at view time** (no new table, no new column, zero migrations).

Reuses the existing FastAPI + SQLAlchemy 2 async + Alembic + MySQL backend and the React 19 + Vite + shadcn/ui + TanStack Query frontend. **No AI/LLM and no external integration.** Phase A adds **no** new runtime dependency (inline SVG only); Phase B adds **one** client dependency (`react-konva` + `konva`).

**Tooling for processes**: Context7 MCP is the source for any `react-konva`/Konva API confirmation in Phase B; the seeded backfill content is **data** transcribed from the existing seed (`backend/app/data/technique_catalog.py`) and `docs/14-tecnica-gymkana-7-15/research.md` — never invented.

## Technical Context

**Language/Version**: Python 3.14 (backend), TypeScript 5 / React 19 (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 (async, aiomysql), Alembic, Pydantic v2 (existing); React 19 + Vite, shadcn/ui + Tailwind v4, TanStack Query, React Hook Form + Zod. **Phase A: no new runtime dependency.** **Phase B: `react-konva` (peer `react ^19.2.0`) + `konva`, MIT.**

**Storage**: MySQL 8.4 (Hostinger prod). Phase A: **one** additive nullable column `layout_json` on `technique_exercises` + idempotent data backfill, via a single Alembic revision. Phase B: **no** schema change.

**Testing**: backend `pytest` + `httpx.AsyncClient` + `aiosqlite`; frontend `vitest` + Testing Library + `jest-axe`. A **cross-renderer equivalence test** asserts the same `GymkhanaLayout` produces structurally equivalent SVG from the React component and the Jinja partial.

**Target Platform**: Linux server (Render free tier, Oregon) + mobile web (coach on a tablet in the field, intermittent 3G/4G, ~50 s cold start).

**Project Type**: Web application (existing `backend/` + `frontend/`), extending feature 018.

**Performance Goals**: diagram render adds no network round-trip (layout ships inside the existing exercise-detail read; small JSON). Catalog/detail reads stay p95 ≤ 500 ms. `<CircuitDiagram>` is pure SVG (no canvas) → no main-thread jank. Phase B `react-konva` editor is a **lazy route chunk** (kept out of the shared bundle; budget ≤ 150 KB gz for the chunk). Cold-start banner (feature 012) on every async surface.

**Constraints**: minors privacy (Ley 1581) — diagrams carry **no** minor PII; Phase A elements have **no** free-text label (controlled set only, FR-023); español neutro for all product copy/legends/captions; WCAG 2.1 AA — every diagram exposes a text alternative (`role="img"` + `<title>`/`<desc>` derived from `layout_alt`) and distinguishes kinds by shape/pattern, not color alone; coach/admin only (inherits 018 RBAC); ASCII fallback retained.

**Scale/Scope**: single club; ~24 seeded exercises (subset are gymkhana with a layout); read-heavy; very low write volume (curation, Phase B composer).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Code Quality & Maintainability** — PASS. Extends existing `models/schemas/routers/services` + `routes/components/hooks/api` layering. One owned schema (`GymkhanaLayout`) shared client/server/editor; no divergent second diagram format (FR-006). `<CircuitDiagram>` replaces the ASCII `<pre>` in `CircuitLayout.tsx` with a fallback path, not a parallel component tree.
- **II. Testing (NON-NEGOTIABLE)** — PASS (planned). `GymkhanaLayout` validation (Zod + Pydantic: reject unknown `kind`, out-of-bounds/non-finite coords, accept empty); `<CircuitDiagram>` render + a11y (`role="img"`/`<title>`/`<desc>`, color-not-sole-channel) via `jest-axe`; **cross-renderer equivalence** test (React SVG ≅ Jinja SVG for a fixture layout); backfill idempotency test; ASCII-fallback test (no `layout_json` → renders legacy croquis); Phase B: composer round-trip (save→reopen→re-render equivalent), keyboard/SR add-position-remove path, assemble-creates-real-`TrainingSession` (no parallel store) reusing 018's assertion.
- **III. UX Consistency & Language** — PASS. All copy/legends/palette/captions in español neutro; shadcn/ui + Tailwind v4; designed loading/empty/cold-start states; diagram responsive + crisp on zoom; SR text alternative. This plan/spec in English (dev corpus).
- **IV. Performance** — PASS. Diagram ships inside the existing detail read (no extra request); pure SVG (no canvas) in-app and in PDF; Phase B Konva editor lazy-loaded out of the shared bundle; backfill runs once in the migration.
- **V. Youth Psychological Assessment Safeguards (NON-NEGOTIABLE)** — N/A as a clinical instrument. The mastery-climate ethos is unaffected — diagrams describe **placement only**, introduce no intensity/load prescription (FR-022), and add **no** minors-data surface (FR-019/023). Domain legibility reviewed by `technique-coach`.

**Result**: No violations. Complexity Tracking empty.

## Migration Decision (single-head check)

```text
$ cd backend && alembic heads
e1f2a3b4c5d6 (head)
```

**One head → no merge migration needed.** The earlier regex-introspection that suggested extra heads (`a1b2c3d4e5f8`, `a1b2c3d4e5f7`, `8c1d2e3f4a5b`) was a false positive (those are subsumed by the feature-004 3-way merge `b4c5d6e7f8a9` already in the chain); `alembic heads` is authoritative and reports a single head.

- **Chosen revision id**: `f1a2b3c4d5e6` — `f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py`, `down_revision = 'e1f2a3b4c5d6'`. *(If `f1a2b3c4d5e6` collides at implementation time, pick the next free hex id; the binding constraint is `down_revision='e1f2a3b4c5d6'` and a single resulting head.)*
- **Schema op**: `ADD COLUMN layout_json JSON NULL` on `technique_exercises` (nullable, additive, no default). MySQL 8.4 native `JSON`; SQLite test path stores as JSON-text — both fine for round-trip.
- **Data step (idempotent)**: in the same revision, `UPDATE` each seeded gymkhana row (matched by stable `slug`) setting `layout_json` from a backfill map, **only where `layout_json IS NULL`**; `layout_ascii`/`layout_alt` untouched. Re-runnable; safe on a championship-free / partially-seeded DB. Downgrade `DROP COLUMN layout_json`.
- **Verification**: SQLite via tests (project convention); prod runs through `entrypoint.sh` (`alembic upgrade head`). Phase B adds **no** migration.

## Code-grounding confirmations (verified against the repo, not assumed)

- **`technique_exercises` gains `layout_json`**: model `backend/app/models/technique_exercise.py::TechniqueExercise` currently has `layout_ascii: Mapped[str | None]` (Text) + `layout_alt` (Text) — add `layout_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)`. No other column changes.
- **Pydantic mirror**: `backend/app/schemas/technique.py` — add `GymkhanaLayout` + `CircuitElement` Pydantic models; expose `layout_json: GymkhanaLayout | None` on `ExerciseDetail` (line ~89) and accept it on `ExerciseCreate` (~262) / `ExerciseUpdate` (~292). `ExerciseListItem` stays lean (no layout in list reads).
- **Zod mirror**: `frontend/src/schemas/technique.schemas.ts` + types in `frontend/src/types/technique.types.ts` — add `gymkhanaLayoutSchema` + `circuitElementSchema`; extend `ExerciseDetail` (currently has `layout_ascii`/`layout_alt` at lines 74–75) with `layout_json: GymkhanaLayout | null`.
- **React renderer**: replace the ASCII `<pre>` body of `frontend/src/components/technique/CircuitLayout.tsx` with the new presentational `frontend/src/components/technique/CircuitDiagram.tsx` (inline SVG); `CircuitLayout` keeps the section shell + legend and chooses `<CircuitDiagram>` when `layout_json` is present, else the legacy ASCII `<pre>` (FR-010).
- **Jinja partial**: new `backend/templates/documents/pdf/charts/circuit_diagram.svg.jinja` mirroring the `line_positions.svg.jinja` macro pattern (`viewBox`, `role="img"`, `aria-label`, inline-only, no external fetch). Embedded into the **printable session sheet** template (O-1).
- **Router**: `backend/app/routers/technique.py` exercise-detail GET (line ~257/304) round-trips `layout_json`; create/update (POST ~334 / PUT ~662) persist it; visibility/curation paths unchanged. No new endpoint required for Phase A (layout travels on the existing exercise read/write).
- **Phase B reuse**: `frontend/src/components/technique/SessionAssembler.tsx` + `technique_session_exercises` link + `app/services/technique/assembler.py` are reused unchanged; the composer feeds them. Combined circuit derived at view time from linked exercises' `layout_json` (O-3) — no new persistence.

## Project Structure

### Documentation (this feature)

```text
specs/019-gymkhana-circuit-diagrams/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── rest-api.md      # Phase 1 output (REST contract delta vs 018)
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks output (not created here)
```

### Source Code (repository root) — delta over feature 018

```text
backend/
├── app/
│   ├── models/technique_exercise.py        # +layout_json (additive)
│   ├── schemas/technique.py                # +GymkhanaLayout/CircuitElement; layout_json on Detail/Create/Update
│   ├── routers/technique.py                # round-trip layout_json on detail/create/update
│   └── data/technique_catalog.py           # +backfill map: slug → GymkhanaLayout (from existing ASCII)
├── templates/documents/pdf/
│   ├── charts/circuit_diagram.svg.jinja    # NEW server-side inline-SVG circuit renderer
│   └── pdf/<printable-session-sheet>.html  # embeds the partial (O-1)
└── alembic/versions/
    └── f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py  # column + idempotent backfill

frontend/
└── src/
    ├── components/technique/
    │   ├── CircuitDiagram.tsx               # NEW presentational inline-SVG renderer (Phase A)
    │   ├── CircuitLayout.tsx                # chooses CircuitDiagram vs ASCII fallback
    │   └── composer/ (Phase B)              # react-konva editor + element palette
    ├── routes/technique/ComposerPage.tsx    # NEW /technique/composer (Phase B)
    ├── schemas/technique.schemas.ts         # +gymkhanaLayoutSchema/circuitElementSchema
    └── types/technique.types.ts             # +GymkhanaLayout/CircuitElement; layout_json on ExerciseDetail
```

**Structure Decision**: Web-application layout, extending feature 018's existing trees and conventions. Phase A is purely additive (one column + one renderer + one Jinja partial + backfill). Phase B adds an isolated, lazy `composer/` subtree and one new route; it reuses 018's assembler/link rather than forking session management.

## Phase 0 — Research (→ research.md)

Adopts the completed deep-research pass (24 adversarially-verified claims): (1) **static diagrams → declarative inline SVG**, no canvas lib, print/PDF-friendly + a11y via `role="img"`/`<title>`/`<desc>`; (2) **editor → `react-konva`** (MIT, React 19 peer, declarative, `draggable`+`Transformer`), Phase B only; (3) **one owned `GymkhanaLayout` schema** drives all renderers — Konva `toJSON()` rejected (drops images/handlers/custom logic); (4) **rejected** tldraw (proprietary, ~$6k/yr, watermark), Excalidraw (wrong UX), Pixi.js (WebGL overkill), Fabric.js (no React bindings); (5) **PDF feasibility confirmed in-repo** — `templates/documents/pdf/charts/*.svg.jinja` already render inline SVG print-clean with `role="img"`, so the server-side circuit renderer mirrors a proven pattern. See [research.md](./research.md).

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md): the `GymkhanaLayout` / `CircuitElement` schema (Zod ⇄ Pydantic), the additive `layout_json` column, the backfill map, validation rules, and the Phase-B "derived at view time" decision.
- [contracts/rest-api.md](./contracts/rest-api.md): the **delta** over 018 — `layout_json` on exercise detail read + create/update; no new endpoint in Phase A; Phase B reuses the existing assemble-session contract.
- [quickstart.md](./quickstart.md): end-to-end validation scenarios mapped to the user stories (diagram in-app, diagram in PDF, cross-renderer equivalence, ASCII fallback, Phase-B composer round-trip).
- Agent context: CLAUDE.md SPECKIT marker updated to point at this plan.

## Phase 2 — Tasks (handled by `/speckit-tasks`)

`/speckit-tasks` will generate `tasks.md`, group tasks by **phase then user story** (Phase A US1/US2 → Phase B US3) for independent delivery, assign each task to a specialized subagent (Appendix A), and order by dependency with `[P]` for parallelizable. **Phase A must be a self-contained, deployable increment** (migration + schema + renderer + Jinja partial + backfill + tests) before any Phase B task starts.

## Phase 3 — Implementation (handled by `/speckit-implement`)

`/speckit-implement` runs a dynamic workflow: dispatch tasks to assigned agents, parallelize independent `[P]` tasks, re-check Constitution gates (esp. minors-privacy: no PII in diagrams/logs; WCAG AA text alternative) before completing each phase. Phase A ships and can deploy independently; Phase B follows.

## Appendix A — Specialized-agent assignment (feeds /speckit-tasks & /speckit-implement)

| Work area | Specialized agent |
|---|---|
| `layout_json` column, single-head Alembic revision (`down_revision='e1f2a3b4c5d6'`), idempotent backfill data step | `database-architect` |
| `GymkhanaLayout`/`CircuitElement` Pydantic schemas, exercise detail/create/update round-trip, validation | `fastapi-architect` |
| `<CircuitDiagram>` inline-SVG renderer, `CircuitLayout` fallback wiring, Zod mirror, types; Phase B `react-konva` composer + palette + `/technique/composer` route + assemble wiring | `react-ui-engineer` |
| Server-side Jinja `circuit_diagram.svg.jinja` partial + printable-session-sheet embed (mirrors `charts/*.svg.jinja`) | `fastapi-architect` (+ `technical-writer` for caption copy) |
| Diagram legibility on tablet, zoom/print, WCAG AA text alternative + color-not-sole-channel, cold-start states; Phase B keyboard/SR non-drag fallback | `ux-researcher` |
| Backend tests (schema validation, cross-renderer SVG equivalence, backfill idempotency, ASCII fallback, RBAC) + frontend vitest + `jest-axe` + Phase B round-trip | `qa-engineer` |
| Minors-privacy audit (no PII in diagrams/labels/logs/PDF captions; Phase A no-free-text-label enforced) | `data-privacy-guard` |
| Confirm element vocabulary matches the club's real circuit materials + research fidelity of the backfill | `technique-coach` |
| Backfill-map extraction from existing ASCII croquis (`technique_catalog.py`) + `docs/14-...` into `GymkhanaLayout` JSON | `data-analyst` |
| Module doc in `docs/`, CLAUDE.md status + implementation-status update | `technical-writer` |
| Run migration on Render, deploy Phase A, smoke test, cold-start mitigation | `devops-engineer` / `release-manager` |

Orchestration delegated by `engineering-lead`, with `head-coach-lead`/`technique-coach` consulted for circuit-vocabulary correctness.

## Complexity Tracking

No constitution violations — table intentionally empty.
