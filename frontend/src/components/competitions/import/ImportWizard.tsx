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
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { launchGroupAnalysis } from "@/api/raceAnalysis";
import { z } from "zod";

import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import { RaceUploadZone } from "@/components/competitions/import/RaceUploadZone";
import { RaceConditionsCard } from "@/components/race/RaceConditionsCard";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  useImportCommit,
  useImportDryRun,
  useImportParse,
} from "@/hooks/ai/useRaceImports";
import { useRevisionReasons } from "@/hooks/race/useRevisionReasons";
import { formatDateTime } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import type {
  ImportCommitResponse,
  ImportDryRunResponse,
  ImportDryRunRevisionResponse,
  ImportMatchPreview,
  ImportParseResponse,
  ImportResolvedMatch,
} from "@/types/raceImports.types";
import {
  SURFACE_CONDITIONS,
  SURFACE_CONDITION_LABELS,
  VENUE_ALTITUDES,
} from "@/types/raceEvents.types";
import type { SurfaceCondition } from "@/types/raceEvents.types";

// DiffTable lazy → solo se descarga si el wizard detecta modo revisión.
// Mantiene el chunk de ImportWizard cerca de la baseline F-UP (~18 KB).
const DiffTable = lazy(() =>
  import("@/components/competitions/import/DiffTable").then((m) => ({ default: m.DiffTable })),
);

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
  return formatDateTime(iso) || "—";
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
  // F-COND — condiciones opcionales (NO bloquean avance)
  temperature_c: z
    .string()
    .optional()
    .refine(
      (v) => {
        if (!v || v.trim() === "") return true;
        const n = parseFloat(v);
        return !isNaN(n) && n >= 0 && n <= 50;
      },
      { message: "Debe estar entre 0 y 50 °C" },
    ),
  surface_condition: z
    .enum(["seca", "humeda", "barro", "lluvia", "mixta"] as const)
    .optional()
    .nullable(),
  altitude_msnm: z
    .string()
    .optional()
    .refine(
      (v) => {
        if (!v || v.trim() === "") return true;
        const n = parseFloat(v);
        return !isNaN(n) && n >= 0 && n <= 5000;
      },
      { message: "Debe estar entre 0 y 5000 msnm" },
    ),
  climate: z
    .string()
    .max(60, "Máximo 60 caracteres")
    .optional(),
  weather_notes: z
    .string()
    .max(2000, "Máximo 2000 caracteres")
    .optional(),
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
// T019 — error messages for launchGroupAnalysis (FR-004 feature 010)
// ---------------------------------------------------------------------------

/**
 * Maps HTTP error codes from POST /race-events/{id}/runs to es-CO copy.
 *
 *   503 → presupuesto mensual agotado
 *   429 → límite de concurrencia
 *   422 → sin resultados importados
 *   other → genérico
 */
function getLaunchGroupErrMsg(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const e = err as { response?: { status?: number } };
    switch (e.response?.status) {
      case 503:
        return "Presupuesto mensual de IA agotado. Los análisis se reactivan el próximo ciclo.";
      case 429:
        return "Límite de análisis simultáneos alcanzado. Intenta de nuevo en unos minutos.";
      case 422:
        return "La competencia no tiene resultados importados.";
    }
  }
  return "No se pudo lanzar el análisis. Intenta de nuevo.";
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface ImportWizardProps {
  /** Callback opcional al completar commit. */
  onCompleted?: (response: ImportCommitResponse) => void;
}

/**
 * Resolución explícita de una fila del paso 2.
 *
 * Bug #3: el state previo era `Record<string, number | null>`, donde `null`
 * cubría DOS estados distintos:
 *  - "El coach todavía no toca esta fila."
 *  - "El coach marcó deliberadamente 'Sin match (rival/otro club)'."
 *
 * Resultado: el botón "Confirmar e ingestar" se quedaba bloqueado para
 * siempre cuando el coach resolvía un ambiguo como "sin match" — porque
 * el filtro `pendingAmbiguous` usaba `resolutions[norm] == null` para
 * detectar pendientes, y la elección "sin match" también evaluaba a
 * `null`.
 *
 * Solución: estado discriminado. La clave AUSENTE (`undefined`) es la
 * única señal de "pendiente"; cualquier objeto es decisión tomada.
 */
type MatchResolution =
  | { decision: "match"; athleteId: number }
  | { decision: "no_match"; athleteId: null };

