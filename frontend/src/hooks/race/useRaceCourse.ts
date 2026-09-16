/**
 * Hooks TanStack Query del módulo race-course — perfil de circuito de una
 * válida (feature 043).
 *
 * - `useRaceCourse(raceEventId)` → query GET /{id}/course.
 * - Una mutation por endpoint de escritura (subir/reemplazar/renombrar/borrar
 *   variante, reemplazar setups, actualizar descripción). Cada una invalida
 *   `["race-course", raceEventId]` (esta misma query) y
 *   `["race-results", raceEventId]` (la tabla de resultados también deriva
 *   distancia/velocidad del circuito una vez conectada esa pieza).
 *
 * El toast de éxito/error vive en el componente que consume estos hooks
 * (patrón establecido en `useRaceEventConditions`).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  deleteCourseVariant,
  getRaceCourse,
  renameCourseVariant,
  replaceCourseSetups,
  replaceCourseVariantFile,
  updateCourseDescription,
  uploadCourseVariant,
} from "@/api/raceCourse";
import type {
  CourseDescriptionUpdateBody,
  CourseRead,
  SetupsReplaceBody,
  VariantRenameBody,
  VariantReplacePayload,
  VariantUploadPayload,
} from "@/types/raceCourse.types";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

/** Key de la query del circuito de una válida específica. */
const raceCourseKey = (raceEventId: number) =>
  ["race-course", raceEventId] as const;

/** Key de la tabla de resultados de la válida (deriva de la geometría). */
const raceResultsKey = (raceEventId: number) =>
  ["race-results", raceEventId] as const;

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

/**
 * Trae el circuito completo (variantes, setups, sugerencia, descripción) de
 * una válida. `retry: false` — los errores 404 (`race_event_not_found`,
 * `course_not_available` para parents) se manejan en el componente, no
 * reintentando.
 */
export function useRaceCourse(raceEventId: number) {
  return useQuery({
    queryKey: raceCourseKey(raceEventId),
    queryFn: ({ signal }) => getRaceCourse(raceEventId, { signal }),
    retry: false,
  });
}

// ---------------------------------------------------------------------------
// Helper de invalidación compartido por todas las mutations de este módulo
// ---------------------------------------------------------------------------

function invalidateCourse(
  queryClient: ReturnType<typeof useQueryClient>,
  raceEventId: number,
): void {
  void queryClient.invalidateQueries({ queryKey: raceCourseKey(raceEventId) });
  void queryClient.invalidateQueries({ queryKey: raceResultsKey(raceEventId) });
}

// ---------------------------------------------------------------------------
// Mutation: subir variante (POST /course/variants)
// ---------------------------------------------------------------------------

export interface UseUploadCourseVariantVariables {
  raceEventId: number;
  payload: VariantUploadPayload;
}

export function useUploadCourseVariant() {
  const queryClient = useQueryClient();

  return useMutation<CourseRead, unknown, UseUploadCourseVariantVariables>({
    mutationKey: ["race-course", "upload-variant"],
    mutationFn: ({ raceEventId, payload }) =>
      uploadCourseVariant(raceEventId, payload),
    onSuccess: (_data, variables) => {
      invalidateCourse(queryClient, variables.raceEventId);
    },
  });
}

// ---------------------------------------------------------------------------
// Mutation: reemplazar archivo de una variante (PUT /course/variants/{id}/file)
// ---------------------------------------------------------------------------

export interface UseReplaceCourseVariantFileVariables {
  raceEventId: number;
  variantId: number;
  payload: VariantReplacePayload;
}

export function useReplaceCourseVariantFile() {
  const queryClient = useQueryClient();

  return useMutation<
    CourseRead,
    unknown,
    UseReplaceCourseVariantFileVariables
  >({
    mutationKey: ["race-course", "replace-variant-file"],
    mutationFn: ({ raceEventId, variantId, payload }) =>
      replaceCourseVariantFile(raceEventId, variantId, payload),
    onSuccess: (_data, variables) => {
      invalidateCourse(queryClient, variables.raceEventId);
    },
  });
}

// ---------------------------------------------------------------------------
// Mutation: renombrar variante (PATCH /course/variants/{id})
// ---------------------------------------------------------------------------

export interface UseRenameCourseVariantVariables {
  raceEventId: number;
  variantId: number;
  body: VariantRenameBody;
}

export function useRenameCourseVariant() {
  const queryClient = useQueryClient();

  return useMutation<CourseRead, unknown, UseRenameCourseVariantVariables>({
    mutationKey: ["race-course", "rename-variant"],
    mutationFn: ({ raceEventId, variantId, body }) =>
      renameCourseVariant(raceEventId, variantId, body),
    onSuccess: (_data, variables) => {
      invalidateCourse(queryClient, variables.raceEventId);
    },
  });
}

// ---------------------------------------------------------------------------
// Mutation: borrar variante (DELETE /course/variants/{id})
// ---------------------------------------------------------------------------

export interface UseDeleteCourseVariantVariables {
  raceEventId: number;
  variantId: number;
}

export function useDeleteCourseVariant() {
  const queryClient = useQueryClient();

  return useMutation<CourseRead, unknown, UseDeleteCourseVariantVariables>({
    mutationKey: ["race-course", "delete-variant"],
    mutationFn: ({ raceEventId, variantId }) =>
      deleteCourseVariant(raceEventId, variantId),
    onSuccess: (_data, variables) => {
      invalidateCourse(queryClient, variables.raceEventId);
    },
  });
}

// ---------------------------------------------------------------------------
// Mutation: reemplazar tabla de vueltas por categoría (PUT /course/setups)
// ---------------------------------------------------------------------------

export interface UseReplaceCourseSetupsVariables {
  raceEventId: number;
  body: SetupsReplaceBody;
}

export function useReplaceCourseSetups() {
  const queryClient = useQueryClient();

  return useMutation<CourseRead, unknown, UseReplaceCourseSetupsVariables>({
    mutationKey: ["race-course", "replace-setups"],
    mutationFn: ({ raceEventId, body }) =>
      replaceCourseSetups(raceEventId, body),
    onSuccess: (_data, variables) => {
      invalidateCourse(queryClient, variables.raceEventId);
    },
  });
}

// ---------------------------------------------------------------------------
// Mutation: actualizar descripción del circuito (PATCH /course/description)
// ---------------------------------------------------------------------------

export interface UseUpdateCourseDescriptionVariables {
  raceEventId: number;
  body: CourseDescriptionUpdateBody;
}

export function useUpdateCourseDescription() {
  const queryClient = useQueryClient();

  return useMutation<CourseRead, unknown, UseUpdateCourseDescriptionVariables>({
    mutationKey: ["race-course", "update-description"],
    mutationFn: ({ raceEventId, body }) =>
      updateCourseDescription(raceEventId, body),
    onSuccess: (_data, variables) => {
      invalidateCourse(queryClient, variables.raceEventId);
    },
  });
}
