/**
 * Cliente API de la planilla mensual de asistencia IMDERTY (feature 047).
 *
 * Contrato: `specs/047-imderty-attendance-sheet/contracts/api.md`. Todas las
 * rutas exigen admin, o coach del club/atleta (403 para padre/atleta — cada
 * ruta tiene su test de acceso negado en el backend). Cada respuesta se
 * valida con `.parse()` (mismo patrón que `api/bodyComposition.ts`).
 *
 * La descarga de la planilla (`downloadImdertySheet`) devuelve el Blob crudo
 * para que el caller use `triggerBlobDownload` (`lib/download.ts`) con el
 * nombre de archivo tomado del header `Content-Disposition` — nunca de datos
 * de un menor (el nombre del archivo solo lleva meses, contrato §Sheet).
 */
import { apiClient } from "@/api/client";
import {
  barrioListSchema,
  barrioSchema,
  clubImdertySettingsSchema,
  imdertyProfileSchema,
  imdertyProfileUpdateResponseSchema,
  imdertyReadinessSchema,
  primaryContactResponseSchema,
  sensitiveAuthorizationSchema,
  sensitiveDataSchema,
  type Barrio,
  type BarrioCreateValues,
  type BarrioUpdateValues,
  type ClubImdertySettings,
  type ClubImdertySettingsUpdateValues,
  type ImdertyProfile,
  type ImdertyProfileUpdateResponse,
  type ImdertyProfileUpdateValues,
  type ImdertyReadiness,
  type ImdertySheetRequestValues,
  type PrimaryContactResponse,
  type PrimaryContactUpdateValues,
  type SensitiveAuthorization,
  type SensitiveAuthorizationCreateValues,
  type SensitiveData,
  type SensitiveDataUpdateValues,
} from "@/schemas/imderty";

function athleteBase(athleteId: number): string {
  return `/api/athletes/${athleteId}`;
}

// ---------------------------------------------------------------------------
// Perfil IMDERTY del atleta
// ---------------------------------------------------------------------------

/** GET /api/athletes/{id}/imderty-profile — nunca 404, un perfil vacío trae nulls. */
export async function getImdertyProfile(athleteId: number): Promise<ImdertyProfile> {
  const response = await apiClient.get<unknown>(`${athleteBase(athleteId)}/imderty-profile`);
  return imdertyProfileSchema.parse(response.data);
}

/** PUT /api/athletes/{id}/imderty-profile — 422 en validaciones del contrato. */
export async function updateImdertyProfile(
  athleteId: number,
  payload: ImdertyProfileUpdateValues,
): Promise<ImdertyProfileUpdateResponse> {
  const response = await apiClient.put<unknown>(`${athleteBase(athleteId)}/imderty-profile`, payload);
  // El backend responde el perfil "aplanado" con `warnings`; normalizamos
  // aquí para que el hook siempre reciba `{ profile, warnings }`.
  const data = response.data as Record<string, unknown>;
  const warnings = Array.isArray(data.warnings) ? data.warnings : [];
  const { warnings: _omit, ...profile } = data;
  return imdertyProfileUpdateResponseSchema.parse({ profile, warnings });
}

