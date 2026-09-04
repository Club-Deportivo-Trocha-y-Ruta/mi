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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  Calendar,
  History,
  Sparkles,
} from "lucide-react";

import { AnalysisRunTimeline } from "@/components/ai/AnalysisRunTimeline";
import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";
import { AthleteAnalystChatPanel } from "@/components/athletes/ai/AthleteAnalystChatPanel";
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
import { invalidateAthleteAiQueries } from "@/hooks/ai/invalidateAthleteAiQueries";
import { useRunStatus } from "@/hooks/ai/useRaceRun";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";
import { useAthleteRuns } from "@/hooks/athletes/useAthleteRuns";
import { useAttachInsightsToNewsletter } from "@/api/athleteNewsletters";
import type { AttachInsightsRequest } from "@/types/athleteNewsletter.types";
import type { AthleteRunStatus } from "@/types/athleteRaceAnalysis.types";
import type { AthleteOut } from "@/types/athlete.types";
import type { InsightV3 } from "@/types/insightV3.types";

type SubTab = "panorama" | "history" | "evolution" | "distribution" | "launch";

/**
 * Estados de `agent_runs` que siguen "vivos" y por lo tanto deben
 * recuperarse al montar el tab: `running` (el pipeline sigue corriendo) y
 * `awaiting_hitl` (el análisis terminó y espera la decisión del coach).
 * Los demás (`completed`, `rejected`, `failed`, `cancelled`) son
 * terminales y pertenecen al histórico, no al timeline en vivo.
 */
const ACTIVE_RUN_STATUSES: ReadonlySet<AthleteRunStatus> = new Set<AthleteRunStatus>([
  "running",
  "awaiting_hitl",
]);

const MONTH_ABBR = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/**
 * T034 (feature 036, US5): "YYYY-MM-DD" → "17 may 2026" — parseo por
 * substring, sin construir un `Date` (inmune al corrimiento de zona
 * horaria que sufren las fechas-only al pasar por `new Date(iso)` en
 * `CLUB_TIMEZONE`/America-Bogota, ver `lib/datetime.ts`). Mismo problema,
 * mismo campo (`event_date`) y misma solución que
 * `LaunchAnalysisForm.tsx#shortEventDate` — duplicada aquí en vez de
 * importada porque ese archivo pertenece a otro agente de esta misma ola
 * (ownership por archivo, feature 036 Wave 2).
 */
