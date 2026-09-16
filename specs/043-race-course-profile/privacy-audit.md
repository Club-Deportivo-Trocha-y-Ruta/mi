# Privacy audit — Feature 043 (race course profile)

Task T063 (mandatory `data-privacy-guard` audit, per CLAUDE.md's "Subagents" workflow
convention and this feature's own tasks.md). Scope: the whole course package (7
implementation phases), auditing against the privacy invariants in
`specs/043-race-course-profile/data-model.md` §7 and Ley 1581/Ley 1098 (minors'
sensitive data).

Audit date: 2026-09-16.

**Overall verdict: APPROVED.** No blocking issue found. No code changes were required
or made. All backend/frontend evidence below was read from the working tree as of this
audit, not inferred from comments.

---

## 1. Raw GPX bytes are never persisted — PASS

Traced `process_gpx` end to end in `backend/app/services/race/course/gpx_processing.py`:

- The function takes `content: bytes` and returns a `ProcessedLap` dataclass
  (`geometry`, `lap_distance_m`, `elevation_gain_m`, `has_elevation`, `point_count`,
  `detection`) — no field carries the original bytes or a reference to them
  (`gpx_processing.py:86-96`).
- Step 3 (`_strip_and_flatten`, `gpx_processing.py:218-266`) explicitly deletes every
  non-geometry field (time, extensions, author, creator, copyright, routes,
  waypoints, per-point name/comment/description/source/link) and the caller does
  `del gpx` right after (`gpx_processing.py:153-155`) so the parsed document with any
  residual reference is dropped before any further processing step runs.
- The module docstring states the contract explicitly: "No hace I/O de ningún tipo
  (sin filesystem, sin red)" (`gpx_processing.py:11-12`) — verified true: there is no
  `open(`, no `write`, no HTTP client, no SFTP/S3 call anywhere in the file (grepped).
- In `backend/app/services/race/course/service.py`, `create_variant` and
  `replace_variant_file` take `content: bytes` and `filename: str`, immediately do
  `del filename  # nunca se persiste ni se loguea` (`service.py:443`, `service.py:497`),
  pass `content` only into `process_gpx(...)` and `hashlib.sha256(content).hexdigest()`
  (`service.py:449-450`, `service.py:501-502`) to compute a dedupe fingerprint, and
  never assign `content`/`raw` to any model field. The `RaceCourseVariant` model
  (`data-model.md` §1) has no BLOB/bytes column — only `geometry` (JSON of rounded
  lat/lon/ele triples), scalar figures, and `source_sha256` (the SHA-256 digest, not
  retrievable back to bytes, used solely to answer "you already uploaded this file"
  with a 409).
- Router-level (`backend/app/routers/race_events.py:1068-1111`,
  `_read_and_validate_course_gpx_upload`) reads the upload into memory (`raw =
  await file.read(...)`), performs magic-byte/size checks, and returns the bytes to
  the caller (`create_race_event_course_variant`, `replace_race_event_course_variant_file`)
  which immediately forwards them into `course_svc.create_variant`/
  `replace_variant_file` above — no filesystem write, no SFTP/S3 upload anywhere in
  this router (grepped for `sftp|SFTP|S3|write_bytes|open(.*wb` in
  `app/services/race/course/` — no matches; the project's Hostinger SFTP media path
  belongs to a completely different subsystem, uploaded photos/documents, and is
  never invoked from this feature).

Evidence of no matches: grep for `sftp|S3|upload_file|write_bytes|open(.*wb|save(`
across `backend/app/services/race/course/` returned nothing.

## 2. `course_notes` never reaches an AI prompt — PASS

Traced `fetch_course_context` (`backend/app/services/race/queries.py:329-419`) end to
end to `format_course_meta` (`backend/app/services/race/agents/analyst.py:534-595`)
and into both v3 prompts:

- `fetch_course_context`'s only course-specific SQL statement is
  `select(RaceCourseCategorySetup, RaceCourseVariant).join(...)` filtered by
  `category_id` and `race_event_id.in_(event_ids)` (`queries.py:392-398`). Neither
  `race_course_category_setups` nor `race_course_variants` has a `course_notes`
  column (that field lives on `race_events`, see data-model.md §3) — there is
  structurally no `course_notes` value this query could return.
- The dict it builds per válida (`queries.py:410-417`) is a fixed 6-key literal:
  `lap_distance_m`, `elevation_gain_m`, `laps`, `terrain_type`,
  `technical_difficulty`, `key_sectors` — `course_notes` is not one of the keys, and
  the code never does `**vars(event)` or similar that could smuggle it in.
