/**
 * ActivityEvidenceStrip — evidencia Strava compacta embebida en la fila de
 * asistencia (feature 025 follow-up,
 * specs/025-strava-activity-sync/session-detail-redesign.md §3.3).
 *
 * Reemplaza la sección "Actividades Strava" que vivía como una segunda
 * tabla independiente en `SessionDetailPage` — la evidencia ahora vive
 * junto al resto del roster row (estado/razón/rúbrica), un solo nivel de
 * disclosure: el chevron expande `ActivityCard` reutilizado tal cual (sin
 * acordeón anidado dentro de otro acordeón).
 *
 * Cuatro estados (ver §3.3 del spec):
 *   1. loading            → skeleton de una línea.
 *   2. sin datos          → texto neutro "Sin actividad Strava" (mayoría de
 *                            los atletas sin Strava conectado — no es un
 *                            error ni una tarea pendiente).
 *   3. sin enlazar         → badge ámbar + acción "Enlazar" (gateada por
 *                            `canLink`) que abre `LinkSessionDialog`
 *                            reutilizado tal cual.
 *   4. enlazada(s)         → métricas informativas (duración/distancia/FC)
 *                            + chevron que expande `ActivityCard` por cada
 *                            actividad enlazada.
 *
 * Nota: el chip de cumplimiento (verde/ámbar/rojo comparando duración
 * planeada vs. actual) que existió aquí fue removido por decisión de
 * producto — señal demasiado ruidosa/dinámica por ahora (ver spec §3.3.1,
 * ahora tachado).
 */
import { useState } from "react";
import { ChevronDown, ChevronUp, Link2 } from "lucide-react";
import { Link } from "react-router-dom";

import { ActivityCard } from "@/components/activities/ActivityCard";
import { LinkSessionDialog } from "@/components/activities/LinkSessionDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ActivityOut } from "@/types/strava.types";

// ---------------------------------------------------------------------------
// Formatters (mirror compacto de ActivityCard.tsx)
// ---------------------------------------------------------------------------

/** 45 → "45 min"; 5400 → "1 h 30 min"; 3600 → "1 h". */
function formatDurationCompact(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} h`;
  return `${h} h ${m} min`;
}

/** 12345 → "12,3 km". */
function formatDistanceCompact(meters: number | null): string {
  if (meters == null) return "—";
  return `${(meters / 1000).toLocaleString("es-CO", { maximumFractionDigits: 1 })} km`;
}

/**
 * Desempate cuando hay >1 actividad enlazada para el mismo atleta+sesión
 * (caso raro — dos grabaciones de dispositivo para una sola rodada): la de
 * mayor `elapsed_time_s` es la "primaria" del resumen colapsado; el resto
 * solo se ve al expandir.
 */
function pickPrimaryActivity(activities: ActivityOut[]): ActivityOut {
  return activities.reduce((longest, current) =>
    current.elapsed_time_s > longest.elapsed_time_s ? current : longest,
  );
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export interface ActivityEvidenceStripProps {
  athleteId: number;
  linkedActivities: ActivityOut[];
  unlinkedActivities: ActivityOut[];
  loading?: boolean;
  canLink: boolean;
}

export function ActivityEvidenceStrip({
  athleteId,
  linkedActivities,
  unlinkedActivities,
  loading = false,
  canLink,
}: ActivityEvidenceStripProps) {
  const [expanded, setExpanded] = useState(false);
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const panelId = `activity-evidence-panel-${athleteId}`;

  if (loading) {
    return (
      <div
        className="h-4 w-32 animate-pulse rounded bg-light-gray"
        data-testid={`activity-evidence-loading-${athleteId}`}
        aria-hidden="true"
      />
    );
  }

  // Estado 2 — sin ningún dato de Strava.
  if (linkedActivities.length === 0 && unlinkedActivities.length === 0) {
    return (
      <p
        className="text-xs text-mid-gray"
        data-testid={`activity-evidence-empty-${athleteId}`}
      >
        Sin actividad Strava
      </p>
    );
  }

  // Estado 3 — hay actividad(es) sin enlazar, ninguna enlazada todavía.
  if (linkedActivities.length === 0) {
    const primaryUnlinked = unlinkedActivities[0];
    const extraUnlinked = unlinkedActivities.length - 1;

    return (
      <div
        className="flex flex-wrap items-center gap-1.5"
        data-testid={`activity-evidence-unlinked-${athleteId}`}
      >
        <Badge variant="warning">Actividad sin enlazar</Badge>
        <span className="text-xs text-mid-gray">
          {formatDurationCompact(primaryUnlinked.elapsed_time_s)} ·{" "}
          {formatDistanceCompact(primaryUnlinked.distance_m)}
        </span>
        {canLink && (
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-12 min-w-12 gap-1.5"
              onClick={() => setLinkDialogOpen(true)}
            >
              <Link2 size={14} aria-hidden="true" />
              Enlazar
            </Button>
            <LinkSessionDialog
              activity={primaryUnlinked}
              open={linkDialogOpen}
              onOpenChange={setLinkDialogOpen}
            />
          </>
        )}
        {extraUnlinked > 0 && (
          <Link
            to={`/activities?athlete_id=${athleteId}&linked=false`}
            className="text-xs font-medium text-charcoal underline hover:opacity-70"
          >
            +{extraUnlinked} más — revisar en Actividades
          </Link>
        )}
      </div>
    );
  }

  // Estado 4 — al menos una actividad enlazada.
  const primaryLinked = pickPrimaryActivity(linkedActivities);
  const extraLinked = linkedActivities.length - 1;
  const avgHr = primaryLinked.average_heartrate;

  return (
    <div className="space-y-2" data-testid={`activity-evidence-linked-${athleteId}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-mid-gray">
          {formatDurationCompact(primaryLinked.elapsed_time_s)} ·{" "}
          {formatDistanceCompact(primaryLinked.distance_m)}
          {avgHr != null ? ` · ${Math.round(avgHr)} lpm` : ""}
        </span>
        {extraLinked > 0 && (
          <span className="text-xs text-mid-gray">+{extraLinked}</span>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-12 w-12"
          aria-expanded={expanded}
          aria-controls={panelId}
          aria-label={
            expanded ? "Ocultar detalle de actividad Strava" : "Ver detalle de actividad Strava"
          }
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? (
            <ChevronUp size={16} aria-hidden="true" />
          ) : (
            <ChevronDown size={16} aria-hidden="true" />
          )}
        </Button>
      </div>

      {expanded && (
        <div id={panelId} className="max-h-96 space-y-2 overflow-y-auto">
          {linkedActivities.map((activity) => (
            <ActivityCard key={activity.id} activity={activity} canLink={canLink} />
          ))}
        </div>
      )}
    </div>
  );
}
