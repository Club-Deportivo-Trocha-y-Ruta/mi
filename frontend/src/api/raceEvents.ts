/**
 * API client del módulo race-events.
 *
 * Auth: JWT via interceptor en apiClient.
 *
 * Endpoints cubiertos:
 *   - PATCH  /{id}/conditions  → updateRaceEventConditions  (F-COND, coach+admin)
 *   - POST   /                 → createRaceEvent            (CF3, coach+admin)
 *   - PATCH  /{id}             → updateRaceEvent            (CF3, coach+admin)
 *   - DELETE /{id}             → deleteRaceEvent            (CF3, admin only)
 *   - GET    /                 → listRaceEvents             (CF3, todos)
 *   - GET    /{id}             → getRaceEvent               (CF5, todos)
 */
import { apiClient } from "@/api/client";
import type {
  CalendarAutoCreateResponse,
  RaceEventCalendarLinkBody,
  RaceEventCalendarLinkResponse,
  RaceEventConditions,
  RaceEventConditionsUpdate,
  RaceEventCreate,
  RaceEventListFilters,
  RaceEventListResponse,
  RaceEventRead,
  RaceEventUpdate,
} from "@/types/raceEvents.types";

const BASE = "/api/race-analysis/race-events";

// ---------------------------------------------------------------------------
// F-COND — condiciones logísticas (ya existía)
// ---------------------------------------------------------------------------

/**
 * PATCH /api/race-analysis/race-events/{raceEventId}/conditions
 *
 * Actualiza parcialmente las condiciones logísticas de un evento.
 * Solo los campos presentes en `body` se modifican (merge semántico).
 *
 * `temperature_c` se serializa a string en JSON si llega como number,
 * el backend lo recibe como Decimal y lo acepta en ambas formas.
 */
export async function updateRaceEventConditions(
  raceEventId: number,
  body: RaceEventConditionsUpdate,
  options?: { signal?: AbortSignal },
): Promise<RaceEventConditions> {
  const response = await apiClient.patch<RaceEventConditions>(
    `${BASE}/${raceEventId}/conditions`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// CF3 — CRUD completo de eventos de carrera
// ---------------------------------------------------------------------------

/**
 * POST /api/race-analysis/race-events/
 *
 * Crea un nuevo evento de carrera (válida de Copa Valle).
 * RBAC: coach + admin.
 *
 * El backend retorna 201 con el evento creado.
 */
export async function createRaceEvent(
  body: RaceEventCreate,
  options?: { signal?: AbortSignal },
): Promise<RaceEventRead> {
  const response = await apiClient.post<RaceEventRead>(BASE + "/", body, {
    signal: options?.signal,
  });
  return response.data;
}

/**
 * PATCH /api/race-analysis/race-events/{id}
 *
 * Actualiza campos básicos del evento (nombre, fecha, ubicación, estado).
 * No incluye condiciones — usar `updateRaceEventConditions` para eso.
 * RBAC: coach + admin.
 *
 * El backend usa `extra=forbid`: no enviar campos no declarados en
 * `RaceEventUpdate`.
 */
export async function updateRaceEvent(
  id: number,
  body: RaceEventUpdate,
  options?: { signal?: AbortSignal },
): Promise<RaceEventRead> {
  const response = await apiClient.patch<RaceEventRead>(
    `${BASE}/${id}`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * DELETE /api/race-analysis/race-events/{id}
 *
 * Elimina un evento de carrera. Retorna 204 sin body.
 * RBAC: admin only.
 *
 * 409 Conflict si el evento tiene `race_results` o `calendar_event`
 * asociados — el hook propagará el error para que el componente muestre
 * el mensaje de confirmación al usuario.
 */
export async function deleteRaceEvent(
  id: number,
  options?: { signal?: AbortSignal },
): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`, { signal: options?.signal });
}

/**
 * GET /api/race-analysis/race-events/{id}
 *
 * Retorna el evento completo (`RaceEventRead`) con todos los campos incluyendo
 * condiciones logísticas. Usa este endpoint cuando necesitas datos completos
 * del evento (ej: CompetitionDetailPage).
 *
 * 404 si el evento no existe.
 */
export async function getRaceEvent(
  id: number,
  options?: { signal?: AbortSignal },
): Promise<RaceEventRead> {
  const response = await apiClient.get<RaceEventRead>(`${BASE}/${id}`, {
    signal: options?.signal,
  });
  return response.data;
}

/**
 * POST /api/race-analysis/race-events/{id}/calendar-link
 *
 * Asocia un `calendar_event` ya existente a una válida cuando la válida
 * aún no tiene ningún vínculo (`has_calendar_event === false`).
 * RBAC: coach + admin.
 *
 * 409 si la válida ya está vinculada (1:1 estricto) o si el calendar_event
 * ya está ligado a otra válida.
 * 404 si el `calendar_event_id` no existe.
 */
export async function linkCalendarEvent(
  raceEventId: number,
  body: RaceEventCalendarLinkBody,
  options?: { signal?: AbortSignal },
): Promise<RaceEventCalendarLinkResponse> {
  const response = await apiClient.post<RaceEventCalendarLinkResponse>(
    `${BASE}/${raceEventId}/calendar-link`,
    body,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * POST /api/race-analysis/race-events/{raceEventId}/calendar-event
 *
 * Crea y vincula un CalendarEvent all-day desde los datos propios de la válida
 * (nombre, fecha, ubicación). Sin cuerpo de petición — todo se toma del backend.
 * RBAC: coach only (FR-008).
 *
 * 201 → evento creado y vinculado (CalendarAutoCreateResponse).
 * 409 → la válida ya tiene un calendar_event asociado (1:1 estricto).
 * 404 → la válida no existe.
 * 403 → el usuario no tiene rol coach.
 *
 * US2 (feature 008 Phase 4): para abrir el formulario pre-rellenado antes de
 * crear, navegar a `/calendar/events/new?race_event_id={raceEventId}`.
 */
export async function createCalendarEventForRaceEvent(
  raceEventId: number,
  options?: { signal?: AbortSignal },
): Promise<CalendarAutoCreateResponse> {
  const response = await apiClient.post<CalendarAutoCreateResponse>(
    `${BASE}/${raceEventId}/calendar-event`,
    null,
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * GET /api/race-analysis/race-events/
 *
 * Lista eventos de carrera con filtros opcionales.
 * Retorna `{ items, total }` paginado.
 *
 * Los parámetros `undefined` se omiten del query string — axios serializa
 * solo los que tienen valor.
 */
export async function listRaceEvents(
  filters: RaceEventListFilters = {},
  options?: { signal?: AbortSignal },
): Promise<RaceEventListResponse> {
  const response = await apiClient.get<RaceEventListResponse>(BASE + "/", {
    params: filters,
    signal: options?.signal,
  });
  return response.data;
}
