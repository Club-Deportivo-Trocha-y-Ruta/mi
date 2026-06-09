# Comprehensive Results Revision Handling — Technical Design

**Project:** Club Deportivo Trocha y Ruta — Youth XCO
**Module:** `services/race/` + `routers/race_imports.py` + `frontend/src/routes/results/` (upload wizard)
**Date:** 2026-05-21
**Author:** System Architect agent
**Status:** Technical design — ready for `/sc:workflow` + `/sc:implement`
**Audience:** coach (UX banner/diff table validation), architect/dev (implementation)
**Authoritative input:** `docs/10-race-results/upload-design.md` (F-UP1-6 closed) + `upload-workflow.md` + `backend/app/services/race/ingestor.py` + `backend/app/routers/race_imports.py:280-330`
**Phase:** **F-UP-REV** (extends upload wizard F-UP)

---

## 0. Executive Summary

### Problem

Today the Copa Valle PDF ingestion system deduplicates **by binary SHA256**:

- If the coach uploads the **exact same byte-for-byte PDF** → endpoint `POST /imports/parse` returns `409 Conflict` (correct).
- If the coach uploads a **revised PDF** (the federation publishes a correction after complaints) with the same logical round but a different SHA256 → the system **accepts it as a new event and creates a logical duplicate**. Two `RaceEvent` entries end up with the same `(series_id, sequence_number)` or, worse, two `RaceImport.status=committed` pointing to conflicting results in the same row `(event_id, category_id, competitor_id)` (the existing UNIQUE blocks them but leaves partial inserts mixed with skips).

### Comprehensive solution

Change the dedup mental model: the logical unit is not **the PDF** but **the round** (`series_id + sequence_number`). When the coach uploads a PDF for an already-committed round with a different SHA:

1. The backend **automatically detects** it as a revision (not a 409 error).
2. The wizard dry-run returns a **complete diff** vs what is persisted: `creates / updates / deletes / unchanged`.
3. The UI shows that diff in a **reviewable table**, with counts and the preserved per-row decision (coach override possible in F2 — MVP uses the entire proposed diff).
4. On confirm, the system applies changes **transactionally** and records **one `RaceResultRevision` entry per change** (model already exists, already designed for this).
5. Soft-delete of removed entries (never physical `DELETE`). The audit trail is reversible via manual SQL.

### Scope

| Includes | Excludes |
|---|---|
| Automatic revision detection by `(series_id, sequence_number)` | Per-row diff override in UI MVP (all or nothing) |
| `parse` endpoint allows same (series, round) if SHA different | Endpoint to revert a revision (semantic rollback) — deferred F2 |
| `dry-run` endpoint returns structured `diff_rows` | UI to visualize revision history of a competitor — deferred F2 |
| `commit` endpoint accepts optional `revision_reason` | Notify parents when a revision is applied — out of scope MVP |
| Soft-delete of removed results | Diff of competitors between PDFs (only diff of `RaceResult`) |
| Complete audit in `RaceResultRevision` (action: create/update/delete) | Free field editing without re-uploading PDF |
| Migration: `parent_import_id` + `revision_reason` in `RaceImport` | Collaborative multi-coach support (pessimistic lock MVP) |
| UI step 2 with `diff` mode (instead of `matches`) | GENERAL diff — only applies to RESULTS (GENERAL only pre-fills catalog) |

**Does not change:** `RaceIngestor.ingest_event` (intact). `pdf_parser`, `normalizer`, `matcher` (intact). `RaceResultRevision` model (intact).

**Reuses maximally:**
- `RaceResultRevision` with its enum `create/update/delete`, `diff_json`, `reason`.
- `RaceResult.deleted_at` (soft-delete pattern already existing in F1.7).
- `RaceImport.status=pending/committed/dry_run/failed` and `RaceImport.series_id`.
- F-UP wizard 3 steps (without additional step — only changes step 2 render).

---

## 1. Logical revision detection

### 1.1 Canonical rule

> An ingestion is a **revision** if a `RaceEvent` exists with `(series_id, sequence_number) = (event_meta.series_id, event_meta.valida_num)` that already has **at least one `RaceImport.status=committed`** associated (via `RaceImport.event_id`).

Equivalently: revision = "there are already committed imports for that logical round".

### 1.2 Step-by-step algorithm (server-side, in `parse` and `dry-run`)

```
def detect_revision(db, series_id, valida_num) -> RevisionDetection | None:
    # 1. Look for RaceEvent by (series_id, sequence_number)
    event = db.execute(
        select(RaceEvent).where(
            RaceEvent.series_id == series_id,
            RaceEvent.sequence_number == valida_num,
        )
    ).scalar_one_or_none()

    if event is None:
        return None  # First import of this round — normal F-UP flow

    # 2. Are there previous committed imports?
    prior_import = db.execute(
        select(RaceImport)
        .where(
            RaceImport.event_id == event.id,
            RaceImport.status == RaceImportStatus.committed,
        )
        .order_by(RaceImport.committed_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if prior_import is None:
        return None  # Event exists but without committed imports — rare F1.7 legacy case

    return RevisionDetection(
        is_revision=True,
        parent_event_id=event.id,
        parent_import_id=prior_import.id,
        prior_committed_at=prior_import.committed_at,
        prior_imported_by=prior_import.imported_by_user_id,
    )
```

