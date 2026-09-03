/**
 * API client para la Bitácora del padre (feature 038).
 *
 * Router backend: `app/routers/parent_newsletters.py`, prefix
 * `/api/parents/me/athletes/{athleteId}/newsletters` (contracts/api.md).
 * RBAC `require_role([parent])`; el backend devuelve 404 si el atleta no
 * está vinculado al padre autenticado.
 */
import { apiClient } from "@/api/client";
import type { ParentStageLog } from "@/types/stageLog.types";

const PARENT_NEWSLETTERS_BASE = "/api/parents/me/athletes";

export interface ParentNewsletterListItem {
  id: number;
  athlete_id: number;
  year: number;
  month: number;
  period_label: string;
  stage_title: string;
  sent_at: string;
  read_at: string | null;
}

export interface ParentNewsletterOut {
  id: number;
  athlete_id: number;
  year: number;
  month: number;
  period_label: string;
  sent_at: string;
  read_at: string | null;
  has_pdf: boolean;
  stage_log: ParentStageLog;
}

function basePath(athleteId: number): string {
  return `${PARENT_NEWSLETTERS_BASE}/${athleteId}/newsletters`;
}

/** `GET /` — lista de boletines enviados, orden `(year, month)` desc. */
export async function listParentNewsletters(
  athleteId: number,
): Promise<ParentNewsletterListItem[]> {
  const response = await apiClient.get<ParentNewsletterListItem[]>(
    basePath(athleteId),
  );
  return response.data;
}

/** `GET /{newsletterId}` — detalle (stage_log ya pasado por to_parent_dto). */
export async function getParentNewsletter(
  athleteId: number,
  newsletterId: number,
): Promise<ParentNewsletterOut> {
  const response = await apiClient.get<ParentNewsletterOut>(
    `${basePath(athleteId)}/${newsletterId}`,
  );
  return response.data;
}

/**
 * URL autenticada del PDF. El backend regenera si el hash está desactualizado.
 * Descargar siempre vía este endpoint (no hay ruta de storage predecible).
 */
export async function getParentNewsletterPdfUrl(
  athleteId: number,
  newsletterId: number,
): Promise<Blob> {
  const response = await apiClient.get(
    `${basePath(athleteId)}/${newsletterId}/pdf`,
    { responseType: "blob" },
  );
  return response.data as Blob;
}

/**
 * `POST /{newsletterId}/read` — idempotente, siempre 204. Marca `read_at`
 * en el primer llamado; llamados subsecuentes son no-op en el backend.
 */
export async function markNewsletterRead(
  athleteId: number,
  newsletterId: number,
): Promise<void> {
  await apiClient.post(`${basePath(athleteId)}/${newsletterId}/read`);
}
