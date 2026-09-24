/**
 * PendingAnalysesPanel — lista de análisis IA pendientes del coach dentro de
 * «Temporada» (feature 045, US5, T057).
 *
 * Es el destino de las filas «Análisis por aprobar» y «Insights IA
 * desactualizados» del Home (`?analisis=por-aprobar|desactualizados`). Muestra
 * EXACTAMENTE los ítems que contó esa fila (SC-005): la lista viene del mismo
 * `GET /api/race-analysis/pending-analyses` que comparte especificación con el
 * conteo del resumen, y por eso NO se acota por temporada (una corrección de
 * PDF de la temporada pasada también cuenta en el Home).
 *
 * Acciones por ítem:
 *   - Abrir el análisis → `/athletes/:id?tab=races&view=analisis[&insight=]`.
 *     `/athletes/:id` es coach-only: para admin no se ofrece.
 *   - Re-ejecutar (solo desactualizados), según `kind`:
 *       · `season_summary` (con `season`) → `POST …/season-summary` de esa
 *         temporada (`RerunSeasonSummaryButton`). Nunca el lanzamiento por
 *         `{season}` de las válidas: correría un análisis por válida de toda la
 *         temporada, que no es lo mismo.
 *       · cualquier otro con competencia (`event_id`) → lanzamiento por válida
 *         existente (`RerunAnalysisButton`).
 *       · sin competencia ni tipo conocido (o resumen sin temporada) → solo
 *         abrir y descartar.
 *   - Descartar aviso (solo desactualizados) → `POST …/dismiss-stale`, con
 *     confirmación: el análisis se conserva tal como está.
 *
 * Estados: cargando (esqueleto), error (con Reintentar), vacío y lista.
 *
 * Privacidad: `athlete_ref` es el nombre que la UI del coach ya muestra; se
 * renderiza tal cual y no se escribe en ningún log ni query key.
 */
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, X } from "lucide-react";

import { AIBudgetHint } from "@/components/ai/AIBudgetHint";
import {
  RerunAnalysisButton,
  RerunSeasonSummaryButton,
} from "@/components/competitions/season/RerunAnalysisButton";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAIStatus } from "@/hooks/ai/useAIStatus";
import { useDismissStaleRun, usePendingAnalyses } from "@/hooks/race/usePendingAnalyses";
import { formatDate } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type { PendingAnalysis, PendingAnalysisState } from "@/types/racePendingAnalyses.types";

/** Valores de `?analisis=` (contracts/ui-routes.md). */
export type PendingAnalysesMode = "por-aprobar" | "desactualizados";

const MODE_STATE: Record<PendingAnalysesMode, PendingAnalysisState> = {
  "por-aprobar": "awaiting_approval",
  desactualizados: "stale",
};

const MODES: ReadonlyArray<{ mode: PendingAnalysesMode; label: string }> = [
  { mode: "por-aprobar", label: "Por aprobar" },
  { mode: "desactualizados", label: "Desactualizados" },
];

const MODE_COPY: Record<PendingAnalysesMode, { hint: string; empty: string }> = {
  "por-aprobar": {
    hint: "Borradores que esperan tu revisión. Al aprobar, la familia podrá verlo en la app. No se envía correo.",
    empty: "No hay análisis por aprobar.",
  },
  desactualizados: {
    hint: "Análisis cuyos resultados cambiaron después de generarse. Puedes re-ejecutarlos o mantenerlos tal como están.",
    empty: "No hay análisis desactualizados.",
  },
};

/** `?analisis=` → modo, o `null` si falta o no se reconoce (nunca un error). */
export function parsePendingAnalysesMode(raw: string | null): PendingAnalysesMode | null {
  return raw === "por-aprobar" || raw === "desactualizados" ? raw : null;
}

/** Enlace profundo al análisis en «Carreras › Análisis IA» del deportista. */
function analysisPath(item: PendingAnalysis): string {
  const base = `/athletes/${item.athlete_id}?tab=races&view=analisis`;
  return item.insight_id != null ? `${base}&insight=${item.insight_id}` : base;
}

function isConflict(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    (err as { response?: { status?: number } }).response?.status === 409
  );
}

// ---------------------------------------------------------------------------
// Fila
// ---------------------------------------------------------------------------

