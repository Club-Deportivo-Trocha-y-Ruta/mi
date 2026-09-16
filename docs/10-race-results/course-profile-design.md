# Race Course Profile — Technical Design

**Project:** Club Deportivo Trocha y Ruta — Youth XCO
**Feature:** 043 — race course profile (`specs/043-race-course-profile/`)
**Module:** `backend/app/services/race/course/` + course routes on `backend/app/routers/race_events.py` + `frontend/src/components/race/course/`
**Status:** Shipped — all 7 implementation phases landed (Setup, Foundational, US1–US5, Polish in progress)
**Date:** 2026-09-16
**Audience:** backend/frontend developers extending this module, `data-privacy-guard` on future audits, on-call debugging a course upload
**Authoritative source documents:** `specs/043-race-course-profile/plan.md`, `data-model.md`, `contracts/*.md`, and the "Phase N completion notes" appended to the bottom of `specs/043-race-course-profile/tasks.md`. This document reflects the working tree as verified on 2026-09-16, including design decisions made mid-implementation that are not in the original plan.

---

## 1. Overview

A válida (a single race in a series) can now carry an optional **course profile**: one or more route **variants** extracted server-side from a GPX the coach records with a personal device, a **laps-per-category table**, and a **structured track description**. From this, results and the race AI analysis derive real distance/speed and course facts without ever storing or estimating them.

Three ideas run through every design choice in this feature:

- **The upload is the coach's personal data, not the club's.** Only the simplified single-lap geometry (position + elevation) is kept; the original file, its timestamps and every device/vendor extension are discarded in memory and never reach the database, a log line, or an AI prompt.
- **Nothing about the course is estimated.** Distance and speed are computed at read time from stored integers, or shown as "sin dato" — never persisted, never guessed when an input is missing.
- **The AI analyst treats the course like race conditions**: a strict present/absent veto, never a "probably" statement about terrain it wasn't told about.

## 2. Data model

Two new tables and four new columns on `race_events`. Full column-level detail lives in `specs/043-race-course-profile/data-model.md` §1–§5; this section summarizes what a developer needs day to day.

### 2.1 `race_course_variants`

One row per named route variant of one válida (e.g. "Circuito completo", "Recorrido reducido"). Holds only the extracted lap — never a file, never a timestamp, never a physiological field.

| Column | Type | Notes |
|---|---|---|
| `id` | `BigInteger` PK | |
| `race_event_id` | FK `race_events.id`, `ondelete=CASCADE` | Deleted with the válida. |
| `label` | `String(60)` | Unique per válida (`uq_race_course_variants_event_label`). |
| `lap_distance_m` | `Integer` | Length of the unsimplified lap, 300–15 000 m. |
| `elevation_gain_m` | `SmallInteger`, nullable | `NULL` when the recording had no elevation. |
| `has_elevation` | `Boolean` | |
| `point_count` | `SmallInteger` | Points in `geometry` (≥ 20, normally ≤ 800). |
| `geometry` | `JSON` | `list[[lat, lon, ele|null]]`, lat/lon rounded to 6 decimals, ele to 1. |
| `detection_method` | `String(16)` | `closed_loop` \| `manual` \| `single` — see §3. |
| `recorded_laps` | `SmallInteger`, default `1` | What the platform believes the recording contained. |
| `source_sha256` | `String(64)` | Hash of the discarded upload, used only to reject a re-upload of the same file (`409 duplicate_recording`); never used to retrieve anything. |
| `created_by_user_id` | FK `users.id`, `ondelete=RESTRICT` | |
| `created_at` / `updated_by_user_id` / `updated_at` | `ActorTimestampMixin` | |

Deleting a variant referenced by a category setup is rejected with `409 variant_in_use`; replacing its file (`PUT .../file`) overwrites geometry and figures in place, keeping the same `id`.

### 2.2 `race_course_category_setups`

One row per (válida, category): the laps ridden and the variant used.

| Column | Type | Notes |
|---|---|---|
| `id` | `BigInteger` PK | |
| `race_event_id` | FK `race_events.id`, `ondelete=CASCADE` | |
| `category_id` | FK `race_categories.id`, `ondelete=RESTRICT` | |
| `variant_id` | FK `race_course_variants.id`, `ondelete=RESTRICT` | Must belong to the same válida (service-level 422 `variant_not_in_event`, backed at the DB level by the same `RESTRICT`). |
| `laps` | `SmallInteger` | 1–20, `CheckConstraint ck_race_course_setups_laps_range`. |
| `created_at` / `updated_by_user_id` / `updated_at` | | |

