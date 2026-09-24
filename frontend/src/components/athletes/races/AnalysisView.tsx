/**
 * AnalysisView — vista «Análisis IA» de la pestaña «Carreras» (feature 045,
 * T038). Reemplaza al cuerpo de `AthleteAIAnalysisTab` (pestaña «Insights
 * IA»), de donde vienen la recuperación de runs activos y el flujo HITL.
 *
 * Orden de arriba abajo:
 *   1. Pendiente — `AnalysisRunTimeline` + `HITLApprovalCard` (solo coach,
 *      solo si hay un run vivo: `running` o `awaiting_hitl`).
 *   2. Último análisis — `PanoramaView` (tarjetas KPI + `HeroLastInsightCard`).
 *   3. Histórico — `InsightsTimeline`; `insightId` (de `insight=` en la URL)
 *      abre ese análisis.
 *   4. Solo coach — `LaunchAnalysisForm`, `AthleteAnalystChatPanel` y
 *      `SeasonSummaryButton`.
 *
 * Privacidad (Ley 1581 + salvaguarda 045): para `audience="family"` no se
 * consultan runs, no se montan casillas de boletín, ni el lanzador, ni el chat,
 * y solo se ven análisis aprobados (el backend ya filtra por rol). La familia
 * ve siempre la etiqueta «Análisis generado con IA y revisado por el
 * entrenador.».
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { AnalysisRunTimeline } from "@/components/ai/AnalysisRunTimeline";
import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";
import { AthleteAnalystChatPanel } from "@/components/athletes/ai/AthleteAnalystChatPanel";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";
import { LaunchAnalysisForm } from "@/components/athletes/ai/LaunchAnalysisForm";
import { PanoramaView } from "@/components/athletes/ai/PanoramaView";
import { SeasonSummaryButton } from "@/components/athletes/ai/SeasonSummaryButton";
import { NewsletterSelectionBar } from "@/components/athletes/races/NewsletterSelectionBar";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { invalidateAthleteAiQueries } from "@/hooks/ai/invalidateAthleteAiQueries";
import { isTerminalState, useRunStatus } from "@/hooks/ai/useRaceRun";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { useAthleteRuns } from "@/hooks/athletes/useAthleteRuns";
import { familyGapMentionsFromEvent, findPendingHitlEvent } from "@/lib/hitlEvents";
import type { AthleteOut } from "@/types/athlete.types";
import type { AthleteRunStatus } from "@/types/athleteRaceAnalysis.types";
import type { InsightV3 } from "@/types/insightV3.types";

/**
 * Estados de `agent_runs` que siguen "vivos" y por lo tanto deben
 * recuperarse al montar la vista: `running` (el pipeline sigue corriendo) y
 * `awaiting_hitl` (el análisis terminó y espera la decisión del coach). Los
 * demás (`completed`, `rejected`, `failed`, `cancelled`) son terminales y
 * pertenecen al histórico, no al timeline en vivo.
 */
const ACTIVE_RUN_STATUSES: ReadonlySet<AthleteRunStatus> = new Set<AthleteRunStatus>([
  "running",
  "awaiting_hitl",
]);

export interface AnalysisViewProps {
  athlete: AthleteOut;
  audience: "coach" | "family";
  /** `insight=<id>` de la URL: abre ese análisis en el histórico. */
  insightId?: number | null;
  /**
   * Avisa cuando el usuario abre (`id`) o cierra (`null`) un análisis, para
   * que la pestaña refleje `insight=` en la URL (enlace compartible).
   */
  onInsightChange?: (id: number | null) => void;
}

