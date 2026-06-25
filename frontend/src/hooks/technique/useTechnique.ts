import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addProgress,
  assembleSession,
  createExercise,
  getAthleteProgress,
  getExercise,
  getSessionExercises,
  listExercises,
  listMaterials,
  listSkills,
  setVisibility,
  updateExercise,
} from "@/api/technique";
import type {
  AssembleSessionInput,
  AssembleSessionResult,
  AthleteProgress,
  CatalogFilters,
  CatalogList,
  ExerciseCreateInput,
  ExerciseDetail,
  ExerciseUpdateInput,
  MaterialRead,
  ProgressInput,
  SkillProgressEvent,
  SkillRead,
  TechniqueSessionItem,
} from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const techniqueKeys = {
  all: ["technique"] as const,
  exercises: (filters?: CatalogFilters) =>
    ["technique", "exercises", filters ?? {}] as const,
  exercise: (id: number) => ["technique", "exercise", id] as const,
  skills: () => ["technique", "skills"] as const,
  materials: () => ["technique", "materials"] as const,
  sessionExercises: (sessionId: number) =>
    ["technique", "session-exercises", sessionId] as const,
  athleteProgress: (athleteId: number) =>
    ["technique", "athlete-progress", athleteId] as const,
};

// ---------------------------------------------------------------------------
// Catalog & discovery (US1)
// ---------------------------------------------------------------------------

/**
 * Lista y filtra el catálogo de ejercicios.
 * staleTime largo: el catálogo cambia raramente y los reads son la mayoría.
 */
export function useTechniqueCatalog(filters?: CatalogFilters) {
  return useQuery<CatalogList>({
    queryKey: techniqueKeys.exercises(filters),
    queryFn: () => listExercises(filters),
    staleTime: 5 * 60 * 1000, // 5 min — catálogo estable
    placeholderData: (prev) => prev, // evita parpadeo al cambiar filtros
  });
}

/** Detalle de un ejercicio por id. */
export function useTechniqueExercise(id: number, enabled = true) {
  return useQuery<ExerciseDetail>({
    queryKey: techniqueKeys.exercise(id),
    queryFn: () => getExercise(id),
    enabled: enabled && id > 0,
    staleTime: 5 * 60 * 1000,
  });
}

/** Taxonomía de habilidades (para filtros y formularios). */
export function useSkills() {
  return useQuery<SkillRead[]>({
    queryKey: techniqueKeys.skills(),
    queryFn: listSkills,
    staleTime: Infinity, // la taxonomía seedeada no cambia en runtime
  });
}

/** Listado de materiales (para filtros y formularios). */
export function useMaterials() {
  return useQuery<MaterialRead[]>({
    queryKey: techniqueKeys.materials(),
    queryFn: listMaterials,
    staleTime: Infinity,
  });
}

// ---------------------------------------------------------------------------
// Session assembly (US3)
// ---------------------------------------------------------------------------

/**
 * Mutación para armar una sesión de entrenamiento técnico.
 * onSuccess: no invalida el catálogo (la sesión se refleja en el módulo de
 * Training Sessions, no en el catálogo de ejercicios).
 */
export function useAssembleTechniqueSession() {
  return useMutation<AssembleSessionResult, unknown, AssembleSessionInput>({
    mutationKey: ["technique", "assemble-session"],
    mutationFn: (input) => assembleSession(input),
  });
}

/** Ejercicios de una sesión guardada (US3 / FR-013). */
export function useSessionExercises(sessionId: number, enabled = true) {
  return useQuery<TechniqueSessionItem[]>({
    queryKey: techniqueKeys.sessionExercises(sessionId),
    queryFn: () => getSessionExercises(sessionId),
    enabled: enabled && sessionId > 0,
    staleTime: 5 * 60 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Per-athlete skill progress (US4)
// ---------------------------------------------------------------------------

/** Progreso de habilidades de un atleta — coach/admin only. */
export function useAthleteSkillProgress(athleteId: number, enabled = true) {
  return useQuery<AthleteProgress>({
    queryKey: techniqueKeys.athleteProgress(athleteId),
    queryFn: () => getAthleteProgress(athleteId),
    enabled: enabled && athleteId > 0,
    staleTime: 2 * 60 * 1000,
  });
}

/** Registra un evento de progreso para un atleta. */
export function useAddProgress(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation<SkillProgressEvent, unknown, ProgressInput>({
    mutationKey: ["technique", "add-progress", athleteId],
    mutationFn: (input) => addProgress(athleteId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: techniqueKeys.athleteProgress(athleteId),
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Curation (US5)
// ---------------------------------------------------------------------------

/** Crea un ejercicio personalizado. Invalida el catálogo al terminar. */
export function useCreateExercise() {
  const queryClient = useQueryClient();
  return useMutation<ExerciseDetail, unknown, ExerciseCreateInput>({
    mutationKey: ["technique", "create-exercise"],
    mutationFn: (input) => createExercise(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["technique", "exercises"],
      });
    },
  });
}

/** Edita un ejercicio (incluyendo seedeados). Invalida catálogo y detalle. */
export function useUpdateExercise() {
  const queryClient = useQueryClient();
  return useMutation<
    ExerciseDetail,
    unknown,
    { id: number; input: ExerciseUpdateInput }
  >({
    mutationKey: ["technique", "update-exercise"],
    mutationFn: ({ id, input }) => updateExercise(id, input),
    onSuccess: (data) => {
      queryClient.setQueryData(techniqueKeys.exercise(data.id), data);
      void queryClient.invalidateQueries({
        queryKey: ["technique", "exercises"],
      });
    },
  });
}

/**
 * Oculta o muestra un ejercicio.
 * Invalida el catálogo y actualiza optimistamente la caché del detalle.
 */
export function useSetVisibility() {
  const queryClient = useQueryClient();
  return useMutation<
    { id: number; is_hidden: boolean },
    unknown,
    { id: number; isHidden: boolean }
  >({
    mutationKey: ["technique", "set-visibility"],
    mutationFn: ({ id, isHidden }) => setVisibility(id, isHidden),
    onSuccess: (data) => {
      // Actualiza el detalle en caché si existe
      queryClient.setQueryData<ExerciseDetail>(
        techniqueKeys.exercise(data.id),
        (prev) => (prev ? { ...prev, is_hidden: data.is_hidden } : prev),
      );
      // Invalida listas (los filtros de include_hidden pueden afectar resultados)
      void queryClient.invalidateQueries({
        queryKey: ["technique", "exercises"],
      });
    },
  });
}
