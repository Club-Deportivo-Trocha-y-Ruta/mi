/**
 * CatalogGrid — envoltorio config-driven del catálogo de técnica y gymkhana
 * sobre `CatalogGrid` compartido (feature 033 / T041).
 *
 * Antes una implementación completa de los cuatro estados loading/error/
 * empty/success (US1 / T014); ahora solo declara la copy y el mapeo de
 * `ExerciseListItem` → `ExerciseCard` del dominio técnica. El shell (grid
 * responsive, skeletons, `ErrorState` con detección de cold-start,
 * `EmptyState`) vive en el componente compartido.
 */
import { CatalogGrid as SharedCatalogGrid } from "@/components/shared/CatalogGrid";
import { isColdStartError } from "@/components/shared/ErrorState";
import { ExerciseCard } from "./ExerciseCard";
import type { ExerciseListItem } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Re-export the onEdit/onAttach callback types so callers share the same shape
// ---------------------------------------------------------------------------
export type OnEditExercise = (exercise: ExerciseListItem) => void;
export type OnAttachExercise = (exercise: ExerciseListItem) => void;

// ---------------------------------------------------------------------------
// Error copy — técnica's own generic vs. cold-start wording, kept as-is
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
  items: ExerciseListItem[] | undefined;
  total: number | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  /** true when at least one filter is active — changes the empty-state copy */
  hasActiveFilters: boolean;
  /**
   * When provided (coach/admin only), each card renders an edit affordance
   * that calls this callback with the exercise to edit.
   */
  onEdit?: OnEditExercise;
  /**
   * When provided (coach/admin only), each card renders an "adjuntar a una
   * sesión" affordance (feature 032, T017).
   */
  onAttach?: OnAttachExercise;
  /** Id of the exercise currently being attached, if any (feature 032, T017). */
  attachingExerciseId?: number | null;
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
  onEdit,
  onAttach,
  attachingExerciseId,
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
      emptyState={
        hasActiveFilters
          ? {
              title: "Sin resultados para estos filtros",
              description: "Ajusta o limpia los filtros para ver más ejercicios.",
            }
          : {
              title: "El catálogo está vacío",
              description: "Aún no hay ejercicios registrados en esta biblioteca.",
            }
      }
      renderCard={(exercise) => (
        <ExerciseCard
          exercise={exercise}
          onEdit={onEdit}
          onAttach={onAttach}
          isAttaching={attachingExerciseId === exercise.id}
        />
      )}
      getItemKey={(exercise) => exercise.id}
    />
  );
}

export default CatalogGrid;
