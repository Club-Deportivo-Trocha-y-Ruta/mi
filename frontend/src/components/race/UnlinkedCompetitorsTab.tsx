/**
 * UnlinkedCompetitorsTab — Option A R1 (enlace retroactivo).
 *
 * Permite al coach enlazar competitors de Copa Valle con athletes del club
 * de forma retroactiva. Renderiza una lista de competitors sin enlace, con
 * top-3 sugerencias inline (match fuzzy backend) + un combobox manual para
 * cuando ninguna sugerencia aplica.
 *
 * Estructura (post-B5):
 *  - `unlinked/SuggestionCard.tsx`     → card de match fuzzy con ScoreBar.
 *  - `unlinked/CompetitorCard.tsx`     → card de un competitor + sugerencias + manual.
 *  - `unlinked/CompetitorSkeleton.tsx` → placeholder shimmer.
 *  - `unlinked/ToastBanner.tsx`        → banner aria-live sin librería.
 *  - `unlinked/useCompetitorActions`   → coordina link/unlink + toast.
 *  - `unlinked/useUnlinkedToast`       → state machine del toast auto-dismiss.
 *
 * Reusa `AthleteCombobox` de `@/components/ai/AthleteCombobox`.
 */
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Filter, Loader2, Unlink, Users } from "lucide-react";

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useUnlinkedCompetitors } from "@/hooks/race/useUnlinkedCompetitors";
import type { UnlinkedCompetitorItem } from "@/types/raceCompetitors.types";

import { CompetitorCard } from "./unlinked/CompetitorCard";
import { CompetitorSkeleton } from "./unlinked/CompetitorSkeleton";
import { ToastBanner } from "./unlinked/ToastBanner";
import { useCompetitorActions } from "./unlinked/useCompetitorActions";
import { useUnlinkedToast } from "./unlinked/useUnlinkedToast";

const CURRENT_YEAR = new Date().getFullYear();
const SEASON_OPTIONS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2];

// ---------------------------------------------------------------------------
// Tab principal
// ---------------------------------------------------------------------------

export interface UnlinkedCompetitorsTabProps {
  /** Si se pasa, se invoca cuando cambia el contador de unlinked. */
  onUnlinkedCountChange?: (total: number) => void;
}

