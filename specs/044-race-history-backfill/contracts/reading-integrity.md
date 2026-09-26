# Contract — Reading integrity (US1 · FR-001…FR-007)

> **Amended 2026-09-26.** The *Parser* section is superseded: the fixed PDF and CSV parsers are retired, and reading is done by the results-skill engine applying a reading profile (`reading-profile.md`, `masked-view.md`). Completeness, corrections, acknowledgement and partial commit still hold; their rows now come from the staged document (`staged-import.md`).

## Parser (`app/services/race/pdf_parser.py`)

```python
@dataclass
class ResultsRow:            # unchanged fields; time_raw == "" means "classified without time"
    ...

@dataclass
class UnreadableRow:
    page: int
    ordinal: Optional[int]   # from table cell 0 when numeric

@dataclass
class ParsedCategory:
    header_raw: str          # as printed, e.g. "PREJUVENIL A DAMAS"
    code: Optional[str]      # None => unrecognised header (rows are kept)
    rows: list[ResultsRow]

@dataclass
class ParsedResults:
    categories: list[ParsedCategory]      # document order
    unreadable_rows: list[UnreadableRow]

def parse_results_document(path: Path) -> ParsedResults: ...
def parse_results_pdf(path: Path) -> dict[str, list[ResultsRow]]:
    """Back-compat wrapper: recognised categories only, same shape as today."""
```

Reading algorithm: research R-01 (row band from rulings → chars in content-stream order → relaxed row regex → cells 2–4 for name/city/club). Helper `_band_text(chars, bbox) -> str` is pure and unit-tested on synthetic char dicts.

`parse_event_header`: numerals I–XII (R-02).

## Completeness (`app/services/race/completeness.py`)

```python
def check_completeness(ordinals: Sequence[int]) -> CompletenessReport
def apply_corrections(parsed: ParsedResults, corrections: list[dict]) -> ParsedResults
```

`status == "inconsistent"` iff the multiset of ordinals ≠ `{1…N}`.

## API deltas (`/api/race-imports`)

| Endpoint | Change |
|---|---|
| `POST /parse` | response gains `categories[]` (`header_raw`, `code`, `mapping_kind`, `rows`, `completeness`) and `unreadable_rows[]`; existing fields unchanged |
| `POST /{id}/corrections` *(new)* | body `{op: add\|edit\|remove, category_header, ordinal, row?}` → re-runs the check, returns the category's new `completeness`. 422 on an unknown category or malformed row |
| `POST /{id}/acknowledge` *(new)* | body `{category_header, reason: AcknowledgeReasonCode}` → `completeness.status = "acknowledged"`; `record_audit` |
| `GET /acknowledge-reasons` *(new)* | closed catalogue for the dropdown |
| `POST /{id}/commit` | ingests categories that are `ok` or `acknowledged` and recognised; response gains `pending_categories[]`; `409 identity_review_pending` (see identity contract) |
| `POST /{id}/commit-pending` *(new)* | same rules, restricted to categories still pending; 409 `nothing_pending` when none |

All new routes: `require_role([admin, coach])`, club scoping as the existing import routes; denied-path tests for parent (403), athlete (403) and a coach of another club (403/404 as today).

Logging: codes, counts, page numbers and ordinals only.

## Tests

- `test_band_reader.py`: overlap, flush club/time, position-without-time, status tokens, club ending in a digit, empty city/club.
- `test_parser_historical_layout.py` on builder PDFs: every row recovered; unknown header kept with rows; header numeral VIII.
- Existing `test_parser.py` / `test_parser_edge_cases.py` unchanged and green (FR-007).
- `test_completeness.py`: gap, duplicate, both, empty, acknowledged.
- Router: corrections lift the block; acknowledgement audited; partial commit leaves the inconsistent category pending and `commit-pending` finishes it; re-commit creates nothing.
