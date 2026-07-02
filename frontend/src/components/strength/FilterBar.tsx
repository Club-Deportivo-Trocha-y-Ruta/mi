/**
 * FilterBar — controles de filtrado del catálogo de Fuerza y Acondicionamiento
 * (feature 021 / T016).
 *
 * Filtros disponibles (todos combinables, AND — FR-002/FR-003/FR-004/FR-005):
 *   - Búsqueda libre (texto) — sobre nombre + resumen
 *   - Equipo (equipment) — select estático
 *   - Franja de edad (age_band) — select estático
 *   - Categoría de movimiento (movement_category) — select estático
 *
 * RHF-driven: los valores se sincronizan via watch + onChange hacia el padre,
 * mismo patrón de `components/technique/FilterBar.tsx` (sin useEffect). El
 * padre mantiene los filtros como estado y los pasa a useStrengthCatalog.
 */
import { useCallback } from "react";
import { useForm } from "react-hook-form";

import { Badge } from "@/components/ui/badge";
import type {
  StrengthAgeBand,
  StrengthEquipmentKind,
  StrengthMovementCategory,
} from "./ExerciseCard";
import {
  EQUIPMENT_LABEL,
  MOVEMENT_CATEGORY_LABEL,
  STRENGTH_AGE_BAND_LABEL,
} from "./ExerciseCard";

// ---------------------------------------------------------------------------
// Form value shape (all optional — empty string = "no filter")
// ---------------------------------------------------------------------------

interface FilterFormValues {
  q: string;
  equipment: string;
  age_band: string;
  movement_category: string;
}

const EMPTY: FilterFormValues = {
  q: "",
  equipment: "",
  age_band: "",
  movement_category: "",
};

// ---------------------------------------------------------------------------
// Filters shape sent to the parent — mirror `CatalogFilters` query params
// (contracts/strength-api.md GET /exercises). Canonical type lands in
// `@/types/strength.types` (owned by T015).
// ---------------------------------------------------------------------------

export interface StrengthCatalogFilters {
  q?: string;
  equipment?: StrengthEquipmentKind;
  age_band?: StrengthAgeBand;
  movement_category?: StrengthMovementCategory;
}

const EQUIPMENT_OPTIONS: { value: StrengthEquipmentKind; label: string }[] = [
  { value: "sin_equipo", label: EQUIPMENT_LABEL.sin_equipo },
  { value: "equipo_gym", label: EQUIPMENT_LABEL.equipo_gym },
];

const AGE_BAND_OPTIONS: { value: StrengthAgeBand; label: string }[] = [
  { value: "10-12", label: `${STRENGTH_AGE_BAND_LABEL["10-12"]} años` },
  { value: "13-15", label: `${STRENGTH_AGE_BAND_LABEL["13-15"]} años` },
];

const MOVEMENT_CATEGORY_OPTIONS: {
  value: StrengthMovementCategory;
  label: string;
}[] = [
  { value: "empuje_superior", label: MOVEMENT_CATEGORY_LABEL.empuje_superior },
  {
    value: "traccion_superior",
    label: MOVEMENT_CATEGORY_LABEL.traccion_superior,
  },
  {
    value: "inferior_bilateral",
    label: MOVEMENT_CATEGORY_LABEL.inferior_bilateral,
  },
  {
    value: "inferior_unilateral",
    label: MOVEMENT_CATEGORY_LABEL.inferior_unilateral,
  },
  { value: "core_estabilidad", label: MOVEMENT_CATEGORY_LABEL.core_estabilidad },
];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface FilterBarProps {
  /** Called whenever any filter changes, with the serialized filters. */
  onChange: (filters: StrengthCatalogFilters) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toApiFilters(values: FilterFormValues): StrengthCatalogFilters {
  const filters: StrengthCatalogFilters = {};
  if (values.q.trim()) filters.q = values.q.trim();
  if (values.equipment)
    filters.equipment = values.equipment as StrengthEquipmentKind;
  if (values.age_band) filters.age_band = values.age_band as StrengthAgeBand;
  if (values.movement_category)
    filters.movement_category = values.movement_category as StrengthMovementCategory;
  return filters;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FilterBar({ onChange }: FilterBarProps) {
  const { register, watch, reset, getValues } = useForm<FilterFormValues>({
    defaultValues: EMPTY,
  });

  // Notify parent on any field change
  const notify = useCallback(
    (values: FilterFormValues) => {
      onChange(toApiFilters(values));
    },
    [onChange],
  );

  function handleFieldChange() {
    // getValues is synchronous — safe to call immediately after RHF field change
    notify(getValues());
  }

  function handleClear() {
    reset(EMPTY);
    onChange({});
  }

  const values = watch();
  const activeCount = [
    values.q.trim(),
    values.equipment,
    values.age_band,
    values.movement_category,
  ].filter(Boolean).length;

  return (
    <section
      aria-label="Filtros del catálogo de fuerza"
      className="rounded-xl border border-slate-200 bg-white p-4"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Búsqueda libre */}
        <div>
          <label
            htmlFor="filter-q"
            className="mb-1 block text-xs font-medium text-slate-700"
          >
            Buscar
          </label>
          <input
            id="filter-q"
            type="text"
            placeholder="Nombre o descripción…"
            {...register("q", { onChange: handleFieldChange })}
            className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        {/* Equipo */}
        <div>
          <label
            htmlFor="filter-equipment"
            className="mb-1 block text-xs font-medium text-slate-700"
          >
            Equipo
          </label>
          <select
            id="filter-equipment"
            {...register("equipment", { onChange: handleFieldChange })}
            className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">Todos los equipos</option>
            {EQUIPMENT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* Franja de edad */}
        <div>
          <label
            htmlFor="filter-age"
            className="mb-1 block text-xs font-medium text-slate-700"
          >
            Franja de edad
          </label>
          <select
            id="filter-age"
            {...register("age_band", { onChange: handleFieldChange })}
            className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">Todas las franjas</option>
            {AGE_BAND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        {/* Categoría de movimiento */}
        <div>
          <label
            htmlFor="filter-movement"
            className="mb-1 block text-xs font-medium text-slate-700"
          >
            Categoría de movimiento
          </label>
          <select
            id="filter-movement"
            {...register("movement_category", { onChange: handleFieldChange })}
            className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">Todas las categorías</option>
            {MOVEMENT_CATEGORY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Limpiar filtros */}
      {activeCount > 0 && (
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={handleClear}
            className="min-h-9 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:border-slate-400 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            Limpiar filtros
          </button>
          <Badge variant="secondary" className="text-xs">
            {activeCount} {activeCount === 1 ? "filtro activo" : "filtros activos"}
          </Badge>
        </div>
      )}
    </section>
  );
}

export default FilterBar;
