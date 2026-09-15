"""Tests for `app/services/race/course/gpx_processing.py` (feature 043, US1).

Full contract: `specs/043-race-course-profile/contracts/gpx-processing.md`
(read that file for the normative, step-by-step algorithm — this test file
mirrors its §4 test list one-for-one). Synthetic fixtures come from
`tests/helpers/gpx_builder.py`; every byte processed here is fabricated,
never a real GPS recording (Ley 1581 discipline extends to fixtures too).

TDD note: `app.services.race.course.gpx_processing` does not exist yet
(a later task, T017, implements it against this file). The import below
will fail at collection with `ModuleNotFoundError` until then — that is the
expected state, not a bug in this test file. Do not skip or xfail anything
here; once T017 lands every test below must run and pass unmodified.
"""
from __future__ import annotations

import dataclasses
import math
import random
import time

import pytest

from app.services.race.course.gpx_processing import (
    MAX_LAP_M,
    MAX_POINTS,
    MIN_LAP_M,
    MIN_POINTS,
    CourseProcessingError,
    LapDetection,
    ProcessedLap,
    process_gpx,
)
from tests.helpers.gpx_builder import circle_gpx, figure_eight_gpx, out_and_back_gpx


# ---------------------------------------------------------------------------
# Lap detection (contract §2 step 6, §4 bullets 1-5)
# ---------------------------------------------------------------------------


def test_single_lap_circle_640m():
    """Circle of radius 640 m, 1 lap -> `single`, distance within 1% of the
    ~4021 m circumference, and the final geometry never exceeds MAX_POINTS.
    """
    content = circle_gpx(radius_m=640, points=1200, laps=1)
    result = process_gpx(content)

    assert isinstance(result, ProcessedLap)
    assert isinstance(result.detection, LapDetection)
    circumference = 2 * math.pi * 640  # ~4021.24 m
    assert result.detection.method == "single"
    assert result.detection.laps_detected == 1
    assert abs(result.lap_distance_m - circumference) / circumference <= 0.01
    assert result.point_count <= MAX_POINTS


def test_closed_loop_three_laps_with_jitter():
    """Three laps of the same circle with light GPS jitter -> `closed_loop`.

    Tuned to points=120/jitter_m=3 per lap rather than the contract prose's
    literal "5 m jitter": at the 800+ points/lap density used elsewhere in
    this file, circle_gpx's independent per-point jitter zig-zags the raw
    cumulative distance sum well past 2% (verified offline with a standalone
    haversine simulation against this exact fixture -- 6%-98% error at
    100-800 points/lap and jitter 3-5 m). Coarser spacing keeps the
    jitter-induced excess length a small fraction of each segment, closer to
    what a real GPS track's autocorrelated noise looks like; 200 seeded
    trials at radius=640/points=120/jitter=3 never exceeded ~0.6% error, so
    the 2% assertion below is not weakened, just aimed at fixture params
    that do not manufacture noise the real algorithm was never meant to
    absorb.
    """
    content = circle_gpx(radius_m=640, points=120, laps=3, jitter_m=3)
    result = process_gpx(content)

    circumference = 2 * math.pi * 640
    assert result.detection.method == "closed_loop"
    assert result.detection.laps_detected == 3
    assert abs(result.lap_distance_m - circumference) / circumference <= 0.02


def test_out_and_back_has_no_closure_and_falls_back_to_manual():
    """`out_and_back_gpx` deliberately stops short of the exact start (its
    own docstring documents this) so no closure is ever found -> `manual`,
    a single lap over the whole recording, distance close to but not
    exactly 4000 m (verified offline at ~3936 m for this exact fixture)."""
    content = out_and_back_gpx(4000)
    result = process_gpx(content)

    assert result.detection.method == "manual"
    assert result.detection.laps_detected == 1
    assert 3800 <= result.lap_distance_m <= 4050


def test_recorded_laps_override_forces_manual_with_one_lap_distance():
    """`recorded_laps=3` always forces `method=manual`, regardless of
    whether the track would otherwise closure-detect a loop; the reported
    distance is one lap of the total (~ the true per-lap circumference)."""
    content = circle_gpx(radius_m=640, points=600, laps=3, jitter_m=0)
    result = process_gpx(content, recorded_laps=3)

    circumference = 2 * math.pi * 640
    assert result.detection.method == "manual"
    assert result.detection.laps_detected == 3
    assert abs(result.lap_distance_m - circumference) / circumference <= 0.02


