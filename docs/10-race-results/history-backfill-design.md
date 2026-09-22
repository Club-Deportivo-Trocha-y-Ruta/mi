# Race History Backfill — Technical Design

Companion to `docs/10-race-results/upload-design.md` (Phase 1.7, the original import
pipeline) and `course-profile-design.md` (feature 043). This document covers what feature
044 (`specs/044-race-history-backfill/`) adds so that the Copa Valle 2024 and 2025 seasons
can be loaded through the same import path and give each club athlete one continuous
progression across 2024–2026. It does not repeat what those two documents already state.

**Status at the time of writing (2026-09-22, third and final update this same day)**:
implemented on branch `feat/044-race-history-backfill`, not deployed, no real historical
file loaded. See `docs/implementation-status.md`'s Feature 044 entry for the phase-by-phase
state and `docs/technical-notes.md` for the dated changelog. All seven user stories are
implemented and closed — US6 and US7 both passed their story gates (G6, §7). Verified
against real infrastructure, all the same day: `pytest -m mysql` (§4.5, 33 passed, one real
migration bug and one real test bug found and fixed) and Playwright end-to-end (§4.6, 1
passed, four real bugs found and fixed getting there). The mandatory full-feature
`data-privacy-guard` audit (T090, §5) is **done**: APROBADO CON CONDICIONES, 0 critical/high
findings, 3 non-blocking MEDIUM findings closed or explicitly tracked, reviewed and
confirmed by the data-privacy lead (T091). What remains between this document and a real
load is deploy and its owner-only steps (§9 below covers legal basis; `runbook-ops.md` §12
covers the operational sequence) — nothing in the feature's own implementation or its
mandatory audit is still open.

## 1. Why reading had to change first

Planning measured the historical files (three official PDFs inspected outside the repo and
deleted, counts only — see `research.md` R-01) and found the platform's stated first
hypothesis wrong. Rows are not lost to wrapped text; a long `Club/Patrocinador` value is not
clipped to its column, overflows to the right and prints **over** the `Tiempo` column.
`page.extract_text()` orders characters by x position, so the club's trailing letters
interleave with the time digits and the row regex fails silently — a loss of 16–25 % of
every file, spread across categories, including category winners.

`app/services/race/pdf_parser.py` now reads each row **band-first, in content-stream
order**:

1. `page.find_tables()` gives one bbox per table row — reliable for row boundaries (every
   row carries a numeric ordinal and bib in cells 0–1) but not for the club/time/points
   column boundaries, since an overflowing club leaves fragments in cells 5–6.
