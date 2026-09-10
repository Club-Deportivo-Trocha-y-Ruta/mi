/**
 * API client para el módulo Boletín Mensual Individual por Atleta (Fase 1.8).
 *
 * Sigue el patrón de trainingSessions.ts: funciones async puras + hooks
 * TanStack Query exportados. Privacy R2: userId al inicio del queryKey.
 */

import { isAxiosError } from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth.store";
import type {
  AthleteNewsletter,
  AthleteNewsletterCreate,
  AthleteNewsletterPatch,
  AttachInsightsRequest,
  AttachInsightsResponse,
  BatchResult,
  RegenerateBlockRequest,
} from "@/types/athleteNewsletter.types";

const ATHLETE_BASE = "/api/athletes";
const CLUBS_BASE = "/api/clubs";

// ---------------------------------------------------------------------------
// Error helpers
// ---------------------------------------------------------------------------

function parseApiError(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const status = err.response?.status;
    const detail = err.response?.data?.detail;
    if (status === 401) return "No autenticado. Inicia sesión de nuevo.";
    if (status === 403) return "Sin permiso para realizar esta acción.";
    if (status === 404) return "El boletín no fue encontrado.";
    if (status === 409 && detail) return String(detail);
    if (status === 409) return "Conflicto: el boletín ya existe o está en un estado que no permite esta operación.";
    // 041 §2.5 — falta la precondición de versión (If-Match/expected_version).
    // El detail del backend ya trae la copia correcta ("Recarga la bitácora
    // antes de guardar."); el fallback cubre solo el caso sin body legible.
    if (status === 428 && detail) return String(detail);
    if (status === 428) return "Falta la versión del boletín. Recarga la bitácora antes de guardar.";
    if (status === 500) return "Error interno del servidor. Intenta de nuevo más tarde.";
    if (detail) return String(detail);
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Funciones API puras
// ---------------------------------------------------------------------------

export async function fetchAthleteNewsletters(
  athleteId: number,
  params?: { limit?: number; offset?: number },
): Promise<AthleteNewsletter[]> {
  const response = await apiClient.get<AthleteNewsletter[]>(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters`,
    { params: { limit: params?.limit ?? 12, offset: params?.offset ?? 0 } },
  );
  return response.data;
}

export async function fetchAthleteNewsletter(
  athleteId: number,
  newsletterId: number,
): Promise<AthleteNewsletter> {
  const response = await apiClient.get<AthleteNewsletter>(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters/${newsletterId}`,
  );
  return response.data;
}

export async function createAthleteNewsletter(
  athleteId: number,
  payload: AthleteNewsletterCreate,
): Promise<AthleteNewsletter> {
  const response = await apiClient.post<AthleteNewsletter>(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters`,
    payload,
  );
  return response.data;
}

/**
 * `expected_version` (041 §2.2) es la precondición de concurrencia
 * optimista, nunca un campo real del payload: se extrae acá y viaja
 * siempre como header `If-Match` en forma débil (`W/"<n>"`, aceptada por
 * el backend igual que la fuerte). CORS ya expone `If-Match` en
 * `allow_headers` (`backend/app/main.py`), así que no hace falta el
 * fallback de body del contrato §6.1 ("si R-15 se difiere") — R-15 ya
 * aterrizó en esta rama.
 *
 * Si el caller no manda `expected_version` (hooks que aún no migraron a
 * la precondición), el PATCH sale sin `If-Match` y el backend responde
 * 428 — más seguro que inventar una versión en el cliente.
 */
export async function patchAthleteNewsletter(
  athleteId: number,
  newsletterId: number,
  payload: AthleteNewsletterPatch,
): Promise<AthleteNewsletter> {
  const { expected_version, ...body } = payload;
  const url = `${ATHLETE_BASE}/${athleteId}/monthly-newsletters/${newsletterId}`;
  const response =
    expected_version != null
      ? await apiClient.patch<AthleteNewsletter>(url, body, {
          headers: { "If-Match": `W/"${expected_version}"` },
        })
      : await apiClient.patch<AthleteNewsletter>(url, body);
  return response.data;
}

export async function approveAthleteNewsletter(
  athleteId: number,
  newsletterId: number,
): Promise<AthleteNewsletter> {
  const response = await apiClient.post<AthleteNewsletter>(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters/${newsletterId}/approve`,
  );
  return response.data;
}

export interface SendNewsletterOptions {
  force_individual?: boolean;
  /** Reenvía aunque el boletín ya esté en status=sent (DeliveryPanel, feature 038). */
  force_resend?: boolean;
}

export async function sendAthleteNewsletter(
  athleteId: number,
  newsletterId: number,
  opts?: SendNewsletterOptions,
): Promise<AthleteNewsletter> {
  const params: Record<string, string> = {};
  if (opts?.force_individual) params.force_individual = "true";
  if (opts?.force_resend) params.force_resend = "true";
  const response = await apiClient.post<AthleteNewsletter>(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters/${newsletterId}/send`,
    undefined,
    { params },
  );
  return response.data;
}

export async function batchCreateNewsletters(
  clubId: number,
  payload: { year: number; month: number; force?: boolean },
): Promise<BatchResult> {
  const response = await apiClient.post<BatchResult>(
    `${CLUBS_BASE}/${clubId}/monthly-newsletters/batch`,
    payload,
  );
  return response.data;
}

/**
 * Adjunta insights de carrera a un boletín mensual del atleta.
 * Si no existe boletín para el mes actual, el backend lo crea en estado draft.
 * Solo accesible para coach (backend devuelve 403 para parent).
 */
export async function attachInsightsToNewsletter(
  athleteId: number,
  body: AttachInsightsRequest,
): Promise<AttachInsightsResponse> {
  const response = await apiClient.post<AttachInsightsResponse>(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters/attach-insights`,
    body,
  );
  return response.data;
}

/**
 * Descarga el PDF de un boletín como Blob.
 * El endpoint devuelve el archivo como attachment binario.
 */
export async function downloadNewsletterPdf(
  athleteId: number,
  newsletterId: number,
): Promise<Blob> {
  const response = await apiClient.get(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters/${newsletterId}/pdf`,
    { responseType: "blob" },
  );
  return response.data as Blob;
}

/**
 * Regenera un bloque puntual de la bitácora con IA (feature 038).
 * 409 si el boletín ya fue enviado; 451 si falta el consentimiento IA;
 * 503 si el proveedor falla (el bloque queda intacto en el backend).
 */
export async function regenerateNewsletterBlock(
  athleteId: number,
  newsletterId: number,
  body: RegenerateBlockRequest,
): Promise<AthleteNewsletter> {
  const response = await apiClient.post<AthleteNewsletter>(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters/${newsletterId}/regenerate-block`,
    body,
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// TanStack Query hooks
// ---------------------------------------------------------------------------

/**
 * Lista los boletines de un atleta.
 * Privacy R2: userId al inicio del queryKey para aislar cache por cuenta.
 */
export function useAthleteNewsletters(athleteId: number | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: ["athlete-newsletters", userId, athleteId],
    queryFn: () => fetchAthleteNewsletters(athleteId!),
    enabled: !!accessToken && !!athleteId,
  });
}

/**
 * Obtiene el detalle de un boletín individual.
 */
export function useAthleteNewsletter(
  athleteId: number | undefined,
  newsletterId: number | undefined,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  return useQuery({
    queryKey: ["athlete-newsletter", userId, athleteId, newsletterId],
    queryFn: () => fetchAthleteNewsletter(athleteId!, newsletterId!),
    enabled: !!accessToken && !!athleteId && !!newsletterId,
  });
}

/**
 * Crea o regenera un boletín draft para un atleta.
 */
export function useGenerateNewsletter(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AthleteNewsletterCreate) =>
      createAthleteNewsletter(athleteId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["athlete-newsletters"] });
    },
  });
}

