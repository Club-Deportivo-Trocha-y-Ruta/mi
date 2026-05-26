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

export async function patchAthleteNewsletter(
  athleteId: number,
  newsletterId: number,
  payload: AthleteNewsletterPatch,
): Promise<AthleteNewsletter> {
  const response = await apiClient.patch<AthleteNewsletter>(
    `${ATHLETE_BASE}/${athleteId}/monthly-newsletters/${newsletterId}`,
    payload,
  );
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
}

export async function sendAthleteNewsletter(
  athleteId: number,
  newsletterId: number,
  opts?: SendNewsletterOptions,
): Promise<AthleteNewsletter> {
  const params: Record<string, string> = {};
  if (opts?.force_individual) params.force_individual = "true";
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
