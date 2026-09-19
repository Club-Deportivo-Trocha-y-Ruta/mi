/**
 * Hooks TanStack Query para el módulo race-imports (F-UP5).
 *
 * - `useImportParse()`  → mutation POST /imports/parse. Invalida history al éxito.
 * - `useImportDryRun()` → mutation POST /imports/{id}/dry-run.
 * - `useImportCommit()` → mutation POST /imports/{id}/commit. Invalida history + race-runs.
 * - `useImportsHistory({limit, offset, status?})` → query GET /imports/.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  acknowledgeRaceImportCategory,
  addRaceImportRowCorrection,
  commitRaceImport,
  dryRunRaceImport,
  getAcknowledgeReasons,
  listRaceImports,
  parseRaceImport,
} from "@/api/raceImports";
import type {
  AcknowledgeInput,
  AcknowledgeReasonsResponse,
  CategoryCompletenessResponse,
  ImportCommitRequest,
  ImportCommitResponse,
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
};

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
      void queryClient.invalidateQueries({ queryKey: raceImportsKeys.all });
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
      void queryClient.invalidateQueries({ queryKey: raceImportsKeys.all });
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
