# Contract — Historical load (US5 · FR-023…FR-029)

> **Amended 2026-09-26.** The sections *Staging service* and *Script* are superseded. Results are no longer staged from an uploaded file or by `stage_race_history.py`: the results skill stages them (`staged-import.md`, `results-skill-cli.md`). The row *Same válida, different file* now follows `revision-via-skill.md`. Full start list, points and standings, idempotence by SHA-256, board fields, `matches_unresolved`, the current season untouched, and ordering still hold.

One path, no parallel rules: the fifteen historical válidas go through the same preview → dry-run → commit flow, duplicate protection and audit trail as a current-season import (FR-023).

## Staging service

`app/services/race/import_staging.py`

```python
async def stage_results_file(
    db, *, file_bytes: bytes, original_filename: str,
    series_name: str, season: int, valida_num: int, event_name: str,
    event_date: date, location: str,
    series_kind: RaceSeriesKind = cup, series_level: RaceSeriesLevel = departmental,
    conditions: ImportParseRequestFields | None = None,
    actor: User, ctx: AuditContext,
) -> ImportParseResponse
```

The body of today's `POST /race-imports/parse` moves here unchanged; the router becomes a thin caller. `general_pdf` is never passed for historical seasons: **only the per-válida results file is staged** (`kind = resultados`), and the organiser's cumulative standings files are not accepted by the script (FR-024).

Season, válida number, date and venue are **explicit inputs** — form fields in the UI, manifest fields in the script. `parse_event_header` only pre-fills the form; when it returns `None` or disagrees with the inputs the response carries a `header_mismatch` warning and the inputs win. Nothing is inferred silently (FR-025).

## Script

`backend/scripts/stage_race_history.py --manifest <path outside the repo> [--dry]`

Manifest entry: `{season, valida_num, event_date, location, event_name, file}`. The script refuses a manifest or file path inside the repository, calls `stage_results_file` once per entry, never commits, never prints a name — ids, counts and warning codes only. Exit code ≠ 0 if any entry failed to stage; already-staged files are reported as such and skipped.

## Full start list (FR-028)

Every recognised category of the file is staged and committed, whether or not a club athlete raced it. There is no "club categories only" switch. Categories with an unrecognised header are kept pending (reading-integrity contract), never dropped.

## Points and standings (FR-026)

`points_awarded` = the integer printed on the row. No recalculation against any points table for historical seasons; series 2024 and 2025 reference the descriptive schemes `copa_valle_2024` / `copa_valle_2025` (`is_official = false`, empty table). `standings.py` keeps summing `points_awarded`; the read schema gains `is_calculated: true` and the UI labels the table "Clasificación calculada por la plataforma". No reconciliation against the organiser's final table is attempted; a possible discard rule is a documented caveat.

## Idempotence and resumption (FR-027)

| Situation | Behaviour |
|---|---|
| Identical file staged again (same SHA-256), not yet committed | returns the existing pending import; creates nothing |
| Identical file staged again, already committed | `already_committed` warning with the import id; creates nothing in any table |
| Same válida, different file | existing revision flow (`will_be_revision`), unchanged |
| Load interrupted after some válidas | each válida is its own import; the board shows state per válida; committed ones are never redone |
| Commit with some categories blocked | consistent/acknowledged categories are ingested; the rest listed in `pending_categories` |
| `POST /{id}/commit-pending` | ingests only categories that have since become consistent or acknowledged; `409 nothing_pending` when none; **subject to the same `409 identity_review_pending` gate as `/commit`, and to the same `409 matches_unresolved` gate (below) for whichever categories it is ingesting this round** |

Re-running any step creates no duplicate válida, competitor, signature or result (data-model invariant 8).

## Board fields (`GET /race-imports/`) and `matches_unresolved`

`HistoricalLoadPage` groups the board by season and always commits with `resolved_matches: []` (no per-row match-resolution UI there — that stays in the current-season Import Wizard). Two additions to support that:

- `ImportListItem` gains `season: int | None`, `valida_num: int | None`, `series_name: str | None`, alongside the already-added `pending_categories_count: int`. Resolved from `parse_meta_json["header"]` while the import still carries meta (pending, or committed with `pending_categories` left); once an import is fully committed (meta cleared to `None`) they're resolved via `RaceEvent` → `RaceSeries` instead (`sequence_number`, `season_year`, `RaceSeries.name`), batched in one query per page. `None` only for a broken import with neither meta nor a resolved event.
- `POST /{id}/commit` and `POST /{id}/commit-pending` return `409 {"code": "matches_unresolved", "missing_count": int, "examples": [<normalized slugs>], "message": str}` when the acta has a club-athlete (TyR) row with no matching entry in `resolved_matches` — distinct from `identity_review_pending` (candidates in the cross-season identity queue) and `nothing_pending` (nothing newly eligible). The board routes the coach to the Import Wizard on this code instead of silently committing an unlinked row. Previously this was an unstructured `422` (`detail` a plain string); the status and shape both changed as part of this addition — no other `/commit` error shape moved.

`stage_results_file`'s actual signature carries a few parameters beyond the sketch above (`results_ext`, `general_bytes`, `kind_override`) needed to keep the current-season wizard's optional-GENERAL-upload and `kind`-override behaviour byte-identical; none of that is visible in the HTTP response shapes.

## Current season untouched (FR-029)

No read path of the current season changes: `GET /evolution`, results, standings, the season panorama and the race-AI analyst context for 2026 are identical with and without historical seasons loaded. Every one of those queries already filters by `season_year`; a regression test pins it.

## Ordering

No historical import may be committed against real data before the third-party lock gate (`contracts/third-party-lock.md`) is green. The runbook's pre-load checklist carries the line; `tasks.md` gate G3 enforces it.

## Tests

- `test_import_staging.py`: golden comparison — the extracted service yields the same `RaceImport` and response as today's `/parse` for a 2026 file; historical file staged with inputs taken verbatim; `header_mismatch` warning; GENERAL file rejected by the script.
- `test_race_imports_history.py`: full start list committed (categories without club athletes included); partial commit + `commit-pending`; identity gate on both commit routes; re-stage and re-commit create nothing (row counts of `race_events`, `race_competitors`, `race_competitor_signatures`, `race_results`, `race_imports` unchanged); resume after interruption; `is_calculated` on standings; printed points kept verbatim; `season`/`valida_num`/`series_name` on the list endpoint from both meta and the `RaceEvent`/`RaceSeries` fallback; `matches_unresolved` on both commit routes; a second identity rebuild does not re-download/re-parse any staged file (G4).
- `test_2026_unchanged.py`: byte-identical 2026 responses and analyst context with two historical seasons present.
- Script: refuses in-repo paths; `--dry` stages nothing; output contains no name (regex sweep against the fake-name list).
