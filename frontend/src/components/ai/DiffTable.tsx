/**
 * DiffTable — tabla de cambios para el wizard de revisión (F-UP-REV5).
 *
 * Renderiza el resultado de `compute_diff` del backend (REV3) con badges
 * por acción y un toggle "Mostrar solo cambios" para esconder filas
 * `unchanged` (default ON cuando hay > 20 unchanged, per Q1 design).
 *
 * Paginación cliente simple (50/pág) para diffs grandes — sin virtualization
 * para mantener el componente lazy chunk pequeño. Mobile-first: scroll
 * horizontal interno.
 *
 * Privacidad: los nombres de competidores son `competitor_display_name`
 * tal como aparecen en el PDF oficial publicado por la Federación. Por
 * eso es información pública y se renderiza directamente.
 */
import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import type { DiffRow, ResultSnapshot } from "@/types/raceImports.types";

interface DiffTableProps {
  diffRows: DiffRow[];
  /** Default ON cuando hay > 20 unchanged (decisión cerrada Q1). */
  defaultOnlyChanges?: boolean;
  /** Página tamaño cliente. */
  pageSize?: number;
  /** Callback opcional cuando el usuario interactúa con una fila. */
  onRowFocus?: (row: DiffRow) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function formatRaceTimeMs(ms?: number | null): string {
  if (ms == null || ms < 0) return "—";
  const totalMs = Math.round(ms);
  const minutes = Math.floor(totalMs / 60_000);
  const seconds = Math.floor((totalMs % 60_000) / 1_000);
  const millis = totalMs % 1_000;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(seconds).padStart(2, "0");
  const mmm = String(millis).padStart(3, "0");
  return `${mm}:${ss}.${mmm}`;
}

function snapField(s: ResultSnapshot | null | undefined, key: keyof ResultSnapshot): unknown {
  if (!s) return undefined;
  return s[key];
}

interface FieldDelta {
  label: string;
  before: string;
  after: string;
}

const FIELD_LABELS: Record<keyof ResultSnapshot, string> = {
  position: "Posición",
  race_time_ms: "Tiempo",
  points_awarded: "Puntos",
  status: "Estado",
};

function formatField(key: keyof ResultSnapshot, value: unknown): string {
  if (value == null || value === "") return "—";
  if (key === "race_time_ms") return formatRaceTimeMs(value as number);
  return String(value);
}

/** Calcula los campos que cambiaron entre `before` y `after`. */
function computeDelta(
  before: ResultSnapshot | null | undefined,
  after: ResultSnapshot | null | undefined,
): FieldDelta[] {
  const keys: Array<keyof ResultSnapshot> = [
    "position",
    "race_time_ms",
    "points_awarded",
    "status",
  ];
  const out: FieldDelta[] = [];
  for (const k of keys) {
    const b = snapField(before, k);
    const a = snapField(after, k);
    if (b !== a && !(b == null && a == null)) {
      out.push({
        label: FIELD_LABELS[k],
        before: formatField(k, b),
        after: formatField(k, a),
      });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Action badge
// ---------------------------------------------------------------------------

const ACTION_META: Record<
  DiffRow["action"],
  { label: string; className: string; aria: string }
> = {
  create: {
    label: "Nuevo",
    className: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200",
    aria: "acción crear",
  },
  update: {
    label: "Actualizado",
    className: "bg-blue-100 text-blue-800 ring-1 ring-blue-200",
    aria: "acción actualizar",
  },
  delete: {
    label: "Removido",
    className: "bg-red-100 text-red-800 ring-1 ring-red-200",
    aria: "acción eliminar",
  },
  unchanged: {
    label: "Sin cambios",
    className: "bg-light-gray text-mid-gray ring-1 ring-light-gray",
    aria: "sin cambios",
  },
};

function ActionBadge({ action }: { action: DiffRow["action"] }) {
  const meta = ACTION_META[action];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
        meta.className,
      )}
      aria-label={meta.aria}
      data-testid={`diff-badge-${action}`}
    >
      {meta.label}
    </span>
  );
}

function CategoryBadge({ code }: { code: string }) {
  return (
    <span className="inline-flex items-center rounded-md bg-light-gray/60 px-1.5 py-0.5 text-[10px] font-mono font-medium text-mid-gray">
      {code}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Changes cell
// ---------------------------------------------------------------------------

function ChangesCell({ row }: { row: DiffRow }) {
  if (row.action === "unchanged") {
    return <span className="text-xs text-mid-gray">—</span>;
  }
  if (row.action === "create") {
    const pos = row.after?.position;
    return (
      <span className="text-xs text-emerald-800">
        Nuevo {pos != null ? `en P${pos}` : ""}
        {row.after?.race_time_ms != null && (
          <span className="ml-2 text-mid-gray">
            {formatRaceTimeMs(row.after.race_time_ms)}
          </span>
        )}
      </span>
    );
  }
  if (row.action === "delete") {
    const pos = row.before?.position;
    return (
      <span className="text-xs text-red-800">
        Removido {pos != null ? `(era P${pos})` : ""}
      </span>
    );
  }
  // update
  const deltas = computeDelta(row.before, row.after);
  if (deltas.length === 0) {
    return <span className="text-xs text-mid-gray">Sin cambios visibles</span>;
  }
  return (
    <ul className="space-y-0.5 text-xs">
      {deltas.map((d) => (
        <li key={d.label} className="text-charcoal">
          <span className="font-medium text-mid-gray">{d.label}:</span>{" "}
          <span className="text-mid-gray">{d.before}</span>
          <span aria-hidden="true" className="mx-1 text-blue-600">
            →
          </span>
          <span className="font-semibold text-blue-800">{d.after}</span>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export function DiffTable({
  diffRows,
  defaultOnlyChanges,
  pageSize = 50,
  onRowFocus,
}: DiffTableProps) {
  const unchangedCount = useMemo(
    () => diffRows.filter((r) => r.action === "unchanged").length,
    [diffRows],
  );
  const initialOnlyChanges =
    defaultOnlyChanges !== undefined ? defaultOnlyChanges : unchangedCount > 20;
  const [onlyChanges, setOnlyChanges] = useState(initialOnlyChanges);
  const [page, setPage] = useState(0);

  const filtered = useMemo(
    () => (onlyChanges ? diffRows.filter((r) => r.action !== "unchanged") : diffRows),
    [diffRows, onlyChanges],
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  // Clamp page si se cambia el filtro y la página actual excede el total.
  const safePage = Math.min(page, totalPages - 1);
  const start = safePage * pageSize;
  const visible = filtered.slice(start, start + pageSize);

  return (
    <div className="space-y-3" data-testid="diff-table">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="inline-flex items-center gap-2 text-xs text-mid-gray">
          <input
            type="checkbox"
            checked={onlyChanges}
            onChange={(e) => {
              setOnlyChanges(e.target.checked);
              setPage(0);
            }}
            data-testid="diff-toggle-only-changes"
            aria-label="Mostrar solo cambios"
          />
          Mostrar solo cambios
        </label>
        <span className="text-xs text-mid-gray" data-testid="diff-rows-count">
          {filtered.length} fila{filtered.length === 1 ? "" : "s"}
        </span>
      </div>

      <div
        className="max-h-[480px] overflow-auto rounded-lg ring-1 ring-light-gray"
        data-testid="diff-table-container"
      >
        <table
          role="table"
          aria-label="Diferencias entre el PDF nuevo y los resultados ya importados"
          className="w-full border-collapse text-sm"
        >
          <thead className="sticky top-0 bg-light-gray/60 text-xs text-mid-gray">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Acción
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Competidor
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Categoría
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Cambios
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td
                  colSpan={4}
                  className="px-3 py-6 text-center text-xs text-mid-gray"
                >
                  {onlyChanges && diffRows.length > 0
                    ? "Esta revisión no cambia ningún resultado."
                    : "Sin filas para mostrar."}
                </td>
              </tr>
            )}
            {visible.map((row, idx) => {
              const rowKey = `${row.category_code}__${row.competitor_normalized_name}__${row.action}__${idx}`;
              return (
                <tr
                  key={rowKey}
                  className="border-t border-light-gray hover:bg-light-gray/20"
                  data-testid={`diff-row-${row.action}-${row.competitor_normalized_name}`}
                  onMouseEnter={() => onRowFocus?.(row)}
                >
                  <td className="px-3 py-2 align-top">
                    <ActionBadge action={row.action} />
                  </td>
                  <td className="px-3 py-2 align-top text-charcoal">
                    {row.competitor_display_name}
                  </td>
                  <td className="px-3 py-2 align-top">
                    <CategoryBadge code={row.category_code} />
                  </td>
                  <td className="px-3 py-2 align-top">
                    <ChangesCell row={row} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {filtered.length > pageSize && (
        <div
          className="flex items-center justify-between text-xs text-mid-gray"
          data-testid="diff-pagination"
        >
          <span>
            Página {safePage + 1} de {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={safePage === 0}
              data-testid="diff-page-prev"
              className="rounded-md bg-white px-2 py-1 ring-1 ring-light-gray hover:bg-light-gray/30 disabled:opacity-40"
            >
              ← Anterior
            </button>
            <button
              type="button"
              onClick={() =>
                setPage((p) => Math.min(totalPages - 1, p + 1))
              }
              disabled={safePage >= totalPages - 1}
              data-testid="diff-page-next"
              className="rounded-md bg-white px-2 py-1 ring-1 ring-light-gray hover:bg-light-gray/30 disabled:opacity-40"
            >
              Siguiente →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
