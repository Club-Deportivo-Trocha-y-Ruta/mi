# UI Contract: RPE OMNI Label Mapping

**Surface**: Coach attendance/rubric panel — `RubricSliders` RPE OMNI control.
**Type**: UI display contract (no network contract; no API change).

## Contract

Given the integer RPE value `v ∈ {0,1,…,10}` held by React Hook Form field `rpe_omni`, the control MUST render:

1. The numeric value `v`.
2. The descriptor `RPE_LABELS[v]` next to it, formatted `"{v} — {label}"`.
3. The emoji `RPE_FACES[v]` emphasized (full opacity) while the rest are dimmed.

### Required mapping

| v | label | v | label |
|--:|-------|--:|-------|
| 0 | Reposo | 6 | Algo duro |
| 1 | Muy fácil | 7 | Duro |
| 2 | Fácil | 8 | Muy duro |
| 3 | Ligero | 9 | Muy muy duro |
| 4 | Algo fácil | 10 | Máximo |
| 5 | Moderado |  |  |

## Guarantees (must hold)

- **G1**: `RPE_LABELS[5] === "Moderado"` (moderate at mid-scale).
- **G2**: `RPE_LABELS[3] !== "Moderado"` (regression: the reported defect is gone).
- **G3**: `RPE_LABELS[0] === "Reposo"` and `RPE_LABELS[10] === "Máximo"` (unambiguous endpoints).
- **G4**: `RPE_LABELS.length === 11` and `RPE_FACES.length === 11`.
- **G5**: The slider still exposes `min=0`, `max=10`, `aria-valuenow=v`, `aria-valuemin=0`, `aria-valuemax=10`, and emits `v` unchanged on change (no behavioral regression).
- **G6**: All labels are valid español neutro (Colombia) with correct diacritics.

## Out of scope (explicitly unchanged)

- Parent read-only view (`ReadOnlyAttendanceRow`) renders `"{v}/10"` with no descriptor — NOT modified.
- Backend `rpe_omni` value, range, and storage — NOT modified.
- The 1–5 rubric sliders (Esfuerzo/Actitud/Técnica) and their `RUBRIC_LABELS` — NOT modified.
