/**
 * MSW handlers para el módulo race roster (convocatoria).
 *
 * Cubre:
 *   - GET    /api/race-analysis/race-events/:id/roster
 *   - POST   /api/race-analysis/race-events/:id/roster
 *   - PATCH  /api/race-analysis/race-events/:id/roster/:entryId
 *   - DELETE /api/race-analysis/race-events/:id/roster/:entryId
 *
 * Uso en tests:
 * ```ts
 * import {
 *   raceRosterHandlers,
 *   makeRaceRosterResponse,
 *   makeRosterEntry,
 *   raceRosterEmptyHandler,
 *   raceRosterErrorHandler,
 *   raceRosterDuplicateHandler,
 * } from "@/test/msw/raceRosterHandlers";
 *
 * mswServer.use(...raceRosterHandlers);
 * ```
 *
 * Privacidad: nombres en fixtures son ficticios/anónimos (Ley 1581).
 */
import { http, HttpResponse } from "msw";

import type {
  RaceRosterResponse,
  RosterEntry,
  RosterReconciliation,
} from "@/types/raceRoster.types";

const BASE = "*/api/race-analysis/race-events";

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function makeRosterEntry(
  overrides?: Partial<RosterEntry>,
): RosterEntry {
  return {
    id: 1,
    athlete_id: 10,
    athlete_name: "Atleta Uno",
    status: "called_up",
    note: null,
    ...overrides,
  };
}

export function makeRosterReconciliation(
  overrides?: Partial<RosterReconciliation>,
): RosterReconciliation {
  return {
    called_up_no_result: [],
    result_not_called_up: [],
    ...overrides,
  };
}

export function makeRaceRosterResponse(
  overrides?: Partial<RaceRosterResponse>,
): RaceRosterResponse {
  return {
    race_event_id: 1,
    entries: [
      makeRosterEntry({ id: 1, athlete_id: 10, athlete_name: "Atleta Uno", status: "called_up" }),
      makeRosterEntry({ id: 2, athlete_id: 20, athlete_name: "Atleta Dos", status: "confirmed" }),
      makeRosterEntry({ id: 3, athlete_id: 30, athlete_name: "Atleta Tres", status: "withdrawn" }),
    ],
    reconciliation: makeRosterReconciliation(),
    ...overrides,
  };
}

/** Fixture con discrepancias de reconciliación. */
export function makeRaceRosterWithDiscrepancies(
  raceEventId = 1,
): RaceRosterResponse {
  return {
    race_event_id: raceEventId,
    entries: [
      makeRosterEntry({ id: 1, athlete_id: 10, athlete_name: "Atleta Uno", status: "called_up" }),
    ],
    reconciliation: {
      // Atleta 10 convocado pero sin resultado en la importación
      called_up_no_result: [10],
      // Atleta 99 aparece en resultados pero no fue convocado
      result_not_called_up: [99],
    },
  };
}

/** Fixture con roster vacío. */
export function makeRaceRosterEmpty(raceEventId = 1): RaceRosterResponse {
  return {
    race_event_id: raceEventId,
    entries: [],
    reconciliation: makeRosterReconciliation(),
  };
}

// ---------------------------------------------------------------------------
// Handlers por defecto (escenario feliz)
// ---------------------------------------------------------------------------

/** GET /race-events/:id/roster → roster con 3 entradas. */
const getRosterHandler = http.get(`${BASE}/:id/roster`, ({ params }) => {
  const id = Number(params.id);
  return HttpResponse.json(makeRaceRosterResponse({ race_event_id: id }));
});

/** POST /race-events/:id/roster → nueva entrada con id=99. */
const createRosterEntryHandler = http.post(
  `${BASE}/:id/roster`,
  async ({ request }) => {
    const body = await request.json() as { athlete_id?: number };
    return HttpResponse.json(
      makeRosterEntry({
        id: 99,
        athlete_id: body?.athlete_id ?? 40,
        athlete_name: "Atleta Nuevo",
        status: "called_up",
      }),
      { status: 201 },
    );
  },
);

/** PATCH /race-events/:id/roster/:entryId → entrada actualizada. */
const updateRosterEntryHandler = http.patch(
  `${BASE}/:id/roster/:entryId`,
  async ({ params, request }) => {
    const entryId = Number(params.entryId);
    const body = await request.json() as Partial<RosterEntry>;
    return HttpResponse.json(
      makeRosterEntry({ id: entryId, ...body }),
    );
  },
);

/** DELETE /race-events/:id/roster/:entryId → 204 sin body. */
const deleteRosterEntryHandler = http.delete(
  `${BASE}/:id/roster/:entryId`,
  () => {
    return new HttpResponse(null, { status: 204 });
  },
);

/** Conjunto de handlers del escenario feliz. */
export const raceRosterHandlers = [
  getRosterHandler,
  createRosterEntryHandler,
  updateRosterEntryHandler,
  deleteRosterEntryHandler,
];

// ---------------------------------------------------------------------------
// Handlers de escenarios de error
// ---------------------------------------------------------------------------

/** GET → roster vacío (sin entradas). */
export const raceRosterEmptyHandler = http.get(
  `${BASE}/:id/roster`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeRaceRosterEmpty(id));
  },
);

/** GET → error 500 (cold-start simulado). */
export const raceRosterErrorHandler = http.get(`${BASE}/:id/roster`, () => {
  return HttpResponse.json(
    { detail: "Error interno del servidor." },
    { status: 500 },
  );
});

/** POST 409 → atleta ya en el roster. */
export const raceRosterDuplicateHandler = http.post(
  `${BASE}/:id/roster`,
  () => {
    return HttpResponse.json(
      { detail: "Este atleta ya está en la convocatoria de esta válida." },
      { status: 409 },
    );
  },
);

/** POST 422 → atleta no pertenece al club. */
export const raceRosterNotClubAthleteHandler = http.post(
  `${BASE}/:id/roster`,
  () => {
    return HttpResponse.json(
      { detail: "El atleta no pertenece al club." },
      { status: 422 },
    );
  },
);

/** GET → roster con discrepancias de reconciliación. */
export const raceRosterWithDiscrepanciesHandler = http.get(
  `${BASE}/:id/roster`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeRaceRosterWithDiscrepancies(id));
  },
);

/** Roster reducido para el padre: solo su propio hijo. */
export function makeRaceRosterParentView(
  myAthleteId: number,
  myAthleteName: string,
): RaceRosterResponse {
  return {
    race_event_id: 1,
    entries: [
      makeRosterEntry({
        id: 1,
        athlete_id: myAthleteId,
        athlete_name: myAthleteName,
        status: "confirmed",
      }),
    ],
    reconciliation: makeRosterReconciliation(),
  };
}
