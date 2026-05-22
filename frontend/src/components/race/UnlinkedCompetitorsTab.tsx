/**
 * UnlinkedCompetitorsTab — Option A R1 (enlace retroactivo).
 *
 * Permite al coach enlazar competitors de Copa Valle con athletes del club
 * de forma retroactiva. Renderiza una lista de competitors sin enlace, con
 * top-3 sugerencias inline (match fuzzy backend) + un combobox manual para
 * cuando ninguna sugerencia aplica.
 *
 * Filtros disponibles:
 *  - Toggle "Solo Trocha y Ruta" → `club_filter=trocha`
 *  - Select temporada → `season=YYYY`
 *
 * Mutations:
 *  - `useLinkCompetitor()` → POST /link
 *  - `useUnlinkCompetitor()` → DELETE /link (con confirm dialog)
 *
 * Toasts (sin librería externa, banner aria-live="polite"):
 *  - Éxito link: "Enlazado: N resultados asociados a {athlete}"
 *  - already_linked=true: "Ya estaba enlazado, sin cambios"
 *  - Error 409: "Ya enlazado a otro atleta, desvincula primero"
 *  - Error 403: "Sin permiso"
 *  - Error 404: "No encontrado"
 *
 * Reusa `AthleteCombobox` de `@/components/ai/AthleteCombobox`.
 */
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Filter,
  Link2,
  Loader2,
  MoreVertical,
  Search,
  TrophyIcon,
  Unlink,
  Users,
  X,
} from "lucide-react";

import { AthleteCombobox } from "@/components/ai/AthleteCombobox";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  getCompetitorErrorMessage,
  useLinkCompetitor,
  useUnlinkCompetitor,
  useUnlinkedCompetitors,
} from "@/hooks/race/useUnlinkedCompetitors";
import { cn } from "@/lib/utils";
import type {
  AthleteSuggestion,
  CompetitorLinkResponse,
  UnlinkedCompetitorItem,
} from "@/types/raceCompetitors.types";

const CURRENT_YEAR = new Date().getFullYear();
const SEASON_OPTIONS = [CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2];

// ---------------------------------------------------------------------------
// Helpers de presentación
// ---------------------------------------------------------------------------

function scoreColor(score: number): {
  bg: string;
  bar: string;
  text: string;
  label: string;
} {
  if (score >= 0.85) {
    return {
      bg: "bg-emerald-50",
      bar: "bg-emerald-500",
      text: "text-emerald-700",
      label: "Alta confianza",
    };
  }
  if (score >= 0.65) {
    return {
      bg: "bg-amber-50",
      bar: "bg-amber-500",
      text: "text-amber-700",
      label: "Confianza media",
    };
  }
  return {
    bg: "bg-red-50",
    bar: "bg-red-500",
    text: "text-red-700",
    label: "Baja confianza",
  };
}

