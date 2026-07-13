/**
 * CatalogGrid — renderiza una cuadrícula de ExerciseCard (US1 / T014).
 *
 * Estados:
 *   - loading  → skeletons accesibles (role="status" wrapper + aria-busy)
 *   - error    → mensaje de error con variante cold-start para 503 / timeout
 *   - empty    → estado diferenciado: sin resultados con filtros activos vs.
 *                catálogo vacío
 *   - success  → grid responsive 1 → 2 → 3 col
 *
 * El componente es presentacional: recibe los datos ya resueltos y los estados
 * de carga/error como props desde CatalogPage.
 */
import { Skeleton } from "@/components/ui/skeleton";
import { ExerciseCard } from "./ExerciseCard";
import type { ExerciseListItem } from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Re-export the onEdit/onAttach callback types so callers share the same shape
// ---------------------------------------------------------------------------
export type OnEditExercise = (exercise: ExerciseListItem) => void;
export type OnAttachExercise = (exercise: ExerciseListItem) => void;

// ---------------------------------------------------------------------------
// Skeleton placeholder cards
// ---------------------------------------------------------------------------

function CardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-card">
      <Skeleton className="mb-2 h-4 w-3/4" />
      <Skeleton className="mb-3 h-3 w-full" />
      <Skeleton className="mb-2 h-3 w-1/2" />
      <div className="flex gap-1.5">
        <Skeleton className="h-5 w-14 rounded-full" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
    </div>
  );
}

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
// Error message helper
// ---------------------------------------------------------------------------

function resolveErrorMessage(error: unknown): string {
  // Detect Render cold-start / timeout
  if (error instanceof Error) {
    const msg = error.message.toLowerCase();
    if (
      msg.includes("timeout") ||
      msg.includes("network") ||
      msg.includes("503") ||
      msg.includes("502")
    ) {
      return "El servidor está iniciando, puede tomar hasta 60 segundos. Intenta de nuevo en un momento.";
    }
  }
  return "No se pudo cargar el catálogo. Intenta de nuevo.";
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
  // Loading state — initial fetch
  if (isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Cargando catálogo de ejercicios…"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {Array.from({ length: 9 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 p-6 text-center"
      >
        <p className="text-sm font-medium text-red-800">
          {resolveErrorMessage(error)}
        </p>
      </div>
    );
  }

  // Empty state — no results
  if (!items || items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
        {hasActiveFilters ? (
          <>
            <p className="text-sm font-medium text-slate-700">
              Sin resultados para estos filtros
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Ajusta o limpia los filtros para ver más ejercicios.
            </p>
          </>
        ) : (
          <>
            <p className="text-sm font-medium text-slate-700">
              El catálogo está vacío
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Aún no hay ejercicios registrados en esta biblioteca.
            </p>
          </>
        )}
      </div>
    );
  }

  return (
    <div>
      {/* Total + refetch indicator */}
      <p className="mb-3 text-xs text-slate-400">
        {total !== undefined ? `${total} ejercicios` : ""}
        {isFetching && !isLoading ? " · Actualizando…" : ""}
      </p>

      <div
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        aria-label={`Catálogo: ${items.length} ejercicios`}
      >
        {items.map((exercise) => (
          <ExerciseCard
            key={exercise.id}
            exercise={exercise}
            onEdit={onEdit}
            onAttach={onAttach}
            isAttaching={attachingExerciseId === exercise.id}
          />
        ))}
      </div>
    </div>
  );
}

export default CatalogGrid;
