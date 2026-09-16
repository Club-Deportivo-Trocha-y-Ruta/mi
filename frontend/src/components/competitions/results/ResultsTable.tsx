/**
 * ResultsTable — tabla de resultados de una válida (tabla de llegada).
 *
 * Características:
 *   - Filas de nuestro club visualmente distinguidas (fondo verde claro +
 *     indicador de barra lateral) — no solo por color (regla WCAG AA: el
 *     badge textual "Club" + `aria-label` sirven de señal no-color).
 *   - Selector de categoría — filtra client-side desde la respuesta ya
 *     cargada para evitar round-trips.
 *   - Toggle "Solo mi club" — filtra a `is_our_club === true`.
 *   - Ordenación client-side por posición (default), nombre o tiempo.
 *   - `race_time_ms` formateado como mm:ss.mmm.
 *   - Lazy-loaded por el padre vía React.lazy.
 *   - Acción "Analizar con IA" por fila (coach/admin, filas is_our_club con
 *     athlete_id vinculado). Confirma si ya existe un análisis fresco; lanza
 *     directamente si no hay insight previo. Requiere `season` y `validaNum`
 *     para construir el body del run.
 *
 * Accesibilidad:
 *   - <table> semántico con <caption> y scope en <th>.
 *   - Las filas del club tienen aria-label que indica pertenencia al club.
 *   - Focus ring en botones de ordenación.
 *
 * Props:
 *   - `data: RaceEventResultsResponse` — respuesta del endpoint ya cargada.
 *   - `season?: number` — año de la temporada (necesario para lanzar análisis).
 *   - `validaNum?: number` — número de válida (sequence_number del evento).
 *   - `isCoachOrAdmin?: boolean` — muestra el botón "Analizar con IA".
 */
import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown, MessageSquarePlus, MessageSquare } from "lucide-react";

import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableScrollContainer,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { AnalyzeAthleteButton } from "@/components/competitions/insights/AnalyzeAthleteButton";
import { EditResultNoteDialog } from "@/components/race/EditResultNoteDialog";
import type {
  RaceEventResultsResponse,
  RaceResultCategory,
  RaceResultRow,
  RaceResultsFilters,
} from "@/types/raceResults.types";

// ---------------------------------------------------------------------------
// Helpers de formato
// ---------------------------------------------------------------------------

/**
 * Formatea milisegundos como mm:ss.mmm
 * Ej: 3_540_000 ms → "59:00.000"
 */
