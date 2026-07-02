/**
 * CatalogGrid — renderiza una cuadrícula de ExerciseCard para el catálogo de
 * Fuerza y Acondicionamiento (feature 021 / T016).
 *
 * Estados:
 *   - loading  → skeletons accesibles (role="status" wrapper + aria-busy)
 *   - error    → mensaje de error con variante cold-start para 503 / timeout
 *   - empty    → estado diferenciado: sin resultados con filtros activos vs.
 *                catálogo vacío (incluye combinación válida sin ejercicios,
 *                p.ej. equipo_gym × 10-12, ver data-model.md)
 *   - success  → grid responsive 1 → 2 → 3 col
 *
 * Mirror de `components/technique/CatalogGrid.tsx`. Componente presentacional:
 * recibe los datos ya resueltos y los estados de carga/error como props desde
 * CatalogPage.
 */
import { Skeleton } from "@/components/ui/skeleton";
import { ExerciseCard, type StrengthExerciseListItem } from "./ExerciseCard";

// ---------------------------------------------------------------------------
// Skeleton placeholder cards
// ---------------------------------------------------------------------------

function CardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-ring-soft">
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
  isSparseKnownCombo = false,
}: CatalogGridProps) {
  // Loading state — initial fetch
  if (isLoading) {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label="Cargando catálogo de ejercicios de fuerza…"
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
        {isSparseKnownCombo ? (
          <>
            <p className="text-sm font-medium text-slate-700">
              Aún no hay ejercicios con equipo de gimnasio para 10–12 años
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Para esta franja de edad el club solo trabaja con ejercicios
              sin equipo (fortalecimiento con el propio peso corporal). Prueba
              el filtro &ldquo;Sin equipo&rdquo; para ver las opciones
              disponibles.
            </p>
          </>
        ) : hasActiveFilters ? (
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
          <ExerciseCard key={exercise.id} exercise={exercise} />
        ))}
      </div>
    </div>
  );
}

export default CatalogGrid;
