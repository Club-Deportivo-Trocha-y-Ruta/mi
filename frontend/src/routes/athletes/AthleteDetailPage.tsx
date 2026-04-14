import { Link, useParams } from "react-router-dom";

import { AthleteInfoCard } from "@/components/athletes/AthleteInfoCard";
import { useAthlete } from "@/hooks/athletes/useAthlete";

export function AthleteDetailPage() {
  const { id } = useParams();
  const athleteId = Number(id);
  const athleteQuery = useAthlete(athleteId, Number.isFinite(athleteId));

  if (athleteQuery.isLoading) {
    return (
      <section className="space-y-3">
        <div className="h-6 w-48 animate-pulse rounded bg-slate-200" />
        <div className="h-40 animate-pulse rounded-lg bg-slate-100" />
      </section>
    );
  }

  if (athleteQuery.isError) {
    return (
      <section className="space-y-3">
        <h1 className="text-2xl font-bold">Atleta no encontrado</h1>
        <p className="text-sm text-slate-600">
          No existe un atleta con ese ID o no tienes permisos para verlo.
        </p>
        <Link to="/athletes" className="text-sm font-medium text-slate-900 hover:underline">
          Volver a la lista
        </Link>
      </section>
    );
  }

  if (!athleteQuery.data) return null;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to="/athletes" className="text-sm text-slate-600 hover:text-slate-900">
          ← Volver a lista
        </Link>
        <Link
          to={`/athletes/${athleteQuery.data.id}/edit`}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100"
        >
          Editar atleta
        </Link>
      </div>

      <AthleteInfoCard athlete={athleteQuery.data} />

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-3 border-b border-slate-200 pb-2 text-sm font-medium text-slate-700">
          Antropometria
        </div>
        <p className="text-sm text-slate-500">Proximamente en Paso 8.</p>
      </div>
    </section>
  );
}
