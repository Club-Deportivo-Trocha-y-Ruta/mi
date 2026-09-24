/**
 * ChampionshipReadingCard — lectura de un campeonato (copa≠campeonato,
 * feature 039, `research.md` D5).
 *
 * Un campeonato es una carrera suelta con su propio pelotón: no hay
 * "tendencia" que graficar (INV-2, un único evento por grupo), así que se
 * lee como tarjeta de estadísticas en lugar de una línea de un solo punto
 * (dataviz `choosing-a-form.md`: "single current value → stat tile").
 *
 * Las etiquetas (`Posición` / `Parrilla` / `Brecha vs. mediana` /
 * `Brecha vs. 1.ª posición` / `Percentil`) son la copia fija de
 * `research.md` D13, actualizada 2026-09-23 (glosario "Brecha vs. mediana"
 * / "Brecha vs. 1.ª posición" / "Parrilla" — antes "Pelotón").
 *
 * Fix B-2/F-1 (integration-review.md) — `EvolutionPoint` ahora trae
 * `position`/`gap_pct`/`gap_to_median_pct` crudos (data-model.md §5,
 * `contracts/evolution-api.md`), poblados para *cualquier* `metric`, no
 * solo cuando el selector coincide. Las tarjetas se leen siempre desde el
 * punto mismo — ya no dependen de la métrica activa del selector.
 *
 * Audiencia (2026-09-23, `audience="coach"|"family"`, default "coach"):
 * «Brecha vs. 1.ª posición» (brecha a la ganadora) es SOLO para coach — la
 * familia nunca la ve, en ningún lado (principio de salvaguardas
 * psicológicas). «Brecha vs. mediana» es la métrica comparable y se
 * muestra para ambas audiencias.
 *
 * Feature 045: la tarjeta enlaza a su competencia (FR-017) — coach al
 * detalle interno, familia a su vista de resultados — con un destino táctil
 * de 48 px (FR-063). Un valor ausente se lee «sin dato», nunca «—»
 * (US2/AC3, FR-020); un DNF/DNS/DSQ se lee «No completó la prueba».
 * Requiere un `Router` en el árbol.
 */
import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";
import { raceEventHref } from "@/lib/raceEventHref";
import { SIN_DATO, formatGapPct } from "@/lib/raceHistoryFormat";
import type {
  ComparisonGroupOption,
  EvolutionPoint,
} from "@/types/athleteRaceAnalysis.types";

interface ChampionshipReadingCardProps {
  point: EvolutionPoint;
  /** Solo se lee `label` — así «Progresión» (que parte de puntos del
   * historial, sin `ComparisonGroupOption` completo) también la usa. */
  group: Pick<ComparisonGroupOption, "label">;
  audience?: "coach" | "family";
}

interface StatTile {
  label: string;
  value: string;
}

export function ChampionshipReadingCard({
  point,
  group,
  audience = "coach",
}: ChampionshipReadingCardProps) {
  const notFinished =
    point.value === null &&
    (point.position === null || point.position === undefined);

  const positionValue =
    point.position !== undefined && point.position !== null
      ? `P${point.position}`
      : SIN_DATO;
  const pelotonValue =
    point.field_size !== undefined && point.field_size !== null
      ? `${point.field_size} corredores`
      : SIN_DATO;
  const percentileValue =
    point.percentile !== undefined && point.percentile !== null
      ? String(Math.round(point.percentile))
      : SIN_DATO;
  const gapToMedianValue = formatGapPct(point.gap_to_median_pct ?? null);
  // Los puntos de familia no traen `gap_pct` (el tile es coach-only).
  const gapToWinnerValue = formatGapPct(
    "gap_pct" in point ? (point.gap_pct ?? null) : null,
  );

  const tiles: StatTile[] = [
    { label: "Posición", value: positionValue },
    { label: "Parrilla", value: pelotonValue },
    { label: "Brecha vs. mediana", value: gapToMedianValue },
    ...(audience === "coach"
      ? [{ label: "Brecha vs. 1.ª posición", value: gapToWinnerValue }]
      : []),
    { label: "Percentil", value: percentileValue },
  ];

  return (
    <div
      className={cn("rounded-card bg-surface-raised p-4 space-y-3", "shadow-card ring-1 ring-hairline")}
      data-testid="championship-reading-card"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="font-display text-sm text-charcoal">{group.label}</h4>
          <p className="mt-0.5 text-xs text-mid-gray">{point.event_date}</p>
        </div>
        <Link
          to={raceEventHref(audience, point.event_id)}
          aria-label={`Ver competencia: ${group.label}`}
          data-testid="championship-reading-card-link"
          className={cn(
            "-mr-2 -mt-1 flex min-h-12 min-w-12 shrink-0 items-center justify-end gap-1 rounded-lg px-2",
            "text-xs font-medium text-charcoal underline underline-offset-2 transition-colors hover:bg-light-gray/50",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
          )}
        >
          Ver competencia
          <ChevronRight size={14} aria-hidden="true" />
        </Link>
      </header>

      {notFinished ? (
        <p className="text-sm text-charcoal">No completó la prueba.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {tiles.map((tile) => (
            <div
              key={tile.label}
              className="rounded-lg bg-light-gray/30 px-3 py-2"
            >
              <dt className="text-[11px] uppercase tracking-wide text-mid-gray">
                {tile.label}
              </dt>
              <dd className="mt-0.5 text-sm font-semibold text-charcoal">
                {tile.value}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <p className="text-xs text-mid-gray">
        Un campeonato reúne un pelotón distinto al de la copa: se lee por
        separado y no se compara con las válidas.
      </p>
    </div>
  );
}
