/**
 * ChampionshipReadingCard — lectura de un campeonato (copa≠campeonato,
 * feature 039, `research.md` D5).
 *
 * Un campeonato es una carrera suelta con su propio pelotón: no hay
 * "tendencia" que graficar (INV-2, un único evento por grupo), así que se
 * lee como tarjeta de estadísticas en lugar de una línea de un solo punto
 * (dataviz `choosing-a-form.md`: "single current value → stat tile").
 *
 * Las cuatro etiquetas (`Posición` / `Pelotón` / `Gap al P1` / `Percentil`)
 * son la copia fija de `research.md` D13.
 *
 * Fix B-2/F-1 (integration-review.md) — `EvolutionPoint` ahora trae
 * `position`/`gap_pct` crudos (data-model.md §5, `contracts/
 * evolution-api.md`), poblados para *cualquier* `metric`, no solo cuando el
 * selector está en `ranking`/`podium_gap_ms`. Las cuatro tarjetas se leen
 * siempre desde el punto mismo — ya no dependen de la métrica activa del
 * selector (antes `Posición`/`Gap al P1` quedaban en "—" con la métrica
 * default, leyéndose como dato faltante en una superficie P2 del coach).
 */
import { cn } from "@/lib/utils";
import type {
  ComparisonGroupOption,
  EvolutionPoint,
} from "@/types/athleteRaceAnalysis.types";

interface ChampionshipReadingCardProps {
  point: EvolutionPoint;
  group: ComparisonGroupOption;
}

interface StatTile {
  label: string;
  value: string;
}

export function ChampionshipReadingCard({
  point,
  group,
}: ChampionshipReadingCardProps) {
  const notFinished =
    point.value === null &&
    (point.position === null || point.position === undefined);

  const positionValue =
    point.position !== undefined && point.position !== null
      ? `P${point.position}`
      : "—";
  const gapValue =
    point.gap_pct !== undefined && point.gap_pct !== null
      ? point.gap_pct === 0
        ? "0.0 %"
        : `+${point.gap_pct.toFixed(1)} %`
      : "—";
  const pelotonValue =
    point.field_size !== undefined && point.field_size !== null
      ? `${point.field_size} corredores`
      : "—";
  const percentileValue =
    point.percentile !== undefined && point.percentile !== null
      ? String(Math.round(point.percentile))
      : "—";

  const tiles: StatTile[] = [
    { label: "Posición", value: positionValue },
    { label: "Pelotón", value: pelotonValue },
    { label: "Gap al P1", value: gapValue },
    { label: "Percentil", value: percentileValue },
  ];

  return (
    <div
      className={cn("rounded-xl bg-white p-4 space-y-3", "shadow-card")}
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
