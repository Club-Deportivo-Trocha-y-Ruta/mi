/**
 * Hooks TanStack Query del módulo Entrenamiento por Intervalos (feature 026).
 *
 * Mirroring de convenciones de `hooks/strength/useStrength.ts` (feature 021):
 * query-key factory + estructuras (US1) + templates/adjunto (US4) + comparación
 * plan-vs-real (US2) + descarga del instructivo (US3).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  archiveTemplate,
  attachTemplate,
  createStructure,
  createTemplate,
  deleteStructure,
  downloadInstructivo,
  getSessionMatch,
  getSessionStructure,
  listTemplates,
  recalculateMatch,
  updateStructure,
  updateTemplate,
} from "@/api/intervals";
import type {
  InstructivoBrand,
  IntervalAttachInput,
  IntervalRecalculateInput,
  IntervalStructureCreateInput,
  IntervalStructureOut,
  IntervalStructureUpdateInput,
  IntervalTemplateFilters,
  IntervalTemplateList,
  IntervalTemplateOut,
  IntervalTemplateSaveInput,
  MatchDetail,
  MatchRecalculateResponse,
} from "@/types/intervals.types";

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const intervalKeys = {
  all: ["intervals"] as const,
  sessionStructure: (trainingSessionId: number) =>
    ["intervals", "session-structure", trainingSessionId] as const,
  templates: (filters?: unknown) =>
    ["intervals", "templates", filters ?? {}] as const,
  template: (id: number) => ["intervals", "template", id] as const,
  sessionMatch: (trainingSessionId: number, activityId?: number) =>
    ["intervals", "session-match", trainingSessionId, activityId ?? null] as const,
};

// ---------------------------------------------------------------------------
// Estructuras (US1)
// ---------------------------------------------------------------------------

/** Estructura de intervalos adjunta a una sesión (404 → sin estructura, estado vacío). */
export function useSessionStructure(
  trainingSessionId: number,
  enabled = true,
) {
  return useQuery<IntervalStructureOut>({
    queryKey: intervalKeys.sessionStructure(trainingSessionId),
    queryFn: () => getSessionStructure(trainingSessionId),
    enabled: enabled && trainingSessionId > 0,
    staleTime: 2 * 60 * 1000,
    retry: false, // 404 es un estado esperado (aún no hay estructura)
  });
}

/** Variables de `useSaveStructure` — unión discriminada por `mode` (bodies distintos). */
export type SaveStructureVariables =
  | { mode: "create"; input: IntervalStructureCreateInput }
  | { mode: "update"; id: number; input: IntervalStructureUpdateInput };

/**
 * Crea o reemplaza la estructura de una sesión (create/update unificados).
 * `mode: "create"` → POST /structures; `mode: "update"` → PUT /structures/{id}
 * (el body de update omite `training_session_id`, de ahí la unión discriminada).
 * Actualiza la caché de la estructura de la sesión e invalida la comparación
 * (un cambio de estructura dispara un recálculo diferido en el servidor).
 */
export function useSaveStructure() {
  const queryClient = useQueryClient();
  return useMutation<IntervalStructureOut, unknown, SaveStructureVariables>({
    mutationKey: ["intervals", "save-structure"],
    mutationFn: (variables) =>
      variables.mode === "update"
        ? updateStructure(variables.id, variables.input)
        : createStructure(variables.input),
    onSuccess: (data) => {
      queryClient.setQueryData(
        intervalKeys.sessionStructure(data.training_session_id),
        data,
      );
      void queryClient.invalidateQueries({
        queryKey: ["intervals", "session-match", data.training_session_id],
      });
    },
  });
}

/**
 * Elimina la estructura de una sesión.
 * Invalida la estructura y la comparación de esa sesión (las vueltas se preservan).
 */
