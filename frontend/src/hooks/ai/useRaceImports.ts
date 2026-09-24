/**
 * Hooks TanStack Query para el módulo race-imports (F-UP5).
 *
 * - `useImportParse()`  → mutation POST /imports/parse. Invalida history al éxito.
 * - `useImportDryRun()` → mutation POST /imports/{id}/dry-run.
 * - `useImportCommit()` → mutation POST /imports/{id}/commit. Invalida history + race-runs.
 * - `useImportsHistory({limit, offset, status?})` → query GET /imports/.
 * - `useRaceImport(id)` → query GET /imports/{id} (retomar una carga, feature 045).
 * - `useDiscardRaceImport()` → mutation POST /imports/{id}/discard (feature 045).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  acknowledgeRaceImportCategory,
  addRaceImportRowCorrection,
  commitPendingRaceImport,
  commitRaceImport,
  discardRaceImport,
  dryRunRaceImport,
  getAcknowledgeReasons,
  getRaceImport,
  listRaceImports,
  parseRaceImport,
} from "@/api/raceImports";
import type {
  AcknowledgeInput,
  AcknowledgeReasonsResponse,
  CategoryCompletenessResponse,
  ImportCommitPendingResponse,
  ImportCommitRequest,
  ImportCommitResponse,
  ImportDetail,
  ImportDryRunResponse,
  ImportListResponse,
  ImportParseRequestFields,
  ImportParseResponse,
  ImportsHistoryParams,
  RowCorrectionInput,
} from "@/types/raceImports.types";

export const raceImportsKeys = {
  all: ["race-imports"] as const,
  history: (params: ImportsHistoryParams) =>
    ["race-imports", "history", params] as const,
  detail: (importId: string | number) =>
    ["race-imports", "detail", String(importId)] as const,
};

/** Refresca lo que depende del conteo de cargas en curso / identidades: el
 *  histórico de imports y el resumen del coach (badge de «Cargas e identidades»). */
function invalidateImportCounters(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: raceImportsKeys.all });
  void queryClient.invalidateQueries({ queryKey: ["dashboard", "coach-summary"] });
}

export interface UseImportParseVariables {
  fields: ImportParseRequestFields;
  files: { resultadosPdf: File; generalPdf?: File | null };
}

export function useImportParse() {
  const queryClient = useQueryClient();
  return useMutation<ImportParseResponse, unknown, UseImportParseVariables>({
    mutationKey: ["race-imports", "parse"],
    mutationFn: ({ fields, files }) => parseRaceImport(fields, files),
    onSuccess: () => {
      // Un parse deja una carga «en curso»: sube el conteo del badge.
      invalidateImportCounters(queryClient);
    },
  });
}

export function useImportDryRun() {
  return useMutation<ImportDryRunResponse, unknown, { parseId: string }>({
    mutationKey: ["race-imports", "dry-run"],
    mutationFn: ({ parseId }) => dryRunRaceImport(parseId),
  });
}

export interface UseImportCommitVariables {
  parseId: string;
  body: ImportCommitRequest;
}

export function useImportCommit() {
  const queryClient = useQueryClient();
  return useMutation<ImportCommitResponse, unknown, UseImportCommitVariables>({
    mutationKey: ["race-imports", "commit"],
    mutationFn: ({ parseId, body }) => commitRaceImport(parseId, body),
    onSuccess: () => {
      invalidateImportCounters(queryClient);
      void queryClient.invalidateQueries({ queryKey: ["race-analysis"] });
    },
  });
}

/**
 * `useCommitPendingRaceImport()` → mutation POST /imports/{id}/commit-pending
 * (feature 044, US5). Misma invalidación que `useImportCommit()`: histórico
 * de imports + race-analysis (standings/evolución de la válida recién
 * completada).
 */
export function useCommitPendingRaceImport() {
  const queryClient = useQueryClient();
  return useMutation<
    ImportCommitPendingResponse,
    unknown,
    { parseId: string }
  >({
    mutationKey: ["race-imports", "commit-pending"],
    mutationFn: ({ parseId }) => commitPendingRaceImport(parseId),
    onSuccess: () => {
      invalidateImportCounters(queryClient);
      void queryClient.invalidateQueries({ queryKey: ["race-analysis"] });
    },
  });
}

export function useImportsHistory(params: ImportsHistoryParams = {}) {
  return useQuery<ImportListResponse, unknown>({
    queryKey: raceImportsKeys.history(params),
    queryFn: () => listRaceImports(params),
    staleTime: 30_000,
  });
}

// ---------------------------------------------------------------------------
// Feature 045 (US3) — cargas que se pueden retomar y descartar
// ---------------------------------------------------------------------------

/**
 * `useRaceImport(id)` → query GET /imports/{id}. `id = null` deshabilita la
 * query (el wizard solo la usa cuando llega `?import=<id>` y aún no tiene el
 * parse en memoria).
 *
 * `staleTime: 0` + `refetchOnMount: "always"`: retomar una carga debe leer el
 * estado ACTUAL (pudo confirmarse o descartarse desde otra pestaña), nunca
 * una copia cacheada.
 */
export function useRaceImport(importId: string | number | null) {
  return useQuery<ImportDetail, unknown>({
    queryKey: raceImportsKeys.detail(importId ?? "none"),
    queryFn: () => getRaceImport(importId as string | number),
    enabled: importId != null && importId !== "",
    staleTime: 0,
    refetchOnMount: "always",
    // Un 404 (otra club / id inexistente) no mejora reintentando.
    retry: false,
  });
}

/** `useDiscardRaceImport()` → mutation POST /imports/{id}/discard. */
export function useDiscardRaceImport() {
  const queryClient = useQueryClient();
  return useMutation<ImportDetail, unknown, { importId: string | number }>({
    mutationKey: ["race-imports", "discard"],
    mutationFn: ({ importId }) => discardRaceImport(importId),
    onSuccess: () => {
      invalidateImportCounters(queryClient);
    },
  });
}

// ---------------------------------------------------------------------------
// Feature 044 (US1) — integridad de lectura: correcciones + reconocimiento
// ---------------------------------------------------------------------------

export interface UseAddRowCorrectionVariables {
  parseId: string;
  body: RowCorrectionInput;
}

/** `useAddRowCorrection()` → mutation POST /imports/{id}/corrections. */
export function useAddRowCorrection() {
  return useMutation<
    CategoryCompletenessResponse,
    unknown,
    UseAddRowCorrectionVariables
  >({
    mutationKey: ["race-imports", "corrections"],
    mutationFn: ({ parseId, body }) =>
      addRaceImportRowCorrection(parseId, body),
  });
}

export interface UseAcknowledgeCategoryVariables {
  parseId: string;
  body: AcknowledgeInput;
}

/** `useAcknowledgeCategory()` → mutation POST /imports/{id}/acknowledge. */
export function useAcknowledgeCategory() {
  return useMutation<
    CategoryCompletenessResponse,
    unknown,
    UseAcknowledgeCategoryVariables
  >({
    mutationKey: ["race-imports", "acknowledge"],
    mutationFn: ({ parseId, body }) =>
      acknowledgeRaceImportCategory(parseId, body),
  });
}

/** `useAcknowledgeReasons()` → query GET /imports/acknowledge-reasons. */
export function useAcknowledgeReasons() {
  return useQuery<AcknowledgeReasonsResponse, unknown>({
    queryKey: ["race-imports", "acknowledge-reasons"],
    queryFn: () => getAcknowledgeReasons(),
    staleTime: 5 * 60_000,
  });
}
