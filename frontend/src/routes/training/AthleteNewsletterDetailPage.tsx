/**
 * AthleteNewsletterDetailPage — detalle y flujo de aprobación de un boletín.
 *
 * Layout 2 columnas (desktop) / stacked (mobile):
 * - Izquierda: preview de bloques email_blocks (NewsletterPreviewBlocks)
 * - Derecha: editor de narrativa IA (NewsletterNarrativeEditor) + acciones
 *
 * Flujo de estados:
 * - draft   → Editor habilitado, "Aprobar" y "Descargar PDF" habilitados, "Enviar" disabled
 * - approved → Editor disabled, "Enviar" habilitado, "Descargar PDF" habilitado
 * - sent    → Todo disabled, mostrar timestamp sent_at
 * - failed  → Mostrar error_message, botón "Regenerar"
 *
 * Path: /training/athlete-newsletters/:athleteId/:newsletterId
 * Roles: coach, admin
 */

import { useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { CheckCircle2, Download, RefreshCw, Send, AlertTriangle } from "lucide-react";

import {
  useAthleteNewsletter,
  useApproveNewsletter,
  useSendNewsletter,
  usePatchNewsletter,
  useGenerateNewsletter,
  useDownloadNewsletterPdf,
  parseApiError,
} from "@/api/athleteNewsletters";
import { NewsletterNarrativeEditor } from "@/components/training/NewsletterNarrativeEditor";
import { NewsletterPreviewBlocks } from "@/components/training/NewsletterPreviewBlocks";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogBody,
  DialogFooter,
} from "@/components/ui/dialog";
import { formatDateTime } from "@/lib/datetime";
import type { NarrativeOverride } from "@/types/athleteNewsletter.types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const cardStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function SkeletonDetail() {
  return (
    <div className="space-y-5">
      <div className="h-16 animate-pulse rounded-xl bg-white" style={cardStyle} />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-white" style={cardStyle} />
          ))}
        </div>
        <div className="h-64 animate-pulse rounded-xl bg-white" style={cardStyle} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Send dialog
// ---------------------------------------------------------------------------

interface SendDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (forceIndividual: boolean) => void;
  isPending: boolean;
  siblingBlockedError: boolean;
}