export function useDeleteStructure() {
  const queryClient = useQueryClient();
  return useMutation<
    void,
    unknown,
    { structureId: number; trainingSessionId: number }
  >({
    mutationKey: ["intervals", "delete-structure"],
    mutationFn: ({ structureId }) => deleteStructure(structureId),
    onSuccess: (_data, { trainingSessionId }) => {
      void queryClient.invalidateQueries({
        queryKey: intervalKeys.sessionStructure(trainingSessionId),
      });
      void queryClient.invalidateQueries({
        queryKey: ["intervals", "session-match", trainingSessionId],
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Templates (US4)
// ---------------------------------------------------------------------------

/** Lista y filtra los templates del club del coach. */
export function useTemplates(filters?: IntervalTemplateFilters) {
  return useQuery<IntervalTemplateList>({
    queryKey: intervalKeys.templates(filters),
    queryFn: () => listTemplates(filters),
    staleTime: 5 * 60 * 1000, // la librería cambia raramente
    placeholderData: (prev) => prev, // evita parpadeo al cambiar filtros
  });
}

/**
 * Crea o edita un template (create/update unificados).
 * Sin `id` → POST /templates; con `id` → PUT /templates/{id}.
 * Actualiza el detalle en caché e invalida el listado.
 */
export function useSaveTemplate() {
  const queryClient = useQueryClient();
  return useMutation<
    IntervalTemplateOut,
    unknown,
    { id?: number; input: IntervalTemplateSaveInput }
  >({
    mutationKey: ["intervals", "save-template"],
    mutationFn: ({ id, input }) =>
      id ? updateTemplate(id, input) : createTemplate(input),
    onSuccess: (data) => {
      queryClient.setQueryData(intervalKeys.template(data.id), data);
      void queryClient.invalidateQueries({
        queryKey: ["intervals", "templates"],
      });
    },
  });
}

/**
 * Archiva o desarchiva un template.
 * Invalida el listado (el default `include_archived=false` puede excluirlo) y
 * actualiza el detalle en caché.
 */
export function useArchiveTemplate() {
  const queryClient = useQueryClient();
  return useMutation<
    IntervalTemplateOut,
    unknown,
    { id: number; isArchived: boolean }
  >({
    mutationKey: ["intervals", "archive-template"],
    mutationFn: ({ id, isArchived }) => archiveTemplate(id, isArchived),
    onSuccess: (data) => {
      queryClient.setQueryData(intervalKeys.template(data.id), data);
      void queryClient.invalidateQueries({
        queryKey: ["intervals", "templates"],
      });
    },
  });
}

/**
 * Adjunta (clona) un template a una sesión → nueva estructura (`StructureOut`).
 * Actualiza la caché de la estructura de la sesión e invalida su comparación.
 */
export function useAttachTemplate() {
  const queryClient = useQueryClient();
  return useMutation<
    IntervalStructureOut,
    unknown,
    { templateId: number; input: IntervalAttachInput }
  >({
    mutationKey: ["intervals", "attach-template"],
    mutationFn: ({ templateId, input }) => attachTemplate(templateId, input),
    onSuccess: (data) => {
      queryClient.setQueryData(
        intervalKeys.sessionStructure(data.training_session_id),
        data,
      );
      void queryClient.invalidateQueries({
        queryKey: ["intervals", "session-match", data.training_session_id],
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Matching (US2)
// ---------------------------------------------------------------------------

/**
 * Comparación plan-vs-real de una sesión. Mientras el servidor reporta
 * `status: "computing"` (job diferido en curso) la query se re-consulta cada
 * 3 s hasta que el resultado exista.
 */
export function useSessionMatch(
  trainingSessionId: number,
  activityId?: number,
  enabled = true,
) {
  return useQuery<MatchDetail>({
    queryKey: intervalKeys.sessionMatch(trainingSessionId, activityId),
    queryFn: () => getSessionMatch(trainingSessionId, activityId),
    enabled: enabled && trainingSessionId > 0,
    staleTime: 30 * 1000,
    refetchInterval: (query) =>
      query.state.data?.status === "computing" ? 3000 : false,
  });
}

/**
 * Dispara el recálculo manual de la comparación (FR-015).
 * Invalida la comparación de la sesión para que la UI muestre "calculando…" y
 * luego el resultado fresco.
 */
export function useRecalculateMatch() {
  const queryClient = useQueryClient();
  return useMutation<
    MatchRecalculateResponse,
    unknown,
    {
      structureId: number;
      trainingSessionId: number;
      input?: IntervalRecalculateInput;
    }
  >({
    mutationKey: ["intervals", "recalculate-match"],
    mutationFn: ({ structureId, input }) => recalculateMatch(structureId, input),
    onSuccess: (_data, { trainingSessionId }) => {
      void queryClient.invalidateQueries({
        queryKey: ["intervals", "session-match", trainingSessionId],
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Instructivo PDF (US3)
// ---------------------------------------------------------------------------

/** Descarga el instructivo PDF de una sesión por marca de dispositivo. */
export function useDownloadInstructivo() {
  return useMutation<
    Blob,
    unknown,
    { trainingSessionId: number; brand: InstructivoBrand }
  >({
    mutationKey: ["intervals", "download-instructivo"],
    mutationFn: ({ trainingSessionId, brand }) =>
      downloadInstructivo(trainingSessionId, brand),
  });
}
