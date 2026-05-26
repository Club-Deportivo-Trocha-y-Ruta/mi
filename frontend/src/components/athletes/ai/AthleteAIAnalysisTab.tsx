/**
 * AthleteAIAnalysisTab — tab raíz "Análisis IA" del perfil del atleta.
 *
 * Estructura:
 *   - Header con resumen ejecutivo (último análisis aprobado + badge
 *     confidence + total de aprobados).
 *   - Sub-tabs internas (shadcn Tabs, Radix):
 *       · Histórico    → InsightsTimeline
 *       · Evolución    → EvolutionChart
 *       · Comparador   → ComparatorPanel
 *       · Distribución → DistributionChart
 *       · Lanzar       → LaunchAnalysisForm (solo coach/admin)
 *
 * Privacidad: en mode="parent" ocultamos completamente la pestaña
 * "Lanzar" y el AnalysisRunTimeline (datos operativos del agente, costos
 * LLM, prompts, etc).
 */
import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  Calendar,
  History,
  Play,
  Scale,
  Sparkles,
} from "lucide-react";

import { AnalysisRunTimeline } from "@/components/ai/AnalysisRunTimeline";
import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";
import { ComparatorPanel } from "@/components/athletes/ai/ComparatorPanel";
import { DistributionChart } from "@/components/athletes/ai/DistributionChart";
import { EvolutionChart } from "@/components/athletes/ai/EvolutionChart";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";
import { LaunchAnalysisForm } from "@/components/athletes/ai/LaunchAnalysisForm";
import { PanoramaView } from "@/components/athletes/ai/PanoramaView";
import { SeasonSummaryButton } from "@/components/athletes/ai/SeasonSummaryButton";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatDateTimeCompact } from "@/lib/datetime";
import { useRunStatus } from "@/hooks/ai/useRaceRun";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import type { AthleteOut } from "@/types/athlete.types";
import type { InsightConfidence } from "@/types/athleteRaceAnalysis.types";

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

type SubTab = "panorama" | "history" | "evolution" | "compare" | "distribution" | "launch";

function confidenceBadgeVariant(
  c: InsightConfidence,
): "success" | "warning" | "destructive" {
  if (c === "high") return "success";
  if (c === "medium") return "warning";
  return "destructive";
}

function confidenceText(c: InsightConfidence): string {
  if (c === "high") return "Confianza alta";
  if (c === "medium") return "Confianza media";
  return "Confianza baja";
}


function validaLabel(num: number | null | undefined): string {
  if (num === null || num === undefined) return "agregado";
  if (num === 0) return "resumen de temporada";
  if (num === 99) return "Cto. Departamental";
  return `Válida ${num}`;
}

interface AthleteAIAnalysisTabProps {
  athlete: AthleteOut;
  mode: "coach" | "parent";
}

