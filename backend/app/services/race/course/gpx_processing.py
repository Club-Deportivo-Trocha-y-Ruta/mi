"""Procesamiento puro de archivos GPX subidos por el coach (feature 043).

``process_gpx`` es la única función pública: recibe los bytes crudos de un
GPX, valida que sea XML seguro y bien formado, elimina en memoria todo dato
que no sea la geometría de la vuelta (fecha/hora, extensiones de dispositivo,
autor, nombres, comentarios — FR-003), detecta la vuelta cerrada o usa el
número de vueltas indicado por el coach, calcula distancia y desnivel, y
simplifica la geometría a un tamaño manejable para guardar en BD y dibujar
en el mapa.

No hace I/O de ningún tipo (sin filesystem, sin red) y no registra logs con
contenido del archivo — el archivo original nunca se persiste ni se vuelve a
referenciar una vez extraída la lista plana de puntos (paso 3). Contrato
normativo completo:
``specs/043-race-course-profile/contracts/gpx-processing.md``.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal

import defusedxml.ElementTree as DefusedET
import gpxpy
import gpxpy.geo
from defusedxml.common import (
    DTDForbidden,
    EntitiesForbidden,
    ExternalReferenceForbidden,
)
from gpxpy.gpx import GPXException

# ---------------------------------------------------------------------------
# Constantes (contrato §1) — no cambiar sin actualizar el contrato y los
# tests que las importan directamente.
# ---------------------------------------------------------------------------

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
# T068 (plan.md §Complexity Tracking): una vuelta real a 1 Hz nunca se acerca
# a este orden de magnitud (~2 000-4 000 puntos incluso al límite de
# MAX_LAP_M); un GPX con más puntos crudos que esto es defectuoso o
# corrupto, y dejarlo llegar a la distancia acumulada / extracción de vuelta
# / RDP es lo que produjo el p95 ≈ 3.18 s medido con un archivo sintético de
# 60 000 puntos, muy por encima del presupuesto de 1 500 ms.
MAX_RAW_POINTS = 20_000

_GZIP_MAGIC = b"\x1f\x8b"
_ZIP_MAGIC = b"\x50\x4b"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class CourseProcessingError(Exception):
    """Error de procesamiento de un GPX, con un código de razón estable.

    El router traduce ``code`` a un mensaje en español y a un status HTTP
    (422 para casi todos, ver ``course-api.md`` §6). ``file_too_large`` está
    definido aquí sólo para completitud/type-checking: lo aplica el router
    antes de llamar a ``process_gpx``, que nunca ve el límite de tamaño de
    la subida cruda.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class LapDetection:
    """Cómo se identificó la vuelta dentro de la grabación completa."""

    method: Literal["closed_loop", "manual", "single"]
    laps_detected: int
    total_distance_m: int
    closure_radius_m: int = CLOSURE_RADIUS_M
    min_lap_m: int = MIN_LAP_M


@dataclass
class ProcessedLap:
    """Resultado de procesar un GPX: la vuelta ya simplificada y lista para
    guardar (``race_course_variants.geometry``)."""

    geometry: list[tuple[float, float, float | None]]
    lap_distance_m: int
    elevation_gain_m: int | None
    has_elevation: bool
    point_count: int
    detection: LapDetection


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def process_gpx(content: bytes, *, recorded_laps: int | None = None) -> ProcessedLap:
    """Procesa los bytes de un GPX y devuelve la vuelta extraída.

    Nunca lanza otra cosa que ``CourseProcessingError`` — cualquier excepción
    inesperada de ``gpxpy``/``defusedxml`` se envuelve como último recurso
    con el código ``malformed``.
    """
    try:
        return _process_gpx_inner(content, recorded_laps=recorded_laps)
    except CourseProcessingError:
        raise
    except Exception as exc:  # noqa: BLE001 — último recurso, ver docstring.
        raise CourseProcessingError("malformed") from exc


