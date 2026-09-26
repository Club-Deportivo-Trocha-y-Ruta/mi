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

**Addendum T024b (2026-09-22) — the time cell is not always a time.** The real local load showed 230 parsed rows across the fifteen official files reaching the ingestor with `time_raw == ""`, all of which `ingestor.py` then dropped (`tiempo_no_parseable` → `continue`). Per válida: 2024 V6 33, 2025 V2 75, 2025 V6 54, 2025 V7 32, the rest 1–9. Measured on the time cell of those bands (counts and masked shapes only): the cell was almost never empty — it held a **lap deficit outside the canonical `(-N VUELTA[S])` form** (`-1 vuelta` without parentheses is the bulk; also `(1- VUELTA`, `(- 1 VUELTA)`, `(2 VUELTAS)`, `(-3 VUELTAS=`, `()-1 VUELTA)`, `-2 vueltas (lap)` and the typos `VULETAS`/`VIELTAS`), or the deficit **glued to the club/city run** with no gap (`…CLUB(-1 VUELTA)`), or a two-digit-hour typo (`12:02:00`, `16:56:00`) or a stray apostrophe (`0:16:'08`). No `MM:SS` time was found in these files, but it is now accepted too. Decision: the row regex's time token also accepts `\d{1,2}` hours, `MM:SS`, a lenient lap token (a number **and** a vuelta-shaped word `V[UÚI]?(?:EL\|LE)TAS?` plus a sign or parenthesis — deliberately narrow so neither a bib, the points nor a proper name starting with `V` can match) and a bare `-N` preceded by whitespace; everything stays anchored right before the trailing points. A glued token is split off the club (or the city, when the club is empty). `normalizer.parse_time` reads every such form as `MINUS_LAPS` with its N, `MM:SS` as `FINISHED`, rejects an hour ≥ 10 as out of XCO range, and returns `(FINISHED, None, 0)` for `""`. Result: rows with an empty time drop from **230 to 6** on the fifteen files (4 genuinely blank cells + 2 bands with an empty name cell whose time the row regex reads as the name — a separate, pre-existing issue); per-file row counts are unchanged and there are still zero unreadable bands; 2 rows carry an out-of-range hour and are kept with a null time plus a warning. The 2026 válida IV file had **0** such rows before and after (229/229), so current-season data was not losing rows this way.

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

**Addendum T024b (2026-09-22) — the ingest must account for every row too.** The parse-level check above did not protect the ingest: it silently dropped any row whose time did not parse. Now (a) a row with a position and no time is stored as **`FINISHED` with `race_time_ms` and `laps_behind` NULL** — the same reading `history.py` and `field_metrics` already give "position without time" (T068: counts in the field, never in time-derived figures); this needed migration `b4e8d2f61a93`, which relaxes `ck_race_results_time_consistent_with_status` so `finished` no longer requires a time (a non-finished status still never carries one); (b) a non-empty time that still cannot be read is kept the same way with a `tiempo_no_parseable` warning; (c) only a row with neither a position nor a time is skipped, with an explicit `fila_sin_posicion_ni_tiempo` warning and before its competitor is resolved (no orphan competitor); (d) per category the ingestor asserts `rows read == inserted + already present + explicit skips` and aborts the whole transaction otherwise. Printed points are always stored verbatim.

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

**Decision.** New pure module `app/services/race/history.py::build_history_points`, which calls `compute_field_metrics` once per season the athlete raced and adds only what is missing: `timed_finishers`, the ≥ 5 thresholds (percentile hidden when `field_size < 5`; gap to the median hidden when `timed_finishers < 5`), the frozen category label, the `category_changed` flag (consecutive results with different `category_id`; a rename maps to the same row, so it never raises the flag), and the per-season completion counts. `compute_field_metrics` is not modified, so the 037 AI contract and its `extra="forbid"` snapshot schemas are untouched. *The spec's FR-030 wording ("full-distance finishers") is aligned to 037's definition; recorded in Assumptions.* **Update 2026-09-22:** `avg_speed_kmh` (originally derived here via `course/derived.py::derive_figures`) was removed from this endpoint per owner decision — see spec Assumptions; `build_history_points` no longer takes a `setups` parameter, and the loader's SQL budget dropped from 4 to 3 statements.

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