export function ImportWizard({ onCompleted }: ImportWizardProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [parseResult, setParseResult] = useState<ImportParseResponse | null>(
    null,
  );
  const [resultadosPdf, setResultadosPdf] = useState<File | null>(null);
  const [generalPdf, setGeneralPdf] = useState<File | null>(null);
  // Resoluciones por competitor_normalized_name. Clave AUSENTE = pendiente.
  // Cualquier `MatchResolution` presente = decisión explícita del coach.
  const [resolutions, setResolutions] = useState<
    Record<string, MatchResolution>
  >({});
  const [onlyPending, setOnlyPending] = useState(false);
  const [step1Error, setStep1Error] = useState<string | null>(null);
  // F-COND: toast neutral cuando el coach avanza sin llenar condiciones.
  const [conditionsToast, setConditionsToast] = useState(false);
  // F-UP-REV5 / PR4: motivo de revisión — code del catálogo CERRADO
  // (sin texto libre, privacidad menores). Obligatorio si hay deletes.
  const [revisionReason, setRevisionReason] = useState("");
  const [revisionReasonTouched, setRevisionReasonTouched] = useState(false);
  const revisionReasonsQuery = useRevisionReasons();

  const parseMutation = useImportParse();
  const dryRunMutation = useImportDryRun();
  const commitMutation = useImportCommit();

  // T019 — lanzar análisis grupal de IA post-commit (FR-004 feature 010).
  const launchGroupMutation = useMutation({
    mutationFn: (raceEventId: number) =>
      launchGroupAnalysis(raceEventId, {}),
    onSuccess: (_data, raceEventId) => {
      navigate(`/competitions/${raceEventId}?tab=insights`);
    },
  });

  // ---------------- Step 1 form
  const {
    register,
    handleSubmit,
    control,
    setValue,
    watch,
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
      // F-COND — condiciones opcionales
      temperature_c: "",
      surface_condition: null,
      altitude_msnm: "",
      climate: "",
      weather_notes: "",
    },
  });

  // F-COND: Auto-rellena altitud cuando location coincide con catálogo Copa Valle.
  // Solo si altitude_msnm está vacío (shouldDirty: false para no marcar dirty).
  const watchedLocation = watch("location");
  const watchedAltitude = watch("altitude_msnm");
  useEffect(() => {
    if (!watchedLocation) return;
    const matched = VENUE_ALTITUDES[watchedLocation];
    if (matched != null && (!watchedAltitude || watchedAltitude.trim() === "")) {
      setValue("altitude_msnm", String(matched), { shouldDirty: false });
    }
  }, [watchedLocation, watchedAltitude, setValue]);

  const submitStep1 = async (values: Step1Values) => {
    if (!resultadosPdf) {
      setStep1Error("Debes adjuntar el archivo de resultados.");
      return;
    }
    setStep1Error(null);

    // F-COND: detecta si el coach avanzó sin llenar ninguna condición.
    const hasAnyCondition =
      (values.temperature_c && values.temperature_c.trim() !== "") ||
      values.surface_condition != null ||
      (values.altitude_msnm && values.altitude_msnm.trim() !== "") ||
      (values.climate && values.climate.trim() !== "") ||
      (values.weather_notes && values.weather_notes.trim() !== "");
    if (!hasAnyCondition) {
      setConditionsToast(true);
      // Auto-ocultar el toast tras 5 s
      setTimeout(() => setConditionsToast(false), 5000);
    } else {
      setConditionsToast(false);
    }

    // Normalizar campos de condiciones: string vacío → null
    const tempC = values.temperature_c && values.temperature_c.trim() !== ""
      ? values.temperature_c
      : null;
    const altMsnm = values.altitude_msnm && values.altitude_msnm.trim() !== ""
      ? parseFloat(values.altitude_msnm)
      : null;
    const climateVal = values.climate && values.climate.trim() !== ""
      ? values.climate.trim()
      : null;
    const weatherNotes = values.weather_notes && values.weather_notes.trim() !== ""
      ? values.weather_notes.trim()
      : null;

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
          // F-COND — condiciones opcionales
          climate: climateVal,
          temperature_c: tempC,
          surface_condition: values.surface_condition ?? null,
          altitude_msnm: isNaN(altMsnm as number) ? null : altMsnm,
          weather_notes: weatherNotes,
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
          // Pre-poblar resoluciones SOLO para matches con candidato TyR
          // confirmado (no ambiguo). Los ambiguos quedan AUSENTES del map
          // para que `pendingAmbiguous` los detecte como tal hasta que el
          // coach actúe explícitamente (Bug #3).
          const initial: Record<string, MatchResolution> = {};
          for (const m of data.matches) {
            if (!m.is_ambiguous && m.tyr_athlete) {
              initial[m.competitor_normalized_name] = {
                decision: "match",
                athleteId: m.tyr_athlete.id,
              };
            }
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

  // Bug #3: "pendiente" = clave AUSENTE en `resolutions`. Antes usábamos
  // `== null` y eso atrapaba como pendiente al coach que marcaba "sin
  // match" explícito (porque la elección "sin match" también es `null`
  // como athlete_id). Ahora el check es `!(norm in resolutions)`.
  const pendingAmbiguous = useMemo(() => {
    if (!matchesData) return [];
    return matchesData.matches.filter(
      (m) =>
        m.is_ambiguous && !(m.competitor_normalized_name in resolutions),
    );
  }, [matchesData, resolutions]);

  const visibleMatches = useMemo<ImportMatchPreview[]>(() => {
    if (!matchesData) return [];
    if (!onlyPending) return matchesData.matches;
    return matchesData.matches.filter(
      (m) =>
        m.is_ambiguous && !(m.competitor_normalized_name in resolutions),
    );
  }, [matchesData, onlyPending, resolutions]);

  // F-UP-REV5 / PR4 — validación del code de revisión (catálogo cerrado).
  // Obligatorio si hay deletes. Sin overflow (ya no es texto libre).
  const reasonTrimmed = revisionReason.trim();
  const reasonRequired =
    revisionData != null && revisionData.diff_summary.n_delete > 0;
  const reasonValid = !reasonRequired || reasonTrimmed.length > 0;
  const reasonOverflow = false;

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

    // Modo matches (F-UP normal). Bug #3: el payload deriva `athlete_id`
    // del objeto `MatchResolution` cuando existe. Si la clave está ausente
    // (no debería llegar aquí por el guard `canCommit`, pero por defensa),
    // se envía `null` — el backend ya acepta `athlete_id=null` como "sin
    // match" persistido como contexto de carrera sin atleta TyR (ver
    // `backend/app/routers/race_imports.py::commit_import`, línea ~766).
    if (!matchesData) return;
    const resolved_matches: ImportResolvedMatch[] = matchesData.matches.map(
      (m) => {
        const r = resolutions[m.competitor_normalized_name];
        return {
          competitor_normalized_name: m.competitor_normalized_name,
          athlete_id: r ? r.athleteId : null,
        };
      },
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
    setConditionsToast(false);
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
          noValidate
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

          {/* ── F-COND: Sección Condiciones de carrera (opcional) ── */}
          <div className="rounded-lg border border-[rgba(34,42,53,0.08)] p-4">
            <div className="mb-3 flex items-center gap-2">
              <h3 className="text-sm font-semibold text-charcoal">
                Condiciones de carrera
              </h3>
              <span className="rounded-full bg-light-gray px-2 py-0.5 text-[11px] font-medium text-mid-gray">
                Opcional
              </span>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {/* Fila 1 — Temperatura */}
              <div className="space-y-1">
                <label
                  htmlFor="wizard-temperature"
                  className="block text-xs font-medium text-mid-gray"
                >
                  Temperatura
                </label>
                <div className="relative">
                  <input
                    id="wizard-temperature"
                    type="number"
                    inputMode="numeric"
                    min={0}
                    max={50}
                    step={0.1}
                    {...register("temperature_c")}
                    className="w-full rounded-lg bg-white py-2.5 pl-3 pr-10 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                    aria-invalid={errors.temperature_c ? true : undefined}
                    data-testid="wizard-temperature"
                  />
                  <span
                    className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-mid-gray"
                    aria-hidden="true"
                  >
                    °C
                  </span>
                </div>
                {errors.temperature_c && (
                  <p className="text-xs text-red-600" role="alert">
                    {errors.temperature_c.message}
                  </p>
                )}
              </div>

              {/* Fila 1 — Superficie (ToggleGroup chips) */}
              <div className="space-y-1">
                <span className="block text-xs font-medium text-mid-gray">
                  Condición del terreno
                </span>
                <Controller
                  name="surface_condition"
                  control={control}
                  render={({ field }) => (
                    <ToggleGroup
                      type="single"
                      value={field.value ?? ""}
                      onValueChange={(v) =>
                        field.onChange(
                          v === "" ? null : (v as SurfaceCondition),
                        )
                      }
                      className="flex flex-wrap gap-1.5"
                      aria-label="Condición del terreno"
                      data-testid="wizard-surface-condition"
                    >
                      {SURFACE_CONDITIONS.map((sc) => (
                        <ToggleGroupItem
                          key={sc}
                          value={sc}
                          aria-label={SURFACE_CONDITION_LABELS[sc]}
                          className="min-h-[48px] rounded-lg border border-[rgba(34,42,53,0.12)] px-3 py-1.5 text-xs font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-white"
                          data-testid={`wizard-surface-chip-${sc}`}
                        >
                          {SURFACE_CONDITION_LABELS[sc]}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                  )}
                />
              </div>

              {/* Fila 2 — Altitud */}
              <div className="space-y-1">
                <label
                  htmlFor="wizard-altitude"
                  className="block text-xs font-medium text-mid-gray"
                >
                  Altitud
                </label>
                <div className="relative">
                  <input
                    id="wizard-altitude"
                    type="number"
                    inputMode="numeric"
                    min={0}
                    max={5000}
                    step={1}
                    {...register("altitude_msnm")}
                    className="w-full rounded-lg bg-white py-2.5 pl-3 pr-14 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                    aria-invalid={errors.altitude_msnm ? true : undefined}
                    data-testid="wizard-altitude"
                  />
                  <span
                    className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-mid-gray"
                    aria-hidden="true"
                  >
                    msnm
                  </span>
                </div>
                {errors.altitude_msnm && (
                  <p className="text-xs text-red-600" role="alert">
                    {errors.altitude_msnm.message}
                  </p>
                )}
              </div>

              {/* Fila 2 — Clima (input text + datalist) */}
              <div className="space-y-1">
                <label
                  htmlFor="wizard-climate"
                  className="block text-xs font-medium text-mid-gray"
                >
                  Clima
                </label>
                <input
                  id="wizard-climate"
                  type="text"
                  list="wizard-climate-suggestions"
                  placeholder="ej: soleado, parcialmente nublado"
                  maxLength={60}
                  {...register("climate")}
                  className="w-full rounded-lg bg-white px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                  style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                  aria-invalid={errors.climate ? true : undefined}
                  data-testid="wizard-climate"
                />
                <datalist id="wizard-climate-suggestions">
                  <option value="Soleado" />
                  <option value="Parcialmente nublado" />
                  <option value="Nublado" />
                  <option value="Llovizna" />
                  <option value="Lluvioso" />
                  <option value="Ventoso" />
                  <option value="Soleado con viento" />
                </datalist>
                {errors.climate && (
                  <p className="text-xs text-red-600" role="alert">
                    {errors.climate.message}
                  </p>
                )}
              </div>

              {/* Fila 3 — Notas de clima (full-width) */}
              <div className="space-y-1 md:col-span-2">
                <label
                  htmlFor="wizard-weather-notes"
                  className="block text-xs font-medium text-mid-gray"
                >
                  Notas de condiciones
                </label>
                <textarea
                  id="wizard-weather-notes"
                  maxLength={2000}
                  placeholder="Condiciones generales del trazado y clima — evite incluir nombres de atletas o información médica"
                  {...register("weather_notes")}
                  className="w-full resize-y rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                  style={{
                    boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
                    minHeight: "80px",
                  }}
                  aria-invalid={errors.weather_notes ? true : undefined}
                  data-testid="wizard-weather-notes"
                />
                {errors.weather_notes && (
                  <p className="text-xs text-red-600" role="alert">
                    {errors.weather_notes.message}
                  </p>
                )}
              </div>
            </div>
          </div>
          {/* ── Fin F-COND ── */}

          {/* Toast neutral si avanza sin condiciones */}
          {conditionsToast && (
            <div
              role="status"
              aria-live="polite"
              className="rounded-lg bg-light-gray px-3 py-2 text-xs text-mid-gray"
              data-testid="wizard-conditions-toast"
            >
              Condiciones sin registrar — podrás agregarlas después desde el evento.
            </div>
          )}

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

              {/* Revision reason — catálogo CERRADO (PR4, sin texto libre) */}
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
                <select
                  id="wizard-revision-reason"
                  data-testid="wizard-revision-reason"
                  value={revisionReason}
                  onChange={(e) => setRevisionReason(e.target.value)}
                  onBlur={() => setRevisionReasonTouched(true)}
                  aria-required={reasonRequired}
                  aria-invalid={
                    !reasonValid && revisionReasonTouched ? true : undefined
                  }
                  className="w-full rounded-lg bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40"
                  style={{
                    boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
                  }}
                >
                  <option value="">Selecciona un motivo…</option>
                  {(revisionReasonsQuery.data?.options ?? []).map((opt) => (
                    <option key={opt.code} value={opt.code}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                {reasonRequired && !reasonValid && revisionReasonTouched && (
                  <span
                    className="block text-[11px] text-red-600"
                    role="alert"
                    data-testid="wizard-revision-reason-error"
                  >
                    Requerido cuando la revisión elimina resultados.
                  </span>
                )}
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

              <div className="flex flex-wrap items-center justify-between gap-2">
                <label className="flex items-center gap-2 text-xs text-mid-gray">
                  <input
                    type="checkbox"
                    checked={onlyPending}
                    onChange={(e) => setOnlyPending(e.target.checked)}
                    data-testid="wizard-toggle-pending"
                  />
                  Mostrar solo pendientes de resolver
                </label>
                {/* Bug #3: acción bulk para marcar el resto como "sin match".
                    Útil cuando el coach revisó visualmente y descarta a los
                    pendientes — evita que tenga que abrir 9+ comboboxes
                    para confirmar lo evidente. */}
                <button
                  type="button"
                  onClick={() => {
                    if (!matchesData) return;
                    setResolutions((prev) => {
                      const next = { ...prev };
                      for (const m of matchesData.matches) {
                        if (
                          m.is_ambiguous &&
                          !(m.competitor_normalized_name in next)
                        ) {
                          next[m.competitor_normalized_name] = {
                            decision: "no_match",
                            athleteId: null,
                          };
                        }
                      }
                      return next;
                    });
                  }}
                  disabled={pendingAmbiguous.length === 0}
                  data-testid="wizard-mark-rest-no-match"
                  className="inline-flex items-center gap-1 rounded-lg border border-light-gray bg-white px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  Marcar restantes como sin match
                </button>
              </div>

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
                      const resolution =
                        resolutions[m.competitor_normalized_name];
                      const isPending =
                        m.is_ambiguous && resolution === undefined;
                      // Combobox value: athleteId si hay decision="match",
                      // null si decision="no_match", null si no hay resolution
                      // (ambiguo sin tocar). El combobox usa null tanto para
                      // "Sin match" seleccionado como para "vacío", pero el
                      // STATE del wizard distingue ambos vía `resolution`.
                      const comboValue =
                        resolution?.decision === "match"
                          ? resolution.athleteId
                          : null;
                      return (
                        <tr
                          key={m.competitor_normalized_name}
                          className="border-t border-light-gray"
                          data-testid={`wizard-match-row-${m.competitor_normalized_name}`}
                        >
                          <td className="px-3 py-2 align-top">
                            <p className="text-charcoal">
                              {m.competitor_name}
                            </p>
                            {isPending && (
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
                                value={comboValue}
                                onChange={(id) =>
                                  setResolutions((prev) => ({
                                    ...prev,
                                    [m.competitor_normalized_name]:
                                      id == null
                                        ? { decision: "no_match", athleteId: null }
                                        : { decision: "match", athleteId: id },
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
                  to={`/competitions/${commitMutation.data.race_event_id}?tab=results`}
                  className="inline-flex items-center gap-1 rounded-lg bg-charcoal px-3 py-2 text-xs font-semibold text-white hover:opacity-90"
                  data-testid="wizard-step3-link-analysis"
                >
                  Ver resultados de la válida
                </Link>
                <button
                  type="button"
                  disabled={launchGroupMutation.isPending}
                  onClick={() =>
                    launchGroupMutation.mutate(
                      commitMutation.data.race_event_id,
                    )
                  }
                  className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                  data-testid="wizard-step3-launch-ai"
                >
                  {launchGroupMutation.isPending ? (
                    <>
                      <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                      Lanzando análisis…
                    </>
                  ) : (
                    <>
                      <Sparkles size={12} aria-hidden="true" />
                      Analizar con IA ahora
                    </>
                  )}
                </button>
                <button
                  type="button"
                  onClick={reset}
                  className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal ring-1 ring-light-gray hover:bg-light-gray"
                  data-testid="wizard-step3-new"
                >
                  Cargar otro
                </button>
              </div>
              {launchGroupMutation.isError && (
                <p
                  className="mt-2 text-xs text-red-700"
                  role="alert"
                  data-testid="wizard-step3-ai-error"
                >
                  {getLaunchGroupErrMsg(launchGroupMutation.error)}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-mid-gray">Procesando…</p>
          )}

          {/* F4 — Tarjeta condiciones tras commit exitoso */}
          {commitMutation.data && !commitMutation.isError && (
            <RaceConditionsCard
              raceEventId={commitMutation.data.race_event_id}
              conditions={parseResult?.conditions}
            />
          )}
        </div>
      )}
    </section>
  );
}