### 1.3 Trigger in API responses

**`POST /imports/parse` response** extended with optional field:

```python
class ImportParseResponse(BaseModel):
    parse_id: int
    results_sha256: str
    ...
    # NEW:
    will_be_revision: bool = False
    parent_event_id: int | None = None
    parent_import_id: int | None = None
    prior_committed_at: datetime | None = None
    prior_imported_by_name: str | None = None  # join to User
```

The `will_be_revision` field allows the UI to change mode **before** the dry-run (immediate banner post-step 1 without waiting for step 2).

**`POST /imports/{parse_id}/dry-run` response** extended with `diff_rows` and `diff_summary` (see §4 and §6).

### 1.4 Detection edge cases

| # | Scenario | Decision |
|---|---|---|
| D-1 | `RaceEvent` exists but **0 committed imports** (F1.7 legacy with `event_id=NULL`) | NOT a revision → normal F-UP flow, first "real" import with `event_id` set. Informational warning logged. |
| D-2 | Coach uploads PDF of **round 99 (championship)** already committed | Normal revision. Same logic applies. |
| D-3 | Coach uploads PDF with correct `valida_num` but different `season` (future 2027) | NOT a revision — `(series_id, sequence_number)` doesn't match because `series_id` is different. Creates new series + new event. |
| D-4 | Coach uploads **the same revised PDF twice** (same SHA different from committed) | First time is normal revision; second time **the revised SHA is already committed** → blocks with 409 (genuine byte-exact duplicate). |
| D-5 | Coach uploads revision of revision (3rd version of PDF) | Normal revision — `parent_import_id` points to the **last committed** (linear chaining via `committed_at DESC LIMIT 1`). |
| D-6 | Logically identical revision (same count, same positions, only PDF metadata different) | `diff_rows` returns empty → UI shows "This revision does not change any result" + button "Apply anyway (record revision import without changes)". Useful for traceability. |
| D-7 | Coach locally deleted the previous `RaceImport.status=pending` from the abandoned wizard (nightly F-UP cleanup) | No impact — detection is based on `committed`, not `pending`. |

---

## 2. Schema delta

### 2.1 Alembic migration — yes, needed

**New migration** `f9a0b1c2d3e4_race_imports_revision_delta.py`
**`down_revision = e8f9a0b1c2d3`** (F-UP head).

Reason: we need to persist **the lineage** (`parent_import_id`) and **the reason** (`revision_reason`) for auditing. Without migration there is nowhere to store them.

### 2.2 New columns in `race_imports`

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `parent_import_id` | INT FK→`race_imports.id ON DELETE SET NULL` | YES | NULL | Self-ref to previous committed import. NULL for first import or legacy. **Linear chaining** (each revision points to the immediately prior committed). |
| `revision_reason` | VARCHAR(300) | YES | NULL | Free text from coach explaining the revision (e.g. "Federation corrected positions after Andrés Mejía complaint 2026-05-19"). Optional when there are no deletes; **required when `diff` includes deletes** (application-level validation, not SQL). |

**`is_revision` boolean:** NOT persisted. **Derived** via `parent_import_id IS NOT NULL`. Reason: avoid denormalization + drift between two fields that must always coincide.

**`committed_at` timestamp:** already exists in `RaceImport` (`status` + `imported_at`/`committed_at` — verify exact name in model). If it didn't exist, add as part of this migration. (TBD during F-UP-REV1: read model and confirm.)

### 2.3 New indexes

| Index | Columns | Purpose |
|---|---|---|
| `ix_race_imports_parent_id` | `parent_import_id` | List descendant revisions of a given import (audit query). |
| (reuse) `ix_race_imports_event_id` | `event_id` | Already exists in F-UP1. It is the key index for revision detection. |

### 2.4 Legacy compatibility

- F1.7 imports with `event_id=NULL`: revision detection is **safe** because it queries `WHERE event_id = <X>` — legacy entries with NULL never match.
- F-UP imports with populated `event_id` but `parent_import_id=NULL` (first "real" import): they are the **first link** in the lineage. Any subsequent revision points to them.

### 2.5 Alembic migration — outline

```
revision: f9a0b1c2d3e4
down_revision: e8f9a0b1c2d3
description: Race imports revision support — parent_import_id + revision_reason
```

**Up:**
1. `ADD COLUMN parent_import_id INT NULL`
2. `ADD CONSTRAINT fk_race_imports_parent FOREIGN KEY (parent_import_id) REFERENCES race_imports(id) ON DELETE SET NULL`
3. `ADD COLUMN revision_reason VARCHAR(300) NULL`
4. `CREATE INDEX ix_race_imports_parent_id ON race_imports(parent_import_id)`

**Down:** drop index → drop FK → drop columns.

