/**
 * RouteFallback — Suspense fallback para rutas perezosas (lazy()).
 *
 * Anuncia el estado de carga UNA sola vez (`role="status"`, `aria-busy`)
 * para que lectores de pantalla no se vean inundados por skeletons
 * descendientes (que son aria-hidden por diseño).
 */
import { Skeleton } from "@/components/ui/skeleton";

export function RouteFallback() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando vista"
      className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-4"
    >
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-4 w-72" />
      <Skeleton className="h-32 w-full max-w-md" />
    </div>
  );
}