export function AthleteAIAnalysisTab({
  athlete,
  mode,
}: AthleteAIAnalysisTabProps) {
  const [subTab, setSubTab] = useState<SubTab>("panorama");
  // run_id devuelto por LaunchAnalysisForm — al setearse muestra el
  // AnalysisRunTimeline encima del histórico para que el coach lo vea
  // ejecutarse en vivo.
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [hitlStepId, setHitlStepId] = useState<string | null>(null);
  // selectedInsightId: compartido entre PanoramaView e InsightsTimeline
  // para abrir el drawer de detalle desde ambos contextos (Sprint 2 BB4).
  const [selectedInsightId, setSelectedInsightId] = useState<number | null>(null);

  // Defensivo: si el sub-tab activo es compare/distribution y el modo es
  // parent (no debería llegar aquí, pero por si hay deep-link o HMR),
  // resetear a "panorama".
  useEffect(() => {
    if (
      mode === "parent" &&
      (subTab === "compare" || subTab === "distribution")
    ) {
      setSubTab("panorama");
    }
  }, [mode, subTab]);

  const handleAddToNewsletter = (insightId: number) => {
    console.info("[TODO Sprint 3] Insight agregado al boletín:", insightId);
  };

  // Resumen del header: último análisis (latest_only=true, limit=1).
  const headerQuery = useAthleteInsights(athlete.id, {
    latest_only: true,
    limit: 1,
  });

  const queryClient = useQueryClient();
  const handleRunComplete = useCallback(() => {
    // Invalidar todas las queries "athlete-*" del atleta para refrescar
    // el header (Total aprobados + último análisis) y el Histórico.
    void queryClient.invalidateQueries({
      predicate: (q) => {
        const k = q.queryKey;
        return (
          Array.isArray(k) &&
          typeof k[0] === "string" &&
          (k[0] as string).startsWith("athlete-")
        );
      },
    });
  }, [queryClient]);
  const latest = headerQuery.data?.items[0];
  const total = headerQuery.data?.total ?? 0;

  const handleStarted = (runId: string) => {
    setActiveRunId(runId);
    setHitlStepId(null);
    setSubTab("history");
  };

  // HITL detection — solo coach (parent NO aprueba). Sólo polleamos si hay run activo.
  const statusQuery = useRunStatus(mode === "coach" ? activeRunId : null);
  const runState = statusQuery.data?.latest?.state;
  const lastHitlEvent = statusQuery.data?.events
    ?.slice()
    .reverse()
    .find(
      (e) =>
        e.type === "hitl_request" ||
        e.type === "hitl_required" ||
        e.node === "hitl_gate_review",
    );
  const hitlStepIdFromEvent =
    typeof lastHitlEvent?.payload?.step_id === "string"
      ? (lastHitlEvent.payload.step_id as string)
      : null;
  const effectiveStepId = hitlStepId ?? hitlStepIdFromEvent ?? "hitl_default";
  const showHITL = runState === "hitl_waiting" || !!hitlStepIdFromEvent;
  const draftMarkdown =
    typeof lastHitlEvent?.payload?.draft_markdown === "string"
      ? (lastHitlEvent.payload.draft_markdown as string)
      : "_(El agente generó un borrador, pero no incluyó el markdown en el evento. Aprueba o rechaza.)_";

  return (
    <section className="space-y-4" data-testid="athlete-ai-analysis-tab">
      {/* Header — resumen ejecutivo */}
      <div
        className="rounded-xl bg-white p-5"
        style={{ boxShadow: cardShadow }}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2
              className="flex items-center gap-2 text-base text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
            >
              <Sparkles size={16} aria-hidden="true" />
              {mode === "parent" ? "Análisis del coach" : "Análisis IA del deportista"}
            </h2>
            <p className="mt-1 text-xs text-mid-gray">
              {mode === "parent"
                ? "Seguimiento y evolución del deportista, revisado por el entrenador."
                : "Pipeline agéntico: análisis, comparaciones y proyecciones a partir de resultados oficiales."}
            </p>
            {mode === "parent" && (
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
          </div>
          <div className="flex flex-col items-end gap-2">
            {mode === "coach" && (
              <SeasonSummaryButton
                athleteId={athlete.id}
                analyzedValidasCount={total}
              />
            )}
            {headerQuery.isLoading ? (
              <Skeleton className="h-16 w-48 rounded-lg" />
            ) : latest ? (
              <div
                className="flex flex-col items-end gap-1 rounded-lg bg-light-gray/40 px-3 py-2"
                data-testid="ai-header-summary"
              >
                <span className="text-[10px] font-medium uppercase tracking-wide text-mid-gray">
                  Último análisis
                </span>
                <span className="text-sm font-semibold text-charcoal">
                  {formatDateTimeCompact(latest.generated_at)}
                </span>
                <div className="flex flex-wrap items-center justify-end gap-1.5">
                  <Badge variant="secondary">{validaLabel(latest.valida_num)}</Badge>
                  {mode === "coach" && (
                    <Badge variant={confidenceBadgeVariant(latest.confidence)}>
                      {confidenceText(latest.confidence)}
                    </Badge>
                  )}
                </div>
                <span className="text-[11px] text-mid-gray">
                  Total aprobados: {total}
                </span>
              </div>
            ) : (
              <p className="text-xs text-mid-gray">Sin análisis aprobados aún.</p>
            )}
          </div>
        </div>
      </div>

      {/* Run timeline en vivo — solo coach, solo si acaba de lanzar */}
      {mode === "coach" && activeRunId && (
        <>
          <AnalysisRunTimeline runId={activeRunId} onComplete={handleRunComplete} />
          {showHITL && (
            <HITLApprovalCard
              runId={activeRunId}
              stepId={effectiveStepId}
              draftMarkdown={draftMarkdown}
              onSubmitted={() => setHitlStepId(null)}
            />
          )}
        </>
      )}

      {/* Sub-tabs (Radix) */}
      <Tabs
        value={subTab}
        onValueChange={(v) => setSubTab(v as SubTab)}
        className="w-full"
      >
        <TabsList className="flex w-full justify-start gap-1 overflow-x-auto bg-white p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <TabsTrigger value="panorama" data-testid="ai-subtab-panorama" className="shrink-0">
            <Sparkles size={14} aria-hidden="true" />
            Panorama
          </TabsTrigger>
          <TabsTrigger value="history" data-testid="ai-subtab-history" className="shrink-0">
            <History size={14} aria-hidden="true" />
            Histórico
          </TabsTrigger>
          <TabsTrigger value="evolution" data-testid="ai-subtab-evolution" className="shrink-0">
            <Calendar size={14} aria-hidden="true" />
            Evolución
          </TabsTrigger>
          {mode === "coach" && (
            <TabsTrigger value="compare" data-testid="ai-subtab-compare" className="shrink-0">
              <Scale size={14} aria-hidden="true" />
              Comparador
            </TabsTrigger>
          )}
          {mode === "coach" && (
            <TabsTrigger
              value="distribution"
              data-testid="ai-subtab-distribution"
              className="shrink-0"
            >
              <BarChart3 size={14} aria-hidden="true" />
              Distribución
            </TabsTrigger>
          )}
          {mode === "coach" && (
            <TabsTrigger value="launch" data-testid="ai-subtab-launch" className="shrink-0">
              <Play size={14} aria-hidden="true" />
              Lanzar
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="panorama">
          <PanoramaView
            athlete={athlete}
            mode={mode}
            onOpenDetail={(id) => {
              setSelectedInsightId(id);
              setSubTab("history");
            }}
            onAddToNewsletter={handleAddToNewsletter}
          />
        </TabsContent>
        <TabsContent value="history">
          <InsightsTimeline
            athleteId={athlete.id}
            mode={mode}
            selectedInsightId={selectedInsightId}
            onSelectInsight={setSelectedInsightId}
          />
        </TabsContent>
        <TabsContent value="evolution">
          <EvolutionChart athleteId={athlete.id} />
        </TabsContent>
        {mode === "coach" && (
          <TabsContent value="compare">
            <ComparatorPanel athleteId={athlete.id} />
          </TabsContent>
        )}
        {mode === "coach" && (
          <TabsContent value="distribution">
            <DistributionChart athleteId={athlete.id} />
          </TabsContent>
        )}
        {mode === "coach" && (
          <TabsContent value="launch">
            <LaunchAnalysisForm
              athleteId={athlete.id}
              athleteName={`${athlete.first_name} ${athlete.last_name}`.trim()}
              onStarted={handleStarted}
            />
          </TabsContent>
        )}
      </Tabs>
    </section>
  );
}
