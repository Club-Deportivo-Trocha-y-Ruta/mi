# Data Model: Interval Block Duration Usability (034)

Delta over feature 026 (`backend/app/models/interval_structure.py`). No new tables.

## New enum

```
IntervalDurationType (values_callable, project convention)
  fixed     — block has an exact planned duration in whole seconds (current behavior)
  open_lap  — block has no planned duration; athlete ends it with the device lap button
```

## Altered: `interval_structure_blocks`

| Column | Change | Notes |
|---|---|---|
| `duration_type` | **NEW** — enum `fixed`/`open_lap`, NOT NULL, `server_default='fixed'` | Existing rows become `fixed` with no data rewrite |
| `duration_s` | Integer NOT NULL → **Integer NULL** | Meaning unchanged for `fixed` rows |

**Invariants (service-layer + Pydantic, matching 026's enforcement style — no DB CHECK):**

- `duration_type = 'fixed'` ⇒ `duration_s` IS NOT NULL AND `duration_s > 0`
- `duration_type = 'open_lap'` ⇒ `duration_s` IS NULL
- `duration_type = 'open_lap'` ⇒ `block_type` ∈ {`warmup`, `cooldown`}
- `duration_type = 'open_lap'` ⇒ `repeat_group` IS NULL (never inside a repeat group)
- Unchanged: `target_zone` and `target_cadence_rpm` (≥ 60) required for every block regardless of duration type; age-gate (Z3+ for band 10–12) applies regardless of duration type; position uniqueness; repeat-group rules (both-or-neither, count ≥ 2, uniform, contiguous).

## Altered: `interval_template_blocks`

Identical delta (`duration_type` NEW, `duration_s` nullable) with identical invariants. Copy-on-attach copies `duration_type` verbatim.

## Migration

- **ID**: `c7d8e9f0a1b2_interval_block_duration_type` · **down_revision**: `b5c6d7e8f9a0` (current head)
- Upgrade: add `duration_type` (server_default `'fixed'`) to both tables; alter `duration_s` to nullable in both tables.
- Downgrade: delete rows with `duration_type='open_lap'`? **No** — downgrade sets `duration_s` back to NOT NULL, which fails on open rows; standard project practice: downgrade first deletes `open_lap` rows (destructive, documented in migration docstring), then restores NOT NULL and drops the column.

## Derived / computed values

| Value | Rule |
|---|---|
| `StructureOut.total_planned_duration_s` | Sum over **fixed** blocks only, with repeat expansion (`duration_s × repeat_count`); open blocks contribute 0 |
| Total label (frontend) | `formatMmSs(total)` + suffix when open blocks exist: "+ calentamiento libre" (open warmup only), "+ enfriamiento libre" (open cooldown only), "+ bloques libres" (both); no fixed blocks → "Duración libre" |
| Flattened plan step | `{position_label, block_type, duration_type, planned_duration_s: int \| None, target_zone, target_cadence_rpm}` — open steps appear once (never repeated, by invariant) |

## Plan-vs-actual comparison (stored JSON rows)

New row status vocabulary (engine v2):

| Status | When | Judged? |
|---|---|---|
| `cumplido` | fixed step, lap within ±30% | yes |
| `fuera_tolerancia` | fixed step, lap outside ±30% | yes |
| **`libre`** | **open step, qualifying lap consumed — actual elapsed shown** | **no (informational)** |
| `sin_dato` | any step without a qualifying lap | no |
| `extra` | surplus laps beyond plan | no |

- `ENGINE_VERSION`: 1 → **2**. Stored comparisons keep their recorded version; v1 rows render unchanged, never recomputed retroactively.
- Open step never enters `_is_within_tolerance` (no division by `planned_duration_s = None`).

## State transitions (editor)

- fixed → open_lap: duration value discarded (UI warns via inline message; Zod clears field); allowed only when block_type ∈ {warmup, cooldown} AND not in repeat group.
- open_lap → fixed: duration required again (entry via MmSsInput).
- Joining a repeat group while open_lap (either action order): blocked in UI **and** rejected by server validation (order-independent, spec edge case).