- `format_course_meta` (`analyst.py:548-566`) reads exactly those 6 keys via
  `course.get(...)` and returns `None` (triggering the prompt's "SIN DATO" veto
  branch) when none are present. There is no code path in this function that touches
  `course_notes`.
- `_course_meta_for_valida` / `_build_v3_inputs` in
  `backend/app/services/race/ai/nodes/analyst_agent.py:485-538` only ever read
  `state["course_context"]` (populated exclusively by `fetch_course_context`, see
  `backend/app/services/race/ai/nodes/load_race_data.py:353-409`) and pass the
  `format_course_meta`-produced markdown string into `AnalystV3Input.course_meta` /
  `course_by_valida`. No other state key or object feeds the course block.
- The two prompt templates (`backend/app/services/race/prompts/race_analyst_v3.md:100-110`
  and `race_season_summary_v3.md:116-130`) render only `{{ course_block }}` /
  `{{ block }}` (the `format_course_meta` output) inside the `{% if course_block %}`
  branch, with an explicit `PROHIBIDO mencionar distancia, vueltas, terreno, desnivel,
  altimetría o dificultad técnica` veto line in the `else` branch. Grepped both prompt
  files for `course_notes` — zero occurrences.
- This is independently covered by existing automated tests
  (`backend/tests/services/race/ai/test_course_block.py`), including a dedicated
  privacy test that seeds a synthetic (fictional, never a real minor)
  forbidden-name string inside `course_notes` and asserts it is absent from both the
  returned dict and its string representation
  (`test_fetch_course_context_never_exposes_course_notes_key`, lines 296-316). Ran
  this suite: **17/17 passed** (see Verification section).

## 3. No coordinate/elevation/GPX data is logged — PASS

Grepped every `logger.*`/`logging.*`/`print(` call reachable from this feature:

- `backend/app/services/race/course/service.py:471-479` and `523-531`
  (`create_variant`, `replace_variant_file`) — the only two log lines this feature
  adds. Both are:
  ```
  logger.info(
      "race_course_variant_processed race_event_id=%s variant_id=%s "
      "point_count=%s lap_distance_m=%s detection_method=%s",
      race_event_id, variant.id, variant.point_count, variant.lap_distance_m,
      variant.detection_method,
  )
  ```
  Fields logged: `race_event_id` (int id), `variant_id` (int id), `point_count`
  (int), `lap_distance_m` (int), `detection_method` (one of three fixed enum-like
  strings: `closed_loop`/`manual`/`single`). No geometry, no filename, no raw bytes,
  no coordinates.
- `backend/app/routers/race_events.py` has no additional `logger.*` call inside the
  course route handlers (grepped all `logger.info`/`logger.debug` line numbers in the
  file — none fall inside the `1114-1455` course-routes block); attribution instead
  goes through `record_audit(..., changed_fields=[f"course_variant:{id}"])`
  (`race_events.py:1204-1214`, `1268-1271`, `1310-1313`, `1346-1349`, `1386-1389`,
  `1449-1452`) — `record_audit` (`backend/app/services/audit.py:551`) only persists
  the `changed_fields` label strings passed to it, never a value/diff for this
  feature's calls, so no geometry ever reaches the audit trail either.
- `CourseProcessingError` (raised by `process_gpx` on any malformed/rejected upload)
  carries only a `code` string (`gpx_processing.py:59-71`); the router's
  `_course_processing_error_to_http` (`race_events.py:1058-1065`) maps that code to a
  fixed Spanish message table and never logs the exception or the uploaded bytes.
- The app's single global exception handler (`backend/app/main.py:136-148`) logs only
  `method`, `path`, and `type(exc).__name__` on an unhandled exception — never the
  request body, so even a code path that raised an unexpected exception during GPX
  processing could not leak geometry through this handler.
- Frontend: grepped `console.*` across all of
  `frontend/src/components/race/course/*.tsx` and both parent pages — zero matches.

## 4. Parents only ever see their own athletes' data — PASS

- Router: `GET /{race_event_id}/course` (`race_events.py:1114-1154`) is reachable by
  `admin`, `coach`, and `parent` (`require_role([UserRole.admin, UserRole.coach,
  UserRole.parent])`), and immediately calls the project's single centralized gate,
  `allowed_athlete_ids_for(current_user, db)` (`app/services/permissions.py:25-48`),
  which returns `None` for admin/coach (unrestricted) and the parent's own athlete-id
  set for `parent` — the same helper already used by the pre-existing
  `/results`/`/standings` endpoints (`race_events.py:160`, `222`), so this feature
  reuses an audited, single source of truth rather than adding a parallel scoping
  rule.
