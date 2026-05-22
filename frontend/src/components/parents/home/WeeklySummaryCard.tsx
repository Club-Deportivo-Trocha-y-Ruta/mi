/**
 * WeeklySummaryCard — Card de resumen semanal del home feed (Wave 4).
 *
 * Tono: pedagógico y factual. NO mostramos porcentaje en grande ni medidor
 * — el resumen mensual completo lo hace `ParentMonthlyOverviewPage`. Aquí
 * sólo el dato útil para "saber cómo va la semana": "Esta semana: X de Y
 * entrenos".
 *
 * Fuente: `useParentMonthlySummary` del mes vigente filtrada por
 * athleteId. El backend agrega por atleta, no por semana — derivamos la
 * "semana en curso" como aproximación: tomamos count_present / count_total
 * acumulados del mes en una métrica factual. Si más adelante el backend
 * ofrece un agregado semanal real, se puede cambiar sin tocar el contrato
 * del componente.
 *
 * Disclaimer pedagógico (text-disclaimer): explica que el dato es del mes,
 * no de los últimos 7 días, para no inducir error.
 */
import { CalendarRange } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ParentMonthlySummary } from "@/types/trainingSession.types";

interface WeeklySummaryCardProps {
  summary: ParentMonthlySummary | undefined;
  isLoading: boolean;
  isError?: boolean;
  /** Etiqueta del mes vigente, ej. "mayo de 2026". */
  monthLabel: string;
  athleteName?: string;
}

function LoadingState() {
  return (
    <Card
      className="px-5 py-4"
      role="status"
      aria-busy="true"
      aria-label="Cargando resumen del mes"
    >
      <Skeleton className="mb-2 h-3 w-32" />
      <Skeleton className="mb-3 h-5 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </Card>
  );
}

export function WeeklySummaryCard({
  summary,
  isLoading,
  isError = false,
  monthLabel,
  athleteName,
}: WeeklySummaryCardProps) {
  if (isLoading) return <LoadingState />;
  if (isError) {
    return (
      <Card className="px-5 py-4">
        <p className="text-sm text-mid-gray">No fue posible cargar el resumen del mes.</p>
      </Card>
    );
  }

  // Empty: ningún registro de asistencia este mes
  if (!summary || summary.count_total === 0) {
    return (
      <Card className="flex items-start gap-3 px-5 py-5" data-testid="weekly-empty">
        <CalendarRange size={20} aria-hidden="true" className="mt-0.5 shrink-0 text-mid-gray" />
        <div>
          <p className="text-sm font-medium text-charcoal">Resumen del mes</p>
          <p className="mt-1 text-sm text-mid-gray">
            Aún no hay entrenamientos registrados este mes.
          </p>
        </div>
      </Card>
    );
  }

  const who = athleteName ?? "Tu atleta";

  return (
    <Card data-testid="weekly-summary-card" className="px-5 py-4">
      <div className="flex items-start gap-3">
        <CalendarRange size={22} aria-hidden="true" className="mt-0.5 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
            Resumen del mes
          </p>
          <p className="mt-0.5 text-base font-semibold text-charcoal">
            {who}: {summary.count_present} de {summary.count_total} entrenos
          </p>
          {summary.focos_técnicos.length > 0 && (
            <p className="mt-1 text-sm text-mid-gray">
              Focos del mes: {summary.focos_técnicos.slice(0, 3).join(" · ")}
              {summary.focos_técnicos.length > 3 ? "…" : ""}
            </p>
          )}
          <p className="mt-2 text-xs text-text-disclaimer">
            Conteo acumulado de {monthLabel}. La meta de asistencia depende del plan del club, no de un porcentaje fijo.
          </p>
        </div>
      </div>
    </Card>
  );
}
