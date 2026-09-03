/**
 * AthleteNewsletterStudioPage — estudio de la bitácora (feature 038, T302).
 *
 * Única página de `/training/athlete-newsletters/:athleteId/:newsletterId`
 * — todos los boletines son bitácoras (StageLog v2); el formato legacy fue
 * retirado (ver docs/technical-notes.md).
 *
 * Layout (plan.md "Coach studio"):
 *  - ≥ 768px: dos columnas — PDF (`PdfPreviewPanel`) a la izquierda,
 *    bloques (`BlockPanel` + `AnalystPicker`) a la derecha; `DeliveryPanel`
 *    debajo, a todo el ancho.
 *  - < 768px: `Tabs` "Vista previa" / "Bloques" / "Entrega".
 *
 * El coach solo necesita ver/descargar el PDF generado — no hay
 * previsualización Móvil/Correo dentro de la app (se retiró el toggle de
 * `DevicePreview`; ver docs/technical-notes.md).
 *
 * Edición: cada guardado de bloque fusiona el patch en el draft local de
 * `stage_overrides` (preview optimista vía `applyOverrides`) y dispara un
 * PATCH con el objeto **completo** — el backend reemplaza `stage_overrides`
 * entero, no hace merge (`routers/athlete_monthly_newsletters.py`).
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CheckCircle2, Send } from "lucide-react";

import {
  useAthleteNewsletter,
  useApproveNewsletter,
  useSendNewsletter,
  useDownloadNewsletterPdf,
  parseApiError,
} from "@/api/athleteNewsletters";
import { useAthlete } from "@/hooks/athletes/useAthlete";
import { useUpdateStageLog } from "@/hooks/training/useUpdateStageLog";
import { useRegenerateBlock } from "@/hooks/training/useRegenerateBlock";
import { AthleteLink } from "@/components/shared/AthleteLink";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { PdfPreviewPanel } from "@/components/newsletter/studio/PdfPreviewPanel";
import { BlockPanel } from "@/components/newsletter/studio/BlockPanel";
import { AnalystPicker } from "@/components/newsletter/studio/AnalystPicker";
import { DeliveryPanel } from "@/components/newsletter/studio/DeliveryPanel";
import { StatusStepper } from "@/components/newsletter/studio/StatusStepper";
import { RegenerateDialog } from "@/components/newsletter/studio/RegenerateDialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { applyOverrides, clearOverrideBlock } from "@/lib/applyOverrides";
import type { RegenerableBlock, StageOverrides, HideableBlock } from "@/types/stageLog.types";

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const BLOCK_TITLES: Record<RegenerableBlock, string> = {
  stage_title: "Título de la etapa",
  summit_caption: "Cima del mes",
  observations: "Lo que vio el entrenador",
  analyst_reading: "Lectura del analista",
  next_segment_text: "Próximo tramo",
  family_compass: "Brújula de la familia",
};

/** ≥ 768px: dos columnas. < 768px: tabs. Mismo patrón que ParentCalendarPage. */
function isDesktopViewport(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia("(min-width: 768px)").matches;
}

function useIsDesktop(): boolean {
  const [desktop, setDesktop] = useState<boolean>(isDesktopViewport);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(min-width: 768px)");
    function handler(e: MediaQueryListEvent) {
      setDesktop(e.matches);
    }
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return desktop;
}

function SkeletonStudio() {
  return (
    <div className="space-y-5">
      <div className="h-16 animate-pulse rounded-xl bg-white shadow-card" />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,1fr)_360px]">
        <div className="h-96 animate-pulse rounded-xl bg-white shadow-card" />
        <div className="h-96 animate-pulse rounded-xl bg-white shadow-card" />
      </div>
    </div>
  );
}

interface ToastState {
  type: "success" | "error";
  message: string;
}