Unique on `(race_event_id, category_id)`. `PUT /course/setups` replaces the whole table for the válida in one transaction (rows not in the payload are deleted, present ones upserted).

### 2.3 `race_events` — four new nullable columns

| Column | Type | Purpose |
|---|---|---|
| `terrain_type` | `Enum(TerrainType)` (`sendero \| trocha \| mixto \| pista \| pavimento`) | |
| `technical_difficulty` | `SmallInteger` | 1–5, `CheckConstraint ck_race_events_difficulty_range`. |
| `key_sectors` | `JSON` (`list[str]`, closed vocabulary) | ≤ 8 codes, e.g. `subida_larga`, `rock_garden`, `singletrack`. |
| `course_notes` | `Text`, ≤ 1 000 chars | Free coach notes. **Never** reaches an AI prompt or a trace — see §6. |

`RaceEventRead` gains these four fields plus `has_course_data: bool`. Note this is not the only `has_course_data` in the codebase — see the deviation box in §4.

### 2.4 Migration

Single Alembic revision (`down_revision="d5b125474e2b"`), local head `5ba077132b3b` per the Phase 1+2 completion notes: creates both tables, adds the four columns and the `terraintype` MySQL enum, symmetric downgrade. The `-m mysql` round-trip against real MySQL 8.4 is a **developer follow-up before merge** — the implementation sandbox has no local MySQL, so this feature's own migration and `tests/mysql/test_race_course_models.py` were verified with an isolated sqlite/ORM harness only (see Phase 1+2 completion notes in `tasks.md`).

## 3. GPX processing algorithm

`app/services/race/course/gpx_processing.py::process_gpx(content, *, recorded_laps=None) -> ProcessedLap` is pure, synchronous, in-memory, and never raises anything other than `CourseProcessingError(code)` — verified constants, read directly from the module:

```python
MIN_LAP_M = 300
MAX_LAP_M = 15_000
CLOSURE_RADIUS_M = 30
LAP_LENGTH_TOLERANCE = 0.10
SMOOTH_WINDOW_M = 30
GAIN_HYSTERESIS_M = 3
SIMPLIFY_EPSILON_M = 3.0
MAX_POINTS = 800
MIN_POINTS = 20
MAX_DISTANCE_ERROR = 0.01
```

### 3.1 Pipeline (normative order)

1. **Sniff & decode**: gzip/zip magic bytes → `compressed_not_allowed`; UTF-8 (BOM-tolerant) decode failure → `malformed`.
2. **Safe parse**: `defusedxml` first (`EntitiesForbidden`/`DTDForbidden`/`ExternalReferenceForbidden` → `xml_unsafe`), root tag must be `gpx` → else `not_gpx`, then `gpxpy.parse` (`GPXException` → `malformed`).
3. **Privacy strip** (`_strip_and_flatten`): `remove_time(all=True)`; every extension at gpx/track/point level cleared; per-point `time`, `speed`, `symbol`, `comment`, `name`, `description`, `source`, `link` cleared; `routes`/`waypoints` dropped; `creator`/`author_*`/`copyright_*`/`link_*`/`keywords` cleared. Segments of every track are merged into one flat point list (a device auto-pause must not split the lap in two); once this step returns, the `GPX` object is never referenced again — only `list[Location(lat, lon, ele)]` survives.
4. **Sanity**: empty point list → `no_track_points`; any point out of range/NaN → `no_position`.
5. **Cumulative distance**: haversine 2-D via `gpxpy.geo.distance`.
6. **Lap extraction** (the core algorithm, see §3.2).
7. **Range check**: `< MIN_LAP_M` → `too_short`; `> MAX_LAP_M` → `too_long`.
8. **Elevation**: computed only `if has_elevation` (every lap point has `ele`); otherwise `elevation_gain_m = None` and every stored elevation is `null` (never a mix).
9. **Simplification**: iterative Ramer-Douglas-Peucker; `< MIN_POINTS` after simplifying → `too_few_points`.
10. **Round & return**: lat/lon to 6 decimals, elevation to 1.

