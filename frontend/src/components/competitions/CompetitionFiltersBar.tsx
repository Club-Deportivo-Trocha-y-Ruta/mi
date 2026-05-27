/**
 * CompetitionFiltersBar — barra de filtros para la lista de competencias.
 *
 * Filtros:
 *   - Temporada (select, default 2026)
 *   - Estado (chips: Planificada | Cancelada — los de Próxima y Con resultados
 *     son client-side, no query params del backend)
 *   - Sede (combobox texto libre con opciones del catálogo VENUE_ALTITUDES)
 *
 * El filtro de "tipo de periodización" (A/B/C) fue descartado porque el modelo
 * `RaceEvent` no tiene ese campo — solo `is_championship` (CD vs válida regular).
 * Se ofrece un toggle "Solo campeonatos" coherente con lo que el backend admite.
 *
 * Persiste los filtros activos en URL search params para URLs compartibles.
 */
import { useCallback } from "react";

import { VENUE_ALTITUDES } from "@/types/raceEvents.types";
import type { RaceEventListFilters } from "@/types/raceEvents.types";

// Años disponibles para el selector de temporada
const SEASON_OPTIONS = [2024, 2025, 2026, 2027];

const inputSelectClass =
  "rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 min-h-[44px]";
const inputSelectStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

interface CompetitionFiltersBarProps {
  value: RaceEventListFilters;
  onChange: (next: RaceEventListFilters) => void;
  /** Filtros client-side adicionales que no pasan al backend */
  localFilters: LocalFilters;
  onLocalFiltersChange: (next: LocalFilters) => void;
}

/** Filtros que se aplican post-fetch (no son query params del backend) */
export interface LocalFilters {
  /** true = solo válidas con resultados, false/undefined = sin filtro */
  hasResults?: boolean;
  /** true = solo las próximas (≤30 días), false/undefined = sin filtro */
  upcoming?: boolean;
}

const VENUE_OPTIONS = Object.keys(VENUE_ALTITUDES);

export function CompetitionFiltersBar({
  value,
  onChange,
  localFilters,
  onLocalFiltersChange,
}: CompetitionFiltersBarProps) {
  const handleSeason = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const season = e.target.value ? Number(e.target.value) : undefined;
      onChange({ ...value, season });
    },
    [value, onChange],
  );

  const handleStatus = useCallback(
    (status: "scheduled" | "cancelled" | undefined) => {
      onChange({ ...value, status });
    },
    [value, onChange],
  );

  const handleChampionship = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const v = e.target.value;
      onChange({
        ...value,
        is_championship: v === "" ? undefined : v === "true",
      });
    },
    [value, onChange],
  );

  const handleLocation = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const location = e.target.value || undefined;
      onChange({ ...value, location });
    },
    [value, onChange],
  );

  const toggleLocalFilter = useCallback(
    (key: keyof LocalFilters) => {
      onLocalFiltersChange({
        ...localFilters,
        [key]: localFilters[key] ? undefined : true,
      });
    },
    [localFilters, onLocalFiltersChange],
  );

  const activeStatus = value.status;

  return (
    <div
      className="rounded-xl bg-white p-4 space-y-3"
      style={{
        boxShadow:
          "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
      }}
    >
      {/* Fila 1: Temporada + Sede + Tipo */}
      <div className="grid gap-3 sm:grid-cols-3">
        {/* Temporada */}
        <div>
          <label htmlFor="filter-season" className="block text-xs font-medium text-mid-gray mb-1">
            Temporada
          </label>
          <select
            id="filter-season"
            value={value.season ?? ""}
            onChange={handleSeason}
            className={inputSelectClass}
            style={inputSelectStyle}
          >
            <option value="">Todas</option>
            {SEASON_OPTIONS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>

        {/* Sede */}
        <div>
          <label htmlFor="filter-location" className="block text-xs font-medium text-mid-gray mb-1">
            Sede
          </label>
          <select
            id="filter-location"
            value={value.location ?? ""}
            onChange={handleLocation}
            className={inputSelectClass}
            style={inputSelectStyle}
          >
            <option value="">Todas las sedes</option>
            {VENUE_OPTIONS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </div>

        {/* Tipo */}
        <div>
          <label htmlFor="filter-type" className="block text-xs font-medium text-mid-gray mb-1">
            Tipo
          </label>
          <select
            id="filter-type"
            value={
              value.is_championship === true
                ? "true"
                : value.is_championship === false
                  ? "false"
                  : ""
            }
            onChange={handleChampionship}
            className={inputSelectClass}
            style={inputSelectStyle}
          >
            <option value="">Todas</option>
            <option value="false">Válidas regulares</option>
            <option value="true">Campeonatos (CD)</option>
          </select>
        </div>
      </div>

      {/* Fila 2: Chips de estado */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs font-medium text-mid-gray">Estado:</span>

        {/* Planificada → status=scheduled */}
        <ChipButton
          active={activeStatus === "scheduled" && !localFilters.upcoming && !localFilters.hasResults}
          onClick={() =>
            activeStatus === "scheduled" && !localFilters.upcoming && !localFilters.hasResults
              ? handleStatus(undefined)
              : (handleStatus("scheduled"), onLocalFiltersChange({}))
          }
        >
          Planificada
        </ChipButton>

        {/* Próxima → scheduled + ≤30 días (client-side) */}
        <ChipButton
          active={!!localFilters.upcoming}
          onClick={() => {
            if (localFilters.upcoming) {
              onLocalFiltersChange({ ...localFilters, upcoming: undefined });
            } else {
              onChange({ ...value, status: "scheduled" });
              onLocalFiltersChange({ ...localFilters, upcoming: true, hasResults: undefined });
            }
          }}
        >
          Próxima
        </ChipButton>

        {/* Con resultados → client-side has_results=true */}
        <ChipButton
          active={!!localFilters.hasResults}
          onClick={() => {
            toggleLocalFilter("hasResults");
            if (!localFilters.hasResults) {
              onChange({ ...value, status: undefined });
            }
          }}
        >
          Con resultados
        </ChipButton>

        {/* Cancelada → status=cancelled */}
        <ChipButton
          active={activeStatus === "cancelled"}
          onClick={() =>
            activeStatus === "cancelled"
              ? (handleStatus(undefined), onLocalFiltersChange({}))
              : (handleStatus("cancelled"), onLocalFiltersChange({}))
          }
        >
          Cancelada
        </ChipButton>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChipButton — helper local para los chips de estado
// ---------------------------------------------------------------------------

interface ChipButtonProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function ChipButton({ active, onClick, children }: ChipButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex min-h-[44px] items-center rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "bg-charcoal text-white"
          : "bg-light-gray text-charcoal hover:bg-[rgba(34,42,53,0.1)]"
      }`}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}
