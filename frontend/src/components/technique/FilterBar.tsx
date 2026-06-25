/**
 * FilterBar — controles de filtrado del catálogo de técnica y gymkhana (US1 / T013).
 *
 * Filtros disponibles:
 *   - Habilidad (skill slug) — select poblado desde useSkills
 *   - Franja de edad (age_band) — select estático
 *   - Dificultad — select estático
 *   - Materiales disponibles — checkboxes multi-select desde useMaterials
 *
 * RHF-driven: los valores se sincronizan via watch + onChange hacia el padre.
 * El padre mantiene los filtros como estado y los pasa a useTechniqueCatalog.
 * Botón "Limpiar filtros" llama a reset() y notifica al padre con los valores
 * vacíos, siguiendo el patrón de la codebase (sin useEffect).
 */
import { useCallback } from "react";
import { useForm } from "react-hook-form";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useMaterials, useSkills } from "@/hooks/technique/useTechnique";
import type { CatalogFilters } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Form value shape (all optional — empty string = "no filter")
// ---------------------------------------------------------------------------

interface FilterFormValues {
  skill: string;
  age_band: string;
  difficulty: string;
  materials: string[]; // selected material slugs
}

const EMPTY: FilterFormValues = {
  skill: "",
  age_band: "",
  difficulty: "",
  materials: [],
};

// ---------------------------------------------------------------------------
// Label maps (español neutro)
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
// Helpers
// ---------------------------------------------------------------------------

function toApiFilters(values: FilterFormValues): CatalogFilters {
  const filters: CatalogFilters = {};
  if (values.skill) filters.skill = values.skill;
  if (values.age_band) filters.age_band = values.age_band as CatalogFilters["age_band"];
  if (values.difficulty) filters.difficulty = values.difficulty as CatalogFilters["difficulty"];
  if (values.materials.length > 0) filters.materials = values.materials.join(",");
  return filters;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FilterBar({ onChange }: FilterBarProps) {
  const { data: skills, isLoading: skillsLoading } = useSkills();
  const { data: materials, isLoading: materialsLoading } = useMaterials();

  const { register, watch, reset, setValue, getValues } =
    useForm<FilterFormValues>({ defaultValues: EMPTY });

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

  function handleMaterialToggle(slug: string) {
    const current = getValues("materials");
    const next = current.includes(slug)
      ? current.filter((s) => s !== slug)
      : [...current, slug];
    setValue("materials", next);
    notify({ ...getValues(), materials: next });
  }

  function handleClear() {
    reset(EMPTY);
    onChange({});
  }

  const selectedMaterials = watch("materials");

  // Count active filters for the clear button label
  const values = watch();
  const activeCount = [
    values.skill,
    values.age_band,
    values.difficulty,
  ].filter(Boolean).length + selectedMaterials.length;

  return (
    <section
      aria-label="Filtros del catálogo"
      className="rounded-xl border border-slate-200 bg-white p-4"
    >
      <div className="grid gap-3 sm:grid-cols-3">
        {/* Habilidad */}
        <div>
          <label
            htmlFor="filter-skill"
            className="mb-1 block text-xs font-medium text-slate-700"
          >
            Habilidad
          </label>
          {skillsLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <select
              id="filter-skill"
              {...register("skill", { onChange: handleFieldChange })}
              className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="">Todas las habilidades</option>
              {skills?.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.name}
                </option>
              ))}
            </select>
          )}
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

        {/* Dificultad */}
        <div>
          <label
            htmlFor="filter-difficulty"
            className="mb-1 block text-xs font-medium text-slate-700"
          >
            Dificultad
          </label>
          <select
            id="filter-difficulty"
            {...register("difficulty", { onChange: handleFieldChange })}
            className="min-h-12 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">Todas las dificultades</option>
            {DIFFICULTY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Materiales disponibles */}
      <div className="mt-3">
        <p className="mb-2 text-xs font-medium text-slate-700">
          Materiales disponibles hoy
        </p>
        {materialsLoading ? (
          <div className="flex flex-wrap gap-2" role="status" aria-label="Cargando materiales…">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-7 w-20 rounded-full" />
            ))}
          </div>
        ) : (
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por material">
            {materials?.map((m) => {
              const active = selectedMaterials.includes(m.slug);
              return (
                <button
                  key={m.slug}
                  type="button"
                  aria-pressed={active}
                  onClick={() => handleMaterialToggle(m.slug)}
                  className={[
                    "min-h-7 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    active
                      ? "border-primary bg-primary text-white"
                      : "border-slate-300 bg-white text-slate-700 hover:border-slate-400",
                  ].join(" ")}
                >
                  {m.name}
                </button>
              );
            })}
          </div>
        )}
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