/** PUT /api/athletes/{id}/primary-contact — 422 si el usuario no es acudiente vinculado. */
export async function updatePrimaryContact(
  athleteId: number,
  payload: PrimaryContactUpdateValues,
): Promise<PrimaryContactResponse> {
  const response = await apiClient.put<unknown>(`${athleteBase(athleteId)}/primary-contact`, payload);
  return primaryContactResponseSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Datos sensibles
// ---------------------------------------------------------------------------

/** POST /api/athletes/{id}/sensitive-authorizations — 409 si ya hay una activa. */
export async function createSensitiveAuthorization(
  athleteId: number,
  payload: SensitiveAuthorizationCreateValues,
): Promise<SensitiveAuthorization> {
  const response = await apiClient.post<unknown>(
    `${athleteBase(athleteId)}/sensitive-authorizations`,
    payload,
  );
  return sensitiveAuthorizationSchema.parse(response.data);
}

/** POST /api/athletes/{id}/sensitive-authorizations/withdraw — 404 sin autorización activa. */
export async function withdrawSensitiveAuthorization(athleteId: number): Promise<void> {
  await apiClient.post(`${athleteBase(athleteId)}/sensitive-authorizations/withdraw`);
}

/** GET /api/athletes/{id}/sensitive-data — 404 sin autorización activa. */
export async function getSensitiveData(athleteId: number): Promise<SensitiveData> {
  const response = await apiClient.get<unknown>(`${athleteBase(athleteId)}/sensitive-data`);
  return sensitiveDataSchema.parse(response.data);
}

/** PUT /api/athletes/{id}/sensitive-data — 403 sin autorización activa. */
export async function updateSensitiveData(
  athleteId: number,
  payload: SensitiveDataUpdateValues,
): Promise<SensitiveData> {
  const response = await apiClient.put<unknown>(`${athleteBase(athleteId)}/sensitive-data`, payload);
  return sensitiveDataSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Catálogo de barrios
// ---------------------------------------------------------------------------

/** GET /api/imderty/barrios — admin y coach. */
export async function getBarrios(includeInactive = false): Promise<Barrio[]> {
  const response = await apiClient.get<unknown>("/api/imderty/barrios", {
    params: { include_inactive: includeInactive },
  });
  return barrioListSchema.parse(response.data);
}

/** POST /api/imderty/barrios — admin only; 409 si el nombre está duplicado. */
export async function createBarrio(payload: BarrioCreateValues): Promise<Barrio> {
  const response = await apiClient.post<unknown>("/api/imderty/barrios", payload);
  return barrioSchema.parse(response.data);
}

/** PATCH /api/imderty/barrios/{id} — admin only; 409 si el nombre está duplicado. */
export async function updateBarrio(barrioId: number, payload: BarrioUpdateValues): Promise<Barrio> {
  const response = await apiClient.patch<unknown>(`/api/imderty/barrios/${barrioId}`, payload);
  return barrioSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Configuración IMDERTY del club
// ---------------------------------------------------------------------------

/** GET /api/clubs/{id}/imderty-settings — nulls/lista vacía si nunca se guardó. */
export async function getClubImdertySettings(clubId: number): Promise<ClubImdertySettings> {
  const response = await apiClient.get<unknown>(`/api/clubs/${clubId}/imderty-settings`);
  return clubImdertySettingsSchema.parse(response.data);
}

/** PUT /api/clubs/{id}/imderty-settings — get-or-create. */
export async function updateClubImdertySettings(
  clubId: number,
  payload: ClubImdertySettingsUpdateValues,
): Promise<ClubImdertySettings> {
  const response = await apiClient.put<unknown>(`/api/clubs/${clubId}/imderty-settings`, payload);
  return clubImdertySettingsSchema.parse(response.data);
}

// ---------------------------------------------------------------------------
// Planilla: readiness + generación
// ---------------------------------------------------------------------------

/**
 * GET /api/clubs/{id}/imderty-sheet/readiness?from=&to= — 422 si `to < from`,
 * el rango supera 12 meses o hay más de 480 atletas en un mes.
 */
export async function getImdertySheetReadiness(
  clubId: number,
  from: string,
  to: string,
): Promise<ImdertyReadiness> {
  const response = await apiClient.get<unknown>(`/api/clubs/${clubId}/imderty-sheet/readiness`, {
    params: { from, to },
  });
  return imdertyReadinessSchema.parse(response.data);
}

const CONTENT_DISPOSITION_FILENAME_RE = /filename="?([^"; ]+)"?/i;

/** Extrae el nombre de archivo del header `Content-Disposition`, con un respaldo genérico. */
export function extractSheetFilename(contentDisposition: string | undefined, fallback: string): string {
  const match = contentDisposition ? CONTENT_DISPOSITION_FILENAME_RE.exec(contentDisposition) : null;
  return match?.[1] ?? fallback;
}

/**
 * POST /api/clubs/{id}/imderty-sheet — genera y descarga el workbook
 * (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`). El
 * archivo nunca se guarda del lado del servidor; el caller dispara la
 * descarga con `triggerBlobDownload`.
 */
export async function downloadImdertySheet(
  clubId: number,
  payload: ImdertySheetRequestValues,
): Promise<{ blob: Blob; filename: string }> {
  const response = await apiClient.post(`/api/clubs/${clubId}/imderty-sheet`, payload, {
    responseType: "blob",
  });
  const filename = extractSheetFilename(
    response.headers?.["content-disposition"] as string | undefined,
    `FO-GDD-057_asistencia_${payload.from}_${payload.to}.xlsx`,
  );
  return { blob: response.data as Blob, filename };
}
