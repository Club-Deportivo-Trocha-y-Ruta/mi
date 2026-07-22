# API Contract Delta: Interval Block Duration Usability (034)

**No new endpoints.** All changes are additive deltas to the feature-026 interval endpoints (structures CRUD, templates CRUD + attach, match read). Coach/admin-only gating unchanged (parents/athletes 403).

## Request schema delta — `BlockIn` (structures & templates create/update)

```jsonc
{
  "position": 1,
  "block_type": "warmup",              // warmup | work | recovery | cooldown (unchanged)
  "duration_type": "open_lap",         // NEW — "fixed" | "open_lap"; OPTIONAL, default "fixed"
  "duration_s": null,                  // CHANGED — int > 0 required iff duration_type == "fixed"; must be null/omitted iff "open_lap"
  "target_zone": "Z1",                 // unchanged, still required for open blocks
  "target_cadence_rpm": 70,            // unchanged (>= 60), still required for open blocks
  "repeat_group": null,                // unchanged; must be null when duration_type == "open_lap"
  "repeat_count": null
}
```

### Validation errors (422, existing error envelope)

| Condition | Message key (español neutro) |
|---|---|
| `open_lap` on `work`/`recovery` | "Solo el calentamiento y el enfriamiento pueden ser libres (hasta botón de vuelta)." |
| `open_lap` with `repeat_group` set | "Un bloque libre no puede pertenecer a un grupo repetido." |
| `open_lap` with `duration_s` present | "Un bloque libre no lleva duración." |
| `fixed` with `duration_s` null/≤ 0 | "La duración debe ser mayor que cero." (existing rule, now conditional) |

Backward compatibility: requests without `duration_type` behave exactly as before (`fixed`).

## Response schema delta — `BlockOut`

- `duration_type`: always present (`"fixed" | "open_lap"`).
- `duration_s`: `int | null` (null only for `open_lap`).

## Response semantics — `StructureOut.total_planned_duration_s`

- Documented as **fixed-blocks-only** sum (repeat-expanded). Open blocks contribute 0. No new fields; clients derive open-block presence from `blocks[]`.

## Match/comparison read endpoint

- Row status enum gains `"libre"` (informational: lap consumed, `lap_elapsed_s` present, no tolerance judgment; `planned_duration_s` null).
- `engine_version` field now emits `2` for new computations; previously stored `1` payloads are served verbatim.

## PDF instructivo endpoint

- Unchanged contract (same route, same brands `garmin | magene | igpsport`). Rendered content: open blocks show "Libre — hasta botón de vuelta" instead of "X min Y s".

## Template attach (copy-on-attach)

- Unchanged contract; copied blocks preserve `duration_type` and nullable `duration_s`.
