import { Link } from "react-router-dom";

import { MaturationStatus } from "@/types/enums";
import type { AthleteOut } from "@/types/athlete.types";

export interface AthleteRow extends AthleteOut {
  latest_maturation_status: MaturationStatus | null;
}

interface AthletesTableProps {
  items: AthleteRow[];
}

function phvBadgeClass(status: MaturationStatus | null): string {
  if (status === MaturationStatus.PrePHV) return "bg-emerald-100 text-emerald-800";
  if (status === MaturationStatus.CircaPHV) return "bg-amber-100 text-amber-800";
  if (status === MaturationStatus.PostPHV) return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-700";
}

export function AthletesTable({ items }: AthletesTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-slate-600">
          <tr>
            <th className="px-4 py-3 font-medium">Nombre</th>
            <th className="px-4 py-3 font-medium">Edad</th>
            <th className="px-4 py-3 font-medium">Sexo</th>
            <th className="px-4 py-3 font-medium">Categoria</th>
            <th className="px-4 py-3 font-medium">Estado PHV</th>
            <th className="px-4 py-3 font-medium">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {items.map((athlete) => (
            <tr key={athlete.id} className="border-t border-slate-100">
              <td className="px-4 py-3 font-medium text-slate-900">
                <Link to={`/athletes/${athlete.id}`} className="hover:underline">
                  {athlete.first_name} {athlete.last_name}
                </Link>
              </td>
              <td className="px-4 py-3">{athlete.age_decimal?.toFixed(1) ?? "-"} anos</td>
              <td className="px-4 py-3">{athlete.sex}</td>
              <td className="px-4 py-3">
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs">
                  {athlete.category ?? "Sin categoria"}
                </span>
              </td>
              <td className="px-4 py-3">
                <span
                  className={`rounded-full px-2 py-1 text-xs font-medium ${phvBadgeClass(athlete.latest_maturation_status)}`}
                >
                  {athlete.latest_maturation_status ?? "Sin evaluar"}
                </span>
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  <Link
                    to={`/athletes/${athlete.id}`}
                    className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
                  >
                    Ver
                  </Link>
                  <Link
                    to={`/athletes/${athlete.id}/edit`}
                    className="rounded-md border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
                  >
                    Editar
                  </Link>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
