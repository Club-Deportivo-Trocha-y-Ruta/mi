/**
 * MSW handlers para el módulo race-series (spec 014 — Cup vs Championship).
 *
 * Cubre los endpoints:
 *   - GET  /api/race-analysis/race-series   → listRaceSeries
 *   - POST /api/race-analysis/race-series   → createRaceSeries
 *
 * Uso en tests:
 * ```ts
 * import { raceSeriesHandlers, makeRaceSeriesRead } from "@/test/msw/raceSeriesHandlers";
 * mswServer.use(...raceSeriesHandlers);
 * ```
 */
import { http, HttpResponse } from "msw";
import type {
  RaceSeriesListResponse,
  RaceSeriesRead,
} from "@/types/raceSeries.types";

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function makeRaceSeriesRead(
  overrides?: Partial<RaceSeriesRead>,
): RaceSeriesRead {
  return {
    id: 2,
    name: "Copa Valle de Ciclomontañismo",
    season_year: 2026,
    organizer: "Liga Vallecaucana de Ciclismo",
    kind: "cup",
    level: "departmental",
    event_count: 3,
    ...overrides,
  };
}

export function makeChampionshipSeriesRead(
  overrides?: Partial<RaceSeriesRead>,
): RaceSeriesRead {
  return {
    id: 9,
    name: "Campeonato Departamental 2026",
    season_year: 2026,
    organizer: "Liga Vallecaucana de Ciclismo",
    kind: "championship",
    level: "departmental",
    event_count: 1,
    ...overrides,
  };
}

export function makeRaceSeriesListResponse(
  overrides?: Partial<RaceSeriesListResponse>,
): RaceSeriesListResponse {
  return {
    items: [
      makeRaceSeriesRead(),
      makeChampionshipSeriesRead(),
    ],
    total: 2,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Handlers — escenario feliz
// ---------------------------------------------------------------------------

const BASE = "*/api/race-analysis/race-series";

/** GET /race-series → lista con copa + campeonato. */
const listHandler = http.get(`${BASE}`, ({ request }) => {
  const url = new URL(request.url);
  const kind = url.searchParams.get("kind");

  if (kind === "cup") {
    return HttpResponse.json({
      items: [makeRaceSeriesRead()],
      total: 1,
    } satisfies RaceSeriesListResponse);
  }

  if (kind === "championship") {
    return HttpResponse.json({
      items: [makeChampionshipSeriesRead()],
      total: 1,
    } satisfies RaceSeriesListResponse);
  }

  return HttpResponse.json(makeRaceSeriesListResponse());
});

/** POST /race-series → serie creada (201). */
const createHandler = http.post(`${BASE}`, async ({ request }) => {
  const body = await request.json() as Partial<RaceSeriesRead>;
  return HttpResponse.json(
    makeRaceSeriesRead({
      id: 99,
      name: body?.name ?? "Nueva serie",
      kind: body?.kind ?? "cup",
      organizer: body?.organizer ?? null,
      event_count: 0,
    }),
    { status: 201 },
  );
});

export const raceSeriesHandlers = [listHandler, createHandler];

// ---------------------------------------------------------------------------
// Handlers de error — importar por suite
// ---------------------------------------------------------------------------

/** POST 409 — ya existe una serie con (name, season_year). */
export const raceSeriesCreateConflictHandler = http.post(`${BASE}`, () =>
  HttpResponse.json(
    { detail: "Ya existe una serie con ese nombre para la temporada." },
    { status: 409 },
  ),
);

/** GET → lista vacía (sin series para el tipo pedido). */
export const raceSeriesEmptyHandler = http.get(`${BASE}`, () =>
  HttpResponse.json({ items: [], total: 0 } satisfies RaceSeriesListResponse),
);

/** GET → solo series tipo copa. */
export const raceSeriesCupOnlyHandler = http.get(`${BASE}`, () =>
  HttpResponse.json({
    items: [makeRaceSeriesRead()],
    total: 1,
  } satisfies RaceSeriesListResponse),
);

/** GET → solo series tipo campeonato. */
export const raceSeriesChampionshipOnlyHandler = http.get(`${BASE}`, () =>
  HttpResponse.json({
    items: [makeChampionshipSeriesRead()],
    total: 1,
  } satisfies RaceSeriesListResponse),
);

/** GET 500 → error de servidor. */
export const raceSeriesErrorHandler = http.get(`${BASE}`, () =>
  HttpResponse.json(
    { detail: "Error interno." },
    { status: 500 },
  ),
);
