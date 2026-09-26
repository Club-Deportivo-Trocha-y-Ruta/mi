/**
 * API client del módulo race-imports (Wizard de carga PDFs Copa Valle).
 *
 * Endpoints bajo `/api/race-analysis/imports/*` (ver
 * docs/10-race-results/upload-design.md §4).
 *
 * Auth: JWT via interceptor en apiClient. Cobertura: coach + admin.
 */
import { apiClient } from "@/api/client";
import type {
  AcknowledgeInput,
  AcknowledgeReasonsResponse,
  CategoryCompletenessResponse,
  ImportCommitPendingResponse,
  ImportCommitRequest,
  ImportCommitResponse,
  ImportDetail,
  ImportDryRunResponse,
  ImportListResponse,
  ImportsHistoryParams,
  RaceEventDiffResponse,
  RevisionReasonsResponse,
  RowCorrectionInput,
} from "@/types/raceImports.types";

const BASE = "/api/race-analysis/imports";

// Amendment 2026-09-26 — `parseRaceImport` (POST /imports/parse, multipart)
// se retiró: la carga se prepara fuera de la app (skill/CLI de resultados)
// y llega ya stageada; el wizard solo revisa y confirma
// (`contracts/ui-review-only.md`).

/** POST /api/race-analysis/imports/{parse_id}/dry-run */
export async function dryRunRaceImport(
  parseId: string,
  options?: { signal?: AbortSignal },
): Promise<ImportDryRunResponse> {
  const response = await apiClient.post<ImportDryRunResponse>(
    `${BASE}/${parseId}/dry-run`,
    {},
    { signal: options?.signal },
  );
  return response.data;
}

/** POST /api/race-analysis/imports/{parse_id}/commit */
export async function commitRaceImport(
  parseId: string,
  body: ImportCommitRequest,
  options?: { signal?: AbortSignal },
): Promise<ImportCommitResponse> {
  const response = await apiClient.post<ImportCommitResponse>(
    `${BASE}/${parseId}/commit`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * POST /api/race-analysis/imports/{parse_id}/commit-pending — feature 044 (US5).
 *
 * Ingiere las categorías que quedaron fuera de un commit parcial anterior
 * (`contracts/historical-load.md`). Sin body — reutiliza los matches ya
 * resueltos en el commit inicial. `409 nothing_pending` cuando no hay nada
 * pendiente; mismo candado `409 identity_pending` (por carga) que `/commit`.
 */
export async function commitPendingRaceImport(
  parseId: string,
  options?: { signal?: AbortSignal },
): Promise<ImportCommitPendingResponse> {
  const response = await apiClient.post<ImportCommitPendingResponse>(
    `${BASE}/${parseId}/commit-pending`,
    {},
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * GET /api/race-analysis/imports/{import_id} — feature 045 (US3).
 *
 * Estado + meta público de una carga (cualquier estado) para retomar el
 * wizard desde `?import=<id>`. `404` si no existe o es de otro club.
 */
export async function getRaceImport(
  importId: string | number,
  options?: { signal?: AbortSignal },
): Promise<ImportDetail> {
  const response = await apiClient.get<ImportDetail>(`${BASE}/${importId}`, {
    signal: options?.signal,
  });
  return response.data;
}

/**
 * POST /api/race-analysis/imports/{import_id}/discard — feature 045 (US3).
 *
 * `pending|dry_run` → `discarded` (200, idempotente si ya lo estaba).
 * `409 import_not_discardable` en una carga confirmada o fallida.
 */
export async function discardRaceImport(
  importId: string | number,
  options?: { signal?: AbortSignal },
): Promise<ImportDetail> {
  const response = await apiClient.post<ImportDetail>(
    `${BASE}/${importId}/discard`,
    {},
    { signal: options?.signal },
  );
  return response.data;
}

/** GET /api/race-analysis/imports/?limit=&offset=&status= */
export async function listRaceImports(
  params: ImportsHistoryParams = {},
  options?: { signal?: AbortSignal },
): Promise<ImportListResponse> {
  const response = await apiClient.get<ImportListResponse>(`${BASE}/`, {
    params: {
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
      status: params.status,
    },
    signal: options?.signal,
  });
  return response.data;
}

/**
 * POST /api/race-analysis/imports/{parse_id}/corrections — feature 044 (US1).
 *
 * Agrega/edita/elimina una fila de una categoría del acta parseada.
 * Privacidad: `body.row` trae nombre/ciudad/club de un menor — nunca se
 * loggea (mismo criterio que `parseRaceImport`).
 */
export async function addRaceImportRowCorrection(
  parseId: string,
  body: RowCorrectionInput,
  options?: { signal?: AbortSignal },
): Promise<CategoryCompletenessResponse> {
  const response = await apiClient.post<CategoryCompletenessResponse>(
    `${BASE}/${parseId}/corrections`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * POST /api/race-analysis/imports/{parse_id}/acknowledge — feature 044 (US1).
 *
 * Reconoce una categoría con completitud `inconsistent` usando un motivo
 * del catálogo cerrado (`GET /acknowledge-reasons`) — sin texto libre.
 */
export async function acknowledgeRaceImportCategory(
  parseId: string,
  body: AcknowledgeInput,
  options?: { signal?: AbortSignal },
): Promise<CategoryCompletenessResponse> {
  const response = await apiClient.post<CategoryCompletenessResponse>(
    `${BASE}/${parseId}/acknowledge`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/** GET /api/race-analysis/imports/acknowledge-reasons — catálogo cerrado (feature 044). */
export async function getAcknowledgeReasons(options?: {
  signal?: AbortSignal;
}): Promise<AcknowledgeReasonsResponse> {
  const response = await apiClient.get<AcknowledgeReasonsResponse>(
    `${BASE}/acknowledge-reasons`,
    { signal: options?.signal },
  );
  return response.data;
}

/** GET /api/race-analysis/imports/revision-reasons — catálogo cerrado (PR4). */
export async function getRevisionReasons(options?: {
  signal?: AbortSignal;
}): Promise<RevisionReasonsResponse> {
  const response = await apiClient.get<RevisionReasonsResponse>(
    `${BASE}/revision-reasons`,
    { signal: options?.signal },
  );
  return response.data;
}

/** GET /api/race-analysis/imports/{race_event_id}/diff — read-only (PR4). */
export async function getRaceEventDiff(
  raceEventId: number,
  options?: { signal?: AbortSignal },
): Promise<RaceEventDiffResponse> {
  const response = await apiClient.get<RaceEventDiffResponse>(
    `${BASE}/${raceEventId}/diff`,
    { signal: options?.signal },
  );
  return response.data;
}
