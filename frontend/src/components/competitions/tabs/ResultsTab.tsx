/**
 * ResultsTab — tabla de resultados de la válida (tabla de llegada).
 *
 * Estado de la tabla:
 *   - loading   → skeleton de filas + anuncio sr-only
 *   - error     → banner con detección de cold-start de Render Free (~50 s)
 *   - vacío     → estado diseñado con CTA "Importar resultados"
 *   - con datos → ResultsTable (lazy chunk) con filtros y ordenación
 *
 * Lazy-loading:
 *   ResultsTable se importa con React.lazy para mantener el chunk del tab
 *   dentro del presupuesto de 150 KB gzipped (constitution IV.5).
 *
 * Props:
 *   - `raceEventId: number` — ID del evento.
 *   - `hasResults?: boolean` — hint del padre (si es false, muestra CTA
 *     antes de la llamada; si es undefined, no bloquea la query).
 *   - `onNavigateToInsights?: () => void` — callback para navegar al tab Insights.
 */
import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Loader2, RefreshCw, Upload } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { buttonVariants } from "@/components/ui/button";
import { useRaceResults } from "@/hooks/race/useRaceResults";

// ResultsTable — lazy chunk (tablas pesadas con 26 categorías)
const ResultsTable = lazy(() =>
  import(
    "@/components/competitions/results/ResultsTable"
  ).then((m) => ({ default: m.ResultsTable })),
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isColdStart(err: unknown): boolean {
  // Render Free cold-start: primera petición tarda ~50 s y puede devolver
  // un error de red (ECONNABORTED / ERR_NETWORK) o 503/502.
  if (typeof err === "object" && err !== null) {
    const e = err as { code?: string; response?: { status?: number } };
    if (e.code === "ECONNABORTED" || e.code === "ERR_NETWORK") return true;
    const status = e.response?.status;
    if (status === 502 || status === 503 || status === 504) return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Sub-componentes de estado
// ---------------------------------------------------------------------------

function ResultsTableSkeleton() {
  return (
    <div
      className="space-y-2"
      role="status"
      aria-busy="true"
      aria-label="Cargando resultados"
    >
      {/* Header skeleton */}
      <Skeleton className="h-9 w-full" />
      {/* Rows skeleton */}
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

function EmptyState({ raceEventId }: { raceEventId: number }) {
  return (
    <div
      className="flex min-h-[28vh] flex-col items-center justify-center gap-4 rounded-xl bg-white p-8 text-center ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid="results-tab-empty"
    >
      <Upload size={36} className="text-mid-gray" aria-hidden="true" />
      <div className="space-y-1">
        <p className="text-sm font-semibold text-charcoal">
          Sin resultados importados
        </p>
        <p className="text-xs text-mid-gray">
          Importa el PDF oficial de la Copa Valle para ver los resultados de
          esta válida.
        </p>
      </div>
      <Link
        to={`/competitions/${raceEventId}/import`}
        className={buttonVariants({ variant: "default" })}
        data-testid="results-tab-import-cta"
      >
        Importar resultados
      </Link>
    </div>
  );
}

function ErrorState({
  err,
  isFetching,
  onRetry,
}: {
  err: unknown;
  isFetching: boolean;
  onRetry: () => void;
}) {
  const coldStart = isColdStart(err);

  return (
    <div
      className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4"
      role="alert"
      data-testid="results-tab-error"
    >
      <AlertCircle
        className="mt-0.5 h-5 w-5 shrink-0 text-red-500"
        aria-hidden="true"
      />
      <div className="flex-1 space-y-1">
        <p className="text-sm font-medium text-red-700">
          {coldStart
            ? "El servidor está iniciando…"
            : "No se pudieron cargar los resultados."}
        </p>
        <p className="text-xs text-red-600">
          {coldStart
            ? "El servidor está despertando del modo de reposo. Esto puede tardar hasta 50 segundos. Por favor, reintenta en un momento."
            : "Ocurrió un error al obtener los datos. Verifica tu conexión y vuelve a intentarlo."}
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        disabled={isFetching}
        className="flex shrink-0 items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-50"
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
        data-testid="results-tab-retry"
      >
        {isFetching ? (
          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
        ) : (
          <RefreshCw size={14} aria-hidden="true" />
        )}
        Reintentar
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ResultsTabProps {
  raceEventId: number;
  hasResults?: boolean;
  onNavigateToInsights?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ResultsTab({
  raceEventId,
  hasResults,
  onNavigateToInsights: _onNavigateToInsights,
}: ResultsTabProps) {
  // Si el padre garantiza que no hay resultados, mostramos CTA de inmediato.
  if (hasResults === false) {
    return <EmptyState raceEventId={raceEventId} />;
  }

  return <ResultsTabInner raceEventId={raceEventId} />;
}

// Inner component que hace la query (separado para que el early-return
// de arriba no viole las reglas de hooks).
function ResultsTabInner({ raceEventId }: { raceEventId: number }) {
  const { data, isLoading, isError, isFetching, error, refetch } =
    useRaceResults(raceEventId);

  // ── Cargando ───────────────────────────────────────────────────────────
  if (isLoading) {
    return <ResultsTableSkeleton />;
  }

  // ── Error ──────────────────────────────────────────────────────────────
  if (isError) {
    return (
      <ErrorState
        err={error}
        isFetching={isFetching}
        onRetry={() => void refetch()}
      />
    );
  }

  // ── Sin datos (categorías vacías o respuesta vacía) ────────────────────
  if (
    !data ||
    data.categories.length === 0 ||
    data.categories.every((c) => c.rows.length === 0)
  ) {
    return <EmptyState raceEventId={raceEventId} />;
  }

  // ── Con datos ──────────────────────────────────────────────────────────
  return (
    <Suspense fallback={<ResultsTableSkeleton />}>
      <ResultsTable data={data} />
    </Suspense>
  );
}
