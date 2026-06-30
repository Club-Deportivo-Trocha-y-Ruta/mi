# Quickstart: Gymkhana Circuit Diagrams & Joint Session Authoring

End-to-end validation scenarios mapped to the spec's user stories. Phase A is independently shippable; Phase B follows. Run as a coach/admin (athletes/parents have no access — FR-021).

## Setup

```bash
# backend
cd backend && source .venv/bin/activate
alembic upgrade head            # applies f1a2b3c4d5e6 (layout_json + backfill)
uvicorn app.main:app --reload

# frontend
cd frontend && npm run dev
```

## Phase A

### QS-A1 — Graphical diagram in-app (US1)
1. Sign in as coach; open the technique catalog; open a **seeded gymkhana** exercise.
2. **Expect**: a 2D graphical SVG circuit (not a monospace `<pre>`), with cones, paths (dashed=guía / solid=técnico), gates, minas, beam, ring, and direction arrows, plus a Spanish legend.
3. Pinch-zoom → diagram stays **crisp** (vector) and does not overflow on a tablet width.
4. Open a **non-gymkhana** exercise → **no** diagram (parity with 018).

### QS-A2 — ASCII fallback during transition (US1 #5)
1. Find/seed a gymkhana whose `layout_json IS NULL` but `layout_ascii` is set.
2. Open it → **expect** the legacy ASCII croquis renders (no blank, no error).

### QS-A3 — Diagram in the printable session sheet (US2)
1. Render the **printable session sheet** for a session containing a gymkhana with `layout_json`.
2. **Expect**: the circuit appears as inline-SVG vector in the PDF/HTML output, visually equivalent to the in-app diagram, with a text alternative present, **no** external image fetch, no clipping.
3. Render a sheet for an exercise without a layout → circuit section omitted gracefully.

### QS-A4 — Schema validation (FR-007)
1. `PUT` an exercise with a malformed `layout_json` (unknown `kind`, or `x > width`, or `width: 0`) → **422**, no half-render.
2. `PUT` with empty `elements: []` → **accepted**.
3. `PUT` with an element free-text `label` (Phase A) → rejected/stripped (FR-023/O-5).

### QS-A5 — Accessibility (FR-017)
1. Inspect the in-app diagram: `role="img"` + `<title>`/`<desc>` (from `layout_alt`); kinds distinguished by shape/pattern (not color alone).
2. `jest-axe` on the exercise-detail page → **0 violations**.

### QS-A6 — Cross-renderer equivalence (FR-006, SC-002)
1. Run the cross-renderer test: the same `GymkhanaLayout` fixture → React SVG and Jinja SVG are structurally equivalent.
2. **Expect**: same element set, positions, ordering; both inline-only.

### QS-A7 — Backfill idempotency (FR-009)
1. Re-run the migration's backfill (or its data step) twice → **no duplicate/changed** rows; `layout_ascii`/`layout_alt` untouched.

## Phase B (later)

### QS-B1 — Compose a combined gymkhana session by drag-and-drop (US3)
1. Open `/technique/composer`.
2. Drag ≥3 element kinds onto the canvas; position/rotate them.
3. Add ≥2 catalog exercises arranged into warm-up / main / cool-down; save.
4. **Expect**: a single **TrainingSession** appears in the existing calendar/session list (no parallel store — SC-005), referencing the chosen exercises, supporting attendance + rubric.

### QS-B2 — Lossless round-trip (SC-006)
1. Reopen the saved combined session in the composer.
2. **Expect**: the combined `GymkhanaLayout` (derived from linked exercises — O-3) reloads with all elements/positions/rotations intact and re-renders identically in `<CircuitDiagram>`.

### QS-B3 — Keyboard / screen-reader path (FR-018)
1. Without a pointer, add → nudge → remove an element via keyboard; SR announces each.
2. **Expect**: full add/position/remove operability (WCAG AA), not drag-only.

### QS-B4 — Mixed age bands (FR-016)
1. Compose a session spanning age bands; save.
2. **Expect**: allowed, with the existing feature-018 mixed-age-band notice surfaced.

## Privacy gate (both phases)
- Inspect diagrams, logs, and the PDF caption: **zero** minor PII (no athlete name/DOB) — `data-privacy-guard` audit required before close (SC-007).
