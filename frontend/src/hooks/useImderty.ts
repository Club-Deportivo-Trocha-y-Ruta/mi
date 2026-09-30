/**
 * useImderty — hooks TanStack Query de la planilla mensual de asistencia
 * IMDERTY (feature 047). Todas las query keys viven bajo `["imderty", …]`;
 * ninguna se agrega a `lib/persistAllowList.ts` (default-deny) porque el
 * perfil, los datos sensibles y la planilla llevan datos de un menor que no
 * deben sobrevivir en caché entre sesiones del navegador.
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  createBarrio,
  createSensitiveAuthorization,
  downloadImdertySheet,
  getBarrios,
  getClubImdertySettings,
  getImdertyProfile,
  getImdertySheetReadiness,
  getSensitiveData,
  updateBarrio,
  updateClubImdertySettings,
  updateImdertyProfile,
  updatePrimaryContact,
  updateSensitiveData,
  withdrawSensitiveAuthorization,
} from "@/api/imderty";
import type {
  BarrioCreateValues,
  BarrioUpdateValues,
  ClubImdertySettingsUpdateValues,
  ImdertyProfileUpdateValues,
  ImdertySheetRequestValues,
  PrimaryContactUpdateValues,
  SensitiveAuthorizationCreateValues,
  SensitiveDataUpdateValues,
} from "@/schemas/imderty";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const imdertyKeys = {
  all: ["imderty"] as const,
  profile: (athleteId: number) => ["imderty", "profile", athleteId] as const,
  sensitiveData: (athleteId: number) => ["imderty", "sensitive-data", athleteId] as const,
  barrios: (includeInactive: boolean) => ["imderty", "barrios", includeInactive] as const,
  clubSettings: (clubId: number) => ["imderty", "club-settings", clubId] as const,
  readiness: (clubId: number, from: string, to: string) =>
    ["imderty", "readiness", clubId, from, to] as const,
};

function invalidateProfileDependents(queryClient: QueryClient, athleteId: number) {
  void queryClient.invalidateQueries({ queryKey: imdertyKeys.profile(athleteId) });
}

// ---------------------------------------------------------------------------
// Perfil IMDERTY del atleta
// ---------------------------------------------------------------------------

export function useImdertyProfile(athleteId: number, enabled = true) {
  return useQuery({
    queryKey: imdertyKeys.profile(athleteId),
    queryFn: () => getImdertyProfile(athleteId),
    enabled: enabled && Number.isFinite(athleteId) && athleteId > 0,
  });
}

export function useUpdateImdertyProfile(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ImdertyProfileUpdateValues) => updateImdertyProfile(athleteId, payload),
    onSuccess: () => invalidateProfileDependents(queryClient, athleteId),
  });
}

export function useUpdatePrimaryContact(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PrimaryContactUpdateValues) => updatePrimaryContact(athleteId, payload),
    onSuccess: () => invalidateProfileDependents(queryClient, athleteId),
  });
}

// ---------------------------------------------------------------------------
// Datos sensibles
// ---------------------------------------------------------------------------

export function useCreateSensitiveAuthorization(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SensitiveAuthorizationCreateValues) =>
      createSensitiveAuthorization(athleteId, payload),
    onSuccess: () => {
      invalidateProfileDependents(queryClient, athleteId);
      void queryClient.invalidateQueries({ queryKey: imdertyKeys.sensitiveData(athleteId) });
    },
  });
}

export function useWithdrawSensitiveAuthorization(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => withdrawSensitiveAuthorization(athleteId),
    onSuccess: () => {
      // FR-007: el backend borró los tres valores; se descartan también de la
      // caché en memoria (no basta con invalidar: el dato viejo quedaría
      // retenido hasta el gcTime y el refetch respondería 404).
      queryClient.removeQueries({ queryKey: imdertyKeys.sensitiveData(athleteId) });
      invalidateProfileDependents(queryClient, athleteId);
    },
  });
}

/** Habilitar solo cuando hay autorización activa (el backend responde 404 si no). */
export function useSensitiveData(athleteId: number, enabled: boolean) {
  return useQuery({
    queryKey: imdertyKeys.sensitiveData(athleteId),
    queryFn: () => getSensitiveData(athleteId),
    enabled: enabled && Number.isFinite(athleteId) && athleteId > 0,
    retry: false,
  });
}

export function useUpdateSensitiveData(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SensitiveDataUpdateValues) => updateSensitiveData(athleteId, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(imdertyKeys.sensitiveData(athleteId), data);
    },
  });
}

// ---------------------------------------------------------------------------
// Catálogo de barrios
// ---------------------------------------------------------------------------

export function useBarrios(includeInactive = false) {
  return useQuery({
    queryKey: imdertyKeys.barrios(includeInactive),
    queryFn: () => getBarrios(includeInactive),
  });
}

export function useCreateBarrio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BarrioCreateValues) => createBarrio(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["imderty", "barrios"] });
    },
  });
}

export function useUpdateBarrio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ barrioId, payload }: { barrioId: number; payload: BarrioUpdateValues }) =>
      updateBarrio(barrioId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["imderty", "barrios"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Configuración IMDERTY del club
// ---------------------------------------------------------------------------

export function useClubImdertySettings(clubId: number, enabled = true) {
  return useQuery({
    queryKey: imdertyKeys.clubSettings(clubId),
    queryFn: () => getClubImdertySettings(clubId),
    enabled: enabled && Number.isFinite(clubId) && clubId > 0,
  });
}

export function useUpdateClubImdertySettings(clubId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ClubImdertySettingsUpdateValues) => updateClubImdertySettings(clubId, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(imdertyKeys.clubSettings(clubId), data);
    },
  });
}

// ---------------------------------------------------------------------------
// Planilla: readiness + generación
// ---------------------------------------------------------------------------

export function useImdertySheetReadiness(
  clubId: number,
  from: string | null,
  to: string | null,
) {
  return useQuery({
    queryKey: imdertyKeys.readiness(clubId, from ?? "", to ?? ""),
    queryFn: () => getImdertySheetReadiness(clubId, from as string, to as string),
    enabled: Number.isFinite(clubId) && clubId > 0 && Boolean(from) && Boolean(to),
  });
}

export function useDownloadImdertySheet(clubId: number) {
  return useMutation({
    mutationFn: (payload: ImdertySheetRequestValues) => downloadImdertySheet(clubId, payload),
  });
}
