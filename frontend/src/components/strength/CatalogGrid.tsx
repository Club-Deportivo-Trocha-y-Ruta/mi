/**
 * CatalogGrid — envoltorio config-driven del catálogo de Fuerza y
 * Acondicionamiento sobre `CatalogGrid` compartido (feature 033 / T042).
 *
 * Antes una implementación completa de los cuatro estados loading/error/
 * empty/success (feature 021 / T016); ahora solo declara la copy y el
 * mapeo de `StrengthExerciseListItem` → `ExerciseCard` del dominio fuerza,
 * incluida la copy diferenciada para la combinación conocida-dispersa
 * equipo_gym × 10-12 (FR-016). El shell (grid responsive, skeletons,
 * `ErrorState` con detección de cold-start, `EmptyState`) vive en el
 * componente compartido.
 */
import { CatalogGrid as SharedCatalogGrid } from "@/components/shared/CatalogGrid";
import { isColdStartError } from "@/components/shared/ErrorState";
import { ExerciseCard, type StrengthExerciseListItem } from "./ExerciseCard";

// ---------------------------------------------------------------------------
// Error copy — fuerza's own generic vs. cold-start wording, kept as-is
// (`isColdStartError` centralizes the detection heuristic; the copy stays
// domain-owned, same pattern the shared component's own callers use).
// ---------------------------------------------------------------------------

const GENERIC_ERROR_MESSAGE = "No se pudo cargar el catálogo. Intenta de nuevo.";
const COLD_START_ERROR_MESSAGE =
  "El servidor está iniciando, puede tomar hasta 60 segundos. Intenta de nuevo en un momento.";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface CatalogGridProps {
  items: StrengthExerciseListItem[] | undefined;
  total: number | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  /** true when at least one filter is active — changes the empty-state copy */
  hasActiveFilters: boolean;
  /**
   * true when the active filters match the known-sparse "equipo_gym" +
   * "10-12" combination (the club's dosing rules keep gym-equipment work
   * out of the 10-12 band — see data-model.md / FR-016). Swaps the generic
   * "sin resultados" copy for one that explains this is expected, not a
   * bug, and suggests the bodyweight alternative.
   */
  isSparseKnownCombo?: boolean;
}

// ---------------------------------------------------------------------------
// Empty-state copy helper
// ---------------------------------------------------------------------------

function resolveEmptyState(hasActiveFilters: boolean, isSparseKnownCombo: boolean) {
  if (isSparseKnownCombo) {
    return {
      title: "Aún no hay ejercicios con equipo de gimnasio para 10–12 años",
      description:
        "Para esta franja de edad el club solo trabaja con ejercicios sin equipo (fortalecimiento con el propio peso corporal). Prueba el filtro “Sin equipo” para ver las opciones disponibles.",
    };
  }
  if (hasActiveFilters) {
    return {
      title: "Sin resultados para estos filtros",
      description: "Ajusta o limpia los filtros para ver más ejercicios.",
    };
  }
  return {
    title: "El catálogo está vacío",
    description: "Aún no hay ejercicios registrados en esta biblioteca.",
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CatalogGrid({
  items,
  total,
  isLoading,
  isFetching,
  isError,
  error,
  hasActiveFilters,
  isSparseKnownCombo = false,
}: CatalogGridProps) {
  return (
    <SharedCatalogGrid
      items={items}
      total={total}
      isLoading={isLoading}
      isFetching={isFetching}
      isError={isError}
      error={error}
      errorMessage={isColdStartError(error) ? COLD_START_ERROR_MESSAGE : GENERIC_ERROR_MESSAGE}
      emptyState={resolveEmptyState(hasActiveFilters, isSparseKnownCombo)}
      loadingLabel="Cargando catálogo de ejercicios de fuerza…"
      renderCard={(exercise) => <ExerciseCard exercise={exercise} />}
      getItemKey={(exercise) => exercise.id}
    />
  );
}

export default CatalogGrid;
