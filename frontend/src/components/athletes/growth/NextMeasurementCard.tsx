/**
 * NextMeasurementCard — fila "Próxima medición" del tab de crecimiento
 * (feature 040, US2, T039), per `contracts/growth-tab-ui.md`: "Próxima
 * medición: {fecha} · cada {n} días en {etapa}"; insignia Vencida / Próxima
 * / Al día / Sin medir.
 *
 * La etapa no viaja en `MeasurementDue` (sólo `interval_days`), pero el
 * intervalo es una función 1:1 de la etapa (`measurement_alerts.MEASUREMENT_INTERVALS`
 * en el backend: 90 → Pre-PHV, 30 → Circa-PHV, 120 → Post-PHV) siempre que
 * `status !== "never"` — ese es el único camino que no pasa por
 * `get_measurement_interval(stage)`. Se reconstruye aquí en vez de sumar una
 * prop nueva, para no romper el contrato `NextMeasurementCard({ measurement })`.
 */
import { getMeasurementStatusMeta } from "@/lib/measurementStatus";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { MeasurementDue } from "@/types/growth.types";

export interface NextMeasurementCardProps {
  measurement: MeasurementDue;
}

const MONTHS_ES_SHORT = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/**
 * Fecha corta en español ("12 dic 2026") a partir de un `YYYY-MM-DD` plano.
 * Se parte el string en vez de `new Date(...)`: una fecha sin hora se
 * interpreta como medianoche UTC y, formateada en `America/Bogota`
 * (UTC-5), puede retroceder un día — mismo criterio que
 * `AnthropometryHistory.tsx::formatDate`.
 */
function formatDueDate(dateStr: string): string {
  const [year, month, day] = dateStr.split("-");
  const label = MONTHS_ES_SHORT[Number(month) - 1] ?? month;
  return `${Number(day)} ${label} ${year}`;
}

/** Intervalo (días) → etapa PHV — bijección de `measurement_alerts.MEASUREMENT_INTERVALS`. */
const INTERVAL_TO_STAGE: Record<number, string> = {
  90: "Pre-PHV",
  30: "Circa-PHV",
  120: "Post-PHV",
};

function formatOverdueDetail(measurement: MeasurementDue): string | null {
  if (measurement.status === "overdue" && measurement.days_overdue !== null) {
    return `${measurement.days_overdue}d de atraso`;
  }
  return null;
}

export function NextMeasurementCard({ measurement }: NextMeasurementCardProps) {
  const meta = getMeasurementStatusMeta(measurement.status);

  const bodyText =
    measurement.status === "never" || measurement.next_due_date === null
      ? "Sin medición registrada"
      : (() => {
          const stageLabel = INTERVAL_TO_STAGE[measurement.interval_days];
          const stageSuffix = stageLabel ? ` en ${stageLabel}` : "";
          return `Próxima medición: ${formatDueDate(measurement.next_due_date)} · cada ${measurement.interval_days} días${stageSuffix}`;
        })();

  const overdueDetail = formatOverdueDetail(measurement);

  return (
    <div
      data-testid="growth-next-measurement"
      className="flex min-h-12 flex-wrap items-center justify-between gap-2 rounded-xl bg-white px-4 py-3 shadow-card"
    >
      <p className="text-sm text-charcoal">
        {bodyText}
        {overdueDetail && <span className="text-mid-gray"> · {overdueDetail}</span>}
      </p>
      <StatusBadge status={meta.tone} label={meta.rowLabel} />
    </div>
  );
}