**Reversible:** yes. Does not require data migration because both columns are NULL for existing imports.

---

## 3. Diff algorithm

### 3.1 Match key between new PDF and persisted data

For each `(category, competitor)` pair:

- **Persisted:** `RaceResult` filtered by `event_id = parent_event_id` AND `deleted_at IS NULL`, joined to `RaceCompetitor.normalized_name`.
- **New PDF:** rows parsed by `parse_results_pdf` / `parse_results_csv`, normalized with `normalize_name`.

**Primary match:** `(category.code, competitor.normalized_name)`.

**Secondary match (fuzzy fallback):** if normalized_name doesn't match exactly, use `rapidfuzz.partial_ratio >= 92` on `normalized_name` within **the same category** (same `code`). Reason: typo in revision (`MEJIA` → `MEJÍA` with accent added by the federation).

**Does not match by bib_number.** Reason: bib can change between PDF versions if the federation corrected one that was mistyped. `normalized_name` is the source of truth.

### 3.2 Row classification

```
Let:
  persisted = {(cat_code, normalized_name): RaceResult}  # filtered deleted_at IS NULL
  new       = {(cat_code, normalized_name): ParsedRow}   # from the new PDF

For each key in (new.keys() ∪ persisted.keys()):
  case (in new) and (in persisted):
    p = persisted[key]; n = new[key]
    fields_changed = {}
    for field in ['position', 'status', 'race_time_ms', 'laps_behind', 'points_awarded']:
      if normalize(p.field) != normalize(n.field):
        fields_changed[field] = {'before': p.field, 'after': n.field}
    if fields_changed:
      yield DiffRow(action='update', result_id=p.id, diff=fields_changed, ...)
    else:
      yield DiffRow(action='unchanged', result_id=p.id)

  case (in new) and NOT (in persisted):
    # New competitor in revision (rare but valid: the federation added an omitted athlete)
    yield DiffRow(action='create', new_row=n, ...)

  case NOT (in new) and (in persisted):
    # Competitor in persisted but NOT in revised PDF
    # Default: soft-delete (the federation officially removed it — DSQ / DNF post-protest)
    yield DiffRow(action='delete', result_id=p.id, ...)
```

### 3.3 Diff edge cases

| # | Scenario | Treatment |
|---|---|---|
| E-1 | Competitor in persisted with `deleted_at IS NOT NULL` and reappears in revision | Treated as `create` (new `RaceResult` row; the old one remains soft-deleted; the revision "revives" the result with a new entry). |
| E-2 | Same competitor in two categories (rare but possible if federation corrected category) | Treats each `(cat, name)` as an independent key: will appear as `delete` in old category + `create` in new category. |
| E-3 | Typo corrected in `normalized_name` (e.g. "JUAN PEREZ" → "JUAN PÉREZ" after `normalize_name`) | If `normalize_name` collapses accents → exact match. If not → fuzzy fallback (§3.1). If fuzzy also fails → appears as old `delete` + new `create` (suboptimal but safe; coach reviews the diff before confirming). |
| E-4 | Competitor without position (`position=NULL`, status=`DNF`) in persisted, now with `position=42, status=FINISHED` in revision | `update` with `position` and `status` in `fields_changed`. |
| E-5 | Change of `athlete_id` (TyR linkage changed) | NOT included in revision diff. The athlete linkage is preserved from the existing record (not overwritten). Reason: the TyR matching decision belongs to the coach, not the federation. If the coach wants to change `athlete_id`, they do it via dedicated endpoint or re-confirm matches in step 2 (UI keeps previous decisions as pre-fill). |
| E-6 | `points_awarded` changed because the federation recalculated (ranges, bonus) | Normal `update` — field is in the list. |
| E-7 | Revised PDF has a **completely new category** (the federation enabled "JUN_F" where only "JUN_M" existed before) | Results for that category all appear as `create`. Zero `update`/`delete` in that category. |
| E-8 | Revised PDF **omits an entire category** (the federation removed "PROMO" due to low enrollment) | All results for that category appear as `delete`. |

### 3.4 `DiffRow` fields (API response)

```python
class DiffRow(BaseModel):
    action: Literal["create", "update", "delete", "unchanged"]
    category_code: str
    competitor_display_name: str  # from new PDF or persisted (private: does not expose PII of minors here because they are already in DB)
    competitor_normalized_name: str
    # For action=update and unchanged:
    result_id: int | None = None
    # For action=create:
    new_row: ParsedRowPreview | None = None
    # For action=update:
    fields_changed: dict[str, dict[str, Any]] | None = None
        # E.g. {"position": {"before": 5, "after": 3}, "race_time_ms": {...}}
    # For action=delete:
    deleted_row: ResultPreview | None = None
```

### 3.5 `DiffSummary` (header for UI)

```python
class DiffSummary(BaseModel):
    total_persisted: int
    total_in_new_pdf: int
    creates: int
    updates: int
    deletes: int
    unchanged: int
    fuzzy_matches: int     # how many pairs matched via fuzzy (suspicious)
    cross_category_moves: int  # how many competitors appear as delete+create across categories
```

