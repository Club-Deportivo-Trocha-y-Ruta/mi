"""Synthetic GPX fixture generator for tests (feature 043, T009).

Every byte produced here is fabricated: a circle, an out-and-back line or a
figure eight around an arbitrary point in Valle del Cauca, never a real GPS
recording. Per this project's privacy rules, a coach's actual ride must
never be committed to the repository — these functions exist so tests can
exercise ``app/services/race/course/gpx_processing.py`` without one.

The XML is built directly as text rather than round-tripped through
``gpxpy``'s writer, because attaching arbitrary namespaced
``<extensions>`` blocks (Garmin ``TrackPointExtension``) to that writer is
awkward; writing the text keeps every fixture a complete, valid GPX 1.1
document with a single ``<trk><trkseg>``.
"""
from __future__ import annotations

import math
import random
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

# Arbitrary reference point, consistent with this feature's other fixtures
# (Valle del Cauca, Colombia) — never a real coordinate of an actual ride.
LAT0 = 3.45
LON0 = -76.5320

METERS_PER_DEGREE_LAT = 111_320.0

GPX_NS = "http://www.topografix.com/GPX/1/1"
GPXTPX_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"

BASE_TIME = datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)

# Closure radius used by the (future) lap-detection scan in
# gpx_processing.py; out_and_back_gpx keeps its return leg outside this by
# a safe margin so it does not accidentally register a false closed lap.
_CLOSURE_RADIUS_M = 30.0


def _meters_per_degree_lon(lat0: float) -> float:
    return METERS_PER_DEGREE_LAT * math.cos(math.radians(lat0))


def _offset_to_latlon(dx: float, dy: float, lat0: float = LAT0, lon0: float = LON0) -> tuple[float, float]:
    """Flat-earth approximation: metre offsets (dx east, dy north) -> lat/lon."""
    dlat = dy / METERS_PER_DEGREE_LAT
    dlon = dx / _meters_per_degree_lon(lat0)
    return lat0 + dlat, lon0 + dlon


def _format_time(index: int, step_seconds: float = 3.0) -> str:
    ts = BASE_TIME + timedelta(seconds=index * step_seconds)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _render_gpx(
    points_xy: list[tuple[float, float]],
    *,
    elevation: Callable[[float], float] | None = None,
    extensions: bool = False,
    with_time: bool = False,
    metadata: bool = False,
    lat0: float = LAT0,
    lon0: float = LON0,
) -> bytes:
    """Render a list of (dx, dy) metre offsets into a full GPX 1.1 document."""
    parts: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']

    if extensions:
        parts.append(
            '<gpx version="1.1" creator="trocha-y-ruta-test-fixtures" '
            f'xmlns="{GPX_NS}" xmlns:gpxtpx="{GPXTPX_NS}">'
        )
    else:
        parts.append(f'<gpx version="1.1" creator="trocha-y-ruta-test-fixtures" xmlns="{GPX_NS}">')

    if metadata:
        parts.append(
            "<metadata><author><name>Coach Test</name></author>"
            "<time>2026-01-15T07:55:00Z</time></metadata>"
        )

    parts.append("<trk><name>Synthetic test track</name><trkseg>")

    cumulative = 0.0
    prev: tuple[float, float] | None = None
    for index, (x, y) in enumerate(points_xy):
        if prev is not None:
            cumulative += math.hypot(x - prev[0], y - prev[1])
        prev = (x, y)

        lat, lon = _offset_to_latlon(x, y, lat0, lon0)
        parts.append(f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}">')
        if elevation is not None:
            parts.append(f"<ele>{elevation(cumulative):.2f}</ele>")
        if with_time:
            parts.append(f"<time>{_format_time(index)}</time>")
        if extensions:
            hr = 140 + (index % 10)
            cad = 78 + (index % 6)
            atemp = 24.5 + 0.1 * math.sin(index / 7.0)
            parts.append(
                "<extensions>"
                f'<gpxtpx:TrackPointExtension xmlns:gpxtpx="{GPXTPX_NS}">'
                f"<gpxtpx:hr>{hr}</gpxtpx:hr>"
                f"<gpxtpx:cad>{cad}</gpxtpx:cad>"
                f"<gpxtpx:atemp>{atemp:.1f}</gpxtpx:atemp>"
                "</gpxtpx:TrackPointExtension>"
                "</extensions>"
            )
        parts.append("</trkpt>")

    parts.append("</trkseg></trk></gpx>")
    return "\n".join(parts).encode("utf-8")


