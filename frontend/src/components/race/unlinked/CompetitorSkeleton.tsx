/**
 * CompetitorSkeleton — placeholder mientras carga la lista de unlinked.
 *
 * Renderiza un card con shimmer en header + chips + grid de 3 sugerencias.
 * Extraído de UnlinkedCompetitorsTab en B5.
 */
export function CompetitorSkeleton() {
  return (
    <div
      className="space-y-3 rounded-xl bg-white p-4 shadow-ring"
      data-testid="competitor-skeleton"
    >
      <div className="h-4 w-1/2 animate-pulse rounded-md bg-light-gray" />
      <div className="flex gap-2">
        <div className="h-4 w-16 animate-pulse rounded-full bg-light-gray" />
        <div className="h-4 w-20 animate-pulse rounded-full bg-light-gray" />
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg bg-light-gray/60"
          />
        ))}
      </div>
    </div>
  );
}
