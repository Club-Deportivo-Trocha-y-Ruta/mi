/**
 * HistoryTable — alternativa textual de `HistoryChart`, agrupada
 * temporada → categoría (feature 044, US6/US7, `contracts/ui-history.md` §1).
 *
 * Cada grupo es su propio `<tbody>`: ninguna fila ni línea visual une dos
 * grupos (una fila de Infantil B 2024 nunca comparte borde/continuidad con
 * la siguiente de Prejuvenil A 2025 — son pelotones distintos, no una
 * misma serie continua). "sin dato" en cualquier campo que llegue `null`
 * de la API — nunca un guion ni un cero.
 *
 * Variante familia (`audience="family"`): al inicio del grupo que arranca
 * con un cambio de categoría, un aviso sin lenguaje comparativo sobre el
 * hijo/a — nunca "bajó" o "empeoró", solo el hecho y la expectativa normal.
 */
import { cn } from "@/lib/utils";
import {
  formatFieldSize,
  formatGapPct,
  formatPercentile,
  formatPosition,
  formatRaceDateShort,
  formatSpeedKmh,
} from "@/lib/raceHistoryFormat";
import {
  NON_FINISHER_STATUSES,
  RACE_HISTORY_STATUS_LABELS,
} from "@/types/raceHistory.types";
import type { RaceHistoryPoint } from "@/types/raceHistory.types";

export interface HistoryTableProps {
  points: RaceHistoryPoint[];
  audience?: "coach" | "family";
  className?: string;
}

interface TableGroup {
  key: string;
  season: number;
  categoryLabel: string;
  categoryChanged: boolean;
  previousCategoryLabel: string | null;
  rows: RaceHistoryPoint[];
}

/** Agrupa por temporada → categoría, preservando el orden cronológico ya
 * resuelto por el backend (`points` viene ordenado por `event_date`). Un
 * nuevo grupo arranca en cada cambio de temporada O de categoría — así una
 * categoría repetida en dos temporadas distintas (p. ej. se queda un año
 * más en la misma) sigue siendo dos grupos, nunca uno solo. */
function groupPoints(points: RaceHistoryPoint[]): TableGroup[] {
  const groups: TableGroup[] = [];
  for (const p of points) {
    const last = groups[groups.length - 1];
    const startsNewGroup =
      !last || last.season !== p.season || last.categoryLabel !== p.category_label;
    if (startsNewGroup) {
      groups.push({
        key: `${p.season}-${p.category_code}-${groups.length}`,
        season: p.season,
        categoryLabel: p.category_label,
        categoryChanged: p.category_changed,
        previousCategoryLabel: p.previous_category_label,
        rows: [p],
      });
    } else {
      last.rows.push(p);
    }
  }
  return groups;
}

function positionCell(point: RaceHistoryPoint): string {
  if (point.position !== null) return formatPosition(point.position);
  if (NON_FINISHER_STATUSES.has(point.status)) {
    return RACE_HISTORY_STATUS_LABELS[point.status];
  }
  return formatPosition(point.position);
}

export function HistoryTable({
  points,
  audience = "coach",
  className,
}: HistoryTableProps) {
  if (points.length === 0) return null;
  const groups = groupPoints(points);

  return (
    <table
      className={cn("w-full text-sm", className)}
      data-testid="history-table"
    >
      <caption className="sr-only">
        Progresión histórica entre temporadas — vista de tabla
      </caption>
      <thead>
        <tr className="text-left text-xs uppercase tracking-wide text-mid-gray">
          <th className="px-3 py-2 font-medium">Fecha</th>
          <th className="px-3 py-2 font-medium">Válida</th>
          <th className="px-3 py-2 font-medium">Puesto</th>
          <th className="px-3 py-2 font-medium">Percentil</th>
          <th className="px-3 py-2 font-medium">Parrilla</th>
          <th className="px-3 py-2 font-medium">Brecha</th>
          <th className="px-3 py-2 font-medium">Velocidad</th>
        </tr>
      </thead>
      {groups.map((group) => (
        <tbody
          key={group.key}
          className="border-t border-[rgba(34,42,53,0.08)]"
          data-testid={`history-table-group-${group.key}`}
        >
          <tr className="bg-light-gray/30">
            <th
              colSpan={7}
              scope="rowgroup"
              className="px-3 py-1.5 text-left text-xs font-semibold text-charcoal"
            >
              {group.season} · {group.categoryLabel}
            </th>
          </tr>
          {audience === "family" && group.categoryChanged && (
            <tr>
              <td colSpan={7} className="px-3 py-1.5">
                {/* MAJOR 3 (T077 ux-review.md) — la redacción anterior
                    ("Subió de categoría… es normal que el puesto baje")
                    afirmaba un ascenso y una expectativa de peor
                    desempeño; se reemplaza por un hecho neutral: cambió de
                    categoría, y el puesto de una no se compara con el de
                    la otra porque compite con otro grupo. */}
                <p
                  role="note"
                  className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs text-blue-900"
                  data-testid={`history-family-category-note-${group.key}`}
                >
                  Cambió de categoría (de {group.previousCategoryLabel ?? "—"}{" "}
                  a {group.categoryLabel}). En la nueva categoría compite con
                  otro grupo, así que el puesto no se compara directamente
                  con el anterior.
                </p>
              </td>
            </tr>
          )}
          {group.rows.map((p) => (
            <tr key={p.event_id} className="text-charcoal">
              <td className="px-3 py-1.5">{formatRaceDateShort(p.event_date)}</td>
              <td className="px-3 py-1.5">{p.label}</td>
              <td className="px-3 py-1.5">{positionCell(p)}</td>
              <td className="px-3 py-1.5">{formatPercentile(p.percentile)}</td>
              <td className="px-3 py-1.5">{formatFieldSize(p.field_size)}</td>
              <td className="px-3 py-1.5">{formatGapPct(p.gap_to_median_pct)}</td>
              <td className="px-3 py-1.5">{formatSpeedKmh(p.avg_speed_kmh)}</td>
            </tr>
          ))}
        </tbody>
      ))}
    </table>
  );
}
