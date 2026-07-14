/**
 * FilterBar — envoltorio config-driven del catálogo de técnica y gymkhana
 * sobre el `LibraryFilterBar` compartido (feature 033 / T041).
 *
 * Antes una implementación completa (259 líneas, idéntica a
 * `components/strength/FilterBar.tsx` salvo los campos); ahora solo declara
 * la config de campos del dominio técnica — habilidad (async, desde
 * `useSkills`), franja de edad, dificultad (ambas estáticas) y materiales
 * disponibles (multi-select async, desde `useMaterials`) — y serializa el
 * resultado a `CatalogFilters`. El shell de filtros (RHF, "Limpiar filtros",
 * conteo de activos, a11y) vive en el componente compartido.
 */
import { LibraryFilterBar, type LibraryFilterField } from "@/components/shared/LibraryFilterBar";
import { useMaterials, useSkills } from "@/hooks/technique/useTechnique";
import type { AgeBand, CatalogFilters, Difficulty } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Label maps (español neutro) — estáticas, sin fetch
// ---------------------------------------------------------------------------

const AGE_BAND_OPTIONS = [
  { value: "7-9", label: "7–9 años" },
  { value: "10-12", label: "10–12 años" },
  { value: "13-15", label: "13–15 años" },
] as const;

const DIFFICULTY_OPTIONS = [
  { value: "facil", label: "Fácil" },
  { value: "media", label: "Media" },
  { value: "avanzada", label: "Avanzada" },
] as const;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface FilterBarProps {
  /** Called whenever any filter changes, with the serialized CatalogFilters. */
  onChange: (filters: CatalogFilters) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FilterBar({ onChange }: FilterBarProps) {
  const { data: skills, isLoading: skillsLoading } = useSkills();
  const { data: materials, isLoading: materialsLoading } = useMaterials();

  const fields: LibraryFilterField[] = [
    {
      type: "select",
      name: "skill",
      label: "Habilidad",
      placeholder: "Todas las habilidades",
      isLoading: skillsLoading,
      options: (skills ?? []).map((s) => ({ value: s.slug, label: s.name })),
    },
    {
      type: "select",
      name: "age_band",
      label: "Franja de edad",
      placeholder: "Todas las franjas",
      options: AGE_BAND_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
    },
    {
      type: "select",
      name: "difficulty",
      label: "Dificultad",
      placeholder: "Todas las dificultades",
      options: DIFFICULTY_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
    },
    {
      type: "multiSelect",
      name: "materials",
      label: "Materiales disponibles hoy",
      isLoading: materialsLoading,
      options: (materials ?? []).map((m) => ({ value: m.slug, label: m.name })),
    },
  ];

  function handleChange(filters: Record<string, string>) {
    const next: CatalogFilters = {};
    if (filters.skill) next.skill = filters.skill;
    if (filters.age_band) next.age_band = filters.age_band as AgeBand;
    if (filters.difficulty) next.difficulty = filters.difficulty as Difficulty;
    if (filters.materials) next.materials = filters.materials;
    onChange(next);
  }

  return <LibraryFilterBar ariaLabel="Filtros del catálogo" fields={fields} onChange={handleChange} />;
}

export default FilterBar;
