# Contract — Derived distance and speed on results

**Service**: `backend/app/services/race/results_read.py::get_event_results` (`:167`, existing, extended). **Schemas**: `backend/app/schemas/race_results.py` (`ResultRow:27`, `CategoryResults`, `EventResultsRead`). **Season rows**: `backend/app/services/race/analytics.py` (athlete per-válida rows, extended with one nullable field). Binding: `research.md` R-08, R-11. Requirements: FR-014–FR-017; SC-002, SC-007; User Story 2.

## 1. Schema deltas (all additive, all `Optional`, default `None`)

`ResultRow` + `distance_km: float | None`, `avg_speed_kmh: float | None`, `lap_distance_km: float | None`, `elevation_gain_m: int | None`.
`CategoryResults` + `laps: int | None`, `variant_label: str | None`.
`EventResultsRead` + `has_course_data: bool` (default `False`).

Existing consumers (frontend `ResultsTable`, parents page, MSW handlers, AI `load_race_data`) keep working unchanged because every new field is optional (SC-007).

## 2. Computation (in `get_event_results`, after the rows are already parent-scoped)

One extra query: `select(RaceCourseCategorySetup).options(selectinload(RaceCourseCategorySetup.variant)).where(race_event_id == …)` → `setup_by_category: dict[int, (laps, variant)]`. `has_course_data = bool(setup_by_category) or event has any variant`.

Per row:

```text
setup = setup_by_category.get(category_id)          # None → all four fields None
status_ok = status in {"finished", "minus_laps"} and race_time_ms is not None
laps_completed:
    None                          if setup is None or not status_ok
    None                          if status == "minus_laps" and laps_behind is None
    setup.laps - (laps_behind or 0)   otherwise; if result ≤ 0 → None (defensive)
distance_km   = round(laps_completed * setup.variant.lap_distance_m / 1000, 1)
avg_speed_kmh = round(distance_km / (race_time_ms / 3_600_000), 1)      # uses the unrounded distance
lap_distance_km = round(setup.variant.lap_distance_m / 1000, 1)        # set whenever setup exists
elevation_gain_m = setup.variant.elevation_gain_m                      # may be None (no elevation)
```

`CategoryResults.laps` / `variant_label` are set whenever `setup` exists, regardless of rows. Rounding uses Python `round` on `Decimal` to avoid float artefacts (`Decimal(str(x)).quantize(Decimal("0.1"), ROUND_HALF_UP)`).

## 3. Season / evolution rows (R-11)

The athlete's per-válida rows produced in `analytics.py` (consumed by the season panorama and the athlete evolution tables) gain `avg_speed_kmh: float | None` computed with the same helper (`app/services/race/course/derived.py::derive_figures(setup, status, race_time_ms, laps_behind)`) so the rule lives once. No aggregate (mean/best/trend) of speed is computed anywhere; comparison groups (`comparison_groups.py`) are untouched. Frontend renders "sin dato" for `null`.

## 4. Tests — `backend/tests/services/race/test_results_derived.py` (new) + extension of the existing results-read tests

- The spec's independent test: variant 4 200 m / 110 m, category 3 laps; finished 30:00 → 12.6 km, 25.2 km/h; `minus_laps` `laps_behind=1` 28:00 → 8.4 km, 18.0 km/h; DNF → all `None`.
- `minus_laps` with `laps_behind=None` → `None`; category without setup → `None` but `has_course_data=True` when another category has one; válida without course → `has_course_data=False` and no field set.
- Parent scope: rows still filtered; figures present only for own athletes.
- Query count: `get_event_results` runs exactly one more statement than before (assert with the statement counter).
- Results revision changing `laps_behind` → next read reflects it (no cache).
- `derive_figures` property test: distance and speed are `None` or positive; speed ≤ 60 km/h for any valid input within ranges (sanity bound, not a business rule).
