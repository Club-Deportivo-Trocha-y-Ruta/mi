/**
 * Utilidades para calcular diferencias entre el estado original y el actual
 * de una sesión de entrenamiento. Se usan en el flujo de notificación a
 * padres (estilo Google Calendar): el coach ve qué cambió antes de decidir
 * si enviar el aviso por correo.
 */

export interface ChangeEntry {
  field: string;
  fieldLabel: string;
  oldValue: string;
  newValue: string;
}

export interface AthleteEntry {
  id: number;
  name: string;
}

export const FIELD_LABELS: Record<string, string> = {
  scheduled_date: "Fecha",
  scheduled_start_time: "Hora de inicio",
  duration_min: "Duración (min)",
  location: "Lugar",
  technical_focus: "Foco técnico",
  description: "Descripción",
  route_text: "Recorrido",
  strava_url: "Link Strava",
};

const DIFFABLE_FIELDS = Object.keys(FIELD_LABELS);

function humanize(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return String(value);
}

/**
 * Compara dos snapshots del formulario de sesión y devuelve solo los campos
 * que cambiaron. `coach_notes` y `convocados_athlete_ids` quedan fuera —
 * el primero porque no se comunica al padre, el segundo se diffea aparte.
 */
export function diffSessionValues(
  initial: Record<string, unknown>,
  current: Record<string, unknown>,
): ChangeEntry[] {
  const changes: ChangeEntry[] = [];
  for (const field of DIFFABLE_FIELDS) {
    const oldRaw = initial[field];
    const newRaw = current[field];
    const oldStr = humanize(oldRaw);
    const newStr = humanize(newRaw);
    if (oldStr !== newStr) {
      changes.push({
        field,
        fieldLabel: FIELD_LABELS[field],
        oldValue: oldStr,
        newValue: newStr,
      });
    }
  }
  return changes;
}

export interface AthleteDiff {
  added: number[];
  removed: number[];
  changed: boolean;
}

export function diffAthleteIds(initial: number[], current: number[]): AthleteDiff {
  const initialSet = new Set(initial);
  const currentSet = new Set(current);
  const added = current.filter((id) => !initialSet.has(id));
  const removed = initial.filter((id) => !currentSet.has(id));
  return { added, removed, changed: added.length > 0 || removed.length > 0 };
}
