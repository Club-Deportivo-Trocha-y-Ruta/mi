# Writing a reading profile from the masked view

Full schema: `specs/044-race-history-backfill/contracts/reading-profile.md`. This page walks one concrete profile from a masked view to a working `apply` run — the same method you follow on a real file, except here the file is a synthetic one from `tests/helpers/results_pdf_builder.py` (fake names only, `FakeNameGenerator`), so this whole document is safe to read, keep, and hand to `data-privacy-guard`.

## Where profiles live

`backend/race_reading_profiles/<profile_id>.json`, committed and reviewed in a pull request, never holding rider data. The first, real profile is `copa-valle-results-pdf`. Reuse it (via `profile-check` + `apply`) before ever writing a new one — most Copa Valle files match it.

## The worked example

This is the exact `masked/view.txt` produced by `build_masked_view` on a two-page-worthy but one-page synthetic PDF (layout `"2026"`, category `PREJUVENIL A`, 4 rows, `FakeNameGenerator`):

```text
# masked-view v1 · format=pdf · sha256=b41eed8f
## page 1 · width=612.0 · rulings_x=[40.4, 542.9]
L001 C | @0.0 ⟨W⟩ ⟨W⟩ ⟨W⟩ ⟨W⟩ ⟨W⟩ ⟨W⟩ ⟨N2⟩ ⟨W⟩ ⟨N4⟩
L002 S | @0.0 ⟨W⟩ : ⟨W⟩ ⟨W⟩
L003 y=70.3 C | @43.0 ⟨W⟩ | @65.5 ⟨W⟩ ° | @95.5 ⟨W⟩ ⟨W⟩ | @268.0 ⟨W⟩ | @365.5 ⟨W⟩ / ⟨W⟩ | @440.5 ⟨W⟩ | @508.0 ⟨W⟩
L004 y=84.0 C | @43.0 ⟨N1⟩ | @65.5 ⟨N3⟩ | @95.5 ⟨W⟩ ⟨W⟩ ⟨W⟩ | @268.0 ⟨W⟩ ⟨W⟩ | @365.5 ⟨W⟩ ⟨W⟩ | @440.5 ⟨T h:mm:ss⟩ | @508.0 ⟨N2⟩
L005 y=97.6 C | @43.0 ⟨N1⟩ | @65.5 ⟨N3⟩ | @95.5 ⟨W⟩ ⟨W⟩ ⟨W⟩ | @268.0 ⟨W⟩ ⟨W⟩ | @365.5 ⟨W⟩ ⟨W⟩ | @440.5 ⟨T h:mm:ss⟩ | @508.0 ⟨N2⟩
L006 y=111.3 C | @43.0 ⟨N1⟩ | @65.5 ⟨N3⟩ | @95.5 ⟨W⟩ ⟨W⟩ ⟨W⟩ | @268.0 ⟨W⟩ ⟨W⟩ | @365.5 ⟨W⟩ ⟨W⟩ | @440.5 ⟨T h:mm:ss⟩ | @508.0 ⟨N2⟩
L007 y=124.9 C | @43.0 ⟨N1⟩ | @65.5 ⟨N3⟩ | @95.5 ⟨W⟩ ⟨W⟩ ⟨W⟩ | @268.0 ⟨W⟩ ⟨W⟩ ⟨W⟩ | @365.5 ⟨W⟩ ⟨W⟩ | @440.5 ⟨T h:mm:ss⟩ | @508.0 ⟨N2⟩
```

### Reading it (geometry only — see `masked-view.md` for what you must not infer)

- `L001` (content): the document title line. Ignore it for column geometry.
- `L002` (structural): a `⟨W⟩ : ⟨W⟩ ⟨W⟩` shape right before the data rows — that is the `CAT:` header. Its position tells you where a category starts; you never learn which category from the view (`references/masked-view.md`).
- `L003` (content, because one run has an unrecognised word): the column-title row. Its **run positions** (`@43.0`, `@65.5`, `@95.5`, `@268.0`, `@365.5`, `@440.5`, `@508.0`) are the same x-anchors the data rows below use — that consistency is exactly what tells you these are column starts, not the row's actual text.
- `L004`–`L007` (content, data rows): four rows, each with 7 runs at the same 7 x-positions as `L003`. Run shapes by column, read purely by token count and class (never content):
  - `@43.0`: one `⟨N1⟩`/`⟨N…⟩` run → **position**.
  - `@65.5`: one `⟨N3⟩` run → **bib**.
  - `@95.5`: two-to-three `⟨W⟩` tokens → **name**.
  - `@268.0`: one-to-two `⟨W⟩` tokens → **city**.
  - `@365.5`: one-to-two `⟨W⟩` tokens → **club**.
  - `@440.5`: a `⟨T h:mm:ss⟩` run → **time_or_status**.
  - `@508.0`: one `⟨N2⟩` run → **points**.

