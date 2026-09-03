/**
 * CoachNote — "Nota del entrenador": texto libre opcional en primera
 * persona (feature 038, T301, AC-4.3). Ya pasó el guard de redacción de
 * nombres en el backend antes de persistirse.
 */
import { PenLine } from "lucide-react";

export interface CoachNoteProps {
  note: string;
}

export function CoachNote({ note }: CoachNoteProps) {
  return (
    <section
      className="rounded-xl border border-dashed border-[rgba(34,42,53,0.15)] bg-white p-4"
      aria-label="Nota del entrenador"
      data-testid="coach-note"
    >
      <h3 className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-mid-gray">
        <PenLine size={13} aria-hidden="true" />
        Nota del entrenador
      </h3>
      <p className="mt-1.5 text-sm italic leading-relaxed text-charcoal">{note}</p>
    </section>
  );
}
