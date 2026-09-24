/**
 * HistoryProgressionCard — tarjeta de progresión histórica entre
 * temporadas de un atleta (feature 044, US6/US7).
 *
 * `audience` decide el matiz de texto — nunca el dato mostrado (ver
 * `HistoryTable`'s nota de cambio de categoría para familias, el
 * explicador familiar de percentil/brecha, el subtítulo "tu hijo o hija"
 * vs. "el atleta" y el tag corto exclusivo del coach en
 * `CategoryChangesList`, todos T083) — la Fase 8 (US6) monta esta tarjeta
 * únicamente con `audience="coach"` desde `AthleteDetailPage.tsx`; la
 * Fase 9 (US7) la reutiliza con `audience="family"` en la página del
 * padre.
 *
 * "Texto primero" (SC-008 — el coach debe poder responder en menos de un
 * minuto si el atleta mejoró y dónde cambió de categoría, desde una sola
 * vista): las chips de temporada, los últimos resultados y los cambios de
 * categoría se renderizan como DOM plano de inmediato — no dependen de
 * recharts. Solo `HistoryChart` se carga lazy (mismo patrón que
 * `CourseSummary`/`EvolutionChart`), así el chunk de recharts no pesa la
 * primera pintura en una conexión 3G.
 */
import { lazy, Suspense } from "react";
import { TrendingUp } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { formatFieldSize, formatRaceDateShort } from "@/lib/raceHistoryFormat";
import { useAthleteRaceHistory } from "@/hooks/race/useAthleteRaceHistory";
import {
  NON_FINISHER_STATUSES,
  RACE_HISTORY_STATUS_LABELS,
} from "@/types/raceHistory.types";
import type { RaceHistoryPoint } from "@/types/raceHistory.types";
import { CaveatsNote } from "@/components/race/history/CaveatsNote";
import { HistoryTable } from "@/components/race/history/HistoryTable";
import { SeasonCompletionChips } from "@/components/race/history/SeasonCompletionChips";

const HistoryChart = lazy(() =>
  import("@/components/race/history/HistoryChart").then((m) => ({
    default: m.HistoryChart,
  })),
);

export type HistoryAudience = "coach" | "family";

export interface HistoryProgressionCardProps {
  athleteId: number;
  audience?: HistoryAudience;
  className?: string;
}

const CAVEATS_NOTE_ID = "history-caveats-note-anchor";

export function summarizeResult(p: RaceHistoryPoint): string {
  if (NON_FINISHER_STATUSES.has(p.status)) {
    return RACE_HISTORY_STATUS_LABELS[p.status];
  }
  if (p.position != null) {
    return `${p.position}° de ${formatFieldSize(p.field_size)}`;
  }
  return "sin dato";
}

/** Etiqueta corta del cambio de categoría para el coach (T083, FR-042) —
 * `"promotion"` es el único caso respaldado por el backend para afirmar un
 * ascenso; cualquier otro valor se queda en la etiqueta neutral. Solo
 * `audience="coach"`: la familia ya recibe la explicación completa dentro
 * de `HistoryTable`'s aviso por grupo, un tag adicional acá sería ruido. */
function categoryChangeTagLabel(kind: RaceHistoryPoint["category_change_kind"]): string {
  return kind === "promotion" ? "Subió de categoría" : "Cambió de categoría";
}

export function CategoryChangesList({
  points,
  audience,
}: {
  points: RaceHistoryPoint[];
  audience: HistoryAudience;
}) {
  const changes = points.filter((p) => p.category_changed);
  if (changes.length === 0) return null;
  return (
    <div data-testid="history-category-changes">
      <h4 className="text-xs font-semibold text-charcoal">
        Cambios de categoría
      </h4>
      <ul className="mt-1 space-y-1 text-xs text-mid-gray">
        {changes.map((p) => (
          <li key={p.event_id}>
            {p.previous_category_label ?? "?"} → {p.category_label} — {p.label}{" "}
            ({formatRaceDateShort(p.event_date)})
            {audience === "coach" && (
              <span
                data-testid={`history-category-change-tag-${p.event_id}`}
                className="ml-1.5 inline-flex items-center rounded-full bg-light-gray px-1.5 py-0.5 text-[10px] font-medium text-charcoal"
              >
                {categoryChangeTagLabel(p.category_change_kind)}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HistoryProgressionCard({
  athleteId,
  audience = "coach",
  className,
}: HistoryProgressionCardProps) {
  const query = useAthleteRaceHistory(athleteId);

  return (
    <section
      className={cn("rounded-card bg-surface-raised p-5 shadow-card ring-1 ring-hairline space-y-4", className)}
      aria-label="Progresión histórica entre temporadas"
      data-testid="history-progression-card"
    >
      <header>
        <h3
          className="font-display flex items-center gap-2 text-sm text-charcoal"
          style={{ letterSpacing: "0.2px" }}
        >
          <TrendingUp size={16} aria-hidden="true" />
          Progresión histórica
        </h3>
        <p className="mt-0.5 text-xs text-mid-gray">
          {/* T083 (ux-review.md, MINOR) — "el atleta" queda para el coach;
              la familia ya lee "tu hijo o hija" en el resto de la vista
              (ej. `history-family-notice.md`). Sin enhebrar el nombre real
              del menor — instrucción explícita del líder. */}
          {audience === "family"
            ? "Cómo ha cambiado tu hijo o hija entre temporadas de Copa Valle."
            : "Cómo ha cambiado el atleta entre temporadas de Copa Valle."}
        </p>
      </header>

      {query.isLoading && (
        <div role="status" aria-busy="true" aria-label="Cargando progresión histórica">
          <Skeleton className="h-24 w-full rounded-lg" />
        </div>
      )}

      {query.isError && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
        >
          No pudimos cargar la progresión histórica de este atleta.
        </div>
      )}

      {!query.isLoading && !query.isError && query.data && (
        query.data.points.length === 0 ? (
          <p
            className="rounded-lg bg-light-gray/30 p-4 text-center text-sm text-mid-gray"
            data-testid="history-empty"
          >
            Todavía no hay carreras históricas para comparar entre temporadas.
          </p>
        ) : (
          <>
            <SeasonCompletionChips seasons={query.data.seasons} />

            <div>
              <h4 className="text-xs font-semibold text-charcoal">
                Últimos resultados
              </h4>
              <ul
                className="mt-1 space-y-0.5 text-sm text-charcoal"
                aria-label="Últimos resultados"
                data-testid="history-latest-three"
              >
                {[...query.data.points]
                  .sort((a, b) => b.event_date.localeCompare(a.event_date))
                  .slice(0, 3)
                  .map((p) => (
                    <li key={p.event_id}>
                      {p.label} ({formatRaceDateShort(p.event_date)}) —{" "}
                      {summarizeResult(p)}
                    </li>
                  ))}
              </ul>
            </div>

            <CategoryChangesList points={query.data.points} audience={audience} />

            <div aria-describedby={CAVEATS_NOTE_ID}>
              <Suspense fallback={<Skeleton className="h-72 w-full rounded-lg" />}>
                <HistoryChart points={query.data.points} />
              </Suspense>
            </div>

            <HistoryTable points={query.data.points} audience={audience} />

            <CaveatsNote id={CAVEATS_NOTE_ID} caveats={query.data.caveats} />
          </>
        )
      )}
    </section>
  );
}
