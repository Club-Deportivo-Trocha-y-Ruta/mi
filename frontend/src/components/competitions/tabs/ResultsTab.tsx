/**
 * ResultsTab — resultados de la válida.
 *
 * Muestra el estado de los resultados importados. Si no hay resultados,
 * ofrece CTA para importar. Si los hay, invita al análisis profundo
 * (InsightsTab) y al módulo de análisis de carreras.
 *
 * Nota: no existe actualmente un endpoint granular de resultados por válida
 * en el frontend. Este tab actúa como hub de navegación contextual hasta
 * que CF6+ exponga un endpoint de race_results por race_event_id.
 *
 * Props:
 *   - `raceEventId: number` — ID del evento.
 *   - `hasResults?: boolean` — si la válida tiene resultados importados.
 *     Si no se pasa (undefined), muestra estado neutro.
 *   - `onNavigateToInsights?: () => void` — callback para navegar al tab Insights.
 */
import { Link } from "react-router-dom";
import { BarChart2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ResultsTabProps {
  raceEventId: number;
  hasResults?: boolean;
  onNavigateToInsights?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ResultsTab({
  raceEventId,
  hasResults,
  onNavigateToInsights,
}: ResultsTabProps) {
  // ── Sin resultados ────────────────────────────────────────────────────────
  if (hasResults === false) {
    return (
      <div
        className="flex min-h-[28vh] flex-col items-center justify-center gap-4 rounded-xl bg-white p-8 text-center"
        style={{
          boxShadow:
            "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
        }}
        data-testid="results-tab-empty"
      >
        <Upload
          size={36}
          className="text-mid-gray"
          aria-hidden="true"
        />
        <div className="space-y-1">
          <p className="text-sm font-semibold text-charcoal">
            Sin resultados importados
          </p>
          <p className="text-xs text-mid-gray">
            Importa el PDF oficial de la Copa Valle para ver los resultados de
            esta válida.
          </p>
        </div>
        <Link
          to={`/competitions/${raceEventId}/import`}
          className={buttonVariants({ variant: "default" })}
        >
          Importar resultados
        </Link>
      </div>
    );
  }

  // ── Con resultados ────────────────────────────────────────────────────────
  if (hasResults === true) {
    return (
      <div
        className="space-y-4 rounded-xl bg-white p-6"
        style={{
          boxShadow:
            "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
        }}
        data-testid="results-tab-available"
      >
        <div className="flex items-center gap-3">
          <BarChart2
            size={20}
            className="text-emerald-600"
            aria-hidden="true"
          />
          <p className="text-sm font-semibold text-charcoal">
            Resultados importados
          </p>
        </div>
        <p className="text-sm text-mid-gray">
          Los resultados de esta válida están disponibles. Consulta los
          insights IA para ver el análisis detallado por atleta o accede al
          módulo de análisis de carreras para el pipeline completo.
        </p>
        <div className="flex flex-wrap gap-3">
          {onNavigateToInsights && (
            <Button variant="outline" onClick={onNavigateToInsights}>
              Ver insights IA
            </Button>
          )}
          <Link
            to="/coach/race-analysis"
            className={buttonVariants({ variant: "outline" })}
          >
            Módulo de análisis
          </Link>
        </div>
      </div>
    );
  }

  // ── Estado indeterminado ──────────────────────────────────────────────────
  return (
    <div
      className="flex min-h-[20vh] items-center justify-center rounded-xl bg-white p-6 text-center"
      style={{
        boxShadow:
          "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
      }}
      data-testid="results-tab-unknown"
    >
      <p className="text-sm text-mid-gray">
        Estado de resultados no disponible.
      </p>
    </div>
  );
}
