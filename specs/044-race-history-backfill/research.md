# Phase 0 Research — Race history backfill (044)

All measurements below were taken on 2026-09-18 on three official files downloaded to a temporary directory outside the repository (opening válida 2025, opening válida 2024, closing válida 2025) and deleted afterwards. Only counts and masked character shapes were inspected; no rider name appears in this document or anywhere in the repository.

---

## R-01 — Why rows are lost, and how to read them

**Finding (corrects the spec's first hypothesis).** Rows are *not* lost because text wraps onto several lines: in all three files every table row band contains exactly one text baseline. The real cause is that a long `Club/Patrocinador` value is **not clipped to its column**: it overflows to the right and is printed *over* the `Tiempo` column. `page.extract_text()` orders characters by x position, so the club's trailing letters interleave with the time digits (masked shapes such as `A9A:9A9 A:9A9A`), and `_RESULTS_ROW_RE`, which needs a clean `H:MM:SS` followed by the points at the end of the line, fails. The row then falls into the "noise" branch of `parse_results_pdf` with no warning. A second, smaller loss mode is a club that ends flush against the time with no gap (`A9:99:99`).

| File | Table rows (rulings) | Rows matched today | Lost today | Prototype |
|---|---|---|---|---|
| 2025 opening válida | 282 | 214 | 68 (24 %) | 282 (280 timed/status + 2 position-without-time) |
| 2024 opening válida | 277 | 232 | 45 (16 %) | 277 |
| 2025 closing válida | 280 | 211 | 69 (25 %) | 280 (278 + 2) |

The loss is file-wide (16–25 %), not confined to one category; the 28 % figure in the spec is one category of the first file.

**Decision.** Row reading becomes **band-first, stream-ordered**:

1. `page.find_tables(_TABLE_SETTINGS)` gives one bbox per table row. The rulings are reliable for *row* boundaries (every row of the three files has a numeric ordinal and bib in cells 0–1) but *not* for the club/time/points column boundaries (cells 5–6 contain club fragments in 84–130 rows per file), so cell text is no longer trusted for time or points.
2. For each row band, take `page.chars` whose `top/bottom` fall inside the band **in content-stream order** (never x-sorted). Insert a space when the gap to the previous char exceeds 1 pt or when x jumps backwards (the start of the next cell's text run). In stream order the club run and the time run are contiguous and clean even when they overlap on the page.
3. Match the rebuilt string with a relaxed row regex: time is `(?<![\d:])\d:\d{2}:\d{2}` (single-digit hour — XCO races are < 10 h — so a club ending in a digit cannot swallow the hour), whitespace before the time is optional, status tokens `DNF|DSQ|DNS|(-N VUELTA[S])` unchanged, trailing integer = points.
4. A band that matches only `pos bib body points` is kept as **classified without time** (`time_raw=""`), never dropped (spec edge case; 2 rows in each 2025 file).
5. A band that matches nothing is returned as an **unreadable row** with its page and ordinal, listed to the coach (FR-001). Zero such rows in the sample.
6. `name / city / club` come from **runs segmented inside the band and assigned by starting x**, not from `table.extract()` cells. *(Corrected during implementation — the original plan to read cells 2–4 was wrong.)* Measured on the official 2026 file: when a club overflows, its own cell is not a truncated prefix of the good value but text interleaved with the neighbouring overflow, and the **city truncates too** (`SANTANDER DE QUILICHAO` → `SANTANDER DE`). Prefix-based reconstruction aligned only 168 of 229 rows. What does work: each cell paints its own text run, and a run always starts within its own column's horizontal range even when the previous cell has overflowed onto it (overflow travels right and never moves the next run's start). Measured starts on the worst row — `63.7 / 91.2 / 112.0 / 259.5 / 329.7 / 468.3 / 541.1` against cell borders `50.7 / 76.8 / 109.9 / 257.4 / 327.6 / 458.6 / 504.3` — fall unambiguously in their own column. Result: **229 of 229 rows** assigned by runs, zero fallbacks, zero text fields carrying time fragments. A run starting outside every cell yields `None` and the cell value is kept; text is never invented. `_band_text` is defined as those same runs joined by a space, so the two functions cannot diverge.

   **Why this matters beyond parsing**: `club` and `city` are two of the three components of the identity signature of R-06. A truncated club produces a different signature for the same person, and the amount truncated depends on how far the text overflowed — so the same rider in two válidas could yield two signatures and be split into two competitors, before the identity review even sees them. On the historical files this would have affected the 84–130 rows per file that carry overflow.
7. Category headers are interleaved with row bands by vertical position on the page (`extract_text_lines` top vs row bbox top), replacing today's line-order walk; the "category persists across pages" rule stays.

The current text-line path is kept as a **fallback for pages where `find_tables` returns no table** (defensive; none in the sample) and as a cross-check: a row found by one path and not the other raises a `row_path_mismatch` warning.

**Rationale.** Measured 100 % recovery with zero unparsed rows on the three files, and ordinal/bib agree with the table cells in every matched row. Uses only pdfplumber primitives already in use.

**Alternatives considered.** (a) Table cells as the source of time/points — rejected, 30–46 % of rows have club fragments in those cells. (b) Splitting chars by ruling x-ranges — rejected, the overflowing club physically crosses the ruling. (c) Clustering chars by baseline to undo wrapping — rejected, there is no wrapping. (d) OCR — irrelevant, files are native text.

**Regression guard (FR-007).** The existing `tests/services/race/test_parser.py` and `test_parser_edge_cases.py` oracles for válida IV 2026 must stay green unchanged.

## R-02 — Event header helper

`_EVENT_HEADER_RE` and `_ROMAN_TO_INT` stop at VII; the 2025 closing válida is `VALIDA VIII …` and `parse_event_header` returns `None` for it. **Decision:** extend the numeral alternation and map to I–XII (order the alternation longest-first so `VIII` is not read as `VII` + `I…`). The header stays a *helper*: season, válida number, date and venue are already explicit form fields of `POST /race-imports/parse`, so FR-025 ("ask the coach, assume nothing") is satisfied by the existing contract. The staging script (R-12) reads them from a manifest.

## R-03 — Category vocabulary (corrects the spec's first description)

Distinct headers observed:

| Season | Count | Differences from the 2026 catalogue |
|---|---|---|
| 2024 | 25 | women's groups printed as `… DAMAS` / `… NIÑAS`; elite men printed as `ELITE HOMBRES`; **masters already in four groups** (`B1, B2, C1, C2`); a single `PREINFANTIL NIÑAS` |
| 2025 | 23 | **masters in two groups** (`MASTER B`, `MASTER C`); a single `PREINFANTIL FEMENINO`; the same category printed as `PREJUVENIL A DAMAS` in one válida and `PREJUVENIL A FEMENINO` in another |
| 2026 | 26 | reference |

So the two-group masters are a 2025 fact only, and the structural difference shared by both historical seasons is the **undivided pre-infantile girls' group** (2026 splits it into A and B).

**Decision.**

- *Renames* are added to `normalizer.HEADER_TO_CODE` as season-agnostic aliases (they are unambiguous in every season, and 2025 itself mixes both spellings): `elite hombres→ELITE_M`, `elite damas→ELITE_F`, `junior damas→JUN_F`, `master damas→MAS_F`, `infantil a ninas→INF_A_F`, `infantil b ninas→INF_B_F`, `prejuvenil a damas→PJUV_A_F`, `prejuvenil b damas→PJUV_B_F`.
- *Season-specific categories* are three new catalogue rows with `is_active=false` (never offered for current data — every current selector already filters on `is_active`, to be verified by a test per selector): `MAS_B_2025`, `MAS_C_2025` (tier `master`, sex `M`) and `PRE_F_U` ("Preinfantil femenino (grupo único)", tier `menores`, sex `F`, age range = union of `PRE_A_F` and `PRE_B_F`), mapped from `master b`, `master c`, `preinfantil ninas`, `preinfantil femenino`. Age ranges of the two 2025 master groups come from the 2025 regulations; when unknown they stay `NULL` and the frozen columns (R-04) record `NULL`.
- The parser returns **unrecognised headers with their rows** instead of dropping them (`UnknownCategory(header_raw, rows)`); the preview lists them (FR-002) and their commit is blocked until a mapping exists (a code change to the alias dict, by design — the catalogue is closed).
- The preview exposes, per category, `header_raw`, resolved `code`, and `mapping_kind ∈ {exact, rename, season_specific, unknown}` (FR-011).

**Alternatives considered.** Season-keyed mapping (`(season, header) → code`) — rejected as unnecessary: no header means two different groups in different seasons. A season-versioned catalogue — out of scope by owner decision.

## R-04 — Freezing what a result meant

**Decision.** Three nullable columns on `race_results`: `category_label_raw VARCHAR(100)` (the header as printed, e.g. `PREJUVENIL A DAMAS`; for CSV imports the CSV header), `category_age_min_raw`, `category_age_max_raw SMALLINT` (copied from the catalogue row at insert time). Written by the ingestor on insert, never updated afterwards (not even by the revision flow, which inserts new rows). The migration backfills existing rows from their catalogue category (`label`, `age_min`, `age_max`). All read paths that show a category for a *past* result prefer the frozen label.

## R-05 — Completeness check, manual correction, acknowledgement, partial commit

**Finding.** The official files themselves contain defects: a duplicated ordinal (`… 19, 20, 20, 21 …`) in one children's category in **both** 2025 files, and a missing ordinal (`… 5, 7 …`) in another. The spec's assumption "official results contain no ties" is therefore wrong, and the acknowledgement path (FR-005) is a necessity, not a corner case.

**Decision.**

- Pure function `check_completeness(ordinals: list[int]) -> CompletenessReport(status, missing, duplicated)` over *all printed ordinals* of a category (every row in the sample carries one, including lapped riders).
- The parsed rows are re-derived from the stored file on every dry-run/commit (`_reload_parsed_from_storage`), so manual corrections must be persisted: `race_imports.parse_meta_json["corrections"]` holds an ordered list of row patches (`add | edit | remove`, keyed by category header and ordinal) applied after parsing and before the check. Patches live only in the database (same sensitivity class as `race_competitors`), never in logs.
- Acknowledgement uses a **closed catalogue of reason codes** (`source_duplicate_ordinal`, `source_missing_ordinal`, `source_disqualification_gap`, `verified_against_source`) instead of free text, following the precedent of `RevisionReasonCode` (free text about a results sheet of minors invites names). Stored in `parse_meta_json["acknowledged"]` with user and time and written to the audit trail through `record_audit`. *This narrows FR-005's "written reason" to a chosen reason; recorded in the spec's Assumptions.*
- **Partial commit without a new enum value** (avoids the MySQL enum/`values_callable` trap): `commit` ingests the consistent or acknowledged categories, sets the import `committed`, and records `parse_meta_json["pending_categories"]`. A new `POST /race-imports/{id}/commit-pending` re-runs the ingest for the same import restricted to categories that have since become consistent; the ingestor is already idempotent per `(event, category, competitor)`, and the SHA-256 short-circuit is bypassed only for this restricted re-run. The import list shows a "categorías pendientes" counter.

## R-06 — Identity across seasons

> **Depends on R-01's run segmentation.** The club and city that feed a signature are only trustworthy because the band reader assigns them by run position; read from table cells they arrive truncated on every overflowing row. See R-01 point 6.

**Finding.** `race_competitors.normalized_name` is globally `UNIQUE` and both upserts match on it alone, so two people with the same name silently become one competitor, and one person printed with and without a second surname becomes two. `ResultsRow.city` is parsed "for homonym resolution" but never stored. Linking already propagates `athlete_id` to every result of a competitor regardless of club (`_propagate_athlete_id`), which is what makes pre-club history work once identity is right — but the ingestor persists `athlete_id` on a new result only when the *row's* club is the club's own (`athlete_id_to_persist = … if is_tyr else None`), which would leave pre-club results of an already linked competitor unattached.

**Decision.**

1. `race_competitors`: drop `uq_race_competitors_normalized_name`, add a plain index on `normalized_name`, add `city_text VARCHAR(100) NULL` (disambiguation only; FR-014).
2. New table `race_competitor_signatures` — the observed `(normalized_name, club_norm, city_norm)` triples, each owned by exactly one competitor, `UNIQUE` on the triple. It is the persistence that lets the platform *remember* decisions and keep homonyms apart in later loads (FR-020, FR-021), and its unique key restores the concurrency guard that the dropped constraint provided (`test_ingestor_concurrency`). It is not a user-managed alias feature: there is no screen to edit it outside the review.
3. New table `race_identity_candidates` — the review queue and the audit of decisions: kind (`same_person_suspect | homonym_suspect`), two record snapshots (name as printed, club, city, seasons, category codes, competitor id when one exists), score, signals, state (`pending | same_person | different_people`), `reversed_at/by`, `linked_athlete_involved`, decider and time. `UNIQUE(pair_hash)` so a rebuild never duplicates or re-asks.
4. Candidate generation (`identity_review.build_candidates`), over all staged historical imports plus existing competitors:
   - *same-person suspects*: different normalised names with `rapidfuzz.fuzz.token_set_ratio ≥ 90`, compatible sex, and a category path that never moves to a younger age group in a later season; blocked by shared surname token so the comparison stays far below n²;
   - *homonym suspects*: identical normalised name with any of: presence in two categories of the same válida; incompatible sex; an age path that moves backwards; **club and city both different** (normalised, fuzzy < 70). A changed club alone is *not* a signal — children change clubs — it only adds a signature.
5. Resolution at ingest (`IdentityResolver`): exact signature → its competitor; else same name, single competitor, no homonym signal → attach and add the signature; else a decision must exist (`same_person` → attach to the decided competitor; `different_people` → new competitor). With no decision the ingest of that row is impossible by construction, because commit is gated (next point).
6. Commit gate: `commit` and `commit-pending` return `409 identity_review_pending` with the pending count while any candidate is `pending`. Current-season imports are unaffected unless a rebuild found candidates that involve them.
7. Reversal: `same_person → reversed` splits the competitor back using the signature that the decision had attached (results carry `imported_from_id` and the signature's seasons, so the split set is exact); if the competitor was linked to an athlete, the split-off competitor is left unlinked and `athlete_id` is cleared on its results. Audited.
8. The ingestor persists `athlete_id` on a new result whenever the resolved competitor is linked, regardless of the row's club. `is_trocha_y_ruta` keeps deciding only whether the *wizard asks* for a match.

9. **Same name, club and city — "separar por categoría" (owner decision 2026-09-21, revision `a7c3e5d91f20`).** The triple alone cannot tell a parent and child of the same club apart. The signature gains `discriminator VARCHAR(32) NOT NULL DEFAULT ''` and the unique key becomes the quadruple. *Rule*: `discriminator = "<sex>:<age_min>-<age_max>@<season>"`, where sex is `M`/`F`/`X` (mixed) and the age range comes from the **catalogue row** of the category (so a header rename never changes it; open bounds stay empty), and season is when it was observed. A row is *compatible* with a discriminator when the sex does not clash and the row's category age range overlaps the discriminator's range shifted by the seasons elapsed, widened by `AGE_TOLERANCE_YEARS = 1` on each side (category cut-offs are by birth year): an Infantil A of 2025 stays compatible with Infantil B in 2026; a Master A never is with an Infantil. *Candidates*: the appearances of one triple are grouped greedily (`split_by_category`, season order; an appearance joins the first compatible group that has no other category in the same válida); two or more groups become separate records keyed `triple + discriminator`, paired as `homonym_suspect` with the usual signals or `age_incompatible_categories` when none applies. *Decision*: `different_people` relabels the competitor's `''` signature with its side's discriminator; if that competitor already mixed both people's committed results (pre-044 data), the other side's results move to a new competitor with its own signature — refused with `linked_competitor_ambiguous` when the competitor is linked to an athlete. A reversal that only relabelled restores `''`; once two signatures exist they stay apart until a `same_person` decision (contract). *Resolver*: a triple with discriminated signatures, or with an intra-triple `different_people` decision, is resolved by the single compatible discriminator (creating that side's competitor on first sighting); none or several people compatible → `IdentityUnresolved`. Single-signature triples keep the `''` behaviour. *Limit*: for a competitor with several signatures its committed results are not split (the triple each came under is unknown); only its staged rows are.

10. **Scope limited to club athletes (owner decision 2026-09-22).** Measured on a real local load of the 15 official files: 781 pending candidates (760 same-person suspects, 21 homonyms), 20 involving a club athlete. *Candidates*: `build_candidates` raises a pair of either kind only when `in_club_scope` holds — at least one side is an existing competitor with `athlete_id` (`IdentityRecord.athlete_linked`). *Resolver* (`IdentityResolver`): the by-name step only considers **linked** competitors, so a third-party row whose name matches only unlinked competitors with a different club/city becomes a new competitor with its own signature (never merged by name; an identical triple is a signature hit anyway). A triple is *third-party* when none of its signatures is owned by a linked competitor and no candidate involves it (except `different_people` with another triple, which only excludes). *Same-válida collision* (identical triple twice in one file): the ingestor computes `collision_discriminators` over the whole file (so dry-run, commit and `/commit-pending` agree): the category discriminator of §9 when unique among the colliding rows, else `bib:<bib>@<season>` when the bib is unique, else `row:<code>-<index>@<season>`; for a third-party triple each row takes the exact signature of its discriminator, else the single compatible category signature already on file (the same person in earlier válidas), else a new competitor — never the `''` signature, and never a signature another colliding row already took. `bib:`/`row:` discriminators are never category-compatible. *Fallback*: a separated third-party triple with no single compatible discriminator resolves to its `''` signature if any, else `bib:<bib>@<season>` (`bib:-@<season>` without a bib), creating it if needed — `IdentityUnresolved` is reserved for club-managed triples. *Queue*: `rebuild` deletes pending candidates that were never decided, were not produced again, and have no side linked today (`remove_out_of_scope`; `RebuildResult.removed`); decided and reversed candidates are history and stay. *Limit*: a third-party parent and child of the same club who never share a válida stay one competitor (no signal is available without the coach), which is harmless because third-party cross-válida data is never exposed.

**Review before code (T043, 2026-09-21).** Rules checked against owner decision 3 (fuzzy suggestion + coach confirmation, blocking before bulk commit) and FR-016/FR-017: nothing merges automatically — a same-person suspect only ever becomes one competitor through a `same_person` decision, and every pending candidate blocks `commit`/`commit-pending`. Confirmed: a changed club alone is not a signal (it only adds a signature); a homonym needs *both* club and city to differ (fuzzy < 70) or one of the three category/sex signals. Blocking key for same-person comparison: any shared surname token (normalised token ≥ 3 chars, excluding the first token), so the pairwise work stays far below n². Thresholds stay as named constants `SAME_PERSON_MIN_SCORE = 90` and `DIVERGENCE_MAX_SCORE = 70`. One implementation constraint from the T036 audit carries into US4: no public callable under `app/services/race/` may take `competitor_ids: list[int]` unless the structural scan of the third-party lock is extended to cover it.

**Alternatives considered.** Keeping the global unique and adding a warning only — rejected: with the full start list the collision is the common case, and a warning after the merge is too late. A general alias-management screen — out of scope by owner decision. Birth dates for third parties — not available and not sought.

## R-07 — Third-party progression lock

**Finding.** The family- and coach-facing progression endpoints are already keyed by `athlete_id` behind `verify_athlete_access`. The exposure is in the service layer: `analytics.athlete_progression`, `podium_gap`, `projection`, and the loaders behind `compute_field_metrics` accept any `competitor_id`; only calling convention keeps them on club athletes.

**Decision.** `app/services/race/third_party_guard.py::require_club_competitor(db, competitor_id) -> int` returns the linked `athlete_id` or raises `ThirdPartyProgressionForbidden` (mapped to 403 at the router edge). Every public function under `app/services/race/` that takes a `competitor_id` and returns per-person data across válidas calls it first. A **structural test** walks the package, finds public callables with a `competitor_id` parameter, and fails unless each is either guarded (detected by a marker decorator `@club_competitor_only`) or on a short, reviewed allow-list of single-event helpers. The new history endpoint (R-08) has no `competitor_id` anywhere in its contract. This ships and is tested before the first historical commit (task ordering in `tasks.md`, plus a runbook gate).

## R-08 — Cross-season progression: reuse, not duplication

**Finding.** `field_metrics.compute_field_metrics` (feature 037) already computes `field_size`, `percentile`, `gap_pct`, `category_median_time_ms` and `gap_to_median_pct` per válida, season by season, with a documented rule: the field is everyone who finished (`FINISHED` or `MINUS_LAPS`), while time-based figures use strict `FINISHED` only. It applies no minimum field.

**Decision.** New pure module `app/services/race/history.py::build_history_points`, which calls `compute_field_metrics` once per season the athlete raced and adds only what is missing: `timed_finishers`, the ≥ 5 thresholds (percentile hidden when `field_size < 5`; gap to the median hidden when `timed_finishers < 5`), the frozen category label, the `category_changed` flag (consecutive results with different `category_id`; a rename maps to the same row, so it never raises the flag), `avg_speed_kmh` via the existing `course/derived.py::derive_figures`, and the per-season completion counts. `compute_field_metrics` is not modified, so the 037 AI contract and its `extra="forbid"` snapshot schemas are untouched. *The spec's FR-030 wording ("full-distance finishers") is aligned to 037's definition; recorded in Assumptions.*

Endpoint: `GET /api/athletes/{athlete_id}/race-analysis/history` behind `verify_athlete_access`, at most four statements (athlete results with event/series; field rows restricted to the athlete's `(event_id, category_id)` pairs; categories; course setups), asserted by statement count. p95 ≤ 500 ms for ≤ 30 results.

## R-09 — Family gate for pre-joining results

**Finding.** `athletes` has no joining date, only `created_at` (the platform registration date). Every athlete was registered in 2026, so for practical purposes all 2024–2025 results are "pre-joining".

**Decision.** Pre-joining = `event_date < athlete.created_at.date()`. New setting `RACE_HISTORY_FAMILY_POLICY_VERSION` (default empty = gate closed). For role `parent`, pre-joining results are filtered out server-side unless the setting names a `privacy_policies.version` whose `effective_date` has arrived. Coach and admin are never filtered. The response carries no count or flag of withheld rows (FR-041). The notice text is drafted in español as part of this feature and published by the owner through the existing policy flow; no per-family consent gate is added.

## R-10 — Historical series and points

Series `Copa Valle de Ciclomontañismo` 2024 and 2025 are created by the existing `_get_or_create_series`. `points_scheme_code` is a logical key; two descriptive rows `copa_valle_2024` and `copa_valle_2025` are seeded with `is_official=false` and an empty `position_points`, documenting that points for those seasons are **as printed**, never recalculated. `standings.py` already sums `points_awarded`; the read schema gains `is_calculated: true` and the UI labels the table "Clasificación calculada por la plataforma". GENERAL files are not staged (`kind=resultados`).

## R-11 — Frontend

- **Coach**: `HistoryProgressionCard` on the athlete's race-analysis surface (lazy chunk, Recharts): x = date on a time scale; one metric at a time through a toggle (gap to the median — default — or average speed), never a dual axis; the gap axis is inverted so "up" means faster than the median, with the zero line labelled "mediana de su categoría"; `ReferenceLine` at each category change labelled `A → B`; missing válidas/seasons as a dashed connector; DNF/DSQ/DNS as a distinct marker on the baseline with no value; every tooltip shows field size. Below it, a table grouped by season and category with position, percentile and field size — never a line across groups. A permanent caveats block (`role="note"`). Per-season completion chips ("5 de 7").
- **Family**: the same card on `MyAthleteDetailPage` with family wording, the category-change explainer (FR-042), text-first rendering before the chart chunk.
- **Historical load**: `HistoricalLoadPage` (board of staged imports: parsed → categories pending → identity review → ready → committed), `IdentityReviewPage` (side-by-side cards, one-tap decision, keyboard accessible, resumable), and preview extensions inside the existing `ImportWizard` (category mapping table, completeness badges, row-correction dialog, acknowledgement dialog).
- jest-axe zero violations on the card, both pages and both dialogs; all copy in español neutro.

## R-12 — Staging the fifteen files

`backend/scripts/stage_race_history.py` reads a manifest (season, válida number, date, venue, file path) and stages each file through the **same service function** the `/parse` endpoint uses (the parse body of `routers/race_imports.py` is extracted into `services/race/import_staging.py`; the router becomes a thin caller). The script never commits: review and commit happen in the UI by the coach, so the audit trail names a person. The manifest and the files stay outside the repository. Reminder recorded in the runbook: a local backend points at the production database.

## R-13 — Performance budgets

`POST …/identity-review/rebuild` is CPU-bound (≈ 3 000 distinct names): runs in a worker thread with a 30 s timeout, blocked comparison, budget ≤ 10 s, documented in the route docstring as an explicit batch budget. Parsing per file stays within the current `_parse_results_with_timeout`; band reading adds one pass over `page.chars` per page (measured negligible). History endpoint budget in R-08. Chart in a lazy chunk so the athlete route stays under the per-route bundle budget.

## R-14 — Test fixtures and a pre-existing concern

Historical-layout fixtures are **synthetic**: `tests/helpers/results_pdf_builder.py` renders a ruled results table with WeasyPrint (already a dependency) using `white-space: nowrap; overflow: visible` on a fixed-width club cell, which reproduces the overprint; a builder self-test asserts that x-sorted text extraction of its output interleaves club and time (proving the fixture exhibits the defect) and names come from a fake-name generator. The band reader is also unit-tested on hand-built char dicts with no PDF at all.

*Pre-existing, out of scope, flagged to the owner:* `tests/fixtures/race/valida_iv_2026_*.pdf` and the 2026 CSV are real official files committed to the repository, which sits uneasily with the rule about git-committed fixtures containing minors' names. This feature relies on them only as the FR-007 regression oracle and adds no new real file.

## R-15 — AI stack

Untouched. A regression test loads the 2026 analyst context with 2024–2025 data present and asserts it is identical to the context without them (every race-AI query already filters by season). The guard of R-07 is satisfied by construction because the AI pipeline only runs for linked athletes.

## R-16 — Deferred governance (FR-043)

Erasure of unlinked competitors and retention of stored source files are documented as the next feature in `docs/10-race-results/history-backfill-design.md` and `runbook-ops.md`; the privacy audit file for this feature records them as accepted debt with an owner and no date promise.
