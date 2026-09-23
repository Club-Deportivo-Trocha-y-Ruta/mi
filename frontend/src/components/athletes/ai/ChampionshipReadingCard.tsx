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
 */
import { cn } from "@/lib/utils";
import { formatGapPct } from "@/lib/raceHistoryFormat";
import type {
  ComparisonGroupOption,
  EvolutionPoint,
} from "@/types/athleteRaceAnalysis.types";

interface ChampionshipReadingCardProps {
  point: EvolutionPoint;
  group: ComparisonGroupOption;
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
      : "—";
  const pelotonValue =
    point.field_size !== undefined && point.field_size !== null
      ? `${point.field_size} corredores`
      : "—";
  const percentileValue =
    point.percentile !== undefined && point.percentile !== null
      ? String(Math.round(point.percentile))
      : "—";
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
      <header>
        <h4 className="font-display text-sm text-charcoal">{group.label}</h4>
        <p className="mt-0.5 text-xs text-mid-gray">{point.event_date}</p>
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