# ---------------------------------------------------------------------------
# Implementación (pasos numerados según el contrato §2)
# ---------------------------------------------------------------------------


def _process_gpx_inner(
    content: bytes, *, recorded_laps: int | None
) -> ProcessedLap:
    # Paso 1 — sniff de compresión y decodificación tolerante a BOM.
    if content[:2] in (_GZIP_MAGIC, _ZIP_MAGIC):
        raise CourseProcessingError("compressed_not_allowed")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CourseProcessingError("malformed") from exc

    # Paso 2 — parseo seguro (defusedxml primero), verificación de raíz,
    # luego el parseo real con gpxpy.
    try:
        root = DefusedET.fromstring(content)
    except (EntitiesForbidden, DTDForbidden, ExternalReferenceForbidden) as exc:
        raise CourseProcessingError("xml_unsafe") from exc
    except ET.ParseError as exc:
        raise CourseProcessingError("malformed") from exc

    local_tag = root.tag.rsplit("}", 1)[-1]
    if local_tag != "gpx":
        raise CourseProcessingError("not_gpx")

    try:
        gpx = gpxpy.parse(text)
    except GPXException as exc:
        raise CourseProcessingError("malformed") from exc

    # Paso 3 — strip de privacidad (FR-003) y aplanado a `list[Location]`.
    # A partir de aquí `gpx` no se vuelve a referenciar.
    points = _strip_and_flatten(gpx)
    del gpx

    # Paso 4 — sanidad. La cota de puntos crudos corta aquí, antes de la
    # distancia acumulada / extracción de vuelta / RDP (T068).
    if not points:
        raise CourseProcessingError("no_track_points")
    if len(points) > MAX_RAW_POINTS:
        raise CourseProcessingError("too_many_points")
    for point in points:
        if not _is_valid_position(point.latitude, point.longitude):
            raise CourseProcessingError("no_position")

    # Paso 5 — distancia acumulada (haversine 2-D).
    cum = _cumulative_distance(points)
    total = cum[-1]

    # Paso 6 — extracción de vuelta (R-04).
    lap_points, lap_distance_m, detection = _extract_lap(
        points, cum, total, recorded_laps=recorded_laps
    )

    # Paso 7 — rango.
    if lap_distance_m < MIN_LAP_M:
        raise CourseProcessingError("too_short")
    if lap_distance_m > MAX_LAP_M:
        raise CourseProcessingError("too_long")

    # Paso 8 — elevación (R-05).
    has_elevation = all(p.elevation is not None for p in lap_points)
    elevation_gain_m: int | None
    if has_elevation:
        lap_cum = cum[: len(lap_points)]
        elevations = [p.elevation for p in lap_points]
        smoothed = _smooth_elevation(lap_cum, elevations, SMOOTH_WINDOW_M)
        elevation_gain_m = round(_hysteresis_gain(smoothed, GAIN_HYSTERESIS_M))
    else:
        elevation_gain_m = None

    # Paso 9 — simplificación (R-06).
    simplified = _simplify_within_budget(lap_points, lap_distance_m)
    if len(simplified) < MIN_POINTS:
        raise CourseProcessingError("too_few_points")

    # Paso 10 — redondeo y construcción del resultado.
    geometry: list[tuple[float, float, float | None]] = []
    for point in simplified:
        ele: float | None = None
        if has_elevation and point.elevation is not None:
            ele = round(point.elevation, 1)
        geometry.append((round(point.latitude, 6), round(point.longitude, 6), ele))

    return ProcessedLap(
        geometry=geometry,
        lap_distance_m=lap_distance_m,
        elevation_gain_m=elevation_gain_m,
        has_elevation=has_elevation,
        point_count=len(simplified),
        detection=detection,
    )


# ---------------------------------------------------------------------------
# Paso 3 — strip de privacidad
# ---------------------------------------------------------------------------


