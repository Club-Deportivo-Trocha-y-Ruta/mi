/**
 * StandingsTab — clasificación general de temporada.
 *
 * Estado de la tabla:
 *   - loading   → skeleton de filas
 *   - error     → banner con detección de cold-start de Render Free (~50 s)
 *   - vacío     → estado diseñado (la temporada puede no tener standings todavía)
 *   - con datos → StandingsTable (lazy chunk)
 *
 * Lazy-loading: StandingsTable se importa con React.lazy.
 *
 * Props:
 *   - `raceEventId: number` — ID del evento para determinar la temporada/serie.
 */
import { lazy, Suspense } from "react";
import { AlertCircle, BarChart2, Loader2, RefreshCw } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useRaceStandings } from "@/hooks/race/useRaceStandings";

// StandingsTable — lazy chunk
const StandingsTable = lazy(() =>
  import(
    "@/components/competitions/results/StandingsTable"
  ).then((m) => ({ default: m.StandingsTable })),
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isColdStart(err: unknown): boolean {
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

function StandingsTableSkeleton() {
  return (
    <div
      className="space-y-2"
      role="status"
      aria-busy="true"
      aria-label="Cargando clasificación"
    >
      <Skeleton className="h-9 w-full" />
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div
      className="flex min-h-[28vh] flex-col items-center justify-center gap-4 rounded-xl bg-white p-8 text-center ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid="standings-tab-empty"
    >
      <BarChart2 size={36} className="text-mid-gray" aria-hidden="true" />
      <div className="space-y-1">
        <p className="text-sm font-semibold text-charcoal">
          Sin clasificación disponible
        </p>
        <p className="text-xs text-mid-gray">
          La clasificación general de la temporada estará disponible cuando se
          hayan importado los resultados de al menos una válida.
        </p>
      </div>
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
      data-testid="standings-tab-error"
    >
      <AlertCircle
        className="mt-0.5 h-5 w-5 shrink-0 text-red-500"
        aria-hidden="true"
      />
      <div className="flex-1 space-y-1">
        <p className="text-sm font-medium text-red-700">
          {coldStart
            ? "El servidor está iniciando…"
            : "No se pudo cargar la clasificación."}
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
        data-testid="standings-tab-retry"
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

export interface StandingsTabProps {
  raceEventId: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StandingsTab({ raceEventId }: StandingsTabProps) {
  const { data, isLoading, isError, isFetching, error, refetch } =
    useRaceStandings(raceEventId);

  // ── Cargando ─────────────────────────────────────────────────────────────
  if (isLoading) {
    return <StandingsTableSkeleton />;
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (isError) {
    return (
      <ErrorState
        err={error}
        isFetching={isFetching}
        onRetry={() => void refetch()}
      />
    );
  }

  // ── Sin datos ─────────────────────────────────────────────────────────────
  if (
    !data ||
    data.categories.length === 0 ||
    data.categories.every((c) => c.rows.length === 0)
  ) {
    return <EmptyState />;
  }

  // ── Con datos ─────────────────────────────────────────────────────────────
  return (
    <Suspense fallback={<StandingsTableSkeleton />}>
      <StandingsTable data={data} />
    </Suspense>
  );
}
