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
  RaceEventDiffResponse,
  RevisionReasonsResponse,
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
  // Spec 014: series_kind para que el backend resuelva/cree la serie por tipo.
  // Default "cup" para compatibilidad hacia atrás con flujos que no lo envían.
  if (fields.series_kind) formData.append("series_kind", fields.series_kind);
  // Feature 023: nivel del campeonato (departamental|nacional). El backend
  // solo lo consulta al CREAR una serie de campeonato nueva.
  if (fields.series_level) formData.append("series_level", fields.series_level);

  // F-COND — campos opcionales de condiciones de carrera.
  // Se omiten si son null, undefined o cadena vacía para no contaminar el
  // multipart con campos vacíos que el backend interpretraría como "sin dato".
  if (fields.climate != null && fields.climate !== "") {
    formData.append("climate", fields.climate);
  }
  if (fields.temperature_c != null && fields.temperature_c !== "") {
    // FormData sólo acepta string o Blob; convertir a string explícitamente.
    formData.append("temperature_c", String(fields.temperature_c));
  }
  if (fields.surface_condition != null) {
    formData.append("surface_condition", fields.surface_condition);
  }
  if (fields.altitude_msnm != null) {
    // Convertir a string para cumplir el contrato de FormData.
    formData.append("altitude_msnm", String(fields.altitude_msnm));
  }
  if (fields.weather_notes != null && fields.weather_notes !== "") {
    formData.append("weather_notes", fields.weather_notes);
  }

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
