/**
 * Vocabulario compartido de estado de medición (`MeasurementStatus`).
 *
 * Antes vivía como `STATUS_META` local en `MeasurementAlerts.tsx` — se
 * extrae aquí para que cualquier otro consumidor (otras tarjetas del
 * dashboard, el módulo de crecimiento) hable el mismo idioma de tono +
 * etiqueta sin duplicar la tabla. El tono alimenta a `StatusBadge`, que
 * siempre acompaña el color con ícono y texto (Constitution III).
 */
import type { Status } from "@/components/shared/StatusBadge";
import type { MeasurementStatus } from "@/types/alerts.types";

export type { MeasurementStatus };

export interface MeasurementStatusMeta {
  tone: Status;
  rowLabel: string;
  summaryLabel: string;
}

export const STATUS_META: Record<MeasurementStatus, MeasurementStatusMeta> = {
  overdue: { tone: "danger", rowLabel: "Vencida", summaryLabel: "vencidas" },
  due_soon: { tone: "warning", rowLabel: "Próxima", summaryLabel: "próximas" },
  ok: { tone: "success", rowLabel: "Al día", summaryLabel: "al día" },
  never: { tone: "neutral", rowLabel: "Sin medir", summaryLabel: "sin medir" },
};

export function getMeasurementStatusMeta(status: MeasurementStatus): MeasurementStatusMeta {
  return STATUS_META[status];
}
