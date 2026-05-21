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
  ImportCommitRequest,
  ImportCommitResponse,
  ImportDryRunResponse,
  ImportListResponse,
  ImportParseRequestFields,
  ImportParseResponse,
  ImportsHistoryParams,
} from "@/types/raceImports.types";

const BASE = "/api/race-analysis/imports";

/** POST /api/race-analysis/imports/parse — multipart.
 *
 * `resultados_pdf` es obligatorio (PDF o CSV); `general_pdf` opcional
 * (sólo PDF). Los demás campos se envían como form fields.
 */
export async function parseRaceImport(
  fields: ImportParseRequestFields,
  files: { resultadosPdf: File; generalPdf?: File | null },
  options?: { signal?: AbortSignal },
): Promise<ImportParseResponse> {
  const formData = new FormData();
  formData.append("resultados_pdf", files.resultadosPdf);
  if (files.generalPdf) {
    formData.append("general_pdf", files.generalPdf);
  }
  formData.append("series_name", fields.series_name);
  formData.append("season", String(fields.season));
  formData.append("valida_num", String(fields.valida_num));
  formData.append("event_name", fields.event_name);
  formData.append("event_date", fields.event_date);
  formData.append("location", fields.location);
  if (fields.kind) formData.append("kind", fields.kind);

  const response = await apiClient.post<ImportParseResponse>(
    `${BASE}/parse`,
    formData,
    {
      signal: options?.signal,
      headers: {
        // Dejamos que axios setee el boundary del multipart.
        "Content-Type": "multipart/form-data",
      },
    },
  );
  return response.data;
}

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
