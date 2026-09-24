/**
 * Cliente API de composición corporal por pliegues cutáneos (feature 046).
 *
 * `contracts/skinfolds-api.md` §8. Cada respuesta se valida con `.parse()`
 * (allowlist en cliente, mismo patrón que `api/intervals.ts`). Los blobs
 * (nota de remisión, instructivo de campo) se devuelven crudos para que el
 * llamador use `triggerBlobDownload` (`lib/download.ts`).
 *
 * RBAC: `getBodyComposition` y `downloadFieldGuide` son coach/admin (el
 * backend responde 403 a padres); `saveSkinfolds`/`deleteSkinfolds`/
 * `downloadReferralNote` también. Ningún método de este módulo es accesible
 * para el rol `parent` — el bloque de familia viaja dentro de
 * `growth-summary`, no por aquí.
 */
import { apiClient } from "@/api/client";
import { bodyCompositionOutSchema, skinfoldSetOutSchema } from "@/schemas/bodyComposition.schema";
import type {
  BodyCompositionOut,
  SkinfoldSetIn,
  SkinfoldSetOut,
} from "@/types/bodyComposition.types";

function athleteBase(athleteId: number): string {
  return `/api/athletes/${athleteId}`;
}

/** GET /api/athletes/{id}/body-composition — coach/admin; parent → 403. */
export async function getBodyComposition(athleteId: number): Promise<BodyCompositionOut> {
  const response = await apiClient.get<unknown>(`${athleteBase(athleteId)}/body-composition`);
  return bodyCompositionOutSchema.parse(response.data);
}

/**
 * PUT /api/athletes/{id}/anthropometry/{recordId}/skinfolds — crea o
 * reemplaza el set de pliegues de una evaluación.
 */
export async function saveSkinfolds(
  athleteId: number,
  recordId: number,
  payload: SkinfoldSetIn,
): Promise<SkinfoldSetOut> {
  const response = await apiClient.put<unknown>(
    `${athleteBase(athleteId)}/anthropometry/${recordId}/skinfolds`,
    payload,
  );
  return skinfoldSetOutSchema.parse(response.data);
}

/** DELETE /api/athletes/{id}/anthropometry/{recordId}/skinfolds — 204. */
export async function deleteSkinfolds(athleteId: number, recordId: number): Promise<void> {
  await apiClient.delete(`${athleteBase(athleteId)}/anthropometry/${recordId}/skinfolds`);
}

/**
 * GET /api/athletes/{id}/body-composition/referral-note.pdf — nota de
 * remisión sin cifras ni nombre (sólo iniciales), 409 `no_skinfold_data`
 * cuando el atleta no tiene ningún set.
 */
export async function downloadReferralNote(athleteId: number): Promise<Blob> {
  const response = await apiClient.get(
    `${athleteBase(athleteId)}/body-composition/referral-note.pdf`,
    { responseType: "blob" },
  );
  return response.data as Blob;
}

/**
 * GET /api/body-composition/field-guide.pdf — instructivo estático, sin
 * datos de ningún deportista; coach/admin, parent → 403.
 */
export async function downloadFieldGuide(): Promise<Blob> {
  const response = await apiClient.get("/api/body-composition/field-guide.pdf", {
    responseType: "blob",
  });
  return response.data as Blob;
}
