/**
 * ReportDetailPage — Editor del Informe Técnico Mensual (coach/admin)
 *
 * Coach/admin: edita bloques narrativos por sección, regenera IA por bloque,
 *              aprueba el informe y descarga el PDF.
 *
 * El informe es un documento interno del equipo técnico: la ruta está protegida
 * con allowedRoles [coach, admin] y los padres son redirigidos por el guard de
 * ruta (ProtectedRoute) antes de montar esta página.
 *
 * Path: /training/reports/:year/:month
 */

import { useState } from "react";
import { useRef } from "react";
import { ChevronDown, Download, RefreshCw, CheckCircle2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import {
  useMonthlyReport,
  useDownloadMonthlyReportPdf,
  useDownloadMonthlyReportDocx,
  useUpdateReportBlocks,
  useRegenerateBlock,
} from "@/api/trainingSessions";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MonthlyMetricsTable } from "@/components/training/MonthlyMetricsTable";
import { formatDateTime } from "@/lib/datetime";
import { triggerBlobDownload } from "@/lib/download";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type {
  MonthlyMetricsSnapshot,
  NarrativeBlock,
  NarrativeBlockKey,
  CompetitionResult,
  MonthlyReportFull,
} from "@/types/trainingSession.types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MONTH_NAMES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

const BLOCK_ORDER: NarrativeBlockKey[] = [
  "objetivo",
  "plan_entrenamiento",
  "desarrollo",
  "competencia",
  "resultados",
  "conclusiones",
  "apoyos_materiales",
  "analisis_grupo",
];

const BLOCK_LABELS: Record<NarrativeBlockKey, string> = {
  objetivo: "Objetivo del período",
  plan_entrenamiento: "Plan de entrenamiento",
  desarrollo: "Desarrollo de actividades",
  resultados: "Resultados obtenidos",
  conclusiones: "Conclusiones",
  apoyos_materiales: "Apoyos materiales y salidas",
  analisis_grupo: "Análisis del grupo",
  competencia: "Participación en competencia",
};

const sectionHeading = "text-sm font-semibold uppercase tracking-wide text-mid-gray mb-3";

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-white p-5 space-y-3 shadow-card">
      {[...Array(3)].map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-light-gray"
          style={{ width: `${70 - i * 15}%` }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatusBadge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: "draft" | "approved" | undefined }) {
  if (status === "approved") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800"
        data-testid="status-badge-approved"
      >
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        Aprobado
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800"
      data-testid="status-badge-draft"
    >
      Borrador
    </span>
  );
}

// ---------------------------------------------------------------------------
// NarrativeBlockEditor — un bloque narrativo editable
// ---------------------------------------------------------------------------

interface NarrativeBlockEditorProps {
  blockKey: NarrativeBlockKey;
  block: NarrativeBlock | null | undefined;
  clubId: number;
  year: number;
  month: number;
  disabled?: boolean;
}

