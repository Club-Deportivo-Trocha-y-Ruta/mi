/**
 * FilterBar — envoltorio config-driven del catálogo de Fuerza y
 * Acondicionamiento sobre el `LibraryFilterBar` compartido (feature 033 /
 * T042).
 *
 * Antes una implementación completa (259 líneas, idéntica a
 * `components/technique/FilterBar.tsx` salvo los campos); ahora solo
 * declara la config de campos del dominio fuerza — búsqueda libre, equipo,
 * franja de edad y categoría de movimiento (los cuatro estáticos, sin
 * fetch) — y serializa el resultado a `StrengthCatalogFilters`. El shell de
 * filtros (RHF, "Limpiar filtros", conteo de activos, a11y) vive en el
 * componente compartido.
 */
import { LibraryFilterBar, type LibraryFilterField } from "@/components/shared/LibraryFilterBar";
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

const MOVEMENT_CATEGORY_OPTIONS: { value: StrengthMovementCategory; label: string }[] = [
  { value: "empuje_superior", label: MOVEMENT_CATEGORY_LABEL.empuje_superior },
  { value: "traccion_superior", label: MOVEMENT_CATEGORY_LABEL.traccion_superior },
  { value: "inferior_bilateral", label: MOVEMENT_CATEGORY_LABEL.inferior_bilateral },
  { value: "inferior_unilateral", label: MOVEMENT_CATEGORY_LABEL.inferior_unilateral },
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
// Component
// ---------------------------------------------------------------------------

export function FilterBar({ onChange }: FilterBarProps) {
  const fields: LibraryFilterField[] = [
    {
      type: "text",
      name: "q",
      label: "Buscar",
      placeholder: "Nombre o descripción…",
    },
    {
      type: "select",
      name: "equipment",
      label: "Equipo",
      placeholder: "Todos los equipos",
      options: EQUIPMENT_OPTIONS,
    },
    {
      type: "select",
      name: "age_band",
      label: "Franja de edad",
      placeholder: "Todas las franjas",
      options: AGE_BAND_OPTIONS,
    },
    {
      type: "select",
      name: "movement_category",
      label: "Categoría de movimiento",
      placeholder: "Todas las categorías",
      options: MOVEMENT_CATEGORY_OPTIONS,
    },
  ];

  function handleChange(filters: Record<string, string>) {
    const next: StrengthCatalogFilters = {};
    if (filters.q) next.q = filters.q;
    if (filters.equipment) next.equipment = filters.equipment as StrengthEquipmentKind;
    if (filters.age_band) next.age_band = filters.age_band as StrengthAgeBand;
    if (filters.movement_category) {
      next.movement_category = filters.movement_category as StrengthMovementCategory;
    }
    onChange(next);
  }

  return (
    <LibraryFilterBar ariaLabel="Filtros del catálogo de fuerza" fields={fields} onChange={handleChange} />
  );
}

export default FilterBar;
