import { PHVBadge } from "@/components/shared/PHVBadge";
import type { AthleteDetailOut } from "@/types/athlete.types";

interface AthleteInfoCardProps {
  athlete: AthleteDetailOut;
}

export function AthleteInfoCard({ athlete }: AthleteInfoCardProps) {
  const latest = athlete.latest_anthropometry;

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5">
      <h2 className="text-xl font-semibold text-slate-900">
        {athlete.first_name} {athlete.last_name}
      </h2>
      <div className="mt-3 flex flex-wrap gap-4 text-sm text-slate-700">
        <p>Edad: {athlete.age_decimal?.toFixed(1) ?? "-"} anos</p>
        <p>Sexo: {athlete.sex}</p>
        <p>Categoria: {athlete.category ?? "Sin categoria"}</p>
        <p>En club: {athlete.years_in_club != null ? `${athlete.years_in_club.toFixed(1)} años` : "—"}</p>
      </div>

      {latest ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
          <p className="mb-2 text-slate-700">Ultima evaluacion: {latest.evaluation_date}</p>
          <PHVBadge status={latest.maturation_status} />
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Sin evaluacion antropometrica registrada.</p>
      )}
    </article>
  );
}
