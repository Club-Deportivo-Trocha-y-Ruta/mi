/**
 * ImportWizard — revisión y confirmación de una carga de resultados ya
 * preparada (amendment 2026-09-26, `contracts/ui-review-only.md`).
 *
 * La carga se prepara FUERA de la app (skill de resultados / CLI, feature
 * 044 amendment) y aparece en el tablero de «Cargas» (`LoadsSection`). El
 * wizard ya no sube archivos: solo retoma la carga persistida desde
 * `?import=<id>` y ofrece:
 *   Paso "Revisar carga": dry-run (matches TyR o diff de revisión),
 *     resolución de ambiguos, tabla de mapeo de categorías, motivo de
 *     revisión, confirmar o descartar.
 *   Paso "Resultado": resumen del commit + link al análisis + circuito.
 *
 * Privacidad: los nombres mostrados (display_name) son los publicados por
 * la Federación en los PDFs oficiales, ya son información pública.
 *
 * Diseño:
 *   - State local con varios useState por simplicidad, sin Zustand.
 *   - Toda carga vive en el servidor (`race_imports`); el wizard lee
 *     `?import=<id>` y retoma en el paso "Revisar carga" — no hay upload.
 *   - Sin `?import`, la ruta contenedora (`CompetitionImportPage`) ya
 *     redirige al tablero antes de montar este componente.
 *   - Stepper visual = breadcrumbs simples con `aria-current`.
 */
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { launchGroupAnalysis } from "@/api/raceAnalysis";

import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import { CategoryMappingTable } from "@/components/competitions/import/CategoryMappingTable";
import { parseResultFromDetail } from "@/components/competitions/import/resumeFromDetail";
import { DiscardImportDialog } from "@/components/competitions/imports/DiscardImportDialog";
import {
  ResumeLoadingNotice,
  ResumeStatusNotice,
} from "@/components/competitions/imports/ResumeStatusNotice";
import { RaceConditionsCard } from "@/components/race/RaceConditionsCard";
import { Stepper } from "@/components/shared/Stepper";
import {
  useImportCommit,
  useImportDryRun,
  useRaceImport,
} from "@/hooks/ai/useRaceImports";
import { useRevisionReasons } from "@/hooks/race/useRevisionReasons";
import { formatDateTime } from "@/lib/datetime";
import { getIdentityPendingInfo, identityGateMessage } from "@/lib/identityGate";
import type {
  ImportCommitResponse,
  ImportDryRunResponse,
  ImportDryRunRevisionResponse,
  ImportMatchPreview,
  ImportParseResponse,
  ImportResolvedMatch,
} from "@/types/raceImports.types";

// Ruta del tablero — «Volver», «Cargar otro», el aviso de retomar sin éxito
// y un descarte exitoso navegan aquí (amendment 2026-09-26).
const BOARD_PATH = "/competitions/imports?seccion=cargas";

// DiffTable lazy → solo se descarga si el wizard detecta modo revisión.
// Mantiene el chunk de ImportWizard cerca de la baseline F-UP (~18 KB).
const DiffTable = lazy(() =>
  import("@/components/competitions/import/DiffTable").then((m) => ({ default: m.DiffTable })),
);

