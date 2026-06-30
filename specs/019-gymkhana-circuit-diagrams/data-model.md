# Phase 1 Data Model: Gymkhana Circuit Diagrams

This feature **extends** feature 018's data model with a single additive column and one new (non-DB) JSON document schema mirrored across Pydantic (server) and Zod (client). No table is created; no table is dropped. Reused unchanged: `technique_exercises`, `technique_session_exercises`, `training_sessions`.

## New document schema — `GymkhanaLayout` (the keystone)

Not a table — a JSON document persisted in `technique_exercises.layout_json` (Phase A) and mirrored Pydantic ⇄ Zod. It is the single source of truth for the React SVG renderer, the Jinja SVG partial, and (Phase B) the Konva editor.

```text
GymkhanaLayout {
  width:    number              # canvas units, > 0
  height:   number              # canvas units, > 0
  elements: CircuitElement[]    # may be empty (valid)
}

CircuitElement {
  kind:      'cone' | 'line' | 'gate' | 'mine' | 'arrow' | 'beam' | 'ring'
  x:         number             # 0 ≤ x ≤ width
  y:         number             # 0 ≤ y ≤ height
  rotation?: number             # degrees, default 0
  style?:    'dashed' | 'solid' # line only: dashed=guía/libre, solid=técnico (O-2)
  label?:    string             # Phase B only; Phase A omits (controlled set, O-5)
}
```

### Element vocabulary → Spanish legend (resolved at render time, not stored)

| `kind` | Legend (español neutro) | Notes |
|---|---|---|
| `cone` | Cono | club's primary marker |
| `line` (`style:dashed`) | Trayecto guía / libre | dashed path |
| `line` (`style:solid`) | Trayecto técnico | solid path (precision) |
| `gate` | Puerta | pass-through gate |
| `mine` | Mina | obstacle to avoid |
| `beam` | Equilibrio (viga) | balance beam |
| `ring` | Círculo de la muerte | tight ring |
| `arrow` | Dirección de recorrido | bike movement direction |

## Column change — `technique_exercises.layout_json`

| Column | Type | Notes |
|---|---|---|
| `layout_json` | `JSON` **NULL** (new) | a `GymkhanaLayout`; null for non-gymkhana or not-yet-backfilled rows. **Additive, nullable, no default.** |
| `layout_ascii` | `Text` NULL (existing) | **retained** (O-4) — transition fallback. |
| `layout_alt` | `Text` NULL (existing) | **retained** (O-4) — screen-reader text-alternative source for both ASCII and SVG renderers. |

All other `technique_exercises` columns unchanged. MySQL 8.4 native `JSON`; SQLite test path stores JSON-text (round-trips fine).

## Alembic revision

- **Revision**: `f1a2b3c4d5e6_add_layout_json_to_technique_exercises.py`, `down_revision = 'e1f2a3b4c5d6'` (single head — see plan Migration Decision). *(Use the next free hex id if this one collides; the constraint is `down_revision='e1f2a3b4c5d6'` + single resulting head.)*
- **upgrade()**: `op.add_column('technique_exercises', sa.Column('layout_json', sa.JSON(), nullable=True))`, then the idempotent backfill.
- **downgrade()**: `op.drop_column('technique_exercises', 'layout_json')`.

## Backfill (idempotent data step)

- A backfill map `slug → GymkhanaLayout` lives in `backend/app/data/technique_catalog.py`, transcribed from each seeded gymkhana's existing `layout_ascii` croquis (`LAYOUT_41`, `LAYOUT_42`, `LAYOUT_43`, …) and `docs/14-tecnica-gymkana-7-15/research.md §4`.
- The migration `UPDATE`s each row matched by stable `slug`, setting `layout_json` **only where it IS NULL**; `layout_ascii`/`layout_alt` untouched.
- Re-runnable; safe on partially-seeded or championship-free DBs.
- Fidelity bar (per spec Assumption): preserve the **meaning** (element placement/sequence) of each croquis, not pixel-perfect ASCII reproduction. Reviewed by `technique-coach`.

## Phase B — no persistence change (O-3)

The combined gymkhana session's circuit is **derived at view time** by composing the `layout_json`s of the exercises linked via `technique_session_exercises`. `training_sessions` gains **no** column; no new table. Phase B adds **zero** migrations and reuses 018's `assembler.py` + `TechniqueSessionExercise` link unchanged.

## Validation & invariant rules

1. **Schema validity (FR-007)** — both Zod and Pydantic: `width>0`, `height>0`; each element has a known `kind`; `0 ≤ x ≤ width`, `0 ≤ y ≤ height`; `rotation`/coords finite; `style` only meaningful on `line`; **empty `elements` is valid**. Reject (422 server / form error client) otherwise — never half-render.
2. **Gymkhana ⇒ layout source (extends 018 FR-008)** — a gymkhana exercise SHOULD have either `layout_json` or `layout_ascii`; renderers prefer `layout_json`, fall back to `layout_ascii` (FR-010).
3. **No free-text label in Phase A (FR-023/O-5)** — server rejects (or strips) `label` free text on Phase A writes; only the controlled set (kind name + `#n`) is allowed. Phase B relaxes this with anti-PII guards.
4. **No minor PII (FR-019)** — `layout_json` is geometry; no athlete name/DOB/medical may be stored; enforced by the no-free-text rule (A) and privacy tests (B).
5. **Renderer equivalence (FR-006)** — the React SVG and the Jinja SVG MUST be structurally equivalent for the same `GymkhanaLayout` (locked by a cross-renderer test).
