/**
 * ActivityReviewPage — vista de revisión de actividades Strava para el
 * coach/admin (feature 025, T031, FR-010).
 *
 * Lista las actividades sincronizadas agrupadas por fecha, con filtros de
 * estado de enlace, atleta y rango de fechas, para que el coach procese
 * rápidamente la semana (SC-005: ~30-60 actividades en <10 min).
 *
 * El enlace/desenlace (`LinkSessionDialog`, `useLinkActivity`) se habilita
 * pasando `canLink` a `ActivityCard`, que renderiza su propio botón +
 * diálogo — esta ruta ya está gateada a coach/admin (`App.tsx`), y
 * `ActivityCard` vuelve a verificar el rol internamente.
 *
 * Privacidad (Ley 1581): reutiliza `ActivityCard`, que nunca renderiza
 * coordenadas, mapas ni ubicación — ver su docstring.
 */
import { useMemo, useState } from "react";
import { AlertCircle, Filter, X } from "lucide-react";

import { ActivityCard } from "@/components/activities/ActivityCard";
import { SiblingViewTabs } from "@/components/layout/SiblingViewTabs";
import { useActivityReview } from "@/hooks/activities/useActivityReview";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import type { ActivityLinkedFilter, ActivityOut } from "@/types/strava.types";

// ---------------------------------------------------------------------------
// Vistas hermanas (Calendario | Sesiones | Actividades) — feature 030, T020
// ---------------------------------------------------------------------------

const SIBLING_VIEWS = [
  { label: "Calendario", to: "/calendar" },
  { label: "Sesiones", to: "/training/sessions" },
  { label: "Actividades", to: "/activities" },
];

// ---------------------------------------------------------------------------
// Design tokens (mirror de CompetitionsListPage / SessionsListPage)
// ---------------------------------------------------------------------------

const inputSelectClass =
  "min-h-[40px] rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";

const DEFAULT_PAGE_SIZE = 30;
const PAGE_SIZE_STEP = 30;
const MAX_PAGE_SIZE = 100;

// ---------------------------------------------------------------------------
// Agrupamiento por fecha
// ---------------------------------------------------------------------------

/**
 * `start_date_local` llega como datetime naive que YA representa la hora
 * local de la actividad (convención de Strava) — igual que en `ActivityCard`,
 * NO se debe convertir de zona horaria acá. Se extraen los componentes tal
 * cual vienen.
 */
function dateKeyOf(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match ? match[0] : value;
}

function formatGroupHeading(dateKey: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateKey);
  if (!match) return dateKey;
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  const label = new Intl.DateTimeFormat("es-CO", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(date);
  return label.charAt(0).toUpperCase() + label.slice(1);
}

interface DateGroup {
  dateKey: string;
  activities: ActivityOut[];
}

/**
 * Agrupa por día preservando el orden de llegada del backend dentro de cada
 * grupo (con `linked=all` eso deja las actividades sin enlazar primero
 * dentro de un mismo día — coherente con el flujo de revisión) y luego
 * ordena los grupos por fecha descendente para que la sección quede
 * cronológica de arriba hacia abajo.
 */
