/**
 * CategoryMappingTable — tabla de categorías del acta parseada, con su
 * completitud (feature 044, US1 + US2).
 *
 * Columnas: encabezado impreso · categoría · tipo (exacta / renombrada /
 * propia de esa temporada / sin reconocer) · filas · estado. `tipo` viene
 * de `normalizer.mapping_kind_for` (contracts/category-mapping.md): un
 * header como "DAMAS"/"NIÑAS" en 2024-2025 resuelve a la categoría activa
 * 2026 (`rename`), mientras que el máster de dos grupos de 2025 o el grupo
 * único de preinfantil femenino son `season_specific` — fundirlos con una
 * subdivisión posterior inventaría un rango de edad que ese año no existía.
 *
 * `estado` combina el badge de completitud con, para una categoría
 * `inconsistent`, la pista en lenguaje llano ("Falta el puesto 6" / "El
 * puesto 20 está repetido") y los dos botones de acción que abren
 * `RowCorrectionDialog`/`AcknowledgeGapDialog`. Una categoría de encabezado
 * `unknown` (código `null`) no tiene acción disponible aquí — esta feature
 * no incluye una UI de mapeo manual, así que solo se advierte que esa
 * categoría no puede confirmarse hasta que el catálogo la reconozca.
 *
 * El componente mantiene su PROPIA copia de `categories` (inicializada
 * desde `props.categories`) porque `/corrections` y `/acknowledge` solo
 * devuelven la completitud recalculada de la categoría afectada — no la
 * lista de filas completa. `onReadyCountChange` informa al wizard cuántas
 * categorías quedan listas para el copy del botón de confirmar.
 *
 * Privacidad: nombre/ciudad/club de un corredor solo aparecen dentro de los
 * diálogos de corrección (mismo origen público que el resto del wizard).
 * Esta tabla en sí no lista filas individuales — evita repetir PII de
 * menores en un componente que se queda montado toda la revisión.
 */
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Pencil, ShieldCheck } from "lucide-react";

import { cn } from "@/lib/utils";
import type {
  CategoryCompleteness,
  CategoryMappingKind,
  CompletenessStatus,
  ParsedCategory,
  RowCorrectionOp,
  UnreadableRow,
} from "@/types/raceImports.types";
import { RowCorrectionDialog } from "@/components/competitions/import/RowCorrectionDialog";
import { AcknowledgeGapDialog } from "@/components/competitions/import/AcknowledgeGapDialog";

const MAPPING_KIND_LABELS: Record<CategoryMappingKind, string> = {
  exact: "Exacta",
  rename: "Renombrada",
  season_specific: "Propia de esa temporada",
  unknown: "Sin reconocer",
};

const STATUS_META: Record<
  CompletenessStatus,
  { label: string; className: string }
> = {
  ok: {
    label: "Completa",
    className: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200",
  },
  inconsistent: {
    label: "Inconsistente",
    className: "bg-amber-100 text-amber-800 ring-1 ring-amber-200",
  },
  acknowledged: {
    label: "Reconocida",
    className: "bg-blue-100 text-blue-800 ring-1 ring-blue-200",
  },
};

function CompletenessBadge({ status }: { status: CompletenessStatus }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        meta.className,
      )}
      data-testid={`completeness-badge-${status}`}
    >
      {meta.label}
    </span>
  );
}

/** "Falta el puesto 6." / "El puesto 20 está repetido." — lenguaje llano. */
function describeGaps(completeness: CategoryCompleteness): string[] {
  const out: string[] = [];
  for (const m of completeness.missing) out.push(`Falta el puesto ${m}.`);
  for (const d of completeness.duplicated) {
    out.push(`El puesto ${d} está repetido.`);
  }
  return out;
}

function isReady(category: ParsedCategory): boolean {
  return (
    category.code !== null &&
    (category.completeness.status === "ok" ||
      category.completeness.status === "acknowledged")
  );
}

// ---------------------------------------------------------------------------
// Aviso de filas ilegibles
// ---------------------------------------------------------------------------