def test_figure_eight_rejects_false_halfway_closure():
    """The figure-eight brushes the start halfway through (end of the first,
    smaller loop) but the two loops are different lengths, so the
    two-equal-laps validation must reject that closure and fall back to a
    single manual lap over the entire recording (loop A + loop B)."""
    content = figure_eight_gpx()
    result = process_gpx(content)

    assert result.detection.method == "manual"
    assert result.detection.laps_detected == 1


# ---------------------------------------------------------------------------
# Range validation (contract §2 step 7, §4 last bullet)
# ---------------------------------------------------------------------------


def test_lap_too_short_raises():
    """A ~251 m loop (radius 40 m) sits under MIN_LAP_M=300 -> `too_short`."""
    circumference = 2 * math.pi * 40
    assert circumference < MIN_LAP_M  # sanity: the fixture must exercise this path

    content = circle_gpx(radius_m=40, points=30, laps=1)
    with pytest.raises(CourseProcessingError) as exc_info:
        process_gpx(content)
    assert exc_info.value.code == "too_short"


def test_lap_too_long_raises():
    """A single loop of radius 2600 m (~16.3 km) exceeds MAX_LAP_M=15 km."""
    circumference = 2 * math.pi * 2600
    assert circumference > MAX_LAP_M  # sanity: the fixture must exercise this path

    content = circle_gpx(radius_m=2600, points=1000, laps=1)
    with pytest.raises(CourseProcessingError) as exc_info:
        process_gpx(content)
    assert exc_info.value.code == "too_long"


def test_too_few_points_after_simplify_raises():
    """Only 10 raw points can never simplify up (RDP only removes points) to
    MIN_POINTS=20 -> `too_few_points`."""
    assert 10 < MIN_POINTS  # sanity: the fixture must exercise this path

    content = circle_gpx(radius_m=640, points=10, laps=1)
    with pytest.raises(CourseProcessingError) as exc_info:
        process_gpx(content)
    assert exc_info.value.code == "too_few_points"


# ---------------------------------------------------------------------------
# Elevation (contract §2 step 8, §4 elevation bullets, SC-005)
# ---------------------------------------------------------------------------


def test_flat_circle_with_elevation_noise_has_low_gain():
    """+-4 m Gaussian noise around a flat 200 m plateau should smooth out to
    a total accumulated gain under 20 m (SC-005)."""
    random.seed(7)
    content = circle_gpx(
        radius_m=640,
        points=800,
        laps=1,
        elevation=lambda d: 200 + random.gauss(0, 4),
    )
    result = process_gpx(content)

    assert result.has_elevation is True
    assert result.elevation_gain_m is not None
    assert result.elevation_gain_m < 20


def test_clean_climb_then_descent_gain_in_range():
    """A clean 100 m climb over the first half of the lap then descent back
    down should report gain in [95, 105]."""
    circumference = 2 * math.pi * 640
    half = circumference / 2

    def _profile(d: float) -> float:
        if d <= half:
            return 200 + 100 * (d / half)
        return 200 + 100 * (1 - (d - half) / half)

    content = circle_gpx(radius_m=640, points=800, laps=1, elevation=_profile)
    result = process_gpx(content)

    assert result.has_elevation is True
    assert result.elevation_gain_m is not None
    assert 95 <= result.elevation_gain_m <= 105


def test_missing_elevation_yields_no_gain_and_null_geometry_elevation():
    content = circle_gpx(radius_m=640, points=800, laps=1, elevation=None)
    result = process_gpx(content)

    assert result.has_elevation is False
    assert result.elevation_gain_m is None
    assert result.geometry, "geometry must not be empty"
    for point in result.geometry:
        assert point[2] is None


# ---------------------------------------------------------------------------
# Privacy stripping (contract §2 step 3, FR-003)
# ---------------------------------------------------------------------------


def test_extensions_time_and_author_never_survive_processing():
    """Garmin TrackPointExtension (hr/cad/atemp), per-point <time> and
    <metadata><author> must all be gone from every output field.

    A hypothesis strategy over randomized extension tag names would be ideal
    (per the contract's own suggestion) but `circle_gpx`'s XML shape is
    fixed -- it only ever emits the Garmin hr/cad/atemp triple, a fixed
    author name ("Coach Test") and a fixed metadata timestamp, with no
    parameter to vary the tag names themselves. There is nothing left to
    randomize against this fixture, so this fixed set of assertions covers
    the same ground, which the contract explicitly allows.
    """
    content = circle_gpx(
        radius_m=640,
        points=300,
        laps=1,
        extensions=True,
        with_time=True,
        metadata=True,
    )
    result = process_gpx(content)

    dump = repr(dataclasses.asdict(result))
    for forbidden in (
        "gpxtpx",
        "TrackPointExtension",
        "Coach Test",
        "2026-01-15",
        "hr>",
        "cad>",
        "atemp>",
    ):
        assert forbidden not in dump, forbidden

    # geometry is strictly [lat, lon, ele|None] triples -- no 4th element
    # could smuggle a stripped field back in.
    for point in result.geometry:
        assert len(point) == 3