/**
 * Edita la narrativa de un boletín en estado draft.
 */
export function usePatchNewsletter(athleteId: number, newsletterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AthleteNewsletterPatch) =>
      patchAthleteNewsletter(athleteId, newsletterId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["athlete-newsletter"] });
      void queryClient.invalidateQueries({ queryKey: ["athlete-newsletters"] });
    },
  });
}

/**
 * Aprueba un boletín (draft → approved).
 */
export function useApproveNewsletter(athleteId: number, newsletterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => approveAthleteNewsletter(athleteId, newsletterId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["athlete-newsletter"] });
      void queryClient.invalidateQueries({ queryKey: ["athlete-newsletters"] });
    },
  });
}

/**
 * Envía un boletín aprobado a los padres del atleta.
 * force_individual=true omite el chequeo de hermanos en draft.
 */
export function useSendNewsletter(athleteId: number, newsletterId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (opts?: SendNewsletterOptions) =>
      sendAthleteNewsletter(athleteId, newsletterId, opts),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["athlete-newsletter"] });
      void queryClient.invalidateQueries({ queryKey: ["athlete-newsletters"] });
    },
  });
}

/**
 * Crea boletines en batch para todos los atletas activos de un club.
 */
export function useBatchCreateNewsletters(clubId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { year: number; month: number; force?: boolean }) =>
      batchCreateNewsletters(clubId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["athlete-newsletters"] });
    },
  });
}

/**
 * Descarga el PDF preview de un boletín.
 * Retorna un Blob para que el caller lo convierta en URL de descarga.
 */
export function useDownloadNewsletterPdf() {
  return useMutation({
    mutationFn: ({ athleteId, newsletterId }: { athleteId: number; newsletterId: number }) =>
      downloadNewsletterPdf(athleteId, newsletterId),
  });
}

/**
 * Adjunta insights de carrera al boletín del mes para un atleta.
 * Invalida la caché de "athlete-newsletters" para reflejar el nuevo estado.
 * Solo coach puede ejecutar esta mutación (el backend rechaza con 403 a parent).
 */
export function useAttachInsightsToNewsletter(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AttachInsightsRequest) =>
      attachInsightsToNewsletter(athleteId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["athlete-newsletters", athleteId],
      });
    },
  });
}

// Re-exportar parseApiError para uso en componentes
export { parseApiError };
