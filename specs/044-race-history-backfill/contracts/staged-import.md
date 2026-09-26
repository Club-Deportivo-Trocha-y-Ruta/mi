# Contract — Staged import and review API deltas (amendment 2026-09-26 · FR-023 · FR-044 · FR-048 · FR-049)

This contract replaces the "Staging service" and "Script" sections of `historical-load.md` and the parser section of `reading-integrity.md`. Everything else in those contracts still holds: completeness, corrections, acknowledgement, partial commit, identity gate, idempotence and board fields. Research: R-20, R-23, R-25, R-26, R-27.

## Staging service (parse-free)

`app/services/race/import_staging.py`:

```python
async def stage_extracted_results(
    db: AsyncSession, *,
    document: ParsedResults,                  # from results_skill.apply_profile
    profile: StagedProfileMeta,               # profile_id, profile_sha256, engine_version
    file_bytes: bytes, original_filename: str, results_ext: Literal["pdf", "csv"],
    header: StageHeader,                      # series_name, series_kind, series_level, season,
                                              # valida_num, event_name, event_date, location
    actor: User, ctx: AuditContext,
    dry: bool = False,
) -> StageResult                              # import_id, status, is_revision, parent_import_id,
                                              # already_committed, n_rows, n_categories, warnings
```

This is the successor of `stage_results_file`. The body keeps what did not depend on parsing; the parse step, `parse_event_header`, the GENERAL path and `_response_for_already_staged` are gone. The steps, in order:

1. `sha256(file_bytes)`. If a committed import has the same SHA, return `already_committed` and create nothing. If a pending import has the same SHA, return it unchanged. This is today's dedupe.
2. Refuse an empty document (0 rows), with the code `empty_document`.
3. `_get_or_create_series`, `_categories_read` (mapping kinds, completeness) and `unreadable_rows`, exactly as `/parse` computed them.
4. Upload the evidence with `storage_sftp.upload_bytes` to `race-imports/pending/{parse_uuid}/resultados.{ext}`.
5. In one transaction: insert the `RaceImport`, insert the `race_import_staged_documents` row, and record the audit `create` with `meta.via = "results_skill"`. `imported_at` is taken from `func.now()`, the database clock. If the transaction fails, delete the uploaded object (best effort) and re-raise.
6. `detect_revision` fills `is_revision`, `parent_import_id` and `parent_committed_at`.

Two things do not happen at stage:
- **No identity rebuild.** The commit gate rebuilds when the queue is stale, as today (`_identity_rebuild_needed`).
- **No conditions.** `parse_meta_json["conditions"]` is written with every field `null`.

## Staged document loader

`app/services/race/staged_document.py`:

```python
class StagedDocumentMissing(Exception): ...          # legacy import, staged by the old upload

async def load(db: AsyncSession, imp: RaceImport) -> ParsedResults
async def delete(db: AsyncSession, import_id: int) -> None
```

`load` reads the document row and deserialises it. Corrections are applied by the callers, as today (`completeness.apply_corrections`).

`load` replaces three pieces of the router:
- `_reload_results_document`, used by corrections and acknowledge;
- `_reload_parsed_from_storage`, used by dry-run, commit, commit-pending and the identity loader;
- the two LRU caches, `clear_parsed_rows_caches` and its autouse test fixture.

This closes privacy-audit finding A. With no file to fetch, the "release the MySQL connection before SFTP" commits in those routes also go.

## API deltas (`/api/race-analysis/imports`)

