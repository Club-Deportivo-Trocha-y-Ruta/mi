# Data Model — National Championship Support (Series Level)

**Feature**: 023-national-championship-level | **Date**: 2026-07-08

## Entity delta

Single entity changes. No new tables, no relationship changes, no changes to `race_events` or `race_results`.

### RaceSeries (modified)

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `level` **(NEW)** | Enum `raceserieslevel` (`departmental` \| `national`) | NOT NULL, `server_default='departmental'` | Stored by *value* via `values_callable` (same pattern as `kind`). Meaningful for `kind=championship`; cups always hold `departmental` and never expose it in UI. |

Python enum:

```python
class RaceSeriesLevel(str, enum.Enum):
    """Ámbito territorial de un campeonato.

    departmental — Campeonato Departamental (ej. Valle del Cauca).
    national     — Campeonato Nacional (ej. Fedeciclismo, Pereira 2026).
    """
    departmental = "departmental"
    national = "national"
```

### Unchanged entities (verified generalization)

| Entity | Why unchanged |
|---|---|
| `RaceEvent` | City lives in existing `location`; championship events already get `sequence_number=1`, `is_championship=True` via `derive_event_fields_for_series`. |
| `RaceResult` | Ingestion links by `event_id`; nothing level-dependent. |
| `RacePointsScheme` | Championships never read the scheme (standings exclude by `kind`). `points_scheme_code` remains `copa_valle_2026` — documented cosmetic debt (research R5). |

## Validation rules

- `level` accepted on series creation only; defaults to `departmental` when omitted (backward-compatible API).
- Invalid level value → 422 (Pydantic enum validation).
- No level mutation endpoint in scope (series edit not part of spec; existing series have correct levels by construction).
- INV-2 (single event per championship) applies identically regardless of level — enforced by existing `assert_championship_single_event`, keyed on `kind`.
- Coexistence: departmental + national championships in the same `season_year` are distinct rows — `UNIQUE(name, season_year)` already permits this (different names). FR-011 needs no new constraint.

## State transitions

None. `level` is immutable post-creation in this feature's scope.

## Migration contract

**File**: `backend/alembic/versions/d3e4f5a6b7c8_add_race_series_level.py`

| Property | Value |
|---|---|
| `revision` | `d3e4f5a6b7c8` |
| `down_revision` | `a7b8c9d0e1f2` (current head — feature 021 strength library) |
| Upgrade | `ALTER TABLE race_series ADD COLUMN level ENUM('departmental','national') NOT NULL DEFAULT 'departmental'` (via `sa.Enum(..., name="raceserieslevel")`, `server_default="departmental"`) |
| Downgrade | Drop column (and enum type where applicable) |
| Backfill | None needed — server default covers all existing rows (Copa Valle cups + "Campeonato Departamental 2026" → `departmental`). |
| Data risk | Zero: additive, no rewrites, no lock-heavy operation on a small table. |

**Test-engine note**: backend tests use `Base.metadata.create_all` on aiosqlite — the new column is picked up automatically; SQLite renders the enum as VARCHAR + CHECK, consistent with how `kind` already behaves in tests.

## Label derivation (not stored)

Labels are derived, never persisted:

| kind | level | Chart/short label | Notification label |
|---|---|---|---|
| cup | (any) | `Válida {romano} — {ciudad}` | `{romano} — {ciudad}` |
| championship | departmental | `Cto. Dep. — {ciudad}` | `Campeonato Departamental` |
| championship | national | `Cto. Nal. — {ciudad}` | `Campeonato Nacional` |

Pre-023 persisted snapshots (monthly reports, insights) keep their stored text untouched (SC-005).
