# Contract — Reading profile and apply engine (amendment 2026-09-26 · FR-001 · FR-002 · FR-045)

A reading profile describes how one organiser's layout is read. The LLM writes it from the masked view only. A tested engine applies it to the real file locally, without the LLM. Research: R-18, R-19.

## Where profiles live

- Profiles live in `backend/race_reading_profiles/<profile_id>.json`. They are committed, reviewed in a pull request, and hold no rider data.
- The first profile is `copa-valle-results-pdf`. It must reproduce the retired parser's output on the synthetic builder files; that parity is the regression guard for 044's reading guarantees.
- A profile is identified by `profile_id` and, at stage, by the SHA-256 of its file (`race_import_staged_documents.profile_sha256`).

## Schema v1

```json
{
  "schema": 1,
  "profile_id": "copa-valle-results-pdf",
  "description": "Copa Valle XCO, resultados por válida, diseño 2024-2026",
  "format": "pdf",
  "pdf": {
    "rows": "table_bands",
    "run_gap_pt": 1.0,
    "columns": [
      {"field": "position",       "x_from": 45.0,  "x_to": 76.5},
      {"field": "bib",            "x_from": 76.5,  "x_to": 109.9},
      {"field": "name",           "x_from": 109.9, "x_to": 257.4},
      {"field": "city",           "x_from": 257.4, "x_to": 327.6},
      {"field": "club",           "x_from": 327.6, "x_to": 466.0},
      {"field": "time_or_status", "x_from": 466.0, "x_to": 539.0},
      {"field": "points",         "x_from": 539.0, "x_to": 600.0}
    ],
    "category_header": {"prefix": "CAT:"},
    "skip_structural_lines_starting_with": ["POS", "RESULTADOS"]
  },
  "category_aliases": {},
  "name_parts_separator": " "
}
```

For delimited text, `"format": "delimited"` replaces the `pdf` block with:

```json
"delimited": {
  "delimiter": ";",
  "header_rows": 1,
  "columns": {"position": 0, "bib": 1, "name": [2, 3], "city": 4, "club": 5, "time_or_status": 6, "points": 7},
  "category": {"column": 8}
}
```

Instead of a category column, `category` may be `{"separator_rows": {"first_cell_prefix": "CAT:"}}` when categories are printed as their own rows.

### Keys and rules

| Key | Type / allowed values | Meaning |
|---|---|---|
| `schema` | `1` | schema version |
| `profile_id` | `^[a-z0-9-]{3,64}$` | file name without `.json` |
| `description` | string ≤ 120 chars, no digits except a year range | human note for reviewers |
| `format` | `"pdf"` \| `"delimited"` | |
| `pdf.rows` | `"table_bands"` \| `"baselines"` | row source: table row bboxes (ruled layouts, R-01) or text baselines (unruled) |
| `pdf.run_gap_pt` | number 0.3–5.0 | gap that starts a new run (R-01: 1.0) |
| `pdf.columns[]` | `{field, x_from, x_to}` with `field` ∈ `position`, `bib`, `name`, `city`, `club`, `time_or_status`, `points` | a run belongs to the column whose `[x_from, x_to)` contains its **start x** |
| `pdf.category_header` | `{"prefix": str}` \| `{"pattern": regex}` \| `{"structural_x_to": number}` | how a category header line is recognised; patterns may only use vocabulary words, digits and regex syntax |
| `pdf.skip_structural_lines_starting_with` | list of vocabulary words | column-title and document lines to ignore |
| `delimited.delimiter` | one of `,` `;` `\t` | |
| `delimited.header_rows` | int 0–5 | rows skipped before data |
| `delimited.columns` | field → column index, or a list of indexes joined by `name_parts_separator` | `name` may span several columns (surname, given names) |
| `delimited.category` | `{"column": int}` \| `{"separator_rows": {"first_cell_prefix": str}}` | |
| `category_aliases` | map of printed header (upper case, vocabulary words only) → catalogue code | applied before `normalizer.HEADER_TO_CODE` |
| `name_parts_separator` | `" "` | |

- Required fields: `position`, `name`, `club`, `time_or_status`.
- Optional fields: `bib`, `city` and `points`. A missing `bib` or `city` is `""`; missing `points` is `0`. The identity signature is weaker without a city, which the operator report says in one line.
- **No other key is accepted.** `profile-check` and a test over every committed profile reject unknown keys, out-of-range numbers, and strings outside the rules above. This is how a profile is kept free of rider data.

## Engine

`app/services/race/results_skill/apply.py`:

```python
def apply_profile(file_bytes: bytes, results_ext: Literal["pdf", "csv"], profile: ReadingProfile) -> ParsedResults
```

### PDF

1. For each page, rows come from `find_tables` row bboxes (`table_bands`) or from baseline bands (`baselines`).
2. Inside a band, characters are read in **content-stream order**, never x-sorted. A run starts on a gap larger than `run_gap_pt` or on a backwards x jump (R-01).
3. Each run is assigned to the column that contains its start x. Several runs in the same column are joined with a space.
4. A header line matching `category_header` opens a new category. `header_raw` is the printed text without the prefix. The code comes from `category_aliases`, then from `normalizer.HEADER_TO_CODE` (exact match after normalisation, as today), and is `None` if neither matches (FR-002).
5. Column-title lines and `skip_structural_lines_starting_with` are skipped.
6. A band is kept as a row when it has a `position` or a `time_or_status`. `time_or_status` is kept raw (`time_raw`), because the platform's `normalizer.parse_time` reads it at ingest, including every T024b lap-deficit variant. A band with an ordinal but nothing readable is an `UnreadableRow(page, ordinal)`, never a silent drop (FR-001).
7. Rows before the first header belong to an unrecognised category named `SIN CATEGORÍA`, which the coach sees in the preview.

### Delimited text

Columns come from `columns`, and categories from the column or from separator rows. Blank rows are skipped. A row with neither a position nor a time or status is unreadable.

### Output

`ParsedResults` (categories in document order, `ResultsRow` with seven fields, `UnreadableRow`), serialised into `race_import_staged_documents.document_json` by `stage`.

## Validation performed by `apply` (printed as counts; nothing personal)

- Rows per category, and completeness per category (`completeness.check_category`: ok, or missing and duplicated ordinals).
- Statuses per category (finished, DNF/DNS/DSQ, lapped, classified without time).
- Unreadable rows as (page, ordinal).
- Unrecognised categories: shown by index, row count and their masked label.
- Zero rows overall: exit 5 (`La lectura no produjo filas; revisa el perfil.`).
- Leak check (`masked-view.md`).

## Tests

- `test_pdf_runs.py`: the band primitives on hand-built char dicts, ported from `test_band_reader.py`.
- `test_apply_profile.py`, where `copa-valle-results-pdf` on builder files reproduces the retired parser's output row by row:
  - the historical overprint layout, including a club printed over the time column;
  - the 2026 layout;
  - removed and duplicated ordinals;
  - an unknown header;
  - lap-deficit variants;
  - a row with a position and no time;
  - a category that continues across a page break.
- A fictional second layout (unruled, columns in a different order, surname and given names in separate columns) with its own profile: full recovery, proving the engine is not shaped around Copa Valle.
- Delimited text: category column, separator rows, multi-column names, `;` and tab delimiters.
- `test_profiles_valid.py`: every file in `backend/race_reading_profiles/` validates against schema v1, and no key or string falls outside the rules.
