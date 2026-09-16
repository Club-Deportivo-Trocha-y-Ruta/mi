/**
 * ElevationProfile — perfil de altimetría de UNA vuelta de circuito
 * (feature 043, US5).
 *
 * `AreaChart` de Recharts (mismo import style que
 * `athletes/ai/EvolutionChart.tsx`), serie única en distancia acumulada
 * (km) × elevación (m), color `var(--color-primary)` — el mismo token
 * neutral de serie única usado en todo el proyecto (`EvolutionChart.tsx`,
 * `CourseMap.tsx`).
 *
 * Decima internamente a lo sumo a 200 muestras para el chart, bucketeando
 * por DISTANCIA acumulada (no por índice del punto — los puntos de un GPX
 * no están espaciados uniformemente en el terreno). min/max del
 * `aria-label` se calculan siempre sobre el set COMPLETO de elevaciones,
 * nunca sobre los datos ya decimados, para no perder un pico/valle real que
 * caiga en un bucket descartado.
 *
 * `elevationGainM` llega ya calculado desde el backend
 * (`VariantRead.elevation_gain_m`) — este componente NUNCA lo recalcula, lo
 * muestra verbatim.
 *
 * No diseña un estado vacío para "sin altimetría": el caller (`CourseSummary`)
 * solo monta este componente cuando `variant.has_elevation === true`.
 */
import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ElevationProfileProps {
  /** `CourseVariant.geometry` verbatim — `[lat, lon, elevación|null]`. */
  geometry: Array<[number, number, number | null]>;
  /** `CourseVariant.elevation_gain_m` — ya calculado en el backend, no se recalcula acá. */
  elevationGainM: number;
}

interface ElevationChartPoint {
  distanceKm: number;
  elevation: number | null;
}

const MAX_SAMPLES = 200;
const EARTH_RADIUS_M = 6371000;

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

/**
 * Distancia entre dos puntos geográficos (fórmula de Haversine), en metros.
 * Único caller hoy es este componente — no se promueve a un util
 * compartido (`src/lib/`) hasta que aparezca un segundo consumidor.
 */
function haversineMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return EARTH_RADIUS_M * c;
}

/** Distancia acumulada (metros) en cada punto de `geometry`, partiendo de 0. */
function computeCumulativeDistancesM(
  geometry: Array<[number, number, number | null]>,
): number[] {
  const cumulative: number[] = [0];
  for (let i = 1; i < geometry.length; i++) {
    const [lat1, lon1] = geometry[i - 1];
    const [lat2, lon2] = geometry[i];
    cumulative.push(cumulative[i - 1] + haversineMeters(lat1, lon1, lat2, lon2));
  }
  return cumulative;
}

/**
 * Decima `geometry` a lo sumo a `MAX_SAMPLES` puntos, bucketeando por
 * distancia acumulada. Bucket count = min(200, N); bucket width =
 * distancia_total / bucket_count; por cada bucket se conserva el ÚLTIMO
 * punto cuya distancia acumulada cae dentro de él — simple, determinístico,
 * y mantiene la serie monótona en distancia.
 */
function decimateByDistance(
  geometry: Array<[number, number, number | null]>,
  cumulativeM: number[],
): ElevationChartPoint[] {
  const n = geometry.length;
  if (n === 0) return [];

  const bucketCount = Math.min(MAX_SAMPLES, n);
  const totalDistanceM = cumulativeM[n - 1];

  if (totalDistanceM <= 0) {
    // Puntos degenerados (misma coordenada repetida, distancia total 0) —
    // no hay nada que bucketear por distancia; se toma 1 de cada N por
    // índice para no exceder MAX_SAMPLES.
    const step = Math.max(1, Math.ceil(n / bucketCount));
    const points: ElevationChartPoint[] = [];
    for (let i = 0; i < n; i += step) {
      points.push({ distanceKm: cumulativeM[i] / 1000, elevation: geometry[i][2] });
    }
    return points;
  }

  const bucketWidth = totalDistanceM / bucketCount;
  const buckets: Array<ElevationChartPoint | undefined> = new Array(bucketCount);

  for (let i = 0; i < n; i++) {
    const d = cumulativeM[i];
    const bucketIndex = Math.min(bucketCount - 1, Math.floor(d / bucketWidth));
    buckets[bucketIndex] = { distanceKm: d / 1000, elevation: geometry[i][2] };
  }

  return buckets.filter((b): b is ElevationChartPoint => b !== undefined);
}