function ScoreBar({ score }: { score: number }) {
  const palette = scoreColor(score);
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  return (
    <div className="space-y-1">
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-light-gray/60"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Score de match: ${pct}%`}
      >
        <div
          className={cn("h-full transition-all", palette.bar)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex items-center justify-between text-[10px]">
        <span className={cn("font-medium", palette.text)}>{palette.label}</span>
        <span className="font-mono text-mid-gray">{pct}%</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card de sugerencia
// ---------------------------------------------------------------------------

interface SuggestionCardProps {
  suggestion: AthleteSuggestion;
  isLinking: boolean;
  onLink: (athleteId: number) => void;
  testId: string;
}

function SuggestionCard({
  suggestion,
  isLinking,
  onLink,
  testId,
}: SuggestionCardProps) {
  const palette = scoreColor(suggestion.score);
  return (
    <div
      data-testid={testId}
      className={cn(
        "flex flex-col gap-2 rounded-lg p-3 ring-1 ring-light-gray",
        palette.bg,
      )}
    >
      <div className="space-y-0.5">
        <p
          className="truncate text-sm text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          title={suggestion.full_name}
        >
          {suggestion.full_name}
        </p>
        <p className="line-clamp-2 text-[11px] text-mid-gray" title={suggestion.reason}>
          {suggestion.reason}
        </p>
      </div>
      <ScoreBar score={suggestion.score} />
      <button
        type="button"
        onClick={() => onLink(suggestion.athlete_id)}
        disabled={isLinking}
        data-testid={`${testId}-link-btn`}
        className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isLinking ? (
          <Loader2 size={12} className="animate-spin" aria-hidden="true" />
        ) : (
          <Link2 size={12} aria-hidden="true" />
        )}
        Enlazar
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card de competitor
// ---------------------------------------------------------------------------

interface CompetitorCardProps {
  competitor: UnlinkedCompetitorItem;
  onLink: (
    competitorId: number,
    athleteId: number,
    competitor: UnlinkedCompetitorItem,
  ) => void;
  onUnlink: (competitor: UnlinkedCompetitorItem) => void;
  isLinkingThis: boolean;
  linkingAthleteId: number | null;
}

function CompetitorCard({
  competitor,
  onLink,
  onUnlink,
  isLinkingThis,
  linkingAthleteId,
}: CompetitorCardProps) {
  const [showManual, setShowManual] = useState(false);
  const [manualAthleteId, setManualAthleteId] = useState<number | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  // Si results_count > 0 y el listado lo devolvió en `unlinked=true`, el
  // competitor está pendiente. Mantenemos el botón "Desvincular" disponible
  // sólo si existe (en este flow R1 no debería estar enlazado, pero por
  // robustez ante refetch lo dejamos en menú overflow).
  const showUnlinkMenu = competitor.results_count > 0;

  return (
    <article
      data-testid={`competitor-card-${competitor.id}`}
      className="space-y-3 rounded-xl bg-white p-4"
      style={{
        boxShadow:
          "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 1px 2px 0px",
      }}
    >
      {/* Header */}
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <h3
            className="truncate text-sm text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
            }}
            title={competitor.display_name}
          >
            {competitor.display_name}
          </h3>
          <div className="flex flex-wrap items-center gap-1.5">
            {competitor.club_text && (
              <span
                className="inline-flex max-w-[180px] items-center rounded-full bg-light-gray/70 px-2 py-0.5 text-[10px] font-medium text-charcoal"
                title={competitor.club_text}
              >
                <span className="truncate">{competitor.club_text}</span>
              </span>
            )}
            {competitor.sex && (
              <span className="inline-flex items-center rounded-full bg-light-gray/70 px-2 py-0.5 text-[10px] font-semibold text-mid-gray">
                {competitor.sex}
              </span>
            )}
            {competitor.seasons.map((season) => (
              <span
                key={season}
                className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700"
              >
                <Calendar size={10} aria-hidden="true" />
                {season}
              </span>
            ))}
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
              <TrophyIcon size={10} aria-hidden="true" />
              {competitor.results_count} resultado
              {competitor.results_count === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        {showUnlinkMenu && (
          <div className="relative shrink-0">
            <button
              type="button"
              aria-label="Más acciones"
              aria-expanded={menuOpen}
              aria-haspopup="menu"
              data-testid={`competitor-${competitor.id}-overflow`}
              onClick={() => setMenuOpen((v) => !v)}
              onBlur={() => setTimeout(() => setMenuOpen(false), 120)}
              className="rounded-md p-1 text-mid-gray transition-colors hover:bg-light-gray focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
            >
              <MoreVertical size={14} aria-hidden="true" />
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-full z-30 mt-1 min-w-[180px] rounded-lg bg-white py-1 shadow-lg ring-1 ring-light-gray"
                data-testid={`competitor-${competitor.id}-menu`}
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    onUnlink(competitor);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-red-700 transition-colors hover:bg-red-50"
                >
                  <Unlink size={12} aria-hidden="true" />
                  Desvincular
                </button>
              </div>
            )}
          </div>
        )}
      </header>

      {/* Sugerencias */}
      {competitor.suggestions.length > 0 ? (
        <section
          aria-label="Sugerencias de atletas"
          className="grid gap-2 sm:grid-cols-3"
        >
          {competitor.suggestions.map((s, idx) => (
            <SuggestionCard
              key={s.athlete_id}
              suggestion={s}
              testId={`competitor-${competitor.id}-suggestion-${idx}`}
              isLinking={isLinkingThis && linkingAthleteId === s.athlete_id}
              onLink={(athleteId) => onLink(competitor.id, athleteId, competitor)}
            />
          ))}
        </section>
      ) : (
        <p className="rounded-lg bg-light-gray/40 px-3 py-2 text-xs text-mid-gray">
          Sin sugerencias automáticas. Usa el buscador manual.
        </p>
      )}

      {/* Buscador manual */}
      <div className="space-y-2 border-t border-[rgba(34,42,53,0.06)] pt-3">
        {!showManual ? (
          <button
            type="button"
            data-testid={`competitor-${competitor.id}-manual-btn`}
            onClick={() => setShowManual(true)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-700 transition-colors hover:text-blue-800"
          >
            <Search size={12} aria-hidden="true" />
            Buscar otro atleta
          </button>
        ) : (
          <div className="space-y-2">
            <AthleteCombobox
              value={manualAthleteId}
              onChange={setManualAthleteId}
              placeholder="Selecciona un atleta del club"
              data-testid={`competitor-${competitor.id}-manual-combobox`}
              label="Atleta manual"
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={manualAthleteId == null || isLinkingThis}
                data-testid={`competitor-${competitor.id}-manual-confirm`}
                onClick={() => {
                  if (manualAthleteId != null) {
                    onLink(competitor.id, manualAthleteId, competitor);
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-lg bg-charcoal px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLinkingThis ? (
                  <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                ) : (
                  <Link2 size={12} aria-hidden="true" />
                )}
                Enlazar
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowManual(false);
                  setManualAthleteId(null);
                }}
                className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-mid-gray transition-colors hover:bg-light-gray"
              >
                <X size={12} aria-hidden="true" />
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function CompetitorSkeleton() {
  return (
    <div
      className="space-y-3 rounded-xl bg-white p-4"
      data-testid="competitor-skeleton"
      style={{
        boxShadow:
          "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px",
      }}
    >
      <div className="h-4 w-1/2 animate-pulse rounded-md bg-light-gray" />
      <div className="flex gap-2">
        <div className="h-4 w-16 animate-pulse rounded-full bg-light-gray" />
        <div className="h-4 w-20 animate-pulse rounded-full bg-light-gray" />
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg bg-light-gray/60"
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toast banner (sin librería externa)
// ---------------------------------------------------------------------------

type ToastVariant = "success" | "error" | "info";

interface ToastState {
  variant: ToastVariant;
  message: string;
}

function ToastBanner({
  toast,
  onDismiss,
}: {
  toast: ToastState | null;
  onDismiss: () => void;
}) {
  if (!toast) return null;
  const palette =
    toast.variant === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : toast.variant === "error"
        ? "border-red-200 bg-red-50 text-red-800"
        : "border-blue-200 bg-blue-50 text-blue-800";
  const Icon =
    toast.variant === "success"
      ? CheckCircle2
      : toast.variant === "error"
        ? AlertTriangle
        : Link2;
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid={`toast-${toast.variant}`}
      className={cn(
        "flex items-start gap-2 rounded-xl border px-4 py-3 text-sm",
        palette,
      )}
    >
      <Icon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
      <span className="flex-1">{toast.message}</span>
      <button
        type="button"
        aria-label="Cerrar notificación"
        onClick={onDismiss}
        className="shrink-0 rounded p-0.5 transition-colors hover:bg-black/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}

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
  const [toast, setToast] = useState<ToastState | null>(null);
  const showToast = (variant: ToastVariant, message: string) => {
    setToast({ variant, message });
    setTimeout(() => setToast(null), 6_000);
  };

  // Dialog de confirmación para unlink
  const [unlinkTarget, setUnlinkTarget] =
    useState<UnlinkedCompetitorItem | null>(null);

  // Estado local para tracking del athleteId en flight (mostrar spinner por suggestion)
  const [linkingAthleteId, setLinkingAthleteId] = useState<number | null>(null);

  // Query + mutations
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
  const linkMutation = useLinkCompetitor();
  const unlinkMutation = useUnlinkCompetitor();

  // Notificar al padre el conteo total (para badge en tab)
  const total = query.data?.total ?? 0;
  useEffect(() => {
    onUnlinkedCountChange?.(total);
  }, [total, onUnlinkedCountChange]);

  // -----------------------------------------------------------------------
  // Handlers
  // -----------------------------------------------------------------------

  const handleLink = (
    competitorId: number,
    athleteId: number,
    competitor: UnlinkedCompetitorItem,
  ) => {
    setLinkingAthleteId(athleteId);
    linkMutation.mutate(
      { competitorId, athleteId },
      {
        onSuccess: (data: CompetitorLinkResponse) => {
          setLinkingAthleteId(null);
          // Nombre del athlete: lo resolvemos por sugerencia para evitar fetch extra
          const suggestion = competitor.suggestions.find(
            (s) => s.athlete_id === athleteId,
          );
          const athleteName = suggestion?.full_name ?? `Atleta #${athleteId}`;
          if (data.already_linked) {
            showToast("info", "Ya estaba enlazado, sin cambios.");
          } else {
            showToast(
              "success",
              `Enlazado: ${data.results_propagated} resultado${data.results_propagated === 1 ? "" : "s"} asociado${data.results_propagated === 1 ? "" : "s"} a ${athleteName}.`,
            );
          }
        },
        onError: (err) => {
          setLinkingAthleteId(null);
          showToast("error", getCompetitorErrorMessage(err));
        },
      },
    );
  };

  const handleUnlinkConfirm = () => {
    if (!unlinkTarget) return;
    const target = unlinkTarget;
    unlinkMutation.mutate(
      { competitorId: target.id },
      {
        onSuccess: (data) => {
          setUnlinkTarget(null);
          showToast(
            "info",
            data.was_linked
              ? `Desvinculado: ${data.results_propagated} resultado${data.results_propagated === 1 ? "" : "s"} sin atleta asociado.`
              : "El competidor no estaba enlazado.",
          );
        },
        onError: (err) => {
          setUnlinkTarget(null);
          showToast("error", getCompetitorErrorMessage(err));
        },
      },
    );
  };

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

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
            <h2
              id="unlinked-competitors-heading"
              className="text-sm text-charcoal"
              style={{
                fontFamily: "'Cal Sans', system-ui, sans-serif",
                fontWeight: 600,
              }}
            >
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
            className="rounded-lg bg-white px-2 py-1.5 text-xs text-charcoal outline-none focus:ring-2 focus:ring-blue-500/40"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
      <ToastBanner toast={toast} onDismiss={() => setToast(null)} />

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
          <p
            className="text-sm text-charcoal"
            style={{
              fontFamily: "'Cal Sans', system-ui, sans-serif",
              fontWeight: 600,
            }}
          >
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
              onClick={handleUnlinkConfirm}
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
