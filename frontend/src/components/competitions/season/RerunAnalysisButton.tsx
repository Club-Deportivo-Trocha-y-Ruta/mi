/**
 * RerunAnalysisButton / RerunSeasonSummaryButton — «Re-ejecutar» un análisis
 * desactualizado desde la lista de «Temporada» (feature 045, US5, T057).
 *
 * - `RerunAnalysisButton` (ítems `kind="valida"`): reutiliza el lanzamiento
 *   existente (`useLaunchAthleteAnalysis`, mismo
 *   `POST /athletes/{id}/race-analysis/runs` que `AnalyzeAthleteButton`) con
 *   `event_id` como ancla: el backend deriva la válida del evento. La
 *   temporada viene del ítem pendiente (`season`, exacta: la del
 *   `race_series`); solo si llega `null` (o un backend previo al campo) se cae
 *   al año de la fecha del evento (`useRaceEvent`, que se consulta únicamente
 *   en ese caso).
 * - `RerunSeasonSummaryButton` (ítems `kind="season_summary"`): reutiliza
 *   `useGenerateSeasonSummary` (`POST /athletes/{id}/race-analysis/season-summary`)
 *   con la `season` exacta del ítem — sin ella el backend resumiría el año
 *   actual, que puede no ser el del análisis desactualizado. El backend exige
 *   ≥3 válidas aprobadas; si no las hay responde 422 y su mensaje se muestra
 *   inline.
 *
 * Estados (ambos): reposo → lanzando → «iniciado» (el desenlace lo sigue
 * `useAthleteRunOutcome`, que avisa con un toast y refresca la lista al
 * terminar) | error inline. Presupuesto de IA agotado → deshabilitado.
 *
 * Privacidad: `displayName` (el `athlete_ref` que la UI del coach ya muestra)
 * solo alimenta el nombre accesible y el toast existente de
 * `useAthleteRunOutcome`; nunca se registra en un log.
 */
import { useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Sparkles } from "lucide-react";

import { AI_BUDGET_EXHAUSTED_MESSAGE, isBudgetExhausted } from "@/components/ai/AIBudgetHint";
import { getAiErrorMessage } from "@/components/competitions/insights/AnalyzeAthleteButton";
import { Button } from "@/components/ui/button";
import { useAIStatus } from "@/hooks/ai/useAIStatus";
import { useAthleteRunOutcome } from "@/hooks/ai/useAthleteRunOutcome";
import { useGenerateSeasonSummary } from "@/hooks/athletes/useGenerateSeasonSummary";
import { useLaunchAthleteAnalysis } from "@/hooks/athletes/useLaunchAthleteAnalysis";
import { useRaceEvent } from "@/hooks/race/useRaceEvents";
import { extractErrorDetail } from "@/lib/apiError";

const SEASON_SUMMARY_ERROR_FALLBACK = "No se pudo iniciar el resumen de temporada. Intenta de nuevo.";

// ---------------------------------------------------------------------------
// Vista compartida
// ---------------------------------------------------------------------------

interface RerunControlProps {
  athleteId: number;
  displayName: string;
  /** Prefijo de los `data-testid` (`{prefix}-btn|started|error-{athleteId}`). */
  testIdPrefix: string;
  /** Complemento del nombre accesible: «el análisis» | «el resumen de temporada». */
  subject: string;
  startedLabel: string;
  isPending: boolean;
  /** Sin datos para lanzar (p. ej. temporada aún desconocida). */
  unavailable: boolean;
  budgetExhausted: boolean;
  started: boolean;
  error: string | null;
  onClick: () => void;
}