---

# Amendment 2026-09-26 — Skill-only results loading (R-17…R-31)

The owner removed every results-file upload (spec Clarifications 2026-09-26: FR-044…FR-049 and the corrected FR-027). This section plans that change on top of the implemented feature. It rests on two read-only sweeps of the code at `ebbb786`: backend routers, staging, parsers, ingestor, identity, revision and tests; frontend wizard, board, entry points and tests.

Three findings shape the design:

1. **Nothing persists parsed rows.** `parse_meta_json["categories"][].rows` is a count on purpose. Dry-run, commit, commit-pending, corrections, acknowledge and the identity-review loader all re-download the stored file and re-parse it (`_reload_results_document`, `_reload_parsed_from_storage`, two process-level LRU caches). Removing the server-side parser therefore requires persisting the staged rows (R-20).
2. **The revision flow is half-wired.** Detection (`detect_revision`, `will_be_revision`, `parent_committed_at`), the reason catalogue, `revision_reason` storage and AI-run invalidation are live. The diff preview is not: the wizard renders `DiffTable` from `is_revision`/`diff_rows` in the dry-run response, and the backend never returns them. The apply step is not either: `revision.compute_diff` and `revision.commit_revision` are implemented and tested but no endpoint calls them. A revision commit today goes through `ingest_event`, which only inserts `(event, category, competitor)` pairs that do not exist yet, so nothing is updated or removed. The corrected FR-027 therefore requires wiring these pieces (R-24). During clarification the owner was told this path was "already built, only the entry point changes"; that was wrong, and it has been reported to the owner.
3. **The wizard can already resume a staged import by id.** Feature 045 US3 added `/competitions/import?import=<id>`: `useRaceImport` → `parseResultFromDetail` → step 2 (dry-run, corrections, acknowledge, commit, discard), as `ImportWizard.resume.test.tsx` proves. Removing the upload is therefore mostly deleting step 1, provided every staged import carries the public `parse_meta_json` keys that `/parse` writes today (R-20).

## R-17 — What the LLM may see: a masked layout view (FR-046, SC-013)

**Decision.** A local, deterministic `mask` step reads the official file and writes a *layout view*: geometry and token classes, no rider data. It is the only file content the LLM ever reads.

- **Tokens.** Each line (PDF: row band or baseline; delimited text: row) is split into tokens. A token glued across a letter/digit boundary is split first (the R-01 `A9:99:99` case). The classes are:
  - `WORD`: contains a letter.
  - `INT`: digits only.
  - `TIME`: `h:mm:ss`, `mm:ss` and the variants `normalizer.parse_time` accepts.
  - `STATUS`: `DNF`, `DNS`, `DSQ`, `DQ` and the lap-deficit forms matched by `normalizer.LAP_WORD_PATTERN`.
  - `PUNCT`.
- **Structural lines.** A line is structural when it has no `TIME`, no `STATUS`, no `INT` of five or more digits, and every `WORD` is in the reviewed vocabulary. Structural lines render verbatim; they carry column titles, category headers and the document title.
- **Content lines.** Every other line renders `WORD` → `⟨W⟩`, `INT` → `⟨N{digits}⟩` and `TIME` → `⟨T {shape}⟩`. `STATUS` and `PUNCT` stay verbatim.
- **Geometry.**
  - PDF: runs are segmented exactly as the apply engine segments them (R-19: content-stream order, with a new run on a gap > 1 pt or a backwards x jump), and each run is prefixed with its start x. Each page lists its width and the x of its table rulings.
  - Delimited text: each cell is prefixed with its column index. The header row is structural only under the same vocabulary rule.
