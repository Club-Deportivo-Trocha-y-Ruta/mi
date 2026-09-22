/**
 * HistoryTable — alternativa textual de `HistoryChart`, agrupada
 * temporada → categoría (feature 044, US6/US7, `contracts/ui-history.md` §1).
 *
 * Cada grupo es su propia unidad visual: ninguna fila ni línea visual une
 * dos grupos (una fila de Infantil B 2024 nunca comparte borde/continuidad
 * con la siguiente de Prejuvenil A 2025 — son pelotones distintos, no una
 * misma serie continua). "sin dato" en cualquier campo que llegue `null` de
 * la API — nunca un guion ni un cero.
 *
 * Responsive (T083 ux-review.md, BLOCKER — mismo patrón que
 * `AnthropometryHistory.tsx`): `<md` renderiza una lista de tarjetas
 * apiladas (una por resultado, agrupadas por temporada/categoría);
 * `md:` renderiza la tabla completa de 6 columnas (velocidad media retirada
 * 2026-09-22 — "no es un dato relevante" en esta vista cruza-temporadas).
 * Ambas vistas se montan siempre (el toggle es puramente CSS, igual que
 * `AnthropometryHistory`) — los tests que necesiten desambiguar contenido
 * duplicado deben escopear por `history-table` (desktop) o
 * `history-table-mobile`.
 *
 * Variante familia (`audience="family"`):
 *  - Al inicio del grupo que arranca con un cambio de categoría, un aviso
 *    de tono según `category_change_kind` (T083, FR-042): `"promotion"` —
 *    dato respaldado por el backend, sí se explica el porqué ("ahora corre
 *    con deportistas mayores… es normal que el puesto baje al comienzo");
 *    `"other"`/`null` — el dato no sostiene esa afirmación, se queda en el
 *    hecho neutral (T077).
 *  - Un explicador de una línea para "Percentil"/"Brecha a la mediana"
 *    (T083, MAJOR) — la vista coach no lo necesita (vocabulario de uso
 *    diario), la familia sí.
 */
import { cn } from "@/lib/utils";
import {
  formatFieldSize,
  formatGapPct,
  formatPercentile,
  formatPosition,
  formatRaceDateShort,
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
  categoryCode: string;
  categoryChanged: boolean;
  categoryChangeKind: RaceHistoryPoint["category_change_kind"];
  previousCategoryLabel: string | null;
  rows: RaceHistoryPoint[];
}

/** Agrupa por temporada → `category_code` (identidad estable de la
 * categoría, resuelta siempre del catálogo vigente — ver el docstring de
 * ``build_history_points`` en el backend), preservando el orden cronológico
 * ya resuelto por el backend (`points` viene ordenado por `event_date`). Un
 * nuevo grupo arranca en cada cambio de temporada O de categoría — así una
 * categoría repetida en dos temporadas distintas (p. ej. se queda un año
 * más en la misma) sigue siendo dos grupos, nunca uno solo.
 *
 * Bug corregido: agrupar antes por `category_label` (la etiqueta impresa,
 * congelada por válida) partía un mismo grupo en dos cuando el catálogo
 * renombraba la categoría entre válidas de la misma temporada (p. ej.
 * "PREJUVENIL A DAMAS" → "PREJUVENIL A FEMENINO" sin cambiar de categoría
 * real) — ver `category_change_kind`/`category_changed`, que ya usan
 * `category_id` en el backend y por eso nunca se disparan en ese caso.
 * `category_code` es la misma identidad estable expuesta al cliente. */
function groupPoints(points: RaceHistoryPoint[]): TableGroup[] {
  const groups: TableGroup[] = [];
  for (const p of points) {
    const last = groups[groups.length - 1];
    const startsNewGroup =
      !last || last.season !== p.season || last.categoryCode !== p.category_code;
    if (startsNewGroup) {
      groups.push({
        key: `${p.season}-${p.category_code}-${groups.length}`,
        season: p.season,
        categoryCode: p.category_code,
        categoryChanged: p.category_changed,
        categoryChangeKind: p.category_change_kind,
        previousCategoryLabel: p.previous_category_label,
        rows: [p],
      });
    } else {
      last.rows.push(p);
    }
  }
  return groups;
}