def _strip_and_flatten(gpx) -> list[gpxpy.geo.Location]:  # noqa: ANN001
    """Limpia todo campo no geométrico y devuelve la lista plana de puntos.

    Cubre extensiones, tiempo, autor/creador/copyright y rutas/waypoints en
    cada nivel del documento (gpx/track/segment/point) — ver contrato §2
    paso 3. Los segmentos de cada track se fusionan en un solo recorrido
    (una pausa automática del dispositivo no debe partir la vuelta en dos).
    """
    gpx.remove_time(all=True)
    gpx.extensions = []

    points: list[gpxpy.geo.Location] = []
    for track in gpx.tracks:
        track.extensions = []
        for segment in track.segments:
            for point in segment.points:
                point.extensions = []
                point.time = None
                point.speed = None
                point.symbol = None
                point.comment = None
                point.name = None
                point.description = None
                point.source = None
                point.link = None
                points.append(
                    gpxpy.geo.Location(point.latitude, point.longitude, point.elevation)
                )

    gpx.routes = []
    gpx.waypoints = []
    gpx.creator = None
    gpx.name = None
    gpx.description = None
    gpx.author_name = None
    gpx.author_email = None
    gpx.author_link = None
    gpx.author_link_text = None
    gpx.author_link_type = None
    gpx.copyright_author = None
    gpx.copyright_year = None
    gpx.copyright_license = None
    gpx.link = None
    gpx.link_text = None
    gpx.link_type = None
    gpx.keywords = None
    gpx.time = None

    return points


