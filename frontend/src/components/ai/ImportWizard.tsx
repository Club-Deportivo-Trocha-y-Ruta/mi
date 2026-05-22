/**
 * ImportWizard — wizard de 3 pasos para cargar resultados Copa Valle.
 *
 * Step 1: form metadata (series, season, válida, fecha, ciudad) + upload
 *         resultados (PDF/CSV) + general opcional (PDF).
 * Step 2: dry-run preview con tabla de matches y resolución de ambiguos
 *         vía AthleteCombobox.
 * Step 3: resumen del commit + link al análisis.
 *
 * Privacidad: los nombres mostrados (display_name) son los publicados por
 * la Federación en los PDFs oficiales, ya son información pública.
 *
 * Diseño:
 *   - State local con useReducer-ish (varios useState por simplicidad).
 *   - No persiste en Zustand; navegar fuera reinicia (DT-5 del workflow).
 *   - Stepper visual = breadcrumbs simples con `aria-current`.
 */
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { z } from "zod";

import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import { RaceUploadZone } from "@/components/ai/RaceUploadZone";

// DiffTable lazy → solo se descarga si el wizard detecta modo revisión.
// Mantiene el chunk de ImportWizard cerca de la baseline F-UP (~18 KB).
const DiffTable = lazy(() =>
  import("@/components/ai/DiffTable").then((m) => ({ default: m.DiffTable })),
);
import {
  useImportCommit,
  useImportDryRun,
  useImportParse,
} from "@/hooks/ai/useRaceImports";
import { cn } from "@/lib/utils";
import type {
  ImportCommitResponse,
  ImportDryRunResponse,
  ImportDryRunRevisionResponse,
  ImportMatchPreview,
  ImportParseResponse,
  ImportResolvedMatch,
} from "@/types/raceImports.types";

// ---------------------------------------------------------------------------
// F-UP-REV5 — Revision UX helpers
// ---------------------------------------------------------------------------

/**
 * Type guard — discrimina la union de dry-run response (matches vs revision).
 *
 * Backend marca `is_revision: true` solo en el branch revisión; en F-UP normal
 * el campo es `false` o ausente.
 */
function isRevisionDryRun(
  data: ImportDryRunResponse | undefined,
): data is ImportDryRunRevisionResponse {
  return !!data && (data as ImportDryRunRevisionResponse).is_revision === true;
}

const REVISION_REASON_MAX = 300;

/** Banner naranja si el diff es inusualmente grande (R1 mitigación). */
function shouldWarnUnusualDiff(summary: {
  n_total: number;
  n_delete: number;
  n_unchanged: number;
}): boolean {
  if (summary.n_total > 500) return true;
  // Si hay deletes y exceden 20% del unchanged.
  if (summary.n_delete > 0 && summary.n_delete > summary.n_unchanged * 0.2) {
    return true;
  }
  return false;
}

