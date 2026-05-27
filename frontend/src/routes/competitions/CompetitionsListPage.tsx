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
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  CalendarPlus,
  Edit2,
  ExternalLink,
  Loader2,
  MoreHorizontal,
  RefreshCw,
  Trophy,
  Upload,
} from "lucide-react";

import {
  CompetitionFiltersBar,
  type LocalFilters,
} from "@/components/competitions/CompetitionFiltersBar";
import { CompetitionStatusBadges } from "@/components/competitions/CompetitionStatusBadges";
import { ConfirmDeleteDialog } from "@/components/common/ConfirmDeleteDialog";
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
import {
  getRaceEventErrorMessage,
  useDeleteRaceEvent,
  useRaceEventsList,
} from "@/hooks/race/useRaceEvents";
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

// Estilos comunes
const cardStyle = {
  boxShadow:
    "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
};

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function CompetitionsListPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === UserRole.admin;

  // Filtros que van al backend
  const [filters, setFilters] = useState<RaceEventListFilters>({ season: 2026 });
  // Filtros client-side (post-fetch)
  const [localFilters, setLocalFilters] = useState<LocalFilters>({});

  const { data, isLoading, isError, refetch, isFetching } = useRaceEventsList(filters);
  const deleteMutation = useDeleteRaceEvent();

  const [deleteTarget, setDeleteTarget] = useState<RaceEventListItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Aplicar filtros client-side
  const items = useMemo(() => {
    const raw = data?.items ?? [];
    return raw.filter((item) => {
      if (localFilters.hasResults && !item.has_results) return false;
      if (localFilters.upcoming && !isUpcomingWithin30Days(item.event_date)) return false;
      return true;
    });
  }, [data?.items, localFilters]);

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

  const canDelete = (item: RaceEventListItem) =>
    isAdmin && !item.has_results && !item.has_calendar_event;

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
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1
            className="text-2xl text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            Competencias
          </h1>
          <p className="mt-0.5 text-sm text-mid-gray">
            Válidas Copa Valle y campeonatos del club.
          </p>
        </div>
        <Link
          to="/competitions/new"
          className="inline-flex min-h-[44px] items-center rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
          style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
        >
          + Nueva competencia
        </Link>
      </div>

      {/* Filtros */}
      <CompetitionFiltersBar
        value={filters}
        onChange={setFilters}
        localFilters={localFilters}
        onLocalFiltersChange={setLocalFilters}
      />

      {/* Loading skeleton */}
      {isLoading && (
        <div className="space-y-2 rounded-xl bg-white p-4" style={cardStyle}>
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
            className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 disabled:opacity-50"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
        <div
          className="rounded-xl bg-white p-10 text-center"
          style={{ ...cardStyle, borderStyle: "dashed" }}
        >
          <Trophy
            size={36}
            className="mx-auto mb-3 text-mid-gray"
            aria-hidden="true"
          />
          <p className="text-sm font-medium text-charcoal">
            No hay competencias en esta temporada
          </p>
          <p className="mt-1 text-xs text-mid-gray">
            Ajusta los filtros o crea la primera válida.
          </p>
          <Link
            to="/competitions/new"
            className="mt-4 inline-flex min-h-[44px] items-center rounded-lg bg-charcoal px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(255, 255, 255, 0.15) 0px 2px 0px inset" }}
          >
            + Crear primera válida
          </Link>
        </div>
      )}

      {/* Tabla desktop (≥md) */}
      {!isLoading && !isError && items.length > 0 && (
        <>
          <div className="hidden md:block rounded-xl bg-white overflow-hidden" style={cardStyle}>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[rgba(34,42,53,0.08)]">
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
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wide text-mid-gray">
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
                  />
                ))}
              </tbody>
            </table>
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
      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        title="Eliminar competencia"
        subject={deleteTarget?.name ?? ""}
        description="Esta acción es irreversible. La válida se eliminará permanentemente del sistema. Los datos históricos no podrán recuperarse."
        confirmLabel="Eliminar válida"
        isPending={deleteMutation.isPending}
        errorMessage={deleteError}
        onCancel={() => {
          if (!deleteMutation.isPending) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
        onConfirm={handleDeleteConfirm}
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
}

function CompetitionTableRow({
  item,
  isAdmin,
  canDelete,
  deleteDisabledReason,
  onDelete,
}: RowProps) {
  return (
    <tr className="hover:bg-[rgba(34,42,53,0.02)] transition-colors">
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
      <td className="px-4 py-3 text-right">
        <ActionsKebab
          item={item}
          isAdmin={isAdmin}
          canDelete={canDelete}
          deleteDisabledReason={deleteDisabledReason}
          onDelete={onDelete}
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
}: RowProps) {
  return (
    <div
      className="rounded-xl bg-white p-4 space-y-3"
      style={{
        boxShadow:
          "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            to={`/competitions/${item.id}`}
            className="block text-sm font-semibold text-charcoal truncate transition-opacity hover:opacity-70"
          >
            {item.name}
          </Link>
          <p className="mt-0.5 text-xs text-mid-gray">
            {item.is_championship ? "CD" : `Válida ${item.sequence_number}`}
            {item.location ? ` · ${item.location}` : ""}
          </p>
        </div>
        <ActionsKebab
          item={item}
          isAdmin={isAdmin}
          canDelete={canDelete}
          deleteDisabledReason={deleteDisabledReason}
          onDelete={onDelete}
        />
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
}

function ActionsKebab({
  item,
  isAdmin,
  canDelete,
  deleteDisabledReason,
  onDelete,
}: ActionsKebabProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray"
          aria-label={`Acciones para ${item.name}`}
        >
          <MoreHorizontal size={16} aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {/* Ver detalle */}
        <DropdownMenuItem asChild>
          <Link to={`/competitions/${item.id}`} className="flex items-center gap-2">
            <ExternalLink size={14} aria-hidden="true" />
            Ver detalle
          </Link>
        </DropdownMenuItem>

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
