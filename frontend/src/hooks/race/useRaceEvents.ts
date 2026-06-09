/**
 * Hooks TanStack Query del módulo race-events — CRUD de eventos (CF3).
 *
 * Hooks exportados:
 *   - `useRaceEventsList(filters)`  → GET /race-events/ con filtros opcionales
 *   - `useRaceEvent(id)`            → ítem individual filtrado desde la lista
 *   - `useCreateRaceEvent()`        → mutation POST /race-events/
 *   - `useUpdateRaceEvent()`        → mutation PATCH /race-events/{id}
 *   - `useDeleteRaceEvent()`        → mutation DELETE /race-events/{id} (admin)
 *
 * Invalidaciones cruzadas:
 *   - `raceEventKeys.lists()` → afecta todas las variantes de lista (filtros)
 *   - `raceEventKeys.detail(id)` → afecta el detalle específico del evento
 *   - `["calendar", "race-events", "available-for-calendar"]` →
 *       useAvailableRaceEvents en hooks/calendar/useAvailableRaceEvents.ts
 *       (el dropdown de EventForm depende de qué eventos están disponibles)
 *
 * El toast de éxito/error vive en el componente consumidor (patrón establecido
 * en useUnlinkedCompetitors.ts / useUpdateRaceEventConditions.ts).
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { invalidatePaired } from "@/hooks/race/invalidation";

import {
  createRaceEvent,
  deleteRaceEvent,
  getRaceEvent,
  linkCalendarEvent,
  listRaceEvents,
  updateRaceEvent,
} from "@/api/raceEvents";
import { useAuthStore } from "@/store/auth.store";
import type {
  RaceEventCalendarLinkBody,
  RaceEventCalendarLinkResponse,
  RaceEventCreate,
  RaceEventListFilters,
  RaceEventListResponse,
  RaceEventRead,
  RaceEventUpdate,
} from "@/types/raceEvents.types";

// ---------------------------------------------------------------------------
// Query keys — exportadas para que los tests y componentes puedan hacer
// queryClient.invalidateQueries/getQueryData sin magic strings.
// ---------------------------------------------------------------------------

export const raceEventKeys = {
  /** Raíz del árbol — invalida todo el módulo race-events. */
  all: ["raceEvents"] as const,

  /** Todas las variantes de lista (con y sin filtros). */
  lists: () => ["raceEvents", "list"] as const,

  /** Lista con filtros específicos. */
  list: (filters: RaceEventListFilters) =>
    ["raceEvents", "list", filters] as const,

  /** Detalle de un evento concreto. */
  detail: (id: number) => ["raceEvents", "detail", id] as const,
} as const;

/**
 * Clave de las queries de "race-events disponibles para calendario" que usa
 * `useAvailableRaceEvents` en hooks/calendar/useAvailableRaceEvents.ts.
 *
 * Se invalida al crear/actualizar/eliminar un evento para que el dropdown
 * de EventForm refleje el estado actual.
 *
 * Nota: la key incluye el `season` como último elemento. Invalidar con
 * el prefijo `["calendar", "race-events", "available-for-calendar"]`
 * cubre todas las temporadas en caché.
 */
const CALENDAR_AVAILABLE_ROOT = [
  "calendar",
  "race-events",
  "available-for-calendar",
] as const;

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

/**
 * Lista paginada de eventos de carrera con filtros opcionales.
 *
 * `staleTime` de 5 min mitiga el cold start de Render Free (primer
 * request tras 15 min de inactividad tarda ~50 s). Los filtros forman
 * parte de la query key para que cada combinación tenga su caché.
 */
export function useRaceEventsList(filters: RaceEventListFilters = {}) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery<RaceEventListResponse, unknown>({
    queryKey: raceEventKeys.list(filters),
    queryFn: () => listRaceEvents(filters),
    enabled: !!accessToken,
    staleTime: 5 * 60_000,
  });
}

/**
 * Evento de carrera individual con datos completos (`RaceEventRead`).
 *
 * Consume el endpoint GET /race-events/{id} directamente — retorna el
 * objeto completo incluyendo condiciones logísticas (climate, temperature_c,
 * surface_condition, altitude_msnm, weather_notes).
 *
 * Key: `raceEventKeys.detail(id)` → se invalida al actualizar el evento.
 * Retorna `undefined` mientras carga; lanza error TanStack si falla (404 incluido).
 */
