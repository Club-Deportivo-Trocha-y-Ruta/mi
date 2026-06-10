/**
 * Hooks TanStack Query del módulo race roster (convocatoria).
 *
 * Hooks exportados:
 *   - `useRaceRoster(raceEventId)`        → GET roster con reconciliación
 *   - `useCreateRosterEntry()`            → mutation POST (agregar atleta)
 *   - `useUpdateRosterEntry()`            → mutation PATCH (cambiar estado/nota)
 *   - `useDeleteRosterEntry()`            → mutation DELETE (retirar)
 *
 * Query keys:
 *   - `rosterKeys.byEvent(id)` → invalida al mutar. Se exporta para tests.
 *
 * Invalidaciones en cada mutación:
 *   1. El roster propio → siempre.
 *   2. `invalidatePaired({ raceEventId })` → competitors + results + standings
 *      + raceAnalysis del mismo evento (un cambio en convocados puede
 *      afectar el estado de enlace de corredores / análisis IA).
 *   3. La lista de race-events → para que `conditions_completeness` y
 *      otros derived fields reflejen el nuevo estado.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  createRosterEntry,
  deleteRosterEntry,
  getRaceRoster,
  updateRosterEntry,
} from "@/api/raceRoster";
import { useAuthStore } from "@/store/auth.store";
import { invalidatePaired } from "@/hooks/race/invalidation";
import { raceEventKeys } from "@/hooks/race/useRaceEvents";
import type {
  RaceRosterResponse,
  RosterEntry,
  RosterEntryCreate,
  RosterEntryUpdate,
} from "@/types/raceRoster.types";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const rosterKeys = {
  /** Raíz del árbol — invalida todos los rosters. */
  all: ["roster"] as const,

  /** Roster de un evento concreto. */
  byEvent: (raceEventId: number) => ["roster", "event", raceEventId] as const,
} as const;

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * Roster de convocados para una válida con reconciliación.
 *
 * staleTime de 2 min: el roster cambia con mutaciones frecuentes en día
 * de competencia (coach marca confirmados/retirados desde el campo).
 */
export function useRaceRoster(raceEventId: number | null | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const enabled =
    !!accessToken && raceEventId != null && raceEventId > 0;

  return useQuery<RaceRosterResponse, unknown>({
    queryKey: rosterKeys.byEvent(raceEventId ?? -1),
    queryFn: ({ signal }) => getRaceRoster(raceEventId as number, { signal }),
    enabled,
    staleTime: 2 * 60_000,
  });
}

// ---------------------------------------------------------------------------
// Mutations — helpers internos de invalidación
// ---------------------------------------------------------------------------

function useRosterInvalidator() {
  const queryClient = useQueryClient();

  return (raceEventId: number) => {
    void queryClient.invalidateQueries({
      queryKey: rosterKeys.byEvent(raceEventId),
    });
    invalidatePaired(queryClient, { raceEventId });
    void queryClient.invalidateQueries({
      queryKey: raceEventKeys.lists(),
    });
    void queryClient.invalidateQueries({
      queryKey: raceEventKeys.detail(raceEventId),
    });
  };
}

// ---------------------------------------------------------------------------
// Mutation: create
// ---------------------------------------------------------------------------

export interface UseCreateRosterEntryVariables {
  raceEventId: number;
  body: RosterEntryCreate;
}

/**
 * Mutation para agregar un atleta del club al roster de convocados.
 * RBAC: coach + admin.
 *
 * 409 → atleta ya en el roster (el componente muestra el error inline).
 * 422 → athlete_id no pertenece al club.
 */
export function useCreateRosterEntry() {
  const invalidate = useRosterInvalidator();

  return useMutation<RosterEntry, unknown, UseCreateRosterEntryVariables>({
    mutationKey: ["roster", "create"],
    mutationFn: ({ raceEventId, body }) =>
      createRosterEntry(raceEventId, body),
    onSuccess: (_data, { raceEventId }) => {
      invalidate(raceEventId);
    },
  });
}

// ---------------------------------------------------------------------------
// Mutation: update
// ---------------------------------------------------------------------------

export interface UseUpdateRosterEntryVariables {
  raceEventId: number;
  entryId: number;
  body: RosterEntryUpdate;
}

/**
 * Mutation para cambiar el estado o la nota de un convocado.
 * RBAC: coach + admin.
 */
export function useUpdateRosterEntry() {
  const queryClient = useQueryClient();
  const invalidate = useRosterInvalidator();

  return useMutation<
    RosterEntry,
    unknown,
    UseUpdateRosterEntryVariables,
    { previous?: RaceRosterResponse }
  >({
    mutationKey: ["roster", "update"],
    mutationFn: ({ raceEventId, entryId, body }) =>
      updateRosterEntry(raceEventId, entryId, body),
    // Feature 012, US3: optimistic — en día de competencia el coach marca
    // confirmado/retirado desde el campo y lo ve al instante. Si el backend
    // rechaza, revertimos y mostramos el error (getRosterErrorMessage).
    onMutate: async ({ raceEventId, entryId, body }) => {
      const key = rosterKeys.byEvent(raceEventId);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<RaceRosterResponse>(key);
      if (previous) {
        queryClient.setQueryData<RaceRosterResponse>(key, {
          ...previous,
          entries: previous.entries.map((e) =>
            e.id === entryId
              ? {
                  ...e,
                  ...(body.status !== undefined
                    ? { status: body.status }
                    : {}),
                  ...(body.note !== undefined ? { note: body.note } : {}),
                }
              : e,
          ),
        });
      }
      return { previous };
    },
    onError: (_err, { raceEventId }, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          rosterKeys.byEvent(raceEventId),
          context.previous,
        );
      }
    },
    // Reconcilia con el servidor tras éxito o error (la fuente de verdad).
    onSettled: (_data, _err, { raceEventId }) => {
      invalidate(raceEventId);
    },
  });
}

// ---------------------------------------------------------------------------
// Mutation: delete
// ---------------------------------------------------------------------------

export interface UseDeleteRosterEntryVariables {
  raceEventId: number;
  entryId: number;
}

/**
 * Mutation para eliminar una entrada del roster.
 * RBAC: coach + admin.
 */
export function useDeleteRosterEntry() {
  const invalidate = useRosterInvalidator();

  return useMutation<void, unknown, UseDeleteRosterEntryVariables>({
    mutationKey: ["roster", "delete"],
    mutationFn: ({ raceEventId, entryId }) =>
      deleteRosterEntry(raceEventId, entryId),
    onSuccess: (_data, { raceEventId }) => {
      invalidate(raceEventId);
    },
  });
}

// ---------------------------------------------------------------------------
// Error message helper
// ---------------------------------------------------------------------------

/**
 * Extrae mensaje legible del error axios para mostrar en toast/banner.
 * Mapea los status codes documentados del endpoint de roster.
 */
export function getRosterErrorMessage(
  err: unknown,
  fallback = "Error inesperado. Intenta de nuevo.",
): string {
  if (typeof err === "object" && err !== null) {
    const e = err as {
      response?: { data?: { detail?: unknown }; status?: number };
      message?: string;
    };
    const status = e.response?.status;
    if (status === 409) {
      return "Este atleta ya está en la convocatoria de esta válida.";
    }
    if (status === 403) {
      return "Sin permiso para modificar la convocatoria.";
    }
    if (status === 404) {
      return "Entrada de convocatoria no encontrada.";
    }
    if (status === 422) {
      return "El atleta no pertenece al club o los datos son inválidos.";
    }
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (e.message && !/status code \d+/i.test(e.message)) {
      return e.message;
    }
  }
  return fallback;
}
