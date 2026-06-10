/**
 * StandingsTable — tabla de clasificación general de temporada (standings).
 *
 * Características:
 *   - Filas del club Trocha y Ruta visualmente distinguidas (fondo verde +
 *     barra lateral) — accesibles también por badge textual "Club" + aria-label.
 *   - Selector de categoría — filtra client-side.
 *   - Toggle "Solo mi club".
 *   - Ordenación client-side: rank (default), puntos, corredores.
 *   - Lazy-loaded por el padre vía React.lazy.
 *
 * Props:
 *   - `data: RaceEventStandingsResponse` — respuesta del endpoint ya cargada.
 */
import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";

import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type {
  RaceEventStandingsResponse,
  StandingCategory,
  StandingRow,
} from "@/types/raceResults.types";

// ---------------------------------------------------------------------------
// Tipos internos
// ---------------------------------------------------------------------------

type SortField = "rank" | "display_name" | "total_points";
type SortDir = "asc" | "desc";

interface SortState {
  field: SortField;
  dir: SortDir;
}

// ---------------------------------------------------------------------------
// Sub-componentes de ordenación (reutilizan patrón de ResultsTable)
// ---------------------------------------------------------------------------

function SortIcon({
  field,
  sort,
}: {
  field: SortField;
  sort: SortState;
}) {
  if (sort.field !== field) {
    return (
      <ChevronsUpDown
        size={12}
        className="shrink-0 text-mid-gray"
        aria-hidden="true"
      />
    );
  }
  return sort.dir === "asc" ? (
    <ChevronUp size={12} className="shrink-0" aria-hidden="true" />
  ) : (
    <ChevronDown size={12} className="shrink-0" aria-hidden="true" />
  );
}

