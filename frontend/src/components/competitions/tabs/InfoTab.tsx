/**
 * InfoTab — metadata del evento de carrera.
 *
 * Muestra: nombre, fecha, sede, estado, serie, número de válida, prioridad,
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
 *   - `seriesName?: string` — nombre de la serie, resuelto en el padre igual
 *     que `seriesLevel` (misma lista, mismo find). Ausente mientras carga o
 *     si no se encontró → la fila "Serie" cae a "—" en vez del id crudo.
 *   - `seriesShortName?: string | null` — nombre corto de la serie (hotfix
 *     multicopa — identidad de válida, 2026-09-16), resuelto en el padre
 *     igual que `seriesName`. Precarga el diálogo de edición; ausente
 *     (`undefined`) mientras carga → el diálogo abre con el campo vacío.
 *
 * Hotfix multicopa — identidad de válida: la fila "Serie" solo permite
 * editar el nombre corto para válidas de copa (`!event.is_championship`) —
 * el nombre corto es un concepto de copa, no de campeonato. La fila
 * "Prioridad" lee `event.priority` directamente (ya viene en `RaceEventRead`,
 * no requiere resolución en el padre).
 */
import { useState } from "react";
import { Pencil } from "lucide-react";

import { ActorChip } from "@/components/audit/ActorChip";
import { EditSeriesShortNameDialog } from "@/components/competitions/EditSeriesShortNameDialog";
import {
  raceEventPriorityLabel,
  type RaceEventRead,
  type RaceEventStatus,
} from "@/types/raceEvents.types";
import type { RaceSeriesLevel } from "@/types/raceSeries.types";
import { championshipLabel, seriesChipLabel } from "@/lib/raceSeriesLabels";

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
  /** Nombre de la serie. Ver nota de props arriba. */
  seriesName?: string;
  /** Nombre corto de la serie (hotfix multicopa). Ver nota de props arriba. */
  seriesShortName?: string | null;
}

export function InfoTab({
  event,
  seriesLevel,
  seriesName,
  seriesShortName,
}: InfoTabProps) {
  const [editShortNameOpen, setEditShortNameOpen] = useState(false);
  // Feature 045 (FR-003): los códigos A/B/C/CD se muestran con su significado.
  const priorityLabel = raceEventPriorityLabel(
    event.priority,
    event.is_championship,
  );

  return (
    <div className="space-y-4">
      {/* Tarjeta principal */}
      <div
        className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline"
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

          <InfoRow label="Prioridad">
            {event.is_championship ? (
              <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                {priorityLabel}
              </span>
            ) : priorityLabel ? (
              <span
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                  event.priority === "A"
                    ? "bg-blue-100 text-blue-800"
                    : "bg-[rgba(34,42,53,0.08)] text-charcoal"
                }`}
              >
                {priorityLabel}
              </span>
            ) : (
              <span className="text-mid-gray">Sin prioridad</span>
            )}
          </InfoRow>

          <InfoRow label="Serie">
            <div className="flex items-center gap-2">
              <span>
                {seriesName
                  ? seriesChipLabel(seriesName, seriesShortName)
                  : "—"}
              </span>
              {!event.is_championship && seriesName && (
                <button
                  type="button"
                  onClick={() => setEditShortNameOpen(true)}
                  aria-label="Editar nombre corto de la copa"
                  className="inline-flex min-h-12 min-w-12 items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal"
                  data-testid="btn-edit-series-short-name"
                >
                  <Pencil size={13} aria-hidden="true" />
                </button>
              )}
            </div>
          </InfoRow>
        </div>
      </div>

      {/*
        Montaje perezoso: solo se monta (y solo entonces se llama
        `useUpdateRaceSeries`, que requiere un QueryClientProvider en el
        árbol) cuando el coach realmente abre el diálogo. Evita forzar un
        QueryClientProvider en cada consumidor de InfoTab que nunca edita
        el nombre corto — mismo criterio que los tabs lazy de
        CompetitionDetailPage.
      */}
      {editShortNameOpen && !event.is_championship && seriesName && (
        <EditSeriesShortNameDialog
          open={editShortNameOpen}
          onOpenChange={setEditShortNameOpen}
          seriesId={event.series_id}
          seriesName={seriesName}
          currentShortName={seriesShortName}
        />
      )}

      {/* Tarjeta de auditoría */}
      <div
        className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline"
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

          <InfoRow label="Creado por">
            <ActorChip userId={event.created_by_user_id} />
          </InfoRow>
        </div>
      </div>
    </div>
  );
}
