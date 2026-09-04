/**
 * GrowthAlerts — avisos activos del resumen de crecimiento (feature 040,
 * US2, T039), per `contracts/growth-tab-ui.md`: filas `Alert` de shadcn
 * (ícono + texto), "misma copia que el dashboard".
 *
 * Sólo traduce a mensaje los tres códigos que además existen en el
 * vocabulario de alertas del dashboard (`types/alerts.types.ts::GrowthAlert`
 * — `rapid_growth` / `approaching_circa` / `phase_changed`, exactamente el
 * subconjunto de 3 de los 6 códigos de `GrowthSummaryAlert` que menciona el
 * comentario de `growth.schemas.ts`). `circa_phv` / `height_p3` / `bmi_p3`
 * NO se repiten aquí: ya se muestran en el bloque propio de
 * `TrainingReadiness.tsx` (`buildAlertsFromSummary`, misma redacción), que
 * documenta explícitamente esta división de responsabilidad para no
 * duplicar el mismo aviso dos veces en la pestaña. Recibe `summary.alerts`
 * completo (los 6 códigos posibles) y filtra en silencio los que no le
 * corresponden — el llamador (`GrowthTab`, T041) no necesita recortar el
 * arreglo.
 *
 * `rapid_growth` reutiliza el título de `dashboard/MeasurementAlerts.tsx`
 * ("Crecimiento acelerado detectado"). `approaching_circa` / `phase_changed`
 * no tenían copia propia en ninguna superficie existente (el dashboard sólo
 * los cuenta, no los redacta) — se definen aquí por primera vez, en español
 * neutro con diacríticos.
 *
 * Orden fijo (no el orden en que el backend arma la lista): crecimiento
 * acelerado primero (más accionable hoy), luego acercamiento al estirón,
 * luego cambio de etapa (el más informativo).
 */
import { AlertTriangle, Info } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import type { GrowthSummaryAlert } from "@/types/growth.types";

export interface GrowthAlertsProps {
  alerts: GrowthSummaryAlert[];
}

type AlertVariant = "default" | "warning" | "destructive";

interface AlertCopy {
  variant: AlertVariant;
  icon: LucideIcon;
  message: string;
}

/** Sólo los 3 códigos compartidos con el dashboard — ver docstring del módulo. */
type DashboardSharedAlert = "rapid_growth" | "approaching_circa" | "phase_changed";

const ALERT_COPY: Record<DashboardSharedAlert, AlertCopy> = {
  rapid_growth: {
    variant: "warning",
    icon: AlertTriangle,
    message: "Crecimiento acelerado detectado (≥ 0.6 cm/mes). Revisar la carga de entrenamiento.",
  },
  approaching_circa: {
    variant: "warning",
    icon: AlertTriangle,
    message: "Se acerca al estirón de crecimiento (Circa-PHV). Prepara la transición del plan de entrenamiento.",
  },
  phase_changed: {
    variant: "default",
    icon: Info,
    message: "Cambió de etapa de maduración desde la última medición. Revisa las reglas de entrenamiento vigentes.",
  },
};

/** Orden de despliegue fijo — ver docstring del módulo. */
const ALERT_ORDER: DashboardSharedAlert[] = ["rapid_growth", "approaching_circa", "phase_changed"];

function isDashboardSharedAlert(code: GrowthSummaryAlert): code is DashboardSharedAlert {
  return code === "rapid_growth" || code === "approaching_circa" || code === "phase_changed";
}

export function GrowthAlerts({ alerts }: GrowthAlertsProps) {
  const present = new Set(alerts.filter(isDashboardSharedAlert));
  const ordered = ALERT_ORDER.filter((code) => present.has(code));

  if (ordered.length === 0) return null;

  return (
    <div data-testid="growth-alerts" className="flex flex-col gap-2">
      {ordered.map((code) => {
        const { variant, icon: Icon, message } = ALERT_COPY[code];
        return (
          <Alert key={code} variant={variant}>
            <Icon aria-hidden="true" />
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        );
      })}
    </div>
  );
}