// CourseTab lazy → panel "Circuito (opcional)" del step final, feature 043.
const CourseTab = lazy(() =>
  import("@/components/race/course/CourseTab").then((m) => ({ default: m.CourseTab })),
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
// Stepper visual — unified shared Stepper (@/components/shared/Stepper,
// contract in specs/028-frontend-design-foundation/contracts/shared-components.md).
// `Stepper.active` is 0-based; the `step` state below is 1-based, so render
// sites pass `step - 1`.
// ---------------------------------------------------------------------------

const STEPS: { label: string }[] = [
  { label: "Revisar carga" },
  { label: "Resultado" },
];

// ---------------------------------------------------------------------------
// Helper para extraer mensaje del error axios
// ---------------------------------------------------------------------------

/** `true` cuando el error es el 409 plano `restage_required` (carga legacy). */
function isRestageRequiredError(err: unknown): boolean {
  if (typeof err !== "object" || err === null) return false;
  const e = err as { response?: { data?: { detail?: unknown }; status?: number } };
  return e.response?.status === 409 && e.response?.data?.detail === "restage_required";
}

function getErrMsg(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null) {
    const e = err as {
      response?: { data?: { detail?: unknown }; status?: number };
      message?: string;
    };
    const detail = e.response?.data?.detail;
    // Feature 044 (US4/US5) — `race_imports.py::commit_import` responde con
    // `detail: {code, message, ...}` para el timeout de recálculo de
    // identidad (`identity_rebuild_timeout`, 503) y otros bloqueos. Ese
    // `message` ya viene en español y es más específico que los status codes
    // genéricos de abajo, así que se prioriza sobre ellos. (El candado de
    // identidad por carga, 409 `identity_pending`, tiene cuerpo plano y lo
    // resuelve `CommitErrorMessage` antes de llegar aquí — feature 045.)
    if (
      detail &&
      typeof detail === "object" &&
      !Array.isArray(detail) &&
      "message" in detail &&
      typeof (detail as { message?: unknown }).message === "string"
    ) {
      return (detail as { message: string }).message;
    }
    // Amendment 2026-09-26 — 409 por código (`contracts/ui-review-only.md`
    // §Copy): `already_committed` tiene copy propio; `restage_required` se
    // resuelve en el render (aviso legacy), nunca aquí.
    if (detail === "already_committed") {
      return "Esta carga ya fue confirmada.";
    }
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
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

/**
 * Banner de error del commit. Casos especiales:
 *
 *  - `409 identity_pending` (feature 045, cuerpo PLANO): esta carga tiene
 *    decisiones de identidad por resolver. Se muestra el copy de
 *    `contracts/ui-copy.md` con el conteo de ESTA carga y un enlace a
 *    `review_path` (que conserva `import=<id>`). La carga NO se pierde: el
 *    servidor la guarda y se retoma desde «Cargas e identidades».
 *  - `identity_rebuild_timeout` (503): el recálculo tardó demasiado antes
 *    del commit. Se usa el mensaje del backend tal cual — ya invita a
 *    reintentar ("Intenta de nuevo en unos minutos.").
 *
 * Cualquier otro error cae en `getErrMsg()` (prioriza `detail.message`,
 * código conocido, luego status codes genéricos).
 */
function CommitErrorMessage({
  error,
  fallback,
}: {
  error: unknown;
  fallback: string;
}) {
  const identity = getIdentityPendingInfo(error);
  if (identity) {
    return (
      <>
        <span data-testid="wizard-identity-gate-message">
          {identityGateMessage(identity.pending)}
        </span>
        <Link
          to={identity.reviewPath}
          className="mt-1 block min-h-11 py-2 font-medium underline underline-offset-2"
          data-testid="wizard-identity-review-link"
        >
          Ir a las decisiones de identidad
        </Link>
      </>
    );
  }
  return <span>{getErrMsg(error, fallback)}</span>;
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

export interface ImportWizardProps {
  /** Callback opcional al completar commit. */
  onCompleted?: (response: ImportCommitResponse) => void;
}

/**
 * Resolución explícita de una fila del paso de revisión.
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
  const [step, setStep] = useState<1 | 2>(1);
  // Feature 028 (T051) — step-focus management contract documented in
  // `@/components/shared/Stepper`: ref + tabIndex={-1} on the step heading +
  // a useEffect keyed on the active step index.
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    stepHeadingRef.current?.focus();
  }, [step]);
  const [parseResult, setParseResult] = useState<ImportParseResponse | null>(
    null,
  );
  // `?import=<id>` — única forma de llegar al wizard (amendment 2026-09-26).
  const [searchParams, setSearchParams] = useSearchParams();
  const resumeImportId = searchParams.get("import");
  const [resumed, setResumed] = useState<{
    filename: string | null;
    status: "pending" | "dry_run";
  } | null>(null);
  const [discardOpen, setDiscardOpen] = useState(false);
  const hydratedIdRef = useRef<string | null>(null);
  // `goToBoard()` navega y desmonta el wizard antes de que haya que volver a
  // consultar nada, así que basta con el parámetro y el parse en memoria.
  const activeResumeId = parseResult || !resumeImportId ? null : resumeImportId;
  const resumeQuery = useRaceImport(activeResumeId);
  const resumeDetail = resumeQuery.data;
  const resumeIsResumable =
    !!resumeDetail &&
    (resumeDetail.status === "pending" || resumeDetail.status === "dry_run") &&
    resumeDetail.parse_meta != null &&
    !resumeDetail.restage_required;
  // Amendment 2026-09-26 — carga legacy (`restage_required`): el detalle
  // existe pero no se puede retomar por este camino. Muestra el aviso legacy
  // (solo *Descartar*), nunca el asistente.
  const isLegacy = !!resumeDetail && resumeDetail.restage_required === true;
  const showResumeLoading =
    activeResumeId != null &&
    (resumeQuery.isPending || (resumeIsResumable && !parseResult));
  const showResumeNotice =
    activeResumeId != null &&
    !showResumeLoading &&
    (resumeQuery.isError || (!!resumeDetail && !resumeIsResumable));
  // Amendment 2026-09-26 — un 409 `restage_required` en dry-run/commit (carga
  // legacy detectada tarde, ej. entre el detalle y el dry-run) también cae al
  // aviso legacy, sin necesidad de recargar el detalle.
  const [legacyFromAction, setLegacyFromAction] = useState(false);

  /** Escribe/borra `?import=<id>` sin apilar historial. */
  function setImportParam(id: string | null) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id) next.set("import", id);
        else next.delete("import");
        return next;
      },
      { replace: true },
    );
  }

  // Hidrata el wizard desde el detalle: `pending` → revisión, `dry_run` →
  // confirmación.
  useEffect(() => {
    if (!resumeDetail || parseResult) return;
    if (!resumeIsResumable) return;
    if (hydratedIdRef.current === String(resumeDetail.id)) return;
    hydratedIdRef.current = String(resumeDetail.id);
    setParseResult(parseResultFromDetail(resumeDetail));
    setResumed({
      filename: resumeDetail.source_filename,
      status: resumeDetail.status === "dry_run" ? "dry_run" : "pending",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeDetail, resumeIsResumable, parseResult]);
  // Resoluciones por competitor_normalized_name. Clave AUSENTE = pendiente.
  // Cualquier `MatchResolution` presente = decisión explícita del coach.
  const [resolutions, setResolutions] = useState<
    Record<string, MatchResolution>
  >({});
  const [onlyPending, setOnlyPending] = useState(false);
  // Feature 044 (US1) — cuántas categorías del acta quedan listas para
  // confirmar (ok/acknowledged y reconocidas) vs. el total, para el copy
  // del botón de confirmar. Lo reporta `CategoryMappingTable`.
  const [categoryReadyCounts, setCategoryReadyCounts] = useState({
    ready: 0,
    total: 0,
  });
  // F-UP-REV5 / PR4: motivo de revisión — code del catálogo CERRADO
  // (sin texto libre, privacidad menores). Obligatorio si hay deletes.
  const [revisionReason, setRevisionReason] = useState("");
  const [revisionReasonTouched, setRevisionReasonTouched] = useState(false);
  const revisionReasonsQuery = useRevisionReasons();

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

  // ---------------- Revisar carga — auto-trigger dry-run al entrar
  useEffect(() => {
    if (step !== 1 || !parseResult) return;
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
        onError: (err) => {
          if (isRestageRequiredError(err)) setLegacyFromAction(true);
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
        setImportParam(null);
        setStep(2);
        onCompleted?.(result);
      } catch (err) {
        if (isRestageRequiredError(err)) setLegacyFromAction(true);
        setStep(2);
      }
      return;
    }

    // Modo matches (F-UP normal). Bug #3: el payload deriva `athlete_id`
    // del objeto `MatchResolution` cuando existe. Si la clave está ausente
    // (no debería llegar aquí por el guard `canCommit`, pero por defensa),
    // se envía `null` — el backend ya acepta `athlete_id=null` como "sin
    // match" persistido como contexto de carrera sin atleta TyR.
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
      setImportParam(null);
      setStep(2);
      onCompleted?.(result);
    } catch (err) {
      if (isRestageRequiredError(err)) setLegacyFromAction(true);
      // El error se muestra en el render (step queda en el paso "Resultado"
      // con commitMutation.isError). La carga NO se pierde: sigue en el
      // servidor y en `?import=<id>`.
      setStep(2);
    }
  };

  /** «Volver», «Cargar otro», el aviso de retomar y un descarte exitoso
   * navegan al tablero — ya no hay un paso 1 al que regresar. */
  function goToBoard() {
    navigate(BOARD_PATH);
  }

  // ---------------- Render
  if (isLegacy || legacyFromAction) {
    return (
      <section
        className="rounded-xl bg-surface-raised p-5 ring-1 ring-light-gray"
        data-testid="import-wizard"
        aria-label="Revisión de carga de resultados"
      >
        <ResumeStatusNotice
          detail={resumeDetail}
          isError={false}
          legacy
          onStartNew={goToBoard}
          onDiscard={() => setDiscardOpen(true)}
        />
        {resumeDetail && (
          <DiscardImportDialog
            open={discardOpen}
            onOpenChange={setDiscardOpen}
            importId={resumeDetail.id}
            filename={resumeDetail.source_filename}
            onDiscarded={goToBoard}
          />
        )}
      </section>
    );
  }

  return (
    <section
      className="rounded-xl bg-surface-raised p-5 ring-1 ring-light-gray"
      data-testid="import-wizard"
      aria-label="Revisión de carga de resultados"
    >
      <div className="mb-4">
        <Stepper steps={STEPS} active={step - 1} />
      </div>
      <h2
        ref={stepHeadingRef}
        tabIndex={-1}
        data-testid="wizard-step-heading"
        className="mb-4 text-base font-semibold text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40 rounded"
      >
        {STEPS[step - 1].label}
      </h2>

      {/* Retomando una carga desde `?import=<id>`. */}
      {step === 1 && showResumeLoading && <ResumeLoadingNotice />}
      {step === 1 && showResumeNotice && (
        <ResumeStatusNotice
          detail={resumeDetail}
          isError={resumeQuery.isError}
          onStartNew={goToBoard}
        />
      )}

      {step === 1 && !showResumeLoading && !showResumeNotice && (
        <div className="space-y-4" data-testid="import-wizard-step2">
          {/* Encabezado de la carga en revisión — de dónde viene el
              manifiesto con que se stageó (skill/CLI). */}
          {parseResult?.header && (
            <div
              className="rounded-lg bg-light-gray/30 px-3 py-2 text-xs text-mid-gray"
              data-testid="wizard-review-header"
            >
              <span className="font-medium text-charcoal">
                {parseResult.header.series_name}
              </span>
              {" · "}Temporada {parseResult.header.season}
              {parseResult.header.valida_num > 0 && (
                <> · Válida {parseResult.header.valida_num}</>
              )}
              {" · "}
              {parseResult.header.event_name}
            </div>
          )}

          {resumed && (
            <div
              role="status"
              className="rounded-lg bg-light-gray/40 px-3 py-2 text-sm text-charcoal"
              data-testid="wizard-resumed-notice"
            >
              Retomaste tu carga
              {resumed.filename ? ` «${resumed.filename}»` : ""}. El archivo
              sigue guardado.{" "}
              {resumed.status === "dry_run"
                ? "Ya se validó: confirma para cargarla."
                : "Revisa las coincidencias y confirma."}
            </div>
          )}

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

          {dryRunMutation.isError && !isRestageRequiredError(dryRunMutation.error) && (
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

          {/* Feature 044 (US1/US2) — integridad de lectura: completitud por
              categoría, mapeo (exacta/renombrada/propia de temporada/sin
              reconocer) y aviso de filas ilegibles. Se muestra tanto en modo
              revisión como en modo matches — el parseo ya trae `categories`
              en cualquiera de los dos casos. */}
          {parseResult && parseResult.categories && parseResult.categories.length > 0 && (
            <CategoryMappingTable
              parseId={parseResult.parse_id}
              categories={parseResult.categories}
              unreadableRows={parseResult.unreadable_rows ?? []}
              onReadyCountChange={(ready, total) =>
                setCategoryReadyCounts({ ready, total })
              }
            />
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
                  className="w-full rounded-lg bg-surface-raised px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500/40 shadow-ring"
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

              {commitMutation.isError && !isRestageRequiredError(commitMutation.error) && (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
                  data-testid="wizard-commit-error"
                >
                  <CommitErrorMessage
                    error={commitMutation.error}
                    fallback="Error aplicando la revisión."
                  />
                </div>
              )}

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={goToBoard}
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
                  className="inline-flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90 disabled:opacity-50"
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
                  className="inline-flex items-center gap-1 rounded-lg border border-light-gray bg-surface-raised px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-90 disabled:opacity-50"
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

              {commitMutation.isError && !isRestageRequiredError(commitMutation.error) && (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
                  data-testid="wizard-commit-error"
                >
                  <CommitErrorMessage
                    error={commitMutation.error}
                    fallback="Error confirmando el commit."
                  />
                </div>
              )}

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={goToBoard}
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
                  className="inline-flex items-center gap-2 rounded-lg bg-charcoal px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {commitMutation.isPending ? (
                    <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                  ) : (
                    <ArrowRight size={14} aria-hidden="true" />
                  )}
                  <span data-testid="wizard-step2-confirm-label">
                    {categoryReadyCounts.total > 0
                      ? `Confirmar categorías completas (${categoryReadyCounts.ready} de ${categoryReadyCounts.total})`
                      : "Confirmar carga"}
                  </span>
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

          {/* Salida explícita: la carga vive en el servidor, así que
              descartarla pide confirmación. */}
          {parseResult && (
            <div className="border-t border-light-gray pt-3">
              <button
                type="button"
                onClick={() => setDiscardOpen(true)}
                data-testid="wizard-discard"
                className="inline-flex min-h-12 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-red-700 hover:bg-red-50"
              >
                <Trash2 size={14} aria-hidden="true" />
                Descartar esta carga
              </button>
            </div>
          )}
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4" data-testid="import-wizard-step3">
          {commitMutation.isError ? (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-800"
              data-testid="wizard-step3-error"
            >
              <div className="mb-2 flex items-start gap-2">
                <AlertCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
                <div>
                  <CommitErrorMessage
                    error={commitMutation.error}
                    fallback="El commit falló. Reintenta o cancela."
                  />
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  commitMutation.reset();
                  setStep(1);
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
                  {revisionData ? "Revisión aplicada" : "Carga confirmada"}
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
                  className="inline-flex items-center gap-1 rounded-lg bg-charcoal px-3 py-2 text-xs font-semibold text-surface hover:opacity-90"
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
                  onClick={goToBoard}
                  className="inline-flex items-center gap-1 rounded-lg bg-surface-raised px-3 py-2 text-xs font-medium text-charcoal ring-1 ring-light-gray hover:bg-light-gray"
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

          {/* Circuito (opcional) tras commit exitoso — feature 043 */}
          {commitMutation.data && !commitMutation.isError && (
            <div className="mt-4 space-y-2">
              <h3 className="text-sm font-semibold text-charcoal">
                Circuito (opcional)
              </h3>
              <Suspense
                fallback={
                  <div
                    role="status"
                    aria-live="polite"
                    className="h-24 animate-pulse rounded-lg bg-light-gray"
                    data-testid="wizard-course-tab-loading"
                  />
                }
              >
                <CourseTab
                  raceEventId={commitMutation.data.race_event_id}
                  compact
                />
              </Suspense>
            </div>
          )}
        </div>
      )}

      {parseResult && step === 1 && (
        <DiscardImportDialog
          open={discardOpen}
          onOpenChange={setDiscardOpen}
          importId={parseResult.parse_id}
          filename={resumed?.filename ?? null}
          onDiscarded={goToBoard}
        />
      )}
    </section>
  );
}
