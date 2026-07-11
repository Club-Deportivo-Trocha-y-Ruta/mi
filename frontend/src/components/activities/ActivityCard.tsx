/**
 * ActivityCard — resumen de una actividad Strava sincronizada (feature 025,
 * T026).
 *
 * Muestra: fecha/hora, tipo de deporte, duración, distancia, frecuencia
 * cardiaca media/máxima, indicador de rodillo (indoor), el badge de estado
 * de enlace con una sesión de entrenamiento y — solo para coach/admin vía
 * `canLink` — la acción para enlazar/cambiar esa sesión (T032b, cierra el
 * gap de integración: `LinkSessionDialog` existía pero nada la renderizaba).
 *
 * Privacidad (Ley 1581) — este componente NUNCA debe renderizar coordenadas,
 * mapas ni ubicación: `ActivityOut` (types/strava.types.ts) no expone esos
 * campos por diseño (ver data-model.md §2, "Explicitly ABSENT columns"), así
 * que no hay nada que omitir a propósito — es una garantía estructural, no
 * una convención de este componente.
 *
 * Reutilizable: pensado para la sección de actividades del perfil del atleta
 * (AthleteDetailPage, T026, `canLink`), la vista de revisión del coach
 * (T028+, con `showAthleteName` + `canLink`) y la vista de padres (T036,
 * `canLink` se omite → solo lectura).
 *
 * Gating de la acción de enlace: DOBLE — el prop `canLink` (lo decide la
 * página contenedora según la superficie: coach sí, padres/atletas no) Y el
 * rol del usuario autenticado (`coach`/`admin`) leído acá mismo de
 * `useAuthStore`. Ambas condiciones deben cumplirse; así una página que
 * olvide gatear por rol no expone el botón a un padre.
 */
import { useState } from "react";
import { Clock, Gauge, Heart, History, Home, Link2, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LinkSessionDialog } from "@/components/activities/LinkSessionDialog";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type { ActivityOut } from "@/types/strava.types";

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

/**
 * `start_date_local` llega como datetime naive que YA representa la hora
 * local de la actividad (convención de Strava — no UTC). A diferencia de
 * `lib/datetime.ts` (que asume naive = UTC y resta el offset de Bogotá), acá
 * NO se debe convertir zona horaria: se parsean los componentes tal cual
 * vienen para evitar un corrimiento de horas al formatear.
 */
function formatActivityDateTime(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!match) return value;
  const [, year, month, day, hour, minute] = match;
  const local = new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
  );
  const datePart = new Intl.DateTimeFormat("es-CO", {
    day: "2-digit",
    month: "short",
  }).format(local);
  const timePart = new Intl.DateTimeFormat("es-CO", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(local);
  return `${datePart} · ${timePart}`;
}