### 3.2 Lap extraction (`_extract_lap`)

- `recorded_laps` given (coach override) → `method="manual"`, lap = prefix of points up to `total_distance / recorded_laps`.
- Else, search for the first point that closes within `CLOSURE_RADIUS_M` (30 m) of the start after at least `MIN_LAP_M` (300 m) traveled:
  - No closure found → `method="manual"`, `laps=1`, the **whole recording** is treated as one lap.
  - Closure found, and the remaining distance after it is `< 0.8×` the first-lap distance (i.e. the recording is essentially one lap that happens to close) → `method="single"`.
  - Closure found and remaining distance is `≥ 0.8×` the first lap: look for a **second** closure and validate `|second_closure − 2×first_closure| / first_closure ≤ LAP_LENGTH_TOLERANCE` (10%) → `method="closed_loop"`, `laps_detected = round(total / first_lap_distance)`. If that second closure doesn't validate (e.g. a figure-eight that brushes the start mid-lap), it falls back to `method="manual"`, `laps=1`, whole recording as one lap — the false closure is rejected, not silently accepted.

### 3.3 Elevation smoothing — implementation detail beyond the contract

The binding contract (`contracts/gpx-processing.md` §2 step 8) describes "a distance-windowed moving average" of radius `SMOOTH_WINDOW_M` (30 m) followed by `GAIN_HYSTERESIS_M` (3 m) hysteresis accumulation. What shipped in `_smooth_elevation` applies that same box average **twice** (`_box_average` called on its own output). The module docstring records why: a single pass at 30 m still leaves point-to-point GPS noise above the SC-005 target (< 5 m/km of spurious gain on a flat course) at typical recording density (~1 point/second); two passes of the same box filter approximate a wider-support kernel without touching the hysteresis threshold, and this is what the "flat circle with ±4 m noise → gain < 20 m" test actually measures against.

### 3.4 Simplification — segment-bounded RDP, not textbook RDP

`_perpendicular_distance` measures each candidate point against the **bounded segment** between the two endpoints being considered, not the infinite line through them (via law-of-cosines projection clamped to `[0, segment_length]`, using only pairwise haversine distances — no reprojection to a local x/y plane). `gpxpy.geo.simplify_polyline` measures against the infinite line, which would incorrectly collapse an out-and-back recording (every point on the return leg sits at ~0 distance from the infinite line through the outbound leg, even when it is hundreds of meters from the real segment). This is why the feature has its own RDP implementation instead of reusing `gpxpy`'s. Simplification runs iteratively: start at `SIMPLIFY_EPSILON_M` (3 m); if the result still exceeds `MAX_POINTS` (800), retry at `epsilon + 1` as long as the 2-D length of the simplified lap stays within `MAX_DISTANCE_ERROR` (1%) of `lap_distance_m`; stop at the last epsilon that respects that bound (may still exceed 800 points rather than distort the shape further).

### 3.5 Error codes

`CourseProcessingError(code)`: `not_gpx`, `xml_unsafe`, `malformed`, `no_track_points`, `no_position`, `too_short`, `too_long`, `too_few_points`, `compressed_not_allowed`. (`file_too_large` and `unsupported_media_type` are applied by the router before `process_gpx` is ever called — see §5.) Full Spanish message table in `contracts/course-api.md` §6, summarized operationally in `runbook-ops.md`.

## 4. Derived result figures (never stored, never estimated)

`app/services/race/course/derived.py::derive_figures(setup, status, race_time_ms, laps_behind) -> DerivedFigures` is the single pure function reused by three call sites: `results_read.py`, `analytics_charts.py`, and (indirectly, via the same rule) the AI course context. `setup` is duck-typed (`.laps`, `.variant.lap_distance_m`, `.variant.elevation_gain_m`) so tests can pass a lightweight double.

```text
setup is None                                         → all four fields None
status not in {finished, minus_laps} or no race_time  → all four fields None
status == minus_laps and laps_behind is None          → all four fields None
laps_completed = setup.laps - (laps_behind or 0)      (≤ 0 → all four fields None, defensive)
distance_km    = round(laps_completed * lap_distance_m / 1000, 1)
avg_speed_kmh  = round(distance_km / (race_time_ms / 3_600_000), 1)   # from the unrounded distance
```

