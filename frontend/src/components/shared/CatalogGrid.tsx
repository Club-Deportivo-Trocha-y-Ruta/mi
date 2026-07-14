/**
 * CatalogGrid — cuadrícula de tarjetas de catálogo genérica (feature 033 /
 * T040).
 *
 * Extraído de `components/technique/CatalogGrid.tsx` y
 * `components/strength/CatalogGrid.tsx` (fuerza documentado como "Mirror de
 * `components/technique/CatalogGrid.tsx`"), unificando los mismos cuatro
 * estados:
 *   - loading  → skeletons accesibles (role="status" wrapper + aria-busy)
 *   - error    → `ErrorState` compartido (detecta cold-start via
 *                `isColdStartError`, reemplazando el `resolveErrorMessage`
 *                que cada módulo reimplementaba por separado)
 *   - empty    → `EmptyState` compartido; el título/descripción (sin
 *                resultados con filtros vs. catálogo vacío vs. combinación
 *                dispersa conocida de fuerza) los decide el llamador, que ya
 *                conoce su propia lógica de dominio
 *   - success  → grid responsive 1 → 2 → 3 col, renderizando cada item con
 *                `renderCard` (normalmente `LibraryEntityCard`)
 *
 * Genérico sobre `T` — no conoce la forma de un ejercicio de técnica ni de
 * fuerza. Presentacional: recibe los datos ya resueltos y los estados de
 * carga/error como props desde la página contenedora.
 */
import type { ReactNode } from "react";
import { cloneElement, isValidElement } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState, isColdStartError } from "@/components/shared/ErrorState";
import { Skeleton } from "@/components/ui/skeleton";

// ---------------------------------------------------------------------------
// Skeleton placeholder cards
// ---------------------------------------------------------------------------

function CardSkeleton() {
  return (
    <div className="rounded-xl border border-border-gray bg-white p-4 shadow-card">
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

interface CatalogGridEmptyState {
  title: string;
  description?: string;
}

interface CatalogGridProps<T> {
  items: T[] | undefined;
  total?: number;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  /** Static, non-cold-start error copy — falls back to `ErrorState`'s own default when omitted. */
  errorMessage?: string;
  onRetry?: () => void | Promise<void>;
  /** Renders a single item — normally a `LibraryEntityCard`. */
  renderCard: (item: T) => ReactNode;
  getItemKey: (item: T) => string | number;
  /**
   * Empty-state copy, decided by the caller (it already knows whether
   * filters are active, or — fuerza's case — whether the empty result is a
   * known-sparse, expected combination rather than a real "no results").
   */
  emptyState: CatalogGridEmptyState;
  /** aria-label on the loading grid. Default "Cargando catálogo de ejercicios…". */
  loadingLabel?: string;
  skeletonCount?: number;
  /** aria-label on the success grid, given the item count. */
  gridAriaLabel?: (count: number) => string;
  /** "N ejercicios" summary line above the grid, given `total`. */
  totalLabel?: (total: number) => string;
  gridClassName?: string;
}

const DEFAULT_GRID_CLASSNAME = "grid gap-4 sm:grid-cols-2 lg:grid-cols-3";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CatalogGrid<T>({
  items,
  total,
  isLoading,
  isFetching,
  isError,
  error,
  errorMessage,
  onRetry,
  renderCard,
  getItemKey,
  emptyState,
  loadingLabel = "Cargando catálogo de ejercicios…",
  skeletonCount = 9,
  gridAriaLabel = (count) => `Catálogo: ${count} ejercicios`,
  totalLabel = (t) => `${t} ejercicios`,
  gridClassName = DEFAULT_GRID_CLASSNAME,
}: CatalogGridProps<T>) {
  // Loading state — initial fetch
  if (isLoading) {
    return (
      <div role="status" aria-busy="true" aria-label={loadingLabel} className={gridClassName}>
        {Array.from({ length: skeletonCount }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    );
  }

  // Error state
  if (isError) {
    return <ErrorState message={errorMessage} onRetry={onRetry} isColdStart={isColdStartError(error)} />;
  }

  // Empty state — no results
  if (!items || items.length === 0) {
    return <EmptyState title={emptyState.title} description={emptyState.description} />;
  }

  return (
    <div>
      {/* Total + refetch indicator */}
      <p className="mb-3 text-xs text-text-disclaimer">
        {total !== undefined ? totalLabel(total) : ""}
        {isFetching && !isLoading ? " · Actualizando…" : ""}
      </p>

      <div className={gridClassName} aria-label={gridAriaLabel(items.length)}>
        {items.map((item) => {
          const node = renderCard(item);
          const key = getItemKey(item);
          // Inject the key onto the rendered element (normally a `LibraryEntityCard`)
          // rather than adding a wrapper <div> that would become an extra grid child.
          return isValidElement(node) ? cloneElement(node, { key }) : <div key={key}>{node}</div>;
        })}
      </div>
    </div>
  );
}

export default CatalogGrid;