/** 45 → "45 min"; 5400 → "1 h 30 min"; 3600 → "1 h". */
function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} h`;
  return `${h} h ${m} min`;
}

/** 12345 → "12,3 km". */
function formatDistance(meters: number | null): string {
  if (meters == null) return "—";
  return `${(meters / 1000).toLocaleString("es-CO", { maximumFractionDigits: 1 })} km`;
}

function formatHeartRate(avg: number | null, max: number | null): string {
  if (avg == null && max == null) return "Sin datos de FC";
  const avgLabel = avg != null ? Math.round(avg) : "—";
  const maxLabel = max != null ? Math.round(max) : "—";
  return `${avgLabel} / ${maxLabel} lpm`;
}

const SPORT_TYPE_LABELS: Record<string, string> = {
  Ride: "Ruta",
  MountainBikeRide: "MTB",
  GravelRide: "Gravel",
  VirtualRide: "Virtual",
  EBikeRide: "E-bike",
  Run: "Carrera",
  Workout: "Entrenamiento",
};

function sportTypeLabel(sportType: string): string {
  return SPORT_TYPE_LABELS[sportType] ?? sportType;
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

interface ActivityCardProps {
  activity: ActivityOut;
  /** Muestra el nombre del atleta en el encabezado (vista de revisión del coach). */
  showAthleteName?: boolean;
  /**
   * Habilita la acción "Enlazar a sesión" / "Cambiar sesión" (coach/admin).
   * La página contenedora decide esto según la superficie — ver docstring
   * del componente. Por defecto `false` (solo lectura), así que las vistas
   * de padres/atletas quedan protegidas simplemente por no pasar el prop.
   */
  canLink?: boolean;
  className?: string;
}

export function ActivityCard({
  activity,
  showAthleteName = false,
  canLink = false,
  className,
}: ActivityCardProps) {
  const isLinked = activity.link !== null;
  const isRemovedUpstream = activity.upstream_state === "removed_upstream";

  const role = useAuthStore((s) => s.user?.role);
  const roleAllowsLink = role === UserRole.coach || role === UserRole.admin;
  const showLinkAction = canLink && roleAllowsLink;

  const [linkDialogOpen, setLinkDialogOpen] = useState(false);

  return (
    <article
      className={cn("rounded-xl bg-white p-4 shadow-card", className)}
      aria-label={`Actividad ${sportTypeLabel(activity.sport_type)} del ${formatActivityDateTime(activity.start_date_local)}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          {showAthleteName && (
            <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
              {activity.athlete_name}
            </p>
          )}
          <p className="truncate text-sm font-semibold text-charcoal">
            {activity.name || sportTypeLabel(activity.sport_type)}
          </p>
          <p className="mt-0.5 text-xs text-mid-gray">
            {formatActivityDateTime(activity.start_date_local)} · {sportTypeLabel(activity.sport_type)}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          {activity.is_trainer && (
            <Badge variant="info" className="gap-1">
              <Home size={12} aria-hidden="true" />
              Rodillo
            </Badge>
          )}
          {isRemovedUpstream && (
            <Badge variant="destructive" className="gap-1">
              <History size={12} aria-hidden="true" />
              Eliminada en Strava
            </Badge>
          )}
          <Badge variant={isLinked ? "success" : "warning"} className="gap-1">
            {isLinked ? `Enlazada · ${activity.link!.session_label}` : "Sin enlazar"}
          </Badge>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-3 border-t border-[rgba(34,42,53,0.06)] pt-3 sm:max-w-sm">
        <div>
          <dt className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-mid-gray">
            <Clock size={12} aria-hidden="true" />
            Duración
          </dt>
          <dd className="mt-0.5 text-sm font-medium text-charcoal">
            {formatDuration(activity.elapsed_time_s)}
          </dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-mid-gray">
            <Gauge size={12} aria-hidden="true" />
            Distancia
          </dt>
          <dd className="mt-0.5 text-sm font-medium text-charcoal">
            {formatDistance(activity.distance_m)}
          </dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-mid-gray">
            <Heart size={12} aria-hidden="true" />
            FC media/máx
          </dt>
          <dd className="mt-0.5 text-sm font-medium text-charcoal">
            {formatHeartRate(activity.average_heartrate, activity.max_heartrate)}
          </dd>
        </div>
      </dl>

      {!activity.summary_complete && (
        <p className="mt-3 text-xs text-mid-gray">
          Strava todavía está completando los datos de esta actividad — algunos
          valores pueden actualizarse más tarde.
        </p>
      )}

      {showLinkAction && (
        <div className="mt-3 border-t border-[rgba(34,42,53,0.06)] pt-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 gap-2"
            onClick={() => setLinkDialogOpen(true)}
          >
            {isLinked ? (
              <RefreshCw size={14} aria-hidden="true" />
            ) : (
              <Link2 size={14} aria-hidden="true" />
            )}
            {isLinked ? "Cambiar sesión" : "Enlazar a sesión"}
          </Button>
        </div>
      )}

      {showLinkAction && (
        <LinkSessionDialog
          activity={activity}
          open={linkDialogOpen}
          onOpenChange={setLinkDialogOpen}
        />
      )}
    </article>
  );
}