### Deriving `columns[].x_from`/`x_to`

Take the midpoint between one column's start x and the next one's start x as the boundary, with a small margin so a slightly earlier or later run still lands in the right column (the same approach `copa-valle-results-pdf.json` uses, and the reason its own boundaries do not sit exactly on the measured runs):

| field | measured `@x` | chosen `x_from` | chosen `x_to` |
|---|---|---|---|
| position | 43.0 | 0.0 | 55.0 |
| bib | 65.5 | 55.0 | 90.0 |
| name | 95.5 | 90.0 | 260.0 |
| city | 268.0 | 260.0 | 360.0 |
| club | 365.5 | 360.0 | 435.0 |
| time_or_status | 440.5 | 435.0 | 500.0 |
| points | 508.0 | 500.0 | 620.0 (page width) |

### The resulting profile

```json
{
  "schema": 1,
  "profile_id": "skill-worked-example",
  "description": "Perfil de ejemplo para la documentacion del skill",
  "format": "pdf",
  "pdf": {
    "rows": "table_bands",
    "run_gap_pt": 1.0,
    "columns": [
      {"field": "position",       "x_from": 0.0,   "x_to": 55.0},
      {"field": "bib",            "x_from": 55.0,  "x_to": 90.0},
      {"field": "name",           "x_from": 90.0,  "x_to": 260.0},
      {"field": "city",           "x_from": 260.0, "x_to": 360.0},
      {"field": "club",           "x_from": 360.0, "x_to": 435.0},
      {"field": "time_or_status", "x_from": 435.0, "x_to": 500.0},
      {"field": "points",         "x_from": 500.0, "x_to": 620.0}
    ],
    "category_header": {"prefix": "CAT:"},
    "skip_structural_lines_starting_with": ["ORD", "RESULTADOS"]
  },
  "category_aliases": {},
  "name_parts_separator": " "
}
```

Note `description` follows the schema rule (`≤120 chars, no digits except a year range`) — it has none here, which is always safe.

### `apply` against that same file, with that profile

Running `apply_profile` on the source bytes with the profile above (this is real engine output, only the row *content* is never shown — exactly what `apply`'s own stdout gives you):

```text
category #1: code=PJUV_A rows=4
unreadable rows: 0
leak_count: 0
```

Four rows recovered, the header resolved automatically to `PJUV_A` through `normalizer.HEADER_TO_CODE` (no alias needed — `PREJUVENIL A` is a standard header), zero unreadable rows, zero leaked words. This is the "apply until clean" state rule 4 asks for; if `apply` had reported an unrecognised category or unreadable rows instead, you would adjust `columns`/`category_header`/`skip_structural_lines_starting_with` and re-run, never guess at the row content.

## Keys and rules, short form

(Full table in the contract — this is what you touch most often.)

- Required fields per row: `position`, `name`, `club`, `time_or_status`. Optional: `bib`, `city`, `points`.
- `category_aliases`: printed header (upper case, **vocabulary words only** — see `masked-view.md` on why you can only ever populate this from what the operator reads on the printed file, never from the masked view) → catalogue code.
- `pdf.category_header`: `{"prefix": str}` is the common case (Copa Valle prints `CAT: <NOMBRE>`). Use `{"pattern": regex}` (vocabulary words, digits and regex syntax only) or `{"structural_x_to": number}` for a different organiser's layout.
- `pdf.skip_structural_lines_starting_with`: column-title and document lines to ignore — vocabulary words only.
- For delimited text, replace the `pdf` block with `delimited` (`delimiter`, `header_rows`, `columns`, `category`) — see `references/manifest.md`'s sibling contract section for the shape, or `contracts/reading-profile.md` directly.
- **No other key is accepted.** `profile-check` enforces this; if it fails, read the violation list it prints (key paths and rule names) and fix the profile, never work around the check.

## When you must ask the operator

Only when `apply` reports an unrecognised category (by index and row count, never text) or an unrecognised column. Ask exactly what is needed: "category #<k>, <n> rows, wasn't recognised — what does the printed header say?" They read the real, printed file and answer. If their answer is a category or column word (never part of a person's name — they confirm that too), it becomes a `category_aliases` entry, or, if the vocabulary itself is missing a legitimate column/category word, a pull request to `app/services/race/results_skill/vocabulary.py` that `data-privacy-guard` reviews. You never add a word to the vocabulary yourself in the same session without that review.
