/**
 * MSW handlers para el módulo race-identity — revisión de identidad
 * (feature 044, US4).
 *
 * Cubre los endpoints:
 *   - POST /api/race-identity/rebuild
 *   - GET  /api/race-identity/candidates
 *   - GET  /api/race-identity/summary
 *   - POST /api/race-identity/candidates/:id/decide
 *   - POST /api/race-identity/candidates/:id/reverse
 *
 * Uso en tests:
 * ```ts
 * import { raceIdentityHandlers, makeIdentityCandidate } from "@/test/msw/raceIdentityHandlers";
 * mswServer.use(...raceIdentityHandlers);
 * ```
 *
 * Privacidad: nombres siempre sintéticos ("Ana Prueba Uno") — nunca datos
 * reales de un menor, ni siquiera en fixtures de test.
 */
import { http, HttpResponse } from "msw";

import type {
  IdentityCandidateRead,
  IdentityCandidatesResponse,
  IdentityRecordRead,
  IdentitySummaryResponse,
} from "@/types/raceIdentity.types";

const BASE = "*/api/race-identity";

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function makeIdentityRecord(
  overrides?: Partial<IdentityRecordRead>,
): IdentityRecordRead {
  return {
    name_printed: "Ana Prueba Uno",
    club: "Club Prueba",
    city: "Ciudad Prueba",
    seasons: [2024, 2025],
    category_labels: ["Infantil B", "Prejuvenil A"],
    competitor_id: 101,
    athlete_linked: false,
    ...overrides,
  };
}

export function makeIdentityCandidate(
  overrides?: Partial<IdentityCandidateRead>,
): IdentityCandidateRead {
  return {
    id: 1,
    kind: "same_person_suspect",
    score: 92,
    signals: ["extra_or_missing_surname"],
    left: makeIdentityRecord({ competitor_id: 101 }),
    right: makeIdentityRecord({
      name_printed: "Ana Prueba",
      competitor_id: 102,
    }),
    state: "pending",
    linked_athlete_involved: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Handlers por defecto (escenario feliz — dos pendientes)
// ---------------------------------------------------------------------------

export function makeCandidatesResponse(
  overrides?: Partial<IdentityCandidatesResponse>,
): IdentityCandidatesResponse {
  const base: IdentityCandidatesResponse = {
    items: [
      makeIdentityCandidate({ id: 1 }),
      makeIdentityCandidate({
        id: 2,
        kind: "homonym_suspect",
        signals: ["same_valida_two_categories", "sex_conflict"],
        left: makeIdentityRecord({
          name_printed: "Beto Prueba Dos",
          competitor_id: 201,
        }),
        right: makeIdentityRecord({
          name_printed: "Beto Prueba Dos",
          competitor_id: 202,
        }),
        linked_athlete_involved: true,
      }),
    ],
    total: 2,
    page: 1,
    page_size: 20,
  };
  return { ...base, ...overrides };
}

export function makeSummaryResponse(
  overrides?: Partial<IdentitySummaryResponse>,
): IdentitySummaryResponse {
  return {
    pending: 2,
    same_person: 1,
    different_people: 0,
    ...overrides,
  };
}

const getCandidatesHandler = http.get(`${BASE}/candidates`, () => {
  return HttpResponse.json(makeCandidatesResponse());
});

const getSummaryHandler = http.get(`${BASE}/summary`, () => {
  return HttpResponse.json(makeSummaryResponse());
});

const decideHandler = http.post(
  `${BASE}/candidates/:id/decide`,
  async ({ params, request }) => {
    const body = (await request.json()) as { answer: string };
    return HttpResponse.json({
      id: Number(params.id),
      state: body.answer,
      merged: false,
      results_moved: 0,
    });
  },
);

const reverseHandler = http.post(`${BASE}/candidates/:id/reverse`, ({ params }) => {
  return HttpResponse.json({
    id: Number(params.id),
    state: "pending",
    split: false,
    results_moved: 0,
    links_cleared: 0,
  });
});

const rebuildHandler = http.post(`${BASE}/rebuild`, () => {
  return HttpResponse.json({
    created: 0,
    unchanged: 2,
    pending: 2,
    removed: 0,
    imports_unreadable: [],
  });
});

export const raceIdentityHandlers = [
  getCandidatesHandler,
  getSummaryHandler,
  decideHandler,
  reverseHandler,
  rebuildHandler,
];

// ---------------------------------------------------------------------------
// Escenarios puntuales
// ---------------------------------------------------------------------------

/** Sin candidatos pendientes — cola vacía. */
export const raceIdentityEmptyHandler = http.get(`${BASE}/candidates`, () => {
  return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 });
});

export const raceIdentityEmptySummaryHandler = http.get(`${BASE}/summary`, () => {
  return HttpResponse.json({ pending: 0, same_person: 0, different_people: 0 });
});

/** Error 500 al listar candidatos. */
export const raceIdentityErrorHandler = http.get(`${BASE}/candidates`, () => {
  return HttpResponse.json({ detail: "Error interno" }, { status: 500 });
});

/**
 * El candidato ya no está pendiente — 409 al decidir.
 * Forma real de `race_identity.py::decide_identity_candidate`:
 * `HTTPException(detail={"code": ..., "message": ...})` serializa como
 * `{"detail": {"code": ..., "message": ...}}`.
 */
export const raceIdentityDecideConflictHandler = http.post(
  `${BASE}/candidates/:id/decide`,
  () => {
    return HttpResponse.json(
      {
        detail: {
          code: "candidate_not_pending",
          message: "Este candidato ya fue decidido.",
        },
      },
      { status: 409 },
    );
  },
);

/**
 * El lado ya vinculado es ambiguo para fusionar (`same_person` sobre un
 * competidor con `athlete_id`, sin desempate posible) — 409 al decidir.
 * Mensaje real de `race_identity.py::_CONFLICT_MESSAGES["linked_competitor_ambiguous"]`.
 */
export const raceIdentityDecideLinkedAmbiguousHandler = http.post(
  `${BASE}/candidates/:id/decide`,
  () => {
    return HttpResponse.json(
      {
        detail: {
          code: "linked_competitor_ambiguous",
          message:
            "Este competidor está vinculado a un deportista del club. Desvincúlalo, decide y vuelve a vincularlo.",
        },
      },
      { status: 409 },
    );
  },
);
