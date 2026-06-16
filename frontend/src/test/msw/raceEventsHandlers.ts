/**
 * MSW handlers para el módulo race-events CRUD (CF3 + CF5).
 *
 * Cubre los endpoints:
 *   - GET    /api/race-analysis/race-events/     → listRaceEvents
 *   - GET    /api/race-analysis/race-events/:id  → getRaceEvent (CF5)
 *   - POST   /api/race-analysis/race-events/     → createRaceEvent
 *   - PATCH  /api/race-analysis/race-events/:id  → updateRaceEvent
 *   - DELETE /api/race-analysis/race-events/:id  → deleteRaceEvent
 *
 * El handler de PATCH /:id/conditions ya tiene su propio test suite y
 * no se duplica aquí.
 *
 * Uso en tests:
 * ```ts
 * import { raceEventsHandlers, makeRaceEventListItem } from "@/test/msw/raceEventsHandlers";
 *
 * // Registrar en setup global o por suite:
 * mswServer.use(...raceEventsHandlers);
 *
 * // Sobreescribir escenario puntual:
 * mswServer.use(raceEventsDeleteConflictHandler);
 * ```
 */
import { http, HttpResponse } from "msw";

import type {
  CalendarAutoCreateResponse,
  RaceEventListItem,
  RaceEventListResponse,
  RaceEventRead,
} from "@/types/raceEvents.types";

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function makeRaceEventRead(
  overrides?: Partial<RaceEventRead>,
): RaceEventRead {
  return {
    id: 1,
    series_id: 1,
    sequence_number: 1,
    name: "Copa Valle XCO — Válida I",
    event_date: "2026-01-31",
    location: "Sevilla",
    is_championship: false,
    status: "completed",
    climate: "soleado",
    temperature_c: "22.5",
    surface_condition: "seca",
    altitude_msnm: 1620,
    weather_notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-31T18:00:00Z",
    created_by_user_id: 10,
    ...overrides,
  };
}

export function makeRaceEventListItem(
  overrides?: Partial<RaceEventListItem>,
): RaceEventListItem {
  return {
    id: 1,
    series_id: 1,
    sequence_number: 1,
    name: "Copa Valle XCO — Válida I",
    event_date: "2026-01-31",
    location: "Sevilla",
    is_championship: false,
    status: "completed",
    has_results: true,
    has_calendar_event: true,
    conditions_completeness: "complete",
    ...overrides,
  };
}

export function makeRaceEventListResponse(
  overrides?: Partial<RaceEventListResponse>,
): RaceEventListResponse {
  return {
    items: [
      makeRaceEventListItem(),
      makeRaceEventListItem({
        id: 2,
        sequence_number: 2,
        name: "Copa Valle XCO — Válida II",
        event_date: "2026-02-28",
        location: "Ginebra",
        has_results: true,
        has_calendar_event: false,
        conditions_completeness: "partial",
      }),
      makeRaceEventListItem({
        id: 3,
        sequence_number: 3,
        name: "Copa Valle XCO — Válida III",
        event_date: "2026-04-19",
        location: "La Cumbre",
        status: "scheduled",
        has_results: false,
        has_calendar_event: false,
        conditions_completeness: "empty",
      }),
    ],
    total: 3,
    ...overrides,
  };
}

/**
 * Feature 015 — evento campeonato para el prefill de importación.
 *
 * `series_id: 9` se alinea con `makeChampionshipSeriesRead()` de
 * raceSeriesHandlers (id 9, kind championship). `is_championship: true`
 * fuerza que el wizard oculte el "Válida #" (FR-008). Sin PII de menores.
 */
