"""``compute_field_metrics`` / ``compute_category_metrics`` — motor único de
métricas de carrera (features 037 y 045).

Implementa el contrato de ``specs/037-ai-insights-v3-causal/data-model.md``
§FieldMetrics y la regla "Expected-vs-actual" de ``plan.md``, extendido por
``specs/045-competitions-one-place/data-model.md`` §1 (MetricSet) y
``research.md`` R-01..R-04: este módulo es la **única** fuente de Parrilla,
Percentil, Brecha vs. mediana, Brecha vs. 1.ª posición y Brecha vs. podio.
Todo otro consumidor delega aquí o queda eliminado.

Entrada: colecciones ORM ya cargadas (``RaceResult``/``RaceEvent``/
``RaceSeries``/``RaceCategory``) vía :mod:`app.services.race.queries`
(``load_results``/``load_events``/``load_series``/``load_categories``).
Ambas funciones públicas son **puras y síncronas**: no hacen I/O, solo
pandas/Python puro sobre listas de objetos ORM ya en memoria — siguen el
patrón de ``analytics.athlete_progression`` (joins en Python, no en SQL).

Diseño interno (feature 045)
-----------------------------
``compute_field_metrics`` y ``compute_category_metrics`` son ahora
orquestadores delgados sobre un único núcleo por-categoría:

1. :func:`_build_category_context` recorre una vez las filas de una
   (válida, categoría) y produce un ``_CategoryContext`` inmutable
   (tamaño de pelotón, cronometrados, tiempo mínimo/máximo, mediana, fila
   oficial de P1 y de P3).
2. Cada campo de ``MetricSet`` tiene su propia función de cómputo pura
   ``(row, ctx) -> valor``, registrada en ``_METRIC_CALCULATORS``.
   :func:`_metric_set_for_row` arma el dict recorriendo ese registro.
3. Agregar una métrica nueva es agregar una función + una entrada en el
   registro + un campo en ``MetricSet`` — no hay que tocar las funciones
   existentes (abierto a extensión, cerrado a modificación).

MetricSet (feature 045, data-model.md §1)
------------------------------------------
- ``field_size`` (« Parrilla »): cuenta a quien cruzó meta, ``FINISHED`` o
  ``MINUS_LAPS`` (perder vueltas no te saca del pelotón), en la (válida,
  categoría).
- ``timed_finishers``: cuenta solo ``FINISHED`` con ``race_time_ms`` no
  nulo — el denominador real del percentil y de la brecha vs. mediana. Un
  ``MINUS_LAPS`` no es comparable en tiempo (recorrió menos vueltas), así
  que nunca cuenta aquí aunque sí cuente en ``field_size``.
- ``position``: la posición oficial, solo si es miembro del pelotón
  (``None`` para DNF/DNS/DSQ).
- ``percentile`` (« Percentil »): ``round(100 × (1 − (t − t_min) ÷ (t_max − t_min)))``
  sobre los tiempos de los ``timed_finishers`` de la (válida, categoría) —
  el más rápido saca 100, el más lento saca 0, los tiempos empatados sacan
  el mismo valor. Es ``None`` si el propio resultado no es ``FINISHED`` con
  tiempo (incluye ``MINUS_LAPS`` y DNF/DNS/DSQ), si ``timed_finishers <
  MIN_FIELD`` (muestra insuficiente para que un percentil signifique algo),
  o si ``t_max == t_min`` (todo el pelotón cronometrado empatado).
- ``gap_to_median_pct`` (« Brecha vs. mediana »): ``100 × (t − mediana) ÷ mediana``
  sobre los ``timed_finishers``; mismas puertas que ``percentile`` (requiere
  ``timed_finishers >= MIN_FIELD`` y tiempo propio).
- ``gap_to_winner_pct`` / ``gap_to_winner_ms`` (« Brecha vs. 1.ª posición »):
  contra el tiempo **oficial** de la posición 1 (no necesariamente el más
  rápido — difieren solo si hay penalizaciones, research.md R-04). ``None``
  si no hay tiempo de P1 o el propio resultado no tiene tiempo. Sin puerta
  de tamaño mínimo. ``gap_to_winner_ms`` es exclusivo de coach/admin, igual
  que ``gap_to_podium_ms`` (data-model.md §1).
- ``gap_to_podium_pct`` / ``gap_to_podium_ms`` (« Brecha vs. podio »):
  ídem contra el tiempo oficial de la posición 3. Sin puerta de tamaño
  mínimo.

``compute_field_metrics`` sigue exponiendo estos valores bajo los nombres
heredados de la feature 037 (``gap_pct`` = ``gap_to_winner_pct``,
``gap_to_p1_ms`` = ``gap_to_winner_ms``, ``gap_to_p3_ms`` =
``gap_to_podium_ms``) para no romper a sus consumidores actuales
(``history.py``, ``race/ai/nodes/compute_metrics.py``,
``newsletter_builder.py``) — esos módulos migran a los nombres canónicos en
fases posteriores de la 045.
``compute_field_metrics`` también agrega ``timed_finishers`` y
``gap_to_podium_pct`` como campos nuevos.

``compute_category_metrics`` es el punto de entrada nuevo (045): da un
``MetricSet`` por cada fila de una (válida, categoría), con los nombres
canónicos de la tabla de arriba — sirve al detalle de competencia para
adjuntar métricas por fila sin ir a la base de datos por atleta.

Salida de ``compute_field_metrics``: ``dict[int, dict]`` keyed por
``event_id`` — una entrada por cada válida de la temporada en la que
``competitor_id`` tiene un ``RaceResult`` (cualquier estado). ``field_size``
cuenta a todo el que terminó (``FINISHED`` o ``MINUS_LAPS``); los campos
derivados de TIEMPO (``race_time_ms``, ``gap_to_p1_ms``, ``gap_pct``,
``gap_to_p3_ms``, ``gap_to_median_pct``) quedan en ``None`` salvo que el
estado propio sea ``FINISHED`` estricto. Cada valor es un dict
JSON-serializable con las claves de ``FieldMetrics`` del data-model de la
037, redondeadas a 1 decimal (``percentile`` se redondea a entero, ver
arriba), sin exponer ids de otros corredores.

Privacidad (CLAUDE.md): la salida nunca incluye ``competitor_id`` de
terceros — solo agregados (``field_size``, ``field_strength``,
``category_median_time_ms``) y los valores propios del atleta analizado.
``compute_category_metrics`` expone métricas por fila (result_id), también
sin ids de terceros más allá del propio ``result_id`` de cada fila.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean, median
from typing import Any, Callable, Optional, Protocol, Sequence, TypedDict

from app.models.race_category import RaceCategory
from app.models.race_event import RaceEvent
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_series import RaceSeries

__all__ = ["compute_field_metrics", "compute_category_metrics", "MetricInput", "MetricSet", "MIN_FIELD"]

# ``MINUS_LAPS`` significa que el corredor terminó la carrera (con vueltas de
# menos), no que abandonó — cuenta para tamaño de pelotón y posición igual
# que ``FINISHED``. Los tiempos (percentil, gap, mediana, histórico) NO se
# comparan entre sí porque un ``MINUS_LAPS`` recorrió menos distancia que
# quien completó todas las vueltas: esas comparaciones siguen restringidas a
# ``FINISHED`` estricto con ``race_time_ms`` no nulo (``timed_finishers``).
_FIELD_MEMBER_STATUSES = (ResultStatus.FINISHED, ResultStatus.MINUS_LAPS)

# feature 045 (data-model.md §1, research.md R-01): tamaño mínimo de pelotón
# *cronometrado* para exponer percentil y brecha vs. mediana. Por debajo de
# esta cantidad de finishers con tiempo, ambos valores quedan en ``None`` —
# no hay muestra suficiente para que un percentil signifique algo. Los gaps
# oficiales (``gap_to_winner_pct``, ``gap_to_podium_pct``) NO llevan esta
# puerta (research.md R-04).
MIN_FIELD = 5

# Posiciones oficiales que definen los gaps "contra alguien" (no contra el
# más rápido): 1.ª posición y podio (3.ª). Nombradas para no repetir los
# literales 1 / 3 sin explicación en el resto del módulo.
_WINNER_POSITION = 1
_PODIUM_POSITION = 3

# Decimales de redondeo para las métricas porcentuales/de gap (todo salvo
# ``percentile``, que el data-model redondea a entero — ver ``_percentile``).
_GAP_DECIMALS = 1


class MetricInput(Protocol):
    """Lo ÚNICO que el motor lee de una fila de resultado (inversión de
    dependencias): ``RaceResult`` la satisface estructuralmente, y también
    cualquier objeto liviano con estos atributos — p. ej. el dataclass que
    arma ``results_read.py`` desde columnas sin cargar la entidad ORM.

    Se declara con propiedades de solo lectura a propósito: así la cumplen
    tanto un atributo mutable (columna ORM) como un dataclass ``frozen``.
    ``compute_category_metrics`` y el núcleo por categoría solo dependen de
    esto; ``compute_field_metrics`` además lee ``competitor_id`` y
    ``laps_behind`` y por eso sigue tipado contra ``RaceResult``.
    """

    @property
    def id(self) -> int: ...

    @property
    def event_id(self) -> int: ...

    @property
    def category_id(self) -> int: ...

    @property
    def status(self) -> ResultStatus: ...

    @property
    def position(self) -> Optional[int]: ...

    @property
    def race_time_ms(self) -> Optional[int]: ...

    @property
    def deleted_at(self) -> Optional[datetime]: ...


class MetricSet(TypedDict):
    """Forma documentada en ``specs/045-competitions-one-place/data-model.md``
    §1. Ver el docstring del módulo para las reglas de cada campo.

    ``compute_field_metrics`` incrusta estos mismos valores bajo los
    nombres heredados de la feature 037 (``gap_pct``, ``gap_to_p3_ms``);
    ``compute_category_metrics`` los devuelve tal cual, con estos nombres
    canónicos. Se modela como ``TypedDict`` (no como dataclass) porque
    ambos consumidores lo tratan como un dict JSON-serializable de acceso
    por clave (``ms["percentile"]``, ``json.dumps(out)``) — un dataclass
    obligaría a un paso extra de serialización sin aportar nada aquí, ya
    que el valor nunca se muta tras construirse.
    """

    field_size: int
    timed_finishers: int
    position: Optional[int]
    percentile: Optional[float]
    gap_to_median_pct: Optional[float]
    gap_to_winner_pct: Optional[float]
    gap_to_winner_ms: Optional[int]
    gap_to_podium_pct: Optional[float]
    gap_to_podium_ms: Optional[int]


@dataclass(frozen=True)
class _CategoryContext:
    """Agregados de una (válida, categoría), calculados una sola vez y
    compartidos por el cómputo de cada fila. Inmutable: nada dentro de
    ``_METRIC_CALCULATORS`` puede mutar el contexto de otra fila."""

    field_size: int
    timed_finishers: int
    t_min: Optional[int]
    t_max: Optional[int]
    median_time: Optional[float]
    winner_row: Optional[MetricInput]
    podium_row: Optional[MetricInput]


def _round1(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), _GAP_DECIMALS)


def _is_field_member(row: MetricInput) -> bool:
    return row.status in _FIELD_MEMBER_STATUSES


def _is_timed(row: MetricInput) -> bool:
    return row.status == ResultStatus.FINISHED and row.race_time_ms is not None


def _official_row(timed_rows: Sequence[MetricInput], *, position: int) -> Optional[MetricInput]:
    return next((r for r in timed_rows if r.position == position), None)


def _build_category_context(category_rows: Sequence[MetricInput]) -> _CategoryContext:
    """Recorre ``category_rows`` (una (válida, categoría), cualquier
    estado) una sola vez y produce los agregados que necesita cada métrica.
    Pura, O(n)."""
    field_rows = [r for r in category_rows if _is_field_member(r)]
    timed_rows = [r for r in field_rows if _is_timed(r)]
    times = [r.race_time_ms for r in timed_rows]

    return _CategoryContext(
        field_size=len(field_rows),
        timed_finishers=len(timed_rows),
        t_min=min(times) if times else None,
        t_max=max(times) if times else None,
        median_time=median(times) if times else None,
        winner_row=_official_row(timed_rows, position=_WINNER_POSITION),
        podium_row=_official_row(timed_rows, position=_PODIUM_POSITION),
    )


# --- Un calculador puro por métrica: (fila, contexto) -> valor. ------------
# Agregar una métrica nueva = agregar una función aquí + una entrada en
# ``_METRIC_CALCULATORS`` + un campo en ``MetricSet``. Ninguna función
# existente cambia (abierto/cerrado).


def _field_size(_row: MetricInput, ctx: _CategoryContext) -> int:
    return ctx.field_size


def _timed_finishers(_row: MetricInput, ctx: _CategoryContext) -> int:
    return ctx.timed_finishers


def _position(row: MetricInput, _ctx: _CategoryContext) -> Optional[int]:
    return row.position if _is_field_member(row) else None


def _percentile(row: MetricInput, ctx: _CategoryContext) -> Optional[float]:
    if not _is_timed(row):
        return None
    if ctx.timed_finishers < MIN_FIELD:
        return None
    if ctx.t_min is None or ctx.t_max is None or ctx.t_max == ctx.t_min:
        return None
    raw = 100.0 * (1 - (row.race_time_ms - ctx.t_min) / (ctx.t_max - ctx.t_min))
    return float(round(raw))


def _gap_to_median_pct(row: MetricInput, ctx: _CategoryContext) -> Optional[float]:
    if not _is_timed(row):
        return None
    if ctx.timed_finishers < MIN_FIELD:
        return None
    if not ctx.median_time:
        return None
    return _round1(100.0 * (row.race_time_ms - ctx.median_time) / ctx.median_time)


def _gap_pct_against(row: MetricInput, official_row: Optional[MetricInput]) -> Optional[float]:
    """Brecha porcentual de ``row`` contra el tiempo de ``official_row``.
    Sin puerta ``MIN_FIELD`` — research.md R-04: los gaps oficiales no la
    llevan, solo ``percentile``/``gap_to_median_pct``."""
    if not _is_timed(row) or official_row is None or not official_row.race_time_ms:
        return None
    return _round1(100.0 * (row.race_time_ms - official_row.race_time_ms) / official_row.race_time_ms)


def _gap_ms_against(row: MetricInput, official_row: Optional[MetricInput]) -> Optional[int]:
    if not _is_timed(row) or official_row is None or official_row.race_time_ms is None:
        return None
    return row.race_time_ms - official_row.race_time_ms


def _gap_to_winner_pct(row: MetricInput, ctx: _CategoryContext) -> Optional[float]:
    return _gap_pct_against(row, ctx.winner_row)


def _gap_to_winner_ms(row: MetricInput, ctx: _CategoryContext) -> Optional[int]:
    return _gap_ms_against(row, ctx.winner_row)


def _gap_to_podium_pct(row: MetricInput, ctx: _CategoryContext) -> Optional[float]:
    return _gap_pct_against(row, ctx.podium_row)


def _gap_to_podium_ms(row: MetricInput, ctx: _CategoryContext) -> Optional[int]:
    return _gap_ms_against(row, ctx.podium_row)


_METRIC_CALCULATORS: tuple[tuple[str, Callable[[MetricInput, _CategoryContext], Any]], ...] = (
    ("field_size", _field_size),
    ("timed_finishers", _timed_finishers),
    ("position", _position),
    ("percentile", _percentile),
    ("gap_to_median_pct", _gap_to_median_pct),
    ("gap_to_winner_pct", _gap_to_winner_pct),
    ("gap_to_winner_ms", _gap_to_winner_ms),
    ("gap_to_podium_pct", _gap_to_podium_pct),
    ("gap_to_podium_ms", _gap_to_podium_ms),
)


def _metric_set_for_row(row: MetricInput, ctx: _CategoryContext) -> MetricSet:
    return {name: calculator(row, ctx) for name, calculator in _METRIC_CALCULATORS}  # type: ignore[return-value]


def _metric_sets_for_category(category_rows: Sequence[MetricInput]) -> dict[int, MetricSet]:
    """Un ``MetricSet`` por fila de ``category_rows`` (una sola (válida,
    categoría)). Pura, O(n). ``category_rows`` puede traer filas de
    cualquier estado (DNF/DNS/DSQ incluidos) — sirven solo para producir
    una entrada por ``result.id``; los agregados del contexto
    (``field_size``, ``timed_finishers``, etc.) se calculan una sola vez
    sobre todo el grupo."""
    ctx = _build_category_context(category_rows)
    return {row.id: _metric_set_for_row(row, ctx) for row in category_rows}


def compute_category_metrics(
    results: Sequence[MetricInput],
    event_id: int,
    category_id: int,
) -> dict[int, MetricSet]:
    """``MetricSet`` de cada fila de una (válida, categoría) (feature 045).

    Sirve al detalle de competencia (``results_read.py``) para adjuntar
    métricas por fila sin ir a la base de datos por atleta. Pura, O(n) sobre
    ``results`` ya cargado — comparte el cómputo por categoría con
    :func:`compute_field_metrics` (ambas delegan en
    :func:`_metric_sets_for_category`), así que un mismo (evento, categoría)
    produce siempre los mismos valores por ambas rutas (invariante SC-002).

    Args:
        results: filas ya cargadas que cumplan :class:`MetricInput`
            (``RaceResult`` la satisface; también un objeto liviano armado
            desde columnas). Pueden ser de cualquier válida/categoría: se
            filtran aquí por ``event_id``/``category_id`` y por
            ``deleted_at``. Es ``Sequence`` (covariante) para que una lista
            de un subtipo estructural se acepte sin ``cast``.
        event_id: PK de ``RaceEvent``.
        category_id: PK de ``RaceCategory``.

    Returns:
        ``{result_id: MetricSet}`` — una entrada por cada ``RaceResult`` vivo
        de esa (válida, categoría), sin importar su estado (DNF/DNS/DSQ
        incluidos, con los campos derivados de tiempo en ``None``).
    """
    category_rows = [
        r
        for r in results
        if r.deleted_at is None
        and r.event_id == event_id
        and r.category_id == category_id
    ]
    return _metric_sets_for_category(category_rows)


def compute_field_metrics(
    results: list[RaceResult],
    events: list[RaceEvent],
    series: list[RaceSeries],
    categories: list[RaceCategory],
    competitor_id: int,
    season: int,
) -> dict[int, dict[str, Any]]:
    """Calcula ``FieldMetrics`` por válida para ``competitor_id`` en ``season``.

    Args:
        results: ``RaceResult`` ya filtrados de ``deleted_at`` (o no —
            se filtran de nuevo aquí por seguridad, igual que
            ``queries.load_results``).
        events: ``RaceEvent`` de cualquier temporada (se filtra por
            ``season`` internamente vía ``series``).
        series: ``RaceSeries`` de cualquier temporada.
        categories: ``RaceCategory`` (catálogo; usado solo si se necesita
            enriquecer en el futuro — hoy no se expone en la salida).
        competitor_id: PK de ``RaceCompetitor`` del atleta analizado.
        season: año de temporada (``RaceSeries.season_year``).

    Returns:
        ``{event_id: {..FieldMetrics..}}``. Vacío si el competidor no
        tiene ningún ``RaceResult`` en eventos de esa temporada. Ver el
        docstring del módulo para las reglas de ``percentile``,
        ``timed_finishers``, ``gap_pct``/``gap_to_winner_pct``,
        ``gap_to_p3_ms``/``gap_to_podium_ms`` y ``gap_to_podium_pct``
        (incluida la puerta ``MIN_FIELD``).
    """
    del categories  # reservado — no se usa hoy, mantenido por firma estable.

    live_results = [r for r in results if getattr(r, "deleted_at", None) is None]

    events_by_id: dict[int, RaceEvent] = {e.id: e for e in events}
    series_by_id: dict[int, RaceSeries] = {s.id: s for s in series}

    season_event_ids = {
        eid
        for eid, e in events_by_id.items()
        if series_by_id.get(e.series_id) is not None
        and series_by_id[e.series_id].season_year == season
    }
    if not season_event_ids:
        return {}

    # --- Agrupa quienes terminaron (FINISHED o MINUS_LAPS) por (event_id, category_id) ---
    # Pelotón real para prior_index/expected_position (solo tiene sentido
    # entre quienes compitieron) — sin cambios respecto a la feature 037.
    completed_in_season = [
        r
        for r in live_results
        if r.event_id in season_event_ids and r.status in _FIELD_MEMBER_STATUSES
    ]
    by_event_category: dict[tuple[int, int], list[RaceResult]] = defaultdict(list)
    for r in completed_in_season:
        by_event_category[(r.event_id, r.category_id)].append(r)

    # feature 045: agrupación por TODO estado (incluye DNF/DNS/DSQ) para que
    # el ``MetricSet`` del propio atleta exista aunque no haya terminado —
    # el percentil y las brechas igual salen en ``None`` en ese caso, pero
    # así ``_metric_sets_for_category`` siempre tiene una entrada para
    # ``r.id`` (comparte el mismo cómputo que ``compute_category_metrics``).
    season_results = [r for r in live_results if r.event_id in season_event_ids]
    by_event_category_all: dict[tuple[int, int], list[RaceResult]] = defaultdict(list)
    for r in season_results:
        by_event_category_all[(r.event_id, r.category_id)].append(r)

    # --- gap_pct histórico por resultado, relativo al ganador (position==1) de su (evento, categoría) ---
    # Alimenta únicamente el índice histórico (prior_index/expected_position,
    # feature 037) — no es la métrica ``gap_to_winner_pct`` de la 045 (esa
    # sale de ``_gap_pct_against`` vía el motor compartido), aunque use la
    # misma fórmula: este dict guarda el gap de TODOS los timed_rows de cada
    # grupo (no solo el del atleta) para construir el historial de terceros.
    gap_pct_by_result: dict[int, float] = {}
    for (_eid, _cid), rows in by_event_category.items():
        timed_rows = [x for x in rows if x.status == ResultStatus.FINISHED]
        winner = next((r for r in timed_rows if r.position == _WINNER_POSITION), None)
        if winner is None or winner.race_time_ms in (None, 0):
            continue
        wt = winner.race_time_ms
        for r in timed_rows:
            if r.race_time_ms is not None:
                gap_pct_by_result[r.id] = 100.0 * (r.race_time_ms - wt) / wt

    # --- índice histórico por competidor: [(event_date, gap_pct), ...] ---
    history_by_competitor: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for (eid, _cid), rows in by_event_category.items():
        ev = events_by_id.get(eid)
        if ev is None or ev.event_date is None:
            continue
        for r in rows:
            g = gap_pct_by_result.get(r.id)
            if g is not None:
                history_by_competitor[r.competitor_id].append((ev.event_date, g))

    def _prior_index(comp_id: int, before: date) -> Optional[float]:
        vals = [g for d, g in history_by_competitor.get(comp_id, []) if d < before]
        return mean(vals) if vals else None

    # --- Resultados propios del atleta en eventos de la temporada (cualquier estado) ---
    own_results = [
        r
        for r in live_results
        if r.competitor_id == competitor_id and r.event_id in season_event_ids
    ]

    out: dict[int, dict[str, Any]] = {}
    for r in own_results:
        event = events_by_id.get(r.event_id)
        if event is None:
            continue
        s = series_by_id.get(event.series_id)
        rows = by_event_category.get((r.event_id, r.category_id), [])
        is_finished = r.status == ResultStatus.FINISHED

        # feature 045: percentil, timed_finishers, brechas, gap_to_p1_ms y
        # la mediana en ms salen todos del mismo contexto compartido con
        # compute_category_metrics — ``r`` siempre está incluido (
        # by_event_category_all se construye a partir de season_results,
        # superconjunto de own_results).
        category_rows_all = by_event_category_all.get((r.event_id, r.category_id), [])
        ctx = _build_category_context(category_rows_all)
        ms = _metric_set_for_row(r, ctx)

        n = ms["field_size"]
        position = ms["position"]
        percentile = ms["percentile"]
        timed_finishers = ms["timed_finishers"]
        gap_pct = ms["gap_to_winner_pct"]
        gap_to_p3_ms = ms["gap_to_podium_ms"]
        gap_to_podium_pct = ms["gap_to_podium_pct"]
        gap_to_median_pct = ms["gap_to_median_pct"]

        gap_to_p1_ms = ms["gap_to_winner_ms"]
        category_median_time_ms: Optional[int] = (
            int(round(ctx.median_time)) if ctx.median_time else None
        )

        # --- prior_index / expected_position / delta / field_strength (sin cambios, feature 037) ---
        own_prior_index = _prior_index(competitor_id, event.event_date) if event.event_date else None

        priors_by_result: dict[int, float] = {}
        if event.event_date is not None:
            for x in rows:
                pv = _prior_index(x.competitor_id, event.event_date)
                if pv is not None:
                    priors_by_result[x.id] = pv

        coverage_with_prior = (len(priors_by_result) / n) if n else 0.0

        expected_position: Optional[int] = None
        delta_vs_expected: Optional[int] = None
        field_strength: Optional[float] = None

        if n > 0 and coverage_with_prior >= 0.5:
            field_strength = _round1(mean(priors_by_result.values()))
            if r.id in priors_by_result:
                # Menor gap_pct histórico = mejor desempeño esperado.
                ranked = sorted(priors_by_result.items(), key=lambda kv: kv[1])
                rank_among_with_prior = next(
                    idx for idx, (rid, _v) in enumerate(ranked) if rid == r.id
                )
                m = len(ranked)
                expected_position = round(
                    1 + rank_among_with_prior * (n - 1) / max(m - 1, 1)
                )
                if position is not None:
                    delta_vs_expected = expected_position - position

        is_championship = bool(getattr(event, "is_championship", False))
        series_kind = s.kind.value if s is not None and hasattr(s.kind, "value") else (str(s.kind) if s else None)
        series_level = (
            s.level.value if s is not None and hasattr(s.level, "value") else (str(s.level) if s else None)
        )
        # ``short_name`` se agrega en paralelo (worker distinto) — getattr con
        # default evita romper antes/después de que esa columna aterrice.
        series_id_val = s.id if s is not None else None
        series_name_val = s.name if s is not None else None
        series_short_name_val = getattr(s, "short_name", None) if s is not None else None

        out[r.event_id] = {
            "event_id": r.event_id,
            "valida_num": event.sequence_number,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "series_id": series_id_val,
            "series_name": series_name_val,
            "series_short_name": series_short_name_val,
            "series_kind": series_kind,
            "series_level": series_level,
            "is_championship": is_championship,
            "field_size": n,
            "timed_finishers": timed_finishers,
            "position": position,
            "percentile": percentile,
            "race_time_ms": r.race_time_ms if is_finished else None,
            "gap_to_p1_ms": gap_to_p1_ms,
            "gap_pct": gap_pct,
            "gap_to_p3_ms": gap_to_p3_ms,
            "gap_to_podium_pct": gap_to_podium_pct,
            "category_median_time_ms": category_median_time_ms,
            "gap_to_median_pct": gap_to_median_pct,
            "laps_behind": r.laps_behind,
            "prior_index": _round1(own_prior_index),
            "expected_position": expected_position,
            "delta_vs_expected": delta_vs_expected,
            "field_strength": field_strength,
            "coverage_with_prior": _round1(coverage_with_prior),
        }

    return out
