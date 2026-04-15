import { Link } from "react-router-dom";
import { ArrowLeft, Calendar, Pencil, Ruler, Scale } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PHVBadge } from "@/components/shared/PHVBadge";
import type { AthleteDetailOut } from "@/types/athlete.types";

interface AthleteInfoCardProps {
  athlete: AthleteDetailOut;
}

function StatPill({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-1.5 text-sm">
      <Icon size={14} className="text-slate-400" />
      <span className="text-slate-500">{label}</span>
      <span className="font-semibold text-slate-800">{value}</span>
    </div>
  );
}

export function AthleteInfoCard({ athlete }: AthleteInfoCardProps) {
  const latest = athlete.latest_anthropometry;
  const initials = `${athlete.first_name.charAt(0)}${athlete.last_name.charAt(0)}`.toUpperCase();

  return (
    <article className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Top bar: navigation */}
      <div className="flex items-center justify-between px-5 pt-4">
        <Link
          to="/athletes"
          className="flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-slate-900"
        >
          <ArrowLeft size={16} />
          Volver a lista
        </Link>
        <Link
          to={`/athletes/${athlete.id}/edit`}
          className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-50"
        >
          <Pencil size={14} />
          Editar
        </Link>
      </div>

      {/* Hero content */}
      <div className="px-5 pb-5 pt-4">
        <div className="flex items-start gap-4">
          {/* Avatar */}
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-slate-100 text-lg font-bold text-slate-600">
            {initials}
          </div>

          {/* Name + subtitle */}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="truncate text-xl font-bold text-slate-900">
                {athlete.first_name} {athlete.last_name}
              </h2>
              <PHVBadge status={latest?.maturation_status ?? null} size="md" />
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {athlete.age_decimal?.toFixed(1) ?? "—"} años
              {" · "}
              {athlete.category ?? "Sin categoría"}
              {" · "}
              {athlete.sex === "M" ? "Masculino" : "Femenino"}
            </p>
          </div>
        </div>

        {/* Stat pills */}
        <div className="mt-4 flex flex-wrap gap-2">
          {athlete.years_in_club != null && (
            <StatPill icon={Calendar} label="En club" value={`${athlete.years_in_club.toFixed(1)} años`} />
          )}
          {latest && (
            <>
              <StatPill icon={Ruler} label="Talla" value={`${latest.standing_height_cm} cm`} />
              <StatPill icon={Scale} label="Peso" value={`${latest.weight_kg} kg`} />
            </>
          )}
        </div>
      </div>
    </article>
  );
}