function NarrativeBlockEditor({
  blockKey,
  block,
  clubId,
  year,
  month,
  disabled,
}: NarrativeBlockEditorProps) {
  const [localText, setLocalText] = useState(block?.final_text ?? block?.ai_draft ?? "");
  const [savedFeedback, setSavedFeedback] = useState(false);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateMutation = useUpdateReportBlocks(clubId, year, month);
  const regenerateMutation = useRegenerateBlock(clubId, year, month);

  const isSaving = updateMutation.isPending;
  const isRegenerating = regenerateMutation.isPending && regenerateMutation.variables === blockKey;

  const hasDraft = !!block?.ai_draft;
  const draftDiffersFromFinal =
    hasDraft && block?.ai_draft !== (block?.final_text ?? "");

  function handleSave() {
    if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    updateMutation.mutate(
      { blocks: { [blockKey]: localText } },
      {
        onSuccess: () => {
          setSavedFeedback(true);
          savedTimerRef.current = setTimeout(() => setSavedFeedback(false), 2500);
        },
      },
    );
  }

  function handleRegenerate() {
    regenerateMutation.mutate(blockKey, {
      onSuccess: (updated) => {
        const newBlock = updated.narrative_blocks?.[blockKey];
        if (newBlock?.ai_draft) {
          setLocalText(newBlock.ai_draft);
        }
      },
    });
  }

  const textareaId = `block-textarea-${blockKey}`;
  const errorId = `block-error-${blockKey}`;

  return (
    <div
      className="rounded-xl bg-white p-5 space-y-3 shadow-card"
      data-testid={`block-editor-${blockKey}`}
    >
      {/* Header del bloque */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-charcoal">
          {BLOCK_LABELS[blockKey]}
        </h3>
        <div className="flex items-center gap-2">
          {/* Botón Regenerar IA */}
          <button
            type="button"
            onClick={handleRegenerate}
            disabled={disabled || isRegenerating || isSaving}
            aria-label={`Regenerar con IA el bloque "${BLOCK_LABELS[blockKey]}"`}
            className="flex min-h-[44px] items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-40 shadow-ring"
            data-testid={`regenerate-btn-${blockKey}`}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isRegenerating ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            {isRegenerating ? "Generando…" : hasDraft ? "Regenerar" : "Generar con IA"}
          </button>
          {/* Botón Guardar */}
          <button
            type="button"
            onClick={handleSave}
            disabled={disabled || isSaving || isRegenerating}
            aria-label={`Guardar bloque "${BLOCK_LABELS[blockKey]}"`}
            className="flex min-h-[44px] items-center gap-1.5 rounded-lg bg-charcoal px-3 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            data-testid={`save-btn-${blockKey}`}
          >
            {isSaving ? "Guardando…" : savedFeedback ? "Guardado" : "Guardar"}
          </button>
        </div>
      </div>

      {/* Banner IA — cuando ai_draft existe */}
      {hasDraft && (
        <div
          className="flex items-start gap-2 rounded-lg border border-yellow-300 bg-yellow-50 px-3 py-2"
          role="note"
          data-testid={`ai-draft-banner-${blockKey}`}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 20 20"
            fill="none"
            className="mt-0.5 shrink-0 text-yellow-600"
            aria-hidden="true"
          >
            <path
              d="M10 2L2 17h16L10 2z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinejoin="round"
            />
            <path
              d="M10 8v4M10 14h.01"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          <p className="text-xs text-yellow-800">
            Texto generado por IA — revísalo antes de aprobar.
          </p>
        </div>
      )}

      {/* Texto borrador de referencia (si difiere del final_text) */}
      {draftDiffersFromFinal && block?.ai_draft && (
        <details className="text-xs">
          <summary className="cursor-pointer text-mid-gray hover:text-charcoal">
            Ver borrador IA original
          </summary>
          <p
            className="mt-2 whitespace-pre-wrap rounded-lg bg-light-gray px-3 py-2 text-mid-gray"
            data-testid={`ai-draft-text-${blockKey}`}
          >
            {block.ai_draft}
          </p>
        </details>
      )}

      {/* Textarea editable */}
      <div>
        <label htmlFor={textareaId} className="sr-only">
          {BLOCK_LABELS[blockKey]}
        </label>
        <textarea
          id={textareaId}
          rows={6}
          value={localText}
          onChange={(e) => setLocalText(e.target.value)}
          disabled={disabled || isRegenerating}
          placeholder={`Escribe el contenido de "${BLOCK_LABELS[blockKey]}"…`}
          className="w-full resize-y rounded-lg px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50 shadow-ring"
          aria-describedby={updateMutation.isError ? errorId : undefined}
          aria-invalid={updateMutation.isError}
          data-testid={`block-textarea-${blockKey}`}
        />
        {updateMutation.isError && (
          <p id={errorId} className="mt-1 text-xs text-red-600" role="alert">
            No se pudo guardar. Intenta de nuevo.
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CompetitionResultsTable — solo lectura
// ---------------------------------------------------------------------------

/** Agrupa por event_id (jornada); event_id ausente (informes antiguos) cae en un único grupo "sin identidad de evento". */
function groupByEvent(results: CompetitionResult[]): { eventId: number | null; eventName: string | null; awardsPoints: boolean | null; rows: CompetitionResult[] }[] {
  const groups = new Map<string, { eventId: number | null; eventName: string | null; awardsPoints: boolean | null; rows: CompetitionResult[] }>();
  for (const r of results) {
    const key = r.event_id != null ? String(r.event_id) : `legacy-${r.event_name ?? "sin-evento"}`;
    const existing = groups.get(key);
    if (existing) {
      existing.rows.push(r);
    } else {
      groups.set(key, {
        eventId: r.event_id ?? null,
        eventName: r.event_name,
        awardsPoints: r.awards_points ?? null,
        rows: [r],
      });
    }
  }
  return Array.from(groups.values());
}

function CompetitionResultsTable({ results }: { results: CompetitionResult[] }) {
  if (results.length === 0) {
    return (
      <p className="text-sm text-mid-gray" data-testid="competition-results-empty">
        Sin competencias en el período.
      </p>
    );
  }
  const groups = groupByEvent(results);
  return (
    <div className="space-y-4" data-testid="competition-results-table">
      {groups.map((group, gi) => (
        <div
          key={group.eventId ?? gi}
          className="overflow-x-auto rounded-xl bg-white shadow-ring"
        >
          <div
            className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
            style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}
          >
            <h3 className="text-sm font-semibold text-charcoal">
              {group.eventName ?? "Evento sin nombre"}
            </h3>
            {group.awardsPoints !== null && (
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  group.awardsPoints
                    ? "bg-green-100 text-green-800"
                    : "bg-light-gray text-mid-gray"
                }`}
                data-testid={`event-points-note-${group.eventId ?? gi}`}
              >
                {group.awardsPoints ? "Otorga puntos" : "No otorga puntos"}
              </span>
            )}
          </div>
          <table className="min-w-full text-sm">
            <caption className="sr-only">Resultados de {group.eventName ?? "la jornada"}</caption>
            <thead style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}>
              <tr>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Atleta
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Categoría
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Pos.
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Puntos
                </th>
              </tr>
            </thead>
            <tbody>
              {group.rows.map((r, i) => (
                <tr
                  key={i}
                  style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
                  className="transition-colors hover:bg-light-gray"
                >
                  <td className="px-4 py-3 font-medium text-charcoal">{r.athlete_name}</td>
                  <td className="px-4 py-3 text-mid-gray">{r.category ?? "—"}</td>
                  <td className="px-4 py-3 text-mid-gray">{r.position ?? "—"}</td>
                  <td className="px-4 py-3 text-mid-gray">{r.points ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CoachEditorView — la vista completa de edición para coach/admin
// ---------------------------------------------------------------------------

interface CoachEditorViewProps {
  report: MonthlyReportFull;
  clubId: number;
  year: number;
  month: number;
  onDownloadPdf: () => void;
  onDownloadDocx: () => void;
  isDownloadingPdf: boolean;
  isDownloadingDocx: boolean;
  downloadError: string | null;
}

function CoachEditorView({
  report,
  clubId,
  year,
  month,
  onDownloadPdf,
  onDownloadDocx,
  isDownloadingPdf,
  isDownloadingDocx,
  downloadError,
}: CoachEditorViewProps) {
  const monthLabel = MONTH_NAMES[report.month - 1] ?? String(report.month);
  const metrics = report.metrics_snapshot as MonthlyMetricsSnapshot | null;
  const blocks = report.narrative_blocks;
  const results = report.competition_results ?? [];
  const isApproved = report.status === "approved";
  const isDownloading = isDownloadingPdf || isDownloadingDocx;

  const updateMutation = useUpdateReportBlocks(clubId, year, month);
  const [approveError, setApproveError] = useState<string | null>(null);

  function handleApprove() {
    setApproveError(null);
    updateMutation.mutate(
      { status: "approved" },
      {
        onError: () => setApproveError("No se pudo aprobar el informe. Intenta de nuevo."),
      },
    );
  }

  return (
    <section className="space-y-5">
      {/* Header */}
      <div className="rounded-xl bg-white px-5 py-4 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link
              to="/training/reports"
              className="mb-2 inline-block text-xs text-mid-gray transition-opacity hover:opacity-70"
            >
              ← Informes mensuales
            </Link>
            <div className="flex flex-wrap items-center gap-2">
              <h1
                className="font-display text-xl text-charcoal"
              >
                Informe Técnico — {monthLabel} {report.year}
              </h1>
              <StatusBadge status={report.status} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* Aprobar */}
            <button
              type="button"
              onClick={handleApprove}
              disabled={isApproved || updateMutation.isPending}
              className="flex min-h-[44px] items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-40 shadow-ring"
              data-testid="approve-btn"
            >
              <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              {updateMutation.isPending && !isApproved ? "Aprobando…" : "Aprobar"}
            </button>
            {/* Descargar informe — PDF o DOCX */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  disabled={isDownloading}
                  aria-label="Descargar informe"
                  className="flex min-h-[48px] items-center gap-1.5 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                  data-testid="download-menu-trigger"
                >
                  <Download className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {isDownloading ? "Descargando…" : "Descargar informe"}
                  <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={onDownloadPdf}
                  disabled={isDownloading}
                  data-testid="download-pdf-option"
                >
                  <Download className="mr-2 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  Descargar PDF
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={onDownloadDocx}
                  disabled={isDownloading}
                  data-testid="download-docx-option"
                >
                  <Download className="mr-2 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  Descargar DOCX
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        {approveError && (
          <p className="mt-2 text-xs text-red-600" role="alert">
            {approveError}
          </p>
        )}
      </div>

      {downloadError && (
        <div
          className="rounded-xl border border-red-200 bg-red-50 px-5 py-4"
          role="alert"
          data-testid="download-error-banner"
        >
          <p className="text-sm text-red-700">{downloadError}</p>
        </div>
      )}

      {/* Métricas — solo lectura */}
      {metrics && (
        <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
          <h2 className={sectionHeading}>Métricas del mes</h2>
          <MonthlyMetricsTable metrics={metrics} athleteNames={report.athlete_names} />
        </div>
      )}

      {/* Bloques narrativos */}
      {blocks ? (
        <div className="space-y-4">
          <h2 className={sectionHeading}>Secciones del informe</h2>
          {BLOCK_ORDER.map((key) => (
            <NarrativeBlockEditor
              key={key}
              blockKey={key}
              block={blocks[key]}
              clubId={clubId}
              year={year}
              month={month}
              disabled={isApproved}
            />
          ))}
        </div>
      ) : (
        <div className="rounded-xl bg-white px-5 py-4 shadow-card">
          <p className="text-sm text-mid-gray">
            Este informe no tiene secciones narrativas disponibles.
          </p>
        </div>
      )}

      {/* Resultados de competencia — solo lectura + bloque narrativo */}
      <div className="rounded-xl bg-white px-5 py-4 space-y-4 shadow-card">
        <h2 className={sectionHeading}>Participación en competencia</h2>
        <CompetitionResultsTable results={results} />
      </div>

      {/* Footer */}
      <div className="rounded-xl bg-white px-5 py-4 shadow-card">
        <p className="text-xs text-mid-gray">
          Generado el {formatDateTime(report.generated_at)}
        </p>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// ReportDetailPage — entry point
// ---------------------------------------------------------------------------

export function ReportDetailPage() {
  const { year: yearParam, month: monthParam } = useParams<{ year: string; month: string }>();
  const year = Number(yearParam);
  const month = Number(monthParam);

  const user = useAuthStore((s) => s.user);
  const clubId = user?.club_ids?.[0];
  const isCoach = user?.role === UserRole.coach || user?.role === UserRole.admin;

  const [downloadError, setDownloadError] = useState<string | null>(null);

  const reportQuery = useMonthlyReport(clubId, year, month);
  const downloadPdfMutation = useDownloadMonthlyReportPdf(clubId ?? 0);
  const downloadDocxMutation = useDownloadMonthlyReportDocx(clubId ?? 0);

  const report = reportQuery.data;

  function handleDownloadPdf() {
    if (!clubId) return;
    setDownloadError(null);
    downloadPdfMutation.mutate(
      { year, month },
      {
        onSuccess: (blob) => {
          triggerBlobDownload(
            blob,
            `informe-tecnico-${year}-${String(month).padStart(2, "0")}.pdf`,
          );
        },
        onError: () =>
          setDownloadError("No se pudo descargar el PDF. Intenta de nuevo."),
      },
    );
  }

  function handleDownloadDocx() {
    if (!clubId) return;
    setDownloadError(null);
    downloadDocxMutation.mutate(
      { year, month },
      {
        onSuccess: (blob) => {
          triggerBlobDownload(
            blob,
            `informe-tecnico-${year}-${String(month).padStart(2, "0")}.docx`,
          );
        },
        onError: () =>
          setDownloadError("No se pudo descargar el DOCX. Intenta de nuevo."),
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
        <div className="rounded-xl bg-white p-8 text-center shadow-card">
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

  if (isCoach && clubId) {
    return (
      <CoachEditorView
        report={report}
        clubId={clubId}
        year={year}
        month={month}
        onDownloadPdf={handleDownloadPdf}
        onDownloadDocx={handleDownloadDocx}
        isDownloadingPdf={downloadPdfMutation.isPending}
        isDownloadingDocx={downloadDocxMutation.isPending}
        downloadError={downloadError}
      />
    );
  }

  // Llegados aquí la cuenta no tiene club asignado (o un rol sin acceso, aunque
  // el guard de ruta ya redirige a los padres a /my-athletes antes de montar
  // esta página). No caemos en una vista de reporte: estado neutro.
  return (
    <section className="space-y-4">
      <div className="rounded-xl bg-white p-8 text-center shadow-card">
        <p className="text-base font-medium text-charcoal">Informe no disponible</p>
        <p className="mt-1 text-sm text-mid-gray">
          Tu cuenta no tiene un club asignado para ver este informe.
        </p>
        <Link
          to="/dashboard"
          className="mt-4 inline-block text-sm font-medium text-charcoal underline hover:opacity-70"
        >
          Volver al inicio
        </Link>
      </div>
    </section>
  );
}
