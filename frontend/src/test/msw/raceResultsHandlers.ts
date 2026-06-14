/**
 * MSW handlers para los endpoints de resultados y standings (Wave A).
 *
 * Cubre:
 *   - GET /api/race-analysis/race-events/:id/results
 *   - GET /api/race-analysis/race-events/:id/standings
 *
 * Uso en tests:
 * ```ts
 * import {
 *   raceResultsHandlers,
 *   makeRaceEventResultsResponse,
 *   makeRaceEventStandingsResponse,
 *   raceResultsEmptyHandler,
 *   raceResultsErrorHandler,
 *   standingsEmptyHandler,
 *   standingsErrorHandler,
 * } from "@/test/msw/raceResultsHandlers";
 *
 * mswServer.use(...raceResultsHandlers);
 * // Sobreescribir puntualmente:
 * mswServer.use(raceResultsEmptyHandler);
 * ```
 *
 * Privacidad: los nombres en los fixtures son ficticios/anónimos.
 * No se usan nombres reales de atletas menores (Ley 1581).
 */
import { http, HttpResponse } from "msw";

import type {
  RaceEventResultsResponse,
  RaceEventStandingsResponse,
  RaceResultRow,
  StandingRow,
} from "@/types/raceResults.types";

const BASE = "*/api/race-analysis/race-events";

// ---------------------------------------------------------------------------
// Factory helpers — RaceResultRow
// ---------------------------------------------------------------------------

export function makeRaceResultRow(
  overrides?: Partial<RaceResultRow>,
): RaceResultRow {
  return {
    result_id: 1001,
    coach_note: null,
    coach_note_updated_at: null,
    position: 1,
    competitor_id: 101,
    display_name: "Corredor A",
    club_text: "Club Trocha y Ruta",
    athlete_id: 55,
    is_our_club: true,
    status: "finished",
    race_time_ms: 3_540_000, // 59:00.000
    laps_behind: null,
    points_awarded: 25,
    bib_number: 7,
    ...overrides,
  };
}