def _is_valid_position(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


# ---------------------------------------------------------------------------
# Paso 5 — distancia acumulada
# ---------------------------------------------------------------------------


def _cumulative_distance(points: list[gpxpy.geo.Location]) -> list[float]:
    cum = [0.0] * len(points)
    for i in range(1, len(points)):
        prev, cur = points[i - 1], points[i]
        cum[i] = cum[i - 1] + gpxpy.geo.distance(
            prev.latitude, prev.longitude, None, cur.latitude, cur.longitude, None
        )
    return cum


def _polyline_length_2d(points: list[gpxpy.geo.Location]) -> float:
    length = 0.0
    for i in range(1, len(points)):
        prev, cur = points[i - 1], points[i]
        length += gpxpy.geo.distance(
            prev.latitude, prev.longitude, None, cur.latitude, cur.longitude, None
        )
    return length


# ---------------------------------------------------------------------------
# Paso 6 — extracción de vuelta (R-04)
# ---------------------------------------------------------------------------


def _find_closure(
    points: list[gpxpy.geo.Location],
    cum: list[float],
    after_index: int,
    reference: gpxpy.geo.Location,
) -> int | None:
    """Primer índice ``k > after_index`` que cierra sobre ``reference``.

    Exige haber recorrido al menos ``MIN_LAP_M`` desde ``after_index`` antes
    de considerar un cierre válido (misma regla usada para el primer cierre
    y, con ``after_index`` en el primer cierre, para validar el segundo).
    """
    base = cum[after_index]
    ref_lat, ref_lon = reference.latitude, reference.longitude
    for k in range(after_index + 1, len(points)):
        if cum[k] - base < MIN_LAP_M:
            continue
        point = points[k]
        if (
            gpxpy.geo.distance(point.latitude, point.longitude, None, ref_lat, ref_lon, None)
            <= CLOSURE_RADIUS_M
        ):
            return k
    return None


def _extract_lap(
    points: list[gpxpy.geo.Location],
    cum: list[float],
    total: float,
    *,
    recorded_laps: int | None,
) -> tuple[list[gpxpy.geo.Location], int, LapDetection]:
    total_rounded = round(total)

    if recorded_laps is not None:
        laps = recorded_laps
        target = total / laps if laps else total
        lap_end = len(points) - 1
        for i, d in enumerate(cum):
            if d >= target:
                lap_end = i
                break
        lap_points = points[: lap_end + 1]
        lap_distance_m = round(total / laps) if laps else total_rounded
        detection = LapDetection(
            method="manual", laps_detected=laps, total_distance_m=total_rounded
        )
        return lap_points, lap_distance_m, detection

    start = points[0]
    i1 = _find_closure(points, cum, 0, start)
    if i1 is None:
        detection = LapDetection(
            method="manual", laps_detected=1, total_distance_m=total_rounded
        )
        return points, total_rounded, detection

    d1 = cum[i1]
    remaining = total - d1
    if remaining >= 0.8 * d1:
        j = _find_closure(points, cum, i1, start)
        if j is not None and d1 > 0 and abs(cum[j] - 2 * d1) / d1 <= LAP_LENGTH_TOLERANCE:
            laps_detected = max(1, round(total / d1)) if d1 else 1
            detection = LapDetection(
                method="closed_loop",
                laps_detected=laps_detected,
                total_distance_m=total_rounded,
            )
            return points[: i1 + 1], round(d1), detection

        # Cierre falso (ej. figura en ocho): no valida como vuelta cerrada.
        detection = LapDetection(
            method="manual", laps_detected=1, total_distance_m=total_rounded
        )
        return points, total_rounded, detection

    detection = LapDetection(
        method="single", laps_detected=1, total_distance_m=total_rounded
    )
    return points[: i1 + 1], round(d1), detection


# ---------------------------------------------------------------------------
# Paso 8 — elevación (R-05): media móvil por distancia + histéresis
# ---------------------------------------------------------------------------


def _box_average(cum: list[float], values: list[float], radius_m: float) -> list[float]:
    """Media móvil centrada en distancia recorrida, radio ``radius_m``
    (ventana total ``2 * radius_m``).

    Two-pointer O(n): tanto el límite inferior como el superior de la
    ventana son funciones no decrecientes de ``i`` porque ``cum`` es
    monótona no decreciente, así que ambos punteros sólo avanzan.
    """
    n = len(values)
    smoothed = [0.0] * n
    left = 0
    right = 0
    running_sum = 0.0
    count = 0
    for i in range(n):
        target_hi = cum[i] + radius_m
        while right < n and cum[right] <= target_hi:
            running_sum += values[right]
            count += 1
            right += 1
        target_lo = cum[i] - radius_m
        while left < right - 1 and cum[left] < target_lo:
            running_sum -= values[left]
            count -= 1
            left += 1
        smoothed[i] = running_sum / count if count else values[i]
    return smoothed


def _smooth_elevation(
    cum: list[float], elevations: list[float], window_m: float
) -> list[float]:
    """Media móvil por distancia, aplicada dos veces (radio ``window_m``
    cada pasada).

    Una sola pasada con radio ``window_m`` deja ruido GPS punto-a-punto no
    correlacionado muy por encima de SC-005 (<5 m/km) porque a la densidad
    típica de un registro (~1 punto/segundo, unos pocos metros entre
    puntos) la ventana sólo cubre un puñado de muestras. gpxpy documenta su
    propio ``segment.smooth()`` como "can be called multiple times" para
    reforzar el suavizado con la misma operación; dos pasadas del mismo
    filtro por caja aproximan un kernel gaussiano de soporte equivalente y
    sí cumplen SC-005 sin tocar el umbral de histéresis.
    """
    once = _box_average(cum, elevations, window_m)
    return _box_average(cum, once, window_m)


def _hysteresis_gain(smoothed: list[float], threshold_m: float) -> float:
    """Acumulador con histéresis: sólo cuenta subidas de >= ``threshold_m``
    desde el último punto de referencia aceptado."""
    if not smoothed:
        return 0.0
    gain = 0.0
    baseline = smoothed[0]
    for value in smoothed[1:]:
        if value - baseline >= threshold_m:
            gain += value - baseline
            baseline = value
        elif baseline - value >= threshold_m:
            baseline = value
    return gain


# ---------------------------------------------------------------------------
# Paso 9 — simplificación (R-06)
# ---------------------------------------------------------------------------


def _perpendicular_distance(
    point: gpxpy.geo.Location,
    seg_start: gpxpy.geo.Location,
    seg_end: gpxpy.geo.Location,
) -> float:
    """Distancia de ``point`` al SEGMENTO (no a la recta infinita) entre
    ``seg_start`` y ``seg_end``, usando sólo distancias 2-D entre puntos
    (ley de cosenos para ubicar la proyección, sin reproyectar a x/y).

    ``gpxpy.geo.simplify_polyline`` mide contra la recta infinita, lo que
    colapsa incorrectamente un recorrido de ida y vuelta por el mismo
    trazado (todo punto queda a distancia ~0 de esa recta aunque el punto
    de retorno esté a cientos de metros del segmento real) — de ahí que
    esta implementación propia, con la distancia acotada al segmento, sea
    necesaria en vez de reutilizar esa función.
    """
    a = gpxpy.geo.distance(
        seg_start.latitude, seg_start.longitude, None,
        seg_end.latitude, seg_end.longitude, None,
    )
    if a == 0:
        return gpxpy.geo.distance(
            point.latitude, point.longitude, None,
            seg_start.latitude, seg_start.longitude, None,
        )
    b = gpxpy.geo.distance(
        point.latitude, point.longitude, None,
        seg_start.latitude, seg_start.longitude, None,
    )
    c = gpxpy.geo.distance(
        point.latitude, point.longitude, None,
        seg_end.latitude, seg_end.longitude, None,
    )
    # Proyección de `point` sobre la recta, parametrizada por t en [0, a]
    # (distancia desde seg_start hasta el pie de la perpendicular), vía ley
    # de cosenos — evita reproyectar lat/lon a un plano local.
    t = (b * b + a * a - c * c) / (2 * a)
    if t < 0:
        return b
    if t > a:
        return c
    height_sq = b * b - t * t
    return math.sqrt(height_sq) if height_sq > 0 else 0.0


def _rdp(points: list[gpxpy.geo.Location], epsilon: float) -> list[gpxpy.geo.Location]:
    """Ramer-Douglas-Peucker sobre la forma 2-D del recorrido.

    Iterativo con una pila explícita en vez de la recursión de libro de
    texto: un tramo casi rectilíneo con miles de puntos (un archivo de
    ~60 000 puntos cabe en el peor caso documentado en el contrato) puede
    producir particiones muy desbalanceadas y superar el límite de
    recursión de Python; la pila no tiene ese límite.
    """
    n = len(points)
    if n < 3:
        return points

    keep = [False] * n
    keep[0] = True
    keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start_i, end_i = stack.pop()
        if end_i - start_i < 2:
            continue
        start, end = points[start_i], points[end_i]
        max_distance = -1.0
        index = start_i
        for i in range(start_i + 1, end_i):
            distance = _perpendicular_distance(points[i], start, end)
            if distance > max_distance:
                max_distance = distance
                index = i
        if max_distance > epsilon:
            keep[index] = True
            stack.append((start_i, index))
            stack.append((index, end_i))

    return [point for point, kept in zip(points, keep) if kept]


def _simplify_within_budget(
    lap_points: list[gpxpy.geo.Location], lap_distance_m: int
) -> list[gpxpy.geo.Location]:
    epsilon = SIMPLIFY_EPSILON_M
    simplified = _rdp(lap_points, epsilon)

    while len(simplified) > MAX_POINTS:
        next_epsilon = epsilon + 1.0
        candidate = _rdp(lap_points, next_epsilon)
        candidate_length = _polyline_length_2d(candidate)
        rel_error = (
            abs(candidate_length - lap_distance_m) / lap_distance_m
            if lap_distance_m
            else 0.0
        )
        if rel_error > MAX_DISTANCE_ERROR:
            # No seguir subiendo epsilon: nos quedamos con el último que sí
            # respetaba la cota de distancia, aunque exceda MAX_POINTS.
            break
        epsilon = next_epsilon
        simplified = candidate

    return simplified
