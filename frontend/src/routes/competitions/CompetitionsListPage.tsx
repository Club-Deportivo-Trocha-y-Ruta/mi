/**
 * CompetitionsListPage — página de lista de competencias (CF4).
 *
 * Layout:
 *   - Header: título + botón "Nueva competencia"
 *   - CompetitionFiltersBar: temporada, estado (chips), tipo, sede
 *   - Tabla desktop (≥md): shadcn Table con badges tri-estado y kebab de acciones
 *   - Cards mobile (<md): un card por válida
 *   - Empty/Loading/Error states
 *
 * Filtros "Próxima" y "Con resultados" son client-side (post-fetch).
 * Filtros "Planificada", "Cancelada", temporada y sede van como query params.
 *
 * Gate de admin: solo admin ve "Eliminar" en el kebab.
 *
 * Sincronización con la URL (2026-09-23): `?season=` fija la temporada
 * inicial (default: la temporada actual, mismo `currentSeason()` que usa
 * `PendingInbox`) y `?filter=needs-results` deja solo las válidas que
 * necesitan resultados — enlace de entrada desde la fila "Resultados por
 * importar" del Inicio (`PendingInbox.tsx`), con el MISMO criterio que esa
 * fila usa para su conteo: sin resultados y con fecha ya pasada
 * (`diffDaysFromToday(event_date) < 0`). Es un filtro de entrada, no un
 * control visible en `CompetitionFiltersBar` — tocar cualquier otro filtro
 * lo limpia. Todo cambio de filtro actualiza la URL con `replace` (no
 * ensucia el historial de navegación).
 */
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  CalendarPlus,
  Edit2,
  History,
  Loader2,
  MoreHorizontal,
  RefreshCw,
  Trash2,
  Trophy,
  UserCheck,
  Upload,
} from "lucide-react";

import {
  CompetitionFiltersBar,
  type LocalFilters,
} from "@/components/competitions/CompetitionFiltersBar";
import { CompetitionStatusBadges } from "@/components/competitions/CompetitionStatusBadges";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import {
  SiblingViewTabs,
  type SiblingViewTabsItem,
} from "@/components/layout/SiblingViewTabs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TableScrollContainer } from "@/components/ui/table";
import {
  getRaceEventErrorMessage,
  raceEventKeys,
  useCleanupDuplicateRaceEvent,
  useDeleteRaceEvent,
  useRaceEventsList,
} from "@/hooks/race/useRaceEvents";
import { getRaceEvent } from "@/api/raceEvents";
import { currentSeason, diffDaysFromToday } from "@/lib/datetime";
import { usePrefetchOnIntent } from "@/hooks/usePrefetchOnIntent";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type {
  RaceEventListFilters,
  RaceEventListItem,
  RaceEventStatus,
} from "@/types/raceEvents.types";

// ---------------------------------------------------------------------------
// Helpers de formato
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<RaceEventStatus, string> = {
  scheduled: "Planificada",
  completed: "Con resultados",
  cancelled: "Cancelada",
};

function formatEventDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  if (!year || !month || !day) return iso;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return date.toLocaleDateString("es-CO", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function isUpcomingWithin30Days(iso: string): boolean {
  const eventDate = new Date(iso);
  const now = new Date();
  const diffMs = eventDate.getTime() - now.getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  return diffDays >= 0 && diffDays <= 30;
}

/** Temporada inicial desde `?season=` — si falta o no es numérica, cae a
 * la temporada actual (`currentSeason()`, mismo helper que `PendingInbox`
 * usa para contar "Resultados por importar"). */
function parseSeasonParam(raw: string | null): number {
  const parsed = raw != null ? Number(raw) : NaN;
  return Number.isFinite(parsed) ? parsed : currentSeason();
}

/** Mismo criterio que `resultsToImportState` en `PendingInbox.tsx` (T033):
 * sin resultados importados y con fecha de evento ya pasada. */
function needsResults(item: RaceEventListItem): boolean {
  if (item.has_results) return false;
  const days = diffDaysFromToday(item.event_date);
  return days !== null && days < 0;
}

// Sibling views of the Competencias area (data-model.md §2) — shared across
// CompetitionsListPage, UnlinkedCompetitorsPage y SeasonInsightsPage.
const COMPETITIONS_SIBLING_VIEWS: SiblingViewTabsItem[] = [
  { label: "Válidas", to: "/competitions" },
  { label: "Sin enlazar", to: "/competitions/unlinked" },
  { label: "Panorama de temporada", to: `/competitions/insights/season/${currentSeason()}` },
];

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function CompetitionsListPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === UserRole.admin;
  const isCoach = user?.role === UserRole.coach;

  const [searchParams, setSearchParams] = useSearchParams();

  // Filtros que van al backend — la temporada se sincroniza con `?season=`.
  const [filters, setFilters] = useState<RaceEventListFilters>(() => ({
    season: parseSeasonParam(searchParams.get("season")),
  }));
  // Filtros client-side (post-fetch)
  const [localFilters, setLocalFilters] = useState<LocalFilters>({});
  // Filtro de entrada desde `?filter=needs-results` (ver docstring del
  // archivo). Se limpia en cuanto el coach toca cualquier otro filtro.
  const [needsResultsOnly, setNeedsResultsOnly] = useState(
    () => searchParams.get("filter") === "needs-results",
  );

  const { data, isLoading, isError, refetch, isFetching } = useRaceEventsList(filters);
  const deleteMutation = useDeleteRaceEvent();
  const cleanupMutation = useCleanupDuplicateRaceEvent();

  const [deleteTarget, setDeleteTarget] = useState<RaceEventListItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Feature 009: limpieza de válida duplicada (coach) — flujo separado del DELETE admin.
  const [cleanupTarget, setCleanupTarget] = useState<RaceEventListItem | null>(null);
  const [cleanupError, setCleanupError] = useState<string | null>(null);

  /** Todo cambio de filtro de backend actualiza `?season=` con `replace`
   * y limpia `?filter=needs-results` — a partir de que el coach toca un
   * filtro, manda su elección sobre el filtro de entrada. */
  function handleFiltersChange(next: RaceEventListFilters) {
    setFilters(next);
    setNeedsResultsOnly(false);
    const params = new URLSearchParams(searchParams);
    if (next.season != null) params.set("season", String(next.season));
    else params.delete("season");
    params.delete("filter");
    setSearchParams(params, { replace: true });
  }

  function handleLocalFiltersChange(next: LocalFilters) {
    setLocalFilters(next);
    setNeedsResultsOnly(false);
    if (searchParams.has("filter")) {
      const params = new URLSearchParams(searchParams);
      params.delete("filter");
      setSearchParams(params, { replace: true });
    }
  }

  // Aplicar filtros client-side
  const items = useMemo(() => {
    const raw = data?.items ?? [];
    return raw.filter((item) => {
      if (localFilters.hasResults && !item.has_results) return false;
      if (localFilters.upcoming && !isUpcomingWithin30Days(item.event_date)) return false;
      if (needsResultsOnly && !needsResults(item)) return false;
      return true;
    });
  }, [data?.items, localFilters, needsResultsOnly]);

  function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleteError(null);
    deleteMutation.mutate(
      { id: deleteTarget.id },
      {
        onSuccess: () => setDeleteTarget(null),
        onError: (err) => setDeleteError(getRaceEventErrorMessage(err)),
      },
    );
  }

  function handleCleanupConfirm() {
    if (!cleanupTarget) return;
    setCleanupError(null);
    cleanupMutation.mutate(
      { id: cleanupTarget.id },
      {
        onSuccess: () => setCleanupTarget(null),
        onError: (err) => setCleanupError(getRaceEventErrorMessage(err)),
      },
    );
  }

  const canDelete = (item: RaceEventListItem) =>
    isAdmin && !item.has_results && !item.has_calendar_event;

  // Feature 009: el coach puede limpiar un duplicado sin resultados (con o sin
  // calendario asociado). Las válidas con resultados quedan protegidas.
  const canCleanup = (item: RaceEventListItem) => isCoach && !item.has_results;

  const deleteDisabledReason = (item: RaceEventListItem): string | null => {
    if (!isAdmin) return "Solo administradores pueden eliminar válidas.";
    if (item.has_results && item.has_calendar_event)
      return "Tiene resultados y evento de calendario vinculados.";
    if (item.has_results) return "Tiene resultados importados. No se puede eliminar.";
    if (item.has_calendar_event) return "Está vinculada al calendario. No se puede eliminar.";
    return null;
  };

  return (
    <section className="space-y-5">
      <PageHeader
        title="Competencias"
        subtitle="Válidas Copa Valle y campeonatos del club."
        actions={
          <>
            {/* Acciones secundarias */}
            <Link
              to="/competitions/import"
              className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-surface-raised px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
              aria-label="Cargar resultados de una válida"
            >
              <Upload size={14} aria-hidden="true" />
              Cargar resultados
            </Link>
            {/* Feature 044 (US4) — entrada a la revisión de identidad del histórico */}
            <Link
              to="/competitions/identity-review"
              className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-surface-raised px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
              aria-label="Revisar identidad de competidores del histórico"
            >
              <UserCheck size={14} aria-hidden="true" />
              Revisión de identidad
            </Link>
            {/* Feature 044 (US5) — entrada al tablero de carga histórica */}
            <Link
              to="/competitions/history"
              className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-surface-raised px-4 py-2 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
              aria-label="Ver el tablero de carga histórica"
            >
              <History size={14} aria-hidden="true" />
              Carga histórica
            </Link>
            {/* Acción primaria */}
            <Link
              to="/competitions/new"
              className="inline-flex min-h-[44px] items-center rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-surface transition-opacity hover:opacity-70 shadow-button-highlight"
            >
              + Nueva competencia
            </Link>
          </>
        }
      />

      <SiblingViewTabs items={COMPETITIONS_SIBLING_VIEWS} />

      {/* Filtros */}
      <CompetitionFiltersBar
        value={filters}
        onChange={handleFiltersChange}
        localFilters={localFilters}
        onLocalFiltersChange={handleLocalFiltersChange}
      />

      {/* Loading skeleton */}
      {isLoading && (
        <div className="space-y-2 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline">
          {Array.from({ length: 5 }).map((_, idx) => (
            <div key={idx} className="h-12 animate-pulse rounded-lg bg-light-gray" />
          ))}
        </div>
      )}

      {/* Error state */}
      {isError && !isLoading && (
        <div
          className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-4"
          role="alert"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-red-500" aria-hidden="true" />
          <p className="flex-1 text-sm text-red-700">
            No se pudo cargar la lista de competencias.
          </p>
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg bg-surface-raised px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-50 shadow-ring"
          >
            {isFetching ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw size={14} aria-hidden="true" />
            )}
            Reintentar
          </button>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && items.length === 0 && (
        <EmptyState
          icon={Trophy}
          title="No hay competencias en esta temporada"
          description="Ajusta los filtros o crea la primera válida."
          action={
            <Link
              to="/competitions/new"
              className="inline-flex min-h-[44px] items-center rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-surface transition-opacity hover:opacity-70 shadow-button-highlight"
            >
              + Crear primera válida
            </Link>
          }
        />
      )}

      {/* Tabla desktop (≥md) */}
      {!isLoading && !isError && items.length > 0 && (
        <>
          <div className="hidden md:block rounded-card bg-surface-raised shadow-card ring-1 ring-hairline">
            <TableScrollContainer className="rounded-xl">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-gray">
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                      #
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                      Fecha
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                      Nombre
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                      Sede
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                      Estado
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-mid-gray">
                      Indicadores
                    </th>
                    {/* Sticky: en t768/t1024 la tabla excede el ancho del
                        contenedor (F-01); fijar Acciones a la derecha la
                        mantiene siempre alcanzable sin depender de que el
                        coach descubra el scroll horizontal. */}
                    <th className="sticky right-0 z-10 bg-surface-raised px-4 py-3 text-right text-xs font-medium uppercase tracking-wide text-mid-gray">
                      Acciones
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[rgba(34,42,53,0.06)]">
                  {items.map((item) => (
                    <CompetitionTableRow
                      key={item.id}
                      item={item}
                      isAdmin={isAdmin}
                      canDelete={canDelete(item)}
                      deleteDisabledReason={deleteDisabledReason(item)}
                      onDelete={() => {
                        setDeleteError(null);
                        setDeleteTarget(item);
                      }}
                      canCleanup={canCleanup(item)}
                      onCleanup={() => {
                        setCleanupError(null);
                        setCleanupTarget(item);
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </TableScrollContainer>
          </div>

          {/* Cards mobile (<md) */}
          <div className="flex flex-col gap-3 md:hidden">
            {items.map((item) => (
              <CompetitionCard
                key={item.id}
                item={item}
                isAdmin={isAdmin}
                canDelete={canDelete(item)}
                deleteDisabledReason={deleteDisabledReason(item)}
                onDelete={() => {
                  setDeleteError(null);
                  setDeleteTarget(item);
                }}
                canCleanup={canCleanup(item)}
                onCleanup={() => {
                  setCleanupError(null);
                  setCleanupTarget(item);
                }}
              />
            ))}
          </div>
        </>
      )}

      {/* Recuento */}
      {!isLoading && !isError && data && (
        <p className="text-xs text-mid-gray text-right">
          Mostrando {items.length} de {data.total} competencias
        </p>
      )}

      {/* Dialog de confirmación de eliminación */}
      <ConfirmDialog
        open={deleteTarget !== null}
        title="Eliminar competencia"
        description={
          <>
            <span className="font-medium text-charcoal">{deleteTarget?.name ?? ""}</span>
            <br />
            Esta acción es irreversible. La válida se eliminará permanentemente del sistema. Los datos históricos no podrán recuperarse.
          </>
        }
        confirmLabel="Eliminar válida"
        tone="danger"
        isPending={deleteMutation.isPending}
        errorMessage={deleteError ?? undefined}
        onCancel={() => {
          if (!deleteMutation.isPending) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
        onConfirm={handleDeleteConfirm}
      />

      {/* Dialog de confirmación de limpieza de duplicado (feature 009, coach) */}
      <ConfirmDialog
        open={cleanupTarget !== null}
        title="Eliminar competencia duplicada"
        description={
          <>
            <span className="font-medium text-charcoal">{cleanupTarget?.name ?? ""}</span>
            <br />
            Esta acción es irreversible. Se eliminarán permanentemente la competencia duplicada y su evento de calendario asociado. Úsala solo para limpiar duplicados sin resultados.
          </>
        }
        confirmLabel="Eliminar duplicado"
        tone="danger"
        isPending={cleanupMutation.isPending}
        errorMessage={cleanupError ?? undefined}
        onCancel={() => {
          if (!cleanupMutation.isPending) {
            setCleanupTarget(null);
            setCleanupError(null);
          }
        }}
        onConfirm={handleCleanupConfirm}
      />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Fila de tabla desktop
// ---------------------------------------------------------------------------

interface RowProps {
  item: RaceEventListItem;
  isAdmin: boolean;
  canDelete: boolean;
  deleteDisabledReason: string | null;
  onDelete: () => void;
  canCleanup: boolean;
  onCleanup: () => void;
}

function CompetitionTableRow({
  item,
  isAdmin,
  canDelete,
  deleteDisabledReason,
  onDelete,
  canCleanup,
  onCleanup,
}: RowProps) {
  const navigate = useNavigate();
  const prefetch = usePrefetchOnIntent();
  // Feature 012, US3: prepara el detalle al mostrar intención (hover/touch)
  // — misma queryKey/fn que useRaceEvent, así abrir la fila no muestra carga.
  const prefetchDetail = () =>
    prefetch({
      queryKey: raceEventKeys.detail(item.id),
      queryFn: ({ signal }) => getRaceEvent(item.id, { signal }),
    });
  return (
    <tr
      className="group hover:bg-[rgba(34,42,53,0.02)] transition-colors cursor-pointer"
      onClick={() => navigate(`/competitions/${item.id}`)}
      onMouseEnter={prefetchDetail}
      onTouchStart={prefetchDetail}
    >
      <td className="px-4 py-3 text-sm font-medium text-charcoal">
        {item.is_championship ? "CD" : `V${item.sequence_number}`}
      </td>
      <td className="px-4 py-3 text-sm text-mid-gray whitespace-nowrap">
        {formatEventDate(item.event_date)}
      </td>
      <td className="px-4 py-3 text-sm font-medium text-charcoal">
        <Link
          to={`/competitions/${item.id}`}
          className="transition-opacity hover:opacity-70"
          onClick={(e) => e.stopPropagation()}
        >
          {item.name}
        </Link>
      </td>
      <td className="px-4 py-3 text-sm text-mid-gray">
        {item.location ?? "—"}
      </td>
      <td className="px-4 py-3 text-sm text-mid-gray">
        {STATUS_LABELS[item.status]}
      </td>
      <td className="px-4 py-3">
        <CompetitionStatusBadges item={item} />
      </td>
      {/* stopPropagation: interactuar con el kebab no debe navegar la fila.
          sticky + bg-surface-raised/group-hover: la celda flota sobre el resto de la
          fila al hacer scroll horizontal y sigue el color de hover de la
          fila (F-01). */}
      <td
        className="sticky right-0 bg-surface-raised px-4 py-3 text-right group-hover:bg-[rgba(34,42,53,0.02)]"
        onClick={(e) => e.stopPropagation()}
      >
        <ActionsKebab
          item={item}
          isAdmin={isAdmin}
          canDelete={canDelete}
          deleteDisabledReason={deleteDisabledReason}
          onDelete={onDelete}
          canCleanup={canCleanup}
          onCleanup={onCleanup}
        />
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Card mobile
// ---------------------------------------------------------------------------

function CompetitionCard({
  item,
  isAdmin,
  canDelete,
  deleteDisabledReason,
  onDelete,
  canCleanup,
  onCleanup,
}: RowProps) {
  const navigate = useNavigate();
  const prefetch = usePrefetchOnIntent();
  // Feature 012, US3: touch-start en el card móvil prepara el detalle.
  const prefetchDetail = () =>
    prefetch({
      queryKey: raceEventKeys.detail(item.id),
      queryFn: ({ signal }) => getRaceEvent(item.id, { signal }),
    });
  return (
    <div
      className="rounded-card bg-surface-raised p-4 space-y-3 cursor-pointer shadow-card ring-1 ring-hairline"
      onClick={() => navigate(`/competitions/${item.id}`)}
      onMouseEnter={prefetchDetail}
      onTouchStart={prefetchDetail}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            to={`/competitions/${item.id}`}
            className="block text-sm font-semibold text-charcoal truncate transition-opacity hover:opacity-70"
            onClick={(e) => e.stopPropagation()}
          >
            {item.name}
          </Link>
          <p className="mt-0.5 text-xs text-mid-gray">
            {item.is_championship ? "CD" : `Válida ${item.sequence_number}`}
            {item.location ? ` · ${item.location}` : ""}
          </p>
        </div>
        {/* stopPropagation: interactuar con el kebab no debe navegar la card */}
        <div onClick={(e) => e.stopPropagation()}>
          <ActionsKebab
            item={item}
            isAdmin={isAdmin}
            canDelete={canDelete}
            deleteDisabledReason={deleteDisabledReason}
            onDelete={onDelete}
            canCleanup={canCleanup}
            onCleanup={onCleanup}
          />
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-mid-gray">
        <span>{formatEventDate(item.event_date)}</span>
        <span>{STATUS_LABELS[item.status]}</span>
      </div>

      <CompetitionStatusBadges item={item} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Kebab de acciones
// ---------------------------------------------------------------------------

interface ActionsKebabProps {
  item: RaceEventListItem;
  isAdmin: boolean;
  canDelete: boolean;
  deleteDisabledReason: string | null;
  onDelete: () => void;
  canCleanup: boolean;
  onCleanup: () => void;
}

function ActionsKebab({
  item,
  isAdmin,
  canDelete,
  deleteDisabledReason,
  onDelete,
  canCleanup,
  onCleanup,
}: ActionsKebabProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex min-h-12 min-w-12 items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray"
          aria-label={`Acciones para ${item.name}`}
        >
          <MoreHorizontal size={16} aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {/* Importar resultados — solo si no tiene resultados */}
        {!item.has_results && (
          <DropdownMenuItem asChild>
            <Link
              to={`/competitions/${item.id}/import`}
              className="flex items-center gap-2"
            >
              <Upload size={14} aria-hidden="true" />
              Importar resultados
            </Link>
          </DropdownMenuItem>
        )}

        {/* Editar metadata */}
        <DropdownMenuItem asChild>
          <Link
            to={`/competitions/${item.id}/edit`}
            className="flex items-center gap-2"
          >
            <Edit2 size={14} aria-hidden="true" />
            Editar metadata
          </Link>
        </DropdownMenuItem>

        {/* Asociar a calendario — solo si no tiene evento de calendario */}
        {!item.has_calendar_event && (
          <DropdownMenuItem asChild>
            <Link
              to={`/calendar/events/new?race_event_id=${item.id}`}
              className="flex items-center gap-2"
            >
              <CalendarPlus size={14} aria-hidden="true" />
              Asociar a calendario
            </Link>
          </DropdownMenuItem>
        )}

        {/* Eliminar duplicado — solo coach, válida sin resultados (feature 009) */}
        {canCleanup && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-red-600 focus:bg-red-50 data-[highlighted]:bg-red-50 data-[highlighted]:text-red-700"
              onSelect={onCleanup}
            >
              <Trash2 size={14} aria-hidden="true" />
              Eliminar duplicado
            </DropdownMenuItem>
          </>
        )}

        {/* Separador + Eliminar — solo admin */}
        {isAdmin && (
          <>
            <DropdownMenuSeparator />
            {canDelete ? (
              <DropdownMenuItem
                className="text-red-600 focus:bg-red-50 data-[highlighted]:bg-red-50 data-[highlighted]:text-red-700"
                onSelect={onDelete}
              >
                Eliminar
              </DropdownMenuItem>
            ) : (
              <TooltipProvider delayDuration={100}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span>
                      <DropdownMenuItem
                        disabled
                        className="cursor-not-allowed text-mid-gray"
                      >
                        Eliminar
                      </DropdownMenuItem>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="left">
                    {deleteDisabledReason}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
