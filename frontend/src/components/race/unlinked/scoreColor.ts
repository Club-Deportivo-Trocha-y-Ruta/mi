/**
 * Paleta visual de un score de match (0-1) — usado por
 * `SuggestionCard` y `ScoreBar` para reflejar la confianza del fuzzy match.
 *
 * Extraído del top-level de UnlinkedCompetitorsTab durante el refactor B5
 * para que los sub-componentes (`SuggestionCard`, `ScoreBar`) lo importen
 * sin acoplamiento circular.
 */
export interface ScorePalette {
  bg: string;
  bar: string;
  text: string;
  label: string;
}

export function scoreColor(score: number): ScorePalette {
  if (score >= 0.85) {
    return {
      bg: "bg-emerald-50",
      bar: "bg-emerald-500",
      text: "text-emerald-700",
      label: "Alta confianza",
    };
  }
  if (score >= 0.65) {
    return {
      bg: "bg-amber-50",
      bar: "bg-amber-500",
      text: "text-amber-700",
      label: "Confianza media",
    };
  }
  return {
    bg: "bg-red-50",
    bar: "bg-red-500",
    text: "text-red-700",
    label: "Baja confianza",
  };
}