function PendingAnalysisRow({ item, canOpen }: { item: PendingAnalysis; canOpen: boolean }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const dismiss = useDismissStaleRun();
  const isStale = item.state === "stale";
  // Un resumen de temporada se re-ejecuta por su temporada exacta; el resto,
  // por la competencia que lo ancla. Sin ninguno de los dos, no hay re-ejecución.
  const isSeasonSummary = item.kind === "season_summary";
  const rerunSeason = isStale && isSeasonSummary && item.season != null ? item.season : null;
  const rerunEventId = isStale && !isSeasonSummary ? item.event_id : null;

  const dismissError = dismiss.isError
    ? isConflict(dismiss.error)
      ? "Este análisis ya no está desactualizado."
      : "No se pudo descartar el aviso. Intenta de nuevo."
    : undefined;

  return (
    <li
      className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between"
      data-testid={`pending-analysis-${item.run_id}`}
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-charcoal">{item.athlete_ref}</p>
        <p className="text-xs text-mid-gray">
          {item.event_label} · Actualizado {formatDate(item.updated_at)}
        </p>
      </div>

      <div className="flex flex-wrap items-start gap-2">
        {canOpen && (
          <Link
            to={analysisPath(item)}
            className={cn(buttonVariants({ variant: "outline" }), "min-h-12")}
            aria-label={`${isStale ? "Abrir" : "Revisar"} el análisis de ${item.athlete_ref}`}
          >
            <ExternalLink size={16} aria-hidden="true" />
            {isStale ? "Abrir análisis" : "Revisar y aprobar"}
          </Link>
        )}

        {rerunSeason !== null && (
          <RerunSeasonSummaryButton
            athleteId={item.athlete_id}
            season={rerunSeason}
            displayName={item.athlete_ref}
          />
        )}

        {rerunEventId != null && (
          <RerunAnalysisButton
            athleteId={item.athlete_id}
            eventId={rerunEventId}
            season={item.season}
            displayName={item.athlete_ref}
          />
        )}

        {isStale && (
          <>
            <Button
              type="button"
              variant="ghost"
              className="min-h-12"
              onClick={() => {
                dismiss.reset();
                setConfirmOpen(true);
              }}
              aria-label={`Descartar el aviso de análisis desactualizado de ${item.athlete_ref}`}
              data-testid={`pending-dismiss-btn-${item.run_id}`}
            >
              Descartar aviso
            </Button>
            <ConfirmDialog
              open={confirmOpen}
              title="Descartar aviso"
              description="El análisis se conserva tal como está y deja de aparecer como desactualizado. No se vuelve a generar."
              confirmLabel="Descartar aviso"
              isPending={dismiss.isPending}
              errorMessage={dismissError}
              onCancel={() => {
                if (!dismiss.isPending) setConfirmOpen(false);
              }}
              onConfirm={() =>
                dismiss.mutate(
                  { runId: item.run_id, athleteId: item.athlete_id },
                  { onSuccess: () => setConfirmOpen(false) },
                )
              }
            />
          </>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export interface PendingAnalysesPanelProps {
  mode: PendingAnalysesMode;
  onModeChange: (mode: PendingAnalysesMode) => void;
  onClose: () => void;
}

export function PendingAnalysesPanel({ mode, onModeChange, onClose }: PendingAnalysesPanelProps) {
  const headingId = useId();
  const role = useAuthStore((s) => s.user?.role);
  const canOpen = role === UserRole.coach;

  const query = usePendingAnalyses({ state: MODE_STATE[mode] });
  const aiStatus = useAIStatus({ enabled: mode === "desactualizados" });
  const copy = MODE_COPY[mode];
  const items = query.data ?? [];

  return (
    <section
      aria-labelledby={headingId}
      className="space-y-4 rounded-card bg-surface-raised p-4 shadow-card ring-1 ring-hairline"
      data-testid="pending-analyses-panel"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 id={headingId} className="text-[15px] font-semibold text-charcoal">
            Análisis pendientes
          </h2>
          <p className="text-sm text-mid-gray">{copy.hint}</p>
        </div>
        <Button
          type="button"
          variant="ghost"
          className="min-h-12 shrink-0"
          onClick={onClose}
          data-testid="pending-analyses-close"
        >
          <X size={16} aria-hidden="true" />
          Ocultar
        </Button>
      </div>

      <div role="group" aria-label="Tipo de análisis pendiente" className="flex flex-wrap gap-2">
        {MODES.map((option) => {
          const active = option.mode === mode;
          return (
            <Button
              key={option.mode}
              type="button"
              variant={active ? "secondary" : "outline"}
              className={cn("min-h-12", active && "ring-2 ring-primary/40")}
              aria-pressed={active}
              onClick={() => onModeChange(option.mode)}
              data-testid={`pending-mode-${option.mode}`}
            >
              {option.label}
            </Button>
          );
        })}
      </div>

      {mode === "desactualizados" && <AIBudgetHint status={aiStatus.data} />}

      {query.isLoading && (
        <div
          className="space-y-2"
          role="status"
          aria-busy="true"
          aria-label="Cargando análisis pendientes"
          data-testid="pending-analyses-loading"
        >
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      )}

      {query.isError && !query.isLoading && (
        <div
          className="flex flex-col items-start gap-3"
          role="alert"
          data-testid="pending-analyses-error"
        >
          <p className="text-sm text-mid-gray">
            No se pudieron cargar los análisis pendientes. Intenta de nuevo.
          </p>
          <Button
            type="button"
            variant="outline"
            className="min-h-12"
            onClick={() => void query.refetch()}
          >
            Reintentar
          </Button>
        </div>
      )}

      {!query.isLoading && !query.isError && items.length === 0 && (
        <p
          className="rounded-xl bg-light-gray/60 px-4 py-6 text-center text-sm text-mid-gray"
          data-testid="pending-analyses-empty"
        >
          {copy.empty}
        </p>
      )}

      {!query.isLoading && !query.isError && items.length > 0 && (
        <ul className="divide-y divide-light-gray" data-testid="pending-analyses-list">
          {items.map((item) => (
            <PendingAnalysisRow key={item.run_id} item={item} canOpen={canOpen} />
          ))}
        </ul>
      )}
    </section>
  );
}
