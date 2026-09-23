/**
 * MSW handlers para la progresión histórica entre temporadas (feature 044,
 * US6/US7).
 *
 * Cubre GET /api/athletes/:athleteId/race-analysis/history.
 *
 * Uso en tests:
 * ```ts
 * import { raceHistoryHandlers, makeAthleteRaceHistoryRead } from "@/test/msw/raceHistoryHandlers";
 *
 * mswServer.use(...raceHistoryHandlers); // por defecto, un fixture con datos
 * mswServer.use(raceHistoryEmptyHandler); // sobreescribe con estado vacío
 * ```
 */
import { http, HttpResponse } from "msw";

import type {
  AthleteRaceHistoryRead,
  CoachRaceHistoryPoint,
  FamilyRaceHistoryPoint,
} from "@/types/raceHistory.types";
import { LEADER_GAP_METRIC_KEYS } from "@/types/raceResults.types";

import { omitKeys } from "./omitKeys";

const URL_PATTERN = "*/api/athletes/:athleteId/race-analysis/history";

/** Punto de coach/admin (con brechas contra 1.ª posición y podio). */
export function makeRaceHistoryPoint(
  overrides?: Partial<CoachRaceHistoryPoint>,
): CoachRaceHistoryPoint {
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

/** Punto de familia: el backend omite `gap_to_winner_pct` y
 * `gap_to_podium_pct` (las claves no existen, no son `null`). */
export function makeFamilyRaceHistoryPoint(
  overrides?: Partial<FamilyRaceHistoryPoint>,
): FamilyRaceHistoryPoint {
  return omitKeys(makeRaceHistoryPoint(overrides), LEADER_GAP_METRIC_KEYS);
}

/** Serie de coach con dos temporadas y un cambio de categoría entre ellas —
 * cubre el caso "de manual" que motiva la tarjeta (SC-008). */
function makeCoachHistoryPoints(): CoachRaceHistoryPoint[] {
  return [
    makeRaceHistoryPoint({
      event_id: 30,
      event_date: "2024-03-10",
      season: 2024,
      label: "Válida 1 — Palmira",
      category_code: "INF_B",
      category_label: "INFANTIL B",
      category_changed: false,
      previous_category_label: null,
      position: 5,
      field_size: 18,
      timed_finishers: 16,
      percentile: 77.8,
      gap_to_median_pct: -8.1,
      gap_to_winner_pct: 6.4,
      gap_to_podium_pct: 2.9,
    }),
    makeRaceHistoryPoint({
      event_id: 31,
      event_date: "2024-04-14",
      season: 2024,
      label: "Válida 2 — Ginebra",
      category_code: "INF_B",
      category_label: "INFANTIL B",
      category_changed: false,
      previous_category_label: null,
      position: 4,
      field_size: 19,
      timed_finishers: 17,
      percentile: 83.3,
      gap_to_median_pct: -6.5,
      gap_to_winner_pct: 5.1,
      gap_to_podium_pct: 1.6,
    }),
    makeRaceHistoryPoint({
      event_id: 41,
      event_date: "2025-02-09",
      season: 2025,
      label: "Válida 1 — Ginebra",
      category_code: "PJUV_A",
      category_label: "PREJUVENIL A",
      category_changed: true,
      previous_category_label: "INFANTIL B",
      // "other": este fixture reproduce una reestructuración del catálogo
      // entre temporadas, no un ascenso real — mantiene la copia familiar
      // neutral en los tests que ya la pinan (T077/T082).
      category_change_kind: "other",
      position: 9,
      field_size: 23,
      timed_finishers: 21,
      percentile: 63.6,
      gap_to_median_pct: -4.2,
      gap_to_winner_pct: 11.8,
      gap_to_podium_pct: 6.9,
    }),
    makeRaceHistoryPoint({
      event_id: 43,
      event_date: "2025-06-08",
      season: 2025,
      label: "Válida 3 — Buga",
      category_code: "PJUV_A",
      category_label: "PREJUVENIL A",
      category_changed: false,
      previous_category_label: null,
      status: "dnf",
      position: null,
      field_size: 20,
      timed_finishers: 18,
      percentile: null,
      gap_to_median_pct: null,
      gap_to_winner_pct: null,
      gap_to_podium_pct: null,
      points_awarded: 0,
    }),
  ];
}

/** Respuesta para coach/admin. */
export function makeAthleteRaceHistoryRead(
  overrides?: Partial<AthleteRaceHistoryRead>,
): AthleteRaceHistoryRead {
  return {
    points: makeCoachHistoryPoints(),
    seasons: [
      { season: 2024, started: 2, finished: 2 },
      { season: 2025, started: 2, finished: 1 },
    ],
    caveats: [
      "different_courses",
      "weather_surface",
      "small_fields",
      "non_finishers_excluded",
      "three_rider_categories",
    ],
    ...overrides,
  };
}

/** Misma serie que `makeAthleteRaceHistoryRead`, tal como la recibe un
 * padre: sin brechas contra 1.ª posición ni podio en ningún punto. */
export function makeFamilyAthleteRaceHistoryRead(
  overrides?: Partial<AthleteRaceHistoryRead>,
): AthleteRaceHistoryRead {
  return {
    ...makeAthleteRaceHistoryRead(),
    points: makeCoachHistoryPoints().map((point) =>
      omitKeys(point, LEADER_GAP_METRIC_KEYS),
    ),
    ...overrides,
  };
}

export const raceHistoryHandlers = [
  http.get(URL_PATTERN, () =>
    HttpResponse.json(makeAthleteRaceHistoryRead()),
  ),
];

/** Sobreescribe con la respuesta que recibe un padre (sin brechas de líder/podio). */
export const raceHistoryFamilyHandler = http.get(URL_PATTERN, () =>
  HttpResponse.json(makeFamilyAthleteRaceHistoryRead()),
);

export const raceHistoryEmptyHandler = http.get(URL_PATTERN, () =>
  HttpResponse.json(
    makeAthleteRaceHistoryRead({ points: [], seasons: [], caveats: [] }),
  ),
);

export const raceHistoryErrorHandler = http.get(URL_PATTERN, () =>
  HttpResponse.json({ detail: "Internal Server Error" }, { status: 500 }),
);