function SendDialog({
  open,
  onClose,
  onConfirm,
  isPending,
  siblingBlockedError,
}: SendDialogProps) {
  const [forcedIndividual, setForcedIndividual] = useState(false);

  function handleClose() {
    setForcedIndividual(false);
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Enviar boletín a los padres</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <p className="text-sm text-charcoal">
            El boletín se enviará por email a los padres registrados del atleta.
          </p>
          <p className="text-xs text-mid-gray">
            Se enviara a todos los padres con email registrado. El PDF incluye
            informacion completa del atleta.
          </p>

          {siblingBlockedError && (
            <div
              className="rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-3 space-y-2"
              role="alert"
              data-testid="sibling-blocked-alert"
            >
              <div className="flex items-start gap-2">
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-yellow-600"
                  aria-hidden="true"
                />
                <p className="text-xs text-yellow-800">
                  Este padre tiene otro hijo con boletín aún en borrador. Si envias
                  individualmente, ese hijo recibirá el email por separado.
                </p>
              </div>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-charcoal">
                <input
                  type="checkbox"
                  checked={forcedIndividual}
                  onChange={(e) => setForcedIndividual(e.target.checked)}
                  className="h-4 w-4 rounded border-mid-gray accent-charcoal"
                />
                Enviar individualmente (sin esperar a hermanos)
              </label>
            </div>
          )}
        </DialogBody>
        <DialogFooter>
          <button
            type="button"
            onClick={handleClose}
            disabled={isPending}
            className="rounded-lg px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity disabled:opacity-50"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => onConfirm(forcedIndividual)}
            disabled={isPending || (siblingBlockedError && !forcedIndividual)}
            className="flex items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            data-testid="confirm-send-btn"
          >
            {isPending && (
              <svg
                className="h-4 w-4 animate-spin"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"
                />
              </svg>
            )}
            <Send className="h-4 w-4" aria-hidden="true" />
            Enviar a los padres
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Toast inline (no external dep needed)
// ---------------------------------------------------------------------------

interface ToastBannerProps {
  type: "success" | "error";
  message: string;
  onDismiss: () => void;
}

function ToastBanner({ type, message, onDismiss }: ToastBannerProps) {
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-xl px-4 py-3 ${
        type === "success"
          ? "border border-green-200 bg-green-50"
          : "border border-red-200 bg-red-50"
      }`}
      role={type === "error" ? "alert" : "status"}
      data-testid={`toast-${type}`}
    >
      <p
        className={`text-sm ${type === "success" ? "text-green-800" : "text-red-700"}`}
      >
        {message}
      </p>
      <button
        type="button"
        onClick={onDismiss}
        className={`text-xs underline ${type === "success" ? "text-green-700" : "text-red-600"}`}
        aria-label="Cerrar notificación"
      >
        Cerrar
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function AthleteNewsletterDetailPage() {
  const { athleteId: athleteIdParam, newsletterId: newsletterIdParam } = useParams<{
    athleteId: string;
    newsletterId: string;
  }>();
  const athleteId = Number(athleteIdParam);
  const newsletterId = Number(newsletterIdParam);

  const [showSendDialog, setShowSendDialog] = useState(false);
  const [siblingBlocked, setSiblingBlocked] = useState(false);
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const newsletterQuery = useAthleteNewsletter(athleteId, newsletterId);
  const newsletter = newsletterQuery.data;

  const patchMutation = usePatchNewsletter(athleteId, newsletterId);
  const approveMutation = useApproveNewsletter(athleteId, newsletterId);
  const sendMutation = useSendNewsletter(athleteId, newsletterId);
  const generateMutation = useGenerateNewsletter(athleteId);
  const downloadMutation = useDownloadNewsletterPdf();

  const showToast = useCallback(
    (type: "success" | "error", message: string) => {
      setToast({ type, message });
      setTimeout(() => setToast(null), 5000);
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleSaveNarrative(overrides: NarrativeOverride) {
    patchMutation.mutate(
      { coach_narrative_overrides: overrides },
      {
        onSuccess: () => showToast("success", "Narrativa guardada correctamente."),
        onError: (err) =>
          showToast("error", parseApiError(err, "Error al guardar la narrativa.")),
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

  function handleSend(forceIndividual: boolean) {
    setSiblingBlocked(false);
    sendMutation.mutate(
      { force_individual: forceIndividual },
      {
        onSuccess: () => {
          setShowSendDialog(false);
          showToast("success", "Boletín enviado correctamente a los padres.");
        },
        onError: (err) => {
          if (isAxiosError(err) && err.response?.status === 409) {
            // Sibling still in draft
            setSiblingBlocked(true);
            // Keep dialog open with the warning
          } else {
            setShowSendDialog(false);
            showToast("error", parseApiError(err, "Error al enviar el boletín."));
          }
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
          a.download = `boletin-${athleteId}-${newsletter?.year}-${String(newsletter?.month).padStart(2, "0")}.pdf`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        },
        onError: (err) =>
          showToast("error", parseApiError(err, "Error al descargar el PDF.")),
      },
    );
  }

  function handleRegenerate() {
    if (!newsletter) return;
    generateMutation.mutate(
      { year: newsletter.year, month: newsletter.month, force: true },
      {
        onSuccess: () =>
          showToast("success", "Boletín regenerado correctamente."),
        onError: (err) =>
          showToast("error", parseApiError(err, "Error al regenerar el boletín.")),
      },
    );
  }

  // ---------------------------------------------------------------------------
  // Render states
  // ---------------------------------------------------------------------------

  if (newsletterQuery.isLoading) {
    return <SkeletonDetail />;
  }

  if (newsletterQuery.isError || !newsletter) {
    return (
      <section>
        <div className="rounded-xl bg-white p-8 text-center" style={cardStyle}>
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

  const status = newsletter.status;
  const isDraft = status === "draft";
  const isApproved = status === "approved";
  const isSent = status === "sent";
  const isFailed = status === "failed";

  const monthLabel =
    MONTH_NAMES[(newsletter.month ?? 1) - 1] ?? String(newsletter.month);

  const canEdit = isDraft;
  const canApprove = isDraft;
  const canDownloadPdf = isDraft || isApproved || isSent;
  const canSend = isApproved;

  return (
    <section className="space-y-5">
      {/* Toast */}
      {toast && (
        <ToastBanner
          type={toast.type}
          message={toast.message}
          onDismiss={() => setToast(null)}
        />
      )}

      {/* Header */}
      <div className="rounded-xl bg-white px-5 py-4" style={cardStyle}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link
              to="/training/athlete-newsletters"
              className="mb-2 inline-block text-xs text-mid-gray transition-opacity hover:opacity-70"
            >
              ← Boletines mensuales
            </Link>
            <h1
              className="text-xl text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
            >
              Boletín de {monthLabel} {newsletter.year}
            </h1>
            <p className="mt-0.5 text-sm text-mid-gray">Atleta #{newsletter.athlete_id}</p>
          </div>

          {/* Status badge */}
          <div className="flex flex-col items-end gap-1">
            {{
              draft: (
                <span className="rounded-full bg-yellow-100 px-3 py-1 text-xs font-semibold text-yellow-700 border border-yellow-300">
                  Borrador
                </span>
              ),
              approved: (
                <span className="flex items-center gap-1.5 rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700 border border-green-300">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Aprobado
                </span>
              ),
              sent: (
                <span className="flex items-center gap-1.5 rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700 border border-blue-300">
                  <Send className="h-3.5 w-3.5" aria-hidden="true" />
                  Enviado
                </span>
              ),
              failed: (
                <span className="flex items-center gap-1.5 rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-red-700 border border-red-300">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                  Fallido
                </span>
              ),
            }[status]}

            {isSent && newsletter.sent_at && (
              <span className="text-xs text-mid-gray" data-testid="sent-at-label">
                Enviado el {formatDateTime(newsletter.sent_at)}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Error state */}
      {isFailed && newsletter.error_message && (
        <div
          className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3"
          role="alert"
          data-testid="error-message-banner"
        >
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800">Error en la generación</p>
            <p className="mt-0.5 text-sm text-red-700">{newsletter.error_message}</p>
          </div>
          <button
            type="button"
            onClick={handleRegenerate}
            disabled={generateMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 transition-opacity hover:bg-red-200 disabled:opacity-50"
            data-testid="regenerate-btn"
          >
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
            Regenerar
          </button>
        </div>
      )}

      {/* Main content: 2-column layout */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Left: Preview */}
        <div>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-mid-gray">
            Preview del boletín
          </h2>
          <NewsletterPreviewBlocks
            emailBlocks={newsletter.email_blocks}
            badges={newsletter.badges_earned}
          />
        </div>

        {/* Right: Narrative editor + actions */}
        <div className="space-y-4">
          {/* Actions panel */}
          <div className="rounded-xl bg-white px-5 py-4 space-y-3" style={cardStyle}>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-mid-gray">
              Acciones
            </h2>

            <div className="flex flex-col gap-2">
              {/* Download PDF */}
              <button
                type="button"
                onClick={handleDownloadPdf}
                disabled={!canDownloadPdf || downloadMutation.isPending}
                className="flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                data-testid="download-pdf-btn"
                aria-label="Descargar PDF del boletín"
              >
                {downloadMutation.isPending ? (
                  <svg
                    className="h-4 w-4 animate-spin"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8v8H4z"
                    />
                  </svg>
                ) : (
                  <Download className="h-4 w-4" aria-hidden="true" />
                )}
                Descargar PDF preview
              </button>

              {/* Approve */}
              {canApprove && (
                <button
                  type="button"
                  onClick={() => setShowApproveConfirm(true)}
                  disabled={approveMutation.isPending}
                  className="flex items-center justify-center gap-2 rounded-lg bg-green-600 px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:bg-green-700 disabled:opacity-40"
                  data-testid="approve-btn"
                  aria-label="Aprobar boletín"
                >
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                  Aprobar boletín
                </button>
              )}

              {/* Send */}
              <button
                type="button"
                onClick={() => {
                  setSiblingBlocked(false);
                  setShowSendDialog(true);
                }}
                disabled={!canSend || sendMutation.isPending}
                className="flex items-center justify-center gap-2 rounded-lg bg-charcoal px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                data-testid="send-btn"
                aria-label="Enviar boletín a los padres"
              >
                <Send className="h-4 w-4" aria-hidden="true" />
                Enviar a los padres
              </button>
            </div>

            {/* Sent info */}
            {isSent && (
              <p className="text-xs text-mid-gray" data-testid="sent-info">
                Boletín enviado el {newsletter.sent_at ? formatDateTime(newsletter.sent_at) : "—"}.
                No se puede modificar.
              </p>
            )}

            {/* Approved by */}
            {(isApproved || isSent) && newsletter.approved_at && (
              <p className="text-xs text-mid-gray">
                Aprobado el {formatDateTime(newsletter.approved_at)}
              </p>
            )}
          </div>

          {/* Narrative editor */}
          <div className="rounded-xl bg-white px-5 py-4" style={cardStyle}>
            <NewsletterNarrativeEditor
              aiNarrative={newsletter.ai_narrative}
              currentOverrides={newsletter.coach_narrative_overrides}
              disabled={!canEdit}
              isPending={patchMutation.isPending}
              onSave={handleSaveNarrative}
            />
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="rounded-xl bg-white px-5 py-3" style={cardStyle}>
        <p className="text-xs text-mid-gray">
          Creado el {formatDateTime(newsletter.created_at)}
        </p>
      </div>

      {/* Dialogs */}
      <ConfirmModal
        open={showApproveConfirm}
        title="Aprobar boletín"
        body={`¿Deseas aprobar el boletín de ${monthLabel} ${newsletter.year}? Una vez aprobado podrás enviarlo a los padres.`}
        confirmLabel="Sí, aprobar"
        cancelLabel="Cancelar"
        isPending={approveMutation.isPending}
        onCancel={() => setShowApproveConfirm(false)}
        onConfirm={handleApprove}
      />

      <SendDialog
        open={showSendDialog}
        onClose={() => {
          setShowSendDialog(false);
          setSiblingBlocked(false);
        }}
        onConfirm={handleSend}
        isPending={sendMutation.isPending}
        siblingBlockedError={siblingBlocked}
      />
    </section>
  );
}
