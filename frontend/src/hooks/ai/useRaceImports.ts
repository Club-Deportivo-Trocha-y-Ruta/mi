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
  commitRaceImport,
  dryRunRaceImport,
  listRaceImports,
  parseRaceImport,
} from "@/api/raceImports";
import type {
  ImportCommitRequest,
  ImportCommitResponse,
  ImportDryRunResponse,
  ImportListResponse,
  ImportParseRequestFields,
  ImportParseResponse,
  ImportsHistoryParams,
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