- **Vocabulary.** A committed, reviewed list made of:
  - the words of `normalizer.HEADER_TO_CODE` keys, plus `CAT`;
  - column titles: `POS`, `PUESTO`, `DORSAL`, `NUMERO`, `NOMBRE(S)`, `APELLIDO(S)`, `DEPORTISTA`, `CORREDOR`, `CLUB`, `EQUIPO`, `PATROCINADOR`, `CIUDAD`, `MUNICIPIO`, `TIEMPO`, `DIFERENCIA`, `VUELTAS`, `PUNTOS`, `CATEGORIA`, `EDAD`;
  - document words: `RESULTADOS`, `VALIDA`, `COPA`, `CAMPEONATO`, `CLASIFICACION`, `OFICIAL(ES)`;
  - roman numerals I–XII;
  - connectors: `DE`, `DEL`, `LA`, `LAS`, `LOS`, `Y`, `EN`.

  A unit test pins that the list contains **no month or weekday name** (Abril, Julio and Mayo are also given names and surnames), no place name, and nothing outside these classes.
- **Leak check (SC-013).** After `apply` extracts the real rows (R-18), the view is searched for every word of three or more letters from every extracted name, club and city. Only a count is printed. Any hit:
  - exits with code 3 and stops the run;
  - triggers the PII-leak procedure in `docs/10-race-results/runbook-ops.md` §3.5;
  - leads to removing the vocabulary word that let it through, in a reviewed change.

**Rationale.** Defining a layout needs geometry, token classes, column titles and category headers, never a value. A digit count separates an ordinal from a bib or a year, the time shape identifies the time column, and statuses are not personal data. This is the `bitacora-pdf` pattern: the LLM reads an anonymized brief, and a script holds the real names.

**Alternatives considered.**
- (a) Show the full text: rejected by the owner (Clarifications Q1) and by the constitution.
- (b) Mask only the name, club and city columns: circular, because finding those columns is the LLM's task.
- (c) Keep numbers verbatim: rejected. Organisers may print a birth-year, age or identity-document column, and a minor's birth year may not reach a provider.
- (d) Stable per-word ids (`⟨W0412⟩`): rejected. They reveal repeated surnames (siblings) and add nothing to layout work.
- (e) A local model reading the full file: option C of Q1, not chosen.

**Residual risk.** A rider's record could produce a structural line made only of vocabulary words, for example a club named after a category word printed alone on a wrapped line. The leak check catches it; it is never silent.

## R-18 — Reading profile: declarative data applied by one tested engine (FR-001, FR-002, FR-045)

**Decision.** The LLM's output is a **reading profile**: a JSON document committed under `backend/race_reading_profiles/<profile_id>.json` (schema v1; JSON because no YAML parser is a dependency). By construction it holds no rider data: a schema test allows only a closed set of keys and value types (`contracts/reading-profile.md`). The engine `apply_profile(file, profile)` in `app/services/race/results_skill/` turns the real file into a `StagedDocument` locally.

- **PDF.** Rows come from table bands (ruled layouts, R-01) or baselines (unruled layouts). Runs are assigned to columns by their start x; a run always starts inside its own column even when the previous cell overflowed (R-01 point 6). Category header lines are found by the profile's rule. Each label is mapped through the profile's `category_aliases`, then `normalizer.HEADER_TO_CODE`. An unknown label stays an unrecognised category with its rows (FR-002).
- **Delimited text.** Columns are taken by index. The category comes from a column or from separator rows.
- **Field grammar comes from the platform, not the profile.** `normalizer.parse_time` reads times, statuses and lap deficits (the T024b variants), and `check_category` checks completeness. There is one grammar for the whole platform.
- **Output.** The seven fields of `ResultsRow` (`position`, `bib`, `name`, `city`, `club`, `time_raw`, `points`), grouped into ordered categories with `header_raw` and `code`, plus unreadable rows (page, ordinal).

**Rationale.** A single interpreter, covered by CI, carries the privacy and correctness guarantees. A new organiser layout is a data file reviewed in a pull request, not new code run once over real data. When a layout needs a primitive the engine lacks, the primitive is added with a synthetic fixture as a normal change.

