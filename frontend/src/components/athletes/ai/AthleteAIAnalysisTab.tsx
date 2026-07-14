/**
 * AthleteAIAnalysisTab — tab raíz "Análisis IA" del perfil del atleta.
 *
 * Sprint 2:
 *   - BB3: Comparador movido a Sheet lateral dentro del tab Distribución.
 *          Tab "Comparador" eliminado de la TabsList.
 *   - BB4: Multi-select bulk para boletín + sticky action bar inferior (solo coach).
 *
 * Estructura de sub-tabs (post-Sprint 2):
 *   · Panorama     → PanoramaView (default)
 *   · Histórico    → InsightsTimeline
 *   · Evolución    → EvolutionChart
 *   · Distribución → DistributionChart + Sheet con ComparatorPanel (solo coach)
 *   · Analizar con IA → LaunchAnalysisForm (solo coach)
 *
 * Privacidad Ley 1581:
 *   - mode="parent" oculta Distribución, "Analizar con IA", Sheet del Comparador.
 *   - Multi-select y action bar SOLO en mode="coach".
 *   - Checkbox nunca se renderiza para parent.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  Calendar,
  History,
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
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
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
import { StatusBadge } from "@/components/shared/StatusBadge";
import { formatDateTimeCompact } from "@/lib/datetime";
import { confidenceStatus, validaLabel } from "@/lib/insights";
import { useRunStatus } from "@/hooks/ai/useRaceRun";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { useAttachInsightsToNewsletter } from "@/api/athleteNewsletters";
import type { AttachInsightsRequest } from "@/types/athleteNewsletter.types";
import type { AthleteOut } from "@/types/athlete.types";

type SubTab = "panorama" | "history" | "evolution" | "distribution" | "launch";

interface AthleteAIAnalysisTabProps {
  athlete: AthleteOut;
  mode: "coach" | "parent";
}

export function AthleteAIAnalysisTab({
  athlete,
  mode,
}: AthleteAIAnalysisTabProps) {
  const [subTab, setSubTab] = useState<SubTab>("panorama");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [hitlStepId, setHitlStepId] = useState<string | null>(null);
  // selectedInsightId: compartido entre PanoramaView e InsightsTimeline.
  const [selectedInsightId, setSelectedInsightId] = useState<number | null>(null);

  // BB3: estado del Sheet del Comparador (dentro de Distribución).
  const [comparatorSheetOpen, setComparatorSheetOpen] = useState(false);

  // BB4: multi-select para boletín — solo coach.
  const [newsletterSelection, setNewsletterSelection] = useState<Set<number>>(new Set());

  const attachMutation = useAttachInsightsToNewsletter(athlete.id);
  // Ref para guardar el último payload enviado (para el botón "Reintentar").
  const lastAttachPayloadRef = useRef<AttachInsightsRequest | null>(null);

  const toggleNewsletterSelection = (id: number) => {
    setNewsletterSelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleAddBulkToNewsletter = () => {
    const ids = Array.from(newsletterSelection);
    if (ids.length === 0) return;
    const payload: AttachInsightsRequest = { insight_ids: ids };
    lastAttachPayloadRef.current = payload;
    attachMutation.mutate(payload, {
      onSuccess: () => setNewsletterSelection(new Set()),
    });
  };

  // Defensivo: si el sub-tab activo es distribution y el modo es parent, resetear.
  useEffect(() => {
    if (mode === "parent" && subTab === "distribution") {
      setSubTab("panorama");
    }
  }, [mode, subTab]);

  // Tras éxito en la sticky bar: la selección ya se limpió (onSuccess).
  // Esperar 3 s mostrando el mensaje de confirmación y luego resetear la mutación
  // para que la barra desaparezca completamente.
  useEffect(() => {
    if (attachMutation.isSuccess && newsletterSelection.size === 0) {
      const timer = setTimeout(() => {
        attachMutation.reset();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [attachMutation, newsletterSelection.size]);

  // T4 — el botón Hero mantiene toggle a newsletterSelection (selección local).
  // El envío real se hace únicamente desde la sticky bar. No llama a la API aquí.
  const handleAddToNewsletter = (insightId: number) => {
    toggleNewsletterSelection(insightId);
  };

  const headerQuery = useAthleteInsights(athlete.id, {
    latest_only: true,
    limit: 1,
  });

  const queryClient = useQueryClient();
  const handleRunComplete = useCallback(() => {
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
        className="rounded-xl bg-white p-5 shadow-card"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2
              className="font-display flex items-center gap-2 text-base text-charcoal"
            >
              <Sparkles size={16} aria-hidden="true" />
              Insights IA
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
                    <StatusBadge
                      status={confidenceStatus(latest.confidence).status}
                      label={confidenceStatus(latest.confidence).label}
                    />
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

      {/* Run timeline en vivo — solo coach */}
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
              <Sparkles size={14} aria-hidden="true" />
              Analizar con IA
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
            newsletterSelection={mode === "coach" ? newsletterSelection : undefined}
            onToggleSelection={mode === "coach" ? toggleNewsletterSelection : undefined}
          />
        </TabsContent>
        <TabsContent value="history">
          <InsightsTimeline
            athleteId={athlete.id}
            mode={mode}
            selectedInsightId={selectedInsightId}
            onSelectInsight={setSelectedInsightId}
            newsletterSelection={mode === "coach" ? newsletterSelection : undefined}
            onToggleSelection={mode === "coach" ? toggleNewsletterSelection : undefined}
          />
        </TabsContent>
        <TabsContent value="evolution">
          <EvolutionChart athleteId={athlete.id} />
        </TabsContent>
        {mode === "coach" && (
          <TabsContent value="distribution">
            <div className="space-y-3">
              {/* BB3: botón para abrir el comparador como Sheet lateral */}
              <div className="flex justify-end">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setComparatorSheetOpen(true)}
                  data-testid="open-comparator-sheet"
                >
                  Comparar con otro atleta
                </Button>
              </div>
              <DistributionChart athleteId={athlete.id} />
            </div>

            {/* Sheet del Comparador (BB3) */}
            <Sheet
              open={comparatorSheetOpen}
              onOpenChange={setComparatorSheetOpen}
            >
              <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto">
                <SheetHeader>
                  <SheetTitle>Comparador de progreso</SheetTitle>
                  <SheetDescription>
                    Compara el progreso del atleta entre dos válidas de la temporada.
                  </SheetDescription>
                </SheetHeader>
                <div className="mt-4">
                  <ComparatorPanel athleteId={athlete.id} />
                </div>
              </SheetContent>
            </Sheet>
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

      {/* BB4: Sticky action bar — solo coach */}
      {mode === "coach" && (newsletterSelection.size > 0 || attachMutation.isSuccess || attachMutation.isError) && (
        <div
          className="sticky bottom-4 left-0 right-0 z-20 mx-auto flex max-w-2xl items-center justify-between gap-3 rounded-xl bg-charcoal p-3 text-white shadow-lg"
          data-testid="newsletter-action-bar"
        >
          {attachMutation.isError ? (
            <>
              <span className="text-sm text-red-200" data-testid="newsletter-action-bar-error">
                No pudimos agregar al boletín. Intenta de nuevo.
              </span>
              <Button
                variant="default"
                size="sm"
                onClick={() => {
                  if (lastAttachPayloadRef.current) {
                    attachMutation.mutate(lastAttachPayloadRef.current, {
                      onSuccess: () => setNewsletterSelection(new Set()),
                    });
                  }
                }}
                className="bg-white text-charcoal hover:bg-white/90"
              >
                Reintentar
              </Button>
            </>
          ) : attachMutation.isSuccess && newsletterSelection.size === 0 ? (
            <span
              className="text-sm text-emerald-200"
              data-testid="newsletter-action-bar-success"
            >
              Agregados al boletín del mes
            </span>
          ) : (
            <>
              <span className="text-sm">
                {newsletterSelection.size}{" "}
                {newsletterSelection.size === 1
                  ? "insight seleccionado"
                  : "insights seleccionados"}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setNewsletterSelection(new Set())}
                  disabled={attachMutation.isPending}
                  className="border-white/30 text-white hover:bg-white/10 hover:text-white"
                >
                  Limpiar
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  onClick={handleAddBulkToNewsletter}
                  disabled={attachMutation.isPending}
                  className="bg-white text-charcoal hover:bg-white/90"
                  data-testid="newsletter-action-bar-submit"
                >
                  {attachMutation.isPending ? "Enviando…" : "Enviar a boletín"}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