/**
 * min/max SIEMPRE sobre el set COMPLETO de elevaciones (nunca sobre los
 * datos ya decimados que ve el chart) — de lo contrario un pico/valle real
 * podría perderse si cae en un bucket descartado por la decimación.
 * Ignora puntos sin elevación (`null`).
 */
function computeElevationRange(
  geometry: Array<[number, number, number | null]>,
): { min: number; max: number } | null {
  let min = Infinity;
  let max = -Infinity;
  for (const [, , elevation] of geometry) {
    if (elevation === null || Number.isNaN(elevation)) continue;
    if (elevation < min) min = elevation;
    if (elevation > max) max = elevation;
  }
  if (min === Infinity || max === -Infinity) return null;
  return { min, max };
}

export function ElevationProfile({
  geometry,
  elevationGainM,
}: ElevationProfileProps) {
  const chartData = useMemo(() => {
    const cumulativeM = computeCumulativeDistancesM(geometry);
    return decimateByDistance(geometry, cumulativeM);
  }, [geometry]);

  const range = useMemo(() => computeElevationRange(geometry), [geometry]);
  const minLabel = range ? Math.round(range.min) : 0;
  const maxLabel = range ? Math.round(range.max) : 0;

  // Eje ajustado al rango real: desde 0 m, 30 m de desnivel a 1 300 msnm se
  // ven como una línea plana. Margen mínimo de 10 m para rangos muy chicos.
  const yDomain = useMemo<[number, number] | undefined>(() => {
    if (!range) return undefined;
    const pad = Math.max(10, (range.max - range.min) * 0.15);
    return [
      Math.floor((range.min - pad) / 10) * 10,
      Math.ceil((range.max + pad) / 10) * 10,
    ];
  }, [range]);

  return (
    <div
      role="img"
      aria-label={`Perfil de altimetría: de ${minLabel} a ${maxLabel} m, ${elevationGainM} m de desnivel positivo`}
      className="h-40 w-full"
      data-testid="elevation-profile"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
        >
          <CartesianGrid stroke="var(--color-border-gray)" />
          <XAxis
            dataKey="distanceKm"
            type="number"
            tick={{ fontSize: 11, fill: "var(--color-mid-gray)" }}
            tickFormatter={(v: number) => `${v.toFixed(1)} km`}
          />
          <YAxis
            domain={yDomain ?? ["auto", "auto"]}
            allowDecimals={false}
            tick={{ fontSize: 11, fill: "var(--color-mid-gray)" }}
            tickFormatter={(v: number) => `${Math.round(v)} m`}
            width={50}
          />
          <Tooltip
            // Recharts v3.8 tipa `formatter`/`labelFormatter` con genéricos
            // (`ValueType`/`NameType`) que no aceptan estrecharse sin caer en
            // errores irreconciliables (mismo motivo que el comentario de
            // `EvolutionChart.tsx` sobre `TooltipLikeProps`) — se tipan laxo
            // acá en vez de pelear contra los genéricos.
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter={((value: any) => [
              `${Math.round(Number(value ?? 0))} m`,
              "Elevación",
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
            ]) as any}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            labelFormatter={((label: any) =>
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              `${Number(label ?? 0).toFixed(1)} km`) as any}
          />
          <Area
            type="monotone"
            dataKey="elevation"
            stroke="var(--color-primary)"
            fill="var(--color-primary)"
            fillOpacity={0.15}
            strokeWidth={2}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
