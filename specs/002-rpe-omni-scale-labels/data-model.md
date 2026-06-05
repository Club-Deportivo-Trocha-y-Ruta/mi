# Phase 1 Data Model: RPE OMNI Scale Labels

This feature introduces **no new persisted entity and no schema change**. The "data model" here is the in-memory presentation mapping between the stored RPE value and its display.

## Stored value (UNCHANGED — for reference only)

- **Entity**: `SessionAttendance.rpe_omni`
- **Type**: nullable integer
- **Constraint**: `rpe_omni BETWEEN 0 AND 10 OR rpe_omni IS NULL`
  - Backend: `backend/app/models/training_session.py` (CHECK) and `backend/app/schemas/training_session.py` (`Field(ge=0, le=10)`)
- **This feature does not alter the type, range, nullability, or any read/write path.** No Alembic migration.

## Presentation mapping (the only thing that changes)

A pure, total function `value → { label, face }` over the domain `0..10`, implemented as two index-aligned constant arrays in `frontend/src/components/training/RubricSliders.tsx`.

### `RPE_LABELS` (index = RPE value)

| Index | Label |
|------:|-------|
| 0 | Reposo |
| 1 | Muy fácil |
| 2 | Fácil |
| 3 | Ligero |
| 4 | Algo fácil |
| 5 | Moderado |
| 6 | Algo duro |
| 7 | Duro |
| 8 | Muy duro |
| 9 | Muy muy duro |
| 10 | Máximo |

### `RPE_FACES` (index = RPE value)

Eleven entries, rest→max progression, aligned with the labels above. Verify the index-5 face reads as neutral/"moderate" (not "tired"); adjust the single midpoint glyph if it skews negative. Otherwise the existing ramp is retained.

## Invariants (to be enforced by tests)

- **INV-1 (totality)**: `RPE_LABELS.length === 11` and `RPE_FACES.length === 11`; every value 0–10 yields exactly one non-empty label (spec FR-002).
- **INV-2 (monotonic intensity)**: descriptor intensity is non-decreasing from index 0 to 10 (spec FR-003). Operationalized in tests by asserting the known ordered checkpoints rather than parsing semantics: index 0 = "Reposo", index 5 = "Moderado", index 10 = "Máximo".
- **INV-3 (moderate centered)**: the "moderate" descriptor is at index 5 (within the 5–7 mid-band), NOT at index 3 (spec FR-004, SC-002). Regression assertion: `RPE_LABELS[3] !== "Moderado"` and `RPE_LABELS[5] === "Moderado"`.
- **INV-4 (value preserved)**: rendering label for a value does not change the value emitted by the control; selecting value N still calls `field.onChange(N)` (spec FR-006/FR-007).
- **INV-5 (language)**: labels are español neutro with diacritics (Constitution III) — e.g. "Muy fácil" carries the accent.

## State transitions

None. This is stateless display logic over an existing value.