- `course_svc.get_course(db, race_event_id, allowed_athlete_ids=scoped)`
  (`service.py:390-422`) branches on `allowed_athlete_ids is not None` into
  `_get_course_for_parent` (`service.py:345-387`), which:
  - derives `my_categories` **only** from `RaceResult` rows filtered by
    `RaceResult.athlete_id.in_(allowed_athlete_ids)` (`service.py:304-325`) — never
    from the roster table (which has no `category_id`, so it cannot be used to
    fabricate a category for someone else's child either);
  - gates visibility (200 vs 404 `course_not_available`) on
    `bool(my_categories) or await _has_roster_visibility(...)`, where
    `_has_roster_visibility` also filters by
    `RaceEventRoster.athlete_id.in_(allowed_athlete_ids)` (`service.py:328-343`);
  - always forces `suggested_setups=[]` and never includes a `results` key
    (`service.py:379-387`).
  - An empty `allowed_athlete_ids` (parent with no linked athletes) short-circuits
    both helpers to `[]`/`False` (`service.py:310-311`, `334-335`), so such a parent
    always gets 404, never a 500 or a partially-filled body.
- `variants`, `setups`, and `description` returned to a parent are **not**
  filtered per-athlete (a coach-registered circuit/lap-table is válida-level, not
  athlete-level, data, so this is by design, not a leak) — but nothing
  athlete-identifying (name, id) appears in those three fields; the only
  athlete-identifying field in the whole `CourseRead` schema is `my_categories`,
  which is scoped as above.
- This exact set of guarantees is independently exercised by
  `backend/tests/routers/test_race_course.py::TestParentRead` (lines 1123-1246),
  including `test_response_never_leaks_other_athletes_or_results_key`
  (lines 1195-1220), which JSON-dumps the whole parent response and asserts that
  three *other* families' athlete ids (9401/9402/9405) never appear anywhere in the
  raw payload, and that the response's key set is exactly the public `CourseRead`
  shape (no stray `results` key). Ran this class: **passing** (see Verification).
- Frontend wiring: both `ParentCompetitionResultsPage.tsx` (line 256) and
  `ParentEventDetailPage.tsx` (line 138) call `useRaceCourse(raceEventId)`, which
  hits the same server-scoped `GET /course` — there is no client-side merge with
  another family's data. The one piece of frontend-side name resolution,
  `athleteNamesFromRaceData` (`ParentCompetitionResultsPage.tsx:59-75`), builds its
  `athleteNamesById` map from the *already family-scoped* `/results`/`/standings`
  responses (those endpoints apply the identical `allowed_athlete_ids_for` gate —
  confirmed at `race_events.py:160-168` and `222-230`), so it can only ever contain
  the calling parent's own children.

## 5. Structural exclusion of `course_notes` at the SQL level — PASS, with one documented nuance (non-blocking)

Re-derived this myself rather than trusting the docstring, by reading the actual
statements and — separately — by spying on `db.execute` in a test.

- The dedicated, feature-043-specific query inside `fetch_course_context`
  (`queries.py:392-398`) is a `select(RaceCourseCategorySetup, RaceCourseVariant)`
  join. Neither table has a `course_notes` column (confirmed against the models:
  `app/models/race_course_category_setup.py`, `app/models/race_course_variant.py`,
  and data-model.md §1-2). **This half of the guarantee is true at the SQL level**:
  the extra query this feature adds cannot select a column that does not exist on
  either joined table.
- The nuance: `fetch_course_context` resolves `terrain_type` /
  `technical_difficulty` / `key_sectors` from the **already-cached** `RaceEvent`
  ORM objects returned by `load_events(db)` (`queries.py:63-65`,
  `select(RaceEvent)` with no column restriction — a full-row select). `RaceEvent`
  *does* have a `course_notes` column (data-model.md §3), so that column **is**
  fetched over the wire by this `SELECT` — it is excluded only by the Python code
  in `fetch_course_context` never reading `event.course_notes` into the output
  dict (`queries.py:404-417` reads only `terrain_type`, `technical_difficulty`,
  `key_sectors` off `event`). `load_events` is a shared primitive used by several
  other callers (analytics, event conditions) for unrelated columns, so this is the
  same pre-existing pattern the codebase already uses for `weather_notes` on the
  same table, not something new introduced by course profile.
  Consequence in practice: `course_notes` text is briefly present in backend
  process memory as an attribute of an ORM object also used for other purposes, but
  it is never serialized into the `course_context` dict, never reaches
  `format_course_meta`, never reaches a prompt, and never reaches a log line or the
  audit trail (confirmed in points 2-3 above) — so there is no exposure outside the
  backend process, and no Ley 1581 violation. I am flagging it only because the
  audit brief specifically asked me to verify the "SQL level" claim rather than trust
  it, and a literal reading of "never SELECTed" is not quite accurate for the
  `RaceEvent` row (only for the two new course tables). Judgment call: **not
  blocking** — fixing it would mean special-casing `load_events`'s column set (used
  by ~5 other call sites) purely for defense-in-depth on a value that already never
  leaves application memory, which is a larger, riskier change than this task's
  scope, and the project's own test suite already documents and accepts this exact
  tradeoff.
