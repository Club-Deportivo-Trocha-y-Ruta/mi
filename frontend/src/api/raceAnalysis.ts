/**
 * API client del módulo race-analysis v2 (Fase 6 frontend).
 *
 * Endpoints documentados en docs/10-race-results/v2-agentic-design.md §9.
 * Auth: JWT via interceptor en apiClient. Cobertura: coach + admin.
 *
 * Privacidad: ninguna función expone athlete_id ni nombres reales en
 * payloads visibles al cliente, sólo los recibe el backend.
 */
import { apiClient } from "@/api/client";
import type {
  ChatRequestBody,
  ChatResponse,
  HITLDecisionRequest,
  HITLDecisionResponse,
  RunResultEnvelope,
  RunStatusResponse,
  StartRunRequest,
  StartRunResponse,
} from "@/types/raceAnalysis.types";

const BASE = "/api/race-analysis";

export async function startRun(
  body: StartRunRequest,
  options?: { signal?: AbortSignal },
): Promise<StartRunResponse> {
  const response = await apiClient.post<StartRunResponse>(`${BASE}/runs`, body, {
    signal: options?.signal,
  });
  return response.data;
}

/** GET /runs/:id/status?since=N
 *
 * Tolerante a 304 (Not Modified) — devuelve null para que el caller
 * sepa que no debe re-procesar eventos. TanStack Query mantiene los
 * datos previos automáticamente (`placeholderData`).
 */
export async function getRunStatus(
  runId: string,
  since: number,
  options?: { signal?: AbortSignal; etag?: string },
): Promise<RunStatusResponse | null> {
  const headers: Record<string, string> = {};
  if (options?.etag) headers["If-None-Match"] = options.etag;

  const response = await apiClient.get<RunStatusResponse>(
    `${BASE}/runs/${runId}/status`,
    {
      params: { since },
      signal: options?.signal,
      headers,
      validateStatus: (status) => status === 200 || status === 304,
    },
  );
  if (response.status === 304) return null;
  return response.data;
}

export async function submitHITLDecision(
  runId: string,
  stepId: string,
  body: HITLDecisionRequest,
  options?: { signal?: AbortSignal },
): Promise<HITLDecisionResponse> {
  const response = await apiClient.post<HITLDecisionResponse>(
    `${BASE}/runs/${runId}/hitl/${stepId}`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

export async function getRunResult(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<RunResultEnvelope> {
  const response = await apiClient.get<RunResultEnvelope>(
    `${BASE}/runs/${runId}/result`,
    { signal: options?.signal },
  );
  return response.data;
}

export async function chatTurn(
  body: ChatRequestBody,
  options?: { signal?: AbortSignal },
): Promise<ChatResponse> {
  const response = await apiClient.post<ChatResponse>(
    `${BASE}/chat`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/** Construye la URL absoluta del PDF, usable directamente en
 * `<a href>` o `window.open`. El backend stream el binario y maneja
 * el header Content-Disposition. Requiere que el navegador adjunte la
 * cookie de sesión — como el SPA usa Bearer JWT, **no** podemos hacer
 * `window.open` directamente sin pasar el token. Por eso devolvemos
 * sólo el path y el componente PdfDownloadButton hace la descarga
 * autenticada vía fetch + blob.
 */
export function getRunPdfPath(runId: string): string {
  return `${BASE}/runs/${runId}/pdf`;
}

/** Descarga el PDF autenticado y dispara el download en el navegador.
 *
 * Usa fetch (no apiClient para evitar interceptors que parsean JSON).
 * El JWT viaja en header Authorization manualmente.
 */
export async function downloadRunPdf(
  runId: string,
  accessToken: string | null,
): Promise<void> {
  const base = (apiClient.defaults.baseURL ?? "").replace(/\/$/, "");
  const url = `${base}${getRunPdfPath(runId)}`;
  const headers: Record<string, string> = {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const res = await fetch(url, { headers });
  if (!res.ok) {
    throw new Error(`PDF download failed: ${res.status}`);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = `analisis-${runId.slice(0, 12)}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

// ---------------------------------------------------------------------------
// PR5 — re-trigger IA + flag stale
// ---------------------------------------------------------------------------

export interface RunInvalidateResponse {
  run_id: string;
  stale: boolean;
}

/** POST /runs/:id/invalidate — marca un run como desactualizado (stale). */
export async function invalidateRun(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<RunInvalidateResponse> {
  const response = await apiClient.post<RunInvalidateResponse>(
    `${BASE}/runs/${runId}/invalidate`,
    undefined,
    { signal: options?.signal },
  );
  return response.data;
}

/** POST /runs/:id/re-execute — re-ejecuta el análisis (manual, D5). */
export async function reExecuteRun(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<StartRunResponse> {
  const response = await apiClient.post<StartRunResponse>(
    `${BASE}/runs/${runId}/re-execute`,
    undefined,
    { signal: options?.signal },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Group runs — Feature 010 (US1: launch group analysis from Insights tab)
// ---------------------------------------------------------------------------

import type {
  GroupRunLaunchRequest,
  GroupRunLaunchResponse,
  RaceEventRunsResponse,
} from "@/types/raceAnalysis.types";

/**
 * POST /race-events/{id}/runs — lanza análisis grupal para todos los
 * deportistas del club con resultados en esa válida. Puede filtrar por
 * athlete_ids (retry de fallidos).
 *
 * Códigos de respuesta:
 *   200  → parcial o completo (GroupRunLaunchResponse)
 *   422  → sin resultados importados
 *   429  → límite de análisis simultáneos
 *   503  → presupuesto mensual agotado
 */
export async function launchGroupAnalysis(
  raceEventId: number,
  body: GroupRunLaunchRequest,
  options?: { signal?: AbortSignal },
): Promise<GroupRunLaunchResponse> {
  const response = await apiClient.post<GroupRunLaunchResponse>(
    `${BASE}/race-events/${raceEventId}/runs`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * GET /race-events/{id}/runs?active_only=true — recupera runs activos
 * para un evento (útil para restaurar estado tras refresh de página).
 */
export async function getRaceEventRuns(
  raceEventId: number,
  opts?: { activeOnly?: boolean },
  options?: { signal?: AbortSignal },
): Promise<RaceEventRunsResponse> {
  const response = await apiClient.get<RaceEventRunsResponse>(
    `${BASE}/race-events/${raceEventId}/runs`,
    {
      params: opts?.activeOnly !== undefined
        ? { active_only: opts.activeOnly }
        : undefined,
      signal: options?.signal,
    },
  );
  return response.data;
}
