import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { useMonthlyReport, useSendMonthlyReport } from "@/api/trainingSessions";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { MonthlyMetricsTable } from "@/components/training/MonthlyMetricsTable";
import { formatDateTime } from "@/lib/datetime";
import { useAuthStore } from "@/store/auth.store";
import type { MonthlyMetricsSnapshot } from "@/types/trainingSession.types";

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const cardStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

const sectionHeading = "text-sm font-semibold uppercase tracking-wide text-mid-gray mb-3";

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-white p-5 space-y-3" style={cardStyle}>
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-4 animate-pulse rounded bg-light-gray" style={{ width: `${70 - i * 15}%` }} />
      ))}
    </div>
  );
}

export function ReportDetailPage() {
  const { year: yearParam, month: monthParam } = useParams<{ year: string; month: string }>();
  const year = Number(yearParam);
  const month = Number(monthParam);

  const user = useAuthStore((s) => s.user);
  const clubId = user?.club_ids?.[0];

  const [showSendModal, setShowSendModal] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(false);

  const reportQuery = useMonthlyReport(clubId, year, month);
  const sendMutation = useSendMonthlyReport(clubId ?? 0);

  const report = reportQuery.data;

  function handleSendConfirm() {
    if (!clubId) return;
    sendMutation.mutate(
      { year, month },
      {
        onSuccess: () => {
          setShowSendModal(false);
          setSendSuccess(true);
        },
        onError: () => setShowSendModal(false),
      },
    );
  }

  if (reportQuery.isLoading) {
    return (
      <section className="space-y-4">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </section>
    );
  }

  if (reportQuery.isError || !report) {
    return (
      <section className="space-y-4">
        <div className="rounded-xl bg-white p-8 text-center" style={cardStyle}>
          <p className="text-base font-medium text-charcoal">Reporte no encontrado</p>
          <p className="mt-1 text-sm text-mid-gray">
            El reporte solicitado no existe o no tienes permiso para verlo.
          </p>
          <Link
            to="/training/reports"
            className="mt-4 inline-block text-sm font-medium text-charcoal underline hover:opacity-70"
          >
            Volver a reportes
          </Link>
        </div>
      </section>
    );
  }

  const monthLabel = MONTH_NAMES[report.month - 1] ?? String(report.month);
  const metrics = report.metrics_snapshot as MonthlyMetricsSnapshot | null;

  return (
    <section className="space-y-5">
      {/* Header */}
      <div className="rounded-xl bg-white px-5 py-4" style={cardStyle}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link
              to="/training/reports"
              className="mb-2 inline-block text-xs text-mid-gray transition-opacity hover:opacity-70"
            >
              ← Reportes mensuales
            </Link>
            <h1
              className="text-xl text-charcoal"
              style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
            >
              Reporte mensual — {monthLabel} {report.year}
            </h1>
          </div>
          <div className="flex flex-col items-end gap-1">
            <button
              type="button"
              onClick={() => setShowSendModal(true)}
              className={
                report.sent_at
                  ? "flex items-center gap-1.5 rounded-lg border border-charcoal/20 bg-white px-4 py-2 text-sm font-semibold text-charcoal transition-opacity hover:opacity-70"
                  : "rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
              }
              data-testid="resend-button"
            >
              {report.sent_at && (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" aria-hidden="true" />
              )}
              {report.sent_at ? "Volver a enviar" : "Re-enviar al club"}
            </button>
            {report.sent_at && (
              <span className="text-xs text-mid-gray">
                Enviado el {formatDateTime(report.sent_at)}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Banner IA — solo cuando existe ai_summary real */}
      {report.ai_summary && (
        <div
          className="flex items-start gap-3 rounded-xl border border-yellow-300 bg-yellow-50 px-5 py-4"
          role="note"
          data-testid="ai-banner"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" className="mt-0.5 shrink-0 text-yellow-600" aria-hidden="true">
            <path d="M10 2L2 17h16L10 2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            <path d="M10 8v4M10 14h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <p className="text-sm text-yellow-800">
            Resumen generado por IA — revisalo antes de enviar.
          </p>
        </div>
      )}

      {sendSuccess && (
        <div
          className="rounded-xl border border-green-300 bg-green-50 px-5 py-4"
          role="status"
          data-testid="send-success-banner"
        >
          <p className="text-sm text-green-800">
            Reporte re-enviado correctamente. Enviado el{" "}
            {report.sent_at ? formatDateTime(report.sent_at) : "—"}
          </p>
        </div>
      )}

      {/* Resumen IA */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-2" style={cardStyle}>
        <h2 className={sectionHeading}>Resumen IA</h2>
        {report.ai_summary ? (
          <p
            className="whitespace-pre-wrap text-sm text-charcoal"
            data-testid="ai-summary-text"
          >
            {report.ai_summary}
          </p>
        ) : (
          <p className="text-sm text-mid-gray">Sin resumen generado.</p>
        )}
      </div>

      {/* Observaciones del coach */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-2" style={cardStyle}>
        <h2 className={sectionHeading}>Observaciones del entrenador</h2>
        {report.coach_observations ? (
          <p className="whitespace-pre-wrap text-sm text-charcoal">
            {report.coach_observations}
          </p>
        ) : (
          <p className="text-sm text-mid-gray">Sin observaciones registradas.</p>
        )}
      </div>

      {/* Métricas */}
      {metrics && (
        <div className="rounded-xl bg-white px-5 py-4 space-y-4" style={cardStyle}>
          <h2 className={sectionHeading}>Métricas del mes</h2>
          <MonthlyMetricsTable metrics={metrics} />
        </div>
      )}

      {/* Footer */}
      <div className="rounded-xl bg-white px-5 py-4" style={cardStyle}>
        <p className="text-xs text-mid-gray">
          Generado el {formatDateTime(report.generated_at)}
        </p>
        {report.sent_at && (
          <p className="mt-1 text-xs text-mid-gray" data-testid="sent-at-text">
            Enviado el {formatDateTime(report.sent_at)}
          </p>
        )}
      </div>

      <ConfirmModal
        open={showSendModal}
        title="Re-enviar reporte al club"
        body={`¿Deseas re-enviar el reporte de ${monthLabel} ${report.year} a todos los administradores del club?`}
        confirmLabel="Sí, re-enviar"
        cancelLabel="Cancelar"
        isPending={sendMutation.isPending}
        onCancel={() => setShowSendModal(false)}
        onConfirm={handleSendConfirm}
      />
    </section>
  );
}
