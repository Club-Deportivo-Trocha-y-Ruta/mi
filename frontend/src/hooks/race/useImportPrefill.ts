/**
 * useImportPrefill — view-model del prefill del wizard de importación cuando
 * se lanza desde una competencia existente (feature 015).
 *
 * Composición (sin endpoint nuevo, FR-011/FR-012):
 *   1. `useRaceEvent(raceEventId)`     → evento (series_id, sequence_number,
 *      nombre, fecha, ciudad, is_championship, condiciones).
 *   2. `useRaceSeriesList()`           → resuelve la serie por `event.series_id`
 *      (no existe GET /race-series/{id}; se filtra la lista).
 *
 * Máquina de estados:
 *   loading → ready    (evento cargado Y serie resuelta)
 *           → blocked  (serie/tipo irresoluble → FR-009, ofrece editMetadataHref)
 *           → error    (fetch del evento falló / 404 → UI de error existente)
 *
 * Derivación (FR-002/FR-005/FR-008):
 *   - `series_kind = series.kind` (NUNCA elegido in-flow).
 *   - `valida_num = is_championship ? null : event.sequence_number`
 *     (oculto para campeonato).
 *   - identidad (nombre, fecha, ciudad, serie, temporada) bloqueada/read-only.
 *
 * Inputs:  `raceEventId` — id de la competencia, o `null`/`undefined` para el
 *          flujo standalone (devuelve `null`, sin prefill — FR-007).
 * Output:  `ImportPrefill | null`.
 * Side effects: dos GET cacheados vía TanStack Query (no N+1).
 *
 * Privacidad: solo lee metadata de competencia (FR-013) — cero PII de menores.
 */
import { useMemo } from "react";

import { useRaceEvent } from "@/hooks/race/useRaceEvents";
import { useRaceSeriesList } from "@/hooks/race/useRaceSeries";
import type {
  ImportPrefill,
  ImportPrefillValues,
} from "@/types/raceImports.types";

export function useImportPrefill(
  raceEventId: number | null | undefined,
): ImportPrefill | null {
  const enabled = raceEventId != null && raceEventId > 0;
  const eventQuery = useRaceEvent(enabled ? raceEventId : null);
  // La lista de series es pequeña (decenas) y se cachea 60 s — resolvemos la
  // serie del evento filtrando por id, no hay GET /race-series/{id}.
  // `enabled` apaga la query en el flujo standalone (FR-007): el wizard sin
  // `raceEventId` no debe disparar ningún request nuevo.
  const seriesQuery = useRaceSeriesList({}, { enabled });

  return useMemo<ImportPrefill | null>(() => {
    // Flujo standalone — sin prefill, el wizard se comporta como hoy (FR-007).
    if (!enabled || raceEventId == null) return null;

    // Error del evento (404 u otro) → estado error (UI de error existente).
    if (eventQuery.isError) {
      return { status: "error", raceEventId };
    }

    // Aún cargando evento o serie → loading (cold-start aware en el wizard).
    if (eventQuery.isLoading || !eventQuery.data || seriesQuery.isLoading) {
      return { status: "loading", raceEventId };
    }

    const event = eventQuery.data;

    // Serie irresoluble (lista vacía, fetch fallido, o id ausente) → bloqueado
    // (FR-009). Nunca se ofrece un selector de serie/tipo in-flow (FR-005).
    const series =
      seriesQuery.data?.items.find((s) => s.id === event.series_id) ?? null;
    if (!series) {
      return {
        status: "blocked",
        raceEventId,
        editMetadataHref: `/competitions/${raceEventId}/edit`,
      };
    }

    const values: ImportPrefillValues = {
      series_kind: series.kind,
      series_name: series.name,
      season: series.season_year,
      // FR-008: campeonato no tiene número de válida (campo oculto).
      valida_num: event.is_championship ? null : event.sequence_number,
      event_name: event.name,
      event_date: event.event_date,
      location: event.location ?? "",
      // Condiciones: precargadas pero EDITABLES (comportamiento actual).
      conditions: {
        climate: event.climate ?? undefined,
        temperature_c:
          event.temperature_c != null
            ? Number(event.temperature_c)
            : undefined,
        surface_condition: event.surface_condition ?? null,
        altitude_msnm: event.altitude_msnm ?? undefined,
        weather_notes: event.weather_notes ?? undefined,
      },
    };

    return { status: "ready", raceEventId, values };
  }, [
    enabled,
    raceEventId,
    eventQuery.isError,
    eventQuery.isLoading,
    eventQuery.data,
    seriesQuery.isLoading,
    seriesQuery.data,
  ]);
}
