/**
 * Hooks TanStack Query del módulo Fuerza y Acondicionamiento (feature 021).
 * Mirroring de convenciones de `hooks/technique/useTechnique.ts` (feature 018).
 *
 * Query-key factory + catálogo (US1) + bloques/adjunto a sesión (US2) +
 * progreso por atleta (US4).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addStrengthProgress,
  archiveStrengthBlock,
  attachStrengthBlock,
  createStrengthBlock,
  detachStrengthBlock,
  getAthleteStrengthProgress,
  getSessionStrengthBlocks,
  getStrengthBlock,
  getStrengthExercise,
  listStrengthBlocks,
  listStrengthExercises,
  updateStrengthBlock,
} from "@/api/strength";
import type {
  StrengthAthleteProgress,
  StrengthAttachOut,
  StrengthBlockList,
  StrengthBlockListFilters,
  StrengthBlockOut,
  StrengthBlockSaveInput,
  StrengthCatalogFilters,
  StrengthCatalogList,
  StrengthExerciseDetail,
  StrengthProgressInput,
  StrengthProgressOut,
  StrengthSessionBlocks,
} from "@/schemas/strength.schemas";

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const strengthKeys = {
  all: ["strength"] as const,
  exercises: (filters?: unknown) =>
    ["strength", "exercises", filters ?? {}] as const,
  exercise: (id: number) => ["strength", "exercise", id] as const,
  blocks: (filters?: unknown) =>
    ["strength", "blocks", filters ?? {}] as const,
  block: (id: number) => ["strength", "block", id] as const,
  sessionBlocks: (trainingSessionId: number) =>
    ["strength", "session-blocks", trainingSessionId] as const,
  athleteProgress: (athleteId: number) =>
    ["strength", "athlete-progress", athleteId] as const,
};

// ---------------------------------------------------------------------------
// Catalog & discovery (US1)
// ---------------------------------------------------------------------------

/**
 * Lista y filtra el catálogo de ejercicios de fuerza.
 * staleTime largo: el catálogo cambia raramente y los reads son la mayoría.
 */
export function useStrengthCatalog(filters?: StrengthCatalogFilters) {
  return useQuery<StrengthCatalogList>({
    queryKey: strengthKeys.exercises(filters),
    queryFn: () => listStrengthExercises(filters),
    staleTime: 5 * 60 * 1000, // 5 min — catálogo estable
    placeholderData: (prev) => prev, // evita parpadeo al cambiar filtros
  });
}

