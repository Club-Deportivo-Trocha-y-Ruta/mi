/**
 * MSW handlers para el tablero de carga histórica (feature 044, US5, T066).
 *
 * Cubre los endpoints que consume `LoadsSection` (y el wizard al retomar):
 *   - GET  /api/race-analysis/imports/
 *   - POST /api/race-analysis/imports/:id/commit
 *   - POST /api/race-analysis/imports/:id/commit-pending
 *   - GET  /api/race-analysis/imports/:id            (feature 045, retomar)
 *   - POST /api/race-analysis/imports/:id/discard    (feature 045)
 *
 * Privacidad: `original_filename`/nombres siempre sintéticos — nunca datos
 * reales de un menor, ni siquiera en fixtures de test.
 */
import { http, HttpResponse } from "msw";

import type {
  ImportCommitResponse,
  ImportDetail,
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

/**
 * `GET /imports/{id}` (feature 045): carga `pending` con dos categorías y
 * meta público (sin `corrections`). Datos sintéticos.
 */
export function makeImportDetail(
  overrides?: Partial<ImportDetail>,
): ImportDetail {
  return {
    id: 1,
    status: "pending",
    source_filename: "valida_1_2026.pdf",
    parse_meta: {
      header: {
        series_name: "Copa Valle de Ciclomontañismo",
        season: 2026,
        valida_num: 1,
        event_name: "Válida I — Ciudad Prueba",
        event_date: "2026-03-15",
        location: "Ciudad Prueba",
      },
      conditions: null,
      n_rows_resultados: 20,
      n_rows_general: 0,
      categories: [
        {
          header_raw: "Sub-15 Mujeres",
          code: "U15F",
          mapping_kind: "exact",
          rows: 12,
          completeness: { status: "ok", missing: [], duplicated: [] },
        },
        {
          header_raw: "Sub-15 Hombres",
          code: "U15M",
          mapping_kind: "exact",
          rows: 8,
          completeness: { status: "ok", missing: [], duplicated: [] },
        },
      ],
      unreadable_rows: [],
      acknowledged: [],
      pending_categories: [],
    },
    created_at: "2026-09-23T12:00:00Z",
    event_id: 501,
    season: 2026,
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
  http.get(`${BASE}/:id`, ({ params }) =>
    HttpResponse.json(makeImportDetail({ id: Number(params.id) })),
  ),
  http.post(`${BASE}/:id/discard`, ({ params }) =>
    HttpResponse.json(
      makeImportDetail({ id: Number(params.id), status: "discarded" }),
    ),
  ),
];

export const raceImportsHistoryEmptyHandler = http.get(`${BASE}/`, () =>
  HttpResponse.json(makeImportListResponse({ items: [], total: 0 })),
);

export const raceImportsHistoryErrorHandler = http.get(`${BASE}/`, () =>
  HttpResponse.json({ detail: "Error interno" }, { status: 500 }),
);

/**
 * `409 identity_pending` (feature 045): cuerpo PLANO, solo cuenta las
 * decisiones que involucran a esta carga. Reemplaza al viejo cuerpo anidado
 * (`detail` como objeto con un código y un conteo global de la cola).
 */
export function identityPendingBody(
  importId: number | string = 1,
  pendingForImport = 3,
) {
  return {
    detail: "identity_pending",
    pending_for_import: pendingForImport,
    review_path: `/competitions/imports?seccion=identidades&import=${importId}`,
  };
}

export const raceImportsHistoryCommitIdentityPendingHandler = http.post(
  `${BASE}/:id/commit`,
  ({ params }) =>
    HttpResponse.json(identityPendingBody(String(params.id)), { status: 409 }),
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
 * `resolved_matches`. Distinto de `identity_pending` (candado de identidad
 * por carga).
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
