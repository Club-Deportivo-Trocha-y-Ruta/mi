/**
 * RaceAnalysisPage — landing del módulo race-analysis v2 (§10.2).
 *
 * 3 tabs:
 *  - Nuevo análisis: StartRunForm + (cuando hay run activo) timeline +
 *    HITL card + viewer + chat + PDF download.
 *  - Runs activos: placeholder con info del run actual (lista real
 *    requiere endpoint GET /runs no expuesto aún — TODO F8+).
 *  - Insights históricos: placeholder (depende de GET
 *    /athletes/{id}/insights, ver §9.7 — pendiente UI).
 *
 * El ExplainModeBanner es global a la página.
 *
 * Acceso: coach + admin (configurado en App.tsx).
 */
import { useMemo, useState } from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { History, ListChecks, Plus } from "lucide-react";

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

function TabTrigger({
  value,
  icon: Icon,
  label,
}: {
  value: string;
  icon: typeof Plus;
  label: string;
}) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className="flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-mid-gray transition-colors data-[state=active]:bg-white data-[state=active]:text-charcoal data-[state=active]:shadow-sm"
    >
      <Icon size={16} aria-hidden="true" />
      {label}
    </TabsPrimitive.Trigger>
  );
}

export function RaceAnalysisPage() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [hitlStepId, setHitlStepId] = useState<string | null>(null);
  const [chatAthleteId, setChatAthleteId] = useState<number | null>(null);

  // Resolvemos el nombre del atleta seleccionado en el chat — para
  // mostrar contexto visual sin tocar el body POST /chat.
  const athletesQuery = useAthletes();
  const chatAthleteName = useMemo(() => {
    if (chatAthleteId == null) return null;
    const a = athletesQuery.data?.items.find((x) => x.id === chatAthleteId);
    return a ? `${a.first_name} ${a.last_name}` : null;
  }, [chatAthleteId, athletesQuery.data]);

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
          <div className="rounded-xl bg-light-gray/40 p-6 text-center text-sm text-mid-gray">
            Historial de insights por atleta — próximamente (depende del
            endpoint GET /athletes/&#123;id&#125;/insights).
          </div>
        </TabsPrimitive.Content>
      </TabsPrimitive.Root>
    </div>
  );
}

export default RaceAnalysisPage;