**Alternatives considered.**
- (a) The LLM writes a Python extractor per organiser: rejected. It is untested code run over real data on every load, nothing structural stops it from printing rows, and each load would need a code review.
- (b) Keep the fixed parser and add organiser branches: this is the path the owner called unsustainable.

## R-19 — Retire the fixed parsers, keep what they learned (FR-001, FR-007)

- `pdf_parser.py` and `csv_parser.py` are deleted together with the upload route.
  - Runtime importers: `completeness.py`, `routers/race_imports.py`, `import_staging.py`, and `csv_parser.py` itself.
  - `ingestor.py` and `revision.py` import the types only under `TYPE_CHECKING`.
  - `normalizer`, `identity_review`, `identity_resolver` and `matcher` do not depend on them.
- The shared types move unchanged to a neutral module, `app/services/race/staged_document.py`: `ResultsRow` (seven fields), `ParsedCategory`, `ParsedResults` and `UnreadableRow`. `GeneralRow` and `EventHeader` are dropped (R-25).
- The band and run primitives (content-stream order, run segmentation, start-x assignment, table-band detection) move to `results_skill/pdf_runs.py`, together with their hand-built-char tests (`test_band_reader.py`).
- **Parity.**
  - The first profile, `copa-valle-results-pdf`, must reproduce the retired parser's output on the synthetic builder files (the historical overprint layout and the 2026 layout). That way 044's reading guarantees (100 % of rows on overprinted files, the lap-deficit variants) survive as engine plus data.
  - A second, fictional organiser layout (different column order, unruled) proves the engine is not shaped around Copa Valle.
- `parse_event_header` goes. Season, válida, date and venue were never inferred (FR-025, R-02); they now come from the manifest or from an existing race event (R-31).
- FR-007 on real files is checked locally and read-only by `compare` (R-30), never in CI.

## R-20 — Staged rows live in the database; the server never re-reads the file (FR-048, FR-049)

**Decision.**

- **Storage.** A new 1:1 table, `race_import_staged_documents` (data-model §11), holds each import's `StagedDocument` as JSON, plus the profile id, the profile hash and the engine version. The alternatives were worse:
  - a key in `parse_meta_json`: the list endpoint and the identity universe load that JSON for every import;
  - a column on `race_imports`: every `select(RaceImport)` would load it, and a `deferred` column fails under async lazy loading.
- **Loading.** `staged_document.load(db, imp) -> ParsedResults` replaces `_reload_results_document`, `_reload_parsed_from_storage`, the two LRU caches, the 410 "re-upload" path and the "release the connection before SFTP" commits. Corrections stay patches in `parse_meta_json["corrections"]` and are applied after loading, as today. **This closes privacy-audit finding A** (process caches holding unfiltered rows).
- **Metadata.** The stage step writes the same public `parse_meta_json` keys `/parse` writes today: `header`, `conditions`, `categories_found`, `n_rows_resultados`, `n_rows_general` (= 0), `categories` with counts and completeness, and `unreadable_rows`. The wizard's resume path needs these. It also writes:
  - the internal keys commit depends on: `results_ext`, `results_storage_path` and `parse_uuid` (the commit storage move needs `parse_uuid`);
  - `source: "results_skill"` and `profile_id`.
