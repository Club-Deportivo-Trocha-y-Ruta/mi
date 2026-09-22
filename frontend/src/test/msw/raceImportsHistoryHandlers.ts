/**
 * MSW handlers para el tablero de carga histórica (feature 044, US5, T066).
 *
 * Cubre los endpoints que consume `HistoricalLoadPage`:
 *   - GET  /api/race-analysis/imports/
 *   - POST /api/race-analysis/imports/:id/commit
 *   - POST /api/race-analysis/imports/:id/commit-pending
 *
 * Privacidad: `original_filename`/nombres siempre sintéticos — nunca datos
 * reales de un menor, ni siquiera en fixtures de test.
 */
import { http, HttpResponse } from "msw";

import type {
  ImportCommitResponse,
  ImportListItem,
  ImportListResponse,
} from "@/types/raceImports.types";

const BASE = "*/api/race-analysis/imports";

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function makeHistoricalImportItem(
  overrides?: Partial<ImportListItem>,
): ImportListItem {
  return {
    id: "1",
    kind: "resultados",
    status: "pending",
    created_at: "2026-09-18T12:00:00Z",
    event_id: 501,
    original_filename: "valida_1_2024.pdf",
    uploaded_by: { id: 1, full_name: "Coach Prueba" },
    n_results: 42,
    season: 2024,
    valida_num: 1,
    series_name: "Copa Valle de Ciclomontañismo",
    pending_categories_count: 0,
    ...overrides,
  };
}

export function makeImportListResponse(
  overrides?: Partial<ImportListResponse>,
): ImportListResponse {
  return {
    items: [makeHistoricalImportItem()],
    total: 1,
    ...overrides,
  };
}

export function makeCommitResponse(
  overrides?: Partial<ImportCommitResponse>,
): ImportCommitResponse {
  return {
    parse_id: "1",
    race_event_id: 501,
    n_results_inserted: 42,
    n_competitors_created: 10,
    n_competitors_linked: 3,
    pending_categories: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Handlers por defecto
// ---------------------------------------------------------------------------

export const raceImportsHistoryHandlers = [
  http.get(`${BASE}/`, () => HttpResponse.json(makeImportListResponse())),
  http.post(`${BASE}/:id/commit`, () =>
    HttpResponse.json(makeCommitResponse()),
  ),
  http.post(`${BASE}/:id/commit-pending`, () =>
    HttpResponse.json(makeCommitResponse()),
  ),
];

export const raceImportsHistoryEmptyHandler = http.get(`${BASE}/`, () =>
  HttpResponse.json(makeImportListResponse({ items: [], total: 0 })),
);

export const raceImportsHistoryErrorHandler = http.get(`${BASE}/`, () =>
  HttpResponse.json({ detail: "Error interno" }, { status: 500 }),
);

export const raceImportsHistoryCommitIdentityPendingHandler = http.post(
  `${BASE}/:id/commit`,
  () =>
    HttpResponse.json(
      { detail: { code: "identity_review_pending", pending: 3 } },
      { status: 409 },
    ),
);

export const raceImportsHistoryCommitPendingNothingHandler = http.post(
  `${BASE}/:id/commit-pending`,
  () =>
    HttpResponse.json(
      { detail: { code: "nothing_pending" } },
      { status: 409 },
    ),
);

/**
 * `409 matches_unresolved` (`contracts/historical-load.md` §"Board fields")
 * — el acta tiene un corredor de club (TyR) sin entrada en
 * `resolved_matches`. Distinto de `identity_review_pending` (cola de
 * identidad cruzada entre temporadas).
 */
export const raceImportsHistoryCommitMatchesUnresolvedHandler = http.post(
  `${BASE}/:id/commit`,
  () =>
    HttpResponse.json(
      {
        detail: {
          code: "matches_unresolved",
          missing_count: 2,
          examples: ["ana-prueba-uno", "carlos-prueba-dos"],
          message:
            "Hay 2 corredores del club sin coincidencia resuelta. Complétala en el asistente de importación.",
        },
      },
      { status: 409 },
    ),
);