function SortButton({
  field,
  label,
  sort,
  onSort,
}: {
  field: SortField;
  label: string;
  sort: SortState;
  onSort: (f: SortField) => void;
}) {
  const isActive = sort.field === field;
  return (
    <button
      type="button"
      onClick={() => onSort(field)}
      className={cn(
        "inline-flex items-center gap-1 transition-colors hover:text-charcoal",
        isActive ? "text-charcoal" : "text-mid-gray",
      )}
      aria-label={`Ordenar por ${label} ${isActive ? (sort.dir === "asc" ? "descendente" : "ascendente") : "ascendente"}`}
    >
      {label}
      <SortIcon field={field} sort={sort} />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Lógica de ordenación
// ---------------------------------------------------------------------------

function sortRows(rows: StandingRow[], sort: SortState): StandingRow[] {
  return [...rows].sort((a, b) => {
    let cmp = 0;
    if (sort.field === "rank") {
      cmp = a.rank - b.rank;
    } else if (sort.field === "display_name") {
      cmp = a.display_name.localeCompare(b.display_name, "es");
    } else if (sort.field === "total_points") {
      cmp = a.total_points - b.total_points;
    }
    return sort.dir === "asc" ? cmp : -cmp;
  });
}

// ---------------------------------------------------------------------------
// StandingsTable — props
// ---------------------------------------------------------------------------

export interface StandingsTableProps {
  data: RaceEventStandingsResponse;
  /**
   * Cuando es `true`, el toggle "Solo mi club" no se renderiza.
   * Usar para la vista de padres donde el backend ya filtra solo los propios hijos
   * y el toggle carece de sentido.
   * @default false
   */
  hideClubFilter?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StandingsTable({ data, hideClubFilter = false }: StandingsTableProps) {
  const categories = data.categories;

  // ── Categorías para el selector ──────────────────────────────────────────
  const categoryOptions = useMemo<{ id: number; label: string }[]>(
    () =>
      categories.map((c) => ({ id: c.category_id, label: c.label })),
    [categories],
  );

  // ── Estado de filtros ────────────────────────────────────────────────────
  const [selectedCategoryId, setSelectedCategoryId] = useState<
    number | "all"
  >("all");
  const [clubOnly, setClubOnly] = useState(false);
  const [sort, setSort] = useState<SortState>({ field: "rank", dir: "asc" });

  function handleSort(field: SortField) {
    setSort((prev) =>
      prev.field === field
        ? { field, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { field, dir: "asc" },
    );
  }

  // ── Categorías filtradas y ordenadas ─────────────────────────────────────
  const visibleCategories = useMemo<StandingCategory[]>(() => {
    const cats =
      selectedCategoryId === "all"
        ? categories
        : categories.filter((c) => c.category_id === selectedCategoryId);

    return cats.map((cat) => {
      const filteredRows = clubOnly
        ? cat.rows.filter((r) => r.is_our_club)
        : cat.rows;
      return { ...cat, rows: sortRows(filteredRows, sort) };
    });
  }, [categories, selectedCategoryId, clubOnly, sort]);

  const totalRows = useMemo(
    () => visibleCategories.reduce((sum, c) => sum + c.rows.length, 0),
    [visibleCategories],
  );

  const noDataAfterFilter =
    totalRows === 0 && (clubOnly || selectedCategoryId !== "all");

  return (
    <div className="space-y-4" data-testid="standings-table-root">
      {/* ── Barra de controles ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Selector de categoría */}
        <div className="flex items-center gap-2">
          <label
            htmlFor="standings-category-select"
            className="text-xs font-medium text-mid-gray"
          >
            Categoría
          </label>
          <select
            id="standings-category-select"
            value={selectedCategoryId}
            onChange={(e) => {
              const val = e.target.value;
              setSelectedCategoryId(val === "all" ? "all" : Number(val));
            }}
            className="h-9 rounded-lg border border-[rgba(34,42,53,0.12)] bg-white px-3 text-sm text-charcoal focus:outline-none focus:ring-2 focus:ring-primary/50"
            data-testid="standings-category-select"
          >
            <option value="all">Todas</option>
            {categoryOptions.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {/* Toggle Solo mi club — oculto cuando hideClubFilter=true (vista padres) */}
        {!hideClubFilter && (
          <label
            className="flex cursor-pointer items-center gap-2 text-sm text-charcoal"
            data-testid="standings-club-only-label"
          >
            <input
              type="checkbox"
              checked={clubOnly}
              onChange={(e) => setClubOnly(e.target.checked)}
              className="h-4 w-4 cursor-pointer rounded border-[rgba(34,42,53,0.2)] accent-primary"
              data-testid="standings-club-only-toggle"
              aria-label="Solo mi club"
            />
            Solo mi club
          </label>
        )}

        {/* Contador */}
        {totalRows > 0 && (
          <span className="ml-auto text-xs text-mid-gray" data-testid="standings-count-badge">
            {totalRows} {totalRows === 1 ? "corredor" : "corredores"}
          </span>
        )}
      </div>

      {/* ── Sin datos después de filtro ──────────────────────────────────── */}
      {noDataAfterFilter && (
        <div
          className="rounded-xl bg-white p-6 text-center text-sm text-mid-gray ring-1 ring-[rgba(34,42,53,0.08)]"
          data-testid="standings-empty-after-filter"
          role="status"
        >
          {clubOnly
            ? "No hay corredores de nuestro club en esta categoría."
            : "No hay clasificación para la categoría seleccionada."}
        </div>
      )}

      {/* ── Tablas por categoría ─────────────────────────────────────────── */}
      {!noDataAfterFilter &&
        visibleCategories
          .filter((cat) => cat.rows.length > 0)
          .map((cat) => (
            <div
              key={cat.category_id}
              className="overflow-hidden rounded-xl bg-white ring-1 ring-[rgba(34,42,53,0.08)]"
              data-testid={`standings-category-section-${cat.category_id}`}
            >
              {/* Encabezado de categoría */}
              <div className="flex items-center justify-between border-b border-[rgba(34,42,53,0.06)] px-4 py-3">
                <h3 className="text-sm font-semibold text-charcoal">
                  {cat.label}
                </h3>
                <span className="text-xs text-mid-gray">
                  {cat.rows.length}{" "}
                  {cat.rows.length === 1 ? "corredor" : "corredores"}
                </span>
              </div>

              <Table>
                <TableCaption className="sr-only">
                  Clasificación de la temporada para la categoría {cat.label}
                </TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-14">
                      <SortButton
                        field="rank"
                        label="Pos."
                        sort={sort}
                        onSort={handleSort}
                      />
                    </TableHead>
                    <TableHead>
                      <SortButton
                        field="display_name"
                        label="Corredor"
                        sort={sort}
                        onSort={handleSort}
                      />
                    </TableHead>
                    <TableHead className="hidden sm:table-cell">Club</TableHead>
                    <TableHead className="text-right">
                      <SortButton
                        field="total_points"
                        label="Puntos"
                        sort={sort}
                        onSort={handleSort}
                      />
                    </TableHead>
                    <TableHead className="hidden md:table-cell text-right">
                      Válidas
                    </TableHead>
                    <TableHead className="hidden md:table-cell text-right">
                      Podios
                    </TableHead>
                    <TableHead className="hidden lg:table-cell text-right">
                      Mejor pos.
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cat.rows.map((row) => (
                    <StandingRowItem key={row.competitor_id} row={row} />
                  ))}
                </TableBody>
              </Table>
            </div>
          ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StandingRowItem — fila individual de clasificación
// ---------------------------------------------------------------------------

function StandingRowItem({ row }: { row: StandingRow }) {
  const isOurClub = row.is_our_club;

  return (
    <TableRow
      className={cn(
        // El indicador de club se pinta como box-shadow inset en la primera
        // celda (no como ::before absoluto): aplicar `position: relative` a un
        // <tr> rompe la grilla de columnas de la tabla en Chrome (border-collapse)
        // y desplazaba toda la fila una columna a la derecha.
        isOurClub && "bg-emerald-50/60 hover:bg-emerald-50",
      )}
      aria-label={
        isOurClub
          ? `${row.display_name} — corredor de nuestro club`
          : undefined
      }
      data-testid={`standings-row-${row.competitor_id}`}
      data-our-club={isOurClub ? "true" : undefined}
    >
      {/* Rank */}
      <TableCell
        className={cn(
          "font-mono text-xs font-medium",
          isOurClub && "shadow-[inset_4px_0_0_0_var(--color-emerald-500)]",
        )}
      >
        <span
          className={cn(
            row.rank <= 3 ? "text-amber-700 font-bold" : "text-charcoal",
          )}
        >
          {row.rank}
        </span>
      </TableCell>

      {/* Nombre + badge club en mobile */}
      <TableCell>
        <div className="flex items-center gap-2">
          <span className={cn("text-sm", isOurClub && "font-medium text-charcoal")}>
            {row.display_name}
          </span>
          {isOurClub && (
            <span
              className="shrink-0 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 sm:hidden"
              aria-label="Corredor de nuestro club"
            >
              Club
            </span>
          )}
        </div>
        {/* Club visible en mobile */}
        <p className="mt-0.5 text-xs text-mid-gray sm:hidden">{row.club_text}</p>
      </TableCell>

      {/* Club (desktop) */}
      <TableCell className="hidden sm:table-cell text-mid-gray">
        <div className="flex items-center gap-1.5">
          {isOurClub && (
            <span
              className="shrink-0 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700"
              aria-label="Corredor de nuestro club"
            >
              Club
            </span>
          )}
          <span className="text-sm">{row.club_text}</span>
        </div>
      </TableCell>

      {/* Puntos */}
      <TableCell className="text-right">
        <span
          className={cn(
            "text-sm font-semibold",
            isOurClub ? "text-emerald-700" : "text-charcoal",
          )}
        >
          {row.total_points}
        </span>
      </TableCell>

      {/* Válidas (desktop md+) */}
      <TableCell className="hidden md:table-cell text-right text-sm text-mid-gray">
        {row.races_run}
      </TableCell>

      {/* Podios (desktop md+) */}
      <TableCell className="hidden md:table-cell text-right text-sm">
        {row.podiums > 0 ? (
          <span className="text-amber-700 font-medium">{row.podiums}</span>
        ) : (
          <span className="text-mid-gray">—</span>
        )}
      </TableCell>

      {/* Mejor posición (desktop lg+) */}
      <TableCell className="hidden lg:table-cell text-right font-mono text-xs text-mid-gray">
        {row.best_position !== null ? row.best_position : "—"}
      </TableCell>
    </TableRow>
  );
}