`fuzzy_matches > 0` ⇒ yellow banner in UI: "Some competitors were matched approximately. Review before confirming."

---

## 4. Revision commit algorithm

### 4.1 Pre-conditions

- `parse_id` valid, status=`pending`, ownership confirmed.
- `is_revision=True` derived from detection.
- Diff calculated and passed to commit endpoint (re-computed server-side to avoid TOCTOU).
- `revision_reason` ≠ None if `summary.deletes > 0` (application-level validation → 400 if fails).
- `confirm=True` in body (same as F-UP commit).

### 4.2 Transactional pseudocode

```python
async def commit_revision(parse_id, event_meta, revision_reason, current_user):
    async with db.begin():  # BEGIN
        # 1. Re-load context
        parse_import = await db.get(RaceImport, parse_id)
        assert parse_import.status == RaceImportStatus.pending
        detection = await detect_revision(db, series_id, event_meta.valida_num)
        assert detection is not None, "race condition: no longer a revision"

        # 2. Optimistic lock on RaceEvent
        event = await db.execute(
            select(RaceEvent).where(RaceEvent.id == detection.parent_event_id)
            .with_for_update()  # advisory lock MySQL
        )

        # 3. Re-parse PDF from storage_path (already uploaded in /parse)
        results_by_cat = await reparse_from_storage(parse_import.storage_path)

        # 4. Re-compute diff (server-side, final authority)
        diff_rows = compute_diff(db, event.id, results_by_cat)

        # 5. Validate revision_reason if there are deletes
        if any(r.action == "delete" for r in diff_rows) and not revision_reason:
            raise HTTPException(400, "revision_reason required if there are deletes")

        # 6. Apply each diff_row transactionally
        for row in diff_rows:
            if row.action == "create":
                new_result = build_race_result(row.new_row, event.id, parse_import.id, current_user.id)
                db.add(new_result)
                await db.flush()  # needed to have new_result.id
                db.add(RaceResultRevision(
                    result_id=new_result.id,
                    action=RaceResultRevisionAction.create,
                    changed_by_user_id=current_user.id,
                    diff_json={"after": serialize_result(new_result)},
                    reason=revision_reason,
                ))

            elif row.action == "update":
                result = await db.get(RaceResult, row.result_id)
                before = serialize_result(result)
                apply_changes(result, row.fields_changed)
                after = serialize_result(result)
                db.add(RaceResultRevision(
                    result_id=result.id,
                    action=RaceResultRevisionAction.update,
                    changed_by_user_id=current_user.id,
                    diff_json={"before": before, "after": after, "fields": list(row.fields_changed.keys())},
                    reason=revision_reason,
                ))

            elif row.action == "delete":
                result = await db.get(RaceResult, row.result_id)
                before = serialize_result(result)
                result.deleted_at = datetime.now(timezone.utc)
                # Policy: do NOT change result.status — leave it as it was.
                # deleted_at is the discriminator. DSQ semantic status is done
                # via revision_reason in human-readable form.
                db.add(RaceResultRevision(
                    result_id=result.id,
                    action=RaceResultRevisionAction.delete,
                    changed_by_user_id=current_user.id,
                    diff_json={"removed": before},
                    reason=revision_reason,
                ))

            # action=unchanged → skip

        # 7. Promote RaceImport to committed with lineage
        parse_import.status = RaceImportStatus.committed
        parse_import.parent_import_id = detection.parent_import_id
        parse_import.revision_reason = revision_reason
        parse_import.event_id = event.id
        parse_import.stats_json = {
            "is_revision": True,
            "creates": sum(1 for r in diff_rows if r.action == "create"),
            "updates": sum(1 for r in diff_rows if r.action == "update"),
            "deletes": sum(1 for r in diff_rows if r.action == "delete"),
            "unchanged": sum(1 for r in diff_rows if r.action == "unchanged"),
        }

    # COMMIT (implicit on exit from db.begin())

    return CommitRevisionResponse(...)
```

### 4.3 Important policy: status of soft-deleted results

**Decision:** soft-delete via `deleted_at` **does NOT change** `status`. The semantic status (DSQ, DNF, DNS, FINISHED) reflects **what the federation originally published**. The soft-delete is operational metadata ("this result was removed by revision").

**Reason:** preserves historical integrity. If a coach wants to report "was disqualified", they do it in `revision_reason`. `RaceResult.status` always reflects the last thing published by the federation.

### 4.4 What if two coaches commit revisions simultaneously?

Pessimistic lock via `SELECT ... FOR UPDATE` on `RaceEvent` (§4.2 step 2). The second transaction waits; on acquiring the lock it recomputes the diff (which now includes changes from the first) and applies only the remaining delta.

**Edge:** if the second coach uploaded the **same PDF** as the first, their post-lock diff will be entirely `unchanged` → nothing is applied, but the `RaceImport` committed is still persisted with `stats.creates=0,updates=0,deletes=0` and `parent_import_id=<id of the first commit>`. Complete audit trail.

---

## 5. API changes

