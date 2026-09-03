/**
 * AnalystPicker — lista los insights de carrera aprobados adjuntados al
 * boletín (`selected_race_insight_ids`) y permite reordenarlos; el primer
 * insight elegible del orden es el que el builder usa para
 * `analyst_reading` (spec.md AC-3.1, contracts/api.md §Coach PATCH).
 *
 * El PATCH solo admite una permutación exacta del multiset ya guardado —
 * este componente nunca agrega ni quita ids (eso es `attach-insights`,
 * fuera del estudio).
 */
import { ArrowDown, ArrowUp } from "lucide-react";

import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { validaLabel } from "@/lib/insights";
import { cn } from "@/lib/utils";

export interface AnalystPickerProps {
  athleteId: number;
  /** Orden actual guardado en el boletín (`newsletter.selected_race_insight_ids`). */
  selectedInsightIds: number[];
  onReorder: (newOrder: number[]) => void;
  isSaving?: boolean;
}

export function AnalystPicker({
  athleteId,
  selectedInsightIds,
  onReorder,
  isSaving = false,
}: AnalystPickerProps) {
  const insightsQuery = useAthleteInsights(athleteId, { limit: 50 });
  const insightsById = new Map(
    (insightsQuery.data?.items ?? []).map((insight) => [insight.id, insight]),
  );

  if (selectedInsightIds.length === 0) {
    return (
      <div className="rounded-xl bg-white px-4 py-3 shadow-card" data-testid="analyst-picker-empty">
        <h3 className="text-sm font-semibold text-charcoal">Análisis adjuntado</h3>
        <p className="mt-1 text-xs text-mid-gray">
          No hay insights de carrera adjuntados a este boletín. Adjúntalos desde el
          tab Análisis IA del atleta.
        </p>
      </div>
    );
  }

  function moveItem(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= selectedInsightIds.length) return;
    const next = [...selectedInsightIds];
    [next[index], next[target]] = [next[target], next[index]];
    onReorder(next);
  }

  return (
    <div className="rounded-xl bg-white px-4 py-3 shadow-card" data-testid="analyst-picker">
      <h3 className="text-sm font-semibold text-charcoal">Análisis adjuntado</h3>
      <p className="mt-1 text-xs text-mid-gray">
        El primero elegible es el que se traduce en "Lectura del analista". Solo el
        titular y la acción principal llegan a la familia — nunca percentiles,
        posiciones esperadas ni la lectura técnica completa.
      </p>

      <ol className="mt-3 space-y-2" data-testid="analyst-picker-list">
        {selectedInsightIds.map((id, index) => {
          const insight = insightsById.get(id);
          const label = insight?.headline || `Insight #${id}`;
          const sublabel = insight ? validaLabel(insight) : null;

          return (
            <li
              key={id}
              className={cn(
                "flex items-start justify-between gap-2 rounded-lg px-3 py-2 shadow-ring",
                index === 0 && "border border-primary/30",
              )}
              data-testid={`analyst-picker-item-${id}`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-charcoal">{label}</p>
                {sublabel && <p className="text-xs text-mid-gray">{sublabel}</p>}
                {index === 0 && (
                  <p className="text-xs font-medium text-primary">Usado en la bitácora</p>
                )}
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  onClick={() => moveItem(index, -1)}
                  disabled={index === 0 || isSaving}
                  aria-label={`Subir ${label}`}
                  className="rounded p-1 text-charcoal transition-opacity hover:opacity-70 disabled:opacity-30"
                >
                  <ArrowUp size={14} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => moveItem(index, 1)}
                  disabled={index === selectedInsightIds.length - 1 || isSaving}
                  aria-label={`Bajar ${label}`}
                  className="rounded p-1 text-charcoal transition-opacity hover:opacity-70 disabled:opacity-30"
                >
                  <ArrowDown size={14} aria-hidden="true" />
                </button>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
