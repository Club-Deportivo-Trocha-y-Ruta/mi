/**
 * RaceAnalysisPage — landing del módulo race-analysis v2 (§10.2).
 *
 * Tabs:
 *  - Nuevo análisis: StartRunForm + (cuando hay run activo) timeline +
 *    HITL card + viewer + chat + PDF download.
 *  - Runs activos: placeholder con info del run actual (lista real
 *    requiere endpoint GET /runs no expuesto aún — TODO F8+).
 *  - Insights históricos: selector de atleta que enruta al tab
 *    "Análisis IA" dentro del perfil del deportista (FE-2). El histórico
 *    en sí lo renderiza `AthleteAIAnalysisTab` con el endpoint
 *    `GET /api/athletes/{id}/race-analysis/insights`.
 *
 * El ExplainModeBanner es global a la página.
 *
 * Acceso: coach + admin (configurado en App.tsx). Como defensa en
 * profundidad, si un padre con un único hijo llegara a entrar (uso
 * compartido de tablet con el coach), el tab "Insights históricos"
 * redirige sin obligarlo a usar el combobox.
 */
import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { History, Link2, ListChecks, Plus, Upload } from "lucide-react";

import { AnalysisRunTimeline } from "@/components/ai/AnalysisRunTimeline";
import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import { ChatConsole } from "@/components/ai/ChatConsole";
import { ExplainModeBanner } from "@/components/ai/ExplainModeBanner";
import { HITLApprovalCard } from "@/components/ai/HITLApprovalCard";
import { MarkdownReportViewer } from "@/components/ai/MarkdownReportViewer";
import { PdfDownloadButton } from "@/components/ai/PdfDownloadButton";
import { StartRunForm } from "@/components/ai/StartRunForm";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import { useRunResult, useRunStatus } from "@/hooks/ai/useRaceRun";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

// Lazy: el wizard y el histórico sólo se cargan al abrir la tab de carga.
// Esto mantiene el chunk principal de RaceAnalysisPage cerca del baseline.
const ImportWizard = lazy(() =>
  import("@/components/competitions/import/ImportWizard").then((m) => ({
    default: m.ImportWizard,
  })),
);
const ImportsHistoryList = lazy(() =>
  import("@/components/ai/ImportsHistoryList").then((m) => ({
    default: m.ImportsHistoryList,
  })),
);
const UnlinkedCompetitorsTab = lazy(() =>
  import("@/components/race/UnlinkedCompetitorsTab").then((m) => ({
    default: m.UnlinkedCompetitorsTab,
  })),
);

function TabTrigger({
  value,
  icon: Icon,
  label,
  badge,
}: {
  value: string;
  icon: typeof Plus;
  label: string;
  badge?: number;
}) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className="flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-mid-gray transition-colors data-[state=active]:bg-white data-[state=active]:text-charcoal data-[state=active]:shadow-sm"
    >
      <Icon size={16} aria-hidden="true" />
      <span>{label}</span>
      {badge != null && badge > 0 && (
        <span
          className="inline-flex min-w-[18px] items-center justify-center rounded-full bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-800"
          aria-label={`${badge} pendientes`}
          data-testid={`tab-badge-${value}`}
        >
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </TabsPrimitive.Trigger>
  );
}

