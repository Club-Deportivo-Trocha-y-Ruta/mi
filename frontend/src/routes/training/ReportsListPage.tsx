import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";

import {
  useGenerateMonthlyReport,
  useMonthlyReports,
  useSendMonthlyReport,
} from "@/api/trainingSessions";
import { ConfirmModal } from "@/components/common/ConfirmModal";
import { useAuthStore } from "@/store/auth.store";
import {
  monthlyReportCreateSchema,
  type MonthlyReportFormValues,
} from "@/schemas/monthlyReport.schema";
import type { MonthlyReportFull } from "@/types/trainingSession.types";

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

function formatDateTime(isoStr: string): string {
  const d = new Date(isoStr);
  return d.toLocaleDateString("es-CO", { day: "2-digit", month: "short", year: "numeric" });
}

const cardStyle: React.CSSProperties = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

interface GenerateModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (values: MonthlyReportFormValues) => void;
  isPending: boolean;
  error: string | null;
}

function GenerateModal({ open, onClose, onSubmit, isPending, error }: GenerateModalProps) {
  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: currentYear - 2023 }, (_, i) => currentYear - i);
  const months = MONTH_NAMES.map((name, i) => ({ value: i + 1, label: name }));

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<MonthlyReportFormValues>({
    resolver: zodResolver(monthlyReportCreateSchema),
    defaultValues: {
      year: currentYear,
      month: new Date().getMonth() === 0 ? 12 : new Date().getMonth(),
      force_regenerate: false,
    },
  });

  function handleClose() {
    reset();
    onClose();
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(19, 19, 22, 0.65)", backdropFilter: "blur(2px)" }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="generate-report-title"
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white"
        style={cardStyle}
      >
        <div className="flex items-center justify-between border-b border-[rgba(34,42,53,0.08)] px-6 py-4">
          <h2
            id="generate-report-title"
            className="text-base text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            Generar reporte mensual
          </h2>
          <button
            type="button"
            onClick={handleClose}
            disabled={isPending}
            className="rounded-lg p-1.5 text-mid-gray transition-colors hover:bg-light-gray disabled:opacity-50"
            aria-label="Cerrar"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="px-6 py-5 space-y-4" data-testid="generate-report-form">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="report-year" className="mb-1 block text-xs font-medium text-charcoal">
                Año
              </label>
              <select
                id="report-year"
                {...register("year", { valueAsNumber: true })}
                className="w-full rounded-lg px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
              >
                {years.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
              {errors.year && (
                <p className="mt-1 text-xs text-red-600">{errors.year.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="report-month" className="mb-1 block text-xs font-medium text-charcoal">
                Mes
              </label>
              <select
                id="report-month"
                {...register("month", { valueAsNumber: true })}
                className="w-full rounded-lg px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
              >
                {months.map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              {errors.month && (
                <p className="mt-1 text-xs text-red-600">{errors.month.message}</p>
              )}
            </div>
          </div>

          <div>
            <label htmlFor="coach-observations" className="mb-1 block text-xs font-medium text-charcoal">
              Observaciones del entrenador{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </label>
            <textarea
              id="coach-observations"
              {...register("coach_observations")}
              rows={4}
              maxLength={2000}
              placeholder="Contexto adicional para el resumen de IA…"
              className="w-full resize-none rounded-lg px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40"
              style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            />
            {errors.coach_observations && (
              <p className="mt-1 text-xs text-red-600">{errors.coach_observations.message}</p>
            )}
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm text-charcoal">
            <input
              type="checkbox"
              {...register("force_regenerate")}
              className="h-4 w-4 rounded border-mid-gray accent-charcoal"
            />
            Forzar regeneración si ya existe
          </label>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
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
              type="submit"
              disabled={isPending}
              className="flex items-center gap-2 rounded-lg bg-charcoal px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {isPending && (
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
              )}
              Generar reporte
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface ReportsTableProps {
  reports: MonthlyReportFull[];
  onResend: (report: MonthlyReportFull) => void;
}

function ReportsTable({ reports, onResend }: ReportsTableProps) {
  const navigate = useNavigate();

  return (
    <>
      {/* Mobile: cards */}
      <ul role="list" className="flex flex-col gap-3 md:hidden">
        {reports.map((r) => (
          <li key={r.id}>
            <div className="rounded-xl bg-white p-4" style={cardStyle}>
              <p className="font-medium text-charcoal">
                {MONTH_NAMES[r.month - 1]} {r.year}
              </p>
              <p className="mt-0.5 text-xs text-mid-gray">
                Generado el {formatDateTime(r.generated_at)}
              </p>
              <p className="mt-0.5 text-xs text-mid-gray">
                {r.sent_at ? `Enviado el ${formatDateTime(r.sent_at)}` : "Pendiente de envío"}
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => navigate(`/training/reports/${r.year}/${r.month}`)}
                  className="rounded-lg px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                >
                  Ver
                </button>
                <button
                  type="button"
                  onClick={() => onResend(r)}
                  className="rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-70"
                >
                  Re-enviar al club
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>

      {/* Desktop: tabla */}
      <div
        className="hidden overflow-x-auto rounded-xl bg-white md:block"
        style={cardStyle}
      >
        <table className="min-w-full text-sm">
          <thead style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}>
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Mes / Año
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Generado el
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Enviado el
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                Acciones
              </th>
            </tr>
          </thead>
          <tbody>
            {reports.map((r) => (
              <tr
                key={r.id}
                className="transition-colors hover:bg-light-gray"
                style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
              >
                <td className="px-4 py-3 font-medium text-charcoal">
                  {MONTH_NAMES[r.month - 1]} {r.year}
                </td>
                <td className="px-4 py-3 text-mid-gray">{formatDateTime(r.generated_at)}</td>
                <td className="px-4 py-3 text-mid-gray">
                  {r.sent_at ? formatDateTime(r.sent_at) : (
                    <span className="text-yellow-700">Pendiente</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => navigate(`/training/reports/${r.year}/${r.month}`)}
                      className="rounded-lg px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                      style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                    >
                      Ver
                    </button>
                    <button
                      type="button"
                      onClick={() => onResend(r)}
                      className="rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-70"
                    >
                      Re-enviar al club
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function ReportsListPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clubId = user?.club_ids?.[0];

  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [resendTarget, setResendTarget] = useState<MonthlyReportFull | null>(null);

  const reportsQuery = useMonthlyReports(clubId);
  const generateMutation = useGenerateMonthlyReport(clubId ?? 0);
  const sendMutation = useSendMonthlyReport(clubId ?? 0);

  const reports = reportsQuery.data ?? [];

  function handleGenerate(values: MonthlyReportFormValues) {
    setGenerateError(null);
    generateMutation.mutate(
      {
        year: values.year,
        month: values.month,
        coach_observations: values.coach_observations || undefined,
        force_regenerate: values.force_regenerate,
      },
      {
        onSuccess: (report) => {
          setShowGenerateModal(false);
          navigate(`/training/reports/${report.year}/${report.month}`);
        },
        onError: (err) => {
          if (isAxiosError(err) && err.response?.status === 409) {
            setGenerateError(
              "Ya existe un reporte para este período. Activa \"Forzar regeneración\" para sobreescribirlo.",
            );
          } else {
            const msg =
              isAxiosError(err) && err.response?.data?.detail
                ? String(err.response.data.detail)
                : "Error al generar el reporte. Intenta de nuevo.";
            setGenerateError(msg);
          }
        },
      },
    );
  }

  function handleResendConfirm() {
    if (!resendTarget) return;
    sendMutation.mutate(
      { year: resendTarget.year, month: resendTarget.month },
      {
        onSuccess: () => setResendTarget(null),
        onError: () => setResendTarget(null),
      },
    );
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1
            className="text-2xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            Reportes Mensuales
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            Resúmenes de actividad del club generados con IA.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setGenerateError(null);
            setShowGenerateModal(true);
          }}
          className="rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          data-testid="open-generate-modal"
        >
          + Generar reporte
        </button>
      </div>

      {reportsQuery.isLoading && (
        <div
          className="space-y-2 rounded-xl bg-white p-4"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        >
          {Array.from({ length: 3 }).map((_, idx) => (
            <div key={idx} className="h-9 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {reportsQuery.isError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          No se pudo cargar la lista de reportes.
        </p>
      )}

      {!reportsQuery.isLoading && !reportsQuery.isError && reports.length === 0 && (
        <div
          className="rounded-xl bg-white p-10 text-center"
          style={{
            boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
            borderStyle: "dashed",
          }}
          data-testid="empty-state"
        >
          <p className="text-sm text-mid-gray">
            Aún no hay reportes mensuales generados.
          </p>
          <button
            type="button"
            onClick={() => {
              setGenerateError(null);
              setShowGenerateModal(true);
            }}
            className="mt-3 inline-block text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
          >
            + Generar primer reporte
          </button>
        </div>
      )}

      {!reportsQuery.isLoading && !reportsQuery.isError && reports.length > 0 && (
        <ReportsTable reports={reports} onResend={setResendTarget} />
      )}

      <GenerateModal
        open={showGenerateModal}
        onClose={() => setShowGenerateModal(false)}
        onSubmit={handleGenerate}
        isPending={generateMutation.isPending}
        error={generateError}
      />

      <ConfirmModal
        open={!!resendTarget}
        title="Re-enviar reporte al club"
        body={
          resendTarget
            ? `¿Deseas re-enviar el reporte de ${MONTH_NAMES[resendTarget.month - 1]} ${resendTarget.year} a todos los administradores del club?`
            : ""
        }
        confirmLabel="Sí, re-enviar"
        cancelLabel="Cancelar"
        isPending={sendMutation.isPending}
        onCancel={() => setResendTarget(null)}
        onConfirm={handleResendConfirm}
      />
    </section>
  );
}
