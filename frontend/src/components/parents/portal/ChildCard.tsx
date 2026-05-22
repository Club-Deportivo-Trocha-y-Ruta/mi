import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

import type { MyAthleteOut } from "@/types/parent.types";
import { MaturationStatus } from "@/types/enums";

interface ChildCardProps {
  athlete: MyAthleteOut;
}

type MeasurementStatus = MyAthleteOut["measurement_status"];

const STATUS_CONFIG: Record<
  MeasurementStatus,
  { label: string; textClass: string; bgClass: string }
> = {
  ok: { label: "Al día", textClass: "text-green-700", bgClass: "bg-green-50" },
  due_soon: { label: "Pronto medición", textClass: "text-amber-700", bgClass: "bg-amber-50" },
  overdue: { label: "Medición vencida", textClass: "text-red-700", bgClass: "bg-red-50" },
  never: { label: "Sin mediciones", textClass: "text-mid-gray", bgClass: "bg-light-gray" },
};

function phvLabel(status: MaturationStatus | null): string {
  if (status === null) return "Sin evaluación de crecimiento";
  if (status === MaturationStatus.PrePHV) return "En etapa de desarrollo temprano";
  if (status === MaturationStatus.CircaPHV) return "En pico de crecimiento — etapa clave";
  if (status === MaturationStatus.PostPHV) return "Crecimiento estabilizándose";
  return "Sin evaluación de crecimiento";
}

function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("es-CO", {
    day: "numeric",
    month: "short",
  }).format(new Date(`${isoDate}T12:00:00`));
}

export function ChildCard({ athlete }: ChildCardProps) {
  const status = STATUS_CONFIG[athlete.measurement_status];
  const hasAnthropometry = athlete.latest_anthropometry_date !== null;

  const heightFormatted = athlete.standing_height_cm
    ? parseFloat(athlete.standing_height_cm).toFixed(1)
    : null;
  const weightFormatted = athlete.weight_kg
    ? parseFloat(athlete.weight_kg).toFixed(1)
    : null;

  return (
    <Link
      to={`/my-athletes/${athlete.athlete_id}`}
      className="flex flex-col rounded-xl bg-white shadow-ring-soft transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link-blue/50"
      aria-label={`Ver detalle de ${athlete.athlete_first_name} ${athlete.athlete_last_name}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between px-5 pt-5 pb-4">
        <div className="min-w-0 flex-1">
          <h2
            className="truncate text-lg text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            {athlete.athlete_first_name} {athlete.athlete_last_name}
          </h2>
          <p className="mt-0.5 text-sm text-mid-gray">
            Edad: {athlete.age_decimal !== null ? `${athlete.age_decimal.toFixed(1)} años` : "N/D"}
            {athlete.category && (
              <>
                {" "}
                <span className="mx-1 text-mid-gray">•</span> Cat: {athlete.category}
              </>
            )}
          </p>
        </div>

        <span
          className={`ml-3 shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${status.textClass} ${status.bgClass}`}
        >
          {status.label}
        </span>
      </div>

      {/* Divider */}
      <div style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }} />

      {/* Body */}
      <div className="flex-1 px-5 py-4">
        {hasAnthropometry ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Talla</p>
              <p className="mt-0.5 text-sm font-semibold text-charcoal">
                {heightFormatted ? `${heightFormatted} cm` : "—"}
              </p>
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                Estado de crecimiento
              </p>
              <p className="mt-0.5 text-sm text-charcoal">{phvLabel(athlete.maturation_status)}</p>
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">Peso</p>
              <p className="mt-0.5 text-sm font-semibold text-charcoal">
                {weightFormatted ? `${weightFormatted} kg` : "—"}
              </p>
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
                Última medición
              </p>
              <p className="mt-0.5 text-sm text-charcoal">
                {formatDate(athlete.latest_anthropometry_date!)}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-mid-gray">Sin mediciones registradas</p>
        )}
      </div>

      {/* Footer — indicador visual de navegación */}
      <div
        className="flex items-center justify-between px-5 py-3"
        style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
      >
        <span className="text-sm font-medium text-link-blue">Ver detalle</span>
        <ArrowRight size={14} className="text-link-blue" />
      </div>
    </Link>
  );
}