export function RaceAnalysisPage() {
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isParent = role === UserRole.parent;

  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [hitlStepId, setHitlStepId] = useState<string | null>(null);
  const [chatAthleteId, setChatAthleteId] = useState<number | null>(null);
  const [unlinkedCount, setUnlinkedCount] = useState<number>(0);
  const [historyAthleteId, setHistoryAthleteId] = useState<number | null>(null);

  // Hijos del padre — sólo se piden si rol=parent (defensa para uso
  // compartido de tablet). El endpoint exige rol=parent así que para
  // coach/admin la query queda deshabilitada (enabled internamente).
  const myAthletesQuery = useMyAthletes();
  const parentSingleChildId = useMemo<number | null>(() => {
    if (!isParent) return null;
    const items = myAthletesQuery.data ?? [];
    return items.length === 1 ? items[0].athlete_id : null;
  }, [isParent, myAthletesQuery.data]);

  // Auto-redirect parent con un único hijo: salta directo al perfil del
  // hijo con el tab IA abierto, sin pasar por el combobox.
  useEffect(() => {
    if (isParent && parentSingleChildId != null) {
      navigate(`/my-athletes/${parentSingleChildId}`, { replace: true });
    }
  }, [isParent, parentSingleChildId, navigate]);

  // Resolvemos el nombre del atleta seleccionado en el chat — para
  // mostrar contexto visual sin tocar el body POST /chat.
  const athletesQuery = useAthletes();
  const chatAthleteName = useMemo(() => {
    if (chatAthleteId == null) return null;
    const a = athletesQuery.data?.items.find((x) => x.id === chatAthleteId);
    return a ? `${a.first_name} ${a.last_name}` : null;
  }, [chatAthleteId, athletesQuery.data]);

  // Navega al tab "Análisis IA" dentro del perfil del deportista — fuente
  // canónica del histórico. Para coach/admin la ruta es /athletes/:id;
  // los padres no llegan aquí (route guard) pero por defensa se enruta
  // al portal del padre si por algún motivo el rol cambia.
  const handleHistoryAthletePick = (athleteId: number | null) => {
    setHistoryAthleteId(athleteId);
    if (athleteId == null) return;
    const base = isParent ? "/my-athletes" : "/athletes";
    const suffix = isParent ? "" : "?tab=ai_analysis";
    navigate(`${base}/${athleteId}${suffix}`);
  };

  // Sólo polleamos si hay un run activo.
  const statusQuery = useRunStatus(activeRunId);
  const state = statusQuery.data?.latest.state;
  const resultQuery = useRunResult(activeRunId, state);

  // Detecta evento hitl_required en el stream.
  const lastHitlEvent = statusQuery.data?.events
    .slice()
    .reverse()
    .find(
      (e) =>
        e.type === "hitl_request" ||
        e.type === "hitl_required" ||
        e.node === "hitl_gate_review",
    );
  const hitlStepIdFromEvent =
    typeof lastHitlEvent?.payload?.step_id === "string"
      ? lastHitlEvent.payload.step_id
      : null;
  const effectiveStepId = hitlStepId ?? hitlStepIdFromEvent ?? "hitl_default";

  const showHITL = state === "hitl_waiting" || !!hitlStepIdFromEvent;

  // Draft markdown del evento (defensivo).
  const draftMarkdown =
    (typeof lastHitlEvent?.payload?.draft_markdown === "string"
      ? (lastHitlEvent.payload.draft_markdown as string)
      : "_(El agente generó un borrador, pero no incluyó el markdown en el evento. Aprueba o rechaza.)_");

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-6">
      <header>
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Análisis de carreras
        </h1>
        <p className="mt-1 text-sm text-mid-gray">
          Pipeline agéntico que combina resultados Copa Valle con el marco
          teórico LTAD.
        </p>
      </header>

      <ExplainModeBanner />

      <TabsPrimitive.Root defaultValue="new">
        <TabsPrimitive.List
          className="flex gap-1 rounded-xl bg-light-gray p-1"
          aria-label="Secciones de race-analysis"
        >
          <TabTrigger value="new" icon={Plus} label="Nuevo análisis" />
          <TabTrigger value="upload" icon={Upload} label="Cargar resultados" />
          <TabTrigger
            value="unlinked"
            icon={Link2}
            label="Sin enlazar"
            badge={unlinkedCount}
          />
          <TabTrigger value="active" icon={ListChecks} label="Runs activos" />
          <TabTrigger value="history" icon={History} label="Insights históricos" />
        </TabsPrimitive.List>

        {/* ── Tab: Nuevo análisis ────────────────────────────── */}
        <TabsPrimitive.Content value="new" className="mt-4 space-y-5">
          <StartRunForm
            onStarted={(runId) => {
              setActiveRunId(runId);
              setHitlStepId(null);
            }}
          />

          {activeRunId && (
            <>
              <AnalysisRunTimeline runId={activeRunId} />

              {showHITL && (
                <HITLApprovalCard
                  runId={activeRunId}
                  stepId={effectiveStepId}
                  draftMarkdown={draftMarkdown}
                  onSubmitted={() => setHitlStepId(null)}
                />
              )}

              {state === "done" && resultQuery.data && (
                <div className="space-y-3">
                  <MarkdownReportViewer
                    markdown={resultQuery.data.final.raw_markdown}
                    citations={resultQuery.data.final.citations_used}
                  />
                  <PdfDownloadButton runId={activeRunId} enabled={true} />
                </div>
              )}

              {(state === "failed" || state === "error") && (
                <div
                  role="alert"
                  className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
                >
                  El análisis falló. Revisa los logs o intenta de nuevo.
                </div>
              )}
            </>
          )}

          <div
            className="space-y-2 rounded-xl bg-white p-3 ring-1 ring-light-gray"
            data-testid="chat-context-picker"
          >
            <AthleteCombobox
              label="Conversar sobre"
              value={chatAthleteId}
              onChange={setChatAthleteId}
              allowAny
              placeholder="Cualquier deportista"
              data-testid="chat-athlete-combobox"
            />
          </div>
          <ChatConsole
            athleteId={chatAthleteId}
            athleteName={chatAthleteName}
          />
        </TabsPrimitive.Content>

        {/* ── Tab: Cargar resultados ─────────────────────────── */}
        <TabsPrimitive.Content value="upload" className="mt-4 space-y-5">
          <Suspense
            fallback={
              <div
                className="rounded-xl bg-light-gray/40 p-6 text-center text-sm text-mid-gray"
                role="status"
                aria-live="polite"
              >
                Cargando módulo de importación…
              </div>
            }
          >
            <ImportWizard />
            <ImportsHistoryList />
          </Suspense>
        </TabsPrimitive.Content>

        {/* ── Tab: Sin enlazar (Option A R1) ─────────────────── */}
        <TabsPrimitive.Content value="unlinked" className="mt-4 space-y-5">
          <Suspense
            fallback={
              <div
                className="rounded-xl bg-light-gray/40 p-6 text-center text-sm text-mid-gray"
                role="status"
                aria-live="polite"
              >
                Cargando módulo de enlace retroactivo…
              </div>
            }
          >
            <UnlinkedCompetitorsTab
              onUnlinkedCountChange={setUnlinkedCount}
            />
          </Suspense>
        </TabsPrimitive.Content>

        {/* ── Tab: Runs activos ──────────────────────────────── */}
        <TabsPrimitive.Content value="active" className="mt-4 space-y-3">
          {activeRunId ? (
            <div className="rounded-xl bg-white p-4 ring-1 ring-light-gray">
              <p className="text-sm font-medium text-charcoal">
                Run activo: <span className="font-mono">{activeRunId.slice(0, 12)}</span>
              </p>
              <p className="text-xs text-mid-gray">
                Estado: {state ?? "desconocido"}
              </p>
            </div>
          ) : (
            <div className="rounded-xl bg-light-gray/40 p-6 text-center text-sm text-mid-gray">
              No tienes runs activos. Inicia uno en la pestaña anterior.
            </div>
          )}
        </TabsPrimitive.Content>

        {/* ── Tab: Insights históricos ───────────────────────── */}
        <TabsPrimitive.Content value="history" className="mt-4">
          <div
            className="space-y-3 rounded-xl bg-white p-5 ring-1 ring-light-gray"
            data-testid="history-tab-picker"
          >
            <p
              id="history-picker-hint"
              className="text-sm text-mid-gray"
            >
              Selecciona un deportista para ver su histórico de análisis IA
              aprobados.
            </p>
            <AthleteCombobox
              id="history-athlete-picker"
              label="Deportista"
              value={historyAthleteId}
              onChange={handleHistoryAthletePick}
              placeholder="Buscar por nombre o categoría..."
              data-testid="history-athlete-combobox"
            />
          </div>
        </TabsPrimitive.Content>
      </TabsPrimitive.Root>
    </div>
  );
}

export default RaceAnalysisPage;