export function formatRaceTime(ms: number | null): string {
  if (ms === null || ms < 0) return "—";
  const totalMs = Math.round(ms);
  const minutes = Math.floor(totalMs / 60_000);
  const seconds = Math.floor((totalMs % 60_000) / 1_000);
  const millis = totalMs % 1_000;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

/**
 * Etiquetas de estado de resultado.
 */
const STATUS_LABELS: Record<string, string> = {
  finished: "—",
  dnf: "DNF",
  dns: "DNS",
  dsq: "DSQ",
};

function statusLabel(
  status: string,
  laps_behind: number | null,
  position: number | null,
): string {
  if (status !== "finished") return STATUS_LABELS[status] ?? status;
  if (position === 1) return "1er"; // ganador
  if (laps_behind !== null && laps_behind > 0) {
    return `+${laps_behind} ${laps_behind === 1 ? "vuelta" : "vueltas"}`;
  }
  return "—";
}

/**
 * Feature 043 (US2) — sufijo del encabezado de categoría con las cifras del
 * circuito: "{laps} vueltas · {variant_label} · {lap_distance_km} km ·
 * {elevation_gain_m} m D+". `lap_distance_km`/`elevation_gain_m` viven en
 * `RaceResultRow` (no en `RaceResultCategory`, ver
 * `results-derived-figures.md` §1) porque el backend los repite por fila
 * desde el setup compartido — se toman de la primera fila de la categoría
 * que los trae definidos, ya que son iguales para todas.
 */
function formatCourseHeaderSuffix(cat: RaceResultCategory): string {
  const lapDistanceRow = cat.rows.find((r) => r.lap_distance_km != null);
  const elevationRow = cat.rows.find((r) => r.elevation_gain_m != null);
  const lapDistance = lapDistanceRow?.lap_distance_km ?? "—";
  const elevation = elevationRow?.elevation_gain_m ?? "sin dato";
  return `· ${cat.laps} vueltas · ${cat.variant_label} · ${lapDistance} km · ${elevation} m D+`;
}

// ---------------------------------------------------------------------------
// Tipos internos
// ---------------------------------------------------------------------------

type SortField = "position" | "display_name" | "race_time_ms";
type SortDir = "asc" | "desc";

interface SortState {
  field: SortField;
  dir: SortDir;
}

// ---------------------------------------------------------------------------
// Sub-componentes
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
        "inline-flex min-h-12 items-center gap-1 transition-colors hover:text-charcoal",
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
// Lógica de orden y filtrado
// ---------------------------------------------------------------------------

function sortRows(rows: RaceResultRow[], sort: SortState): RaceResultRow[] {
  return [...rows].sort((a, b) => {
    let cmp = 0;
    if (sort.field === "position") {
      // Filas sin posición (DNF/DNS/DSQ) van al final
      const pa = a.position ?? Number.MAX_SAFE_INTEGER;
      const pb = b.position ?? Number.MAX_SAFE_INTEGER;
      cmp = pa - pb;
    } else if (sort.field === "display_name") {
      cmp = a.display_name.localeCompare(b.display_name, "es");
    } else if (sort.field === "race_time_ms") {
      const ta = a.race_time_ms ?? Number.MAX_SAFE_INTEGER;
      const tb = b.race_time_ms ?? Number.MAX_SAFE_INTEGER;
      cmp = ta - tb;
    }
    return sort.dir === "asc" ? cmp : -cmp;
  });
}

// ---------------------------------------------------------------------------
// ResultsTable — props
// ---------------------------------------------------------------------------

export interface ResultsTableProps {
  data: RaceEventResultsResponse;
  /**
   * Cuando es `true`, el toggle "Solo mi club" no se renderiza.
   * Usar para la vista de padres donde el backend ya filtra solo los propios hijos
   * y el toggle carece de sentido.
   * @default false
   */
  hideClubFilter?: boolean;
  /**
   * Año de temporada (ej. 2026). Necesario para la acción "Analizar con IA".
   * Si es undefined, el botón de análisis no se muestra aunque `isCoachOrAdmin` sea true.
   */
  season?: number;
  /**
   * Número de válida (sequence_number del RaceEventRead). Necesario para la
   * acción "Analizar con IA". Si es undefined, el botón no se muestra.
   */
  validaNum?: number;
  /**
   * true cuando el usuario autenticado es coach o admin. Activa el botón
   * "Analizar con IA" en las filas elegibles (is_our_club && athlete_id != null).
   * @default false
   */
  isCoachOrAdmin?: boolean;
  /**
   * Mapa athlete_id → stale_run_id construido por el padre a partir de
   * `useClubInsightsByRace`. El padre (ResultsTabInner) lo hace para mantener
   * ResultsTable libre de hooks de server state (patrón establecido).
   *
   * Semántica del valor:
   *   - key ausente / `undefined` → no hay insight previo → launch directo.
   *   - `null`    → insight fresco (stale_run_id == null) → pedir confirmación.
   *   - `string`  → stale run_id → launch directo (análisis desactualizado).
   */
  insightFreshnessMap?: Map<number, string | null>;
  /**
   * Filtros activos en esta tabla. Se pasan a EditResultNoteDialog para que
   * la invalidación optimista apunte a la query key exacta.
   */
  activeFilters?: RaceResultsFilters;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ResultsTable({
  data,
  hideClubFilter = false,
  season,
  validaNum,
  isCoachOrAdmin = false,
  insightFreshnessMap,
  activeFilters = {},
}: ResultsTableProps) {
  const categories = data.categories;

  // Whether the "Analizar con IA" button should be shown per row.
  // Requires coach/admin role, plus season + validaNum to build the run body.
  const canLaunch = isCoachOrAdmin && season != null && validaNum != null;

  // Feature 043 (US2) — columnas derivadas de circuito ("Distancia" /
  // "Vel. prom.") solo cuando la válida tiene circuito configurado. Un
  // coach viendo una válida sin datos de circuito ve exactamente las mismas
  // columnas que antes de esta feature (SC-007).
  const showCourseColumns = data.has_course_data === true;

  // ── Categorías únicas para el selector ──────────────────────────────────
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
  const [sort, setSort] = useState<SortState>({
    field: "position",
    dir: "asc",
  });

  function handleSort(field: SortField) {
    setSort((prev) =>
      prev.field === field
        ? { field, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { field, dir: "asc" },
    );
  }

  // ── Categorías filtradas y ordenadas ─────────────────────────────────────
  const visibleCategories = useMemo<RaceResultCategory[]>(() => {
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

  // ── Sin datos después de filtros ─────────────────────────────────────────
  const noDataAfterFilter =
    totalRows === 0 && (clubOnly || selectedCategoryId !== "all");

  return (
    <TooltipProvider delayDuration={200}>
    <div className="space-y-4" data-testid="results-table-root">
      {/* ── Barra de controles ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Selector de categoría */}
        <div className="flex items-center gap-2">
          <label
            htmlFor="results-category-select"
            className="text-xs font-medium text-mid-gray"
          >
            Categoría
          </label>
          <select
            id="results-category-select"
            value={selectedCategoryId}
            onChange={(e) => {
              const val = e.target.value;
              setSelectedCategoryId(val === "all" ? "all" : Number(val));
            }}
            className="h-12 rounded-lg border border-[rgba(34,42,53,0.12)] bg-white px-3 text-sm text-charcoal focus:outline-none focus:ring-2 focus:ring-primary/50"
            data-testid="results-category-select"
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
            data-testid="results-club-only-label"
          >
            {/* h-12 w-12 directo en el input (no un wrapper con padding): el
                sweep e2e de target-size.spec.ts mide el boundingBox() real
                del propio <input> — mismo patrón ya usado en
                InsightsTimeline.tsx (checkbox de selección de insights). */}
            <input
              type="checkbox"
              checked={clubOnly}
              onChange={(e) => setClubOnly(e.target.checked)}
              className="h-12 w-12 cursor-pointer rounded border-[rgba(34,42,53,0.2)] accent-primary"
              data-testid="results-club-only-toggle"
              aria-label="Solo mi club"
            />
            Solo mi club
          </label>
        )}

        {/* Contador */}
        {totalRows > 0 && (
          <span className="ml-auto text-xs text-mid-gray" data-testid="results-count-badge">
            {totalRows} {totalRows === 1 ? "corredor" : "corredores"}
          </span>
        )}
      </div>

      {/* ── Sin datos después de filtro ──────────────────────────────────── */}
      {noDataAfterFilter && (
        <div
          className="rounded-xl bg-white p-6 text-center text-sm text-mid-gray ring-1 ring-[rgba(34,42,53,0.08)]"
          data-testid="results-empty-after-filter"
          role="status"
        >
          {clubOnly
            ? "No hay corredores de nuestro club en esta categoría."
            : "No hay resultados para la categoría seleccionada."}
        </div>
      )}

      {/* ── Tablas por categoría ─────────────────────────────────────────── */}
      {!noDataAfterFilter &&
        visibleCategories
          .filter((cat) => cat.rows.length > 0)
          .map((cat) => (
            <div
              key={cat.category_id}
              className="rounded-xl bg-white ring-1 ring-[rgba(34,42,53,0.08)]"
              data-testid={`results-category-section-${cat.category_id}`}
            >
              {/* Encabezado de categoría */}
              <div className="flex items-center justify-between border-b border-[rgba(34,42,53,0.06)] px-4 py-3">
                <h3 className="text-sm font-semibold text-charcoal">
                  {cat.label}
                  {cat.laps != null && (
                    <span className="ml-2 text-xs font-normal text-mid-gray">
                      {formatCourseHeaderSuffix(cat)}
                    </span>
                  )}
                </h3>
                <span className="text-xs text-mid-gray">
                  {cat.rows.length}{" "}
                  {cat.rows.length === 1 ? "corredor" : "corredores"}
                </span>
              </div>

              {/* F-05: overflow-hidden recortaba la columna Puntos en
                  t768/d1280 sin dejar forma de alcanzarla; el wrapper con
                  scroll + indicador la deja visible o alcanzable. */}
              <TableScrollContainer className="rounded-b-xl">
              <Table>
                <TableCaption className="sr-only">
                  Resultados de la categoría {cat.label}
                </TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-14">Pos.</TableHead>
                    <TableHead>
                      <SortButton
                        field="display_name"
                        label="Corredor"
                        sort={sort}
                        onSort={handleSort}
                      />
                    </TableHead>
                    <TableHead className="hidden sm:table-cell">Club</TableHead>
                    <TableHead className="whitespace-nowrap text-right">
                      <SortButton
                        field="race_time_ms"
                        label="Tiempo"
                        sort={sort}
                        onSort={handleSort}
                      />
                    </TableHead>
                    {/* Columnas derivadas de circuito (feature 043 US2) —
                        solo cuando la válida tiene circuito configurado. */}
                    {showCourseColumns && (
                      <>
                        <TableHead className="hidden sm:table-cell whitespace-nowrap text-right">
                          Distancia
                        </TableHead>
                        <TableHead className="hidden sm:table-cell whitespace-nowrap text-right">
                          Vel. prom.
                        </TableHead>
                      </>
                    )}
                    <TableHead className="hidden md:table-cell text-right">
                      Puntos
                    </TableHead>
                    <TableHead className="hidden lg:table-cell text-right">
                      Dorsal
                    </TableHead>
                    {/* Acciones — solo visible para coach/admin */}
                    {isCoachOrAdmin && (
                      <TableHead className="w-10 text-right" aria-label="Acciones" />
                    )}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cat.rows.map((row) => (
                    <ResultRow
                      key={row.competitor_id}
                      row={row}
                      sort={sort}
                      canLaunch={canLaunch}
                      isCoachOrAdmin={isCoachOrAdmin}
                      season={season}
                      validaNum={validaNum}
                      insightFreshness={
                        row.athlete_id != null
                          ? insightFreshnessMap?.get(row.athlete_id)
                          : undefined
                      }
                      raceEventId={data.race_event_id}
                      activeFilters={activeFilters}
                      showCourseColumns={showCourseColumns}
                    />
                  ))}
                </TableBody>
              </Table>
              </TableScrollContainer>
            </div>
          ))}
    </div>
    </TooltipProvider>
  );
}

// ---------------------------------------------------------------------------
// ResultRow — fila individual de resultado
// ---------------------------------------------------------------------------

function ResultRow({
  row,
  sort: _sort,
  canLaunch = false,
  isCoachOrAdmin = false,
  season,
  validaNum,
  insightFreshness,
  raceEventId,
  activeFilters = {},
  showCourseColumns = false,
}: {
  row: RaceResultRow;
  sort: SortState;
  canLaunch?: boolean;
  isCoachOrAdmin?: boolean;
  season?: number;
  validaNum?: number;
  /** undefined = no insight; null = fresh insight; string = stale run_id */
  insightFreshness?: string | null;
  raceEventId: number;
  activeFilters?: RaceResultsFilters;
  /**
   * Feature 043 (US2) — refleja `data.has_course_data`; controla si esta
   * fila renderiza las celdas "Distancia"/"Vel. prom." (deben coincidir
   * 1:1 con las `<TableHead>` que pinta `ResultsTable`, o la tabla queda
   * desalineada).
   */
  showCourseColumns?: boolean;
}) {
  const isOurClub = row.is_our_club;

  // Show per-row AI button: coach/admin only, our-club row, athlete_id linked,
  // and season + validaNum available.
  const showAnalyzeBtn =
    canLaunch &&
    isOurClub &&
    row.athlete_id != null &&
    season != null &&
    validaNum != null;

  // Show note button: coach/admin only, our-club row, athlete_id linked.
  const showNoteBtn = isCoachOrAdmin && isOurClub && row.athlete_id != null;

  const [noteDialogOpen, setNoteDialogOpen] = useState(false);

  return (
    <>
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
        data-testid={`results-row-${row.competitor_id}`}
        data-our-club={isOurClub ? "true" : undefined}
      >
        {/* Posición */}
        <TableCell
          className={cn(
            "font-mono text-xs font-medium",
            isOurClub && "shadow-[inset_4px_0_0_0_var(--color-emerald-500)]",
          )}
        >
          {row.position !== null ? (
            <span
              className={cn(
                row.position <= 3
                  ? "text-amber-700 font-bold"
                  : "text-charcoal",
              )}
            >
              {row.position}
            </span>
          ) : (
            <span className="text-mid-gray">
              {STATUS_LABELS[row.status] ?? row.status}
            </span>
          )}
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
          {/* Club visible en mobile (hidden en sm+) */}
          <p className="mt-0.5 text-xs text-mid-gray sm:hidden">{row.club_text}</p>
          {/* Nota del entrenador — preview inline en mobile para coach/admin */}
          {isCoachOrAdmin && isOurClub && row.coach_note && (
            <p className="mt-1 line-clamp-2 text-xs italic text-mid-gray sm:hidden">
              {row.coach_note}
            </p>
          )}
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
          {/* Nota del entrenador — preview inline en desktop para coach/admin */}
          {isCoachOrAdmin && isOurClub && row.coach_note && (
            <p className="mt-1 line-clamp-2 max-w-[22ch] text-xs italic text-mid-gray">
              {row.coach_note}
            </p>
          )}
        </TableCell>

        {/* Tiempo / estado */}
        <TableCell className="whitespace-nowrap text-right font-mono text-xs">
          {row.status === "finished" ? (
            <span>{formatRaceTime(row.race_time_ms)}</span>
          ) : (
            <span className="text-mid-gray">
              {statusLabel(row.status, row.laps_behind, row.position)}
            </span>
          )}
          {row.status === "finished" &&
            row.laps_behind !== null &&
            row.laps_behind > 0 && (
              <span className="ml-1 text-xs text-mid-gray">
                +{row.laps_behind}v
              </span>
            )}
        </TableCell>

        {/* Distancia / Vel. prom. (feature 043 US2) — solo cuando la
            válida tiene circuito configurado (showCourseColumns). */}
        {showCourseColumns && (
          <>
            <TableCell className="hidden sm:table-cell whitespace-nowrap text-right font-mono text-xs">
              {row.distance_km != null ? (
                `${row.distance_km.toFixed(1)} km`
              ) : (
                <span className="text-mid-gray">sin dato</span>
              )}
            </TableCell>
            <TableCell className="hidden sm:table-cell whitespace-nowrap text-right font-mono text-xs">
              {row.avg_speed_kmh != null ? (
                `${row.avg_speed_kmh.toFixed(1)} km/h`
              ) : (
                <span className="text-mid-gray">sin dato</span>
              )}
            </TableCell>
          </>
        )}

        {/* Puntos (desktop md+) */}
        <TableCell className="hidden md:table-cell text-right text-sm">
          {row.points_awarded !== null ? (
            <span className={cn(isOurClub && "font-semibold text-emerald-700")}>
              {row.points_awarded}
            </span>
          ) : (
            <span className="text-mid-gray">—</span>
          )}
        </TableCell>

        {/* Dorsal (desktop lg+) */}
        <TableCell className="hidden lg:table-cell text-right font-mono text-xs text-mid-gray">
          {row.bib_number !== null ? `#${row.bib_number}` : "—"}
        </TableCell>

        {/* Acciones — solo cuando isCoachOrAdmin=true */}
        {isCoachOrAdmin && (
          <TableCell className="text-right">
            <div className="flex items-center justify-end gap-1">
              {/* Nota del entrenador */}
              {showNoteBtn && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => setNoteDialogOpen(true)}
                      className={cn(
                        "flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors",
                        row.coach_note
                          ? "text-blue-600 hover:bg-blue-50"
                          : "text-mid-gray hover:bg-charcoal/8 hover:text-charcoal",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
                        "min-h-[48px] min-w-[48px]",
                      )}
                      aria-label={
                        row.coach_note
                          ? `Editar nota de ${row.display_name}`
                          : `Agregar nota para ${row.display_name}`
                      }
                      data-testid={`note-btn-${row.competitor_id}`}
                    >
                      {row.coach_note ? (
                        <MessageSquare size={13} aria-hidden="true" />
                      ) : (
                        <MessageSquarePlus size={13} aria-hidden="true" />
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="left">
                    {row.coach_note ? "Editar nota" : "Agregar nota"}
                  </TooltipContent>
                </Tooltip>
              )}
              {/* Analizar con IA */}
              {showAnalyzeBtn ? (
                <AnalyzeAthleteButton
                  athleteId={row.athlete_id!}
                  season={season!}
                  validaNum={validaNum!}
                  eventId={raceEventId}
                  insightFreshness={insightFreshness}
                  displayName={row.display_name}
                />
              ) : null}
            </div>
          </TableCell>
        )}
      </TableRow>

      {/* Note dialog — mounted outside the <tr> to avoid DOM nesting issues */}
      {showNoteBtn && (
        <EditResultNoteDialog
          resultId={row.result_id}
          displayName={row.display_name}
          currentNote={row.coach_note}
          raceEventId={raceEventId}
          filters={activeFilters}
          open={noteDialogOpen}
          onOpenChange={setNoteDialogOpen}
        />
      )}
    </>
  );
}
