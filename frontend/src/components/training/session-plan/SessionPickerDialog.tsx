/**
 * SessionPickerDialog — selector compartido "¿A qué sesión?" (feature 032,
 * research.md R6). Reutilizado por los dos puntos de entrada iniciados desde
 * una biblioteca (catálogo de técnica, `/strength/blocks/new` sin
 * `?session_id=`) cuando el id de la sesión destino todavía no se conoce —
 * si ya se conoce (por venir desde la propia sesión), este paso simplemente
 * se omite y no hace falta este componente.
 *
 * Fuente de datos: `useTrainingSessions({ status: "planned" })`
 * (`frontend/src/api/trainingSessions.ts`). El orden por defecto del
 * servicio es `scheduled_date DESC` — la sesión más lejana en el futuro
 * primero (`backend/app/services/training/sessions.py:905-910`, gotcha
 * documentada en research.md R6/R10). Este componente reordena el resultado
 * **ascendente** por `(scheduled_date, scheduled_start_time)` en el cliente
 * antes de mostrar las próximas ~5 sesiones — nunca confía en el orden crudo
 * de la API.
 *
 * El buscador de texto es el fallback para cualquier sesión más lejana que
 * no entra en las próximas 5: filtra sobre la lista completa (no solo el
 * recorte de 5) por lugar, foco técnico o fecha.
 *
 * Presentacional puro: expone `onSelect(sessionId)` y cierra el diálogo tras
 * la selección — cada consumidor decide qué hacer a continuación (técnica:
 * adjunta directo; fuerza: navega con `?session_id=`).
 */
import * as React from "react";
import { Loader2, Search } from "lucide-react";

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTrainingSessions } from "@/api/trainingSessions";
import { formatDate, formatTime } from "@/lib/datetime";
import type { TrainingSession } from "@/types/trainingSession.types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const UPCOMING_LIMIT = 5;

/**
 * Reordena ascendente por (scheduled_date, scheduled_start_time). El
 * servicio devuelve DESC (research.md R6/R10) — este es el punto donde se
 * corrige, una sola vez, antes de cualquier recorte/filtro.
 */
function sortAscending(sessions: TrainingSession[]): TrainingSession[] {
  return [...sessions].sort((a, b) => {
    const dateCmp = a.scheduled_date.localeCompare(b.scheduled_date);
    if (dateCmp !== 0) return dateCmp;
    return a.scheduled_start_time.localeCompare(b.scheduled_start_time);
  });
}

function matchesQuery(session: TrainingSession, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    session.location?.toLowerCase().includes(q) ||
    session.technical_focus?.toLowerCase().includes(q) ||
    session.scheduled_date?.toLowerCase().includes(q) ||
    false
  );
}

function sessionLabel(session: TrainingSession): string {
  const date = formatDate(session.scheduled_date);
  const time = formatTime(session.scheduled_start_time);
  const when = [date, time].filter(Boolean).join(" · ");
  const place = session.location?.trim() || "Sin lugar";
  return when ? `${when} — ${place}` : place;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SessionPickerDialogProps {
  /** Controla la visibilidad — el padre es dueño del estado open/close. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Llamado con el id de la sesión elegida. El diálogo se cierra después. */
  onSelect: (sessionId: number) => void;
  title?: string;
  description?: string;
}

const DEFAULT_TITLE = "¿A qué sesión?";
const DEFAULT_DESCRIPTION =
  "Elegí una sesión planificada próxima o buscá por lugar, foco técnico o fecha.";

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function SessionPickerDialog({
  open,
  onOpenChange,
  onSelect,
  title = DEFAULT_TITLE,
  description = DEFAULT_DESCRIPTION,
}: SessionPickerDialogProps): React.ReactElement {
  const [query, setQuery] = React.useState("");
  const { data, isLoading, isError } = useTrainingSessions({
    status: "planned",
  });

  // Reset del buscador cada vez que el diálogo se vuelve a abrir.
  React.useEffect(() => {
    if (open) setQuery("");
  }, [open]);

  const sorted = React.useMemo(() => sortAscending(data ?? []), [data]);

  const visible = React.useMemo(() => {
    if (query.trim()) {
      return sorted.filter((s) => matchesQuery(s, query));
    }
    return sorted.slice(0, UPCOMING_LIMIT);
  }, [sorted, query]);

  function handleSelect(sessionId: number) {
    onSelect(sessionId);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-mid-gray"
              aria-hidden="true"
            />
            <input
              type="search"
              role="searchbox"
              aria-label="Buscar sesión"
              placeholder="Buscar por lugar, foco técnico o fecha"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="min-h-12 w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <SessionPickerResults
            isLoading={isLoading}
            isError={isError}
            hasAnySession={sorted.length > 0}
            items={visible}
            onSelect={handleSelect}
          />
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Resultados — estados loading / error / vacío / lista
// ---------------------------------------------------------------------------

interface SessionPickerResultsProps {
  isLoading: boolean;
  isError: boolean;
  hasAnySession: boolean;
  items: TrainingSession[];
  onSelect: (sessionId: number) => void;
}

function SessionPickerResults({
  isLoading,
  isError,
  hasAnySession,
  items,
  onSelect,
}: SessionPickerResultsProps): React.ReactElement {
  if (isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500"
      >
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        Cargando sesiones…
      </div>
    );
  }

  if (isError) {
    return (
      <p
        role="alert"
        className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
      >
        No se pudieron cargar las sesiones planificadas. Intentá de nuevo.
      </p>
    );
  }

  if (!hasAnySession) {
    return (
      <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">
        No hay sesiones planificadas próximamente. Creá una sesión primero.
      </p>
    );
  }

  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">
        No se encontraron sesiones para esa búsqueda.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {items.map((session) => (
        <li key={session.id}>
          <button
            type="button"
            onClick={() => onSelect(session.id)}
            className="min-h-12 w-full rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm font-medium text-slate-900 transition-colors hover:border-primary hover:bg-light-gray focus:outline-none focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2"
          >
            {sessionLabel(session)}
            {session.technical_focus?.trim() ? (
              <span className="mt-0.5 block text-xs font-normal text-slate-500">
                {session.technical_focus}
              </span>
            ) : null}
          </button>
        </li>
      ))}
    </ul>
  );
}

export default SessionPickerDialog;