def _circle_offsets(radius_m: float, points: int, *, jitter_m: float = 0) -> list[tuple[float, float]]:
    offsets: list[tuple[float, float]] = []
    for i in range(points):
        theta = 2 * math.pi * i / points
        x = radius_m * math.cos(theta)
        y = radius_m * math.sin(theta)
        if jitter_m:
            x += random.gauss(0, jitter_m)
            y += random.gauss(0, jitter_m)
        offsets.append((x, y))
    return offsets


def circle_gpx(
    radius_m: float,
    points: int,
    laps: int = 1,
    jitter_m: float = 0,
    elevation: Callable[[float], float] | None = None,
    extensions: bool = False,
    with_time: bool = False,
    metadata: bool = False,
) -> bytes:
    """A rider going `laps` times around a circle of radius `radius_m`.

    `points` is the point count for ONE lap; the same circular path (each
    point independently re-jittered when `jitter_m > 0`) is repeated `laps`
    times consecutively, for `points * laps` points in total. Each lap
    closes to within a few metres of its own start, letting a
    closure-detection scan recognise consecutive laps.
    """
    all_points: list[tuple[float, float]] = []
    for _ in range(laps):
        all_points.extend(_circle_offsets(radius_m, points, jitter_m=jitter_m))

    return _render_gpx(
        all_points,
        elevation=elevation,
        extensions=extensions,
        with_time=with_time,
        metadata=metadata,
    )


def out_and_back_gpx(length_m: float) -> bytes:
    """A line north for `length_m / 2` with a gentle lateral wobble, then
    back toward the start.

    The inbound leg is the same points in reverse, except it deliberately
    stops a safe margin short of the exact start (more than
    `_CLOSURE_RADIUS_M`) instead of retracing all the way to (0, 0): an
    exact return would register as a legitimate closed single lap, but this
    fixture exists specifically to exercise the "no closure found -> manual,
    1 lap" branch of lap detection. Total recorded distance is therefore
    approximately, not exactly, `length_m`. No elevation, no extensions, no
    time.

    A small sine wobble (amplitude 5 m, period 10 points) is added on the
    cross-track axis: a perfectly straight out-and-back has zero curvature,
    so Ramer-Douglas-Peucker (`gpx_processing._rdp`, epsilon 3 m) correctly
    collapses each leg to its two endpoints -- 3 points total, legitimately
    below `MIN_POINTS=20` per the simplification contract. Real GPS
    recordings always carry some position noise; this wobble (kept far
    under `_CLOSURE_RADIUS_M`, so it does not affect the closure check
    above) restores that realism instead of exercising a degenerate
    zero-curvature path no real upload would ever produce.
    """
    half = length_m / 2.0
    num_steps = 100
    step = half / num_steps
    wobble_amplitude_m = 5.0
    wobble_period_points = 10

    def _wobble(i: int) -> float:
        return wobble_amplitude_m * math.sin(2 * math.pi * i / wobble_period_points)

    outbound = [(_wobble(i), step * i) for i in range(num_steps + 1)]  # 0 .. half

    safe_margin = _CLOSURE_RADIUS_M + 15.0
    stop_at_y = min(half, safe_margin)
    inbound = [
        (_wobble(num_steps + i), y)
        for i, y in enumerate((half - step * k for k in range(1, num_steps + 1)), start=1)
        if y >= stop_at_y
    ]

    return _render_gpx(outbound + inbound)


def figure_eight_gpx() -> bytes:
    """Two adjacent circular loops sharing a crossing point at the start.

    Loop A (smaller) is traced first, back to the shared point, then loop B
    (larger) is traced, back to the shared point again. The path therefore
    brushes within `_CLOSURE_RADIUS_M` of the start twice: once at roughly
    the halfway mark (after loop A alone) and once at the true end (after
    both loops). The two loops are deliberately different lengths so that
    loop A alone is not mistaken for a valid closed lap: there is plainly
    more distance left to travel after it (loop B), and the two loops'
    lengths are too different from each other for a two-equal-laps closure
    to validate — lap detection must reject the halfway brush as a false
    closure and fall back to a single manual lap over the whole recording.
    """
    radius_a = 250.0
    radius_b = 350.0
    points_per_loop = 150

    loop_a: list[tuple[float, float]] = []
    for i in range(points_per_loop + 1):  # start (i=0) through the shared point again
        theta = math.pi + 2 * math.pi * i / points_per_loop
        x = radius_a + radius_a * math.cos(theta)
        y = radius_a * math.sin(theta)
        loop_a.append((x, y))

    loop_b: list[tuple[float, float]] = []
    for i in range(1, points_per_loop + 1):  # skip i=0: same point as loop_a's last
        phi = 2 * math.pi * i / points_per_loop
        x = -radius_b + radius_b * math.cos(phi)
        y = radius_b * math.sin(phi)
        loop_b.append((x, y))

    return _render_gpx(loop_a + loop_b)