/** Etiqueta del encabezado del grupo: la más reciente si todas las filas
 * comparten la misma, o "A / B" (en orden de aparición) si el catálogo se
 * renombró a mitad del grupo — nunca se pierde ninguna de las dos. */
function groupHeadingLabel(group: TableGroup): string {
  const distinct: string[] = [];
  for (const p of group.rows) {
    if (!distinct.includes(p.category_label)) distinct.push(p.category_label);
  }
  return distinct.join(" / ");
}

/** Cuando la etiqueta impresa de una fila no coincide con el encabezado del
 * grupo (renombre a mitad de temporada), se anota junto al nombre de la
 * válida — la fila nunca oculta cuál era su etiqueta real. */
function rowCategoryNote(point: RaceHistoryPoint, headingLabel: string): string | null {
  return point.category_label !== headingLabel ? point.category_label : null;
}

function positionCell(point: RaceHistoryPoint): string {
  if (point.position !== null) return formatPosition(point.position);
  if (NON_FINISHER_STATUSES.has(point.status)) {
    return RACE_HISTORY_STATUS_LABELS[point.status];
  }
  return formatPosition(point.position);
}

/** Texto del aviso familiar de cambio de categoría — T083/FR-042.
 * `"promotion"` es el único caso donde el dato sostiene explicar el porqué;
 * cualquier otro valor se queda en el hecho neutral (T077). */
function familyCategoryChangeNote(group: TableGroup, headingLabel: string): string {
  if (group.categoryChangeKind === "promotion") {
    return "Subió de categoría: ahora corre con deportistas mayores. Es normal que el puesto baje al comienzo.";
  }
  return `Cambió de categoría (de ${group.previousCategoryLabel ?? "—"} a ${headingLabel}). En la nueva categoría compite con otro grupo, así que el puesto no se compara directamente con el anterior.`;
}

/** Explicador de una línea para "Percentil"/"Brecha a la mediana" —
 * T083 MAJOR. Evita "el atleta": el resto de la vista familiar dice
 * "tu hijo o hija" (T083 MINOR), sin enhebrar el nombre real del menor. */
function FamilyMetricsExplainer() {
  return (
    <p
      role="note"
      data-testid="history-family-metrics-explainer"
      className="rounded-lg bg-light-gray/40 px-3 py-2 text-xs text-mid-gray"
    >
      <strong className="font-medium text-charcoal">Percentil:</strong> de
      cada 100 corredores de la categoría de tu hijo o hija en esa válida,
      cuántos terminaron detrás.{" "}
      <strong className="font-medium text-charcoal">
        Brecha a la mediana:
      </strong>{" "}
      qué tan lejos, en porcentaje, estuvo del tiempo típico (mediana) del
      grupo — negativo es más rápido, positivo es más lento.
    </p>
  );
}

function FamilyCategoryNote({
  group,
  headingLabel,
  testId,
}: {
  group: TableGroup;
  headingLabel: string;
  testId: string;
}) {
  return (
    <p
      role="note"
      className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs text-blue-900"
      data-testid={testId}
    >
      {familyCategoryChangeNote(group, headingLabel)}
    </p>
  );
}

const METRIC_FORMATTERS = {
  position: positionCell,
  percentile: (p: RaceHistoryPoint) => formatPercentile(p.percentile),
  field_size: (p: RaceHistoryPoint) => formatFieldSize(p.field_size),
  gap_to_median_pct: (p: RaceHistoryPoint) => formatGapPct(p.gap_to_median_pct),
} as const;

const METRIC_ROW_LABELS: { key: keyof typeof METRIC_FORMATTERS; label: string }[] = [
  { key: "position", label: "Puesto" },
  { key: "percentile", label: "Percentil" },
  { key: "field_size", label: "Parrilla" },
  { key: "gap_to_median_pct", label: "Brecha" },
];

