# Contract — GPX processing (`app/services/race/course/gpx_processing.py`)

Pure, synchronous, in-memory. No I/O, no logging of content, no dependency beyond `gpxpy` and `defusedxml` (both pinned in `backend/requirements.txt:25-26`). Binding decisions: `research.md` R-03…R-06, R-15. Requirements: FR-002–FR-007, FR-025; SC-003, SC-005.

## 1. Signature

```python
def process_gpx(content: bytes, *, recorded_laps: int | None = None) -> ProcessedLap
```

Raises `CourseProcessingError(code: str)` with one of the codes in `course-api.md` §6. Never raises anything else for any byte input (fuzz test: random bytes, random XML, truncated GPX → always `CourseProcessingError`).

Constants (module level, imported by tests and echoed in `LapDetection`): `MIN_LAP_M = 300`, `MAX_LAP_M = 15_000`, `CLOSURE_RADIUS_M = 30`, `LAP_LENGTH_TOLERANCE = 0.10`, `SMOOTH_WINDOW_M = 30`, `GAIN_HYSTERESIS_M = 3`, `SIMPLIFY_EPSILON_M = 3.0`, `MAX_POINTS = 800`, `MIN_POINTS = 20`, `MAX_DISTANCE_ERROR = 0.01`.

## 2. Steps (order is normative)

1. **Sniff**: first bytes `1f 8b` or `50 4b` → `compressed_not_allowed`. Decode UTF-8 (BOM tolerated) → failure `malformed`. Root element local name must be `gpx` (check after the safe parse, on `root.tag`) → else `not_gpx`.
2. **Safe parse**: `defusedxml.ElementTree.fromstring(content)`; `DefusedXmlException` subclasses (`EntitiesForbidden`, `DTDForbidden`, `ExternalReferenceForbidden`) → `xml_unsafe`; `ParseError` → `malformed`. Then `gpxpy.parse(content.decode())`; `GPXException` → `malformed`.
3. **Strip** (privacy, FR-003): `gpx.remove_time(all=True)`; `gpx.extensions = []`; for every track: `track.extensions = []`, for every segment, for every point: `point.extensions = []`, `point.time = None`, `point.speed = None`, `point.symbol = None`, `point.comment = None`, `point.name = None`, `point.description = None`, `point.source = None`, `point.link = None`; `gpx.routes = []`, `gpx.waypoints = []`; `gpx.creator = gpx.name = gpx.description = gpx.author_name = gpx.author_email = gpx.author_link = gpx.author_link_text = gpx.author_link_type = gpx.copyright_author = gpx.copyright_year = gpx.copyright_license = gpx.link = gpx.link_text = gpx.link_type = gpx.keywords = None`; `gpx.time = None`. After this step the function works only with a `list[Point(lat, lon, ele | None)]` built from all segments of all tracks in order — the `GPX` object is not referenced again, which is what guarantees nothing else can leak.
4. **Sanity**: `len(points) == 0` → `no_track_points`; any point with lat/lon outside range or NaN → `no_position`.
5. **Cumulative distance** `d[i]` via `gpxpy.geo.distance(lat1, lon1, None, lat2, lon2, None)` (haversine, 2-D). `total = d[-1]`.
6. **Lap extraction** (R-04):
   - If `recorded_laps` is given: `method = "manual"`, `laps = recorded_laps`; lap = prefix of points until `d[i] ≥ total / laps` (inclusive); `lap_distance_m = round(total / laps)`.
   - Else search `i ≥ first index with d[i] ≥ MIN_LAP_M` for the first `distance(P[i], P[0]) ≤ CLOSURE_RADIUS_M`. If found and `total − d[i] ≥ 0.8 × d[i]`: from `P[i]` find the next closure `j`; accept iff `|d[j] − 2·d[i]| / d[i] ≤ LAP_LENGTH_TOLERANCE` → `method = "closed_loop"`, `laps = round(total / d[i])`, lap = `P[0..i]`, `lap_distance_m = round(d[i])`. If found but `total − d[i] < 0.8 × d[i]` (single lap that closes): `method = "single"`, `laps = 1`, lap = `P[0..i]`, `lap_distance_m = round(d[i])`.
   - Else (no closure or validation failed): `method = "manual"`, `laps = 1`, lap = all points, `lap_distance_m = round(total)`.
7. **Range**: `lap_distance_m < MIN_LAP_M` → `too_short`; `> MAX_LAP_M` → `too_long`.
8. **Elevation** (R-05): `has_elevation = all(p.ele is not None for p in lap)`. If true: smooth with a distance-windowed moving average (window `SMOOTH_WINDOW_M` centred on each point along `d`), then hysteresis accumulation with `GAIN_HYSTERESIS_M`; `elevation_gain_m = round(gain)`. If false: `elevation_gain_m = None` and elevations are stored as `null` for every point (never a mix).
9. **Simplify** (R-06): RDP with `SIMPLIFY_EPSILON_M` on the lap (2-D, using the same linear-approximation distance gpxpy uses); while `len > MAX_POINTS` and the 2-D length of the simplified lap stays within `MAX_DISTANCE_ERROR` of `lap_distance_m`, increase epsilon by 1 m; stop at the last epsilon that satisfies the error bound. `len < MIN_POINTS` → `too_few_points`.
10. **Round**: lat/lon to 6 decimals, ele to 1 decimal. Return `ProcessedLap`.

## 3. Determinism and limits

Same bytes + same `recorded_laps` → identical output (no randomness, no time). Worst-case input 5 MB ≈ 60 000 points: the closure scan is O(n) with an early exit, RDP is O(n log n) typical; target ≤ 1 s on Render's CPU — asserted in a timed test at 20 000 points ≤ 300 ms locally.

## 4. Tests — `backend/tests/services/race/test_gpx_processing.py` (new) with a synthetic-GPX builder in `tests/helpers/gpx_builder.py`

- Circle of radius 640 m (≈ 4.0 km), 1 lap → `single`, `lap_distance_m` within 1 % of 4 021, points ≤ 800.
- Same circle × 3 laps with 5 m Gaussian jitter → `closed_loop`, `laps_detected = 3`, lap distance within 2 %.
- Out-and-back 2 km → `manual`, `laps = 1`, distance ≈ 4 000.
- Three laps with `recorded_laps = 3` → `manual`, distance ≈ one lap.
- Figure-eight (brushes the start mid-lap) → validation rejects the false closure → `manual`.
- Flat circle with ±4 m elevation noise → `elevation_gain_m < 20` (SC-005).
- Circle with a clean 100 m climb and descent per lap → gain 95–105.
- Missing elevation on one point → `has_elevation=false`, gain `None`, every ele `null`.
- Garmin extensions + `<time>` + `<metadata><author>` in the input → output structure has no such fields (hypothesis strategy over random extension tags).
- XXE (`<!DOCTYPE … SYSTEM "file:///etc/passwd">`), billion laughs, gzip bytes, random bytes, empty file → the expected code each; never another exception.
- 200 m circle → `too_short`; 20 km loop → `too_long`; 10-point track → `too_few_points`.
