# Contract — Category mapping and frozen labels (US2 · FR-008…FR-011)

## Aliases added to `normalizer.HEADER_TO_CODE` (normalised header → code)

| Header (normalised) | Code | `mapping_kind` |
|---|---|---|
| `elite hombres` | `ELITE_M` | rename |
| `elite damas` | `ELITE_F` | rename |
| `junior damas` | `JUN_F` | rename |
| `master damas` | `MAS_F` | rename |
| `infantil a ninas` / `infantil b ninas` | `INF_A_F` / `INF_B_F` | rename |
| `prejuvenil a damas` / `prejuvenil b damas` | `PJUV_A_F` / `PJUV_B_F` | rename |
| `master b` / `master c` | `MAS_B_2025` / `MAS_C_2025` | season_specific |
| `preinfantil ninas` / `preinfantil femenino` | `PRE_F_U` | season_specific |

`mapping_kind` is derived, not stored: `exact` when the header is one of the 26 original keys, `rename` for the aliases above that resolve to an active category, `season_specific` when the resolved category has `is_active = false`, `unknown` when unresolved. A second dict `HEADER_ALIASES: frozenset[str]` marks which keys are aliases.

## Catalogue rows (`scripts/seed_race_categories.py`)

| code | label | sex | tier | is_active |
|---|---|---|---|---|
| `MAS_B_2025` | Máster B (2025) | M | master | false |
| `MAS_C_2025` | Máster C (2025) | M | master | false |
| `PRE_F_U` | Preinfantil femenino (grupo único) | F | menores | false |

## Ingestor

On insert: `category_label_raw = parsed_category.header_raw`, `category_age_min_raw/max_raw = category.age_min/age_max`. Never updated afterwards.

## Read paths

Schemas that show the category of a stored result gain `category_label: str` resolved as `category_label_raw or category.label`. Current-season selectors filter `is_active = true` (one test per selector: import wizard, course setups, results filters, standings filters).

## Tests

Alias resolution (each row of the table, with and without diacritics and hyphen); `mapping_kind` derivation; frozen columns survive a catalogue edit and a revision import; migration backfill fills pre-existing rows; season-specific codes absent from every current selector; `-m mysql` round-trip for the three columns.