### 5.1 `POST /imports/parse` — behavior change

**Before (F-UP):**
- SHA committed found → `409 Conflict`.

**After (F-UP-REV):**
- **Identical SHA** (exact binary) committed found → still `409 Conflict`. (Genuine byte-exact duplicate; provides no new information.)
- **`(series_id, sequence_number)` already has committed but SHA different** → `200 OK` with `will_be_revision=true, parent_event_id, parent_import_id, prior_committed_at, prior_imported_by_name`.

**No breaking change:** the new fields are optional with falsy defaults. F-UP client continues working.

⚠️ **Note:** determining `(series_id, sequence_number)` in `parse` requires the client to send `series_name + season + valida_num` in the form (already does, see `race_imports.py:281-283`). If not sent, the detector falls back to `None` and treats it as the first upload. Confirm that the wizard pre-fills these fields in step 1 even before step 2.

### 5.2 `POST /imports/{parse_id}/dry-run` — extended response

```python
class ImportDryRunResponse(BaseModel):
    parse_id: int
    report: IngestReport  # as before
    matches_preview: list[MatchPreview]  # as before — only if NOT a revision
    will_create_event: bool
    will_update_event_id: int | None

    # NEW (only present if is_revision=true):
    is_revision: bool = False
    parent_event_id: int | None = None
    parent_import_id: int | None = None
    prior_committed_at: datetime | None = None
    prior_imported_by_name: str | None = None
    diff_summary: DiffSummary | None = None
    diff_rows: list[DiffRow] | None = None  # ordered: deletes → updates → creates → unchanged
```

**Backend behavior:**
- If `is_revision=False` → F-UP behavior intact, response without `diff_*` (optional NULL fields).
- If `is_revision=True` → `IngestReport.results_inserted` represents the count **of creates**, not "all results from the new PDF". This maintains semantics of "what will be written". `IngestReport.warnings` includes `"REVISION: vs import_id=<parent>"`.

### 5.3 `POST /imports/{parse_id}/commit` — extended body

```python
class ImportCommitRequest(BaseModel):
    event_meta: EventMeta
    match_decisions: dict[str, int | None]
    force_reingest: bool = False
    confirm: bool

    # NEW:
    revision_reason: str | None = Field(None, max_length=300)
```

**Application-level validation (not SQL):**
- If `is_revision=True` and `diff_summary.deletes > 0` and `revision_reason` empty → `400`.
- If `is_revision=False` and `revision_reason` provided → `400` ("revision_reason only applies to revisions").

**Extended response:**

```python
class ImportCommitResponse(BaseModel):
    parse_id: int
    event_id: int
    series_id: int
    report: IngestReport
    storage_url_results: str | None
    storage_url_general: str | None

    # NEW:
    is_revision: bool = False
    parent_import_id: int | None = None
    revisions_created: int = 0  # how many rows in race_result_revisions
    creates: int = 0
    updates: int = 0
    deletes: int = 0
    unchanged: int = 0
```

### 5.4 New errors / changes

| Code | New trigger |
|---|---|
| 400 | `revision_reason` required (deletes present) or `revision_reason` provided but not a revision |
| 409 (no change) | Byte-exact identical SHA already committed |
| 422 (no change) | Unknown category (same as F-UP) |
| 423 Locked (NEW optional) | Race condition: another coach is committing revision to the same event (lock timeout) — UI shows "Another coach is applying a revision to this round. Wait 30s and retry." |

### 5.5 Optional new endpoint (NOT MVP)

`GET /imports/{import_id}/revisions` — list revisions derived from an import. Useful for auditing. **Deferred F2** unless coach explicitly requests it.

---

## 6. UI step 2 — `diff` mode (changes render according to `is_revision`)

### 6.1 Mode logic

```typescript
const step2Mode: 'matches' | 'diff' =
  parseResponse.will_be_revision ? 'diff' : 'matches';
```

### 6.2 `diff` mode — layout

