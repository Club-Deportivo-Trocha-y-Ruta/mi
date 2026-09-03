/**
 * TrailRoute — "Ruta del mes": visual de la ruta con los hitos (waypoints)
 * del mes (feature 038, T301, AC-1.3 / AC-1.4).
 *
 * Un SVG inline responsivo: trazado horizontal (>=480px) y trazado
 * vertical debajo (<480px) — ambos leen los mismos `waypoints`. El SVG en
 * sí (línea punteada + marcadores) es decorativo: la única superficie que
 * expone información a lectores de pantalla es la lista `<ol>` oculta
 * visualmente (`sr-only`, ya usada en el proyecto — ver
 * `PercentileCurves.tsx`), que enumera los mismos hitos en texto plano.
 * Adicionalmente el trazado horizontal (el único de los dos que se marca
 * `role="img"`, para no duplicar el nombre accesible del gráfico cuando
 * ambos DOM nodes coexisten) lleva `<title>`/`<desc>` con un resumen.
 *
 * El waypoint que coincide con la fecha de la "cima del mes" (`summitDate`)
 * se dibuja como triángulo en vez de disco (plan.md "Visual language").
 * Los discos usan charcoal con anillo teal (`--color-primary`); los
 * hitos futuros (`is_future`) se dibujan con relleno hueco (solo el
 * anillo) para distinguirse por FORMA, no solo por color.
 */
import { useId } from "react";
import {
  Award,
  Compass,
  Flag,
  Flame,
  MapPin,
  Star,
  type LucideIcon,
} from "lucide-react";

import { formatDayMonthShort } from "@/lib/datetime";
import type { Waypoint } from "@/types/stageLog.types";

export interface TrailRouteProps {
  waypoints: Waypoint[];
  /** Fecha ISO de la cima del mes (`summit.date`) — marca ese waypoint como triángulo. */
  summitDate?: string | null;
}

const WAYPOINT_ICONS: Record<string, LucideIcon> = {
  flag: Flag,
  award: Award,
  flame: Flame,
  star: Star,
  "map-pin": MapPin,
  compass: Compass,
};

function iconFor(icon: string): LucideIcon {
  return WAYPOINT_ICONS[icon] ?? MapPin;
}

interface MarkerProps {
  waypoint: Waypoint;
  isSummit: boolean;
}

function Marker({ waypoint, isSummit }: MarkerProps) {
  const Icon = iconFor(waypoint.icon);
  const shapeClass = isSummit ? "" : "rounded-full";
  const fillClass = waypoint.is_future
    ? "bg-white border-2 border-dashed border-primary"
    : "bg-charcoal border-2 border-primary";

  return (
    <div
      className="flex min-w-0 flex-col items-center gap-1 text-center"
      data-testid="trail-marker"
      data-waypoint-kind={waypoint.kind}
      data-waypoint-summit={isSummit || undefined}
    >
      <span
        aria-hidden="true"
        className={`flex h-8 w-8 shrink-0 items-center justify-center ${shapeClass} ${fillClass}`}
        style={
          isSummit
            ? { clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)" }
            : undefined
        }
      >
        <Icon
          size={14}
          className={waypoint.is_future ? "text-primary" : "text-white"}
        />
      </span>
      <span className="max-w-20 truncate text-[11px] font-medium text-charcoal">
        {waypoint.label}
      </span>
      <span className="text-[10px] text-mid-gray">
        {formatDayMonthShort(waypoint.date)}
      </span>
    </div>
  );
}

export function TrailRoute({ waypoints, summitDate }: TrailRouteProps) {
  const titleId = useId();
  const descId = useId();

  if (waypoints.length === 0) return null;

  const isSummitWaypoint = (w: Waypoint) =>
    summitDate != null && w.date === summitDate;

  return (
    <div className="trail-terrain-bg rounded-xl p-4" data-testid="trail-route">
      {/* Trazado horizontal — >=480px */}
      <div className="hidden min-[480px]:block" data-testid="trail-route-horizontal">
        <svg
          role="img"
          aria-labelledby={`${titleId} ${descId}`}
          viewBox="0 0 100 4"
          preserveAspectRatio="none"
          className="h-4 w-full"
        >
          <title id={titleId}>Ruta del mes</title>
          <desc id={descId}>
            Trazado con {waypoints.length} hitos del mes, del primero al
            último. El detalle de cada hito está en la lista de texto que
            sigue a esta gráfica.
          </desc>
          <line
            x1="2"
            y1="2"
            x2="98"
            y2="2"
            stroke="var(--color-primary)"
            strokeWidth="0.6"
            strokeDasharray="2 2"
            strokeLinecap="round"
          />
        </svg>
        <div className="mt-1 flex items-start justify-between gap-1">
          {waypoints.map((w, idx) => (
            <Marker
              key={`${w.kind}-${w.date}-${idx}`}
              waypoint={w}
              isSummit={isSummitWaypoint(w)}
            />
          ))}
        </div>
      </div>

      {/* Trazado vertical — <480px. Puramente decorativo (aria-hidden): la
          gráfica horizontal de arriba ya expone role="img" + title/desc,
          y la lista sr-only de abajo cubre el contenido en ambos anchos. */}
      <div
        className="flex min-[480px]:hidden"
        data-testid="trail-route-vertical"
        aria-hidden="true"
      >
        <svg
          viewBox="0 0 4 100"
          preserveAspectRatio="none"
          className="w-4 shrink-0 self-stretch"
        >
          <line
            x1="2"
            y1="2"
            x2="2"
            y2="98"
            stroke="var(--color-primary)"
            strokeWidth="0.6"
            strokeDasharray="2 2"
            strokeLinecap="round"
          />
        </svg>
        <div className="flex flex-1 flex-col gap-3 py-1">
          {waypoints.map((w, idx) => (
            <div key={`${w.kind}-${w.date}-${idx}`} className="flex items-center gap-2">
              <Marker waypoint={w} isSummit={isSummitWaypoint(w)} />
            </div>
          ))}
        </div>
      </div>

      {/* Alternativa textual WCAG 2.1 AA — mismos hitos, siempre en el DOM */}
      <ol className="sr-only" aria-label="Hitos de la ruta del mes">
        {waypoints.map((w, idx) => (
          <li key={`sr-${w.kind}-${w.date}-${idx}`}>
            {w.label}
            {w.sublabel ? `, ${w.sublabel}` : ""} — {formatDayMonthShort(w.date)}
            {w.is_future ? " (próximo)" : ""}
          </li>
        ))}
      </ol>
    </div>
  );
}
