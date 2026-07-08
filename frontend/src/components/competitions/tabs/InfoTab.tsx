/**
 * InfoTab — metadata del evento de carrera.
 *
 * Muestra: nombre, fecha, sede, estado, serie, número de válida,
 * campeonato y datos de auditoría.
 *
 * Props:
 *   - `event: RaceEventRead` — datos completos del evento.
 *   - `seriesLevel?: RaceSeriesLevel` — nivel de la serie (feature 023,
 *     Campeonato Nacional). Solo relevante cuando `event.is_championship`.
 *     Se resuelve en el padre (`CompetitionDetailPage`) a partir de la lista
 *     de series ya cargada — no dispara un fetch nuevo aquí. Ausente
 *     (`undefined`) mientras la serie está cargando o para snapshots
 *     pre-023 sin nivel resuelto → se asume "Campeonato Departamental"
 *     (fallback conservador, comportamiento previo).
 */
import type { RaceEventRead, RaceEventStatus } from "@/types/raceEvents.types";
import type { RaceSeriesLevel } from "@/types/raceSeries.types";
import { championshipLabel } from "@/lib/raceSeriesLabels";

// ---------------------------------------------------------------------------
// Helpers de formato
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<RaceEventStatus, string> = {
  scheduled: "Planificada",
  completed: "Completada",
  cancelled: "Cancelada",
};

function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  if (!year || !month || !day) return iso;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return date.toLocaleDateString("es-CO", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("es-CO", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Sub-componente: fila de información
// ---------------------------------------------------------------------------

function InfoRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wide text-mid-gray">
        {label}
      </p>
      <div className="mt-0.5 text-sm text-charcoal">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface InfoTabProps {
  event: RaceEventRead;
  /** Nivel de la serie del campeonato. Ver nota de props arriba. */
  seriesLevel?: RaceSeriesLevel;
}

export function InfoTab({ event, seriesLevel }: InfoTabProps) {
  return (
    <div className="space-y-4">
      {/* Tarjeta principal */}
      <div
        className="rounded-xl bg-white p-5 ring-1 ring-[rgba(34,42,53,0.08)]"
        data-testid="info-tab-main"
      >
        <h2 className="mb-4 text-sm font-semibold text-charcoal">
          Información de la competencia
        </h2>

        <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          <InfoRow label="Nombre">{event.name}</InfoRow>

          <InfoRow label="Fecha">{formatDate(event.event_date)}</InfoRow>

          <InfoRow label="Sede">{event.location ?? "—"}</InfoRow>

          <InfoRow label="Estado">
            <span
              className={
                event.status === "completed"
                  ? "text-emerald-700"
                  : event.status === "cancelled"
                    ? "text-mid-gray line-through"
                    : "text-amber-700"
              }
            >
              {STATUS_LABELS[event.status]}
            </span>
          </InfoRow>

          <InfoRow label="Tipo">
            {event.is_championship ? (
              <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                {championshipLabel(seriesLevel ?? "departmental")}
              </span>
            ) : (
              <span>Válida {event.sequence_number}</span>
            )}
          </InfoRow>

          <InfoRow label="Serie ID">
            <span className="font-mono text-xs text-mid-gray">
              {event.series_id}
            </span>
          </InfoRow>
        </div>
      </div>

      {/* Tarjeta de auditoría */}
      <div
        className="rounded-xl bg-white p-5 ring-1 ring-[rgba(34,42,53,0.08)]"
        data-testid="info-tab-audit"
      >
        <h2 className="mb-4 text-sm font-semibold text-charcoal">Auditoría</h2>

        <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
          <InfoRow label="Creado">
            {formatDateTime(event.created_at)}
          </InfoRow>

          <InfoRow label="Última modificación">
            {formatDateTime(event.updated_at)}
          </InfoRow>

          <InfoRow label="Creado por usuario ID">
            <span className="font-mono text-xs text-mid-gray">
              {event.created_by_user_id}
            </span>
          </InfoRow>
        </div>
      </div>
    </div>
  );
}
