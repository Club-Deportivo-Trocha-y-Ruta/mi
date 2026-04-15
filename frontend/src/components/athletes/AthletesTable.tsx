import { Link } from "react-router-dom";

import { PHVBadge } from "@/components/shared/PHVBadge";
import { MaturationStatus } from "@/types/enums";
import type { AthleteOut } from "@/types/athlete.types";

export interface AthleteRow extends AthleteOut {
  latest_maturation_status: MaturationStatus | null;
}

interface AthletesTableProps {
  items: AthleteRow[];
}

export function AthletesTable({ items }: AthletesTableProps) {
  return (
    <div
      className="overflow-x-auto rounded-xl bg-white"
      style={{
        boxShadow:
          "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px",
      }}
    >
      <table className="min-w-full text-sm">
        <thead className="text-left" style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}>
          <tr>
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">Nombre</th>
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">Edad</th>
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">Sexo</th>
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">Categoría</th>
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">Estado PHV</th>
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {items.map((athlete) => (
            <tr
              key={athlete.id}
              className="transition-colors hover:bg-light-gray"
              style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
            >
              <td className="px-4 py-3 font-medium text-charcoal">
                <Link to={`/athletes/${athlete.id}`} className="transition-opacity hover:opacity-70">
                  {athlete.first_name} {athlete.last_name}
                </Link>
              </td>
              <td className="px-4 py-3 text-mid-gray">{athlete.age_decimal?.toFixed(1) ?? "-"} años</td>
              <td className="px-4 py-3 text-mid-gray">{athlete.sex}</td>
              <td className="px-4 py-3">
                <span
                  className="rounded-full bg-light-gray px-2.5 py-1 text-xs font-medium text-charcoal"
                >
                  {athlete.category ?? "Sin categoría"}
                </span>
              </td>
              <td className="px-4 py-3">
                <PHVBadge status={athlete.latest_maturation_status} />
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  <Link
                    to={`/athletes/${athlete.id}`}
                    className="rounded-lg bg-white px-3 py-1 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
                  >
                    Ver
                  </Link>
                  <Link
                    to={`/athletes/${athlete.id}/edit`}
                    className="rounded-lg bg-white px-3 py-1 text-xs font-medium text-charcoal transition-opacity hover:opacity-70"
                    style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
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