export function AnalysisView({
  athlete,
  audience,
  insightId = null,
  onInsightChange,
}: AnalysisViewProps) {
  const isCoach = audience === "coach";
  const mode = isCoach ? "coach" : "parent";

  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [hitlStepId, setHitlStepId] = useState<string | null>(null);
  // Análisis abierto en el histórico: nace del `insight=` de la URL y luego
  // lo controla el usuario (PanoramaView / InsightsTimeline).
  const [selectedInsightId, setSelectedInsightId] = useState<number | null>(insightId);
  useEffect(() => {
    setSelectedInsightId(insightId);
  }, [insightId]);

  // Selección multi para el boletín — solo coach.
  const [newsletterSelection, setNewsletterSelection] = useState<Set<number>>(
    () => new Set(),
  );
  const toggleNewsletterSelection = useCallback((id: number) => {
    setNewsletterSelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const clearNewsletterSelection = useCallback(
    () => setNewsletterSelection(new Set()),
    [],
  );

  // El botón «Hero» solo alterna la selección local; el envío real se hace
  // desde la barra fija (`NewsletterSelectionBar`).
  const handleAddToNewsletter = toggleNewsletterSelection;

  const headerQuery = useAthleteInsights(athlete.id, {
    latest_only: true,
    limit: 1,
  });
  const total = headerQuery.data?.total ?? 0;

  const queryClient = useQueryClient();
  // T012: al completar el run (AnalysisRunTimeline invoca esto una sola vez,
  // al llegar a estado terminal) hay que soltar activeRunId; antes nunca
  // volvía a null y el timeline (y una HITL card colgada) quedaban fijados
  // arriba para siempre. T042: la invalidación delega en el helper
  // compartido `invalidateAthleteAiQueries`.
  const handleRunComplete = useCallback(() => {
    void invalidateAthleteAiQueries(queryClient, athlete.id);
    setActiveRunId(null);
    setHitlStepId(null);
  }, [queryClient, athlete.id]);

  // ── Recuperación de runs activos desde el servidor ──────────────────────
  //
  // `activeRunId` es estado local: antes sólo se poblaba cuando el coach
  // lanzaba el análisis en ESTA instancia de React. Un run en
  // `awaiting_hitl` desaparecía de la vista tras un refresh o al volver al
  // día siguiente — y seguía bloqueando con 409 cualquier intento de
  // relanzar, sin nada en pantalla que lo explicara. Mismo patrón que el
  // panel grupal (`hooks/ai/useGroupAnalysis.ts`): recovery query + efecto
  // que siembra el run activo más reciente. El endpoint del atleta NO tiene
  // `active_only`: el filtro por estado se hace en cliente.
  const runsRecoveryQuery = useAthleteRuns(
    athlete.id,
    { limit: 20 },
    { enabled: isCoach },
  );

  // Runs ya adoptados (sembrados o lanzados aquí). Sin esta marca, al
  // completar un run `handleRunComplete` limpia `activeRunId` e invalida
  // `athlete-runs`; si el refetch alcanzara a traer todavía el estado
  // viejo, el efecto de abajo lo volvería a sembrar y el timeline
  // reaparecería solo.
  const adoptedRunIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!isCoach) return;
    if (activeRunId !== null) return;
    const items = runsRecoveryQuery.data?.items;
    if (!items || items.length === 0) return;
    // El backend ordena por `started_at DESC, id DESC`: el primer match es
    // el más reciente.
    const candidate = items.find(
      (run) =>
        ACTIVE_RUN_STATUSES.has(run.status) &&
        !adoptedRunIdsRef.current.has(run.run_id),
    );
    if (!candidate) return;
    adoptedRunIdsRef.current.add(candidate.run_id);
    setActiveRunId(candidate.run_id);
    setHitlStepId(null);
  }, [isCoach, activeRunId, runsRecoveryQuery.data]);

  // Los lanzadores viven al final de la vista y el run en vivo arriba: al
  // lanzar, se lleva el timeline a la vista (antes se cambiaba de sub-tab).
  const pendingRef = useRef<HTMLDivElement>(null);
  const scrollToPendingRef = useRef(false);
  useEffect(() => {
    if (activeRunId && scrollToPendingRef.current) {
      scrollToPendingRef.current = false;
      pendingRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
  }, [activeRunId]);

  const handleStarted = (runId: string) => {
    adoptedRunIdsRef.current.add(runId);
    scrollToPendingRef.current = true;
    setActiveRunId(runId);
    setHitlStepId(null);
  };

  const statusQuery = useRunStatus(isCoach ? activeRunId : null);
  const runState = statusQuery.data?.latest?.state;
  // T014: se busca hacia atrás (evento más reciente primero) y se detiene
  // en CUALQUIERA de los dos hitos: `hitl_request`/`hitl_required` (la
  // interrupción vigente) o `hitl_response` (el coach ya decidió — así un
  // `hitl_request` viejo, que useRunStatus nunca purga, no revive la card).
  const lastHitlEvent = useMemo(
    () => findPendingHitlEvent(statusQuery.data?.events),
    [statusQuery.data],
  );
  // Autorreparación: el run está pausado esperando aprobación pero el
  // `hitl_request` —el único evento que transporta el `draft_markdown`— no
  // está en el buffer acumulado. Sin él la card le pide al coach que
  // apruebe un borrador que no puede leer. El cursor `since` sólo avanza,
  // así que se reinicia UNA vez por run para forzar un refetch completo.
  const healedRunRef = useRef<string | null>(null);
  useEffect(() => {
    if (runState !== "hitl_waiting") return;
    if (!activeRunId) return;
    if (lastHitlEvent) return;
    if (healedRunRef.current === activeRunId) return;
    healedRunRef.current = activeRunId;
    statusQuery.resetEvents();
    void statusQuery.refetch();
  }, [runState, activeRunId, lastHitlEvent, statusQuery]);

  const hitlStepIdFromEvent =
    typeof lastHitlEvent?.payload?.step_id === "string"
      ? (lastHitlEvent.payload.step_id as string)
      : null;
  const effectiveStepId = hitlStepId ?? hitlStepIdFromEvent ?? "hitl_default";
  // No mostrar una card de aprobación colgada del último dato bueno si la
  // query de estado ya quedó en error (techo de polling T017). Excepción: si
  // el último estado conocido es `hitl_waiting`, el run sigue vivo esperando
  // al coach — un error transitorio de red no debe borrarle la card.
  const showHITL =
    !isTerminalState(runState) &&
    (!statusQuery.isError || runState === "hitl_waiting") &&
    (runState === "hitl_waiting" || !!hitlStepIdFromEvent);
  const draftMarkdown =
    typeof lastHitlEvent?.payload?.draft_markdown === "string"
      ? (lastHitlEvent.payload.draft_markdown as string)
      : "_(El agente generó un borrador, pero no incluyó el markdown en el evento. Aprueba o rechaza.)_";
  // Feature 037 (T301): `structured_draft` viaja en el mismo evento — `InsightV3 |
  // null` (el backend lo omite en `null` para runs v2).
  const structuredDraft =
    lastHitlEvent?.payload &&
    typeof lastHitlEvent.payload === "object" &&
    "structured_draft" in lastHitlEvent.payload &&
    lastHitlEvent.payload.structured_draft !== null &&
    typeof lastHitlEvent.payload.structured_draft === "object"
      ? (lastHitlEvent.payload.structured_draft as InsightV3)
      : null;

  const selectInsight = useCallback(
    (id: number | null) => {
      setSelectedInsightId(id);
      onInsightChange?.(id);
    },
    [onInsightChange],
  );
  const openDetail = useCallback((id: number) => selectInsight(id), [selectInsight]);

  return (
    <section
      className="space-y-4"
      aria-label="Análisis IA de carreras"
      data-testid="analysis-view"
    >
      <header className="rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline">
        <h3
          className="font-display flex items-center gap-2 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          <Sparkles size={16} aria-hidden="true" />
          Análisis IA
        </h3>
        <p className="mt-1 text-xs text-mid-gray" data-testid="analysis-ai-label">
          {isCoach
            ? "Análisis generado con IA a partir de los resultados oficiales de carrera."
            : "Análisis generado con IA y revisado por el entrenador."}
        </p>
        {!isCoach && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  className="mt-1.5 inline-block cursor-default text-[11px] text-mid-gray underline decoration-dotted underline-offset-2"
                  tabIndex={0}
                >
                  ¿Cómo se elaboran estos análisis?
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-64">
                Análisis preparado con apoyo de herramientas y revisado por el coach
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </header>

      {/* 1. Pendiente — run en vivo, solo coach. Compacto por defecto
          (~72px): antes se renderizaba `full` y los 13 nodos del grafo
          empujaban el histórico fuera de la pantalla; el detalle queda a un
          clic. */}
      {isCoach && activeRunId && (
        <div ref={pendingRef} className="scroll-mt-4 space-y-4" data-testid="analysis-pending">
          <AnalysisRunTimeline
            runId={activeRunId}
            variant="compact"
            collapsible
            onComplete={handleRunComplete}
          />
          {showHITL && (
            <HITLApprovalCard
              runId={activeRunId}
              stepId={effectiveStepId}
              draftMarkdown={draftMarkdown}
              structuredDraft={structuredDraft}
              familyGapMentions={familyGapMentionsFromEvent(lastHitlEvent)}
              onSubmitted={() => setHitlStepId(null)}
            />
          )}
        </div>
      )}

      {/* 2. Último análisis — tarjetas KPI + hero. */}
      <PanoramaView
        athlete={athlete}
        mode={mode}
        onOpenDetail={openDetail}
        onAddToNewsletter={handleAddToNewsletter}
        newsletterSelection={isCoach ? newsletterSelection : undefined}
        onToggleSelection={isCoach ? toggleNewsletterSelection : undefined}
      />

      {/* 3. Histórico. */}
      <InsightsTimeline
        athleteId={athlete.id}
        mode={mode}
        selectedInsightId={selectedInsightId}
        onSelectInsight={selectInsight}
        newsletterSelection={isCoach ? newsletterSelection : undefined}
        onToggleSelection={isCoach ? toggleNewsletterSelection : undefined}
      />

      {/* 4. Herramientas del coach. */}
      {isCoach && (
        <section
          className="space-y-3"
          aria-label="Analizar con IA"
          data-testid="analysis-coach-tools"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3
              className="font-display flex items-center gap-2 text-sm text-charcoal"
              style={{ letterSpacing: "0.2px" }}
            >
              <Sparkles size={16} aria-hidden="true" />
              Analizar con IA
            </h3>
            <SeasonSummaryButton
              athleteId={athlete.id}
              analyzedValidasCount={total}
              onRunStarted={handleStarted}
            />
          </div>
          <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
            <LaunchAnalysisForm
              athleteId={athlete.id}
              athleteName={`${athlete.first_name} ${athlete.last_name}`.trim()}
              onStarted={handleStarted}
            />
            <AthleteAnalystChatPanel athleteId={athlete.id} />
          </div>
        </section>
      )}

      {isCoach && (
        <NewsletterSelectionBar
          athleteId={athlete.id}
          selection={newsletterSelection}
          onClear={clearNewsletterSelection}
        />
      )}
    </section>
  );
}