export function makeChampionshipRaceEventRead(
  overrides?: Partial<RaceEventRead>,
): RaceEventRead {
  return makeRaceEventRead({
    id: 15,
    series_id: 9,
    sequence_number: 1,
    is_championship: true,
    name: "Campeonato Departamental XCO — Ginebra",
    event_date: "2026-06-12",
    location: "Ginebra",
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Handlers por defecto (escenario feliz)
// ---------------------------------------------------------------------------

const BASE = "*/api/race-analysis/race-events";

/** GET /race-events/ → lista con 3 válidas de la Copa Valle 2026. */
const listHandler = http.get(`${BASE}/`, () => {
  return HttpResponse.json(makeRaceEventListResponse());
});

/**
 * GET /race-events/:id → evento completo (RaceEventRead) por id.
 * Retorna el evento de la lista de fixtures o un evento genérico con el id solicitado.
 */
const getByIdHandler = http.get(`${BASE}/:id`, ({ params }) => {
  const id = Number(params.id);
  // Mapeamos los ids fijos de los fixtures
  const fixtureMap: Record<number, Partial<ReturnType<typeof makeRaceEventRead>>> = {
    1: { id: 1, sequence_number: 1, name: "Copa Valle XCO — Válida I", location: "Sevilla", status: "completed" },
    2: { id: 2, sequence_number: 2, name: "Copa Valle XCO — Válida II", location: "Ginebra", status: "completed" },
    3: { id: 3, sequence_number: 3, name: "Copa Valle XCO — Válida III", location: "La Cumbre", status: "scheduled", climate: null, temperature_c: null, surface_condition: null, altitude_msnm: null, weather_notes: null },
  };
  const overrides = fixtureMap[id] ?? { id };
  return HttpResponse.json(makeRaceEventRead(overrides));
});

/** POST /race-events/ → evento recién creado con id=99. */
const createHandler = http.post(`${BASE}/`, () => {
  return HttpResponse.json(makeRaceEventRead({ id: 99 }), { status: 201 });
});

/** PATCH /race-events/:id → evento actualizado. */
const updateHandler = http.patch(`${BASE}/:id`, ({ params }) => {
  const id = Number(params.id);
  return HttpResponse.json(makeRaceEventRead({ id }));
});

/** DELETE /race-events/:id → 204 sin body. */
const deleteHandler = http.delete(`${BASE}/:id`, () => {
  return new HttpResponse(null, { status: 204 });
});

/**
 * POST /race-events/:id/calendar-link → 200 con {id, has_calendar_event:true}.
 * Escenario feliz: la válida queda vinculada al calendar_event recibido.
 */
const calendarLinkHandler = http.post(`${BASE}/:id/calendar-link`, ({ params }) => {
  const id = Number(params.id);
  return HttpResponse.json({ id, has_calendar_event: true });
});

/**
 * POST /race-events/:id/calendar-event → 201 CalendarAutoCreateResponse.
 * US1: crea y vincula un CalendarEvent all-day desde los datos de la válida.
 */
const calendarAutoCreateHandler = http.post(
  `${BASE}/:id/calendar-event`,
  ({ params }) => {
    const id = Number(params.id);
    const payload: CalendarAutoCreateResponse = {
      race_event_id: id,
      calendar_event_id: 100 + id,
      has_calendar_event: true,
    };
    return HttpResponse.json(payload, { status: 201 });
  },
);

/** Conjunto de handlers del escenario feliz — registrar en setup global. */
export const raceEventsHandlers = [
  listHandler,
  getByIdHandler,
  createHandler,
  updateHandler,
  deleteHandler,
  calendarLinkHandler,
  calendarAutoCreateHandler,
];

// ---------------------------------------------------------------------------
// Handlers de escenarios de error — importar por suite según necesidad
// ---------------------------------------------------------------------------

/**
 * DELETE 409 Conflict — el evento tiene race_results o calendar_event.
 * Usar cuando el test valida que el componente muestra el mensaje de error.
 */
export const raceEventsDeleteConflictHandler = http.delete(
  `${BASE}/:id`,
  () => {
    return HttpResponse.json(
      {
        detail:
          "El evento tiene resultados importados o está vinculado al calendario. Elimina esas dependencias primero.",
      },
      { status: 409 },
    );
  },
);

/**
 * GET 500 — simula error de servidor (cold start Render expirado).
 * Usar en tests de estado de error de `useRaceEventsList`.
 */
export const raceEventsListErrorHandler = http.get(`${BASE}/`, () => {
  return HttpResponse.json(
    { detail: "Error interno del servidor." },
    { status: 500 },
  );
});

/**
 * GET /:id 404 — evento no encontrado.
 * Usar en tests de CompetitionDetailPage para simular evento eliminado.
 */
export const raceEventNotFoundHandler = http.get(`${BASE}/:id`, () => {
  return HttpResponse.json(
    { detail: "Evento de carrera no encontrado." },
    { status: 404 },
  );
});

/**
 * POST 422 — payload inválido (ej. sequence_number duplicado).
 */
export const raceEventsCreateValidationErrorHandler = http.post(
  `${BASE}/`,
  () => {
    return HttpResponse.json(
      {
        detail: [
          {
            loc: ["body", "sequence_number"],
            msg: "sequence_number ya existe en esta serie.",
            type: "value_error",
          },
        ],
      },
      { status: 422 },
    );
  },
);

/**
 * POST 409 — sequence_number duplicado en la temporada.
 * Se usa para verificar el manejo inline de errores en CompetitionFormPage.
 */
export const raceEventsCreateConflictHandler = http.post(`${BASE}/`, () => {
  return HttpResponse.json(
    {
      detail:
        "Ya existe una válida con sequence_number=3 en la temporada 2026.",
    },
    { status: 409 },
  );
});

/**
 * POST /:id/calendar-link 409 — la válida ya está vinculada a un calendar_event
 * (1:1 estricto). Usar en tests que validan el mensaje de error de conflicto.
 */
export const raceEventsCalendarLinkConflictHandler = http.post(
  `${BASE}/:id/calendar-link`,
  () => {
    return HttpResponse.json(
      {
        detail:
          "La válida ya tiene un calendar_event asociado. Desvincula el actual antes de asociar uno nuevo.",
      },
      { status: 409 },
    );
  },
);

/**
 * POST /:id/calendar-link 404 — el calendar_event_id proporcionado no existe.
 */
export const raceEventsCalendarLinkNotFoundHandler = http.post(
  `${BASE}/:id/calendar-link`,
  () => {
    return HttpResponse.json(
      { detail: "Evento de calendario no encontrado." },
      { status: 404 },
    );
  },
);

/**
 * POST /:id/calendar-event 409 — la válida ya tiene un calendar_event (1:1 estricto).
 * Usar en tests que validan el mensaje de error al intentar crear un duplicado.
 */
export const raceEventsCalendarAutoCreateConflictHandler = http.post(
  `${BASE}/:id/calendar-event`,
  ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(
      {
        detail: `La válida id=${id} ya está vinculada al evento de calendario id=42`,
      },
      { status: 409 },
    );
  },
);

// ---------------------------------------------------------------------------
// Feature 015 — prefill de importación desde competencia
//
// Usar junto con `raceSeriesHandlers` (que aporta la serie copa id 2 y la
// serie campeonato id 9). Solo metadata de competencia — cero PII (FR-013).
//
//   mswServer.use(...raceSeriesHandlers, prefillCupEventHandler);
// ---------------------------------------------------------------------------

/**
 * GET /:id → evento copa con `series_id=2` → resuelve a la serie copa de
 * `makeRaceSeriesRead()` (kind cup). Prefill `ready` con "Válida #" visible.
 */
export const prefillCupEventHandler = http.get(`${BASE}/:id`, ({ params }) =>
  HttpResponse.json(
    makeRaceEventRead({
      id: Number(params.id),
      series_id: 2,
      is_championship: false,
      sequence_number: 4,
      name: "Copa Valle XCO — Válida IV",
      event_date: "2026-05-17",
      location: "Cali",
    }),
  ),
);

/**
 * GET /:id → evento campeonato con `series_id=9` → resuelve a la serie
 * campeonato (kind championship). Prefill `ready` SIN "Válida #" (FR-008).
 */
export const prefillChampionshipEventHandler = http.get(
  `${BASE}/:id`,
  ({ params }) =>
    HttpResponse.json(makeChampionshipRaceEventRead({ id: Number(params.id) })),
);

/**
 * GET /:id → evento con `series_id=999`, que NO existe en la lista de series →
 * el prefill queda `blocked` y ofrece el escape hatch "Editar metadata" (FR-009).
 */
export const prefillUnresolvableSeriesEventHandler = http.get(
  `${BASE}/:id`,
  ({ params }) =>
    HttpResponse.json(
      makeRaceEventRead({ id: Number(params.id), series_id: 999 }),
    ),
);
