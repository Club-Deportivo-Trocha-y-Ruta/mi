# Research — Race course profile (043)

**Date**: 2026-09-15 · **Inputs**: `spec.md` (owner decisions in Assumptions), the code map of the race and training modules produced during planning (file:line citations below were verified against the working tree on 2026-09-15), a web/library research brief (gpxpy source on GitHub `dev` branch, defusedxml README, GPS Visualizer and Ride with GPS elevation write-ups, Leaflet reference and accessibility guide, leaflet-gpx README, python-fitparse and garmin fit-python-sdk repositories), `specs/042-traceable-growth-ai/research.md` (format precedent and the "present / SIN DATO" prompt-block discipline this feature copies).

Each entry: **Decision** · **Rationale** · **Alternatives considered** · (where useful) **Evidence**. All unknowns of the Technical Context are resolved here; none remains for `/speckit-clarify`.

---

## R-01 File format: GPX only in this feature; FIT deferred

**Decision**: Accept only `.gpx` (`application/gpx+xml`, `application/xml`, `text/xml`). Reject `.fit`, `.gpx.gz`, `.zip` and anything else at the router. `spec.md` FR-002 and Assumptions were amended on 2026-09-15 to say so.

**Rationale**: The training-session upload (`backend/app/services/training/route_files.py:61-104`) accepts `.fit` but never parses it — it only checks the `0x0E` magic byte and stores the raw file. This feature must extract geometry, so FIT would need a new runtime dependency (`python-fitparse` or Garmin's `fit-python-sdk`), a second privacy-stripping path and a second security review, for a format every device the coach uses (Garmin Connect, Strava, Wahoo, Coros) already exports as GPX. The data model is format-agnostic (only the extracted lap is stored), so FIT can be added later without a migration.

**Alternatives considered**: `python-fitparse` (MIT, pure Python, widely used) — viable, deferred. Garmin `fit-python-sdk` (0.x, Garmin licence terms) — rejected as heavier and less mature. Accepting FIT "as stored file only" like training — rejected, it would violate FR-003 (original never kept) and give no geometry.

---

## R-02 Storage: the extracted lap lives in the database, not on disk

**Decision**: Each route variant stores its simplified lap as a `JSON` column (`geometry`: list of `[lat, lon, ele|null]`), plus `lap_distance_m`, `elevation_gain_m`, `point_count`, `has_elevation`, `detection_method`, `recorded_laps` and a `source_sha256` of the discarded upload. No file is written anywhere; the upload is processed in memory and dropped.

**Rationale**: Render's free-tier filesystem is ephemeral — training route files under `static/uploads/routes/` do not survive a deploy today. A 4 km lap simplified to 300–600 points is 10–15 KB of JSON, trivial for MySQL 8.4 and for one HTTP response; a `JSON` column validates structure on write and follows the existing convention (`from sqlalchemy import JSON`, `Mapped[dict | None] = mapped_column(JSON, ...)` at `backend/app/models/ai_explanation.py:89` and `athlete_newsletter.py`). Storing only the derived lap is also what makes FR-003/FR-025 (no timestamps, no physiological data, no original) verifiable: there is simply nowhere for them to go.

**Alternatives considered**: Google encoded polyline — 8–10× smaller but 2-D only (needs a parallel elevation array), not worth it at one course per válida. Hostinger SFTP like session media — durable but adds a network hop, a fallback path and a file that would have to be re-parsed on every read. GeoJSON `LineString` — equivalent; the bare array is smaller and simpler to type in Zod, and a GeoJSON wrapper can be produced on the fly if a future consumer needs it.

---

## R-03 Processing pipeline (server side, in memory)

**Decision**: `app/services/race/course/gpx_processing.py` implements a pure function `process_gpx(content: bytes, *, recorded_laps: int | None) -> ProcessedLap` with these ordered steps:

1. **Guard**: size ≤ 5 MB (reuse `_MAX_GPX_SIZE_BYTES`), content is UTF-8 text, root element is `<gpx>` (this is the "magic bytes" check the constitution demands for a text format).
2. **Safe parse**: `defusedxml.ElementTree.fromstring` first (fails closed on DTD, external entities, billion laughs), then `gpxpy.parse` on the same bytes. gpxpy's own parser is stdlib `xml.etree` only (no lxml) and does not compose with defusedxml automatically, so the pre-parse is what provides the XXE defence — the same order `route_files.py:_validate_gpx_content` already uses.
3. **Strip**: `gpx.remove_time(all=True)`; set `.extensions = []` on the GPX, every track, every segment's points, routes and waypoints (gpxpy keeps `<extensions>` as raw `Element` copies at every level, so Garmin `TrackPointExtension` hr/cad/atemp/power survive unless cleared at each level); null `creator`, `author_*`, `email`, `link*`, `name`, `description`, `time`, `keywords`; drop waypoints and routes entirely; merge all track segments into one point list (device auto-pause splits segments).
4. **Lap extraction** (R-04) → one list of points.
5. **Elevation** (R-05) → smoothed elevations, gain in whole metres or `None`.
6. **Simplify** (R-06) → ≤ 800 points, distance preserved within 1 %.
7. **Range check**: lap distance 300 m – 15 km and ≥ 20 points after simplification (FR-007); otherwise a typed `CourseProcessingError` with a Spanish reason code the router maps to 422.

The function never logs point data, file names or metadata; only `point_count`, `lap_distance_m` and the reason code appear in structured logs.

**Rationale**: One pure function is unit-testable with synthetic tracks (a generated circle, a generated three-lap circuit with noise, an out-and-back), which is how SC-003 and SC-005 are proven without any real recording in the repository.

**Alternatives considered**: Doing the extraction in the browser and posting the coordinates — rejected: the privacy invariant must be enforced server-side, and a client could post anything.

---

## R-04 Closed-lap detection

**Decision**: With the merged point list `P`, cumulative distance `d[i]` (haversine, via `gpxpy.geo.distance`), start `P[0]`:

- Scan `i` from the first index with `d[i] ≥ 300 m`; the lap closes at the first `i` where `distance(P[i], P[0]) ≤ 30 m`.
- If found and the remaining track after `i` is at least 80 % of `d[i]`, validate that the next closure (same rule from `P[i]`) yields a length within ±10 % of `d[i]`; on success `detection_method = "closed_loop"`, `laps_detected = round(d_total / d[i])`, and the lap is `P[0..i]`.
- If no closure is found or validation fails: `detection_method = "manual"`, and the lap is the whole track divided by `recorded_laps` (default 1) — geometry is the first `1/recorded_laps` of the cumulative distance, distance and gain are `total / recorded_laps`.
- If a closure is found but the coach passed `recorded_laps`, the coach's value wins (`detection_method = "manual"`), because the coach knows what they rode.

The API response carries `detection` (`method`, `laps_detected`, `lap_distance_m`, `total_distance_m`) so the UI can show "Detectamos 3 vueltas de 4,2 km — ¿es correcto?" and, if not, let the coach re-upload with `recorded_laps` set. Re-upload is the correction path because the original is never retained (R-02).

**Rationale**: No maintained library solves this; every reference (gpx-tools.com's lap-recording guide, community threads) hand-rolls proximity-to-start with a minimum-distance guard, which is exactly what start-line GPS noise requires. The ±10 % validation catches a false closure on a figure-eight or a course that brushes the start straight mid-lap. Snapping the start to a "better" point than sample 0 is not worth its complexity: the coach controls the recording and can trim it, and the manual override covers the rest.

**Alternatives considered**: Choosing the start as the point of maximum local revisit density — better lap alignment in theory, more code and more surprises; rejected. Detecting laps client-side for interactivity — rejected (R-03).

---

## R-05 Elevation gain and smoothing

**Decision**: If any point lacks elevation → `has_elevation=false`, `elevation_gain_m=None`, no profile. Otherwise: one pass of gpxpy `segment.smooth(vertical=True, horizontal=False, remove_extremes=True)`, then a **distance-windowed moving average** (window 30 m along the track) over elevation, then a **hysteresis accumulator**: walk the smoothed series keeping a running "last counted" elevation and add a climb only when the current value exceeds it by ≥ 3 m (reset the baseline on each accepted step and whenever the series drops ≥ 3 m below it). Result rounded to whole metres. Do **not** call `get_uphill_downhill()` on top — it smooths internally and would double-smooth.

**Rationale**: Consumer GPS altitude is noisy (GPS Visualizer shows raw gain 5–10× too high; Ride with GPS and Strava-adjacent write-ups both describe a moving average plus a threshold as the standard server-side treatment). A 3 m threshold suits short, punchy MTB laps better than the 10 m used for hiking-scale tracks. SC-005 (flat circuit reports < 5 m per km) is checked with a synthetic flat lap with ±4 m Gaussian noise.

**Alternatives considered**: gpxpy `get_uphill_downhill()` alone — undocumented window, no hysteresis, fails SC-005 on noisy flat tracks in a quick local trial. Barometric-vs-GPS detection — not knowable from GPX; the same algorithm handles both because barometric data tracks relative change well.

---

## R-06 Simplification and profile decimation

**Decision**: `segment.simplify(max_distance=3.0)` (Ramer–Douglas–Peucker, metres), then, if more than 800 points remain, raise `max_distance` in 1 m steps until ≤ 800. After simplification assert `|length_2d_simplified − length_2d_original| / original ≤ 1 %`; if the assertion fails at the cap, keep the last epsilon that satisfied it and let the point count exceed 800 (never violate the distance bound). The stored `lap_distance_m` is measured on the **unsimplified** lap. The elevation profile is decimated client-side to ≤ 200 samples by distance bucket for the chart; the map draws all stored points.

**Rationale**: 3–5 m is the commonly cited epsilon for consumer trail GPS that keeps < 1 % length error while cutting points 5–10×. Storing the true distance and only using the simplified shape for display removes any accuracy question from the derived speed figures (FR-014).

---

## R-07 Data model: two new tables plus four columns on the válida

**Decision**: `race_course_variants` (one row per variant), `race_course_category_setups` (one row per válida × category), and four nullable description columns on `race_events` (`terrain_type`, `technical_difficulty`, `key_sectors` JSON list, `course_notes`). Both new tables use `ActorTimestampMixin` (`backend/app/models/mixins.py`) for `updated_by_user_id` + `updated_at`, and every mutating route also calls `record_audit(...)` exactly as the conditions PATCH does (`backend/app/routers/race_events.py:919-1004`) — the dual pattern feature 041 established. Single Alembic revision with `down_revision = "d5b125474e2b"`. Details in `data-model.md`.

**Rationale**: The description belongs to the válida (FR-013 says "with or without a recording") and mirrors how the five weather fields already live on `race_events`; variants and setups are genuinely one-to-many. `RaceEvent` itself does not carry `updated_by_user_id` today and this feature does not add it — attribution for the description goes through `record_audit` like the conditions do, keeping the model change additive.

**Alternatives considered**: A separate `race_course_descriptions` table — one extra join for four columns; rejected. Storing setups as a JSON map on the event — rejected because `variant_id` must be a real foreign key for the "cannot delete while referenced" rule (FR-008) and because results reads join on `category_id`.

---

## R-08 Derived figures are computed in the existing results read, never stored

**Decision**: `backend/app/services/race/results_read.py::get_event_results` (`:167`, single aggregated query, already parent-scoped via `allowed_athlete_ids`) gains **one** extra query per call: the event's setups joined with their variants, loaded into a dict keyed by `category_id`. `ResultRow` (`backend/app/schemas/race_results.py:27`) gains four optional fields: `distance_km`, `avg_speed_kmh`, `lap_distance_km`, `elevation_gain_m`; `CategoryResults` gains `laps` and `variant_label`; `EventResultsRead` gains `has_course_data: bool`. Rule: `laps_completed = laps − (laps_behind or 0)` when `status ∈ {finished, minus_laps}` and `race_time_ms` is set; if `status == minus_laps` and `laps_behind is None` → all four `None`. Distance = `laps_completed × lap_distance_m / 1000` rounded to 0.1; speed = `distance_km / (race_time_ms / 3_600_000)` rounded to 0.1.

**Rationale**: A stored column would go stale on every setup edit, variant re-upload or results revision (FR-009, edge case "revision changes laps down"); computing at read time makes those free. One extra indexed query keeps the p95 ≤ 500 ms budget and avoids N+1 (Principle IV), and the parent scope is inherited because the rows are already filtered before the figures are attached (FR-017).

**Alternatives considered**: Materialising `distance_m`/`avg_speed` on `race_results` — rejected (staleness). Computing in the frontend — rejected: the AI context and the parent page need the same numbers, and rounding rules must live in one place.

---

## R-09 Parent access to course data

**Decision**: New `GET /api/race-analysis/race-events/{id}/course` with `require_role([admin, coach, parent])`. For a parent, the service takes `allowed_athlete_ids` from the existing `allowed_athlete_ids_for(current_user, db)` helper and returns the course only if at least one of those athletes is on the válida's roster (`race_event_roster`) or has a result in it; otherwise `404` (not `403`, so the existence of a válida the family is not part of is not confirmed). The response for a parent additionally carries `my_categories: [{athlete_id, category_id}]` so the UI can highlight the laps of each child's category (US5 scenario 2) without exposing other rows. Free notes, terrain, difficulty and sectors are included for parents (they are course information, spec US5).

**Rationale**: Parents cannot call `GET /{id}` today; results/standings/roster are the only parent-reachable reads and all use the same `allowed_athlete_ids` kwarg. Reusing the helper keeps RBAC in one place (constitution: RBAC in `services/permissions.py` or equivalent) and gives the denied-path test its natural shape.

---

## R-10 AI context: a `course_block` with the "present / SIN DATO" discipline

**Decision**: `RaceAnalystState` (`backend/app/services/race/ai/state.py`) gains `course_context: dict[int, dict]` keyed by `valida_num` exactly like `event_conditions`; `load_race_data` (`ai/nodes/load_race_data.py:344`) fills it through a new `fetch_course_context(db, season, validas, category_id)` in `queries.py` that reuses the cached events (no extra round trip beyond one query for the setups+variants of the requested válidas). `AnalystV3Input` gains `course_meta: str | None`, built by a new `format_course_meta(course: dict | None) -> str | None` in `race/agents/analyst.py` beside `format_race_meta` (`:468-504`); `_build_v3_context` (`:1377-1407`) adds `"course_block": input_.course_meta`. `race_analyst_v3.md` and `race_season_summary_v3.md` gain a block that copies the conditions pattern: when present, "Estas son las **únicas** características del circuito registradas"; when absent, "## Circuito — SIN DATO · PROHIBIDO mencionar distancia, vueltas, terreno, desnivel o dificultad". The block lists only: lap distance, elevation gain (when known), laps of the rider's category, terrain type, difficulty label, key sectors. `course_notes` is **never** included (FR-020). Golden dataset `golden_v3/` gains two cases: one with `course_meta` present (expected theme: contextualises the time by distance/terrain) and one absent with `forbidden_terms` covering distance/vueltas/terreno/desnivel; `RACE_EVAL_THRESHOLD` unchanged at 0.75.

**Rationale**: This is the same mechanism feature 011 used for conditions and the same block discipline 042 documented; the prompt already contains the anti-fabrication veto, so the change is additive and rollback is `RACE_AI_PROMPT_VERSION=race_analyst_v2` (v2 prompts are untouched and simply ignore the new key because they are rendered with the same context — verify with a rendering test).

**Alternatives considered**: Injecting course facts into `race_block` — rejected, it would bypass the explicit SIN DATO veto that keeps the analyst honest when data is missing.

---

## R-11 Cross-válida comparisons: per-válida figures only, no aggregate of speed

**Decision**: In this feature the only cross-válida surfaces that change are the athlete's per-válida rows in the season/evolution views (`analytics.py` rows and the corresponding frontend tables), which gain a nullable `avg_speed_kmh` rendered as "sin dato" when absent. No average, best, or trend of speed across válidas is computed anywhere; comparison groups (`comparison_groups.py`, feature 039) keep comparing positions and points and are not touched. This satisfies FR-016 by construction: a normalised figure is never mixed into an aggregate.

**Rationale**: Speed across different circuits is only meaningful when both circuits are known, and even then it needs a per-course normalisation this feature does not attempt. Showing the per-válida figure with an explicit gap is honest and cheap; a later feature can add normalised comparisons once several válidas carry course data.

---

## R-12 Frontend: plain Leaflet polyline and a lazy Recharts profile; no `leaflet-gpx`

**Decision**: New lazy components under `frontend/src/components/race/course/`: `CourseMap.tsx` (dynamic `import("leaflet")` + `leaflet.css`, `L.polyline(latlngs)`, `map.fitBounds`, `aria-label="Mapa del circuito"`, keyboard-focusable container, reuse of the icon-path workaround from `components/training/RouteViewer.tsx`) and `ElevationProfile.tsx` (Recharts `AreaChart` in `ResponsiveContainer`, distance km on X, elevation m on Y, ≤ 200 decimated samples, `role="img"` with an `aria-label` that states min/max elevation and total gain). Both behind `React.lazy` + Suspense (Principle IV: heavy components lazy). `leaflet-gpx` is not used by this feature — it only accepts a GPX URL and no file exists. Palette and axis rules follow the `dataviz` skill (single neutral series colour for the profile; status colours reserved).

**Rationale**: `RouteViewer.tsx` fetches the raw file and lets `leaflet-gpx` parse it client-side, which contradicts R-02. Everything else in it (dynamic import, CSS, container UX) is reused. Recharts is already a dependency (`recharts ^3.8.1`) and used elsewhere, so no new package.

---

## R-13 Where the UI lives: a "Circuito" tab, a post-commit wizard panel, and a parent card

**Decision**:

- Coach: new URL-driven tab `circuito` in `CompetitionDetailPage.tsx` (`TabValue` union at `:86`), between `conditions` and `athletes`, rendering `CourseTab` (variants card with upload dialog and detection confirmation, `CategorySetupTable`, `CourseDescriptionCard` with its edit sheet, and the read-only `CourseSummary` with map + profile). The tab exists for every válida; when there is no course data the coach sees the tri-state "Agregar" empty state exactly like `RaceConditionsCard`. The `CompetitionFormPage` (create/edit) is **not** extended with uploads: a válida must exist before a variant can belong to it, so the form's success screen links to the tab ("Agregar circuito"), which is what "at creation" means in practice.
- Import wizard: the válida is created or linked at commit, so an upload cannot happen in steps 1–2. The optional "Circuito" panel is rendered in **step 3** ("Resultado") once `race_event_id` is known, reusing `CourseTab` in compact mode; skipping it has no effect on the import. The `STEPS` array (`ImportWizard.tsx:207`) is unchanged (no fourth gate), which keeps the existing step-focus contract and tests intact. This is the planned reading of spec US1 scenario 9.
- Parents: `CourseSummary` (read-only: map, profile, distance, gain, laps of each child's category, description) at the top of `ParentCompetitionResultsPage.tsx`, and in `ParentEventDetailPage.tsx` when the calendar event links a válida (that is how a family reaches a scheduled válida before race day). The card is absent — not empty — when `GET /course` returns 404.
- Results: `ResultsTable.tsx` gains "Distancia" and "Vel. prom." columns only when `has_course_data` is true (US2 scenario 4).

**Rationale**: Reusing the tri-state card and the URL-tab pattern keeps UX consistent (Principle III) and lets one component serve coach, wizard and parents.

---

## R-14 Prefill from the previous válida

**Decision**: `GET /{id}/course` includes `suggested_setups` (list of `{category_id, laps, variant_label}`) computed server-side from the válida with the highest `sequence_number` lower than the current one in the same `series_id` that has setups; empty when none. The suggestion is only rendered into the table when the válida has no saved setups; saving `PUT /course/setups` persists what the coach confirmed. Variant labels are matched by name to the current válida's variants when the coach saves (a suggestion whose label has no variant here leaves the selector empty).

**Rationale**: One response, no second endpoint, no client-side series scanning like `useImportPrefill.ts` has to do today.

---

## R-15 Security and privacy guardrails

**Decision**: Router-level content-type allow-list and 5 MB cap (reusing the training constants); `.gz`/`.zip` rejected by extension and by content sniff (`1f 8b`, `50 4b`); defusedxml pre-parse (R-03); root-element check; no filename, no metadata and no point data in logs; `source_sha256` stored for idempotent re-upload detection only; structured log event `race_course_variant_processed` with `{race_event_id, variant_id, point_count, lap_distance_m, detection_method, reason_code?}` and nothing else. The `data-privacy-guard` audit runs over the processing module, the results read, the AI block and the parent endpoint. No CVE is known for gpxpy; modern CPython's expat already blocks billion-laughs, defusedxml is cheap insurance.

---

## R-16 Dependencies and performance budget

**Decision**: No new runtime dependency on either side (`gpxpy>=1.6`, `defusedxml>=0.7`, `leaflet`, `recharts` already pinned). Budgets: `POST /course/variants` is a transactional write with CPU-bound parsing of ≤ 5 MB — target p95 ≤ 1500 ms on Render for a typical 1–2 MB, 3-lap recording (measured locally with a synthetic 20 000-point file; documented in Complexity Tracking if it exceeds). `GET /course` p95 ≤ 500 ms (two indexed queries, ≤ 15 KB per variant). `GET /results` adds one query. Frontend: map chunk (leaflet ≈ 42 KB gz) and chart chunk (recharts already in the bundle graph) lazy; results route stays under the 150 KB per-lazy-route budget.