function formatRaceDateShort(isoDate: string): string {
  const year = isoDate.slice(0, 4);
  const month = Number(isoDate.slice(5, 7));
  const day = Number(isoDate.slice(8, 10));
  const abbr = MONTH_ABBR[month - 1];
  return abbr && Number.isFinite(day) ? `${day} ${abbr} ${year}` : isoDate;
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
  //
  // T013: TanStack Query v5 devuelve un objeto `attachMutation` NUEVO en
  // cada render (incluye cada poll tick de un run activo). Depender del
  // objeto completo reiniciaba este timer constantemente y la
  // confirmación nunca llegaba a limpiarse. `isSuccess` es un booleano
  // estable y `reset` es la misma función ligada durante toda la vida
  // del observer — sólo esos dos deben disparar el efecto.
  useEffect(() => {
    if (attachMutation.isSuccess && newsletterSelection.size === 0) {
      const timer = setTimeout(() => {
        attachMutation.reset();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [attachMutation.isSuccess, attachMutation.reset, newsletterSelection.size]);

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
  // T012: al completar el run (AnalysisRunTimeline invoca esto una sola
  // vez, al llegar a estado terminal), hay que soltar activeRunId. Antes
  // nunca se volvía a null y el timeline (y una eventual HITL card
  // colgada) quedaban fijados arriba de los sub-tabs para siempre.
  //
  // T042: la invalidación de queries delega en el helper compartido
  // `invalidateAthleteAiQueries` — antes este predicate sólo matcheaba
  // claves que empiezan con "athlete-" y se perdía `club-insights-by-race`
  // (grid cross-atleta) y `season-panorama` (dashboard de temporada).
  const handleRunComplete = useCallback(() => {
    void invalidateAthleteAiQueries(queryClient, athlete.id);
    setActiveRunId(null);
    setHitlStepId(null);
  }, [queryClient, athlete.id]);
  const latest = headerQuery.data?.items[0];
  const total = headerQuery.data?.total ?? 0;

  // ── Recuperación de runs activos desde el servidor ──────────────────────
  //
  // `activeRunId` es estado local: antes sólo se poblaba cuando el coach
  // lanzaba el análisis en ESTA instancia de React. Un run en
  // `awaiting_hitl` (análisis listo, esperando aprobación) desaparecía de
  // la vista tras un refresh, un cambio de sub-tab o simplemente al volver
  // al día siguiente — y encima seguía bloqueando con 409 cualquier intento
  // de relanzar, sin nada en pantalla que lo explicara.
  //
  // Mismo patrón que el panel grupal (`hooks/ai/useGroupAnalysis.ts`):
  // recovery query + efecto que siembra el run activo más reciente.
  // Diferencia obligada: el endpoint del atleta NO tiene `active_only` —
  // `GET /api/athletes/{id}/race-analysis/runs` sólo acepta `limit`/`offset`
  // (ver `list_athlete_runs` en el router; `status` y `season` existen en
  // `AthleteRunsParams` pero FastAPI los descarta en silencio). Por eso el
  // filtro por estado se hace en cliente.
  const runsRecoveryQuery = useAthleteRuns(
    athlete.id,
    { limit: 20 },
    { enabled: mode === "coach" },
  );

  // Runs que este componente ya adoptó (sembrados o lanzados aquí). Sin
  // esta marca, al completar un run `handleRunComplete` limpia
  // `activeRunId` e invalida `athlete-runs`; si el refetch alcanzara a
  // traer todavía el estado viejo, el efecto de abajo lo volvería a
  // sembrar y el timeline reaparecería solo.
  const adoptedRunIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (mode !== "coach") return;
    if (activeRunId !== null) return;
    const items = runsRecoveryQuery.data?.items;
    if (!items || items.length === 0) return;
    // El backend ordena por `started_at DESC, id DESC`, así que el primer
    // match es el más reciente.
    const candidate = items.find(
      (run) =>
        ACTIVE_RUN_STATUSES.has(run.status) &&
        !adoptedRunIdsRef.current.has(run.run_id),
    );
    if (!candidate) return;
    adoptedRunIdsRef.current.add(candidate.run_id);
    setActiveRunId(candidate.run_id);
    setHitlStepId(null);
  }, [mode, activeRunId, runsRecoveryQuery.data]);

  const handleStarted = (runId: string) => {
    adoptedRunIdsRef.current.add(runId);
    setActiveRunId(runId);
    setHitlStepId(null);
    setSubTab("history");
  };

  const statusQuery = useRunStatus(mode === "coach" ? activeRunId : null);
  const runState = statusQuery.data?.latest?.state;
  // T014: buscamos hacia atrás (evento más reciente primero) y nos
  // detenemos apenas encontramos CUALQUIERA de los dos hitos:
  //   - hitl_request/hitl_required → esa es la interrupción vigente.
  //   - hitl_response              → el coach ya decidió; no seguimos
  //     buscando, así un hitl_request viejo (varios nodos atrás en el
  //     array, que useRunStatus nunca purga) no revive la card.
  // Antes se usaba `node === "hitl_gate_review"` como tercera condición,
  // pero el propio evento hitl_response también viaja con ese node (y
  // con step_id en su payload) — por eso una decisión ya tomada seguía
  // matcheando y la card quedaba pegada para siempre. Memoizado porque
  // recorre el array de eventos en cada evaluación.
  const lastHitlEvent = useMemo(() => {
    const events = statusQuery.data?.events;
    if (!events) return undefined;
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const e = events[i];
      if (e.type === "hitl_response") return undefined;
      if (e.type === "hitl_request" || e.type === "hitl_required") return e;
    }
    return undefined;
  }, [statusQuery.data]);
  // Autorreparación: el run está pausado esperando aprobación pero el
  // `hitl_request` —el único evento que transporta el `draft_markdown`— no
  // está en el buffer acumulado. Sin él la card le pide al coach que
  // apruebe un borrador que no puede leer.
  //
  // El buffer vive en refs del hook y el cursor `since` sólo avanza, así
  // que si el evento no llegó a entrar (buffer perdido tras un remount,
  // polling reanudado con el cursor ya pasado, respuesta descartada) NUNCA
  // se vuelve a pedir: el backend sólo reenvía eventos con `seq > since`.
  // Reiniciamos el cursor UNA vez por run para forzar un refetch completo.
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
  // No mostrar una card de aprobación colgada del último dato bueno si
  // la query de estado ya quedó en error (p. ej. techo de polling T017).
  // Excepción: si el último estado conocido es `hitl_waiting`, el run está
  // pausado esperando al coach y sigue vivo — un error transitorio de red
  // no debe borrarle la card de aprobación de la pantalla.
  const showHITL =
    (!statusQuery.isError || runState === "hitl_waiting") &&
    (runState === "hitl_waiting" || !!hitlStepIdFromEvent);
  const draftMarkdown =
    typeof lastHitlEvent?.payload?.draft_markdown === "string"
      ? (lastHitlEvent.payload.draft_markdown as string)
      : "_(El agente generó un borrador, pero no incluyó el markdown en el evento. Aprueba o rechaza.)_";
  // Feature 037 (T301): `structured_draft` viaja en el mismo evento
  // `hitl_request`/`hitl_required` — `InsightV3 | null` (el backend lo
  // omite en `null` para runs v2, ver `nodes/hitl_gate_review.py`).
  const structuredDraft =
    lastHitlEvent?.payload &&
    typeof lastHitlEvent.payload === "object" &&
    "structured_draft" in lastHitlEvent.payload &&
    lastHitlEvent.payload.structured_draft !== null &&
    typeof lastHitlEvent.payload.structured_draft === "object"
      ? (lastHitlEvent.payload.structured_draft as InsightV3)
      : null;

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
                ? "Resumen del rendimiento en carreras, revisado por el entrenador antes de publicarse."
                : "Análisis generado con IA a partir de los resultados oficiales de carrera."}
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
          <div className="flex shrink-0 flex-col items-end gap-2">
            {mode === "coach" && (
              <SeasonSummaryButton
                athleteId={athlete.id}
                analyzedValidasCount={total}
                onRunStarted={handleStarted}
              />
            )}
          </div>
        </div>

        {/* Franja de "último análisis" — antes era una card flotando a la
            derecha que dejaba un hueco muerto de ~1000px en el centro. Como
            fila horizontal a ancho completo la información se lee de corrido
            y la cabecera baja de ~150px a ~110px. */}
        {headerQuery.isLoading ? (
          <Skeleton className="mt-4 h-10 w-full rounded-lg" />
        ) : latest ? (
          <div
            className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-light-gray pt-3"
            data-testid="ai-header-summary"
          >
            <span className="text-[10px] font-medium uppercase tracking-wide text-mid-gray">
              Último análisis
            </span>
            {/* T034 (feature 036, US5): esta línea antes mostraba
                `generated_at` — la fecha en que se ESCRIBIÓ el análisis, no
                la fecha de la carrera. Eso hacía ver "reciente" una válida
                vieja apenas analizada (ej. generada hoy, sobre la Válida 1 de
                hace meses), ocultando que ya hubo carreras más nuevas sin
                analizar todavía — la fecha de generación se conserva al
                final, marcada explícitamente como tal. Para el agregado de
                temporada (sin `event_id`, `event_date` null) no hay una fecha
                de carrera que anclar, así que cae a la temporada. */}
            <span
              className="text-sm font-semibold text-charcoal"
              data-testid="ai-header-race-date"
            >
              {latest.event_date
                ? formatRaceDateShort(latest.event_date)
                : `Temporada ${latest.season}`}
            </span>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="secondary">
                {validaLabel({
                  valida_num: latest.valida_num,
                  series_kind: latest.series_kind,
                  series_level: latest.series_level,
                })}
              </Badge>
              {mode === "coach" && (
                <StatusBadge
                  status={confidenceStatus(latest.confidence).status}
                  label={confidenceStatus(latest.confidence).label}
                />
              )}
            </div>
            {/* `ml-auto` empuja la metadata secundaria al extremo: lo primero
                que se lee es la carrera analizada, no cuándo se generó. */}
            <span className="text-[11px] text-mid-gray sm:ml-auto">
              Generado {formatDateTimeCompact(latest.generated_at)} · {total} aprobados
            </span>
          </div>
        ) : (
          <p className="mt-4 border-t border-light-gray pt-3 text-xs text-mid-gray">
            Sin análisis aprobados aún.
          </p>
        )}
      </div>

      {/* Run timeline en vivo — solo coach */}
      {mode === "coach" && activeRunId && (
        <>
          {/* Compacto por defecto (~72px). Antes se renderizaba `full`: los
              13 nodos del grafo ocupaban ~470px de vocabulario de ingeniería
              ("Anonimizar datos", "Rehidratar nombres") y empujaban el
              histórico fuera de la pantalla. El detalle queda a un clic. */}
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
        {/* T090 (feature 036, US6): a 360–400px este strip solía recortar
            en "Distribució…" con el scroll horizontal oculto a propósito
            (scrollbar-width:none) — "Analizar con IA", el último sub-tab y
            la acción principal del módulo, quedaba inalcanzable salvo que
            el usuario adivinara que podía deslizar. `flex-wrap` reemplaza
            el scroll oculto: los 5 sub-tabs quedan siempre visibles (en 2
            líneas si hace falta), sin depender de ningún gesto. Mismo
            patrón que la fila de tabs del perfil (AthleteDetailPage.tsx,
            `flex flex-wrap gap-2`) y el ToggleGroup de Progreso. */}
        <TabsList className="flex w-full flex-wrap justify-start gap-1 bg-white p-1">
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
                  className="min-h-12"
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
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 items-start">
              <LaunchAnalysisForm
                athleteId={athlete.id}
                athleteName={`${athlete.first_name} ${athlete.last_name}`.trim()}
                onStarted={handleStarted}
              />
              <AthleteAnalystChatPanel athleteId={athlete.id} />
            </div>
          </TabsContent>
        )}
      </Tabs>

      {/* BB4: Sticky action bar — solo coach */}
      {mode === "coach" && (newsletterSelection.size > 0 || attachMutation.isSuccess || attachMutation.isError) && (
        <div
          className="sticky bottom-4 left-0 right-0 z-20 mx-auto flex max-w-2xl items-center justify-between gap-3 rounded-xl bg-charcoal p-3 text-white shadow-lg"
          data-testid="newsletter-action-bar"
          // T093 (feature 036, US6): la barra cambia de estado (conteo de
          // selección, éxito, error) sin avisarle a nadie que use lector de
          // pantalla. `role="status"` ya implica aria-live="polite", pero
          // se deja explícito por consistencia con el resto del código
          // (ver p.ej. ImportWizard.tsx, EditConditionsDialog.tsx). Ninguno
          // de los tres estados es lo bastante urgente para "assertive": el
          // envío es reintentable y no hay pérdida de datos en juego.
          role="status"
          aria-live="polite"
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
                className="min-h-12 bg-white text-charcoal hover:bg-white/90"
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
                  className="min-h-12 border-white/30 text-white hover:bg-white/10 hover:text-white"
                >
                  Limpiar
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  onClick={handleAddBulkToNewsletter}
                  disabled={attachMutation.isPending}
                  className="min-h-12 bg-white text-charcoal hover:bg-white/90"
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
