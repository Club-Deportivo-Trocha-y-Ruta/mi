/**
 * Mock de `GET /api/athletes/:id/race-analysis/history` (feature 044/045) para
 * los specs que abren la pestaña única «Carreras» del atleta.
 *
 * Por qué existe: desde la feature 045 la vista por defecto de «Carreras» es
 * «Progresión», que pide este endpoint con `series_kind=all` apenas monta. Los
 * specs que solo miran «Análisis IA» o «Comparar» no lo tocan (solo se monta la
 * vista activa), pero los que recorren las tres vistas — o entran por
 * `?tab=races` sin `view` — necesitan una respuesta determinista en vez de
 * pegarle al seed real del stack e2e.
 *
 * Datos 100 % sintéticos (sin nombres ni fechas de nacimiento). La variante
 * `family` OMITE las claves de brecha contra 1.ª posición y podio (no llegan
 * como `null`), igual que el backend (salvaguarda 045, Ley 1581).
 */
import type { Page, Route } from "@playwright/test";

const APP_PORT = process.env.E2E_APP_PORT ?? "5173";

/** Peticiones al backend (el dev server de Vite queda fuera del mock). */
const isBackend = (url: URL) => url.port !== APP_PORT;

export type HistoryAudience = "coach" | "family";

export interface HistoryPointFixture {
  event_id: number;
  event_date: string;
  season: number;
  label: string;
  series_id: number;
  series_name: string;
  series_kind: "cup" | "championship";
  category_code: string;
  category_label: string;
  category_changed: boolean;
  previous_category_label: string | null;
  category_change_kind: "promotion" | "other" | null;
  status: "finished" | "minus_laps" | "dnf" | "dns" | "dsq";
  position: number | null;
  field_size: number;
  timed_finishers: number;
  percentile: number | null;
  gap_to_median_pct: number | null;
  gap_to_winner_pct: number | null;
  gap_to_podium_pct: number | null;
  points_awarded: number;
}

/** Punto de copa terminado, con métricas completas de coach. */
export function makeHistoryPoint(
  overrides: Partial<HistoryPointFixture> = {},
): HistoryPointFixture {
  return {
    event_id: 41,
    event_date: "2025-02-09",
    season: 2025,
    label: "Válida 1 — Ginebra",
    series_id: 7,
    series_name: "Copa Valle de Ciclomontañismo",
    series_kind: "cup",
    category_code: "PJUV_A",
    category_label: "PREJUVENIL A",
    category_changed: false,
    previous_category_label: null,
    category_change_kind: null,
    status: "finished",
    position: 9,
    field_size: 23,
    timed_finishers: 21,
    percentile: 63.6,
    gap_to_median_pct: -4.2,
    gap_to_winner_pct: 11.8,
    gap_to_podium_pct: 6.9,
    points_awarded: 18,
    ...overrides,
  };
}

/** Serie mínima: dos válidas de copa en la misma temporada. */
export function defaultHistoryPoints(): HistoryPointFixture[] {
  return [
    makeHistoryPoint({
      event_id: 41,
      event_date: "2025-02-09",
      label: "Válida 1 — Ginebra",
    }),
    makeHistoryPoint({
      event_id: 43,
      event_date: "2025-06-08",
      label: "Válida 3 — Buga",
      position: 6,
      percentile: 75.0,
      gap_to_median_pct: -7.9,
      gap_to_winner_pct: 8.2,
      gap_to_podium_pct: 3.4,
    }),
  ];
}

/** Quita de un punto las brechas contra el líder y el podio (variante familia). */
function toFamilyPoint(point: HistoryPointFixture): Omit<
  HistoryPointFixture,
  "gap_to_winner_pct" | "gap_to_podium_pct"
> {
  const { gap_to_winner_pct: _w, gap_to_podium_pct: _p, ...rest } = point;
  void _w;
  void _p;
  return rest;
}

export function makeHistoryResponse(
  audience: HistoryAudience,
  points: HistoryPointFixture[] = defaultHistoryPoints(),
) {
  const seasons = [...new Set(points.map((p) => p.season))].sort().map((season) => {
    const inSeason = points.filter((p) => p.season === season);
    return {
      season,
      started: inSeason.filter((p) => p.status !== "dns").length,
      finished: inSeason.filter(
        (p) => p.status === "finished" || p.status === "minus_laps",
      ).length,
    };
  });
  return {
    points: audience === "family" ? points.map(toFamilyPoint) : points,
    seasons,
    caveats: ["different_courses", "weather_surface", "non_finishers_excluded"],
  };
}

export interface MockAthleteRaceHistoryOptions {
  audience: HistoryAudience;
  points?: HistoryPointFixture[];
}

/**
 * Registra el endpoint de historial del atleta. Devuelve un arreglo vivo con
 * los `series_kind` pedidos (`"cup"` cuando no viaja el parámetro) para que un
 * spec pueda afirmar que «Progresión» pide `all`.
 */
export async function mockAthleteRaceHistory(
  page: Page,
  athleteId: number,
  { audience, points }: MockAthleteRaceHistoryOptions,
): Promise<string[]> {
  const requestedKinds: string[] = [];
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${athleteId}/race-analysis/history`,
    (route: Route) => {
      const kind = new URL(route.request().url()).searchParams.get("series_kind");
      requestedKinds.push(kind ?? "cup");
      return route.fulfill({
        status: 200,
        json: makeHistoryResponse(audience, points),
      });
    },
  );
  return requestedKinds;
}
