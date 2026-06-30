# Phase 1 Contracts: REST API delta (vs feature 018)

This feature adds **no new endpoint in Phase A**. The `GymkhanaLayout` travels on the **existing** exercise read/write endpoints from feature 018 (`backend/app/routers/technique.py`). Phase B reuses the existing assemble-session contract. Below is the delta only; everything else in `specs/018-technique-gymkhana-library/contracts/rest-api.md` is unchanged.

All endpoints inherit feature 018 RBAC: **coach/admin only**, club-scoped. español neutro error copy.

## Exercise detail — read (extended)

`GET /api/technique/exercises/{exercise_id}` *(existing — `ExerciseDetail`)*

- **Adds** field `layout_json: GymkhanaLayout | null` to the response body (beside the existing `layout_ascii` / `layout_alt`).
- `null` when the exercise is non-gymkhana or not yet backfilled. Clients prefer `layout_json`; fall back to `layout_ascii` (FR-010).
- `ExerciseListItem` (catalog list) is **not** extended — layouts are detail-only to keep list reads lean.

```jsonc
// 200 OK (excerpt)
{
  "id": 42,
  "slug": "limbo-en-bici",
  "is_gymkhana": true,
  "layout_ascii": "…",          // retained (a11y/fallback)
  "layout_alt": "Coloca tres conos…",
  "layout_json": {
    "width": 100, "height": 60,
    "elements": [
      { "kind": "cone", "x": 20, "y": 30 },
      { "kind": "cone", "x": 50, "y": 30 },
      { "kind": "line", "x": 10, "y": 30, "style": "dashed" },
      { "kind": "arrow", "x": 5, "y": 30, "rotation": 0 }
    ]
  }
}
```

## Exercise curation — create / update (extended)

`POST /api/technique/exercises` *(existing — `ExerciseCreate`)*
`PUT  /api/technique/exercises/{exercise_id}` *(existing — `ExerciseUpdate`)*

- **Accept** optional `layout_json: GymkhanaLayout | null`.
- **Validation (422)**: malformed `GymkhanaLayout` — unknown `kind`, out-of-bounds/non-finite coords, `width`/`height` ≤ 0. Empty `elements` is accepted.
- **Phase A guard (FR-023/O-5)**: free-text `label` on elements is rejected/stripped; only the controlled set (kind name + `#n`) is allowed. Phase B relaxes with anti-PII guards.
- No minor PII may be stored in `layout_json` (FR-019).

## Server-side document rendering (not a REST endpoint)

The printable session sheet template embeds the new Jinja partial `backend/templates/documents/pdf/charts/circuit_diagram.svg.jinja`, which renders a `GymkhanaLayout` as inline SVG (`role="img"` + `aria-label` from `layout_alt`), mirroring `line_positions.svg.jinja`. No external image fetch (FR-005). Monthly technical report and newsletter are **not** targets in Phase A (O-1).

## Phase B — assemble combined session (reuses existing contract)

`POST /api/technique/sessions/assemble` *(existing 018 — `AssembleSessionRequest` → `AssembleSessionResponse`)*

- **Reused unchanged.** The composer selects exercises (arranged into `calentamiento`/`principal`/`vuelta_calma`) and assembles them into a real `TrainingSession` via the existing `technique_session_exercises` link and `services/technique/assembler.py` — no parallel store (FR-014).
- The combined circuit is **derived at view time** from the linked exercises' `layout_json` (O-3); **nothing new is persisted** and **no new request body field** is added. Editing the layout again updates the same session (FR-015) — via the existing per-exercise `layout_json` update path, not a session-level layout.

## Summary table

| Endpoint | Phase | Change |
|---|---|---|
| `GET /technique/exercises/{id}` | A | +`layout_json` in `ExerciseDetail` |
| `POST /technique/exercises` | A | accept optional `layout_json` (validated, no free-text label) |
| `PUT /technique/exercises/{id}` | A | accept optional `layout_json` (validated, no free-text label) |
| Printable session sheet (Jinja) | A | embeds `circuit_diagram.svg.jinja` |
| `POST /technique/sessions/assemble` | B | reused unchanged; circuit derived at view time |
