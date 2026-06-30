# Phase 0 Research: Gymkhana Circuit Diagrams & Joint Session Authoring

Source: a completed deep-research pass (24 adversarially-verified claims). This file records the decisions adopted by the plan and the in-repo evidence that confirms each.

## R1 — Static drill diagrams: declarative inline SVG (no canvas library)

**Decision**: render static circuit diagrams as hand-authored declarative **inline SVG** React components. No canvas library, no heavy new client dependency in Phase A.

**Rationale**:
- No mature drop-in "tactic-board" library exists — the open-source options are all <16 stars and unmaintained; depending on one is a liability for a youth club on a free tier.
- Inline SVG is **print/PDF-friendly**, which is load-bearing: the diagram must render in the existing PDF/email document pipeline. **In-repo evidence**: `backend/templates/documents/pdf/charts/{line_positions,gap_pct,points_accumulated,projection_band,percentile_curves}.svg.jinja` already render inline SVG server-side, print-clean, with `role="img"` + `aria-label` and `viewBox`/`preserveAspectRatio`. The circuit renderer mirrors this proven pattern.
- SVG is **crisp at any zoom** (vector) — matters for a coach pinch-zooming on a tablet in sunlight.
- SVG is **accessible**: `role="img"` + `<title>`/`<desc>` give a first-class text alternative (WCAG 2.1 AA).

**Rejected for static**: Canvas/WebGL — neither prints well nor exposes an accessible tree.

## R2 — Coach drag-and-drop editor (Phase B): react-konva

**Decision**: the Phase B authoring canvas uses **`react-konva`** (Konva), MIT-licensed.

**Rationale**: actively maintained; React 19 compatible (peer dep `react ^19.2.0`); declarative React bindings; built-in `draggable` nodes + `Transformer`; all needed shape primitives (lines, shapes, arrows). Lower priority than the static diagrams, hence Phase B.

**Constraint carried into the plan**: the editor is a **lazy route chunk** (kept out of the shared bundle) and MUST provide a keyboard/SR-accessible non-drag path (add + nudge + remove) for WCAG AA on the tablet.

## R3 — Keystone: one owned `GymkhanaLayout` schema (NOT Konva `toJSON()`)

**Decision**: define **one** plain, library-agnostic `GymkhanaLayout` JSON schema that drives the static SVG renderer, the Jinja server renderer, AND the Konva editor, and is what is persisted.

**Rationale / refutation**: Konva's own `toJSON()` is **not** sufficient — it drops images, event handlers, and custom logic, and couples the DB format to a rendering library. Owning the schema decouples persistence from the rendering lib and lets the same bytes round-trip across all three renderers.

## R4 — Rejected editor alternatives

| Option | Why rejected |
|---|---|
| **tldraw** | Proprietary; dev-only default license; ~$6,000/yr commercial; watermark. Non-starter for a youth club on a Render free tier. |
| **Excalidraw** | General hand-drawn whiteboard; wrong UX for a structured, palette-driven circuit. |
| **Pixi.js** | WebGL; overkill; poor print/a11y story. |
| **Fabric.js** | No first-class React bindings. |

## R5 — Stack compatibility

shadcn/ui officially supports Tailwind v4 + React 19 — matches the project stack; no friction adding the SVG component or (Phase B) the Konva editor route.

## R6 — Phasing & migration shape

- **Phase A** is independently valuable and deployable: schema + `<CircuitDiagram>` + Jinja partial + additive `layout_json` column + idempotent backfill. ASCII retained as a11y/fallback source.
- **Single Alembic head** confirmed by `alembic heads` → `e1f2a3b4c5d6 (head)`; the new revision chains directly, **no merge migration**.
- **Phase B** persists nothing new: the combined session's circuit is derived at view time from the linked exercises' `layout_json` (O-3) → zero migrations.

## Resolved unknowns (from spec Open Questions, closed by coach/PM 2026-06-30)

1. **Document surface (O-1)** — Phase A embeds the diagram in the printable session sheet **only**.
2. **Line palette (O-2)** — one `line` kind + optional `style` (`dashed`=guía/libre, `solid`=técnico); no `line_free`/`line_technical`.
3. **Combined-session persistence (O-3)** — derived at view time; no new column; no Phase-B migration.
4. **Legacy columns (O-4)** — retain `layout_ascii`/`layout_alt` as the SR text source; removal deferred to a cleanup spec.
5. **Label policy (O-5)** — Phase A: controlled label set only (kind name + `#n`), no free text; free text deferred to the Phase B editor with anti-PII guards.
