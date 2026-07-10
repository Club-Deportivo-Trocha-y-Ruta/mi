/**
 * MSW handlers para el módulo Strava Activity Sync (feature 025, T027).
 *
 * Mock data que respeta los shapes de `@/types/strava.types` (mirror de
 * contracts/api.md §A/§C). Factories para sobreescribir campos puntuales
 * por suite.
 *
 * Estos handlers NO se registran por default en el server global
 * (`src/test/setup.ts`) — cada suite los importa y los empuja con
 * `mswServer.use(...)` para evitar interferir con tests existentes.
 *
 * Privacidad (Ley 1581): los fixtures NUNCA incluyen coordenadas, polyline,
 * mapa ni descripción de ubicación — mismo criterio que el resto del
 * módulo (ver ActivityCard.tsx docstring).
 */
import { http, HttpResponse } from "msw";

import type {
  ActivityListResponse,
  ActivityOut,
  SessionSuggestion,
  SessionSuggestionListResponse,
  StravaConnectionOut,
  StravaConnectResponse,
} from "@/types/strava.types";

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function mockStravaConnection(
  overrides?: Partial<StravaConnectionOut>,
): StravaConnectionOut {
  return {
    status: "active",
    connected_at: "2026-06-01T10:00:00Z",
    disconnected_at: null,
    authorized_by: "María Ficticia Pérez",
    last_sync_at: "2026-07-09T18:30:00Z",
    ...overrides,
  };
}

export function mockActivity(overrides?: Partial<ActivityOut>): ActivityOut {
  return {
    id: 1,
    athlete_id: 42,
    athlete_name: "Sebastián Ficticio García",
    name: "Rodada matutina",
    sport_type: "MountainBikeRide",
    start_date_local: "2026-07-08T06:30:00",
    elapsed_time_s: 5400,
    moving_time_s: 5100,
    distance_m: 32000,
    total_elevation_gain_m: 450,
    average_heartrate: 148,
    max_heartrate: 172,
    is_trainer: false,
    upstream_state: "present",
    summary_complete: true,
    link: null,
    ...overrides,
  };
}

export function mockActivityListResponse(
  overrides?: Partial<ActivityListResponse>,
): ActivityListResponse {
  const items = overrides?.items ?? [
    mockActivity(),
    mockActivity({
      id: 2,
      name: "Salida familiar",
      start_date_local: "2026-07-05T09:00:00",
      elapsed_time_s: 3600,
      distance_m: 15000,
      average_heartrate: 130,
      max_heartrate: 155,
      is_trainer: true,
    }),
  ];
  return {
    total: items.length,
    page: 1,
    page_size: 20,
    ...overrides,
    items,
  };
}

export function mockAuthorizeUrl(athleteId = 42): StravaConnectResponse {
  return {
    authorize_url: `https://www.strava.com/oauth/authorize?client_id=1&redirect_uri=https%3A%2F%2Fmi-2yzi.onrender.com%2Fapi%2Fintegrations%2Fstrava%2Fcallback&response_type=code&approval_prompt=auto&scope=activity%3Aread_all&state=signed-state-${athleteId}`,
  };
}

/**
 * Fixture para GET /api/activities (revisión coach, T031/T034). Dos
 * actividades en fechas distintas — una enlazada, una sin enlazar — para
 * ejercitar el agrupamiento por día y los badges de estado en un solo
 * fixture reutilizable.
 */
export function mockReviewActivityListResponse(
  overrides?: Partial<ActivityListResponse>,
): ActivityListResponse {
  const items = overrides?.items ?? [
    mockActivity({
      id: 1,
      athlete_name: "Sebastián Ficticio García",
      start_date_local: "2026-07-08T06:30:00",
      link: null,
    }),
    mockActivity({
      id: 2,
      athlete_name: "Valentina Ficticia López",
      name: "Rodada con el grupo",
      start_date_local: "2026-07-05T09:00:00",
      elapsed_time_s: 3600,
      distance_m: 15000,
      average_heartrate: 130,
      max_heartrate: 155,
      link: {
        training_session_id: 10,
        session_label: "5 jul · Entrenamiento",
        linked_by: "Entrenador Ficticio",
        linked_at: "2026-07-05T12:00:00Z",
      },
    }),
  ];
  return {
    total: items.length,
    page: 1,
    page_size: 30,
    ...overrides,
    items,
  };
}

export function mockSessionSuggestion(
  overrides?: Partial<SessionSuggestion>,
): SessionSuggestion {
  return {
    training_session_id: 10,
    scheduled_date: "2026-07-08T15:00:00",
    session_kind: "entrenamiento",
    location: "Pista XCO La Cumbre",
    technical_focus: "Frenada controlada",
    same_day: true,
    athlete_in_attendance: true,
    ...overrides,
  };
}

