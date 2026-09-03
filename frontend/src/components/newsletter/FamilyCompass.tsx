/**
 * FamilyCompass — "Brújula de la familia" (antes "Rincón de la familia"):
 * pregunta para conversar, reto del mes y qué observar en la próxima
 * válida (feature 038, T301). Reemplaza los tips genéricos rotados
 * deterministamente de 024.
 */
import { Compass, Eye, MessageCircle } from "lucide-react";

import type { FamilyCompass as FamilyCompassData } from "@/types/stageLog.types";

export interface FamilyCompassProps {
  compass: FamilyCompassData;
}

export function FamilyCompass({ compass }: FamilyCompassProps) {
  return (
    <section
      className="rounded-xl bg-white p-4 shadow-card"
      aria-label="Brújula de la familia"
      data-testid="family-compass"
    >
      <h3 className="font-display flex items-center gap-2 text-base font-semibold text-charcoal">
        <Compass size={16} className="text-primary" aria-hidden="true" />
        Brújula de la familia
      </h3>
      <ul className="mt-2 space-y-3" role="list">
        <li className="flex items-start gap-2">
          <MessageCircle size={14} className="mt-0.5 shrink-0 text-mid-gray" aria-hidden="true" />
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
              Para conversar
            </p>
            <p className="text-sm text-charcoal">{compass.conversation_question}</p>
          </div>
        </li>
        <li className="flex items-start gap-2">
          <Compass size={14} className="mt-0.5 shrink-0 text-mid-gray" aria-hidden="true" />
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
              Reto del mes
            </p>
            <p className="text-sm text-charcoal">{compass.monthly_challenge}</p>
          </div>
        </li>
        <li className="flex items-start gap-2">
          <Eye size={14} className="mt-0.5 shrink-0 text-mid-gray" aria-hidden="true" />
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-mid-gray">
              Qué observar
            </p>
            <p className="text-sm text-charcoal">{compass.what_to_watch}</p>
          </div>
        </li>
      </ul>
    </section>
  );
}
