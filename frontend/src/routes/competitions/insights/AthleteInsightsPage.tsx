/**
 * AthleteInsightsPage — análisis IA longitudinal por deportista (PR3).
 *
 * Ruta: /competitions/insights/athletes/:id
 * Acceso: coach + admin (parents → redirect por ProtectedRoute).
 *
 * Reutiliza `AthleteAIAnalysisTab` en modo coach. NO duplica la lógica del
 * tab del perfil de atleta; lo monta dentro del contexto /competitions.
 *
 * PR7: import directo (el barrel transitorio `components/competitions/insights`
 * fue eliminado en la deprecación final).
 */
import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft } from "lucide-react";

import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAthlete } from "@/hooks/athletes/useAthlete";

export function AthleteInsightsPage() {
  const { id } = useParams<{ id: string }>();
  const athleteId = Number(id);
  const validId = !Number.isNaN(athleteId) && athleteId > 0;

  const { data: athlete, isLoading, isError, refetch } = useAthlete(
    athleteId,
    validId,
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-6">
      <header className="space-y-1">
        <Link
          to="/competitions/insights"
          className="inline-flex items-center gap-1.5 text-sm text-mid-gray transition-colors hover:text-charcoal"
          data-testid="back-to-insights"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Análisis IA
        </Link>
        <h1
          className="font-display text-2xl text-charcoal"
        >
          {athlete
            ? `${athlete.first_name} ${athlete.last_name}`
            : "Análisis del deportista"}
        </h1>
        <p className="text-sm text-mid-gray">
          Evolución longitudinal e insights IA del deportista.
        </p>
      </header>

      {!validId && (
        <div
          className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4"
          role="alert"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-red-500" aria-hidden="true" />
          <p className="text-sm text-red-700">ID de deportista inválido.</p>
        </div>
      )}

      {validId && isLoading && (
        <div className="space-y-3" data-testid="athlete-insights-loading">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {validId && isError && !isLoading && (
        <div
          className="flex flex-col items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-6"
          role="alert"
          data-testid="athlete-insights-error"
        >
          <p className="text-sm text-red-700">
            No se pudo cargar el deportista.
          </p>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            Reintentar
          </Button>
        </div>
      )}

      {validId && !isLoading && !isError && athlete && (
        <AthleteAIAnalysisTab athlete={athlete} mode="coach" />
      )}
    </div>
  );
}

export default AthleteInsightsPage;