export function useRaceEvent(id: number | null | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery<RaceEventRead, unknown>({
    queryKey: raceEventKeys.detail(id ?? -1),
    queryFn: ({ signal }) => getRaceEvent(id as number, { signal }),
    enabled: !!accessToken && id != null && id > 0,
    staleTime: 5 * 60_000,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export interface UseCreateRaceEventVariables {
  body: RaceEventCreate;
}

/**
 * Mutation para crear un nuevo evento de carrera.
 * RBAC: coach + admin.
 *
 * On success invalida:
 *   - toda la lista de eventos (todas las combinaciones de filtros)
 *   - el dropdown de "disponibles para calendario" (todas las temporadas)
 */
export function useCreateRaceEvent() {
  const queryClient = useQueryClient();

  return useMutation<RaceEventRead, unknown, UseCreateRaceEventVariables>({
    mutationKey: ["raceEvents", "create"],
    mutationFn: ({ body }) => createRaceEvent(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: raceEventKeys.lists(),
      });
      void queryClient.invalidateQueries({
        queryKey: CALENDAR_AVAILABLE_ROOT,
      });
    },
  });
}

export interface UseUpdateRaceEventVariables {
  id: number;
  body: RaceEventUpdate;
}

/**
 * Mutation para actualizar campos básicos de un evento de carrera.
 * RBAC: coach + admin.
 *
 * On success invalida:
 *   - la lista completa (el nombre/fecha/estado puede cambiar los filtros)
 *   - el detalle específico del evento actualizado
 *   - el dropdown de "disponibles para calendario" (el status puede cambiar)
 */
export function useUpdateRaceEvent() {
  const queryClient = useQueryClient();

  return useMutation<RaceEventRead, unknown, UseUpdateRaceEventVariables>({
    mutationKey: ["raceEvents", "update"],
    mutationFn: ({ id, body }) => updateRaceEvent(id, body),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: raceEventKeys.lists(),
      });
      void queryClient.invalidateQueries({
        queryKey: raceEventKeys.detail(variables.id),
      });
      void queryClient.invalidateQueries({
        queryKey: CALENDAR_AVAILABLE_ROOT,
      });
    },
  });
}

export interface UseDeleteRaceEventVariables {
  id: number;
}

/**
 * Mutation para eliminar un evento de carrera.
 * RBAC: admin only.
 *
 * El backend retorna 409 si el evento tiene race_results o calendar_event
 * asociados. El componente debe manejar este error con confirmación al usuario
 * (ej: "Este evento tiene resultados importados. ¿Deseas eliminarlo de todas formas?").
 *
 * On success invalida:
 *   - la lista completa
 *   - el dropdown de "disponibles para calendario"
 *   (el detalle ya no existe — no tiene sentido invalidarlo)
 */
export function useDeleteRaceEvent() {
  const queryClient = useQueryClient();

  return useMutation<void, unknown, UseDeleteRaceEventVariables>({
    mutationKey: ["raceEvents", "delete"],
    mutationFn: ({ id }) => deleteRaceEvent(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: raceEventKeys.lists(),
      });
      void queryClient.invalidateQueries({
        queryKey: CALENDAR_AVAILABLE_ROOT,
      });
    },
  });
}

export interface UseLinkCalendarEventVariables {
  raceEventId: number;
  body: RaceEventCalendarLinkBody;
}

/**
 * Mutation para asociar un `calendar_event` existente a una válida.
 * `POST /api/race-analysis/race-events/{id}/calendar-link`
 * RBAC: coach + admin.
 *
 * Casos de uso:
 *   - La válida fue creada con `create_calendar_event=false` y el coach
 *     posteriormente quiere vincularla a un calendar_event existente.
 *   - La validación 1:1 la hace el backend (409 si ya vinculada).
 *
 * On success invalida:
 *   - `raceEventKeys.detail(id)` → refresca `has_calendar_event` en el header
 *   - `raceEventKeys.lists()` → actualiza la lista (badge "En calendario")
 *   - El árbol de calendario completo vía `invalidatePaired({ includeCalendar: true })`
 */
export function useLinkCalendarEvent() {
  const queryClient = useQueryClient();

  return useMutation<
    RaceEventCalendarLinkResponse,
    unknown,
    UseLinkCalendarEventVariables
  >({
    mutationKey: ["raceEvents", "calendarLink"],
    mutationFn: ({ raceEventId, body }) => linkCalendarEvent(raceEventId, body),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: raceEventKeys.detail(variables.raceEventId),
      });
      void queryClient.invalidateQueries({
        queryKey: raceEventKeys.lists(),
      });
      // Refresca el calendario y available-for-calendar
      invalidatePaired(queryClient, {
        raceEventId: variables.raceEventId,
        includeCalendar: true,
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Error message helper
// ---------------------------------------------------------------------------

/**
 * Extrae mensaje legible del error axios para mostrar en banners/toast.
 * Mapea los status codes documentados del endpoint de race-events.
 *
 * 409 en DELETE → el evento tiene dependencias (race_results o calendar_event).
 * 403 → sin permiso RBAC (ej. padre intentando crear, o coach intentando borrar).
 * 404 → evento no encontrado (puede haber sido eliminado en paralelo).
 * 422 → payload inválido (ej. sequence_number duplicado en la misma serie).
 */
export function getRaceEventErrorMessage(
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
      return "No se puede eliminar: el evento tiene resultados importados o está vinculado al calendario.";
    }
    if (status === 403) {
      return "Sin permiso para realizar esta acción.";
    }
    if (status === 404) {
      return "Evento de carrera no encontrado.";
    }
    if (status === 422) {
      return "Datos inválidos. Verifica el formulario y vuelve a intentarlo.";
    }
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (e.message && !/status code \d+/i.test(e.message)) {
      return e.message;
    }
  }
  return fallback;
}