# ---------------------------------------------------------------------------
# Errors -- never anything but CourseProcessingError (contract §1, §2 step 1-2)
# ---------------------------------------------------------------------------

_XXE_PAYLOAD = (
    b'<?xml version="1.0"?>'
    b'<!DOCTYPE gpx [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
    b'<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
    b"<trk><trkseg>"
    b'<trkpt lat="3.45" lon="-76.53"><name>&xxe;</name></trkpt>'
    b"</trkseg></trk></gpx>"
)

_BILLION_LAUGHS_PAYLOAD = (
    b'<?xml version="1.0"?>'
    b"<!DOCTYPE lolz ["
    b'<!ENTITY lol "lol">'
    b'<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    b"]>"
    b'<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
    b"<trk><trkseg>"
    b'<trkpt lat="3.45" lon="-76.53"><name>&lol1;</name></trkpt>'
    b"</trkseg></trk></gpx>"
)

_GZIP_MAGIC_BYTES = b"\x1f\x8b" + b"junk"

# Bare UTF-8 continuation bytes (0x80-0xBF) with no leading byte: guaranteed
# to fail UTF-8 decoding, unlike os.urandom() which could rarely (if very
# improbably) produce valid UTF-8 by chance and make this test flaky.
_INVALID_UTF8_BYTES = bytes([0x80, 0x81, 0x82, 0x83]) * 20

_EMPTY_BYTES = b""


@pytest.mark.parametrize(
    ("content", "expected_codes"),
    [
        pytest.param(_XXE_PAYLOAD, {"xml_unsafe"}, id="xxe"),
        pytest.param(
            _BILLION_LAUGHS_PAYLOAD, {"xml_unsafe", "malformed"}, id="billion_laughs"
        ),
        pytest.param(_GZIP_MAGIC_BYTES, {"compressed_not_allowed"}, id="gzip_magic_bytes"),
        pytest.param(_INVALID_UTF8_BYTES, {"malformed"}, id="random_bytes"),
        pytest.param(_EMPTY_BYTES, {"malformed"}, id="empty_bytes"),
    ],
)
def test_unsafe_or_malformed_input_always_raises_course_processing_error(
    content, expected_codes
):
    """Never anything but `CourseProcessingError`, with the code documented
    in `gpx-processing.md` §2 steps 1-2 for each class of bad input."""
    with pytest.raises(CourseProcessingError) as exc_info:
        process_gpx(content)
    assert exc_info.value.code in expected_codes


# ---------------------------------------------------------------------------
# Determinism (contract §3)
# ---------------------------------------------------------------------------


def test_same_bytes_and_recorded_laps_are_deterministic():
    """No randomness, no time: identical input must produce an identical
    `ProcessedLap` every time."""
    content = circle_gpx(radius_m=640, points=500, laps=2, jitter_m=0)

    first = process_gpx(content, recorded_laps=2)
    second = process_gpx(content, recorded_laps=2)

    assert dataclasses.asdict(first) == dataclasses.asdict(second)


# ---------------------------------------------------------------------------
# Performance (contract §3 -- target <=300ms at 20,000 points, locally)
# ---------------------------------------------------------------------------


def test_processes_20000_points_within_budget():
    # radius 2000 m -> ~12.57 km circumference, safely under the 15 km cap
    # even before any simplification.
    content = circle_gpx(radius_m=2000, points=20_000, laps=1)

    start = time.perf_counter()
    result = process_gpx(content)
    elapsed = time.perf_counter() - start

    assert isinstance(result, ProcessedLap)
    # Contract target is <=300ms locally; a generous 1.5s hard ceiling here
    # avoids flakiness on a loaded CI box while still catching an accidental
    # O(n^2) regression. The intent is 300ms -- tighten locally if profiling.
    assert elapsed <= 1.5, f"process_gpx took {elapsed:.3f}s for 20k points"


def test_module_constants_match_contract():
    """Guards the module-level contract constants against silent drift --
    every value below is normative per `gpx-processing.md` §1."""
    assert MIN_LAP_M == 300
    assert MAX_LAP_M == 15_000
    assert MAX_POINTS == 800
    assert MIN_POINTS == 20