export function HistoryTable({
  points,
  audience = "coach",
  className,
}: HistoryTableProps) {
  if (points.length === 0) return null;
  const groups = groupPoints(points);

  return (
    <div className={cn("space-y-3", className)} data-testid="history-table-container">
      {audience === "family" && <FamilyMetricsExplainer />}

      {/* Vista mobile: tarjetas apiladas (<md) — T083 BLOCKER, mismo patrón
          que `AnthropometryHistory.tsx`. */}
      <ul
        role="list"
        className="flex flex-col gap-3 md:hidden"
        data-testid="history-table-mobile"
        aria-label="Progresión histórica entre temporadas — vista de tarjetas"
      >
        {groups.map((group) => {
          const headingLabel = groupHeadingLabel(group);
          return (
            <li key={group.key} className="space-y-2" data-testid={`history-table-mobile-group-${group.key}`}>
              <p className="rounded-lg bg-light-gray/30 px-3 py-1.5 text-xs font-semibold text-charcoal">
                {group.season} · {headingLabel}
              </p>
              {audience === "family" && group.categoryChanged && (
                <FamilyCategoryNote
                  group={group}
                  headingLabel={headingLabel}
                  testId={`history-family-category-note-mobile-${group.key}`}
                />
              )}
              <ul role="list" className="space-y-2">
                {group.rows.map((p) => {
                  const rowNote = rowCategoryNote(p, headingLabel);
                  return (
                    <li
                      key={p.event_id}
                      className="rounded-lg border border-[rgba(34,42,53,0.08)] p-3"
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-sm font-medium text-charcoal">
                          {p.label}
                          {rowNote && (
                            <span className="block text-xs font-normal text-mid-gray">
                              {rowNote}
                            </span>
                          )}
                        </span>
                        <span className="shrink-0 text-xs text-mid-gray">
                          {formatRaceDateShort(p.event_date)}
                        </span>
                      </div>
                      <dl className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                        {METRIC_ROW_LABELS.map(({ key, label }) => (
                          <div key={key} className="flex gap-1">
                            <dt className="text-mid-gray">{label}:</dt>
                            <dd className="font-medium text-charcoal">
                              {METRIC_FORMATTERS[key](p)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </li>
                  );
                })}
              </ul>
            </li>
          );
        })}
      </ul>

      {/* Vista desktop: tabla completa (md+) */}
      <div className="hidden overflow-x-auto md:block" data-testid="history-table-desktop">
        <table className="w-full text-sm" data-testid="history-table">
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
            </tr>
          </thead>
          {groups.map((group) => {
            const headingLabel = groupHeadingLabel(group);
            return (
              <tbody
                key={group.key}
                className="border-t border-[rgba(34,42,53,0.08)]"
                data-testid={`history-table-group-${group.key}`}
              >
                <tr className="bg-light-gray/30">
                  <th
                    colSpan={6}
                    scope="rowgroup"
                    className="px-3 py-1.5 text-left text-xs font-semibold text-charcoal"
                  >
                    {group.season} · {headingLabel}
                  </th>
                </tr>
                {audience === "family" && group.categoryChanged && (
                  <tr>
                    <td colSpan={6} className="px-3 py-1.5">
                      <FamilyCategoryNote
                        group={group}
                        headingLabel={headingLabel}
                        testId={`history-family-category-note-${group.key}`}
                      />
                    </td>
                  </tr>
                )}
                {group.rows.map((p) => {
                  const rowNote = rowCategoryNote(p, headingLabel);
                  return (
                    <tr key={p.event_id} className="text-charcoal">
                      <td className="px-3 py-1.5">{formatRaceDateShort(p.event_date)}</td>
                      <td className="px-3 py-1.5">
                        {p.label}
                        {rowNote && (
                          <span className="block text-xs text-mid-gray">{rowNote}</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5">{positionCell(p)}</td>
                      <td className="px-3 py-1.5">{formatPercentile(p.percentile)}</td>
                      <td className="px-3 py-1.5">{formatFieldSize(p.field_size)}</td>
                      <td className="px-3 py-1.5">{formatGapPct(p.gap_to_median_pct)}</td>
                    </tr>
                  );
                })}
              </tbody>
            );
          })}
        </table>
      </div>
    </div>
  );
}
