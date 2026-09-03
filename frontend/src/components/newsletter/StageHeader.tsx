/**
 * StageHeader — encabezado de la bitácora de etapa (feature 038, T301).
 *
 * "Etapa N · Mes Año" (eyebrow) + título de la etapa (Cal Sans). Cuando
 * `isCurrentMonth` es true muestra "Etapa en curso" — nunca solo color,
 * siempre ícono + texto (StatusBadge, tono neutral: un mes en curso no es
 * un error ni un éxito, es informativo).
 */
import { CalendarClock } from "lucide-react";

import { StatusBadge } from "@/components/shared/StatusBadge";

export interface StageHeaderProps {
  stageNumber: number;
  periodLabel: string;
  isCurrentMonth: boolean;
  stageTitle: string;
}

export function StageHeader({
  stageNumber,
  periodLabel,
  isCurrentMonth,
  stageTitle,
}: StageHeaderProps) {
  return (
    <header className="space-y-1.5" data-testid="stage-header">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-mid-gray">
          Etapa {stageNumber} · {periodLabel}
        </span>
        {isCurrentMonth && (
          <StatusBadge
            status="neutral"
            label="Etapa en curso"
            icon={CalendarClock}
          />
        )}
      </div>
      <h2 className="font-display text-xl font-semibold leading-tight text-charcoal sm:text-2xl">
        {stageTitle}
      </h2>
    </header>
  );
}
