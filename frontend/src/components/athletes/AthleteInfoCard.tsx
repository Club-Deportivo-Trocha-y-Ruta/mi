import { Link } from "react-router-dom";
import { ArrowLeft, Calendar, Pencil, Ruler, Scale } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PHVBadge } from "@/components/shared/PHVBadge";
import type { AthleteDetailOut } from "@/types/athlete.types";

interface AthleteInfoCardProps {
  athlete: AthleteDetailOut;
  /** Ruta del botón "Volver a lista". null = ocultar. Default: "/athletes" */
  backUrl?: string | null;
  /** Ruta del botón "Editar". null = ocultar. Default: "/athletes/:id/edit" */
  editUrl?: string | null;
}

function StatPill({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div
      className="flex items-center gap-1.5 rounded-lg bg-light-gray px-3 py-1.5 text-sm"
    >
      <Icon size={14} className="text-mid-gray" />
      <span className="text-mid-gray">{label}</span>
      <span className="font-semibold text-charcoal">{value}</span>
    </div>
  );
}

export function AthleteInfoCard({
  athlete,
  backUrl = "/athletes",
  editUrl,
}: AthleteInfoCardProps) {
  const resolvedEditUrl = editUrl === undefined ? `/athletes/${athlete.id}/edit` : editUrl;
  const latest = athlete.latest_anthropometry;
  const initials = `${athlete.first_name.charAt(0)}${athlete.last_name.charAt(0)}`.toUpperCase();

  return (
    <article className="overflow-hidden rounded-xl bg-white shadow-card">
      {/* Top bar: navigation */}
      {(backUrl !== null || resolvedEditUrl !== null) && (
        <div
          className="flex items-center justify-between px-5 pt-4 pb-3"
          style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.06)" }}
        >
          {backUrl !== null ? (
            <Link
              to={backUrl}
              className="flex items-center gap-1.5 text-sm text-mid-gray transition-colors hover:text-charcoal"
            >
              <ArrowLeft size={16} />
              Volver a lista
            </Link>
          ) : (
            <span />
          )}
          {resolvedEditUrl !== null && (
            <Link
              to={resolvedEditUrl}
              className="flex items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
            >
              <Pencil size={14} />
              Editar
            </Link>
          )}
        </div>
      )}

      {/* Hero content */}
      <div className="px-5 py-4">
        <div className="flex items-start gap-4">
          {/* Avatar */}
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-light-gray text-lg font-bold text-charcoal">
            {initials}
          </div>

          {/* Name + subtitle */}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <h2
                className="font-display truncate text-xl text-charcoal"
                style={{ letterSpacing: "0.2px" }}
              >
                {athlete.first_name} {athlete.last_name}
              </h2>
              <PHVBadge status={latest?.maturation_status ?? null} size="md" />
            </div>
            <p className="mt-1 text-sm text-mid-gray">
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
