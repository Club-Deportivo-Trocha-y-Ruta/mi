/**
 * ObservationsList — "Lo que vio el entrenador": hasta 3 observaciones
 * grounded (claim + evidencia numérica) que reemplazan las viejas
 * Fortalezas / Área a desarrollar / Hito (feature 038, T301, AC-2.1/2.2).
 */
import { Award, Bike, Flame, TrendingUp, Users, type LucideIcon } from "lucide-react";

import type { Observation, StageBlockRef } from "@/types/stageLog.types";

export interface ObservationsListProps {
  observations: Observation[];
}

const BLOCK_REF_ICONS: Record<StageBlockRef, LucideIcon> = {
  attendance: Users,
  technical: TrendingUp,
  race: Award,
  badges: Award,
  streak: Flame,
};

export function ObservationsList({ observations }: ObservationsListProps) {
  if (observations.length === 0) return null;

  return (
    <section aria-label="Lo que vio el entrenador" data-testid="observations-list">
      <h3 className="font-display text-base font-semibold text-charcoal">
        Lo que vio el entrenador
      </h3>
      <ul className="mt-2 space-y-3" role="list">
        {observations.map((obs, idx) => {
          const Icon = BLOCK_REF_ICONS[obs.block_ref] ?? Bike;
          return (
            <li key={idx} className="flex items-start gap-3">
              <span
                className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-light-gray text-charcoal"
                aria-hidden="true"
              >
                <Icon size={14} />
              </span>
              <div className="min-w-0">
                <p className="text-sm leading-relaxed text-charcoal">{obs.claim}</p>
                <p className="mt-0.5 text-xs text-mid-gray">{obs.evidence}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