```
╔══════════════════════════════════════════════════════════════════╗
║ Step 2 of 3 — REVISION DETECTED                                  ║
╠══════════════════════════════════════════════════════════════════╣
║ ⚠ This round was previously imported.                            ║
║                                                                  ║
║ Round IV — Cali (event #4)                                       ║
║ Imported by:  coach       ·   2026-05-17 18:42                   ║
║ Prior import: #12         ·   PDF: valida_iv_v1.pdf              ║
║                                                                  ║
║ Changes detected vs prior PDF:                                   ║
║                                                                  ║
║  ┌─────────────────────────────────────────────────────────┐     ║
║  │  3 new    ·  12 updated  ·  2 removed                   │     ║
║  │                          ·  210 unchanged               │     ║
║  └─────────────────────────────────────────────────────────┘     ║
║                                                                  ║
║  [✓] Show only changes                                           ║
║                                                                  ║
║  ┌──────┬──────────┬──────────────────┬──────────────────────┐   ║
║  │ Act. │ Cat      │ Competitor       │ Changes              │   ║
║  ├──────┼──────────┼──────────────────┼──────────────────────┤   ║
║  │ 🟡 U │ JUN_M    │ ANDRÉS MEJÍA     │ position: 5 → 3      │   ║
║  │      │          │                  │ time: 50:12 → 49:08  │   ║
║  ├──────┼──────────┼──────────────────┼──────────────────────┤   ║
║  │ 🟡 U │ INF_A_M  │ JUAN PÉREZ MORA  │ position: NULL → 4   │   ║
║  │      │          │                  │ status: DNF → FIN.   │   ║
║  ├──────┼──────────┼──────────────────┼──────────────────────┤   ║
║  │ 🟢 C │ INF_A_F  │ MARÍA GÓMEZ      │ NEW in revision      │   ║
║  │      │          │                  │ pos: 7  time: 33:42  │   ║
║  ├──────┼──────────┼──────────────────┼──────────────────────┤   ║
║  │ 🔴 D │ JUN_M    │ DIEGO ROJAS      │ REMOVED              │   ║
║  │      │          │                  │ (was pos 8, FIN.)    │   ║
║  └──────┴──────────┴──────────────────┴──────────────────────┘   ║
║                                                                  ║
║  ⚠ There are deletions — explain the reason for the revision:    ║
║  ┌────────────────────────────────────────────────────────────┐  ║
║  │ Results corrected by the federation after complaint from   │  ║
║  │ Andrés Mejía regarding timed finish in V-IV (2026-05-19)   │  ║
║  └────────────────────────────────────────────────────────────┘  ║
║  120/300 characters                                              ║
║                                                                  ║
║                          [← Back]   [Final preview →]            ║
╚══════════════════════════════════════════════════════════════════╝
```

### 6.3 New UI components

| Component | Location | Responsibility |
|---|---|---|
| `RevisionBanner` | `frontend/src/components/race/RevisionBanner.tsx` | Yellow banner with prior import metadata, user lookup via API. |
| `DiffSummaryCounts` | `frontend/src/components/race/DiffSummaryCounts.tsx` | 4 colored badges with counts. |
| `DiffTable` | `frontend/src/components/race/DiffTable.tsx` | Virtualized table (TanStack Table + react-window if >100 rows). Columns: Action (badge), Category, Competitor, Changes. "Show only changes" filter. |
| `RevisionReasonInput` | `frontend/src/components/race/RevisionReasonInput.tsx` | Controlled textarea with counter and validation (required if deletes > 0). |

### 6.4 Step 2 behavior by mode

| Mode | Show | Required inputs |
|---|---|---|
| `matches` (not revision) | EventMetaForm + MatchDecisionTable (F-UP) | match decisions |
| `diff` (revision) | EventMetaForm (pre-fills with existing event values) + RevisionBanner + DiffSummaryCounts + DiffTable + RevisionReasonInput | revision_reason (if deletes>0) |

**EventMetaForm in `diff` mode:** pre-fills with current values of the persisted `RaceEvent` (weather, temperature, city). The coach can edit them. Changes are applied via the ingestor upsert (same as F-UP — the `_upsert_event` method already does in-place update).

### 6.5 Step 3 success — confirmation

```
╔══════════════════════════════════════════════════════════════╗
║ ✓ Revision applied successfully                              ║
║                                                              ║
║  Event:  Round IV — Cali (event #4)                          ║
║  Import: #15 (revision of #12)                               ║
║                                                              ║
║  Changes applied:                                            ║
║    🟢 3 new results                                          ║
║    🟡 12 updated results                                     ║
║    🔴 2 removed results (soft-delete)                        ║
║    ⚪ 210 unchanged                                          ║
║                                                              ║
║  Audit:                                                      ║
║    17 rows recorded in race_result_revisions                 ║
║    Reason: "Results corrected by the federation..."          ║
║                                                              ║
║  [Load another file]    [Go to New analysis →]               ║
╚══════════════════════════════════════════════════════════════╝
```

### 6.6 UX pagination if large diff

- **N ≤ 50 changes:** full table rendered (no virtualization).
- **50 < N ≤ 500:** TanStack Table with virtualization (react-window/react-virtual).
- **N > 500:** additionally, client pagination (20/page) + warning banner "Unusually large diff (>500 changes). Are you sure it's the same round?".

---

## 7. Risk register

