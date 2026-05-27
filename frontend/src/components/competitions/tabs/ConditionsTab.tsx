/**
 * ConditionsTab — wrapper que monta RaceConditionsCard para la CompetitionDetailPage.
 *
 * Recibe el evento completo (RaceEventRead) y extrae las condiciones para
 * pasarlas al card ya existente. El card tri-estado maneja internamente
 * los permisos de edición (solo coach/admin).
 *
 * Props:
 *   - `raceEventId: number` — ID del evento para la mutation de actualización.
 *   - `event: RaceEventRead` — datos del evento con condiciones embebidas.
 */
import { RaceConditionsCard } from "@/components/race/RaceConditionsCard";
import type { RaceEventConditions } from "@/types/raceEvents.types";
import type { RaceEventRead } from "@/types/raceEvents.types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ConditionsTabProps {
  raceEventId: number;
  event: RaceEventRead;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ConditionsTab({ raceEventId, event }: ConditionsTabProps) {
  // Construimos el objeto Partial<RaceEventConditions> desde RaceEventRead.
  // RaceEventRead ya incluye todos los campos de condición embebidos.
  const conditions: Partial<RaceEventConditions> = {
    race_event_id: event.id,
    climate: event.climate,
    temperature_c: event.temperature_c,
    surface_condition: event.surface_condition,
    altitude_msnm: event.altitude_msnm,
    weather_notes: event.weather_notes,
    updated_at: event.updated_at,
  };

  return (
    <div className="space-y-4" data-testid="conditions-tab">
      <RaceConditionsCard
        raceEventId={raceEventId}
        conditions={conditions}
      />
    </div>
  );
}