| Route | Change |
|---|---|
| `POST /parse` | **removed** (FR-044); the audit-registry entry and the settings used only by it are removed too |
| `POST /{id}/dry-run` | rows from `staged_document.load`; a revision returns the revision shape (`revision-via-skill.md`); `409 restage_required` when the document is missing |
| `POST /{id}/commit` | rows from the loader; the revision branch goes through `commit_revision`; deletes the document on full commit; `409 restage_required` when missing |
| `POST /{id}/commit-pending` | rows from the loader; deletes the document when nothing remains pending; `409 restage_required` when missing (a legacy partial commit, R-27) |
| `POST /{id}/corrections`, `POST /{id}/acknowledge` | rows from the loader; `409 restage_required` when missing |
| `POST /{id}/discard` | also deletes the document |
| `GET /{id}`, `GET /` | + `restage_required: bool` on `ImportDetailRead` and `ImportListItem`: true when the import is `pending` with no document, or committed with `pending_categories` and no document. It is computed with one batched `EXISTS` per page, so no document is loaded. Otherwise unchanged |
| reason catalogues, `GET /{race_event_id}/diff` | unchanged |
| `POST /api/race-identity/rebuild`, commit identity gate | `load_identity_rows` reads the loader; a legacy staged import is reported as unreadable, as an unreadable file is today; GENERAL rows are no longer loaded |

`409` body: `{"detail": "restage_required", "import_id": <id>}`. The message shown to the coach lives in the frontend (`ui-review-only.md`).

## GENERAL retirement (R-25)

Removed:
- `parse_general_pdf`, `_parse_general_with_timeout` and `GeneralRow`;
- the ingestor's "GENERAL first" step (`_upsert_competitor_from_general`) and its `general_by_category` parameter;
- the unused `pdf_general_sha256`;
- the GENERAL branch of `load_identity_rows` and `load_universe`, including the `GENERAL_VALIDA_NUM` handling.

Kept: `RaceImportKind.general` and `both`, and the `general_*` columns, for legacy rows only.

## Settings removed

`race_max_pdf_mb`, `race_parse_timeout_seconds` and `race_pending_ttl_hours` (`app/config.py`), plus their `.env.example` lines.

## Structural guards (FR-044, SC-014)

`backend/tests/privacy/test_no_results_upload.py`:

1. **Allow-list scan.** Walk `app.routes`. The set of `(method, path)` pairs whose endpoint declares an `UploadFile` or `File(...)` parameter equals exactly:
   - `POST /api/training-sessions/{session_id}/route-file`
   - `POST /api/training-sessions/{session_id}/media`
   - `POST /api/race-analysis/race-events/{race_event_id}/course/variants`
   - `PUT /api/race-analysis/race-events/{race_event_id}/course/variants/{variant_id}/file`
2. **Denied path.** A multipart POST to `/api/race-analysis/imports/parse` returns 404 or 405 for admin, coach, parent and athlete.
3. **No router imports `app.services.race.results_skill`**, so the offline engine never becomes an upload path by accident.

## Tests (backend)

- A new test helper, `tests/helpers/staging.py::stage_for_test(db, document, header, actor, …)`, replaces the HTTP `/parse` calls. About 60 tests across the following files are ported to it:
  - `test_race_imports.py`, `test_race_imports_revision.py`, `test_race_series_014.py`, `test_race_imports_series_level.py`, `test_audit_race_results.py`;
  - `test_race_imports_club_scope.py` (router and root), `test_race_imports_integrity.py`, `test_race_imports_history.py`, `test_race_imports_identity_gate.py`.
  - Tests that only asserted upload mechanics (size cap, magic bytes, timeout, 410 re-upload, cache reuse) are deleted with the code they covered, and each deletion is listed in the task that makes it.
- `test_import_staging.py` is rewritten for `stage_extracted_results`:
  - dedupe (pending and committed);
  - an empty document is refused;
  - an upload failure and a transaction failure leave neither an orphan import nor an orphan document, and the uploaded object is deleted;
  - `imported_at` comes from the database clock;
  - the public meta keys match what the wizard's resume path reads;
  - the audit row carries `via`.
- `test_staged_document.py`: load round-trip; a missing document raises `StagedDocumentMissing`; delete on full commit, on commit-pending completion and on discard; kept on partial commit.
- Legacy handling: an import created without a document gets `409 restage_required` on each review route; discard still works; GET still works; `restage_required` is true on detail and list, and false for a staged import. The list is checked with a statement-count assertion (no N+1).
- `test_audit_coverage` stays green after the registry entry is removed.
- `tests/conftest.py` loses the cache-clear autouse fixture.
