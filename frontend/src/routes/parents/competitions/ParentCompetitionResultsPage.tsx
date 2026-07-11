/**
 * ParentCompetitionResultsPage — vista de resultados de una competencia para padres.
 *
 * Ruta: /parents/competitions/:raceEventId (allowedRoles: parent)
 *
 * El backend filtra las filas al hijo/a propio del padre autenticado, por lo que
 * esta página nunca expone datos de otros menores. El toggle "Solo mi club" se
 * oculta (hideClubFilter) porque carece de sentido en este contexto.
 *
 * Privacidad (FR-030 / US1 escenario 5):
 *   - `display_name` en las filas proviene del backend ya filtrado.
 *   - Nunca se muestra el nombre de otro menor ni datos de terceros.
 *   - No hay CTA "Importar resultados" (solo coach/admin puede importar).
 */
import { lazy, Suspense, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CalendarDays, MapPin } from "lucide-react";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useRaceResults } from "@/hooks/race/useRaceResults";
import { useRaceStandings } from "@/hooks/race/useRaceStandings";
import { formatDate } from "@/lib/datetime";

// ---------------------------------------------------------------------------
// Lazy chunks — mismas tablas que usa el coach, con hideClubFilter
// ---------------------------------------------------------------------------

const ResultsTable = lazy(() =>
  import(
    "@/components/competitions/results/ResultsTable"
  ).then((m) => ({ default: m.ResultsTable })),
);

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
// Sub-componentes
// ---------------------------------------------------------------------------