export function AthleteNewsletterStudioPage() {
  const { athleteId: athleteIdParam, newsletterId: newsletterIdParam } = useParams<{
    athleteId: string;
    newsletterId: string;
  }>();
  const athleteId = Number(athleteIdParam);
  const newsletterId = Number(newsletterIdParam);

  const isDesktop = useIsDesktop();

  const [toast, setToast] = useState<ToastState | null>(null);
  const [overridesDraft, setOverridesDraft] = useState<StageOverrides>({});
  const [regenerateTarget, setRegenerateTarget] = useState<RegenerableBlock | null>(null);
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [showSendConfirm, setShowSendConfirm] = useState(false);
  const [showResendConfirm, setShowResendConfirm] = useState(false);

  const newsletterQuery = useAthleteNewsletter(athleteId, newsletterId);
  const newsletter = newsletterQuery.data;
  const athleteQuery = useAthlete(athleteId, Number.isFinite(athleteId));

  const updateStageLog = useUpdateStageLog(athleteId, newsletterId);
  const regenerateBlock = useRegenerateBlock(athleteId, newsletterId);
  const approveMutation = useApproveNewsletter(athleteId, newsletterId);
  const sendMutation = useSendNewsletter(athleteId, newsletterId);
  const downloadMutation = useDownloadNewsletterPdf();

  // Sincroniza el draft local con el valor guardado del servidor: cada vez
  // que la query trae datos nuevos (carga inicial, refetch tras PATCH), el
  // draft arranca desde la verdad del servidor — nunca se acumulan ediciones
  // "fantasma" que ya fueron persistidas.
  useEffect(() => {
    if (newsletter?.stage_overrides) {
      setOverridesDraft(newsletter.stage_overrides as StageOverrides);
    } else if (newsletter) {
      setOverridesDraft({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newsletter?.id, newsletter?.updated_at]);

  function showToast(type: "success" | "error", message: string) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 5000);
  }

  function scrollToBlock(dataBlock: string) {
    if (typeof document === "undefined") return;
    const el = document.querySelector(`[data-block="${dataBlock}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleSaveBlock(_block: RegenerableBlock, patch: Partial<StageOverrides>) {
    const merged: StageOverrides = { ...overridesDraft, ...patch };
    setOverridesDraft(merged);
    updateStageLog.mutate(
      { stage_overrides: merged },
      {
        onSuccess: () => showToast("success", "Bloque guardado."),
        onError: (err) => showToast("error", parseApiError(err, "No se pudo guardar el bloque.")),
      },
    );
  }

  function handleSaveCoachNote(note: string) {
    updateStageLog.mutate(
      { coach_note: note },
      {
        onSuccess: () => showToast("success", "Nota del entrenador guardada."),
        onError: (err) => showToast("error", parseApiError(err, "No se pudo guardar la nota.")),
      },
    );
  }

  function handleHideToggle(block: HideableBlock) {
    if (!newsletter) return;
    const current = newsletter.hidden_blocks ?? [];
    const next = current.includes(block)
      ? current.filter((b) => b !== block)
      : [...current, block];
    updateStageLog.mutate(
      { hidden_blocks: next },
      {
        onError: (err) => showToast("error", parseApiError(err, "No se pudo actualizar el bloque.")),
      },
    );
  }

  function handleReorderInsights(newOrder: number[]) {
    updateStageLog.mutate(
      { selected_race_insight_ids: newOrder },
      {
        onError: (err) => showToast("error", parseApiError(err, "No se pudo reordenar el análisis.")),
      },
    );
  }

  function handleRegenerateConfirm(instruction: string | undefined) {
    if (!regenerateTarget) return;
    const block = regenerateTarget;
    regenerateBlock.mutate(
      { block, instruction },
      {
        onSuccess: () => {
          setOverridesDraft((prev) => clearOverrideBlock(prev, block));
          setRegenerateTarget(null);
          showToast("success", "Bloque regenerado con IA.");
        },
        onError: (err) => {
          setRegenerateTarget(null);
          showToast("error", parseApiError(err, "No se pudo regenerar el bloque."));
        },
      },
    );
  }

  function handleApprove() {
    approveMutation.mutate(undefined, {
      onSuccess: () => {
        setShowApproveConfirm(false);
        showToast("success", "Boletín aprobado. Ya puedes enviarlo a los padres.");
      },
      onError: (err) => {
        setShowApproveConfirm(false);
        showToast("error", parseApiError(err, "Error al aprobar el boletín."));
      },
    });
  }

  function handleSend() {
    sendMutation.mutate(undefined, {
      onSuccess: () => {
        setShowSendConfirm(false);
        showToast("success", "Boletín enviado correctamente a los padres.");
      },
      onError: (err) => {
        setShowSendConfirm(false);
        showToast("error", parseApiError(err, "Error al enviar el boletín."));
      },
    });
  }

  function handleResend() {
    sendMutation.mutate(
      { force_resend: true },
      {
        onSuccess: () => {
          setShowResendConfirm(false);
          showToast("success", "Boletín reenviado a las familias registradas.");
        },
        onError: (err) => {
          setShowResendConfirm(false);
          showToast("error", parseApiError(err, "Error al reenviar el boletín."));
        },
      },
    );
  }

  function handleDownloadPdf() {
    downloadMutation.mutate(
      { athleteId, newsletterId },
      {
        onSuccess: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `bitacora-${athleteId}-${newsletter?.year}-${String(newsletter?.month).padStart(2, "0")}.pdf`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        },
        onError: (err) => showToast("error", parseApiError(err, "Error al descargar el PDF.")),
      },
    );
  }

  // ---------------------------------------------------------------------------
  // Render states
  // ---------------------------------------------------------------------------

  if (newsletterQuery.isLoading) {
    return <SkeletonStudio />;
  }

  if (newsletterQuery.isError || !newsletter) {
    return (
      <section>
        <div className="rounded-xl bg-white p-8 text-center shadow-card">
          <p className="text-base font-medium text-charcoal">Boletín no encontrado</p>
          <p className="mt-1 text-sm text-mid-gray">
            El boletín solicitado no existe o no tienes permiso para verlo.
          </p>
          <Link
            to="/training/athlete-newsletters"
            className="mt-4 inline-block text-sm font-medium text-charcoal underline hover:opacity-70"
          >
            Volver a boletines
          </Link>
        </div>
      </section>
    );
  }

  if (!newsletter.stage_log) {
    return (
      <section>
        <div className="rounded-xl bg-white p-8 text-center shadow-card">
          <p className="text-base font-medium text-charcoal">
            Esta bitácora todavía no tiene contenido generado.
          </p>
        </div>
      </section>
    );
  }

  const previewStageLog = applyOverrides(newsletter.stage_log, overridesDraft);
  const monthLabel = MONTH_NAMES[(newsletter.month ?? 1) - 1] ?? String(newsletter.month);
  const canApprove = newsletter.status === "draft";
  const canSend = newsletter.status === "approved";
  const canDownloadPdf = newsletter.status !== "failed";
  const isSaving = updateStageLog.isPending;

  const blockPanelAndPicker = (
    <div className="space-y-4">
      <h2 className="sr-only">Bloques de la bitácora</h2>
      <BlockPanel
        stageLog={previewStageLog}
        hiddenBlocks={newsletter.hidden_blocks}
        isSaving={isSaving}
        regeneratingBlock={regenerateTarget}
        onSaveBlock={handleSaveBlock}
        onSaveCoachNote={handleSaveCoachNote}
        onRegenerateClick={(block) => setRegenerateTarget(block)}
        onHideToggle={handleHideToggle}
        onScrollToBlock={scrollToBlock}
      />
      <AnalystPicker
        athleteId={athleteId}
        selectedInsightIds={newsletter.selected_race_insight_ids ?? []}
        onReorder={handleReorderInsights}
        isSaving={isSaving}
      />
    </div>
  );

  const previewPanel = (
    <>
      <h2 className="sr-only">PDF de la bitácora</h2>
      <PdfPreviewPanel
        onDownloadPdf={handleDownloadPdf}
        isDownloadingPdf={downloadMutation.isPending}
        canDownloadPdf={canDownloadPdf}
      />
    </>
  );

  const deliveryPanel = (
    <DeliveryPanel
      delivery={newsletter.delivery}
      onResend={() => setShowResendConfirm(true)}
      isResending={sendMutation.isPending}
    />
  );

  return (
    <section className="space-y-5" data-testid="newsletter-studio-page">
      {toast && (
        <div
          className={`flex items-center justify-between gap-3 rounded-xl px-4 py-3 ${
            toast.type === "success"
              ? "border border-green-200 bg-green-50"
              : "border border-red-200 bg-red-50"
          }`}
          role={toast.type === "error" ? "alert" : "status"}
          data-testid={`toast-${toast.type}`}
        >
          <p className={`text-sm ${toast.type === "success" ? "text-green-800" : "text-red-700"}`}>
            {toast.message}
          </p>
          <button
            type="button"
            onClick={() => setToast(null)}
            className={`text-xs underline ${toast.type === "success" ? "text-green-700" : "text-red-600"}`}
            aria-label="Cerrar notificación"
          >
            Cerrar
          </button>
        </div>
      )}

      {/* Header */}
      <div className="rounded-xl bg-white px-5 py-4 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Link
                to="/training/athlete-newsletters"
                className="text-xs text-mid-gray transition-opacity hover:opacity-70"
              >
                ← Boletines mensuales
              </Link>
              {athleteQuery.data && (
                <div className="inline-flex rounded-full shadow-ring" data-testid="athlete-profile-chip">
                  <AthleteLink
                    athleteId={athleteId}
                    tab="newsletters"
                    className="inline-flex min-h-[44px] items-center gap-1.5 rounded-full py-2 px-3 text-xs font-medium text-charcoal transition-opacity hover:opacity-70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-charcoal"
                  >
                    <span
                      className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-charcoal text-[10px] font-bold text-white"
                      aria-hidden="true"
                    >
                      {athleteQuery.data.first_name[0]}
                      {athleteQuery.data.last_name[0]}
                    </span>
                    <span>
                      {athleteQuery.data.first_name} {athleteQuery.data.last_name}
                    </span>
                  </AthleteLink>
                </div>
              )}
            </div>
            <h1 className="font-display text-xl text-charcoal">
              Bitácora de {monthLabel} {newsletter.year}
            </h1>
            <p className="mt-0.5 text-sm text-mid-gray">Etapa {previewStageLog.stage_number}</p>
          </div>

          <div className="flex flex-col items-end gap-2">
            <StatusStepper status={newsletter.status} readAt={newsletter.read_at} />
            <div className="flex flex-wrap justify-end gap-2">
              {canApprove && (
                <button
                  type="button"
                  onClick={() => setShowApproveConfirm(true)}
                  disabled={approveMutation.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:bg-green-700 disabled:opacity-40"
                  data-testid="studio-approve-btn"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Aprobar
                </button>
              )}
              {canSend && (
                <button
                  type="button"
                  onClick={() => setShowSendConfirm(true)}
                  disabled={sendMutation.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-charcoal px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                  data-testid="studio-send-btn"
                >
                  <Send className="h-3.5 w-3.5" aria-hidden="true" />
                  Enviar
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Layout responsivo */}
      {isDesktop ? (
        <div data-testid="studio-layout-desktop">
          <div className="grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,1fr)_380px]">
            <div>{previewPanel}</div>
            <div>{blockPanelAndPicker}</div>
          </div>
          <div className="mt-5">{deliveryPanel}</div>
        </div>
      ) : (
        <div data-testid="studio-layout-mobile">
          <Tabs defaultValue="preview">
            <TabsList>
              <TabsTrigger value="preview">Vista previa</TabsTrigger>
              <TabsTrigger value="blocks">Bloques</TabsTrigger>
              <TabsTrigger value="delivery">Entrega</TabsTrigger>
            </TabsList>
            <TabsContent value="preview">{previewPanel}</TabsContent>
            <TabsContent value="blocks">{blockPanelAndPicker}</TabsContent>
            <TabsContent value="delivery">{deliveryPanel}</TabsContent>
          </Tabs>
        </div>
      )}

      {/* Dialogs */}
      <ConfirmDialog
        open={showApproveConfirm}
        title="Aprobar bitácora"
        description={`¿Deseas aprobar la bitácora de ${monthLabel} ${newsletter.year}? Una vez aprobada podrás enviarla a los padres.`}
        confirmLabel="Sí, aprobar"
        cancelLabel="Cancelar"
        isPending={approveMutation.isPending}
        onCancel={() => setShowApproveConfirm(false)}
        onConfirm={handleApprove}
      />

      <ConfirmDialog
        open={showSendConfirm}
        title="Enviar bitácora a los padres"
        description="Se enviará por email a los padres registrados del atleta, junto con el enlace a la versión web."
        confirmLabel="Sí, enviar"
        cancelLabel="Cancelar"
        isPending={sendMutation.isPending}
        onCancel={() => setShowSendConfirm(false)}
        onConfirm={handleSend}
      />

      <ConfirmDialog
        open={showResendConfirm}
        title="Reenviar bitácora"
        description="Se reenviará por email a todas las familias registradas de este boletín, aunque ya lo hayan recibido."
        confirmLabel="Sí, reenviar"
        cancelLabel="Cancelar"
        isPending={sendMutation.isPending}
        onCancel={() => setShowResendConfirm(false)}
        onConfirm={handleResend}
      />

      <RegenerateDialog
        open={regenerateTarget !== null}
        blockTitle={regenerateTarget ? BLOCK_TITLES[regenerateTarget] : ""}
        isPending={regenerateBlock.isPending}
        onConfirm={handleRegenerateConfirm}
        onCancel={() => setRegenerateTarget(null)}
      />
    </section>
  );
}