function formatCommittedAt(iso: string | undefined | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-CO", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Step 1 schema
// ---------------------------------------------------------------------------

const CURRENT_YEAR = new Date().getFullYear();

const step1Schema = z.object({
  series_name: z.string().min(2, "Nombre de serie requerido"),
  season: z
    .number({ message: "Temporada requerida" })
    .int()
    .min(2020, "Temporada inválida")
    .max(2100, "Temporada inválida"),
  valida_num: z
    .number({ message: "Número de válida requerido" })
    .int()
    .min(1, "Mínimo 1")
    .max(9, "Máximo 9"),
  event_name: z.string().min(2, "Nombre del evento requerido"),
  event_date: z
    .string()
    .min(1, "Fecha requerida")
    .refine(
      (v) => /^\d{4}-\d{2}-\d{2}$/.test(v),
      "Formato YYYY-MM-DD",
    ),
  location: z.string().min(2, "Ciudad requerida"),
});

type Step1Values = z.infer<typeof step1Schema>;

// ---------------------------------------------------------------------------
// Stepper visual
// ---------------------------------------------------------------------------

const STEPS = [
  { idx: 1, label: "Archivos y datos" },
  { idx: 2, label: "Validar matches" },
  { idx: 3, label: "Resultado" },
] as const;

function Stepper({ active }: { active: 1 | 2 | 3 }) {
  return (
    <ol
      className="mb-4 flex items-center gap-2 text-xs"
      aria-label="Pasos del wizard"
    >
      {STEPS.map((s, i) => {
        const done = s.idx < active;
        const current = s.idx === active;
        return (
          <li
            key={s.idx}
            className="flex items-center gap-2"
            aria-current={current ? "step" : undefined}
          >
            <span
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold",
                done && "bg-charcoal text-white",
                current && "bg-blue-100 text-blue-700 ring-2 ring-blue-500",
                !done && !current && "bg-light-gray text-mid-gray",
              )}
              aria-hidden="true"
            >
              {done ? "✓" : s.idx}
            </span>
            <span
              className={cn(
                "font-medium",
                current ? "text-charcoal" : "text-mid-gray",
              )}
            >
              {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <span className="mx-1 text-mid-gray" aria-hidden="true">
                →
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// Helper para extraer mensaje del error axios
// ---------------------------------------------------------------------------

function getErrMsg(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null) {
    const e = err as {
      response?: { data?: { detail?: unknown }; status?: number };
      message?: string;
    };
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
    }
    if (e.response?.status === 413) {
      return "El archivo excede el tamaño permitido (máx 8 MB).";
    }
    if (e.response?.status === 409) {
      return "Este PDF ya fue ingestado previamente.";
    }
    if (e.response?.status === 500) {
      return "Error interno al procesar la ingesta. Revisa el archivo o contacta soporte.";
    }
    if (e.response?.status === 422) {
      return "Datos inválidos. Revisa el formulario y vuelve a intentar.";
    }
    if (e.message && !/status code \d+/i.test(e.message)) {
      // Solo mostrar e.message si NO es el genérico "Request failed with status code XXX"
      return e.message;
    }
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface ImportWizardProps {
  /** Callback opcional al completar commit. */
  onCompleted?: (response: ImportCommitResponse) => void;
}

export function ImportWizard({ onCompleted }: ImportWizardProps) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [parseResult, setParseResult] = useState<ImportParseResponse | null>(
    null,
  );
  const [resultadosPdf, setResultadosPdf] = useState<File | null>(null);
  const [generalPdf, setGeneralPdf] = useState<File | null>(null);
  // Resoluciones por competitor_normalized_name → athlete_id (null = no match).
  const [resolutions, setResolutions] = useState<
    Record<string, number | null>
  >({});
  const [onlyPending, setOnlyPending] = useState(false);
  const [step1Error, setStep1Error] = useState<string | null>(null);
  // F-UP-REV5: motivo de revisión (obligatorio si hay deletes).
  const [revisionReason, setRevisionReason] = useState("");
  const [revisionReasonTouched, setRevisionReasonTouched] = useState(false);

  const parseMutation = useImportParse();
  const dryRunMutation = useImportDryRun();
  const commitMutation = useImportCommit();

  // ---------------- Step 1 form
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<Step1Values>({
    resolver: zodResolver(step1Schema),
    defaultValues: {
      series_name: "Copa Valle de Ciclomontañismo",
      season: CURRENT_YEAR,
      valida_num: 1,
      event_name: "",
      event_date: "",
      location: "",
    },
  });

  const submitStep1 = async (values: Step1Values) => {
    if (!resultadosPdf) {
      setStep1Error("Debes adjuntar el archivo de resultados.");
      return;
    }
    setStep1Error(null);
    try {
      const result = await parseMutation.mutateAsync({
        fields: {
          series_name: values.series_name,
          season: values.season,
          valida_num: values.valida_num,
          event_name: values.event_name,
          event_date: values.event_date,
          location: values.location,
          kind: generalPdf ? "both" : "resultados",
        },
        files: {
          resultadosPdf,
          generalPdf,
        },
      });
      setParseResult(result);
      setStep(2);
    } catch (err) {
      setStep1Error(getErrMsg(err, "No se pudo procesar el archivo."));
    }
  };

  // ---------------- Step 2 — auto-trigger dry-run al entrar
  useEffect(() => {
    if (step !== 2 || !parseResult) return;
    dryRunMutation.mutate(
      { parseId: parseResult.parse_id },
      {
        onSuccess: (data) => {
          // En modo revisión no hay matches que resolver — los matches del
          // import original ya están persistidos en BD.
          if (isRevisionDryRun(data)) {
            setResolutions({});
            return;
          }
          // Pre-poblar resoluciones con matches confirmados.
          const initial: Record<string, number | null> = {};
          for (const m of data.matches) {
            initial[m.competitor_normalized_name] =
              m.tyr_athlete?.id ?? null;
          }
          setResolutions(initial);
        },
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, parseResult]);

  const dryRunData: ImportDryRunResponse | undefined = dryRunMutation.data;
  const revisionData = isRevisionDryRun(dryRunData) ? dryRunData : null;
  const matchesData = !isRevisionDryRun(dryRunData) ? dryRunData : undefined;

  const pendingAmbiguous = useMemo(() => {
    if (!matchesData) return [];
    return matchesData.matches.filter(
      (m) =>
        m.is_ambiguous && resolutions[m.competitor_normalized_name] == null,
    );
  }, [matchesData, resolutions]);

  const visibleMatches = useMemo<ImportMatchPreview[]>(() => {
    if (!matchesData) return [];
    if (!onlyPending) return matchesData.matches;
    return matchesData.matches.filter(
      (m) =>
        m.is_ambiguous && resolutions[m.competitor_normalized_name] == null,
    );
  }, [matchesData, onlyPending, resolutions]);

  // F-UP-REV5 — validación de revision_reason (obligatorio si hay deletes).
  const reasonTrimmed = revisionReason.trim();
  const reasonRequired =
    revisionData != null && revisionData.diff_summary.n_delete > 0;
  const reasonValid = !reasonRequired || reasonTrimmed.length > 0;
  const reasonOverflow = revisionReason.length > REVISION_REASON_MAX;

  const canCommit = revisionData
    ? reasonValid && !reasonOverflow
    : pendingAmbiguous.length === 0 && !!matchesData;

  const submitCommit = async () => {
    if (!parseResult || !dryRunData) return;
    if (revisionData) {
      // Modo revisión: matches ya persistidos, sólo enviamos revision_reason
      // (cuando aplica). El backend recomputa el diff server-side y aplica
      // los cambios transaccionalmente.
      if (!reasonValid) {
        setRevisionReasonTouched(true);
        return;
      }
      try {
        const result = await commitMutation.mutateAsync({
          parseId: parseResult.parse_id,
          body: {
            resolved_matches: [],
            ...(reasonTrimmed.length > 0
              ? { revision_reason: reasonTrimmed }
              : {}),
          },
        });
        setStep(3);
        onCompleted?.(result);
      } catch {
        setStep(3);
      }
      return;
    }

    // Modo matches (F-UP normal).
    if (!matchesData) return;
    const resolved_matches: ImportResolvedMatch[] = matchesData.matches.map(
      (m) => ({
        competitor_normalized_name: m.competitor_normalized_name,
        athlete_id: resolutions[m.competitor_normalized_name] ?? null,
      }),
    );
    try {
      const result = await commitMutation.mutateAsync({
        parseId: parseResult.parse_id,
        body: { resolved_matches },
      });
      setStep(3);
      onCompleted?.(result);
    } catch {
      // El error se muestra en el render (step queda en 2 con commitMutation.isError).
      setStep(3);
    }
  };

  const reset = () => {
    setStep(1);
    setParseResult(null);
    setResultadosPdf(null);
    setGeneralPdf(null);
    setResolutions({});
    setOnlyPending(false);
    setStep1Error(null);
    setRevisionReason("");
    setRevisionReasonTouched(false);
    parseMutation.reset();
    dryRunMutation.reset();
    commitMutation.reset();
  };

  // ---------------- Render
  return (
    <section
      className="rounded-xl bg-white p-5 ring-1 ring-light-gray"
      data-testid="import-wizard"
      aria-label="Wizard de carga de resultados"
    >
      <Stepper active={step} />

      {step === 1 && (
        <form
          onSubmit={handleSubmit(submitStep1)}
          className="space-y-4"
          data-testid="import-wizard-step1"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label
                htmlFor="series_name"
                className="block text-xs font-medium text-mid-gray"
              >
                Nombre de la serie
              </label>
              <input
                id="series_name"
                type="text"
                {...register("series_name")}
                className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                data-testid="wizard-series-name"
              />
              {errors.series_name && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {errors.series_name.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="season"
                className="block text-xs font-medium text-mid-gray"
              >
                Temporada
              </label>
              <input
                id="season"
                type="number"
                min={2020}
                max={2100}
                {...register("season", { valueAsNumber: true })}
                className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                data-testid="wizard-season"
              />
              {errors.season && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {errors.season.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="valida_num"
                className="block text-xs font-medium text-mid-gray"
              >
                Válida #
              </label>
              <input
                id="valida_num"
                type="number"
                min={1}
                max={9}
                {...register("valida_num", { valueAsNumber: true })}
                className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                data-testid="wizard-valida-num"
              />
              {errors.valida_num && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {errors.valida_num.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="event_name"
                className="block text-xs font-medium text-mid-gray"
              >
                Nombre del evento
              </label>
              <input
                id="event_name"
                type="text"
                placeholder="Ej: Válida IV — Cali"
                {...register("event_name")}
                className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                data-testid="wizard-event-name"
              />
              {errors.event_name && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {errors.event_name.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="event_date"
                className="block text-xs font-medium text-mid-gray"
              >
                Fecha del evento
              </label>
              <input
                id="event_date"
                type="date"
                {...register("event_date")}
                className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                data-testid="wizard-event-date"
              />
              {errors.event_date && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {errors.event_date.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="location"
                className="block text-xs font-medium text-mid-gray"
              >
                Ciudad
              </label>
              <input
                id="location"
                type="text"
                placeholder="Ej: Cali"
                {...register("location")}
                className="mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                data-testid="wizard-location"
              />
              {errors.location && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {errors.location.message}
                </p>
              )}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <RaceUploadZone
              kind="resultados"
              label="Resultados (PDF o CSV) *"
              value={resultadosPdf}
              onChange={(f) => {
                setResultadosPdf(f);
                // Limpia error previo al reemplazar archivo (UX bug F-UP6 MEDIUM).
                if (step1Error) setStep1Error(null);
              }}
              hint="obligatorio"
            />
            <RaceUploadZone
              kind="general"
              label="General (PDF)"
              value={generalPdf}
              onChange={setGeneralPdf}
              hint="opcional"
            />
          </div>

          {step1Error && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
              data-testid="wizard-step1-error"
            >
              <div className="flex items-start gap-2">
                <AlertCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                <span>{step1Error}</span>
              </div>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={parseMutation.isPending}
              data-testid="wizard-step1-submit"
              className="inline-flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {parseMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              ) : (
                <ArrowRight size={14} aria-hidden="true" />
              )}
              Continuar
            </button>
          </div>
        </form>
      )}

      {step === 2 && (
        <div className="space-y-4" data-testid="import-wizard-step2">
          {dryRunMutation.isPending && (
            <div
              className="space-y-2"
              role="status"
              aria-live="polite"
              data-testid="wizard-dry-run-loading"
            >
              <p className="text-sm text-mid-gray">
                Validando datos…
              </p>
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-10 animate-pulse rounded-lg bg-light-gray"
                />
              ))}
            </div>
          )}

          {dryRunMutation.isError && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
              data-testid="wizard-step2-error"
            >
              {getErrMsg(
                dryRunMutation.error,
                "Error validando datos. Reintenta.",
              )}
            </div>
          )}

          {revisionData && (
            <div className="space-y-4" data-testid="wizard-revision-mode">
              {/* Banner revisión detectada */}
              <div
                role="status"
                className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900"
                data-testid="wizard-revision-banner"
              >
                <p className="font-semibold">Revisión detectada</p>
                <p className="mt-1 text-xs">
                  Válida{" "}
                  <strong>{parseResult?.header.valida_num ?? "?"}</strong> ya
                  fue importada el{" "}
                  <strong>
                    {formatCommittedAt(parseResult?.parent_committed_at)}
                  </strong>
                  . Cambios:{" "}
                  <strong>{revisionData.diff_summary.n_create}</strong> create ·{" "}
                  <strong>{revisionData.diff_summary.n_update}</strong> update ·{" "}
                  <strong>{revisionData.diff_summary.n_delete}</strong> delete ·{" "}
                  <strong>{revisionData.diff_summary.n_unchanged}</strong> sin
                  cambios (de un total de{" "}
                  <strong>{revisionData.diff_summary.n_total}</strong>).
                </p>
              </div>

              {/* Banner naranja warning si diff inusualmente grande */}
              {shouldWarnUnusualDiff(revisionData.diff_summary) && (
                <div
                  role="alert"
                  className="rounded-lg border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-900"
                  data-testid="wizard-revision-warning-large"
                >
                  <div className="flex items-start gap-2">
                    <AlertCircle
                      size={16}
                      aria-hidden="true"
                      className="mt-0.5 shrink-0"
                    />
                    <span>
                      Cambios inusualmente grandes — verifica que sea la
                      misma válida antes de aplicar.
                    </span>
                  </div>
                </div>
              )}

              {/* Diff table — lazy para mantener chunk wizard pequeño */}
              <Suspense
                fallback={
                  <div
                    role="status"
                    aria-live="polite"
                    className="h-32 animate-pulse rounded-lg bg-light-gray"
                    data-testid="wizard-diff-table-loading"
                  />
                }
              >
                <DiffTable diffRows={revisionData.diff_rows} />
              </Suspense>

              {/* Revision reason input */}
              <div className="space-y-1">
                <label
                  htmlFor="wizard-revision-reason"
                  className="block text-xs font-medium text-mid-gray"
                >
                  Motivo de la revisión
                  {reasonRequired && (
                    <span className="ml-1 text-red-600" aria-hidden="true">
                      *
                    </span>
                  )}
                </label>
                <textarea
                  id="wizard-revision-reason"
                  data-testid="wizard-revision-reason"
                  rows={2}
                  maxLength={REVISION_REASON_MAX + 10}
                  value={revisionReason}
                  onChange={(e) => setRevisionReason(e.target.value)}
                  onBlur={() => setRevisionReasonTouched(true)}
                  placeholder="Ej: Corrección oficial federación post-reclamo Andrés Mejía"
                  aria-required={reasonRequired}
                  aria-invalid={
                    !reasonValid && revisionReasonTouched ? true : undefined
                  }
                  className="w-full resize-y rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                  style={{
                    boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
                  }}
                />
                <div className="flex items-center justify-between text-[11px]">
                  <span
                    className={cn(
                      "text-mid-gray",
                      reasonOverflow && "text-red-600",
                    )}
                  >
                    {revisionReason.length}/{REVISION_REASON_MAX}
                  </span>
                  {reasonRequired && !reasonValid && revisionReasonTouched && (
                    <span
                      className="text-red-600"
                      role="alert"
                      data-testid="wizard-revision-reason-error"
                    >
                      Requerido cuando la revisión elimina resultados.
                    </span>
                  )}
                </div>
              </div>

              {commitMutation.isError && (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
                  data-testid="wizard-commit-error"
                >
                  {getErrMsg(
                    commitMutation.error,
                    "Error aplicando la revisión.",
                  )}
                </div>
              )}

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  data-testid="wizard-step2-back"
                  className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-mid-gray hover:text-charcoal"
                >
                  <ArrowLeft size={14} aria-hidden="true" />
                  Volver
                </button>
                <button
                  type="button"
                  onClick={submitCommit}
                  disabled={!canCommit || commitMutation.isPending}
                  data-testid="wizard-step2-confirm"
                  className="inline-flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {commitMutation.isPending ? (
                    <Loader2
                      size={14}
                      className="animate-spin"
                      aria-hidden="true"
                    />
                  ) : (
                    <ArrowRight size={14} aria-hidden="true" />
                  )}
                  Confirmar y aplicar revisión
                </button>
              </div>
            </div>
          )}

          {matchesData && (
            <>
              <div
                className="grid grid-cols-2 gap-2 rounded-lg bg-light-gray/40 p-3 text-sm sm:grid-cols-4"
                data-testid="wizard-counts"
              >
                <div>
                  <p className="text-xs text-mid-gray">Confirmados</p>
                  <p className="font-semibold text-charcoal">
                    {matchesData.counts.confirmed}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-mid-gray">Ambiguos</p>
                  <p className="font-semibold text-amber-700">
                    {matchesData.counts.ambiguous}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-mid-gray">Sin match</p>
                  <p className="font-semibold text-mid-gray">
                    {matchesData.counts.no_match}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-mid-gray">Total</p>
                  <p className="font-semibold text-charcoal">
                    {matchesData.counts.total}
                  </p>
                </div>
              </div>

              <label className="flex items-center gap-2 text-xs text-mid-gray">
                <input
                  type="checkbox"
                  checked={onlyPending}
                  onChange={(e) => setOnlyPending(e.target.checked)}
                  data-testid="wizard-toggle-pending"
                />
                Mostrar solo pendientes de resolver
              </label>

              <div
                className="max-h-96 overflow-y-auto rounded-lg ring-1 ring-light-gray"
                data-testid="wizard-matches-table"
              >
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-light-gray/60 text-xs text-mid-gray">
                    <tr>
                      <th className="px-3 py-2 text-left">Competidor</th>
                      <th className="px-3 py-2 text-left">Match TyR</th>
                      <th className="px-3 py-2 text-left">Confianza</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleMatches.length === 0 && (
                      <tr>
                        <td
                          colSpan={3}
                          className="px-3 py-4 text-center text-xs text-mid-gray"
                        >
                          No hay matches pendientes.
                        </td>
                      </tr>
                    )}
                    {visibleMatches.map((m) => {
                      const editable = m.is_ambiguous || !m.tyr_athlete;
                      const value =
                        resolutions[m.competitor_normalized_name] ?? null;
                      return (
                        <tr
                          key={m.competitor_normalized_name}
                          className="border-t border-light-gray"
                          data-testid={`wizard-match-row-${m.competitor_normalized_name}`}
                        >
                          <td className="px-3 py-2 align-top">
                            <p className="text-charcoal">
                              {m.competitor_display_name}
                            </p>
                            {m.is_ambiguous && value == null && (
                              <p className="text-[10px] font-medium text-amber-700">
                                Requiere resolución
                              </p>
                            )}
                          </td>
                          <td className="px-3 py-2 align-top">
                            {editable ? (
                              <AthleteCombobox
                                allowAny
                                anyLabel="Sin match (rival/otro club)"
                                value={value}
                                onChange={(id) =>
                                  setResolutions((prev) => ({
                                    ...prev,
                                    [m.competitor_normalized_name]: id,
                                  }))
                                }
                                data-testid={`wizard-combo-${m.competitor_normalized_name}`}
                              />
                            ) : (
                              <span className="text-charcoal">
                                {m.tyr_athlete?.full_name ?? "—"}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 align-top text-xs text-mid-gray">
                            {(m.confidence * 100).toFixed(0)}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {commitMutation.isError && (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
                  data-testid="wizard-commit-error"
                >
                  {getErrMsg(
                    commitMutation.error,
                    "Error confirmando el commit.",
                  )}
                </div>
              )}

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  data-testid="wizard-step2-back"
                  className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-mid-gray hover:text-charcoal"
                >
                  <ArrowLeft size={14} aria-hidden="true" />
                  Volver
                </button>
                <button
                  type="button"
                  onClick={submitCommit}
                  disabled={!canCommit || commitMutation.isPending}
                  data-testid="wizard-step2-confirm"
                  className="inline-flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {commitMutation.isPending ? (
                    <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                  ) : (
                    <ArrowRight size={14} aria-hidden="true" />
                  )}
                  Confirmar e ingestar
                </button>
              </div>
              {!canCommit && pendingAmbiguous.length > 0 && (
                <p
                  className="text-xs text-amber-700"
                  role="status"
                  data-testid="wizard-pending-hint"
                >
                  Quedan {pendingAmbiguous.length} matches ambiguos por
                  resolver antes de confirmar.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4" data-testid="import-wizard-step3">
          {commitMutation.isError ? (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-800"
              data-testid="wizard-step3-error"
            >
              <div className="mb-2 flex items-start gap-2">
                <AlertCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                <span>
                  {getErrMsg(
                    commitMutation.error,
                    "El commit falló. Reintenta o cancela.",
                  )}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  commitMutation.reset();
                  setStep(2);
                }}
                data-testid="wizard-step3-retry"
                className="inline-flex items-center gap-2 rounded-lg bg-red-700 px-3 py-2 text-xs font-semibold text-white hover:opacity-90"
              >
                <RefreshCw size={12} aria-hidden="true" />
                Reintentar
              </button>
            </div>
          ) : commitMutation.data ? (
            <div
              role="status"
              className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-900"
              data-testid="wizard-step3-success"
            >
              <div className="mb-2 flex items-center gap-2">
                <CheckCircle2 size={18} aria-hidden="true" />
                <span className="font-semibold">
                  {revisionData ? "Revisión aplicada" : "Ingesta completada"}
                </span>
              </div>
              {revisionData ? (
                <p className="text-xs" data-testid="wizard-step3-revision-summary">
                  <strong>{revisionData.diff_summary.n_update}</strong>{" "}
                  actualizaciones,{" "}
                  <strong>{revisionData.diff_summary.n_delete}</strong>{" "}
                  eliminaciones,{" "}
                  <strong>{revisionData.diff_summary.n_create}</strong>{" "}
                  nuevas. Audit completo en historial.
                </p>
              ) : (
                <ul className="ml-5 list-disc space-y-1 text-xs">
                  <li>
                    Resultados insertados:{" "}
                    <strong>{commitMutation.data.n_results_inserted}</strong>
                  </li>
                  <li>
                    Competidores creados:{" "}
                    <strong>
                      {commitMutation.data.n_competitors_created}
                    </strong>
                  </li>
                  <li>
                    Competidores vinculados a TyR:{" "}
                    <strong>{commitMutation.data.n_competitors_linked}</strong>
                  </li>
                </ul>
              )}
              {commitMutation.data.warning_banner && (
                <p
                  className="mt-2 rounded-md bg-orange-100 px-2 py-1 text-[11px] text-orange-900"
                  data-testid="wizard-step3-warning-banner"
                  role="alert"
                >
                  {commitMutation.data.warning_banner}
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <Link
                  to="/coach/race-analysis?tab=runs"
                  className="inline-flex items-center gap-1 rounded-lg bg-charcoal px-3 py-2 text-xs font-semibold text-white hover:opacity-90"
                  data-testid="wizard-step3-link-analysis"
                >
                  Ver análisis de la válida
                </Link>
                <button
                  type="button"
                  onClick={reset}
                  className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal ring-1 ring-light-gray hover:bg-light-gray"
                  data-testid="wizard-step3-new"
                >
                  Cargar otro
                </button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-mid-gray">Procesando…</p>
          )}
        </div>
      )}
    </section>
  );
}