function groupByDate(activities: ActivityOut[]): DateGroup[] {
  const buckets = new Map<string, ActivityOut[]>();
  for (const activity of activities) {
    const key = dateKeyOf(activity.start_date_local);
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.push(activity);
    } else {
      buckets.set(key, [activity]);
    }
  }
  return Array.from(buckets.entries())
    .map(([dateKey, items]) => ({ dateKey, activities: items }))
    .sort((a, b) => (a.dateKey < b.dateKey ? 1 : a.dateKey > b.dateKey ? -1 : 0));
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function ActivityReviewPage() {
  const [linkedFilter, setLinkedFilter] = useState<ActivityLinkedFilter>("all");
  const [athleteId, setAthleteId] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const athletesQuery = useAthletes();
  const athletes = athletesQuery.data?.items ?? [];

  const reviewQuery = useActivityReview({
    linked: linkedFilter,
    athlete_id: athleteId ? Number(athleteId) : undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page: 1,
    page_size: pageSize,
  });

  const items = reviewQuery.data?.items ?? [];
  const total = reviewQuery.data?.total ?? 0;
  const hasMore = items.length < total;

  const groups = useMemo(() => groupByDate(items), [items]);

  const hasActiveFilters =
    linkedFilter !== "all" || athleteId !== "" || dateFrom !== "" || dateTo !== "";

  function resetFilters() {
    setLinkedFilter("all");
    setAthleteId("");
    setDateFrom("");
    setDateTo("");
    setPageSize(DEFAULT_PAGE_SIZE);
  }

  function handleFilterChange<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setPageSize(DEFAULT_PAGE_SIZE);
    };
  }

  return (
    <section className="space-y-5">
      {/* Header */}
      <div>
        <h1
          className="font-display text-2xl text-charcoal"
        >
          Revisión de actividades
        </h1>
        <p className="mt-0.5 text-sm text-mid-gray">
          Actividades sincronizadas desde Strava, agrupadas por día. Enlázalas a
          una sesión de entrenamiento o déjalas sin enlazar.
        </p>
      </div>

      <SiblingViewTabs items={SIBLING_VIEWS} />

      {/* Filtros */}
      <div className="rounded-xl bg-white p-4 shadow-card">
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-end sm:gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="filter-linked" className="text-xs font-medium text-mid-gray">
              Estado
            </label>
            <select
              id="filter-linked"
              value={linkedFilter}
              onChange={(e) =>
                handleFilterChange(setLinkedFilter)(e.target.value as ActivityLinkedFilter)
              }
              className={inputSelectClass}
            >
              <option value="all">Todas</option>
              <option value="false">Sin enlazar</option>
              <option value="true">Enlazadas</option>
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="filter-athlete" className="text-xs font-medium text-mid-gray">
              Atleta
            </label>
            <select
              id="filter-athlete"
              value={athleteId}
              onChange={(e) => handleFilterChange(setAthleteId)(e.target.value)}
              disabled={athletesQuery.isLoading}
              className={inputSelectClass}
            >
              <option value="">Todos los atletas</option>
              {athletes.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.first_name} {a.last_name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="filter-date-from" className="text-xs font-medium text-mid-gray">
              Desde
            </label>
            <input
              id="filter-date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => handleFilterChange(setDateFrom)(e.target.value)}
              className={inputSelectClass}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="filter-date-to" className="text-xs font-medium text-mid-gray">
              Hasta
            </label>
            <input
              id="filter-date-to"
              type="date"
              value={dateTo}
              onChange={(e) => handleFilterChange(setDateTo)(e.target.value)}
              className={inputSelectClass}
            />
          </div>

          {hasActiveFilters && (
            <button
              type="button"
              onClick={resetFilters}
              className="inline-flex min-h-[40px] items-center gap-1.5 self-end rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70 shadow-ring"
            >
              <X size={14} aria-hidden="true" />
              Limpiar filtros
            </button>
          )}
        </div>
      </div>

      {/* Loading */}
      {reviewQuery.isLoading && (
        <div className="space-y-2 rounded-xl bg-white p-4 shadow-card" role="status" aria-live="polite">
          <span className="sr-only">Cargando actividades…</span>
          {Array.from({ length: 5 }).map((_, idx) => (
            <div key={idx} className="h-16 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {/* Error */}
      {reviewQuery.isError && !reviewQuery.isLoading && (
        <div
          className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4"
          role="alert"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-red-500" aria-hidden="true" />
          <p className="flex-1 text-sm text-red-700">
            No se pudo cargar la lista de actividades.
          </p>
          <button
            type="button"
            onClick={() => reviewQuery.refetch()}
            className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-red-700 transition-opacity hover:opacity-70 shadow-ring"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Empty */}
      {!reviewQuery.isLoading && !reviewQuery.isError && items.length === 0 && (
        <div
          className="rounded-xl bg-white p-10 text-center shadow-card"
          style={{ borderStyle: "dashed" }}
        >
          <Filter className="mx-auto h-8 w-8 text-mid-gray" aria-hidden="true" />
          <p className="mt-2 text-sm text-mid-gray">
            {hasActiveFilters
              ? "No hay actividades para los filtros seleccionados."
              : "Todavía no ha llegado ninguna actividad sincronizada. Aparecerán aquí automáticamente cuando los atletas suban rodadas a Strava."}
          </p>
        </div>
      )}

      {/* Lista agrupada por fecha */}
      {!reviewQuery.isLoading && !reviewQuery.isError && items.length > 0 && (
        <div className="space-y-6">
          {groups.map((group) => (
            <div key={group.dateKey} className="space-y-3">
              <h2 className="text-sm font-semibold text-charcoal">
                {formatGroupHeading(group.dateKey)}
              </h2>
              <div className="space-y-3">
                {group.activities.map((activity) => (
                  <ActivityCard
                    key={activity.id}
                    activity={activity}
                    showAthleteName
                    canLink
                  />
                ))}
              </div>
            </div>
          ))}

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <p className="text-xs text-mid-gray">
              Mostrando {items.length} de {total} actividades.
            </p>
            {hasMore && (
              <button
                type="button"
                onClick={() =>
                  setPageSize((prev) => Math.min(prev + PAGE_SIZE_STEP, MAX_PAGE_SIZE))
                }
                disabled={reviewQuery.isFetching || pageSize >= MAX_PAGE_SIZE}
                className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-50 shadow-ring"
              >
                {reviewQuery.isFetching ? "Cargando…" : "Cargar más"}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export default ActivityReviewPage;