export function mockSessionSuggestionListResponse(
  overrides?: Partial<SessionSuggestionListResponse>,
): SessionSuggestionListResponse {
  const suggestions = overrides?.suggestions ?? [
    mockSessionSuggestion(),
    mockSessionSuggestion({
      training_session_id: 11,
      scheduled_date: "2026-07-09T15:00:00",
      location: "Parque El Ingenio",
      same_day: false,
      athlete_in_attendance: false,
    }),
  ];
  return { ...overrides, suggestions };
}

// ---------------------------------------------------------------------------
// Default handlers
// ---------------------------------------------------------------------------

/**
 * Set base: conexión activa + dos actividades. Cada suite sobreescribe con
 * `mswServer.use(...variantHandler)` para estados none/broken/disconnected.
 */
export const stravaHandlers = [
  http.get("*/api/athletes/:athleteId/strava/connection", () =>
    HttpResponse.json(mockStravaConnection()),
  ),

  http.post("*/api/athletes/:athleteId/strava/connect", ({ params }) =>
    HttpResponse.json(mockAuthorizeUrl(Number(params.athleteId))),
  ),

  http.delete(
    "*/api/athletes/:athleteId/strava/connection",
    () => new HttpResponse(null, { status: 204 }),
  ),

  http.get("*/api/athletes/:athleteId/activities", () =>
    HttpResponse.json(mockActivityListResponse()),
  ),

  http.get("*/api/activities", () =>
    HttpResponse.json(mockReviewActivityListResponse()),
  ),

  http.get("*/api/activities/:id/session-suggestions", () =>
    HttpResponse.json(mockSessionSuggestionListResponse()),
  ),

  http.patch("*/api/activities/:id/link", async ({ request, params }) => {
    const body = (await request.json()) as { training_session_id: number | null };
    return HttpResponse.json(
      mockActivity({
        id: Number(params.id),
        link:
          body.training_session_id != null
            ? {
                training_session_id: body.training_session_id,
                session_label: "8 jul · Entrenamiento",
                linked_by: "Entrenador Ficticio",
                linked_at: "2026-07-10T12:00:00Z",
              }
            : null,
      }),
    );
  }),
];

// ---------------------------------------------------------------------------
// Variant handlers — estados de conexión
// ---------------------------------------------------------------------------

export const noneConnectionHandler = http.get(
  "*/api/athletes/:athleteId/strava/connection",
  () =>
    HttpResponse.json(
      mockStravaConnection({
        status: "none",
        connected_at: null,
        authorized_by: null,
        last_sync_at: null,
      }),
    ),
);

export const brokenConnectionHandler = http.get(
  "*/api/athletes/:athleteId/strava/connection",
  () =>
    HttpResponse.json(
      mockStravaConnection({
        status: "broken",
        last_sync_at: "2026-06-20T08:00:00Z",
      }),
    ),
);

export const disconnectedConnectionHandler = http.get(
  "*/api/athletes/:athleteId/strava/connection",
  () =>
    HttpResponse.json(
      mockStravaConnection({
        status: "disconnected",
        disconnected_at: "2026-07-01T12:00:00Z",
      }),
    ),
);

export const connectionErrorHandler = http.get(
  "*/api/athletes/:athleteId/strava/connection",
  () => new HttpResponse(null, { status: 500 }),
);

export const connectServiceUnavailableHandler = http.post(
  "*/api/athletes/:athleteId/strava/connect",
  () => new HttpResponse(null, { status: 503 }),
);

export const connectErrorHandler = http.post(
  "*/api/athletes/:athleteId/strava/connect",
  () => new HttpResponse(null, { status: 500 }),
);

export const disconnectErrorHandler = http.delete(
  "*/api/athletes/:athleteId/strava/connection",
  () => new HttpResponse(null, { status: 500 }),
);

export const emptyActivitiesHandler = http.get(
  "*/api/athletes/:athleteId/activities",
  () => HttpResponse.json(mockActivityListResponse({ items: [], total: 0 })),
);

export const activitiesErrorHandler = http.get(
  "*/api/athletes/:athleteId/activities",
  () => new HttpResponse(null, { status: 500 }),
);

// ---------------------------------------------------------------------------
// Variant handlers — revisión coach (GET /api/activities), sugerencias y link
// ---------------------------------------------------------------------------

export const emptyReviewActivitiesHandler = http.get("*/api/activities", () =>
  HttpResponse.json(mockReviewActivityListResponse({ items: [], total: 0 })),
);

export const reviewActivitiesErrorHandler = http.get(
  "*/api/activities",
  () => new HttpResponse(null, { status: 500 }),
);

export const emptySessionSuggestionsHandler = http.get(
  "*/api/activities/:id/session-suggestions",
  () => HttpResponse.json({ suggestions: [] }),
);

export const sessionSuggestionsErrorHandler = http.get(
  "*/api/activities/:id/session-suggestions",
  () => new HttpResponse(null, { status: 500 }),
);

export const linkActivityErrorHandler = http.patch(
  "*/api/activities/:id/link",
  () =>
    HttpResponse.json(
      { detail: "No se pudo actualizar el vínculo. Verifica la conexión e intenta de nuevo." },
      { status: 500 },
    ),
);