export function makeRaceResultRowRival(
  overrides?: Partial<RaceResultRow>,
): RaceResultRow {
  return {
    result_id: 1002,
    coach_note: null,
    coach_note_updated_at: null,
    position: 2,
    competitor_id: 202,
    display_name: "Corredor B",
    club_text: "Club Rival XCO",
    athlete_id: null,
    is_our_club: false,
    status: "finished",
    race_time_ms: 3_600_000, // 60:00.000
    laps_behind: null,
    points_awarded: 20,
    bib_number: 12,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Factory helpers — StandingRow
// ---------------------------------------------------------------------------

export function makeStandingRow(
  overrides?: Partial<StandingRow>,
): StandingRow {
  return {
    rank: 1,
    competitor_id: 101,
    display_name: "Corredor A",
    club_text: "Club Trocha y Ruta",
    athlete_id: 55,
    is_our_club: true,
    total_points: 75,
    races_run: 3,
    podiums: 2,
    best_position: 1,
    ...overrides,
  };
}

export function makeStandingRowRival(
  overrides?: Partial<StandingRow>,
): StandingRow {
  return {
    rank: 2,
    competitor_id: 202,
    display_name: "Corredor B",
    club_text: "Club Rival XCO",
    athlete_id: null,
    is_our_club: false,
    total_points: 60,
    races_run: 3,
    podiums: 1,
    best_position: 2,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Factory helpers — respuestas completas
// ---------------------------------------------------------------------------

/**
 * Crea una respuesta de resultados para padre (solo 1 fila — el hijo propio).
 * Incluye los campos opcionales de cabecera (event_name, event_date, location).
 */
export function makeParentRaceEventResultsResponse(
  overrides?: Partial<RaceEventResultsResponse>,
): RaceEventResultsResponse {
  return {
    race_event_id: 1,
    event_name: "Copa Valle IV — Cali",
    event_date: "2026-05-17",
    location: "Cali",
    status: "completed",
    categories: [
      {
        category_id: 1,
        code: "INF_M",
        label: "Infantil Masculino",
        rows: [
          makeRaceResultRow({
            competitor_id: 101,
            display_name: "Mi Hijo",
            athlete_id: 55,
            is_our_club: true,
            position: 3,
            race_time_ms: 3_720_000,
          }),
        ],
      },
    ],
    ...overrides,
  };
}

/**
 * Crea una respuesta de standings para padre (solo 1 fila — el hijo propio).
 * Incluye los campos opcionales de cabecera.
 */
export function makeParentRaceEventStandingsResponse(
  overrides?: Partial<RaceEventStandingsResponse>,
): RaceEventStandingsResponse {
  return {
    race_event_id: 1,
    event_name: "Copa Valle IV — Cali",
    event_date: "2026-05-17",
    location: "Cali",
    status: "completed",
    categories: [
      {
        category_id: 1,
        code: "INF_M",
        label: "Infantil Masculino",
        rows: [
          makeStandingRow({
            competitor_id: 101,
            display_name: "Mi Hijo",
            athlete_id: 55,
            is_our_club: true,
            rank: 5,
            total_points: 48,
          }),
        ],
      },
    ],
    ...overrides,
  };
}

/**
 * MSW handler: GET /results → respuesta de padre (1 fila propia, con header).
 */
export const parentResultsHandler = http.get(
  `${BASE}/:id/results`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(
      makeParentRaceEventResultsResponse({ race_event_id: id }),
    );
  },
);

/**
 * MSW handler: GET /standings → respuesta de padre (1 fila propia, con header).
 */
export const parentStandingsHandler = http.get(
  `${BASE}/:id/standings`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(
      makeParentRaceEventStandingsResponse({ race_event_id: id }),
    );
  },
);

/** Handlers felices para el escenario de padre. */
export const parentRaceResultsHandlers = [
  parentResultsHandler,
  parentStandingsHandler,
];

/**
 * Crea una respuesta de resultados con 2 categorías y 3 corredores.
 */
export function makeRaceEventResultsResponse(
  overrides?: Partial<RaceEventResultsResponse>,
): RaceEventResultsResponse {
  return {
    race_event_id: 1,
    categories: [
      {
        category_id: 1,
        code: "INF_M",
        label: "Infantil Masculino",
        rows: [
          makeRaceResultRow(),
          makeRaceResultRowRival(),
          makeRaceResultRow({
            position: 3,
            competitor_id: 303,
            display_name: "Corredor C",
            club_text: "Club Otro",
            athlete_id: null,
            is_our_club: false,
            race_time_ms: 3_660_000,
            points_awarded: 16,
            bib_number: 23,
          }),
        ],
      },
      {
        category_id: 2,
        code: "INF_F",
        label: "Infantil Femenino",
        rows: [
          makeRaceResultRow({
            competitor_id: 401,
            display_name: "Corredor D",
            club_text: "Club Trocha y Ruta",
            athlete_id: 60,
            is_our_club: true,
            race_time_ms: 4_020_000,
            bib_number: 1,
          }),
          makeRaceResultRowRival({
            position: 2,
            competitor_id: 502,
            display_name: "Corredor E",
            club_text: "Club Rival XCO",
            race_time_ms: 4_080_000,
            bib_number: 8,
          }),
        ],
      },
    ],
    ...overrides,
  };
}

/**
 * Crea una respuesta de standings con 2 categorías.
 */
export function makeRaceEventStandingsResponse(
  overrides?: Partial<RaceEventStandingsResponse>,
): RaceEventStandingsResponse {
  return {
    race_event_id: 1,
    categories: [
      {
        category_id: 1,
        code: "INF_M",
        label: "Infantil Masculino",
        rows: [
          makeStandingRow(),
          makeStandingRowRival(),
          makeStandingRow({
            rank: 3,
            competitor_id: 303,
            display_name: "Corredor C",
            club_text: "Club Otro",
            athlete_id: null,
            is_our_club: false,
            total_points: 48,
            races_run: 3,
            podiums: 0,
            best_position: 3,
          }),
        ],
      },
      {
        category_id: 2,
        code: "INF_F",
        label: "Infantil Femenino",
        rows: [
          makeStandingRow({
            competitor_id: 401,
            display_name: "Corredor D",
            club_text: "Club Trocha y Ruta",
            athlete_id: 60,
            is_our_club: true,
            total_points: 50,
            best_position: 1,
          }),
          makeStandingRowRival({
            rank: 2,
            competitor_id: 502,
            display_name: "Corredor E",
            total_points: 40,
            best_position: 2,
          }),
        ],
      },
    ],
    ...overrides,
  };
}

/**
 * Crea un fixture con las 26 categorías de la Copa Valle para probar
 * rendimiento con el dataset completo.
 *
 * Cada categoría tiene 10 corredores (mix de nuestro club y rivales).
 * Total: 260 filas — simula un evento completo.
 */
export function makeFullFieldResultsResponse(
  raceEventId = 1,
): RaceEventResultsResponse {
  const CATEGORY_CODES = [
    ["PRE_M", "Pre-Infantil Masculino"],
    ["PRE_F", "Pre-Infantil Femenino"],
    ["INF_M", "Infantil Masculino"],
    ["INF_F", "Infantil Femenino"],
    ["ALV_M", "Álvaro Masculino"],
    ["ALV_F", "Álvaro Femenino"],
    ["JUV_M", "Juvenil Masculino"],
    ["JUV_F", "Juvenil Femenino"],
    ["SU23_M", "Sub-23 Masculino"],
    ["SU23_F", "Sub-23 Femenino"],
    ["ELI_M", "Élite Masculino"],
    ["ELI_F", "Élite Femenino"],
    ["MAS_A_M", "Master A Masculino"],
    ["MAS_A_F", "Master A Femenino"],
    ["MAS_B_M", "Master B Masculino"],
    ["MAS_B_F", "Master B Femenino"],
    ["MAS_C_M", "Master C Masculino"],
    ["MAS_C_F", "Master C Femenino"],
    ["MAS_D_M", "Master D Masculino"],
    ["MAS_D_F", "Master D Femenino"],
    ["MAS_E_M", "Master E Masculino"],
    ["MAS_E_F", "Master E Femenino"],
    ["MAS_F_M", "Master F Masculino"],
    ["MAS_F_F", "Master F Femenino"],
    ["MAS_G_M", "Master G Masculino"],
    ["MAS_G_F", "Master G Femenino"],
  ] as const;

  return {
    race_event_id: raceEventId,
    categories: CATEGORY_CODES.map(([code, label], catIdx) => ({
      category_id: catIdx + 1,
      code,
      label,
      rows: Array.from({ length: 10 }, (_, rowIdx) => {
        const isOurClub = rowIdx === 0; // Solo el primero es de nuestro club
        const competitorId = catIdx * 100 + rowIdx + 1;
        return makeRaceResultRow({
          position: rowIdx + 1,
          competitor_id: competitorId,
          display_name: `Corredor ${competitorId}`,
          club_text: isOurClub ? "Club Trocha y Ruta" : `Club Rival ${rowIdx}`,
          athlete_id: isOurClub ? competitorId + 1000 : null,
          is_our_club: isOurClub,
          race_time_ms: 3_600_000 + rowIdx * 30_000,
          points_awarded: 25 - rowIdx * 2,
          bib_number: competitorId,
          laps_behind: rowIdx >= 5 ? rowIdx - 4 : null,
        });
      }),
    })),
  };
}

/**
 * Fixture de standings con las 26 categorías.
 */
export function makeFullFieldStandingsResponse(
  raceEventId = 1,
): RaceEventStandingsResponse {
  const CATEGORY_CODES = [
    ["PRE_M", "Pre-Infantil Masculino"],
    ["PRE_F", "Pre-Infantil Femenino"],
    ["INF_M", "Infantil Masculino"],
    ["INF_F", "Infantil Femenino"],
    ["ALV_M", "Álvaro Masculino"],
    ["ALV_F", "Álvaro Femenino"],
    ["JUV_M", "Juvenil Masculino"],
    ["JUV_F", "Juvenil Femenino"],
    ["SU23_M", "Sub-23 Masculino"],
    ["SU23_F", "Sub-23 Femenino"],
    ["ELI_M", "Élite Masculino"],
    ["ELI_F", "Élite Femenino"],
    ["MAS_A_M", "Master A Masculino"],
    ["MAS_A_F", "Master A Femenino"],
    ["MAS_B_M", "Master B Masculino"],
    ["MAS_B_F", "Master B Femenino"],
    ["MAS_C_M", "Master C Masculino"],
    ["MAS_C_F", "Master C Femenino"],
    ["MAS_D_M", "Master D Masculino"],
    ["MAS_D_F", "Master D Femenino"],
    ["MAS_E_M", "Master E Masculino"],
    ["MAS_E_F", "Master E Femenino"],
    ["MAS_F_M", "Master F Masculino"],
    ["MAS_F_F", "Master F Femenino"],
    ["MAS_G_M", "Master G Masculino"],
    ["MAS_G_F", "Master G Femenino"],
  ] as const;

  return {
    race_event_id: raceEventId,
    categories: CATEGORY_CODES.map(([code, label], catIdx) => ({
      category_id: catIdx + 1,
      code,
      label,
      rows: Array.from({ length: 10 }, (_, rowIdx) => {
        const isOurClub = rowIdx === 0;
        const competitorId = catIdx * 100 + rowIdx + 1;
        return makeStandingRow({
          rank: rowIdx + 1,
          competitor_id: competitorId,
          display_name: `Corredor ${competitorId}`,
          club_text: isOurClub ? "Club Trocha y Ruta" : `Club Rival ${rowIdx}`,
          athlete_id: isOurClub ? competitorId + 1000 : null,
          is_our_club: isOurClub,
          total_points: 75 - rowIdx * 8,
          races_run: 3,
          podiums: rowIdx === 0 ? 2 : 0,
          best_position: rowIdx + 1,
        });
      }),
    })),
  };
}

// ---------------------------------------------------------------------------
// Handlers por defecto
// ---------------------------------------------------------------------------

/** GET /race-events/:id/results → respuesta completa (2 categorías). */
const resultsHandler = http.get(`${BASE}/:id/results`, ({ params }) => {
  const id = Number(params.id);
  return HttpResponse.json(
    makeRaceEventResultsResponse({ race_event_id: id }),
  );
});

/** GET /race-events/:id/standings → respuesta completa (2 categorías). */
const standingsHandler = http.get(`${BASE}/:id/standings`, ({ params }) => {
  const id = Number(params.id);
  return HttpResponse.json(
    makeRaceEventStandingsResponse({ race_event_id: id }),
  );
});

/** Conjunto de handlers del escenario feliz. */
export const raceResultsHandlers = [resultsHandler, standingsHandler];

// ---------------------------------------------------------------------------
// Handlers de error / casos especiales
// ---------------------------------------------------------------------------

/** GET /results → respuesta vacía (sin categorías). */
export const raceResultsEmptyHandler = http.get(
  `${BASE}/:id/results`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json({
      race_event_id: id,
      categories: [],
    });
  },
);

/** GET /standings → respuesta vacía. */
export const standingsEmptyHandler = http.get(
  `${BASE}/:id/standings`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json({
      race_event_id: id,
      categories: [],
    });
  },
);

/** GET /results → error 500 (cold-start simulado). */
export const raceResultsErrorHandler = http.get(`${BASE}/:id/results`, () => {
  return HttpResponse.json(
    { detail: "Error interno del servidor." },
    { status: 500 },
  );
});

/** GET /standings → error 503 (cold-start simulado). */
export const standingsErrorHandler = http.get(`${BASE}/:id/standings`, () => {
  return HttpResponse.json(
    { detail: "Servicio temporalmente no disponible." },
    { status: 503 },
  );
});

/** GET /results con las 26 categorías — fixture de campo completo. */
export const raceResultsFullFieldHandler = http.get(
  `${BASE}/:id/results`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeFullFieldResultsResponse(id));
  },
);

/** GET /standings con las 26 categorías. */
export const standingsFullFieldHandler = http.get(
  `${BASE}/:id/standings`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeFullFieldStandingsResponse(id));
  },
);
