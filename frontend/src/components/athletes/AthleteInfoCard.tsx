import type { AthleteDetailOut } from "@/types/athlete.types";
import { MaturationStatus } from "@/types/enums";

interface AthleteInfoCardProps {
  athlete: AthleteDetailOut;
}

function badgeClass(status: MaturationStatus | null): string {
  if (status === MaturationStatus.PrePHV) return "bg-emerald-100 text-emerald-800";
  if (status === MaturationStatus.CircaPHV) return "bg-amber-100 text-amber-800";
  if (status === MaturationStatus.PostPHV) return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-700";
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
        <p>En club: {athlete.years_in_club ?? 0} anos</p>
      </div>

      {latest ? (
        <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
          <p className="mb-2 text-slate-700">Ultima evaluacion: {latest.evaluation_date}</p>
          <span
            className={`rounded-full px-2 py-1 text-xs font-medium ${badgeClass(latest.maturation_status)}`}
          >
            {latest.maturation_status}
          </span>
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Sin evaluacion antropometrica registrada.</p>
      )}
    </article>
  );
}