function UnreadableRowsNotice({ rows }: { rows: UnreadableRow[] }) {
  if (rows.length === 0) return null;
  const pages = Array.from(new Set(rows.map((r) => r.page))).sort(
    (a, b) => a - b,
  );
  return (
    <div
      role="note"
      data-testid="unreadable-rows-notice"
      className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
    >
      <AlertTriangle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
      <span>
        {rows.length === 1
          ? "Hay 1 fila que el sistema no pudo leer del acta original"
          : `Hay ${rows.length} filas que el sistema no pudo leer del acta original`}{" "}
        (página{pages.length === 1 ? "" : "s"} {pages.join(", ")}). Revisa el
        documento fuente y agrégalas a mano si corresponden a un corredor.
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export interface CategoryMappingTableProps {
  parseId: string;
  categories: ParsedCategory[];
  unreadableRows?: UnreadableRow[];
  /** Cuántas categorías quedan listas para confirmar vs. el total. */
  onReadyCountChange?: (ready: number, total: number) => void;
}

interface CorrectionTarget {
  category: ParsedCategory;
  op: RowCorrectionOp;
  ordinal: number | null;
}

export function CategoryMappingTable({
  parseId,
  categories: initialCategories,
  unreadableRows = [],
  onReadyCountChange,
}: CategoryMappingTableProps) {
  const [categories, setCategories] = useState(initialCategories);
  const [correctionTarget, setCorrectionTarget] =
    useState<CorrectionTarget | null>(null);
  const [acknowledgeTarget, setAcknowledgeTarget] =
    useState<ParsedCategory | null>(null);

  // Re-sincroniza si el parse cambia (nuevo archivo cargado en step 1).
  useEffect(() => {
    setCategories(initialCategories);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parseId]);

  const readyCount = useMemo(
    () => categories.filter(isReady).length,
    [categories],
  );

  useEffect(() => {
    onReadyCountChange?.(readyCount, categories.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readyCount, categories.length]);

  function applyCompletenessUpdate(
    header: string,
    completeness: CategoryCompleteness,
  ) {
    setCategories((prev) =>
      prev.map((c) =>
        c.header_raw === header ? { ...c, completeness } : c,
      ),
    );
  }

  if (categories.length === 0) return null;

  return (
    <div className="space-y-3" data-testid="category-mapping-table">
      <UnreadableRowsNotice rows={unreadableRows} />

      <div className="overflow-x-auto rounded-lg ring-1 ring-light-gray">
        <table className="w-full text-sm">
          <thead className="bg-light-gray/60 text-xs text-mid-gray">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Encabezado impreso
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Categoría
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Tipo
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Filas
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Estado
              </th>
            </tr>
          </thead>
          <tbody>
            {categories.map((category) => {
              const gaps =
                category.completeness.status === "inconsistent"
                  ? describeGaps(category.completeness)
                  : [];
              return (
                <tr
                  key={category.header_raw}
                  className="border-t border-light-gray align-top"
                  data-testid={`category-row-${category.header_raw}`}
                >
                  <td className="px-3 py-2 text-charcoal">
                    {category.header_raw}
                  </td>
                  <td className="px-3 py-2">
                    {category.code ?? (
                      <span className="italic text-mid-gray">
                        Sin reconocer
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-mid-gray">
                    {MAPPING_KIND_LABELS[category.mapping_kind]}
                  </td>
                  <td className="px-3 py-2 tabular-nums text-charcoal">
                    {category.row_count ?? category.rows.length}
                  </td>
                  <td className="px-3 py-2">
                    <div className="space-y-1.5">
                      <CompletenessBadge status={category.completeness.status} />

                      {category.code === null && (
                        <p className="text-xs text-mid-gray">
                          Esta categoría no se puede confirmar hasta que el
                          catálogo la reconozca.
                        </p>
                      )}

                      {gaps.length > 0 && (
                        <ul className="space-y-0.5 text-xs text-amber-800">
                          {gaps.map((gap) => (
                            <li key={gap}>{gap}</li>
                          ))}
                        </ul>
                      )}

                      {category.completeness.status === "inconsistent" && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() =>
                              setCorrectionTarget({
                                category,
                                op: category.completeness.missing.length > 0
                                  ? "add"
                                  : "edit",
                                ordinal:
                                  category.completeness.missing[0] ??
                                  category.completeness.duplicated[0] ??
                                  null,
                              })
                            }
                            data-testid={`correct-row-${category.header_raw}`}
                            className="inline-flex min-h-[48px] items-center gap-1 rounded-lg border border-light-gray bg-surface-raised px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-90"
                          >
                            <Pencil size={12} aria-hidden="true" />
                            Corregir fila
                          </button>
                          <button
                            type="button"
                            onClick={() => setAcknowledgeTarget(category)}
                            data-testid={`acknowledge-${category.header_raw}`}
                            className="inline-flex min-h-[48px] items-center gap-1 rounded-lg border border-light-gray bg-surface-raised px-3 py-1.5 text-xs font-medium text-charcoal transition-opacity hover:opacity-90"
                          >
                            <ShieldCheck size={12} aria-hidden="true" />
                            Reconocer
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {correctionTarget && (
        <RowCorrectionDialog
          open
          onOpenChange={(open) => {
            if (!open) setCorrectionTarget(null);
          }}
          parseId={parseId}
          categoryHeader={correctionTarget.category.header_raw}
          initialOp={correctionTarget.op}
          initialOrdinal={correctionTarget.ordinal}
          onCorrected={(completeness) =>
            applyCompletenessUpdate(
              correctionTarget.category.header_raw,
              completeness,
            )
          }
        />
      )}

      {acknowledgeTarget && (
        <AcknowledgeGapDialog
          open
          onOpenChange={(open) => {
            if (!open) setAcknowledgeTarget(null);
          }}
          parseId={parseId}
          categoryHeader={acknowledgeTarget.header_raw}
          onAcknowledged={(completeness) =>
            applyCompletenessUpdate(acknowledgeTarget.header_raw, completeness)
          }
        />
      )}
    </div>
  );
}