/** Detalle de un ejercicio de fuerza por id. */
export function useStrengthExercise(id: number, enabled = true) {
  return useQuery<StrengthExerciseDetail>({
    queryKey: strengthKeys.exercise(id),
    queryFn: () => getStrengthExercise(id),
    enabled: enabled && id > 0,
    staleTime: 5 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Blocks (US2)
// ---------------------------------------------------------------------------

/** Detalle de un bloque de fuerza por id. */
export function useStrengthBlock(id: number, enabled = true) {
  return useQuery<StrengthBlockOut>({
    queryKey: strengthKeys.block(id),
    queryFn: () => getStrengthBlock(id),
    enabled: enabled && id > 0,
    staleTime: 2 * 60 * 1000,
  });
}

/** Lista los bloques de fuerza del club del coach autenticado. */
export function useStrengthBlocks(filters?: StrengthBlockListFilters) {
  return useQuery<StrengthBlockList>({
    queryKey: strengthKeys.blocks(filters),
    queryFn: () => listStrengthBlocks(filters),
    staleTime: 2 * 60 * 1000,
    placeholderData: (prev) => prev,
  });
}

/**
 * Crea o reemplaza un bloque de fuerza (create/update unificados).
 * Sin `id` → POST /blocks; con `id` → PUT /blocks/{id}.
 * Invalida la lista de bloques y actualiza/invalida el detalle en caché.
 */
export function useSaveBlock() {
  const queryClient = useQueryClient();
  return useMutation<
    StrengthBlockOut,
    unknown,
    { id?: number; input: StrengthBlockSaveInput }
  >({
    mutationKey: ["strength", "save-block"],
    mutationFn: ({ id, input }) =>
      id ? updateStrengthBlock(id, input) : createStrengthBlock(input),
    onSuccess: (data) => {
      queryClient.setQueryData(strengthKeys.block(data.id), data);
      void queryClient.invalidateQueries({
        queryKey: ["strength", "blocks"],
      });
    },
  });
}

/**
 * Archiva o desarchiva un bloque de fuerza.
 * Invalida la lista (el default `include_archived=false` puede excluirlo) y
 * actualiza el detalle en caché.
 */
export function useArchiveBlock() {
  const queryClient = useQueryClient();
  return useMutation<
    StrengthBlockOut,
    unknown,
    { id: number; isArchived: boolean }
  >({
    mutationKey: ["strength", "archive-block"],
    mutationFn: ({ id, isArchived }) => archiveStrengthBlock(id, isArchived),
    onSuccess: (data) => {
      queryClient.setQueryData(strengthKeys.block(data.id), data);
      void queryClient.invalidateQueries({
        queryKey: ["strength", "blocks"],
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Session attachment (US2)
// ---------------------------------------------------------------------------

/**
 * Adjunta un bloque de fuerza a una sesión de entrenamiento.
 * Invalida los bloques de la sesión y el detalle del bloque (para reflejar
 * el nuevo vínculo en cualquier vista que lo muestre).
 */
export function useAttachBlock() {
  const queryClient = useQueryClient();
  return useMutation<
    StrengthAttachOut,
    unknown,
    { blockId: number; trainingSessionId: number }
  >({
    mutationKey: ["strength", "attach-block"],
    mutationFn: ({ blockId, trainingSessionId }) =>
      attachStrengthBlock(blockId, trainingSessionId),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({
        queryKey: strengthKeys.sessionBlocks(data.training_session_id),
      });
      void queryClient.invalidateQueries({
        queryKey: strengthKeys.block(data.block_id),
      });
    },
  });
}

/** Desadjunta un bloque de fuerza de una sesión. Invalida los bloques de la sesión. */
export function useDetachBlock() {
  const queryClient = useQueryClient();
  return useMutation<
    void,
    unknown,
    { blockId: number; trainingSessionId: number }
  >({
    mutationKey: ["strength", "detach-block"],
    mutationFn: ({ blockId, trainingSessionId }) =>
      detachStrengthBlock(blockId, trainingSessionId),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: strengthKeys.sessionBlocks(variables.trainingSessionId),
      });
    },
  });
}

/** Bloques de fuerza adjuntos a una sesión (para renderizar el plan de sesión). */
export function useSessionBlocks(trainingSessionId: number, enabled = true) {
  return useQuery<StrengthSessionBlocks>({
    queryKey: strengthKeys.sessionBlocks(trainingSessionId),
    queryFn: () => getSessionStrengthBlocks(trainingSessionId),
    enabled: enabled && trainingSessionId > 0,
    staleTime: 2 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Per-athlete progress notes (US4)
// ---------------------------------------------------------------------------

/** Progreso de fuerza de un atleta — coach/admin only. */
export function useAthleteStrengthProgress(athleteId: number, enabled = true) {
  return useQuery<StrengthAthleteProgress>({
    queryKey: strengthKeys.athleteProgress(athleteId),
    queryFn: () => getAthleteStrengthProgress(athleteId),
    enabled: enabled && athleteId > 0,
    staleTime: 2 * 60 * 1000,
  });
}

/** Registra una nota de progreso de fuerza para un atleta (append-only). */
export function useAddStrengthProgress(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation<StrengthProgressOut, unknown, StrengthProgressInput>({
    mutationKey: ["strength", "add-progress", athleteId],
    mutationFn: (input) => addStrengthProgress(athleteId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: strengthKeys.athleteProgress(athleteId),
      });
    },
  });
}
