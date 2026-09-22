/**
 * SeasonCompletionChips — "2025 · 6 de 7" por temporada (feature 044, US6).
 *
 * Parte del bloque "texto primero" de `HistoryProgressionCard`: no depende
 * de recharts, se renderiza como DOM plano antes de que llegue el chunk de
 * la gráfica (presupuesto 3G, `ui-history.md` §1).
 */
import { cn } from "@/lib/utils";
import type { RaceHistorySeasonCompletion } from "@/types/raceHistory.types";

export interface SeasonCompletionChipsProps {
  seasons: RaceHistorySeasonCompletion[];
  className?: string;
}

export function SeasonCompletionChips({
  seasons,
  className,
}: SeasonCompletionChipsProps) {
  if (seasons.length === 0) return null;

  // Orden cronológico ascendente — la narrativa de la tarjeta es "cómo
  // progresó de una temporada a la siguiente", no un selector.
  const ordered = [...seasons].sort((a, b) => a.season - b.season);

  return (
    <ul
      className={cn("flex flex-wrap gap-2", className)}
      aria-label="Válidas corridas por temporada"
      data-testid="season-completion-chips"
    >
      {ordered.map((s) => (
        <li
          key={s.season}
          className="rounded-full bg-light-gray/50 px-3 py-1 text-xs font-medium text-charcoal ring-1 ring-[rgba(34,42,53,0.08)]"
          data-testid={`season-completion-chip-${s.season}`}
        >
          {s.season} · {s.finished} de {s.started}
        </li>
      ))}
    </ul>
  );
}