2. For each row band, `page.chars` inside the band are read in the order the PDF's content
   stream wrote them — never re-sorted by x. A space is inserted when the gap to the
   previous character exceeds 1 pt or x jumps backwards (the start of the next cell's run).
   The club and time runs stay contiguous and clean in stream order even when they overlap
   visually on the page.
3. A relaxed row regex matches the rebuilt string: time is `(?<![\d:])\d:\d{2}:\d{2}`
   (single-digit hour, since XCO races run under 10 h, so a club ending in a digit cannot
   swallow the hour), whitespace before the time is optional, status tokens
   (`DNF`/`DSQ`/`DNS`/`-N VUELTA(S)`) are unchanged, the trailing integer is points.
4. A band matching only `pos bib body points` is kept as **classified without time**
   (`time_raw=""`) rather than dropped — the official files do carry rows like this.
5. A band matching nothing is returned as an **unreadable row** with its page and ordinal,
   surfaced to the coach in the preview (FR-001). Zero such rows in the sample.
6. `name` / `city` / `club` are assigned from text runs inside the band by **starting x**,
   not from `table.extract()` cells. This was corrected mid-implementation: cell text
   truncates on an overflowing row exactly like the time did (a city such as `SANTANDER DE
   QUILICHAO` arrives as `SANTANDER DE`), and prefix-based reconstruction only aligned 168 of
   229 rows on the worst real file measured. What holds instead: a text run always starts
   inside its own column's horizontal range even when the previous cell overflowed onto it —
   overflow travels right and never moves the next run's start. Measured 229 of 229 rows
   assigned correctly, zero fallbacks. A run starting outside every known column yields
   `None` rather than an invented value.
7. Category headers are matched to row bands by vertical position on the page, replacing the
   previous line-order walk; the rule that a category persists across a page break is kept.

The text-line path from before this feature is kept as a fallback for a page where
`find_tables` returns nothing (none in the sample) and as a cross-check: a row found by one
path and not the other raises a `row_path_mismatch` warning rather than silently picking one.

**Why this matters beyond parsing.** `club` and `city` are two of the three components of
the identity signature (§3). A truncated club produces a different signature for the same
rider between válidas, and the amount truncated depends on how far the text overflowed — so
the same person could have been split into two competitors before the identity review even
saw them. The band reader's run-position fix is what makes §3 trustworthy at all.

Measured recovery: 282/277/280 rows across the three sample files, zero unparsed, versus
214/232/211 read by the previous line-order parser (24 %, 16 %, 25 % lost). The fix also
recovered **2 real rows the 2026 official fixture was silently losing** (`PREINFANTIL B`
position 17, `MASTER B1` position 5) — the FR-007 regression oracle in
`tests/services/race/test_parser.py` was corrected from 227 to 229 expected rows, with a new
per-category completeness regression test guarding it.

## 2. Category vocabulary across seasons

Distinct printed headers per season (research R-03): 2024 has 25, 2025 has 23, 2026 has 26.
Two different kinds of divergence from the 2026 catalogue exist, and they are handled
differently:

- **Renames** — the same group under a different label. Added as season-agnostic aliases to
  `normalizer.HEADER_TO_CODE` (unambiguous in every season; 2025 itself mixes both
  spellings for the same category): `elite hombres→ELITE_M`, `elite damas→ELITE_F`,
  `junior damas→JUN_F`, `master damas→MAS_F`, `infantil a ninas→INF_A_F`,
  `infantil b ninas→INF_B_F`, `prejuvenil a damas→PJUV_A_F`, `prejuvenil b damas→PJUV_B_F`.
- **Structural differences** — a group that was later subdivided, merged or that has no
  current equivalent. Three new `race_categories` rows, seeded with `is_active=false` so no
  current-season selector offers them: `MAS_B_2025`, `MAS_C_2025` (2025 printed masters as
  two groups where 2024 and 2026 print four) and `PRE_F_U` (both historical seasons printed
  a single undivided pre-infantile girls' group where 2026 splits it into A and B).

A header the parser does not recognise is never dropped: it comes back as an
`UnknownCategory(header_raw, rows)`, listed in the preview with its row count, and its
commit is blocked until a mapping exists — a code change to the alias dict, by design, since
the catalogue is closed. Every category in a preview carries `header_raw`, the resolved
`code`, and `mapping_kind ∈ {exact, rename, season_specific, unknown}` (FR-011).

**Frozen labels.** `race_results` gained three nullable columns —
`category_label_raw VARCHAR(100)`, `category_age_min_raw`, `category_age_max_raw
SMALLINT` — written once by the ingestor at insert time from the resolved catalogue row and
never updated afterwards, not even by the revision flow (which inserts new rows rather than
editing). A later catalogue edit (a relabel, a widened age range) never rewrites what a past
result meant. The migration backfilled every existing 2026 result from its current catalogue
category so every read path can prefer the frozen label unconditionally.

## 3. Completeness, correction, acknowledgement, partial commit

The official files themselves are not clean: a duplicated ordinal (`… 19, 20, 20, 21 …`) in
one children's category of **both** 2025 files inspected, and a missing ordinal in another.
The "official results contain no ties" assumption in the original spec draft was wrong; the
acknowledgement path is a necessity, not a corner case.

`app/services/race/completeness.py::check_completeness(ordinals) -> CompletenessReport`
checks that a category's printed ordinals form the sequence 1…N with no gaps or duplicates,
over every printed ordinal (lapped riders included). A category that fails is marked
inconsistent, naming the missing or duplicated positions, and its commit is blocked; the
other categories of the same válida are not held back.

Because parsed rows are re-derived from the stored file on every dry-run/commit, manual
corrections are persisted as an ordered list of row patches (`add | edit | remove`) in
`race_imports.parse_meta_json["corrections"]`, applied after parsing and before the
completeness check. A gap that genuinely exists in the source is acknowledged through a
**closed catalogue of reason codes** — `source_duplicate_ordinal`, `source_missing_ordinal`,
`source_disqualification_gap`, `verified_against_source` — rather than free text, following
the precedent of `RevisionReasonCode`: free text about a results sheet of minors invites
names. Stored in `parse_meta_json["acknowledged"]` with author and time, written through
`record_audit`.

**Partial commit, no new enum value.** `commit` ingests the consistent-or-acknowledged
categories, marks the import `committed`, and records `parse_meta_json["pending_categories"]`.
`POST /race-imports/{id}/commit-pending` re-runs the ingest restricted to categories that
have since become consistent, reusing the ingestor's existing `(event, category, competitor)`
idempotence and bypassing the SHA-256 short-circuit only for this restricted re-run.

Corrections and acknowledgements live only in the database, at the same sensitivity class as
`race_competitors` — never in a log line.

## 4. Identity across three seasons

`race_competitors.normalized_name` was globally `UNIQUE`; with the full start list the name
collision stops being an edge case and becomes routine (several hundred third-party riders
across three seasons). The unique constraint is dropped in favour of an explicit,
coach-decided review.

### 4.1 Signatures

`race_competitor_signatures` (new table) is the observed `(normalized_name, club_norm,
city_norm, discriminator)` a competitor has been printed under, each owned by exactly one
competitor, `UNIQUE` on the quadruple — the persistence that lets the platform remember a
decision and keep homonyms apart on a later load. `race_competitors` gains `city_text
VARCHAR(100) NULL`, disambiguation only (FR-014): never serialised outside the
identity-review schemas.

The `discriminator` column (revision `a7c3e5d91f20`, owner decision 2026-09-21 —
"separar por categoría") exists because a triple alone cannot tell a parent and child of
the same club apart, the realistic case of two different people sharing name, club **and**
city. Default `''` for a signature that needs no tie-break; otherwise
`"<sex>:<age_min>-<age_max>@<season>"`, taken from the catalogue row of the category so a
rename never changes it. Two rows for the same triple are grouped into compatible-category
clusters (season order, `AGE_TOLERANCE_YEARS = 1` on each side, since category cut-offs are
by birth year); two or more clusters become separate homonym candidates. A competitor with
several signatures does not have its already-committed results split retroactively — only
its still-staged rows are — which is a recorded limit, not a bug (§8).

### 4.2 Candidates and decisions

`race_identity_candidates` (new table) is both the review queue and the decision audit:
`kind` (`same_person_suspect | homonym_suspect`), two record snapshots (name as printed,
club, city, seasons, category codes, competitor id and `athlete_linked` when applicable),
`score` (0–100), `signals` (e.g. `["extra_surname"]`, `["club_and_city_differ"]`), `state`
(`pending | same_person | different_people`), `linked_athlete_involved`, decider and
timestamps, plus reversal stamps. `UNIQUE(pair_hash)` — a SHA-256 of the two ordered record
keys — makes a rebuild idempotent and "never ask again" structural rather than a promise.

`app/services/race/identity_review.py::build_candidates`, over all staged historical imports
plus existing competitors:

- **same-person suspects**: different normalised names with
  `rapidfuzz.fuzz.token_set_ratio ≥ SAME_PERSON_MIN_SCORE` (90), compatible sex, a category
  path that never moves to a younger age group in a later season; blocked by a shared
  surname token so the comparison stays far below n².
- **homonym suspects**: identical normalised name with any of — presence in two categories
  of the same válida; incompatible sex; an age path moving backwards; club **and** city both
  different (fuzzy `< DIVERGENCE_MAX_SCORE`, 70). A changed club alone is never a signal by
  itself — children change clubs — it only adds a new signature.

Nothing merges automatically (FR-017): `app/services/race/identity_resolver.py`'s
`IdentityResolver` attaches an exact signature match to its owning competitor; attaches a
row to an existing competitor by name alone only when there is a single match and no homonym
signal; otherwise a decision must already exist, or the ingest of that row is impossible by
construction — which is why the commit gate exists.

### 4.3 Commit gate

`commit` and `commit-pending` on `POST /race-imports/{id}/…` return `409
identity_review_pending` with the pending count while any candidate is `pending`
(FR-018). The gate runs a rebuild first, so a stale review queue can never let a commit
through. Wave 5's own gate check (G5, 2026-09-22) found and fixed one hole in this: a
partially committed import kept its still-pending categories **out** of the identity
universe entirely, so a homonym between those rows and a later file could reach
`commit-pending` unreviewed — `load_universe` and `load_identity_rows` now include the
pending categories of a partially committed import too, with a regression test.

Reversal (`POST /candidates/{id}/reverse`) returns a `same_person` decision to `pending` and
splits the competitor back using the exact signature the decision attached (results carry
`imported_from_id` and the signature's seasons, so the split set is exact); if the
competitor was linked to an athlete, the split-off side is left unlinked and `athlete_id` is
cleared on its results. Every decision and reversal is audited via `record_audit`.

The ingestor persists `athlete_id` on a new result whenever the resolved competitor is
linked, regardless of the row's own club — a real bug fixed as part of this feature: before
044, `athlete_id` was only persisted when the *row's* club matched the club's own, which
would have left a pre-club historical result of an already-linked competitor unattached.

### 4.4 Rebuild cost — the parsed-rows cache

A rebuild's candidate-building core is cheap (0.22 s / 0.09 s idempotent re-run on 3 000
synthetic names, measured G4 2026-09-21 — see `plan.md` Complexity Tracking). What is not
cheap is `load_identity_rows`, which in production re-downloads and re-parses every staged
PDF over SFTP on every `/rebuild` **and** every commit-gate check — 0.60 s per 229-row file
measured locally, so a 15-file historical stage cost ≈ 9 s of parsing alone before
mitigation, plausibly over the 10 s route budget on Render's free tier.

Mitigation, implemented and re-measured the same day: two process-local bounded LRUs in
`routers/race_imports.py` (comment above `_reload_results_document`) — the raw parse keyed
by `sha256` (a committed import's file never changes, so this entry never invalidates) and
the corrected-categories result keyed by `(sha256, len(corrections))` (a new correction
changes the key; the stale entry is simply never requested again). Re-measured against 15
real staged imports through the actual download-and-parse path: first `rebuild` 1.513 s,
second (same corrections revision) 0.002 s — a ≈750× reduction. The "stage in batches of ≤
5" workaround `runbook-ops.md` §12 would otherwise have needed is no longer necessary.

### 4.5 MySQL verification and a real migration bug (T086, 2026-09-22)

`alembic upgrade head` → `downgrade c2314ccd7927` → `upgrade head` ran clean on a throwaway
MySQL 8.4 container (`_test` database, isolated from production) — but not on the first try.
The original `downgrade()` of `8efe1618cb83` called `drop_index` on
`ix_race_competitor_signatures_competitor_id` before `drop_table` on
`race_competitor_signatures`. MySQL refuses that order (error 1553) because the index backs
a foreign key, and since MySQL DDL is not transactional, the failure left the schema
half-reverted rather than rolling back cleanly. Fixed by removing the explicit `drop_index`
calls for that table's own indexes — `DROP TABLE` already takes its indexes with it, in both
directions of the migration. Upgrade of both revisions on an empty database: 4.2 s wall.
`tests/test_audit_mysql.py`'s `CURRENT_HEAD` constant was bumped to `a7c3e5d91f20` to match.
`backend/tests/mysql/test_race_history_models.py` (T085 — the signature triple with empty
strings, the dropped unique + plain index, the three frozen columns round-trip, both new
enums' stored values) collects and skips cleanly without `TEST_DATABASE_URL` and was not
itself run against this container in the same pass; the migration round-trip above is the
real-MySQL evidence for this section.

**Update, 2026-09-22 (final pass)**: T085 *was* run for real, against the same container,
later the same day — full `-m mysql` lane, `33 passed`. One more real MySQL-only bug turned
up: `test_signature_server_default_lands_as_empty_string_not_null`'s raw `INSERT` omitted
`created_at`/`updated_at` — those two columns rely on a Python-side ORM default, not a
`server_default`, unlike `club_norm`/`city_norm`/`discriminator` on the same table, which do
declare one — and MySQL's strict mode rejected the missing-column insert with error 1364.
Fixed with an explicit `UTC_TIMESTAMP()` in the test's raw SQL.

### 4.6 End-to-end verification and four real Playwright bugs (T087, 2026-09-22)

`frontend/e2e/race-history.spec.ts` (with a companion fixture generator,
`backend/scripts/generate_e2e_race_history_fixtures.py`) covers the whole path in one run:
stage two synthetic files → correct a gap → decide identity → commit → coach series with a
category-change marker → parent view with zero third-party strings. Once Docker became
available mid-implementation, it ran for real against a dedicated `docker-compose.e2e.yml`
stack: `1 passed (6.9s)`.

Getting it green surfaced four real bugs, not spec-writing artifacts — each is also
documented in the spec file's own comments:

- A successful commit navigates straight out of the import wizard, so a "step 3, success"
  DOM state is never actually observable — the spec had to assert on the post-navigation
  state instead.
- The commit-confirm button can render `enabled` before `matchesData` has finished
  resolving, so a click that lands in that window is a silent no-op
  (`submitCommit`'s own `if (!matchesData) return`) — fixed by waiting for `toBeEnabled`
  before clicking, not just for the button to exist.
- A Playwright coordinate-based click, even with `force: true`, can land on an unrelated
  `sonner` toast stacked visually over the intended button rather than the button itself —
  fixed by switching every wizard/identity-review/board action to a native
  `.evaluate(el => el.click())` DOM click, which ignores stacking order.
- The app session lives in `sessionStorage`, not cookies — switching from the coach login to
  the parent login inside the same test needs `sessionStorage.clear()`, not
  Playwright's `clearCookies()`, or the coach session survives the "login as parent" step.

**Operational gotcha for whoever reruns this spec**: re-running against the same seeded
stack hits the SHA-256 commit-dedupe guard on the very first file — it reports "ya fue
commiteado" against data left over from the previous run. The stack needs `docker compose
-f docker-compose.e2e.yml down -v` (the `-v` matters — a plain `down` keeps the volume) and
a fresh `up` between runs; now noted in the spec's own header comment.

## 5. Third-party progression lock

Loading the full start list of fifteen válidas brings several hundred non-club riders, most
of them minors, into the platform. The legal basis for holding their results is legitimate
interest limited to situating the club's own athletes (§10); the guarantee that a third
party can never be profiled over time had to exist **before** the data did.

`app/services/race/third_party_guard.py::require_club_competitor(db, competitor_id) -> int`
returns the linked `athlete_id` or raises `ThirdPartyProgressionForbidden`, mapped to a
`403` with the public code `third_party_progression_forbidden` at the app-level exception
handler (deliberately not per-router, so any future router is covered). An unknown
`competitor_id`, a missing one, and one that exists but is not linked all produce the exact
same response body — only the internal `reason` differs, and it never leaves the server log.

A **structural test** (`tests/privacy/test_third_party_lock.py`) walks
`app/services/race/*` and fails unless every public callable with a `competitor_id`
parameter is either marked `@club_competitor_only` or on a short, individually-justified
allow-list (`field_metrics.compute_field_metrics`, the three `competitor_linking` functions,
`require_club_competitor` itself). Extended during US4 (gate G4, 2026-09-21) to also index
`competitor_ids: list[int]` and public methods, closing a gap the T036 audit flagged in
advance: the identity review works over sets of competitors, a shape the original scan could
not see. This lock shipped and went green **before** any historical commit task, per the
hard ordering rule in `tasks.md` (Phase 5 before Phase 7's commit tasks).

One condition from the T036 audit (scoped narrowly to the lock itself, dated 2026-09-18, not
a full-feature audit) is recorded as closed by gate G3: `ThirdPartyProgressionForbidden`'s
message no longer reaches `agent_run_events` via the AI node's error-event wrapper — see
`specs/044-race-history-backfill/privacy-audit.md` §1 for the finding and the fix.

**The mandatory full-feature audit (T090) is now done too (2026-09-22, `privacy-audit.md`
§2)** — split into five independent sub-reviews (parser/staging, identity, history/lock,
frontend, migrations/fixtures/docs), each running its own tests rather than trusting the
others' summaries. Verdict: **APROBADO CON CONDICIONES**, 0 critical/high findings across
all five slices, 3 non-blocking MEDIUM ones, all closed or explicitly tracked by the lead's
review (§3 of the same file, T091): the two process-local parse caches in `race_imports.py`
hold unfiltered minors' PII with no access control of their own beyond the router's
`require_role([admin, coach])` on all six call sites (now documented, not fixed — the
existing RBAC perimeter is judged sufficient); a docstring overclaiming `IdentityRecordRead`
as the platform's *only* schema serialising `city` (it isn't — `race_imports.py`'s own
`ParsedResultsRowRead`/`ResultsRowIn` also do, under identical RBAC) was fixed the same day;
and a "list of competitor ids" lock extension a commit message and the structural-scan test
both reference has no matching runtime primitive today (`require_club_competitors` doesn't
exist) — noted in `third_party_guard.py` so a future change doesn't assume it does. FR-043's
deferred items (§10) were also written down with an owner each in this pass: third-party
erasure and source-file/`parse_meta_json` retention to the club owner before the family-gate
notice ships, legal-basis sign-off to the club owner before `RACE_HISTORY_FAMILY_POLICY_VERSION`
is ever set.

## 6. Cross-season progression

`field_metrics.compute_field_metrics` (feature 037) already computes field size, percentile,
gap-to-median and category-median time per válida — this feature reuses it rather than
duplicating it, and does not modify it, so its existing AI contract and `extra="forbid"`
snapshot schemas stay untouched.

`app/services/race/history.py::build_history_points` is a pure function calling
`compute_field_metrics` once per season the athlete raced and adding only what was missing:

- `timed_finishers` and the `MIN_FIELD = 5` threshold — percentile hidden below 5
  finishers (any status), gap-to-median hidden below 5 *timed* finishers;
- the frozen category label (§2) and a `category_changed` flag, raised only when
  consecutive results carry a different `category_id` — a rename resolves to the same row,
  so it never raises the flag;
- per-season completion counts (finished over started).

No `avg_speed_kmh` — removed from this cross-season history 2026-09-22 (owner decision,
"no es un dato relevante" here); per-válida speed is unaffected on the Circuito tab and
`EvolutionChart`/`EvolutionTable` (feature 043).

`GET /api/athletes/{athlete_id}/race-analysis/history` sits behind `verify_athlete_access`,
at most three statements (athlete results with event/series; field rows restricted to the
athlete's own `(event_id, category_id)` pairs; categories — no course-setups query since
speed was removed) — asserted by a statement-count test, not just documented.

## 7. Family visibility

User Story 7 (Phase 9 of `tasks.md`) is fully implemented and closed — T083 (UX review) and
gate G6 both landed 2026-09-22.

**The gate.** `app/config.py` declares `race_history_family_policy_version: str = ""`
(`RACE_HISTORY_FAMILY_POLICY_VERSION`, empty = closed). Pre-joining = `event_date <
athlete.created_at.date()` — the platform has no separate joining date (`research.md` R-09).
`GET /api/athletes/{athlete_id}/race-analysis/history`
(`app/routers/athlete_race_analysis.py`) checks, for role `parent` only:

```python
if current_user.role == UserRole.parent and not await is_policy_version_in_force(
    settings.race_history_family_policy_version, db
):
    results = withhold_before(results, events, athlete.created_at.date())
```

`is_policy_version_in_force` costs one extra query only when the setting has a value (empty
string short-circuits, no DB round-trip). `withhold_before`
(`app/services/race/history.py`) is a pure filter over `(results, events)` by event date — it
does not itself decide *whether* to apply, keeping the role/policy decision at the router and
the filtering logic independently testable. Coach and admin are never filtered. The response
carries no count, flag or caveat of what was withheld (FR-041) — a parent with the gate
closed sees a shorter series, not a series with a gap explained.

**The family card.** `HistoryProgressionCard` (§6) is shared, not duplicated: it mounts with
`audience="family"` on a **Carreras** tab of `frontend/src/routes/parents/
MyAthleteDetailPage.tsx` — the same tab name and placement pattern as the coach's own
`AthleteDetailPage.tsx` (§6, ux-review BLOCKER fix), so a parent and a coach recognise the
same surface. `audience` only changes text nuance, not data or layout.

**The category-change explainer went through two rewrites, not one — the final version
restores part of the spec's original wording, but only where the data actually supports
it.** The first rewrite (before T083) replaced the spec's draft copy ("Subió de categoría:
ahora corre con deportistas mayores. Es normal que el puesto baje al comienzo.") with a
neutral sentence, because `category_changed` alone — "`category_id` differs from the
previous result" (§2, §6) — carries no direction guarantee, and a renamed-but-equivalent
category could trip the same flag. T083's own review then pointed out that the neutral
sentence, while safe, silently dropped half of FR-042's requirement: it must also *explain*
that moving up means racing older riders and that a lower placing right after is expected —
not just avoid overclaiming. The fix needed a backend signal the frontend didn't have: a
new field on `HistoryPoint`, `category_change_kind: Literal["promotion", "other"] | None`
(`athlete_race_analysis.py` schema; computed by `history.py::_category_change_kind`), which
returns `"promotion"` **only** with catalogue evidence — same sex, both categories' `age_min`
known, and the new one strictly greater — never inferred from the id/label difference alone.
`HistoryTable.tsx` (shared by both audiences) now branches on it:

- `"promotion"` → the original spec copy is restored, verbatim: *"Subió de categoría: ahora
  corre con deportistas mayores. Es normal que el puesto baje al comienzo."*
- anything else (`"other"` or unknown) → the neutral sentence from the first rewrite: *"Cambió
  de categoría (de {anterior} a {nueva}). En la nueva categoría compite con otro grupo, así
  que el puesto no se compara directamente con el anterior."*

The lesson generalises beyond this one string: a family-facing claim about a minor's
competitive trajectory needs to be gated on evidence the platform can actually verify, not
just on whichever event triggered the marker.

**Two more T083 fixes, both mobile/comprehension gaps rather than correctness bugs.**
`HistoryTable.tsx` had no viewport accommodation at all for its seven-column table — at
360 px it would have either forced horizontal scroll or squeezed into unreadable cells,
right below the card's otherwise-solid text-first block. Fixed with a `md:hidden` stacked
card list (one card per válida, matching the existing `AnthropometryHistory.tsx` pattern)
rather than the cheaper scroll-container wrap, since a parent audience reading percentile
and gap figures cold benefits more from label:value pairs than from a horizontally-scrolled
table. Separately, "Percentil" and "Brecha a la mediana" were the two headline metrics of
both the table and the chart with no plain-language anchor anywhere in the family view — a
`role="note"` explainer, gated to `audience === "family"` (the coach keeps the bare terms,
already part of daily vocabulary), now spells out what each one means in one sentence. A
third, minor fix: the shared "el atleta" subtitle now reads "tu hijo o hija" for
`audience="family"`, matching the tone the rest of the family surface already uses —
deliberately without threading the child's actual first name into the component, per an
explicit instruction from the lead.

**What is drafted but not yet published.** The privacy-notice paragraph for families (T081)
is drafted at `docs/10-race-results/history-family-notice.md` — **currently untracked, not
committed** — ready for the owner to publish as a policy version. Its contact line is
`privacidad@trochyruta.com`, the same address already given to families in the stage-log
email template (`templates/email/athlete_stage_log.html`).

**Operational gotcha, recorded for whoever operates this gate (also in `runbook-ops.md`
§12.2)**: `is_policy_version_in_force` (`app/services/privacy.py:58`) treats a **deprecated**
policy version as no longer in force — it returns `False` once `policy.deprecated_at` is on
or before today, exactly the same as an unknown or not-yet-effective version.
`RACE_HISTORY_FAMILY_POLICY_VERSION` must keep naming *a* version that is currently in
force — so whenever the owner publishes a newer privacy-policy version that supersedes the
one this setting currently names, the setting must be updated to the new version in the same
change. There is no warning or error if this is missed: the family gate silently closes
again and pre-registration results disappear from every parent account until the variable is
updated. This is a documented operational coupling by design, not a defect the code works
around — the setting deliberately stays a single string naming one version, reusing the
existing policy-version mechanism from FR-041's design unmodified.

**Closed 2026-09-22**: gate G6 passed — US6+US7 tests green (224 backend history tests, 387
frontend tests on the parent Carreras tab), and the Playwright end-to-end run (§4.6) is this
gate's SC-010 evidence end to end: the parent view shows zero third-party strings against a
real running stack, not just a unit-test assertion.

## 8. Known limits, recorded on purpose

- A competitor with several printed identity signatures does not have their
  **already-committed** results retroactively split by category discriminator — only rows
  still in a staged import are. Which triple a committed result came under is not tracked.
- The acknowledgement reason catalogue (§3) can name that a gap is real but cannot itself
  distinguish *why* beyond its four closed codes; a genuinely novel defect type still needs a
  code change, by design (closed catalogue, no free text).
- `compute_field_metrics` keys per event; nothing in this feature changes that, and the
  cross-season series is built by calling it once per season rather than by a single
  cross-season query.
- The historical categories loaded as season-specific (`MAS_B_2025`, `MAS_C_2025`,
  `PRE_F_U`) never appear in a current-season selector, by construction (`is_active=false`),
  and they are also never candidates for later merging — a general alias/merge-split
  management screen stays explicitly out of scope.

## 9. Legal basis

The legal basis for holding several hundred third-party minors' results is **legitimate
interest in a sporting context**, limited to situating the club's own ~20 athletes against
the field they raced. Publication on the organiser's public blog does **not** make the data
"public data" in the sense of Ley 1581 Art. 3 lit. g — a public-blog PDF is not the same
legal category as data the subject or their guardian actively published as public. This is
why the third-party lock (§5) had to exist before the load, not merely before the interface
offered a way to ask for it.

## 10. Deferred on purpose (FR-043)

Two items the privacy audit's preliminary review (2026-09-18) required as conditions of
approval, and that this feature deliberately does **not** implement:

- **Erasure**: a real path for a third-party (unlinked) competitor to be removed on request.
- **Retention**: a policy for how long the fifteen stored source PDFs are kept.

Both are recorded here as accepted, documented governance debt, owed to the feature
immediately following this one — not a silent gap. The closing audit (T090/T091, §5) wrote
down an owner and a "before what" for each, so the debt has a trigger, not just a name:

| Deferred item | Owner | Due before |
|---|---|---|
| Erasure on request for a third-party competitor's name, club, city, results, signatures and identity candidates | Club owner (data controller) + the feature after 044 | Publishing the privacy-notice version that opens the family gate |
| Retention period for the stored source PDFs and historical imports' `parse_meta_json` | Club owner | Same feature as erasure |
| Legal basis (legitimate interest) and the notice's text, with legal sign-off | Club owner | Setting `RACE_HISTORY_FAMILY_POLICY_VERSION` for the first time |

## 11. References

- `specs/044-race-history-backfill/spec.md`, `plan.md`, `research.md` (R-01…R-16),
  `data-model.md`, `contracts/*.md`, `quickstart.md`, `privacy-audit.md`, `ux-review.md`,
  `tasks.md`.
- `docs/10-race-results/upload-design.md` — the original Phase 1.7 import pipeline this
  feature extends rather than replaces (FR-023).
- `docs/10-race-results/course-profile-design.md` — feature 043, per-válida course/speed
  figures (`derive_figures`); untouched by this feature after `history.py` stopped using
  `avg_speed_kmh` (2026-09-22).
- `docs/implementation-status.md` — phase-by-phase status of this feature.
- `docs/technical-notes.md` — dated changelog entries.