| # | Risk | Prob | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Data loss from erroneous soft-delete (revision that was actually a PDF from a different round confused by the coach) | Low | **High** | (a) explicit confirmation in step 3 with checkbox; (b) `revision_reason` required if there are deletes; (c) complete audit trail in `RaceResultRevision` (reversible via SQL: `UPDATE race_results SET deleted_at=NULL WHERE id IN (SELECT result_id FROM race_result_revisions WHERE ...)`); (d) yellow banner "Unusually large diff" if >500 changes or deletes >20% of total. |
| R2 | Very large diff (>500 changes) degrades UI performance (render lag) | Low | Medium | TanStack Table with virtualization. Client pagination. Backend always returns `diff_rows` complete (no streaming MVP) but limited by `IngestReport.results_inserted < 5000` (defensive cap: if exceeded, return 422 "diff too large, contact dev"). |
| R3 | Coach accidentally changes normalized_name (re-parsing extracts differently because we updated `normalize_name`) → exact match fails, fuzzy also fails → everything appears as delete+create | Low | High | (a) `normalize_name` is a pure and stable function (not changed between backend versions without prior migration); (b) fuzzy match with `partial_ratio >= 92` covers minor typos; (c) `DiffSummary.fuzzy_matches` count visible in UI → banner if > 0; (d) `cross_category_moves` also visible. |
| R4 | Race condition: 2 coaches upload same revised PDF simultaneously | Very low | Low | Pessimistic lock `SELECT ... FOR UPDATE` on `RaceEvent` in commit (§4.2). Second coach waits and recomputes diff post-lock (will be entirely `unchanged`). If SHA of second === SHA of first → normal 409. |
| R5 | `parent_import_id` chain corrupted if admin does hard-delete of an import (manual SQL operation) | Very low | Low | FK `ON DELETE SET NULL` preserves descendants with `parent_import_id=NULL` (broken audit but doesn't break queries). Document in runbook that imports should **never** be hard-deleted — always mark `status=failed`. |
| R6 | Re-parsing in commit (§4.2 step 3) uses storage_path but file was moved/deleted | Low | Medium | Storage path is **immutable** post-`/parse` (F-UP DT-4: parse uploads to `pending/`, commit moves to `committed/` only at the end). If rename fails → rollback. If file doesn't exist → 500 with clear message. |
| R7 | Coach waits for diff but `dry-run` hangs (large PDF, costly fuzzy matching) | Low | Medium | 30s timeout already exists in parse (F-UP). Diff is trivial in SQL (1 persisted query + 1 fuzzy in memory); O(N×M) cost bounded by N<300 competitors and M=top-3 candidates. Estimated <500ms for typical diff. If exceeds 5s → log warning. |
| R8 | `RaceResultRevision.action=delete` is "orphaned" if soft-delete is manually reverted afterwards | Low | Low | By design: revisions are **append-only**. Reverting a soft-delete via SQL leaves `deleted_at=NULL` but keeps the `action=delete` revision as historical evidence. If coach wants to record "was reactivated", a future revision of the same PDF will re-create an `action=create` entry. |
| R9 | UI filter "Show only changes" hides `unchanged` rows but on confirm the backend recomputes diff and applies everything — visual vs execution discrepancy | Very low | Medium | Backend is final authority (§4.2 step 4). The UI filter only affects render. Step 3 shows complete summary (with `unchanged` count) → coach sees the real total. |
| R10 | Coach abandons wizard in step 2 with revision pending → on return, the persisted data changed (another coach revised in between) | Low | Medium | TTL pending 24h (F-UP). If coach returns and `parse_id` is still valid, the dry-run **re-executes** (not cached) and shows the updated diff. Banner "Notice: these changes reflect the current state, not the state when you uploaded the file." (future F2). |
| R11 | `revision_reason` filtered in application logs contains names of minors | Low | High | Logger sanitization: `logger.info("revision_committed import_id=%d reason_length=%d", id, len(reason))` — never log the reason text. The reason is only persisted in DB, not in logs. |
| R12 | Coach uploads revised PDF that **excludes GENERAL** intentionally — this is not a GENERAL revision (which only pre-fills catalog) but coach expects to see changes | Low | Low | Document in UI: "Revisions only apply to round results. The season accumulator (GENERAL) is automatically recalculated." |

---

## 8. Decisions closed for the workflow

`/sc:workflow` and `/sc:implement` must respect the following without re-consulting:

1. **`RaceResultRevision` is reused** intact. Three actions: `create`, `update`, `delete`. No new model created.
2. **`RaceResult.deleted_at`** is the soft-delete discriminator. `status` does NOT change on deletes — only `deleted_at`.
3. **Alembic migration** adds `parent_import_id` (self-ref FK, ON DELETE SET NULL) + `revision_reason VARCHAR(300)` + index. Reversible.
4. **`is_revision` is derived** from `parent_import_id IS NOT NULL`. NOT persisted as a column.
5. **Revision detection:** `(series_id, sequence_number)` with prior `RaceImport.status=committed`. Linear chaining via `committed_at DESC LIMIT 1`.
6. **Diff match:** primary `(category.code, normalized_name)`. Fuzzy `partial_ratio >= 92` within same category as fallback. NO match by bib.
7. **Diff includes:** create / update / delete / unchanged. Compared fields: `position, status, race_time_ms, laps_behind, points_awarded`. Does NOT compare `athlete_id` (TyR linkage preserved by upsert).
8. **`revision_reason` required** if there are deletes. Optional otherwise.
9. **`POST /parse`:**
   - Byte-exact SHA committed → 409 (no change).
   - `(series, round)` committed but SHA different → 200 with `will_be_revision=true`.
10. **`POST /dry-run` response** includes `is_revision`, `diff_summary`, `diff_rows` (only if revision).
11. **`POST /commit` request** accepts `revision_reason: str | None`. App-level validation.
12. **Transactional commit:** one `RaceResultRevision` per change (create/update/delete). Soft-delete via `deleted_at=NOW()`. Pessimistic lock `FOR UPDATE` on `RaceEvent`.
13. **UI step 2 dual mode:** `matches` (not revision) | `diff` (revision). Same wizard, different render.
14. **UI step 2 `diff` mode:** RevisionBanner + DiffSummaryCounts + DiffTable + RevisionReasonInput. EventMetaForm pre-filled with existing event data.
15. **DiffTable virtualized** if >50 rows (TanStack Table + react-window).
16. **DiffTable readonly in MVP:** coach CANNOT override the diff row by row. All or nothing. Override is F2 if coach requests it.
17. **`athlete_id` linkage** NOT overwritten in revision. The upsert preserves the existing TyR binding.
18. **Append-only audit:** `RaceResultRevision` is never hard-deleted. Reversion via manual SQL (documented in runbook).
19. **Pessimistic lock** via `SELECT ... FOR UPDATE` on `RaceEvent` in commit. Default MySQL timeout (50s).
20. **Tests required before merging:** backend new ≥90% in `diff.py` + `commit_revision`; frontend new components ≥85% including DiffTable virtualization; E2E happy revision (re-upload modified Round IV) + 1 error path (deletes without reason).
21. **No new endpoint** `GET /imports/{id}/revisions` in MVP. Deferred F2.
22. **No per-row override** in DiffTable MVP. Deferred F2.

---

## 9. Open questions for coach (⚠️ require validation)

| # | Question | Default recommendation if no response |
|---|---|---|
| Q1 | ⚠️ Does the coach want to see `unchanged` rows by default in DiffTable, or hide them ("Show only changes" filter active by default)? | **Filter active by default** (hides unchanged). Less visual noise; toggle available. |
| Q2 | ⚠️ Should the `revision_reason` field be required ALWAYS (not just if there are deletes)? | **Only if there are deletes** (closed decision 8). Reason: typos in positions don't require justification; removing an athlete does. |
| Q3 | ⚠️ Should applying a revision notify parents of affected TyR athletes? | **NO in MVP** (consistent with upload v1 without emails). Eventually F2 with opt-in. |
| Q4 | ⚠️ Allow coach to **override** the diff row by row ("don't apply this create") in MVP? | **NO** (decision 16). If explicitly requested → F2. |
| Q5 | ⚠️ After applying a revision, does the coach want to see the complete revision history of the event? | **NO in MVP** (decision 21). Show only the last commit. `GET /imports/{id}/revisions` endpoint deferred. |
| Q6 | ⚠️ If the diff has **0 changes** (logically identical revised PDF), allow "fake" commit to record traceability? | **YES** (D-6 §1.4). Generates committed `RaceImport` with all stats at 0 + `parent_import_id` set. Useful for auditing ("I verified that v2 of the PDF changed nothing"). |
| Q7 | ⚠️ On a revision, is `RaceEvent.climate`, `temperature_c`, etc. also updated if the coach edited the EventMetaForm? | **YES** (decision 14 + F1.7 upsert already does it). This is a feature, not a bug — the coach can correct the reported weather via revision. |

---

## 10. Appendix — `diff_json` examples in `RaceResultRevision`

### 10.1 action=create

```json
{
  "after": {
    "result_id": 1234,
    "event_id": 4,
    "category_id": 7,
    "competitor_id": 88,
    "athlete_id": null,
    "bib_number": 152,
    "position": 7,
    "status": "finished",
    "race_time_ms": 2022000,
    "laps_behind": null,
    "points_awarded": 18
  }
}
```

### 10.2 action=update

```json
{
  "before": {
    "position": 5,
    "status": "finished",
    "race_time_ms": 3012000,
    "laps_behind": null,
    "points_awarded": 22
  },
  "after": {
    "position": 3,
    "status": "finished",
    "race_time_ms": 2948000,
    "laps_behind": null,
    "points_awarded": 26
  },
  "fields": ["position", "race_time_ms", "points_awarded"]
}
```

### 10.3 action=delete

```json
{
  "removed": {
    "result_id": 891,
    "event_id": 4,
    "category_id": 7,
    "competitor_id": 42,
    "bib_number": 412,
    "position": 8,
    "status": "finished",
    "race_time_ms": 3142000,
    "points_awarded": 12
  }
}
```

---

## 11. Next steps

1. **Validate Q1-Q7 with coach** (10 min session — most have a reasonable default).
2. **`/sc:workflow revision-design.md`** → generates `revision-workflow.md` with phases F-UP-REV0..7 (already drafted in parallel file).
3. **`/sc:implement F-UP-REV1`** for the Alembic migration.
4. **Coordinate with F-UP in progress:** F-UP-REV depends on F-UP being merged (needs `event_id`, `kind`, `storage_*` in `RaceImport`).
5. **Code review before merge:** special attention to the pessimistic lock §4.2 and the diff §3.2 (the most likely source of bugs).

---

**End of document.**
