import { ChildCard } from "@/components/parents/portal/ChildCard";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";

const CARD_SHADOW =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

function SkeletonCard() {
  return <div className="h-48 animate-pulse rounded-xl bg-light-gray" />;
}

export function ParentDashboardPage() {
  const { data: athletes, isLoading, isError } = useMyAthletes();

  return (
    <section className="space-y-6">
      <div>
        <h1
          className="text-2xl text-charcoal"
          style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
        >
          Mis Atletas
        </h1>
        <p className="mt-1 text-sm text-mid-gray">Seguimiento de tus deportistas</p>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {isError && !isLoading && (
        <div
          className="rounded-xl bg-white px-5 py-6"
          style={{ boxShadow: CARD_SHADOW }}
        >
          <p className="text-sm text-mid-gray">
            No fue posible cargar tus atletas. Intenta de nuevo.
          </p>
        </div>
      )}

      {!isLoading && !isError && athletes !== undefined && athletes.length === 0 && (
        <div
          className="rounded-xl bg-white px-5 py-6"
          style={{ boxShadow: CARD_SHADOW }}
        >
          <p className="text-sm text-mid-gray">
            No tienes atletas vinculados aún. Contacta a tu entrenador.
          </p>
        </div>
      )}

      {!isLoading && !isError && athletes && athletes.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {athletes.map((athlete) => (
            <ChildCard key={athlete.athlete_id} athlete={athlete} />
          ))}
        </div>
      )}
    </section>
  );
}
