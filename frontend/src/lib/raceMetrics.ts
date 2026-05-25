/**
 * Helpers puros (sin estado, sin React) usados por el Comparador v2 del
 * análisis IA por atleta.
 *
 * Convenciones:
 *   - "Delta" se interpreta como ``despues - antes``. Si la métrica es
 *     "menor es mejor" (tiempo, gap al podio, ranking), un delta negativo
 *     ⇒ MEJORA.
 *   - Tiempos absolutos van en milisegundos (snapshot V1 del backend).
 *   - El carácter usado para los negativos es ``−`` (U+2212), no ``-``,
 *     por consistencia tipográfica y accesibilidad (los lectores de
 *     pantalla lo leen como "menos").
 */

/**
 * Formatea un tiempo absoluto en milisegundos.
 *
 *   - 2_538_400 ms → ``"42:18.4"``    (42 minutos, 18.4 segundos)
 *   - 3_600_000 ms → ``"1:00:00.0"`` (1 hora exacta)
 *   - 45_200 ms   → ``"0:45.2"``      (menos de un minuto)
 *   - null/undef  → ``"—"``
 */
export function formatRaceTime(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  const totalMs = Math.max(0, Math.round(ms));
  const hours = Math.floor(totalMs / 3_600_000);
  const minutes = Math.floor((totalMs % 3_600_000) / 60_000);
  const seconds = (totalMs % 60_000) / 1000;
  const secStr = seconds.toFixed(1).padStart(4, "0"); // "08.3" / "18.4"
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${secStr}`;
  }
  return `${minutes}:${secStr}`;
}

/**
 * Formatea un delta de tiempo (B − A) con signo explícito.
 *
 *   - -85_700 ms → ``"−1:25.7"``  (mejora superior a 1 min)
 *   - -45_200 ms → ``"−45.2s"``   (mejora bajo el minuto)
 *   - +12_000 ms → ``"+12.0s"``   (regresión)
 *   - 0 ms       → ``"0.0s"``     (sin cambio)
 *   - null       → ``"—"``
 */
export function formatDeltaTime(deltaMs: number | null | undefined): string {
  if (deltaMs === null || deltaMs === undefined || !Number.isFinite(deltaMs)) {
    return "—";
  }
  if (deltaMs === 0) return "0.0s";
  const abs = Math.abs(deltaMs);
  const sign = deltaMs > 0 ? "+" : "−";
  if (abs < 60_000) {
    return `${sign}${(abs / 1000).toFixed(1)}s`;
  }
  const minutes = Math.floor(abs / 60_000);
  const seconds = (abs % 60_000) / 1000;
  const secStr = seconds.toFixed(1).padStart(4, "0");
  return `${sign}${minutes}:${secStr}`;
}

/**
 * Formatea un delta de ranking en categoría (B − A).
 *
 * Recordar: ranking menor = mejor. ``-3`` significa "subió 3 puestos".
 *
 *   -3 → ``"−3 puestos"``
 *   -1 → ``"−1 puesto"``
 *    0 → ``"Mantuvo"``
 *   +2 → ``"+2 puestos"``
 *   +1 → ``"+1 puesto"``
 */
export function formatDeltaRank(
  deltaRank: number | null | undefined,
): string {
  if (deltaRank === null || deltaRank === undefined || !Number.isFinite(deltaRank)) {
    return "—";
  }
  if (deltaRank === 0) return "Mantuvo";
  const abs = Math.abs(deltaRank);
  const noun = abs === 1 ? "puesto" : "puestos";
  const sign = deltaRank > 0 ? "+" : "−";
  return `${sign}${abs} ${noun}`;
}

/**
 * Estructura real del ``metrics_snapshot`` persistido por ``persist_insight.py``.
 * No es ``MetricsSnapshotV1`` plano — es un superset agregado con la
 * progresión completa del competidor y el contexto del podio.
 *
 * Solo extraemos los campos que el Comparador v2 necesita; el resto se
 * preserva pero no se tipa.
 */
export interface LegacyProgressionRow {
  valida_num?: number | null;
  event_date?: string | null;
  category_code?: string | null;
  position?: number | null;
  race_time_ms?: number | null;
  gap_to_winner_ms?: number | null;
  gap_to_winner_pct?: number | null;
}

export interface LegacyPodiumGapRow {
  valida_num?: number | null;
  position?: number | null;
  gap_to_p1_ms?: number | null;
  gap_to_p3_ms?: number | null;
}

export interface ExtractedMetrics {
  race_time_ms: number | null;
  ranking_in_category: number | null;
  podium_gap_ms: number | null;
  /** Total corredores FINISHED en la categoría del atleta esa válida. */
  category_size: number | null;
  /** Tiempo del más rápido FINISHED (= P1) de la categoría. */
  category_time_min_ms: number | null;
  /** Tiempo del más lento FINISHED (= último) de la categoría. */
  category_time_max_ms: number | null;
}

/**
 * Umbral mínimo de corredores para mostrar percentil.
 * Bajo eso el dato es ruido estadístico (rango muy chico).
 */
export const PERCENTILE_MIN_FIELD_SIZE = 5;

/**
 * Calcula percentil por TIEMPO dentro de la categoría.
 *
 * Override coach real (2026-05-25): el club acepta usar P1/Pn como
 * referencias del campo presente, pese al veto inicial por edad
 * biológica. El coach interpreta la métrica con ese contexto.
 *
 * Fórmula: ``100 × (1 − (t − t_min) / (t_max − t_min))``
 *
 *   - t == t_min → 100 (es el P1)
 *   - t == t_max → 0 (es el último)
 *   - t_min == t_max → 100 (todos empataron — degenerado)
 *
 * Devuelve ``null`` si faltan datos o el campo es muy chico (n < 5).
 */
export function computePercentile(
  raceTimeMs: number | null | undefined,
  timeMinMs: number | null | undefined,
  timeMaxMs: number | null | undefined,
  size: number | null | undefined,
): number | null {
  if (
    raceTimeMs === null ||
    raceTimeMs === undefined ||
    timeMinMs === null ||
    timeMinMs === undefined ||
    timeMaxMs === null ||
    timeMaxMs === undefined ||
    size === null ||
    size === undefined ||
    !Number.isFinite(raceTimeMs) ||
    !Number.isFinite(timeMinMs) ||
    !Number.isFinite(timeMaxMs) ||
    !Number.isFinite(size)
  ) {
    return null;
  }
  if (size < PERCENTILE_MIN_FIELD_SIZE) return null;
  if (raceTimeMs < timeMinMs || raceTimeMs > timeMaxMs) return null;
  if (timeMaxMs === timeMinMs) return 100;
  const pct = 100 * (1 - (raceTimeMs - timeMinMs) / (timeMaxMs - timeMinMs));
  return Math.round(pct);
}

/**
 * Extrae métricas de una válida específica desde el snapshot persistido.
 *
 * El snapshot tiene la forma ``{ progression: [...], podium_gap: [...] }``
 * con la progresión COMPLETA del competidor a lo largo de la temporada.
 * Buscamos las filas correspondientes a ``validaNum`` para reconstruir
 * los datos puntuales de esa válida.
 *
 * Devuelve ``null`` si el snapshot no tiene la forma esperada o si la
 * válida no aparece en la progresión.
 */
export function extractMetricsForValida(
  snapshot: unknown,
  validaNum: number,
): ExtractedMetrics | null {
  if (!snapshot || typeof snapshot !== "object") return null;
  const snap = snapshot as Record<string, unknown>;
  const progression = Array.isArray(snap.progression)
    ? (snap.progression as LegacyProgressionRow[])
    : null;
  const podiumGap = Array.isArray(snap.podium_gap)
    ? (snap.podium_gap as LegacyPodiumGapRow[])
    : null;
  if (!progression) return null;

  const progRow = progression.find((r) => r?.valida_num === validaNum);
  if (!progRow) return null;

  const podRow = podiumGap?.find((r) => r?.valida_num === validaNum);

  const numeric = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? v : null;

  // `category_stats` se popula en persist_insight.py (BE-fix 2026-05-25).
  // Snapshots pre-fix tienen `{}` o el campo ausente → todo queda null.
  let categorySize: number | null = null;
  let categoryTimeMinMs: number | null = null;
  let categoryTimeMaxMs: number | null = null;
  if (snap.category_stats && typeof snap.category_stats === "object") {
    const stats = (snap.category_stats as Record<string, unknown>)[
      String(validaNum)
    ];
    if (stats && typeof stats === "object") {
      const s = stats as Record<string, unknown>;
      categorySize = numeric(s.size);
      categoryTimeMinMs = numeric(s.time_min_ms);
      categoryTimeMaxMs = numeric(s.time_max_ms);
    }
  }

  return {
    race_time_ms: numeric(progRow.race_time_ms),
    ranking_in_category: numeric(progRow.position),
    podium_gap_ms: numeric(podRow?.gap_to_p3_ms ?? null),
    category_size: categorySize,
    category_time_min_ms: categoryTimeMinMs,
    category_time_max_ms: categoryTimeMaxMs,
  };
}

/**
 * Snapshot mínimo que necesitamos del insight para calcular la mejor
 * marca de la temporada. Acepta tanto V1 plano como legacy con progression.
 */
export interface MinimalSnapshot {
  metrics_snapshot?: unknown;
}

/**
 * Devuelve el ``race_time_ms`` más bajo de la temporada.
 *
 * Estrategia:
 *   1. Si algún snapshot es V1 plano con ``race_time_ms``, lo usa.
 *   2. Si el snapshot tiene ``progression[]`` (formato real persistido),
 *      itera todas las filas y toma el mínimo ``race_time_ms`` de filas
 *      con ``position`` no-null (excluye DNF/DSQ).
 */
export function computeBestTimeForSeason(
  insights: ReadonlyArray<MinimalSnapshot>,
): number | null {
  let best: number | null = null;
  const consider = (t: unknown) => {
    if (typeof t !== "number" || !Number.isFinite(t)) return;
    if (best === null || t < best) best = t;
  };
  for (const insight of insights) {
    const snap = insight.metrics_snapshot;
    if (!snap || typeof snap !== "object") continue;
    const s = snap as Record<string, unknown>;
    if (s.schema_version === 1) {
      consider(s.race_time_ms);
      continue;
    }
    const progression = Array.isArray(s.progression)
      ? (s.progression as LegacyProgressionRow[])
      : null;
    if (!progression) continue;
    for (const row of progression) {
      if (typeof row?.position === "number") consider(row.race_time_ms);
    }
  }
  return best;
}

/**
 * Cuenta cuántas métricas mejoraron.
 *
 *   - ``rank``, ``gap``: menor es mejor → delta negativo = mejora.
 *   - ``percentile``: mayor es mejor → delta positivo = mejora.
 *
 * ``total`` es el conteo de métricas con valor numérico no-null.
 */
export interface ImprovementInput {
  rank: number | null | undefined;
  gap: number | null | undefined;
  percentile?: number | null | undefined;
}

export interface ImprovementSummary {
  improved: number;
  total: number;
}

export function evaluateImprovementCount(
  deltas: ImprovementInput,
): ImprovementSummary {
  let improved = 0;
  let total = 0;
  const consider = (
    value: number | null | undefined,
    higherIsBetter = false,
  ) => {
    if (value === null || value === undefined || !Number.isFinite(value)) return;
    total += 1;
    if (higherIsBetter ? value > 0 : value < 0) improved += 1;
  };
  consider(deltas.rank);
  consider(deltas.gap);
  consider(deltas.percentile, true);
  return { improved, total };
}

/**
 * Versión cualitativa del delta de ranking para vista padre — sin números
 * cuando el cambio es 0 ("Mantuvo posición") y plural correcto.
 */
export function formatQualitativeRank(
  deltaRank: number | null | undefined,
): string {
  if (deltaRank === null || deltaRank === undefined || !Number.isFinite(deltaRank)) {
    return "Sin datos para comparar";
  }
  if (deltaRank === 0) return "Mantuvo posición";
  const abs = Math.abs(deltaRank);
  const noun = abs === 1 ? "puesto" : "puestos";
  if (deltaRank < 0) return `Mejoró ${abs} ${noun}`;
  return `Bajó ${abs} ${noun}`;
}

/**
 * Banda cualitativa de proximidad al podio para vista padre.
 *   ≤30s  → "Muy cerca del podio"
 *   ≤90s  → "Cerca del podio"
 *   ≤180s → "En desarrollo"
 *   >180s → "Construyendo base"
 */
export function formatQualitativePodiumProximity(
  gapMs: number | null | undefined,
): string {
  if (gapMs === null || gapMs === undefined || !Number.isFinite(gapMs)) {
    return "Sin datos";
  }
  const g = Math.max(0, gapMs);
  if (g <= 30_000) return "Muy cerca del podio";
  if (g <= 90_000) return "Cerca del podio";
  if (g <= 180_000) return "En desarrollo";
  return "Construyendo base";
}