Rounding uses `Decimal` + `ROUND_HALF_UP` on values built from the original integers (laps, metres, milliseconds), not from floats that already went through one division — the module docstring documents a concrete tie (`1*300/1000 / (21_600_000/3_600_000)`) that would otherwise round the wrong way under native float/banker's rounding.

**Deviation from the plan — `has_course_data` on the results endpoint is a narrower, deliberately different definition than the course tab's own.** The contract (`contracts/results-derived-figures.md`) promised `get_event_results` runs "exactly one more statement than before." The as-shipped implementation initially added a second, conditional `EXISTS` query against `race_course_variants` (firing only when no setups existed yet) to widen `has_course_data` to "any variant, even unassigned." That was caught and reverted during Phase 3+4 verification: `has_course_data` on `EventResultsRead` is now `bool(setup_by_category)` alone — a variant uploaded but not yet assigned to any category shows no distance/speed for any row either way, so gating column visibility on setup existence is both the more useful signal to a coach and what keeps the query count a hard, unconditional +1. This is intentionally different from `course/service.py::has_course_data(event)` (any variant OR any description field — used by the Circuito tab's empty-state check) and from `race_events_svc.event_has_course_data(db, event)` (the one used by `RaceEventRead` on list/detail, a single `EXISTS` query because `course_variants` isn't eager-loaded there). Three functions, three call sites, three intentionally different questions — do not assume they can be unified without checking which UI surface calls which.

**Deviation from the plan — the season/evolution surface for `avg_speed_kmh` is not where the plan named it.** `plan.md`/`data-model.md` pointed at "the athlete per-válida rows in `analytics.py`" and `SeasonInsightsPage.tsx`. Neither exists as such: `analytics.py` only holds DataFrame-returning AI-pipeline internals with no per-válida schema, and `SeasonInsightsPage.tsx` renders a per-athlete season aggregate with no per-válida breakdown. The real, and only sensible, surface — found by reading the working tree during Phase 3+4 — is `EvolutionPoint` (`backend/app/schemas/athlete_race_analysis.py:486`) populated by `build_evolution` (`backend/app/services/race/analytics_charts.py:489-500`, calling `derive_figures` per válida), rendered in `frontend/src/components/athletes/ai/EvolutionChart.tsx`'s `EvolutionTable` (table-view tab, one row per válida, column formatted `"{value.toFixed(1)} km/h"` or "sin dato"). No aggregate (mean/best/trend) of speed is computed anywhere, per FR-016/R-11.

## 5. API surface

All seven endpoints hang off the existing race-events router, under `/api/race-analysis/race-events/{race_event_id}` (`backend/app/main.py:177` mounts `race_events.router` at that prefix). Verified directly against `backend/app/routers/race_events.py`.

| Method | Path (relative to `/{race_event_id}`) | Roles | Purpose |
|---|---|---|---|
| `GET` | `/course` | admin, coach, parent (scoped) | Whole course: variants (with geometry), setups, description, prefill suggestion, parent `my_categories`. |
| `POST` | `/course/variants` | admin, coach | Multipart GPX upload → process → create variant. `201`. |
| `PUT` | `/course/variants/{variant_id}/file` | admin, coach | Multipart GPX upload → reprocess → replace geometry/figures in place, same `id`. `200`. |
| `PATCH` | `/course/variants/{variant_id}` | admin, coach | Rename (`label`). |
| `DELETE` | `/course/variants/{variant_id}` | admin, coach | Delete; `409 variant_in_use` when a setup references it. |
| `PUT` | `/course/setups` | admin, coach | Full replace of the laps-per-category table. |
| `PATCH` | `/course/description` | admin, coach | Partial update of the four description fields (`exclude_unset` semantics — explicit `null` clears, an absent field is untouched). |

Every mutation returns the full `CourseRead` and calls `record_audit(entity_type=race_event, changed_fields=[...])`. `GET /course` is guarded by `require_role([admin, coach, parent])`; the parent/coach split inside the handler is `allowed_athlete_ids_for(current_user, db)` returning `None` for admin/coach (unrestricted) or a `set[int]` of the caller's own athlete ids for parent — the same helper that already gates results and standings reads. Full request/response shapes and the complete error-code table are in `specs/043-race-course-profile/contracts/course-api.md` §1–§6; the operational summary for support debugging is in `runbook-ops.md` §10 (added by this same change).

## 6. AI `course_block` integration

The race analyst treats course facts exactly like race conditions: a strict present/SIN-DATO veto, never an inference. State, loader, formatter and prompts, verified against the working tree:

- **State**: `RaceAnalystState.course_context: dict[int, dict]` (`backend/app/services/race/ai/state.py`), keyed by `valida_num`, every requested válida present as a key (absence is representable, `{}` when the válida/category has no setup).
- **Loader**: `fetch_course_context(db, season, validas, category_id)` — **deviation from the plan**: the plan named `backend/app/services/race/ai/queries.py`, which does not exist for this purpose; the function actually lives in `backend/app/services/race/queries.py`, alongside the sibling `fetch_event_conditions` it mirrors (corrected in the Phase 5+6 dispatch before implementation, per the tasks.md completion notes). It selects only the allow-listed columns — `course_notes` is never in the select list, a structural exclusion rather than a runtime filter.
- **Formatter**: `format_course_meta(course: dict | None) -> str | None` in `backend/app/services/race/agents/analyst.py:534`. Returns `None` (the veto trigger) when none of the six fields (`lap_distance_m`, `elevation_gain_m`, `laps`, `terrain_type`, `technical_difficulty`, `key_sectors`) is present; otherwise emits only the bullets for fields that are actually set, e.g.:

  ```text
  - Distancia por vuelta: 4,2 km
  - Desnivel positivo por vuelta: 110 m
  - Vueltas de la categoría: 3 (distancia total 12,6 km)
  - Terreno: mixto
  - Dificultad técnica: 4/5 (técnico)
  - Sectores clave: subida larga, rock garden
  ```

- **`course_block` vs `course_by_valida` — two different shapes for two different prompts, by design.** The per-válida analysis (`race_analyst_v3.md`) receives a single `course_block: str | None` — one formatted block for the one válida being analyzed. The season summary (`race_season_summary_v3.md`) instead receives `course_by_valida: dict[int, str]` — one `format_course_meta` block per válida that actually has course data, rendered in a loop ("**Válida N:** ..."); a válida absent from the dict is covered by the section's own SIN-DATO fallback rather than an empty per-válida entry. Both are built in `AnalystV3Input` (`analyst.py:674-678`) and threaded into `_build_v3_context` as `"course_block"` / `"course_by_valida"` (`analyst.py:1499-1500`).

  Prompt fragment (both v3 templates, immediately after the conditions block):

  ```jinja
  {% if course_block %}
  ## Circuito registrado

  Estas son las **únicas** características del circuito registradas. No agregues
  ninguna otra ni estimes distancias o desniveles no listados.

  {{ course_block }}
  {% else %}
  ## Circuito — SIN DATO

  PROHIBIDO mencionar distancia, vueltas, terreno, desnivel, altimetría o
  dificultad técnica del circuito.
  {% endif %}
  ```

  The `race_analyst_v2` prompts are untouched; they render correctly with the extended context (superset of keys) for rollback via `RACE_AI_PROMPT_VERSION=race_analyst_v2`.

- **Deviation found and fixed after implementation — season-launch bug in `analyst_agent.py`.** `_build_v3_inputs`'s season branch originally built `course_by_valida` by iterating `state["valida_nums"]`, which is **empty** on a global/season launch — the common case where the coach does not pick specific válidas. The actual válidas raced that season only exist as keys of `state["course_context"]` (populated in `load_race_data.py` from the athlete's own results when `valida_nums` is empty). Left as first implemented, the season summary's course block would silently render "Circuitos — SIN DATO" even when every válida had a registered course profile, on the feature's most common path. Fixed by iterating `sorted(state["course_context"].keys())` instead; two regression tests were added (`tests/services/race/ai/nodes/test_analyst_agent_resolution.py`).
- **Golden eval**: two new v3 cases, `backend/evals/race_analyst/golden_v3/case_010_course_present.json` and `case_011_course_absent.json`. The absent case's `forbidden_terms` include `km`, `vuelta`, `vueltas`, `terreno`, `desnivel`, `técnico`, `dificultad`. `RACE_EVAL_THRESHOLD` stays `0.75`. **`pytest -m golden` for these two cases has not yet been run with a real API key** in this implementation environment (the test module's `_skip_no_api` guard skips it without one) — a developer with `RACE_AI_API_KEY` must run it, confirm the composite ≥ 0.75, and regenerate the baseline before merge; see `runbook-ops.md` §3.3 for the existing procedure.
- **Two open, non-blocking observations from the data-privacy-guard review of this AI diff** (left open deliberately, not privacy issues): (1) the pre-existing (feature 011) conditions-absent veto text forbids mentioning "terreno", while the course block, when present, prints "Terreno: mixto" a few lines below — a wording overlap between two independently-gated sections, not introduced by this feature; (2) `app/services/race/eval/scorer_v3.py::_DATA_BLOCK_KEYS` does not include `course_block`/`course_by_valida`, so the golden eval's grounding subscore does not currently reward a model correctly citing a course-specific number — worked around in the two new cases by keeping course digits out of grounded fields, but the scorer gap needs its own follow-up before the golden lane can be trusted to score course-context usage.