- **Deletion.** The document row is deleted on full commit (together with `parse_meta_json = None`, as today) and on discard. It survives a partial commit until `commit-pending` finishes. This is data minimization: once results are committed they live in `race_results`, and the evidence file (R-23) is the source of record.
- **Clock.** `imported_at` comes from the database clock, not the operator's laptop. `_identity_rebuild_needed` compares it with `RaceIdentityCandidate.created_at` (server clock), so a skewed laptop clock could skip a needed rebuild.
- **Same-content re-stage.** A pending import with the same SHA-256 is returned as is (today's behaviour). A committed one is refused as `already_committed`.

## R-21 — Target selection and credentials (FR-047)

**Decision.**

- **Local by default.** The local target reads `backend/.env` through `app.config`. It refuses to run unless all of these hold:
  - `MYSQL_HOST` is local: `localhost`, `127.0.0.1`, `::1`, the compose service `mysql`, or `host.docker.internal`;
  - `APP_ENV` is not `production`;
  - if `backend/.env.production` exists, the `(MYSQL_HOST, MYSQL_DB)` pair differs from the one in it. The comparison is internal and no value is printed.
- **Production** requires `--target production --confirm produccion`, so the confirmation names the target. Then it:
  - loads only the keys it needs from `backend/.env.production` before importing `app.*`, following the `bitacora_snapshot._load_env` pattern: `MYSQL_*`, `HOSTINGER_SFTP_*` and `HOSTINGER_PUBLIC_BASE_URL`, with `APP_ENV=development`, `AI_ENABLED=false` and `STRAVA_ENABLED=false`;
  - refuses if SFTP is not fully configured, because a production import must not point at a file on a laptop;
  - refuses if the database's `alembic_version` differs from the repository head, because models and schema must match before writing;
  - scrubs every environment value from error messages.
- **The skill never stages to production on its own initiative.** It does so only after the operator asks for it in the session, and it shows the command before running it.
- **`--dry`** resolves the target and validates everything, then writes nothing.

**Rationale.** A local backend pointed at the production database writes to production (runbook §12.2), so the default must be safe by structure, not by convention. Naming the target in the confirmation, instead of repeating the database name, keeps every `.env.production` value out of the transcript.

## R-22 — Who stages: attribution and RBAC parity for a script that bypasses HTTP (FR-048)

**Decision.**
- `--user-id` is required. It must be an active user with role `admin` or `coach` in the target database: today's `_load_actor`, and the same roles the removed route required.
- That user becomes `imported_by_user_id`, which also drives club scope (`permissions.py`) and the dry-run roster, exactly as today.
- Audit: `record_audit(create, race_import)` with `AuditContext.for_user(actor)` and `meta.via = "results_skill"`.
- The staged import stays pending and invisible outside the import review. Only an authenticated coach can commit it in the app, so the audit record of the commit still names the person who decided.
- Anyone holding the database credentials can already write anything. The check prevents mistakes, not an attacker, and the contract says so.

## R-23 — Evidence file (FR-049)

**Decision.**
- **Upload.** `stage` uploads the original file through `storage_sftp.upload_bytes` to `race-imports/pending/{parse_uuid}/resultados.{pdf|csv}`. This is today's path scheme, so commit's move to `race-imports/committed/{parse_uuid}/` keeps working.
- **Validation.** Content is checked by magic bytes: `%PDF-` for PDFs; for delimited text, UTF-8 plus a delimiter (today's `_is_csv_like`). The size cap is a script constant, today's 8 MB.
- **Order.** Extract and validate locally first, upload second, insert the import third, in one database transaction. If the insert fails, the uploaded object is deleted best-effort. (Today a failed parse leaves orphaned files.)
- The app never reads the stored file again (FR-049). Retention stays deferred (FR-043).

## R-24 — Corrections are revisions, and revisions become real (FR-027 corrected, SC-006)

**Decision.**
- **Staging.** `stage` calls `detect_revision`. A different reading of a válida whose `(series, sequence_number)` is already committed becomes a pending revision. An identical SHA-256 is refused (`already_committed`).
- **Dry-run, revision branch.** When the import is a revision, dry-run returns the shape the wizard already renders: `is_revision: true`, `parent_event_id`, `diff_summary`, `diff_rows` and `warnings` (`ImportDryRunRevisionResponse` in `frontend/src/types/raceImports.types.ts`). `revision.compute_diff` computes it.
- **Commit, revision branch.** The diff is applied with `revision.commit_revision`:
  - updates, and soft-deletes through `deleted_at`;
  - one `race_result_revisions` row per change;
  - a pessimistic lock on the event;
  - `parent_import_id` and `revision_reason` set, with the reason mandatory when anything is removed.

  The existing AI-run invalidation then runs. The non-revision commit path is unchanged.
- **Identity-aware matching.** `compute_diff` predates 044. It matches by `(category, normalized_name)` with a fuzzy fallback, which is wrong now that two competitors may share a name (044 signatures). It is adapted to:
  - resolve each row with the same read-only resolution the ingestor uses (signature plus discriminator);
  - diff by `(category, competitor_id)`;
  - keep the fuzzy fallback only for rows whose signature is new.

  Rows of new competitors pass the per-import identity gate (feature 045), like any staged import.
- **Links and deleted rows.** Athlete links are never overwritten (existing `commit_revision` rule). Read paths already filter `race_results.deleted_at IS NULL` (24 uses across the race module). A test sweep pins that filter on every surface that consumes results: `history`, `field_metrics`, `standings`, `results_read`, the analyst context and the family views.
- **Legacy partial commits** (R-27) are completed through this path: re-staging the válida yields a revision whose diff creates the rows of the pending categories.

**Rationale.** The owner chose revisions over a single-row editor. The diff and apply logic exist and are tested, and so does the UI. What is missing is the wiring and the identity-aware match, which is less work than a new editor and keeps a single audited correction path. The wiring is an independent phase in `tasks.md`, so the owner can defer it without blocking the rest.

## R-25 — The GENERAL sheet is retired (FR-024 for every season)

- **What it is.** The optional GENERAL upload is the Liga's cumulative season standings. It never creates results: the ingestor only upserts competitors from it (`_upsert_competitor_from_general`) and feeds their names to the identity universe.
- **Why it can go.** Historical staging never accepted it, and FR-024 already excludes cumulative standings files.
- **Decision.** The skill stages only the per-válida results file, for every season.
  - New imports are `kind = resultados`. The `general_*` columns stay for legacy rows.
  - Removed as dead code: the ingestor's GENERAL step, `GeneralRow`, `parse_general_pdf`, `_parse_general_with_timeout`, and the GENERAL handling in the identity loader (`GENERAL_VALIDA_NUM`).
- **Side effect.** Fewer third-party minors get a competitor record without any result, which is data minimization. This is recorded in `spec.md` as a planning adjustment.

## R-26 — Remove the upload surface, and prove it stays removed (FR-044, SC-014)

**Backend.** Delete:
- `POST /api/race-analysis/imports/parse` (`parse_import`);
- its upload-only helpers: `_is_pdf`, `_is_csv_like`, `_read_with_cap`, `_validate_results_magic`, `_validate_general_magic`, the dead `_sanitize_filename` and `_compute_sha256`, the related constants and the `File`/`Form`/`UploadFile` imports;
- `_response_for_already_staged`;
- the settings used only by the route: `race_max_pdf_mb`, `race_parse_timeout_seconds`, the unused `race_pending_ttl_hours`, and their `.env.example` lines;
- the audit-registry entry `("POST", "/api/race-analysis/imports/parse")` (`test_audit_coverage` fails otherwise);
- `scripts/stage_race_history.py`;
- the mutmut entries that name the parsers.

`python-multipart` and `pdfplumber` stay in `requirements.txt`: four other routes accept uploads, and the newsletter PDF reader uses pdfplumber.

**Frontend.**
- Delete wizard step 1 (upload, metadata, conditions, prefill), `RaceUploadZone`, `parseRaceImport`, `useImportParse`, `ImportParseRequestFields`, `useImportPrefill` and its types, and `VITE_RACE_MAX_PDF_MB`.
- The wizard becomes a review of a staged import and requires `?import=<id>`. Without it, `/competitions/import` and `/competitions/:id/import` redirect to the board (`/competitions/imports?seccion=cargas`).
- Every "Cargar resultados", "Importar resultados" and "Cargar archivo" entry point is removed or rewritten (full list in `contracts/ui-review-only.md`). The new copy explains that loads are prepared outside the app and appear in *Cargas* for review.

**Structural guards.**
1. A backend test walks `app.routes` and asserts that the only endpoints with a file parameter are the four known non-results uploads: training route file, session media, and course variant create and replace. Any new upload fails CI until it is added deliberately.
2. A denied-path test: a multipart POST to the old path returns 404/405 for every role.
3. A frontend test asserts there is no `input[type=file]` in the competitions import area, the board, the competitions list and detail pages, or the results tab.

## R-27 — Imports staged before the change

- **Pending imports without a staged document** can no longer be reviewed, because their rows lived only in the stored file.
  - Every review endpoint except `GET` and discard returns `409 {"detail": "restage_required"}`.
  - The board shows them with a neutral badge and only *Descartar*.
  - `ResumeStatusNotice` explains that the load must be prepared again.
- **Committed imports with `pending_categories`** (partial commits made through the old path): `commit-pending` returns the same 409. The fix is to re-stage the válida with the skill; that yields a revision whose diff creates the missing categories (R-24).
- **No data migration touches either group.** The runbook's pre-deploy checklist counts both with one SQL query, so the owner knows what to re-stage.

## R-28 — Real official files in the repository

- `tests/fixtures/race/valida_iv_2026_resultados.pdf` and `valida_iv_2026_general.pdf` are real official files (flagged in R-14). `valida_i_2026_sevilla.csv` is synthetic.
- Once the parser tests, and the four ingestor tests that read the two PDFs, are retired or moved to synthetic builder output, both PDFs are deleted from the tree.
- They remain in git history. Purging it means rewriting `main`, which is an owner decision. It is recorded as a follow-up in the privacy audit and not done here.

## R-29 — Skill packaging and session guardrails

- **Skill.** `.claude/skills/race-results-load/SKILL.md` (English, instruction corpus), with `references/masked-view.md`, `references/reading-profile.md` (schema plus a synthetic worked example) and `references/manifest.md`. Trigger phrases in Spanish and English ("cargar resultados de la válida …", "load race results").
- **CLI.** `backend/scripts/race_results.py`, with subcommands `mask`, `profile-check`, `apply`, `compare` and `stage`. The engine lives in `app/services/race/results_skill/`; a test pins that no router imports it.
- **Outputs.** Under the git-ignored `output/race-results/<run>/`:
  - `masked/`: the only folder the LLM reads;
  - `private/`: extracted rows, never read by the LLM.

  Official files and the manifest live outside the repository (the old script's rule, kept).
- **Stdout discipline.** Every subcommand prints only ids, counts, structural category labels, ordinals, codes and paths, never a name, club, city, bib or time. A test sweeps every subcommand's output against the synthetic names.
- **Claude Code guardrails.** The project's `.claude/settings.json` gains `permissions.deny` rules for reading `output/race-results/**/private/**`. `SKILL.md` tells the operator where to keep official files so a matching local deny rule can be added. These rules are defence in depth; the masked view is the control. The exact rule syntax is checked at implementation.

## R-30 — Local-first loop and the FR-007 check

- **The loop.**
  1. `mask`
  2. profile (LLM)
  3. `apply`: counts, completeness, leak check
  4. optional `compare`
  5. `stage` (local)
  6. review and commit in the local app
  7. `stage --target production`
  8. the coach reviews and commits in production
- **`compare`** reads the committed results of the same válida from the target database, read-only, and prints matched, changed, missing and extra counts per category. It is the FR-007 check for the 2026 válidas already loaded, and a preview of what a revision would do.
- **Identity decisions taken locally do not travel.** Production computes its own queue against production competitors, and the coach decides there.

## R-31 — What moves out of the web wizard

- **Válida metadata** (series, kind, level, season, válida, date, venue, event name) moves to the manifest and is validated by the same rules as the removed form (`series_kind`, `series_level`, ISO date).
- **`race_event_id`** in the manifest replaces the calendar prefill of feature 015. The script reads series, season, válida, date and venue from that event and its series in the target database. The prefill was client-side composition, so no endpoint is removed for it.
- **Race conditions** (climate, temperature, surface, altitude, notes) are no longer captured at load. The coach enters them on the válida's existing *Condiciones* tab (`ConditionsTab` → `RaceConditionsCard`). Staged imports carry empty `conditions`.