function TableSkeleton({ label }: { label: string }) {
  return (
    <div
      className="space-y-2"
      role="status"
      aria-busy="true"
      aria-label={label}
    >
      <Skeleton className="h-9 w-full" />
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

function ErrorState({
  err,
  isFetching,
  onRetry,
  label,
}: {
  err: unknown;
  isFetching: boolean;
  onRetry: () => void;
  label: string;
}) {
  const coldStart = isColdStart(err);
  return (
    <div
      className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4"
      role="alert"
      data-testid="parent-results-error"
    >
      <AlertCircle
        className="mt-0.5 h-5 w-5 shrink-0 text-red-500"
        aria-hidden="true"
      />
      <div className="flex-1 space-y-1">
        <p className="text-sm font-medium text-red-700">
          {coldStart ? "El servidor está iniciando…" : `No se pudo cargar ${label}.`}
        </p>
        <p className="text-xs text-red-600">
          {coldStart
            ? "El servidor está despertando del modo de reposo. Esto puede tardar hasta 50 segundos. Por favor, reintenta en un momento."
            : "Verifica tu conexión y vuelve a intentarlo."}
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        disabled={isFetching}
        className="flex shrink-0 items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-50 shadow-ring"
        data-testid="parent-results-retry"
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

/** Estado vacío neutro para padres — sin CTA de importar (solo coach puede). */
function ParentEmptyState() {
  return (
    <div
      className="flex min-h-[20vh] flex-col items-center justify-center gap-3 rounded-xl bg-white p-8 text-center ring-1 ring-[rgba(34,42,53,0.08)]"
      data-testid="parent-results-empty"
    >
      <p className="text-sm font-semibold text-charcoal">
        Sin resultados publicados
      </p>
      <p className="text-xs text-mid-gray">
        Aún no se han publicado resultados de esta competencia.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tabs — local (evita dependencia de shadcn Tabs para evitar JS extra)
// ---------------------------------------------------------------------------

type TabId = "results" | "standings";

interface TabBarProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

function TabBar({ active, onChange }: TabBarProps) {
  const base =
    "flex-1 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50";
  const activeClass = "border-b-2 border-primary text-charcoal";
  const inactiveClass = "border-b border-[rgba(34,42,53,0.08)] text-mid-gray hover:text-charcoal";

  return (
    <div
      className="flex rounded-t-xl bg-white"
      role="tablist"
      aria-label="Secciones de la competencia"
    >
      <button
        type="button"
        role="tab"
        id="tab-results"
        aria-controls="panel-results"
        aria-selected={active === "results"}
        onClick={() => onChange("results")}
        className={`${base} ${active === "results" ? activeClass : inactiveClass}`}
        data-testid="tab-btn-results"
      >
        Resultados
      </button>
      <button
        type="button"
        role="tab"
        id="tab-standings"
        aria-controls="panel-standings"
        aria-selected={active === "standings"}
        onClick={() => onChange("standings")}
        className={`${base} ${active === "standings" ? activeClass : inactiveClass}`}
        data-testid="tab-btn-standings"
      >
        Clasificación general
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sección de skeleton de cabecera
// ---------------------------------------------------------------------------

function HeaderSkeleton() {
  return (
    <div className="rounded-xl bg-white px-5 py-4 space-y-3 shadow-card">
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-4 w-1/4" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ParentCompetitionResultsPage() {
  const { raceEventId: raceEventIdParam } = useParams<{ raceEventId: string }>();
  const raceEventId = Number(raceEventIdParam);

  const [activeTab, setActiveTab] = useState<TabId>("results");

  const resultsQuery = useRaceResults(raceEventId);
  const standingsQuery = useRaceStandings(raceEventId);

  // Derivar header desde cualquiera de las dos respuestas (mismos campos)
  const headerData = resultsQuery.data ?? standingsQuery.data;
  const eventName = headerData?.event_name;
  const eventDate = headerData?.event_date;
  const eventLocation = headerData?.location;

  const isHeaderLoading = resultsQuery.isLoading && standingsQuery.isLoading;

  // ── Skeleton de carga inicial (ambas queries pendientes) ─────────────────
  if (isHeaderLoading) {
    return (
      <section
        role="status"
        aria-busy="true"
        aria-label="Cargando competencia"
        className="space-y-4"
        data-testid="parent-results-page-loading"
      >
        <Skeleton className="h-4 w-28" />
        <HeaderSkeleton />
        <TableSkeleton label="Cargando resultados" />
      </section>
    );
  }

  return (
    <section className="space-y-5" data-testid="parent-results-page">
      {/* Breadcrumb */}
      <nav aria-label="Ruta de navegación">
        <Link
          to="/parents/calendar"
          className="flex w-fit items-center gap-1 text-sm font-medium text-mid-gray hover:text-charcoal"
          data-testid="breadcrumb-back"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Calendario
        </Link>
      </nav>

      {/* Header del evento */}
      <div
        className="rounded-xl bg-white px-5 py-4 space-y-2 shadow-card"
        data-testid="event-header"
      >
        <h1
          className="font-display text-xl text-charcoal"
          data-testid="event-name"
        >
          {eventName ?? "Competencia"}
        </h1>
        {eventDate && (
          <div className="flex items-center gap-2 text-sm text-mid-gray">
            <CalendarDays size={14} aria-hidden="true" />
            <span className="capitalize">{formatDate(eventDate)}</span>
          </div>
        )}
        {eventLocation && (
          <div className="flex items-center gap-2 text-sm text-mid-gray">
            <MapPin size={14} aria-hidden="true" />
            <span>{eventLocation}</span>
          </div>
        )}
      </div>

      {/* Tabs + paneles */}
      <div className="overflow-hidden rounded-xl shadow-card">
        <TabBar active={activeTab} onChange={setActiveTab} />

        {/* Panel Resultados */}
        <div
          role="tabpanel"
          id="panel-results"
          aria-labelledby="tab-results"
          hidden={activeTab !== "results"}
          className="bg-white px-4 py-4"
        >
          {/* h2 sr-only garantiza la jerarquía h1→h2→h3 (axe heading-order) */}
          <h2 className="sr-only">Resultados de la competencia</h2>
          {activeTab === "results" && (
            <ResultsSection raceEventId={raceEventId} resultsQuery={resultsQuery} />
          )}
        </div>

        {/* Panel Clasificación general */}
        <div
          role="tabpanel"
          id="panel-standings"
          aria-labelledby="tab-standings"
          hidden={activeTab !== "standings"}
          className="bg-white px-4 py-4"
        >
          {/* h2 sr-only garantiza la jerarquía h1→h2→h3 (axe heading-order) */}
          <h2 className="sr-only">Clasificación general de temporada</h2>
          {activeTab === "standings" && (
            <StandingsSection raceEventId={raceEventId} standingsQuery={standingsQuery} />
          )}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// ResultsSection — maneja loading/error/empty/data para la pestaña resultados
// ---------------------------------------------------------------------------

function ResultsSection({
  raceEventId: _raceEventId,
  resultsQuery,
}: {
  raceEventId: number;
  resultsQuery: ReturnType<typeof useRaceResults>;
}) {
  const { data, isLoading, isError, isFetching, error, refetch } = resultsQuery;

  if (isLoading) {
    return <TableSkeleton label="Cargando resultados" />;
  }

  if (isError) {
    return (
      <ErrorState
        err={error}
        isFetching={isFetching}
        onRetry={() => void refetch()}
        label="los resultados"
      />
    );
  }

  const hasData =
    data &&
    data.categories.length > 0 &&
    data.categories.some((c) => c.rows.length > 0);

  if (!hasData) {
    return <ParentEmptyState />;
  }

  return (
    <Suspense fallback={<TableSkeleton label="Cargando tabla de resultados" />}>
      <ResultsTable data={data} hideClubFilter />
    </Suspense>
  );
}

// ---------------------------------------------------------------------------
// StandingsSection — maneja loading/error/empty/data para la pestaña standings
// ---------------------------------------------------------------------------

function StandingsSection({
  raceEventId: _raceEventId,
  standingsQuery,
}: {
  raceEventId: number;
  standingsQuery: ReturnType<typeof useRaceStandings>;
}) {
  const { data, isLoading, isError, isFetching, error, refetch } = standingsQuery;

  if (isLoading) {
    return <TableSkeleton label="Cargando clasificación" />;
  }

  if (isError) {
    return (
      <ErrorState
        err={error}
        isFetching={isFetching}
        onRetry={() => void refetch()}
        label="la clasificación"
      />
    );
  }

  const hasData =
    data &&
    data.categories.length > 0 &&
    data.categories.some((c) => c.rows.length > 0);

  if (!hasData) {
    return <ParentEmptyState />;
  }

  return (
    <Suspense fallback={<TableSkeleton label="Cargando tabla de clasificación" />}>
      <StandingsTable data={data} hideClubFilter />
    </Suspense>
  );
}