- This exact distinction is already known and tested by the team itself:
  `backend/tests/services/race/ai/test_course_block.py::test_fetch_course_context_course_table_queries_never_select_course_notes`
  (lines 319-382) spies on `db.execute`, compiles every statement whose SQL touches
  `race_course_category_setups`/`race_course_variants`, and asserts
  `"course_notes" not in compiled` for each — i.e., it tests exactly the same
  SQL-level claim I re-derived, and its own docstring (lines 322-338) explicitly
  states the same nuance about `load_events`/`RaceEvent` that I found. I ran this
  test standalone to confirm it currently passes (see Verification) rather than
  taking the docstring's word for it.
- Two further dict-level tests reinforce this from a different angle:
  `test_fetch_course_context_never_exposes_course_notes_key` (a synthetic
  forbidden-name string inside `course_notes` never appears in the returned dict or
  its `str()`) and the general-shape assertion `assert set(result[1].keys()) ==
  expected_keys` (line 289) which would fail immediately if `course_notes` were ever
  added to the output dict.

---

## Verification

No blocking issue was found, so **no code was modified** for this audit. The
following existing test suites were run to confirm the codebase already satisfies
the five invariants above (before-state only; nothing needed a re-run):

```bash
# Backend — course package + router + AI course-context/prompt wiring
cd backend && source .venv/bin/activate
python -m pytest tests/services/race/test_gpx_processing.py \
                  tests/services/race/ai/test_course_block.py \
                  tests/routers/test_race_course.py -q
# → 73 passed, 6 warnings (unrelated Starlette deprecation warnings) in 4.68s

python -m pytest tests/services/race/ai/ -k course -q
# → 17 passed, 387 deselected in 0.80s
```

```bash
# Frontend — parent-facing course components + both parent pages
cd frontend
npx vitest run src/components/race/course/__tests__/CourseSummary.test.tsx \
                src/components/race/course/__tests__/CourseMap.test.tsx \
                src/components/race/course/__tests__/ElevationProfile.test.tsx
# → 3 files, 30 tests passed

npx vitest run src/routes/parents/competitions/ParentCompetitionResultsPage.test.tsx \
                src/routes/parents/calendar/ParentEventDetailPage.test.tsx
# → 2 files, 33 tests passed
```

`ruff check` was not run against any backend file because none was modified in this
audit.

---

## Non-blocking observations (worth knowing, not a Ley 1581 violation)

1. **Point 5's `load_events` nuance** (above) — `course_notes` is fetched over SQL as
   part of the full `RaceEvent` row inside `fetch_course_context`'s reused
   `load_events()` call, even though it is never read into the output. Consistent
   with the pre-existing `weather_notes` pattern on the same table/loader. No action
   taken; documented for whoever next touches `load_events` or adds a new free-text
   column to `race_events`.
2. `CourseMap.tsx` (`frontend/src/components/race/course/CourseMap.tsx:42-45`) points
   Leaflet's marker icon assets at `unpkg.com` — the same pattern already used by the
   pre-existing `training/RouteViewer.tsx`. Those requests carry no course/athlete
   data (static icon images only), so this is not a privacy issue, just noted for
   completeness since it's a third-party network call from a parent-facing page.
3. `CourseMap.tsx` also loads OpenStreetMap tiles directly from
   `{s}.tile.openstreetmap.org` from the browser. Tile requests reveal the
   *approximate bounding box of a public race venue* (not an athlete's location) to
   OSM's tile servers/CDN — a pre-existing pattern in this codebase for other route
   maps, not something new to gate on for this audit, and not personal data of a
   minor.
4. `race_course_variants.source_sha256` (data-model.md §1) is a SHA-256 of the
   discarded upload, kept solely for duplicate-detection. This is a one-way digest of
   ephemeral bytes, not a way to reconstruct the original GPX, and the data model
   already documents this precisely ("never used to retrieve anything because nothing
   is retained").

## Summary of verdicts

| # | Check | Verdict |
|---|-------|---------|
| 1 | Raw GPX bytes never persisted | PASS |
| 2 | `course_notes` never reaches an AI prompt | PASS |
| 3 | No coordinate/elevation/GPX data logged | PASS |
| 4 | Parents only see their own athletes' data | PASS |
| 5 | Structural exclusion holds at the SQL level | PASS (one documented, non-blocking nuance re: `load_events`) |

**Status: APPROVED**
