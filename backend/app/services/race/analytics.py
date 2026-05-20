"""Analíticas longitudinales del módulo Race (Fase 1.7 Paso 5).

Cuatro funciones puras async que consumen ``AsyncSession`` y devuelven
``pd.DataFrame`` o ``dict`` JSON-serializable:

- :func:`athlete_progression` — historial cronológico por competidor.
- :func:`podium_gap` — gap al P1 y al P3 por válida para los TyR de una categoría.
- :func:`club_ranking` — agregados por categoría/tier para el club (sólo
  competitors con ``athlete_id NOT NULL``, es decir matches confirmados).
- :func:`projection` — regresión lineal simple sobre histórico para estimar
  próxima válida. Marca ``confidence:low`` si n<5 (CLAUDE.md restriccion).

Decisiones de diseño:
- Las queries son **planas** por tabla (``select(Model)`` sin joins SQL).
  Los joins se hacen con pandas. Razón: el dataset por temporada es chico
  (cientos de filas), y mantiene el ``FakeAsyncSession`` simple — no
  necesitamos soportar SQL ``IN`` ni ``IS NULL`` ni joins en el fake.
- Filtros ``deleted_at IS NULL`` se aplican en Python después del select.
- DataFrames devueltos son JSON-serializables (``.to_dict("records")``
  funciona): fechas convertidas a ISO string, ints/floats nativos.

Privacidad (CLAUDE.md):
- ``competitor_id`` y agregados están OK en outputs — el coach autenticado
  ya sabe a quién consulta.
- ``club_ranking`` es agregado por categoría/tier — NO incluye identificadores
  individuales (no se expone ningún ``competitor_id`` ni nombre).
- Predicciones con ``n_samples < 5`` marcan ``confidence='low'`` siempre.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.race_category import CategoryTier
from app.models.race_result import ResultStatus

# Primitivas extraídas a queries.py en F1 (race-results v2). Re-exportamos con
# nombres legacy ``_load_*`` / ``_*_df`` para preservar compatibilidad de
# imports en tests y otros módulos.
from app.services.race.queries import (
    categories_to_df as _categories_df,
    events_to_df as _events_df,
    load_categories as _load_categories,
    load_competitors as _load_competitors,
    load_events as _load_events,
    load_results as _load_results,
    results_to_df as _results_df,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

#: Confidence thresholds para la proyección (CLAUDE.md + workflow §5.2).
_CONFIDENCE_LOW_MAX_N: int = 4   # n<5 → low
_CONFIDENCE_MED_MAX_N: int = 8   # 5..8 → medium ; >8 → high


# ---------------------------------------------------------------------------
# 1. athlete_progression
# ---------------------------------------------------------------------------


async def athlete_progression(db: AsyncSession, competitor_id: int) -> pd.DataFrame:
    """Historial cronológico de un competidor a lo largo de las válidas.

    Args:
        db: Sesión async (AsyncSession real o ``FakeAsyncSession`` para tests).
        competitor_id: PK del ``RaceCompetitor`` cuyo historial queremos.

    Returns:
        ``pd.DataFrame`` con columnas:

        - ``valida_num``         (int)
        - ``event_date``         (ISO date string)
        - ``category_code``      (str)
        - ``position``           (int o nullable)
        - ``race_time_ms``       (int o nullable)
        - ``points_awarded``     (int)
        - ``gap_to_winner_ms``   (int o nullable; 0 para P1)
        - ``gap_to_winner_pct``  (float o nullable; ej. 12.5 = +12.5%)

        Ordenado ascendente por ``event_date``. Filtra ``deleted_at IS NULL``.
        Si el competidor no tiene resultados, devuelve DataFrame vacío con
        las columnas presentes.
    """
    results = await _load_results(db)
    events = await _load_events(db)
    categories = await _load_categories(db)

    columns = [
        "valida_num",
        "event_date",
        "category_code",
        "position",
        "race_time_ms",
        "points_awarded",
        "gap_to_winner_ms",
        "gap_to_winner_pct",
    ]

    if not results:
        return pd.DataFrame(columns=columns)

    df_r = _results_df(results)
    df_e = _events_df(events)
    df_c = _categories_df(categories)

    # Calcular tiempo del P1 por (event, category) para gap downstream.
    finished = df_r[df_r["status"] == ResultStatus.FINISHED.value].copy()
    if not finished.empty:
        winners = (
            finished[finished["position"] == 1]
            .groupby(["event_id", "category_id"], as_index=False)["race_time_ms"]
            .min()  # defensivo: si hubiera dos P1 (no debería), tomamos el menor
            .rename(columns={"race_time_ms": "winner_time_ms"})
        )
    else:
        winners = pd.DataFrame(
            columns=["event_id", "category_id", "winner_time_ms"]
        )

    # Filtrar al competidor consultado.
    df_mine = df_r[df_r["competitor_id"] == competitor_id].copy()
    if df_mine.empty:
        return pd.DataFrame(columns=columns)

    # Join: results + events + categories + winners.
    df = df_mine.merge(df_e, on="event_id", how="left")
    df = df.merge(df_c, on="category_id", how="left")
    df = df.merge(winners, on=["event_id", "category_id"], how="left")

    # Calcular gap al ganador.
    # gap_ms = race_time_ms - winner_time_ms (0 si es P1; NaN si DNF/DSQ).
    df["gap_to_winner_ms"] = df["race_time_ms"] - df["winner_time_ms"]
    df["gap_to_winner_pct"] = np.where(
        df["winner_time_ms"].notna() & (df["winner_time_ms"] > 0) & df["gap_to_winner_ms"].notna(),
        (df["gap_to_winner_ms"] / df["winner_time_ms"]) * 100.0,
        np.nan,
    )

    # Orden cronológico (event_date asc). NaT/None van al final por defecto.
    df = df.sort_values(by=["event_date", "valida_num"], na_position="last")

    # Convertir gap_to_winner_ms a Int64 nullable (acepta NaN).
    df["gap_to_winner_ms"] = df["gap_to_winner_ms"].astype("Int64")
    # gap_to_winner_pct se queda como float (nan-safe).
    # Position y race_time_ms también pueden ser NaN (DNF/DSQ).
    df["position"] = df["position"].astype("Int64")
    df["race_time_ms"] = df["race_time_ms"].astype("Int64")
    df["points_awarded"] = df["points_awarded"].fillna(0).astype("Int64")
    df["valida_num"] = df["valida_num"].astype("Int64")

    out = df[columns].reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# 2. podium_gap
# ---------------------------------------------------------------------------


async def podium_gap(
    db: AsyncSession, category_id: int, season: int
) -> pd.DataFrame:
    """Gap al P1 y al P3 por válida para corredores TyR de una categoría.

    Solo considera competitors con ``athlete_id IS NOT NULL`` (matches
    confirmados por el coach).

    Args:
        db: Sesión async.
        category_id: PK de ``RaceCategory``.
        season: año de temporada (filtro vía ``RaceEvent``/``RaceSeries``).

    Returns:
        DataFrame con una fila por (competitor TyR, válida) de la temporada.
        Columnas:

        - ``competitor_id``    (int)
        - ``valida_num``       (int)
        - ``event_date``       (ISO date string)
        - ``position``         (Int64 nullable; None si DNF/DSQ o no participó)
        - ``gap_to_p1_ms``     (Int64 nullable; 0 si P1)
        - ``gap_to_p3_ms``     (Int64 nullable; <0 si P1/P2, 0 si P3, >0 si P4+)
        - ``gap_pct``          (float nullable; gap_to_p1_ms / p1_time * 100)

        Una fila ``NULL`` (position/gap_to_p1_ms/gap_to_p3_ms/gap_pct todos
        nulos) por cada (competitor TyR, válida) donde el corredor no
        participó o aparece DNF/DSQ.

        Requiere ``RaceSeries`` con ``season_year=season``. Si no hay eventos
        en la temporada o no hay TyR en la categoría, devuelve DataFrame vacío.
    """
    results = await _load_results(db)
    events = await _load_events(db)

    columns = [
        "competitor_id",
        "valida_num",
        "event_date",
        "position",
        "gap_to_p1_ms",
        "gap_to_p3_ms",
        "gap_pct",
    ]

    if not events:
        return pd.DataFrame(columns=columns)

    # Filtrar eventos por season vía RaceSeries → series_year.
    # Para no asumir join SQL, cruzamos in-memory: cargamos series.
    from app.services.race.queries import load_series

    series_list = await load_series(db)
    series_ids_in_season = {s.id for s in series_list if s.season_year == season}
    events_in_season = [e for e in events if e.series_id in series_ids_in_season]
    if not events_in_season:
        return pd.DataFrame(columns=columns)

    df_e = _events_df(events_in_season)
    df_r = _results_df(results)

    # Resultados de la categoría dentro de la temporada
    df_cat = df_r[
        (df_r["category_id"] == category_id)
        & (df_r["event_id"].isin(df_e["event_id"]))
    ].copy()
    if df_cat.empty:
        return pd.DataFrame(columns=columns)

    # Identificar competitors TyR (athlete_id NOT NULL) que aparecen en
    # cualquier válida de la categoría/temporada.
    tyr_competitor_ids = sorted(
        {
            int(cid)
            for cid in df_cat.loc[df_cat["athlete_id"].notna(), "competitor_id"].unique()
        }
    )
    if not tyr_competitor_ids:
        return pd.DataFrame(columns=columns)

    # Calcular tiempo del P1 y P3 por evento (solo FINISHED entran al podio).
    finished = df_cat[df_cat["status"] == ResultStatus.FINISHED.value].copy()
    podium_times = (
        finished[finished["position"].isin([1, 3])]
        .pivot_table(
            index="event_id",
            columns="position",
            values="race_time_ms",
            aggfunc="min",
        )
        .reset_index()
    )
    # Garantizar columnas 1 y 3 aunque no haya P3 en alguna válida.
    if 1 not in podium_times.columns:
        podium_times[1] = np.nan
    if 3 not in podium_times.columns:
        podium_times[3] = np.nan
    podium_times = podium_times.rename(columns={1: "p1_time_ms", 3: "p3_time_ms"})

    # Producto cartesiano (competitor TyR × event) y luego left-join con
    # los resultados reales: filas sin match quedarán "no participó".
    grid_rows = []
    for cid in tyr_competitor_ids:
        for _, e in df_e.iterrows():
            grid_rows.append(
                {
                    "competitor_id": cid,
                    "event_id": int(e["event_id"]),
                    "valida_num": int(e["valida_num"]) if pd.notna(e["valida_num"]) else None,
                    "event_date": e["event_date"],
                }
            )
    grid = pd.DataFrame(grid_rows)

    # Join con resultados reales del competitor + evento (mismo category_id).
    own = df_cat[df_cat["competitor_id"].isin(tyr_competitor_ids)][
        ["competitor_id", "event_id", "position", "race_time_ms", "status"]
    ].copy()
    merged = grid.merge(own, on=["competitor_id", "event_id"], how="left")

    # Join con tiempos de podio del evento.
    merged = merged.merge(podium_times, on="event_id", how="left")

    # Reglas de gap:
    # - Si status != FINISHED o race_time_ms es NaN o no participó →
    #   position/gap_to_p1_ms/gap_to_p3_ms/gap_pct = NaN.
    is_finished = merged["status"] == ResultStatus.FINISHED.value
    has_time = merged["race_time_ms"].notna()
    valid = is_finished & has_time

    merged["gap_to_p1_ms"] = np.where(
        valid & merged["p1_time_ms"].notna(),
        merged["race_time_ms"] - merged["p1_time_ms"],
        np.nan,
    )
    merged["gap_to_p3_ms"] = np.where(
        valid & merged["p3_time_ms"].notna(),
        merged["race_time_ms"] - merged["p3_time_ms"],
        np.nan,
    )
    merged["gap_pct"] = np.where(
        valid & merged["p1_time_ms"].notna() & (merged["p1_time_ms"] > 0),
        (merged["race_time_ms"] - merged["p1_time_ms"]) / merged["p1_time_ms"] * 100.0,
        np.nan,
    )
    # position en filas de "no participó" debe ser NaN explícito.
    merged.loc[~valid, "position"] = np.nan

    # Nullable Int64 para enteros con NaN.
    merged["position"] = merged["position"].astype("Int64")
    merged["gap_to_p1_ms"] = merged["gap_to_p1_ms"].astype("Int64")
    merged["gap_to_p3_ms"] = merged["gap_to_p3_ms"].astype("Int64")
    merged["valida_num"] = merged["valida_num"].astype("Int64")

    merged = merged.sort_values(
        by=["competitor_id", "event_date", "valida_num"], na_position="last"
    )

    return merged[columns].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. club_ranking
# ---------------------------------------------------------------------------


async def club_ranking(db: AsyncSession, season: int) -> dict[str, Any]:
    """Agregados del club TyR por temporada (categoría/tier).

    Sólo cuenta resultados de competitors con ``athlete_id IS NOT NULL``
    (matches confirmados → corredores que el coach validó como TyR).

    Args:
        db: Sesión async.
        season: año de temporada (filtra vía ``RaceSeries.season_year``).

    Returns:
        ``dict`` con la siguiente estructura (JSON-serializable):

        ```
        {
          'by_category': [
            {
              'category_code': str,
              'total_points': int,
              'podiums': int,        # P1..P3
              'wins': int,           # P1
              'active_riders': int,  # competitors únicos con ≥1 resultado en la cat
            },
            ...
          ],
          'total_points': int,             # sum de by_category.total_points
          'total_podiums': int,            # sum de by_category.podiums
          'total_wins': int,               # sum de by_category.wins
          'active_riders': int,            # competitors únicos en TODA la temporada
          'distribution_by_tier': {
            'menores': int, 'juvenil': int, 'adulto': int, 'master': int
          }
        }
        ```

        Si no hay datos en la temporada, devuelve totales en 0 y listas vacías.
        El agregado NO incluye identificadores individuales (privacidad).
    """
    results = await _load_results(db)
    events = await _load_events(db)
    categories = await _load_categories(db)

    from app.services.race.queries import load_series

    series_list = await load_series(db)
    series_ids_in_season = {s.id for s in series_list if s.season_year == season}
    events_in_season = [e for e in events if e.series_id in series_ids_in_season]

    empty_tier_distribution = {t.value: 0 for t in CategoryTier}

    if not events_in_season:
        return {
            "by_category": [],
            "total_points": 0,
            "total_podiums": 0,
            "total_wins": 0,
            "active_riders": 0,
            "distribution_by_tier": empty_tier_distribution,
        }

    df_e = _events_df(events_in_season)
    df_c = _categories_df(categories)
    df_r = _results_df(results)

    # Filtrar: solo TyR (athlete_id NOT NULL) y solo eventos de la temporada.
    df_tyr = df_r[
        df_r["athlete_id"].notna()
        & df_r["event_id"].isin(df_e["event_id"])
    ].copy()

    if df_tyr.empty:
        return {
            "by_category": [],
            "total_points": 0,
            "total_podiums": 0,
            "total_wins": 0,
            "active_riders": 0,
            "distribution_by_tier": empty_tier_distribution,
        }

    # Join con categorías para code y tier.
    df_tyr = df_tyr.merge(df_c, on="category_id", how="left")

    # Agregados por categoría.
    df_tyr["is_podium"] = df_tyr["position"].isin([1, 2, 3]).astype(int)
    df_tyr["is_win"] = (df_tyr["position"] == 1).astype(int)

    by_cat = (
        df_tyr.groupby("category_code", dropna=False)
        .agg(
            total_points=("points_awarded", "sum"),
            podiums=("is_podium", "sum"),
            wins=("is_win", "sum"),
            active_riders=("competitor_id", "nunique"),
        )
        .reset_index()
        .sort_values(by="category_code")
    )

    by_category = [
        {
            "category_code": row["category_code"],
            "total_points": int(row["total_points"]),
            "podiums": int(row["podiums"]),
            "wins": int(row["wins"]),
            "active_riders": int(row["active_riders"]),
        }
        for _, row in by_cat.iterrows()
    ]

    total_points = int(df_tyr["points_awarded"].sum())
    total_podiums = int(df_tyr["is_podium"].sum())
    total_wins = int(df_tyr["is_win"].sum())
    active_riders = int(df_tyr["competitor_id"].nunique())

    # Distribución por tier: competitors únicos por tier (no fila-counts).
    tier_distribution = {t.value: 0 for t in CategoryTier}
    if "tier" in df_tyr.columns:
        # Para cada tier, cuántos competitors únicos.
        for tier_val, group in df_tyr.groupby("tier", dropna=True):
            if tier_val in tier_distribution:
                tier_distribution[tier_val] = int(group["competitor_id"].nunique())

    return {
        "by_category": by_category,
        "total_points": total_points,
        "total_podiums": total_podiums,
        "total_wins": total_wins,
        "active_riders": active_riders,
        "distribution_by_tier": tier_distribution,
    }


# ---------------------------------------------------------------------------
# 4. projection
# ---------------------------------------------------------------------------


def _confidence_from_n(n: int) -> str:
    if n < _CONFIDENCE_LOW_MAX_N + 1:  # n<5
        return "low"
    if n <= _CONFIDENCE_MED_MAX_N:  # 5..8
        return "medium"
    return "high"


async def projection(
    db: AsyncSession, competitor_id: int, next_event_id: int
) -> dict[str, Any]:
    """Proyección lineal para próxima válida basada en histórico del competidor.

    Args:
        db: Sesión async.
        competitor_id: PK del ``RaceCompetitor``.
        next_event_id: PK del ``RaceEvent`` para el que queremos proyectar.
            Se usa para inferir el ``valida_num`` objetivo (eje X de la
            regresión).

    Returns:
        ``dict`` con:

        - ``competitor_id``                (int)
        - ``next_event_id``                (int)
        - ``next_valida_num``              (int o None — si el evento no existe)
        - ``expected_position``            (float o None — None si no hay datos)
        - ``expected_position_range``      ([low, high] floats, o None)
        - ``expected_race_time_ms``        (float o None — None si DNF en histórico)
        - ``n_samples``                    (int)
        - ``confidence``                   (``'low'`` n<5 / ``'medium'`` 5-8 / ``'high'`` >8)

        Si ``n_samples == 0``, todos los campos derivados son ``None`` y
        ``confidence='low'``. ``np.polyfit`` se usa con ``deg=1`` sobre
        ``(valida_num → position)`` y ``(valida_num → race_time_ms)``.
        El rango es ``[expected ± std(residuos)]``, clipado a ≥1 para
        ``position``.
    """
    results = await _load_results(db)
    events = await _load_events(db)

    df_e = _events_df(events)
    df_r = _results_df(results)

    next_valida_num: Optional[int] = None
    next_event_row = df_e[df_e["event_id"] == next_event_id]
    if not next_event_row.empty:
        v = next_event_row.iloc[0]["valida_num"]
        next_valida_num = int(v) if pd.notna(v) else None

    df_mine = df_r[df_r["competitor_id"] == competitor_id].copy()
    df_mine = df_mine.merge(df_e[["event_id", "valida_num"]], on="event_id", how="left")

    # Defaults para "no hay datos".
    base: dict[str, Any] = {
        "competitor_id": competitor_id,
        "next_event_id": next_event_id,
        "next_valida_num": next_valida_num,
        "expected_position": None,
        "expected_position_range": None,
        "expected_race_time_ms": None,
        "n_samples": 0,
        "confidence": "low",
    }
    if df_mine.empty:
        return base

    # Solo registros con valida_num conocido + position válida (no DNF/DSQ).
    df_pos = df_mine[
        df_mine["valida_num"].notna()
        & df_mine["position"].notna()
        & (df_mine["status"] == ResultStatus.FINISHED.value)
    ].copy()

    n_samples = int(len(df_pos))
    if n_samples == 0:
        return base

    base["n_samples"] = n_samples
    base["confidence"] = _confidence_from_n(n_samples)

    # Si no tenemos el valida_num del próximo evento, no podemos proyectar.
    if next_valida_num is None:
        return base

    x = df_pos["valida_num"].to_numpy(dtype=float)
    y_pos = df_pos["position"].to_numpy(dtype=float)

    # Edge case n=1: polyfit deg=1 con un solo punto degenera. Usamos el
    # propio valor como predicción "constante" y std=0.
    if n_samples == 1:
        expected_pos = float(y_pos[0])
        std_pos = 0.0
    else:
        slope, intercept = np.polyfit(x, y_pos, deg=1)
        expected_pos = float(slope * next_valida_num + intercept)
        residuals = y_pos - (slope * x + intercept)
        std_pos = float(np.std(residuals, ddof=0))

    # Clip position a >=1 (no existe puesto 0 o negativo).
    expected_pos_clipped = max(expected_pos, 1.0)
    low = max(expected_pos_clipped - std_pos, 1.0)
    high = expected_pos_clipped + std_pos
    base["expected_position"] = round(expected_pos_clipped, 2)
    base["expected_position_range"] = [round(low, 2), round(high, 2)]

    # race_time_ms proyectado (solo si hay tiempos finitos).
    df_time = df_pos[df_pos["race_time_ms"].notna()].copy()
    if not df_time.empty:
        x_t = df_time["valida_num"].to_numpy(dtype=float)
        y_t = df_time["race_time_ms"].to_numpy(dtype=float)
        if len(x_t) == 1:
            expected_time = float(y_t[0])
        else:
            slope_t, intercept_t = np.polyfit(x_t, y_t, deg=1)
            expected_time = float(slope_t * next_valida_num + intercept_t)
        # Tiempo no puede ser negativo.
        expected_time = max(expected_time, 0.0)
        base["expected_race_time_ms"] = round(expected_time, 2)

    return base
