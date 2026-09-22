/**
 * Tipos del módulo de progresión histórica entre temporadas (feature 044,
 * US6/US7).
 *
 * Mirror de `AthleteRaceHistoryRead` — contrato completo en
 * `specs/044-race-history-backfill/contracts/history-progression-api.md`.
 * Endpoint: `GET /api/athletes/{athlete_id}/race-analysis/history`.
 *
 * Privacidad: la respuesta nunca incluye `competitor_id` de terceros ni de
 * el propio atleta — solo los campos agregados/derivados de esta sección.
 * Cuando el llamante es un padre, el backend ya filtra los puntos previos
 * a la vinculación del atleta (ver el contrato, "Parent filter") — el
 * frontend no vuelve a filtrar nada, solo renderiza lo que llega.
 */

/** Estado del corredor al cierre de la válida — mirror de `ResultStatus`
 * (`backend/app/models/race_result.py`). */
export type RaceHistoryResultStatus =
  | "finished"
  | "minus_laps"
  | "dnf"
  | "dns"
  | "dsq";

/** Estados que cuentan como "no llegó a la meta" — se dibujan como marcador
 * hueco en la gráfica, nunca conectados por la línea de tendencia. */
export const NON_FINISHER_STATUSES: ReadonlySet<RaceHistoryResultStatus> =
  new Set(["dnf", "dns", "dsq"]);

/** Etiquetas en español para el estado — usadas en tabla y tooltip. */
export const RACE_HISTORY_STATUS_LABELS: Record<
  RaceHistoryResultStatus,
  string
> = {
  finished: "Terminó",
  minus_laps: "Terminó (-vueltas)",
  dnf: "No terminó",
  dns: "No salió",
  dsq: "Descalificado",
};

/** `series_kind` del filtro de consulta — `all` mezcla copa y campeonato;
 * `cup` es el valor por defecto del contrato. */
export type RaceHistorySeriesKind = "cup" | "championship" | "all";

/** Código cerrado de advertencia (`caveats`) — catálogo fijo del contrato,
 * siempre presente en la respuesta (nunca vacío en la práctica). */
export type RaceHistoryCaveatCode =
  | "different_courses"
  | "weather_surface"
  | "small_fields"
  | "non_finishers_excluded"
  | "three_rider_categories";

/** Una oración por código — catálogo cerrado, `CaveatsNote` no inventa
 * texto para un código que no reconozca (lo omite en vez de romper). */
export const RACE_HISTORY_CAVEAT_LABELS: Record<
  RaceHistoryCaveatCode,
  string
> = {
  different_courses:
    "Cada válida se corre en un circuito distinto — el tiempo no es directamente comparable entre válidas.",
  weather_surface:
    "El clima y el estado del terreno cambian de una válida a otra y afectan el tiempo.",
  small_fields:
    "Algunas categorías tienen muy pocos corredores — el percentil y la brecha a la mediana pueden no ser representativos.",
  non_finishers_excluded:
    "Quien no terminó una válida no entra en el cálculo de percentil ni de brecha a la mediana de esa válida.",
  three_rider_categories:
    "Con tres corredores o menos en la categoría, la posición dice poco sobre el nivel real.",
};

/** Un punto de la serie histórica — una fila de `race_results` con su
 * contexto de válida/serie/categoría ya resuelto por el backend. */
export interface RaceHistoryPoint {
  event_id: number;
  event_date: string;
  season: number;
  label: string;
  series_id: number;
  series_name: string;
  series_kind: "cup" | "championship";
  category_code: string;
  category_label: string;
  /** `true` si la categoría cambió respecto al punto anterior en orden de
   * fecha del mismo atleta; el primer punto de la serie siempre es `false`. */
  category_changed: boolean;
  previous_category_label: string | null;
  status: RaceHistoryResultStatus;
  position: number | null;
  /** Finishers incluyendo quien perdió vueltas (`minus_laps`). */
  field_size: number | null;
  /** `FINISHED` estricto con tiempo — subconjunto de `field_size`. */
  timed_finishers: number | null;
  /** `null` cuando `field_size < 5`. */
  percentile: number | null;
  /** `null` cuando `timed_finishers < 5`, o el atleta no terminó, o no
   * tiene tiempo. Negativo = más rápido que la mediana. */
  gap_to_median_pct: number | null;
  /** Misma regla de estado que `gap_to_median_pct`, sin umbral de tamaño. */
  gap_to_winner_pct: number | null;
  /** `null` sin circuito configurado para esa válida — nunca estimado. */
  avg_speed_kmh: number | null;
  points_awarded: number;
}

/** Resumen de asistencia por temporada. */
export interface RaceHistorySeasonCompletion {
  season: number;
  /** Excluye DNS. */
  started: number;
  /** Cuenta `finished` y `minus_laps`. */
  finished: number;
}

export interface AthleteRaceHistoryRead {
  points: RaceHistoryPoint[];
  seasons: RaceHistorySeasonCompletion[];
  caveats: RaceHistoryCaveatCode[];
}

export interface RaceHistoryQueryParams {
  series_kind?: RaceHistorySeriesKind;
}
