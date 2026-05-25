/**
 * SuggestionCard — card de sugerencia top-N fuzzy.
 *
 * Renderiza una sugerencia de athlete con su score (barra de confianza
 * + label) y un CTA "Enlazar". Extraído de UnlinkedCompetitorsTab en B5.
 */
import { Link2, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AthleteSuggestion } from "@/types/raceCompetitors.types";
import { scoreColor } from "./scoreColor";

function ScoreBar({ score }: { score: number }) {
  const palette = scoreColor(score);
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  return (
    <div className="space-y-1">
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-light-gray/60"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Score de match: ${pct}%`}
      >
        <div
          className={cn("h-full transition-all", palette.bar)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex items-center justify-between text-[10px]">
        <span className={cn("font-medium", palette.text)}>{palette.label}</span>
        <span className="font-mono text-mid-gray">{pct}%</span>
      </div>
    </div>
  );
}

export interface SuggestionCardProps {
  suggestion: AthleteSuggestion;
  isLinking: boolean;
  onLink: (athleteId: number) => void;
  testId: string;
}

export function SuggestionCard({
  suggestion,
  isLinking,
  onLink,
  testId,
}: SuggestionCardProps) {
  const palette = scoreColor(suggestion.score);
  return (
    <div
      data-testid={testId}
      className={cn(
        "flex flex-col gap-2 rounded-lg p-3 ring-1 ring-light-gray",
        palette.bg,
      )}
    >
      <div className="space-y-0.5">
        <p
          className="truncate text-sm text-charcoal font-heading"
          title={suggestion.full_name}
        >
          {suggestion.full_name}
        </p>
        <p className="line-clamp-2 text-[11px] text-mid-gray" title={suggestion.reason}>
          {suggestion.reason}
        </p>
      </div>
      <ScoreBar score={suggestion.score} />
      <button
        type="button"
        onClick={() => onLink(suggestion.athlete_id)}
        disabled={isLinking}
        data-testid={`${testId}-link-btn`}
        className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isLinking ? (
          <Loader2 size={12} className="animate-spin" aria-hidden="true" />
        ) : (
          <Link2 size={12} aria-hidden="true" />
        )}
        Enlazar
      </button>
    </div>
  );
}
