/**
 * BadgesRow — "Insignias": insignias ganadas en el mes (feature 038,
 * T301). SIEMPRE muestra `badge.label` (texto legible en español, p. ej.
 * "Asistencia 90 %") — el `badge.code` (p. ej. `attendance_90`) es
 * exclusivamente una clave interna y nunca se renderiza como texto
 * visible (024/033: los códigos crudos no son un texto de producto).
 */
import { Award, Compass, Flag, Flame, MapPin, Star, type LucideIcon } from "lucide-react";

import type { BadgeView } from "@/types/stageLog.types";

export interface BadgesRowProps {
  badges: BadgeView[];
}

const BADGE_ICONS: Record<string, LucideIcon> = {
  flag: Flag,
  award: Award,
  flame: Flame,
  star: Star,
  "map-pin": MapPin,
  compass: Compass,
};

export function BadgesRow({ badges }: BadgesRowProps) {
  if (badges.length === 0) return null;

  return (
    <section aria-label="Insignias" data-testid="badges-row">
      <h3 className="font-display text-base font-semibold text-charcoal">Insignias</h3>
      <div className="mt-2 flex flex-wrap gap-2">
        {badges.map((badge) => {
          const Icon = BADGE_ICONS[badge.icon] ?? Award;
          return (
            <div
              key={badge.code}
              className="flex items-center gap-1.5 rounded-full border border-primary/20 bg-light-gray px-3 py-1.5"
              data-testid="badge-chip"
            >
              <Icon size={13} className="text-primary" aria-hidden="true" />
              <span className="text-xs font-medium text-charcoal">{badge.label}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