export function UnlinkedCompetitorsTab({
  onUnlinkedCountChange,
}: UnlinkedCompetitorsTabProps = {}) {
  // Filtros
  const [onlyTrocha, setOnlyTrocha] = useState(true);
  const [season, setSeason] = useState<number | null>(null);

  // Toast simple (sin librería)
  const { toast, showToast, dismiss: dismissToast } = useUnlinkedToast();

  // Dialog de confirmación para unlink
  const [unlinkTarget, setUnlinkTarget] =
    useState<UnlinkedCompetitorItem | null>(null);

  // Query
  const filters = useMemo(
    () => ({
      unlinked: true,
      include_suggestions: true,
      suggestions_limit: 3,
      limit: 50,
      offset: 0,
      ...(onlyTrocha ? { club_filter: "trocha" } : {}),
      ...(season ? { season } : {}),
    }),
    [onlyTrocha, season],
  );

  const query = useUnlinkedCompetitors(filters);

  // Mutations + state coordinado (link/unlink + spinner por sugerencia).
  const {
    linkMutation,
    unlinkMutation,
    linkingAthleteId,
    handleLink,
    handleUnlinkConfirm,
  } = useCompetitorActions({ showToast });

  // Notificar al padre el conteo total (para badge en tab)
  const total = query.data?.total ?? 0;
  useEffect(() => {
    onUnlinkedCountChange?.(total);
  }, [total, onUnlinkedCountChange]);

  const items = query.data?.items ?? [];

  return (
    <section
      aria-labelledby="unlinked-competitors-heading"
      className="space-y-4"
      data-testid="unlinked-competitors-tab"
    >
      {/* Header con contador + filtros */}
      <header
        className="flex flex-col gap-3 rounded-xl bg-white p-4 ring-1 ring-light-gray sm:flex-row sm:items-center sm:justify-between"
        data-testid="unlinked-header"
      >
        <div className="flex items-center gap-3">
          <span
            className="flex h-9 w-9 items-center justify-center rounded-full bg-amber-50 text-amber-700"
            aria-hidden="true"
          >
            <Users size={16} />
          </span>
          <div>
            <h2 id="unlinked-competitors-heading" className="text-sm text-charcoal font-heading">
              Atletas sin enlazar
            </h2>
            <p className="text-xs text-mid-gray" data-testid="unlinked-count">
              {query.isLoading
                ? "Cargando…"
                : total === 0
                  ? "Todos los competidores están enlazados"
                  : `${total} competidor${total === 1 ? "" : "es"} pendiente${total === 1 ? "" : "s"} de enlazar`}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-light-gray/40 px-3 py-1.5 text-xs font-medium text-charcoal transition-colors hover:bg-light-gray/70">
            <input
              type="checkbox"
              checked={onlyTrocha}
              onChange={(e) => setOnlyTrocha(e.target.checked)}
              data-testid="filter-only-trocha"
              className="h-3.5 w-3.5 rounded border-mid-gray text-charcoal focus:ring-2 focus:ring-blue-500/40"
            />
            <Filter size={11} aria-hidden="true" />
            Solo Trocha y Ruta
          </label>

          <label className="sr-only" htmlFor="filter-season">
            Filtrar por temporada
          </label>
          <select
            id="filter-season"
            value={season ?? ""}
            onChange={(e) =>
              setSeason(e.target.value ? Number(e.target.value) : null)
            }
            data-testid="filter-season"
            aria-label="Filtrar por temporada"
            className="rounded-lg bg-white px-2 py-1.5 text-xs text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40 shadow-ring"
          >
            <option value="">Todas las temporadas</option>
            {SEASON_OPTIONS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Toast */}
      <ToastBanner toast={toast} onDismiss={dismissToast} />

      {/* Lista */}
      {query.isLoading && (
        <div className="space-y-3" aria-busy="true">
          <CompetitorSkeleton />
          <CompetitorSkeleton />
        </div>
      )}

      {query.isError && (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          data-testid="unlinked-error"
        >
          No se pudo cargar el listado de competidores sin enlazar. Reintenta
          más tarde.
        </div>
      )}

      {query.data && items.length === 0 && (
        <div
          className="flex flex-col items-center gap-3 rounded-xl bg-white p-8 text-center ring-1 ring-light-gray"
          data-testid="unlinked-empty"
        >
          <span
            className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"
            aria-hidden="true"
          >
            <CheckCircle2 size={24} />
          </span>
          <p className="text-sm text-charcoal font-heading">
            Todos los competidores están enlazados
          </p>
          <p className="max-w-md text-xs text-mid-gray">
            Cuando importes resultados nuevos y queden competitors sin
            asociar a un atleta del club, aparecerán aquí para que los
            enlaces retroactivamente.
          </p>
        </div>
      )}

      {query.data && items.length > 0 && (
        <div className="space-y-3" data-testid="unlinked-list">
          {items.map((c) => (
            <CompetitorCard
              key={c.id}
              competitor={c}
              isLinkingThis={
                linkMutation.isPending &&
                linkMutation.variables?.competitorId === c.id
              }
              linkingAthleteId={
                linkMutation.variables?.competitorId === c.id
                  ? linkingAthleteId
                  : null
              }
              onLink={handleLink}
              onUnlink={(competitor) => setUnlinkTarget(competitor)}
            />
          ))}

          {query.data.total > items.length && (
            <p
              className="text-center text-[10px] text-mid-gray"
              data-testid="unlinked-pagination-hint"
            >
              Mostrando {items.length} de {query.data.total}. Ajusta los
              filtros para acotar.
            </p>
          )}
        </div>
      )}

      {/* Confirm dialog: unlink */}
      <Dialog
        open={unlinkTarget != null}
        onOpenChange={(open) => {
          if (!open) setUnlinkTarget(null);
        }}
      >
        <DialogContent data-testid="unlink-confirm-dialog">
          <DialogHeader>
            <DialogTitle>Desvincular competidor</DialogTitle>
            <DialogDescription>
              ¿Estás seguro? {unlinkTarget?.results_count ?? 0} resultado
              {(unlinkTarget?.results_count ?? 0) === 1 ? "" : "s"} de{" "}
              <strong>{unlinkTarget?.display_name}</strong> quedarán sin
              atleta asociado.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <p className="text-xs text-mid-gray">
              Esta acción no borra los resultados; sólo elimina el vínculo
              con el atleta. Puedes volver a enlazar después.
            </p>
          </DialogBody>
          <DialogFooter>
            <button
              type="button"
              onClick={() => setUnlinkTarget(null)}
              className="rounded-lg px-3 py-2 text-sm font-medium text-mid-gray transition-colors hover:bg-light-gray"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => {
                if (unlinkTarget) {
                  handleUnlinkConfirm(unlinkTarget, () =>
                    setUnlinkTarget(null),
                  );
                }
              }}
              disabled={unlinkMutation.isPending}
              data-testid="unlink-confirm-btn"
              className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {unlinkMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              ) : (
                <Unlink size={14} aria-hidden="true" />
              )}
              Sí, desvincular
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}

export default UnlinkedCompetitorsTab;
