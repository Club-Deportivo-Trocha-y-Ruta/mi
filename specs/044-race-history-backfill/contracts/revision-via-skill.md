# Contract — Correcting a committed válida through a revision (amendment 2026-09-26 · FR-027 corrected · SC-006)

A different reading of a válida that is already committed can only enter as a **revision**. The coach sees what it changes and commits it with a reason from the closed list. Nothing committed changes before that. Research: R-24.

## Current state (measured at `ebbb786`)

| Piece | State |
|---|---|
| `revision.detect_revision` at stage, `will_be_revision`, `parent_committed_at` | live |
| Reason catalogue (`RevisionReasonCode`, `GET /revision-reasons`), `imports.revision_reason` storage, AI-run invalidation on a revision commit | live |
| Wizard revision UI (`DiffTable`, reason select, revision banner) | built; never reached, because dry-run never returns `is_revision: true` |
| `revision.compute_diff`, `revision.commit_revision` (update, soft delete, `race_result_revisions` rows, event lock) | implemented and tested; **called by no endpoint** |
| Revision commit today | `ingest_event`: adds `(event, category, competitor)` pairs that do not exist yet; nothing is updated or removed; `parent_import_id` is never set |

## Stage

`stage_extracted_results` calls `detect_revision(series, sequence_number)`.

- A committed parent with the same SHA-256 → `already_committed`, nothing is created (CLI exit 8).
- A committed parent with a different SHA-256 → the import is staged `pending` with `is_revision`, and the CLI prints `revisión de la importación #<parent>`.

## Dry-run, revision branch

`POST /{id}/dry-run` on a revision import returns the shape the wizard already renders (`ImportDryRunRevisionResponse` in `frontend/src/types/raceImports.types.ts`):

```json
{
  "parse_id": "…", "is_revision": true, "parent_event_id": 17,
  "diff_summary": {"n_create": 2, "n_update": 3, "n_delete": 1, "n_unchanged": 214, "n_total": 220},
  "diff_rows": [{"action": "update", "competitor_normalized_name": "…", "competitor_display_name": "…",
                 "category_code": "INF_A", "before": {"position": 4, "race_time_ms": 3723000, "points_awarded": 120, "status": "finished"},
                 "after":  {"position": 3, "race_time_ms": 3701000, "points_awarded": 130, "status": "finished"},
                 "result_id": 9812}],
  "warnings": []
}
```

- `diff_rows` omits `unchanged` rows by default, to keep the payload small; the summary counts them.
- The route stays coach/admin only, and names in `diff_rows` follow today's rules for the import wizard family (coach and admin only, never logged).
- The non-revision dry-run is unchanged.

## Identity-aware diff

`compute_diff` predates feature 044. It matches by `(category_code, normalized_name)` with a fuzzy fallback, which is wrong now that two competitors may share a name. It is changed to the following:

1. Resolve each row of the revision document to a competitor with the read-only path of `identity_resolver`: signature `(normalized_name, club_norm, city_norm)` plus the discriminator rules of R-06 §9–10. The result is the id of an existing competitor, or "new".
2. Match `(category_code, competitor_id)` against the committed, non-deleted results of the parent event:
   - a match with differing fields (`position`, `race_time_ms`, `points_awarded`, `status`) → `update`;
   - a match with no difference → `unchanged`;
   - no match (new competitor, or a known competitor in a category it did not have) → `create`;
   - a committed result that no row matches → `delete`.
3. The fuzzy `partial_ratio ≥ 92` fallback survives only for rows that resolve to "new". It proposes an `update` of a same-category result whose competitor is not matched by any other row, and the diff row carries `fuzzy_matched: true` so the coach can see it. A fuzzy candidate involving a club athlete is never auto-matched: the row stays `create`, and the identity gate raises it.
4. A competitor who moves category shows as `delete` in the old category plus `create` in the new one. That is honest, and the coach sees both lines.

## Commit, revision branch

`POST /{id}/commit` on a revision import:

1. `revision_reason` is **mandatory** (closed catalogue; `422` without it). Today's rule, "mandatory only when something is deleted", is widened, because the spec requires a reason for every revision.
2. The per-import identity gate (feature 045) runs as for any import, since new competitors of a revision are identity questions like any other.
3. **No partial revision.** If any category of the revision document is inconsistent and not acknowledged, the commit returns `409 {"detail": "revision_incomplete", "pending_categories": [...]}`. A revision applies as a whole or not at all.
4. The diff is recomputed server-side and never taken from the client, then applied with `commit_revision`:
   - pessimistic lock on the event (`SELECT … FOR UPDATE`, nowait 5 s → `409 event_locked`);
   - updates in place;
   - soft delete through `deleted_at`, never touching `status`;
   - creates through the same competitor resolution and signature writing as the ingestor, with frozen category label and age range (invariant 1);
   - one `race_result_revisions` row per change, with the user;
   - `parent_import_id`, `revision_reason`, `committed_at` and `committed_by_user_id` set on the import.
5. Athlete links are never overwritten (existing rule).
6. The staged document is deleted and `parse_meta_json` is set to `None`. The evidence file moves to `committed/`, as on a normal commit.
7. The existing AI invalidation runs (`invalidate_runs_for_event`), and nothing is re-run automatically.
8. Audit: `record_audit(execute, race_import)` with `meta.is_revision = true`, plus create, update and delete counts. No names.

## Reads exclude removed results

Every consumer already filters `race_results.deleted_at IS NULL`; 24 uses exist. A sweep test commits a revision that deletes one result and asserts that it disappears from:
- `history` (cross-season series)
- `field_metrics` / `compute_category_metrics` (field size, median, percentile)
- `standings`
- `results_read` (coach and family)
- the race-analyst context (`queries.py`)
- the season panorama
- the family results views

## Legacy partial commits (R-27)

A válida committed through the old upload with `pending_categories` cannot run `commit-pending` any more (`409 restage_required`). The operator re-stages the válida with the skill. The result is a revision whose diff creates the rows of the missing categories, and whose other rows come out `unchanged` if the reading matches.

## Tests

- `test_revision_diff_identity.py`:
  - two competitors with the same name in the same category (a homonym pair decided "different people") are diffed separately;
  - a surname correction resolves through the fuzzy fallback and is marked;
  - a club athlete's fuzzy candidate stays `create`;
  - a category move yields `delete` plus `create`.
- `test_race_imports_revision.py` (extended):
  - dry-run returns the revision shape;
  - commit without a reason returns 422;
  - commit applies update, create and delete, and writes `race_result_revisions` rows;
  - `parent_import_id` is set;
  - an athlete link survives;
  - AI runs are invalidated;
  - an identity-gate 409 on a revision with a new name;
  - `revision_incomplete` on an inconsistent category;
  - the event lock returns 409;
  - the staged document is deleted.
- `test_deleted_results_excluded.py`: the read sweep above.
- Frontend: `DiffConfirm.test.tsx` and `ImportWizard.test.tsx` start from `?import=<id>` with an MSW revision dry-run. They cover the diff table, the reason becoming required, and the commit payload carrying `revision_reason`.
