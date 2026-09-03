/**
 * NextSegment — "Próximo tramo": focos técnicos planeados + próxima
 * válida (feature 038, T301).
 */
import { Calendar, Flag, Target } from "lucide-react";

import { formatDayMonth } from "@/lib/datetime";
import type { NextSegment as NextSegmentData } from "@/types/stageLog.types";

export interface NextSegmentProps {
  nextSegment: NextSegmentData;
}

export function NextSegment({ nextSegment }: NextSegmentProps) {
  const hasContent =
    nextSegment.focus_groups.length > 0 ||
    nextSegment.next_race !== null ||
    !!nextSegment.text;
  if (!hasContent) return null;

  return (
    <section
      className="rounded-xl bg-white p-4 shadow-card"
      aria-label="Próximo tramo"
      data-testid="next-segment"
    >
      <h3 className="font-display flex items-center gap-2 text-base font-semibold text-charcoal">
        <Target size={16} className="text-primary" aria-hidden="true" />
        Próximo tramo
      </h3>

      {nextSegment.text && (
        <p className="mt-2 text-sm leading-relaxed text-charcoal">{nextSegment.text}</p>
      )}

      {nextSegment.focus_groups.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {nextSegment.focus_groups.map((focus) => (
            <span
              key={focus}
              className="rounded-full bg-light-gray px-2.5 py-0.5 text-xs font-medium text-charcoal"
            >
              {focus}
            </span>
          ))}
        </div>
      )}

      {nextSegment.next_race && (
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-light-gray/50 px-3 py-2">
          <Calendar size={14} className="mt-0.5 shrink-0 text-mid-gray" aria-hidden="true" />
          <div className="min-w-0 text-sm">
            <p className="font-medium text-charcoal">{nextSegment.next_race.label}</p>
            <p className="text-xs text-mid-gray">
              {formatDayMonth(nextSegment.next_race.date)}
              {nextSegment.next_race.venue ? ` · ${nextSegment.next_race.venue}` : ""}
            </p>
            {nextSegment.next_race.priority_label && (
              <p className="mt-0.5 flex items-center gap-1 text-xs text-mid-gray">
                <Flag size={11} aria-hidden="true" />
                {nextSegment.next_race.priority_label}
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