## 7. UI map

| Component / page | Lives in | Role | Notes |
|---|---|---|---|
| `CourseTab` | `frontend/src/components/race/course/CourseTab.tsx` | coach/admin (read-write), parent (read-only when reused) | Composes `VariantsCard`, `CategorySetupTable`, `CourseDescriptionCard`, `CourseSummary`. Empty state offers "Agregar variante" / "Describir la pista". |
| Circuito tab | `frontend/src/routes/competitions/CompetitionDetailPage.tsx` | coach/admin | New `TabValue = "circuito"`, inserted after "Condiciones", lazy-loaded like the other tabs. |
| Import wizard panel | `frontend/src/components/competitions/import/ImportWizard.tsx`, step 3 | coach/admin | Renders `<CourseTab compact />` after a successful commit, under "Circuito (opcional)"; `STEPS` and the focus contract are unchanged. |
| `VariantUploadDialog` | `.../course/VariantUploadDialog.tsx` | coach/admin | GPX upload sheet; shows the detected method (`closed_loop`/`manual`/`single`) for confirmation, with a "No, indicar vueltas" path that re-submits via `PUT .../file`. |
| `VariantsCard` | `.../course/VariantsCard.tsx` | coach/admin | List, rename, replace, delete (409 toast naming categories). |
| `CategorySetupTable` | `.../course/CategorySetupTable.tsx` | coach/admin | Laps 1–20 + variant per category; prefill banner from `suggested_setups`. |
| `CourseDescriptionCard` / `EditCourseDescriptionDialog` | `.../course/CourseDescriptionCard.tsx`, `EditCourseDescriptionDialog.tsx` | coach/admin (edit), parent (read-only) | Tri-state card copied from `RaceConditionsCard`. |
| `CourseSummary` | `.../course/CourseSummary.tsx` | coach tab + both parent pages | Shared read-only view: figures line, laps by category (highlighted for the parent's own child via `my_categories`), description, `<Suspense>` around the map/profile. |
| `CourseMap` (lazy) | `.../course/CourseMap.tsx` | shared | Dynamic Leaflet import, `L.polyline` + `fitBounds`; `role="region"`, `aria-label="Mapa del circuito {label}"`. |
| `ElevationProfile` (lazy) | `.../course/ElevationProfile.tsx` | shared | Recharts area chart, ≤ 200 samples; `role="img"`, `aria-label` states min/max/gain. |
| Results columns | `frontend/src/components/competitions/results/ResultsTable.tsx` | coach + parent (same table) | "Distancia" / "Vel. prom." columns, shown only when `has_course_data`; "sin dato" for `null`. |
| Evolution table column | `frontend/src/components/athletes/ai/EvolutionChart.tsx` (`EvolutionTable`) | coach | `avg_speed_kmh` per válida, "sin dato" when absent — see the §4 deviation note on where this surface actually lives. |
| Parent results card | `frontend/src/routes/parents/competitions/ParentCompetitionResultsPage.tsx` | parent | `useRaceCourse(id)` with `retry: false`; `404` renders no card (no toast, no error state) — this is the normal state for a parent whose child is not related to the válida. |
| Parent calendar card | `frontend/src/routes/parents/calendar/ParentEventDetailPage.tsx` | parent | Same `CourseSummary`, shown when the calendar event links a válida; same 404 handling. |

Progressive rendering: figures, laps and description are plain DOM, rendered before the lazy map/chart chunks resolve, so a parent on throttled 3G sees text first (FR-024).

## 8. Privacy invariants

`specs/043-race-course-profile/privacy-audit.md` (task T063, the dedicated `data-privacy-guard` audit) had **not landed** at the time this document was written. Until it does, the binding invariants are the ones in `data-model.md` §7 and `plan.md`'s Constitution Check, reproduced here with their current verification status:

| Invariant | Verified how |
|---|---|
| A stored variant never contains keys other than the schema in §2.1; `geometry` entries are 3-tuples of numbers/null; no `time`, `hr`, `cad`, `atemp`, `power`, `creator`, `author` anywhere in the row or the response. | `_strip_and_flatten` (§3.1 step 3) clears every such field before the point list is built; the `GPX` object is discarded immediately after. Asserted by a hypothesis test over synthetic GPX with randomized Garmin extensions (`test_gpx_processing.py`). |
| Logs from the processing path carry only ids, counts and codes. | `race_course_variant_processed` logs `race_event_id`, `variant_id`, `point_count`, `lap_distance_m`, `detection_method` — no filename, no coordinates (`course/service.py::create_variant`/`replace_variant_file`). The original filename is explicitly discarded (`del filename`) at the top of both functions, never persisted or logged. |
| `course_notes` never reaches an AI prompt or a trace. | Structural exclusion at the query level (`fetch_course_context` never selects the column) plus the existing redact-always tracing (`docs/10-race-results/runbook-ops.md` §8.6). |
| Parents see course data only for válidas their own children are related to, and `my_categories` only their own athletes. | `_get_course_for_parent` gates visibility on roster **or** results of the caller's `allowed_athlete_ids`, and derives `my_categories` from `RaceResult` alone (never from the roster, which has no category); an unrelated parent gets `404 course_not_available`, not a filtered `200`. |
| The upload bytes are never written to the backend filesystem. | `process_gpx` is pure/in-memory; the router reads the multipart body into memory (`_read_and_validate_course_gpx_upload`), never opens a file handle. |

## 9. Summary of design decisions made mid-implementation

For a developer who only has time to read one section before touching this module:

1. `has_course_data` means three different things in three different places (§4) — check which function you're calling before assuming they agree.
2. `fetch_course_context` lives in `app/services/race/queries.py`, not `app/services/race/ai/queries.py` as originally planned (§6).
3. The season AI prompt block (`course_by_valida`) and the per-válida block (`course_block`) are different shapes fed by the same formatter (§6).
4. The season-launch path derives its válida list from `course_context.keys()`, not from `state["valida_nums"]`, because the common case (global launch) leaves the latter empty (§6).
5. `avg_speed_kmh` for the season/evolution view lives on `EvolutionPoint`/`EvolutionTable`, not on `analytics.py`/`SeasonInsightsPage.tsx` as the plan named (§4).
6. Elevation smoothing is a double box-average pass, and simplification uses a segment-bounded (not infinite-line) RDP distance — both undocumented in the original contract text but load-bearing for the SC-005 noise target and for out-and-back recordings respectively (§3.3, §3.4).

## 10. References

- `specs/043-race-course-profile/plan.md`, `data-model.md`, `quickstart.md`, `research.md` (R-01…R-16)
- `specs/043-race-course-profile/contracts/course-api.md`, `gpx-processing.md`, `results-derived-figures.md`, `ai-course-block.md`, `ui-course.md`
- `specs/043-race-course-profile/tasks.md` — Phase completion notes (Phase 1+2, Phase 3+4, Phase 5+6) document every deviation cited above with full detail
- `backend/app/services/race/course/gpx_processing.py`, `service.py`, `derived.py`
- `backend/app/services/race/agents/analyst.py`, `backend/app/services/race/prompts/race_analyst_v3.md`, `race_season_summary_v3.md`
- `docs/10-race-results/runbook-ops.md` §10 — operational addendum for this feature
