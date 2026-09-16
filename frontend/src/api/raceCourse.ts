/**
 * API client del módulo race-course (perfil de circuito de una válida).
 *
 * Auth: JWT via interceptor en apiClient.
 * Contrato: `specs/043-race-course-profile/contracts/course-api.md`.
 *
 * Endpoints cubiertos:
 *   - GET    /{id}/course                       → getRaceCourse
 *   - POST   /{id}/course/variants               → uploadCourseVariant
 *   - PUT    /{id}/course/variants/{vid}/file    → replaceCourseVariantFile
 *   - PATCH  /{id}/course/variants/{vid}         → renameCourseVariant
 *   - DELETE /{id}/course/variants/{vid}         → deleteCourseVariant
 *   - PUT    /{id}/course/setups                 → replaceCourseSetups
 *   - PATCH  /{id}/course/description            → updateCourseDescription
 *
 * Toda mutación retorna el `CourseRead` completo (contrato §0): el caller
 * reemplaza la query key `["race-course", raceEventId]` en vez de mergear
 * parciales.
 *
 * Códigos de error posibles (manejo delegado al caller/hook — ver
 * `CourseErrorCode` en `@/types/raceCourse.types`):
 *   415 unsupported_media_type
 *   422 not_gpx | compressed_not_allowed | xml_unsafe | malformed |
 *       no_track_points | no_position | too_short | too_long |
 *       too_few_points | variant_not_in_event | unknown_category |
 *       duplicate_category
 *   413 file_too_large
 *   409 duplicate_recording | variant_label_taken | variant_in_use
 *   404 course_not_available | race_event_not_found | variant_not_found
 */
import { apiClient } from "@/api/client";
import type {
  CourseDescriptionUpdateBody,
  CourseRead,
  SetupsReplaceBody,
  VariantRenameBody,
  VariantReplacePayload,
  VariantUploadPayload,
} from "@/types/raceCourse.types";

const BASE = "/api/race-analysis/race-events";

/**
 * GET /api/race-analysis/race-events/{raceEventId}/course
 *
 * Trae el circuito completo de la válida: variantes (con geometría),
 * configuración de vueltas por categoría, sugerencia de prellenado y
 * descripción cualitativa. `200` con `has_course_data=false` cuando la
 * válida aún no tiene nada (nunca `404` para coach/admin en ese caso).
 *
 * 404 `race_event_not_found` si la válida no existe.
 * 404 `course_not_available` (parents) cuando ninguno de sus atletas está
 * en el roster ni en los resultados de esta válida.
 */
export async function getRaceCourse(
  raceEventId: number,
  options?: { signal?: AbortSignal },
): Promise<CourseRead> {
  const response = await apiClient.get<CourseRead>(
    `${BASE}/${raceEventId}/course`,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * POST /api/race-analysis/race-events/{raceEventId}/course/variants
 *
 * Sube un GPX (multipart) y crea una nueva variante de circuito. `label`
 * es requerido; `recorded_laps`, si se envía, fuerza `detection.method="manual"`.
 * RBAC: coach + admin.
 *
 * 201 con `CourseRead` completo.
 */
export async function uploadCourseVariant(
  raceEventId: number,
  payload: VariantUploadPayload,
  options?: { signal?: AbortSignal },
): Promise<CourseRead> {
  const formData = new FormData();
  formData.append("file", payload.file);
  formData.append("label", payload.label);
  if (payload.recorded_laps !== undefined) {
    formData.append("recorded_laps", String(payload.recorded_laps));
  }
  const response = await apiClient.post<CourseRead>(
    `${BASE}/${raceEventId}/course/variants`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      signal: options?.signal,
    },
  );
  return response.data;
}

/**
 * PUT /api/race-analysis/race-events/{raceEventId}/course/variants/{variantId}/file
 *
 * Reemplaza la grabación GPX de una variante existente (recalcula geometría
 * y métricas in situ). No admite cambiar el `label` — usar
 * `renameCourseVariant` para eso. RBAC: coach + admin.
 */
export async function replaceCourseVariantFile(
  raceEventId: number,
  variantId: number,
  payload: VariantReplacePayload,
  options?: { signal?: AbortSignal },
): Promise<CourseRead> {
  const formData = new FormData();
  formData.append("file", payload.file);
  if (payload.recorded_laps !== undefined) {
    formData.append("recorded_laps", String(payload.recorded_laps));
  }
  const response = await apiClient.put<CourseRead>(
    `${BASE}/${raceEventId}/course/variants/${variantId}/file`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      signal: options?.signal,
    },
  );
  return response.data;
}

/**
 * PATCH /api/race-analysis/race-events/{raceEventId}/course/variants/{variantId}
 *
 * Renombra una variante. RBAC: coach + admin.
 *
 * 409 `variant_label_taken` si el nombre ya existe en esta válida.
 * 404 `variant_not_found` si el id no pertenece a esta válida.
 */
export async function renameCourseVariant(
  raceEventId: number,
  variantId: number,
  body: VariantRenameBody,
  options?: { signal?: AbortSignal },
): Promise<CourseRead> {
  const response = await apiClient.patch<CourseRead>(
    `${BASE}/${raceEventId}/course/variants/${variantId}`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * DELETE /api/race-analysis/race-events/{raceEventId}/course/variants/{variantId}
 *
 * Elimina una variante. RBAC: coach + admin.
 *
 * 409 `variant_in_use` cuando algún setup de categoría la referencia
 * (el body de error incluye las categorías afectadas).
 */
export async function deleteCourseVariant(
  raceEventId: number,
  variantId: number,
  options?: { signal?: AbortSignal },
): Promise<CourseRead> {
  const response = await apiClient.delete<CourseRead>(
    `${BASE}/${raceEventId}/course/variants/${variantId}`,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * PUT /api/race-analysis/race-events/{raceEventId}/course/setups
 *
 * Reemplaza la tabla completa de vueltas por categoría. Una lista vacía
 * limpia la tabla. RBAC: coach + admin.
 *
 * 422 `variant_not_in_event` | `unknown_category` | `duplicate_category`.
 */
export async function replaceCourseSetups(
  raceEventId: number,
  body: SetupsReplaceBody,
  options?: { signal?: AbortSignal },
): Promise<CourseRead> {
  const response = await apiClient.put<CourseRead>(
    `${BASE}/${raceEventId}/course/setups`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * PATCH /api/race-analysis/race-events/{raceEventId}/course/description
 *
 * Actualiza parcialmente la descripción cualitativa del circuito.
 * Semántica `exclude_unset`: un campo ausente no se toca; `null` explícito
 * lo limpia (igual que `updateRaceEventConditions`). RBAC: coach + admin.
 */
export async function updateCourseDescription(
  raceEventId: number,
  body: CourseDescriptionUpdateBody,
  options?: { signal?: AbortSignal },
): Promise<CourseRead> {
  const response = await apiClient.patch<CourseRead>(
    `${BASE}/${raceEventId}/course/description`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}