function RerunControl({
  athleteId,
  displayName,
  testIdPrefix,
  subject,
  startedLabel,
  isPending,
  unavailable,
  budgetExhausted,
  started,
  error,
  onClick,
}: RerunControlProps) {
  if (started) {
    return (
      <p
        role="status"
        className="flex min-h-12 items-center gap-1.5 text-sm text-emerald-700"
        data-testid={`${testIdPrefix}-started-${athleteId}`}
      >
        <CheckCircle2 size={16} aria-hidden="true" />
        {startedLabel}
      </p>
    );
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        type="button"
        variant="outline"
        className="min-h-12"
        onClick={onClick}
        disabled={isPending || unavailable || budgetExhausted}
        aria-label={
          budgetExhausted
            ? `${AI_BUDGET_EXHAUSTED_MESSAGE} No se puede re-ejecutar ${subject} de ${displayName}.`
            : `Re-ejecutar ${subject} de ${displayName}`
        }
        data-testid={`${testIdPrefix}-btn-${athleteId}`}
      >
        {isPending ? (
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
        ) : (
          <Sparkles size={16} aria-hidden="true" />
        )}
        Re-ejecutar
      </Button>
      {error && (
        <p
          role="alert"
          className="flex max-w-[260px] items-start gap-1.5 text-xs text-danger"
          data-testid={`${testIdPrefix}-error-${athleteId}`}
        >
          <AlertCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Válida
// ---------------------------------------------------------------------------

export interface RerunAnalysisButtonProps {
  athleteId: number;
  eventId: number;
  /** Temporada del ítem pendiente; `null`/ausente → se deriva del evento. */
  season?: number | null;
  displayName: string;
}

/** Temporada de un evento: el año de su fecha (`YYYY-MM-DD…`); `null` si no se puede leer. */
function seasonOf(eventDate: string | undefined): number | null {
  const year = Number(eventDate?.slice(0, 4));
  return Number.isInteger(year) && year >= 2000 ? year : null;
}

export function RerunAnalysisButton({
  athleteId,
  eventId,
  season: seasonProp,
  displayName,
}: RerunAnalysisButtonProps) {
  // Respaldo: solo se consulta el evento cuando el ítem no trae la temporada.
  const eventQuery = useRaceEvent(seasonProp == null ? eventId : null);
  const season = seasonProp ?? seasonOf(eventQuery.data?.event_date);

  const launch = useLaunchAthleteAnalysis(athleteId);
  const aiStatus = useAIStatus();
  const budgetExhausted = isBudgetExhausted(aiStatus.data);

  const [runId, setRunId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const { failureMessage } = useAthleteRunOutcome(runId, { athleteId, displayName });
  const shownError = errorMsg ?? failureMessage;

  function handleClick() {
    if (season === null || budgetExhausted) return;
    setErrorMsg(null);
    setRunId(null);
    launch.mutate(
      { season, event_id: eventId },
      {
        onSuccess: (res) => setRunId(res.run_id),
        onError: (err) => setErrorMsg(getAiErrorMessage(err)),
      },
    );
  }

  return (
    <RerunControl
      athleteId={athleteId}
      displayName={displayName}
      testIdPrefix="pending-rerun"
      subject="el análisis"
      startedLabel="Análisis iniciado"
      isPending={launch.isPending}
      unavailable={season === null}
      budgetExhausted={budgetExhausted}
      started={Boolean(runId) && !shownError}
      error={shownError}
      onClick={handleClick}
    />
  );
}

// ---------------------------------------------------------------------------
// Resumen de temporada
// ---------------------------------------------------------------------------

export interface RerunSeasonSummaryButtonProps {
  athleteId: number;
  /** Temporada exacta del resumen desactualizado (obligatoria: no se deduce). */
  season: number;
  displayName: string;
}

export function RerunSeasonSummaryButton({
  athleteId,
  season,
  displayName,
}: RerunSeasonSummaryButtonProps) {
  const launch = useGenerateSeasonSummary(athleteId, season);
  const aiStatus = useAIStatus();
  const budgetExhausted = isBudgetExhausted(aiStatus.data);

  const [runId, setRunId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const { failureMessage } = useAthleteRunOutcome(runId, { athleteId, displayName });
  const shownError = errorMsg ?? failureMessage;

  function handleClick() {
    if (budgetExhausted) return;
    setErrorMsg(null);
    setRunId(null);
    launch.mutate(undefined, {
      onSuccess: (res) => setRunId(res.run_id),
      onError: (err) => setErrorMsg(extractErrorDetail(err, SEASON_SUMMARY_ERROR_FALLBACK)),
    });
  }

  return (
    <RerunControl
      athleteId={athleteId}
      displayName={displayName}
      testIdPrefix="pending-rerun-season"
      subject="el resumen de temporada"
      startedLabel="Resumen de temporada iniciado"
      isPending={launch.isPending}
      unavailable={false}
      budgetExhausted={budgetExhausted}
      started={Boolean(runId) && !shownError}
      error={shownError}
      onClick={handleClick}
    />
  );
}
