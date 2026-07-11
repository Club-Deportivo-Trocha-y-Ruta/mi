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
    <>
      {/* Vista mobile: lista de cards (<md) */}
      <ul role="list" className="flex flex-col gap-3 md:hidden">
        {items.map((athlete) => (
          <li key={athlete.id}>
            <div className="rounded-xl bg-white p-4 shadow-card">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/athletes/${athlete.id}`}
                    className="text-base font-medium text-charcoal transition-opacity hover:opacity-70"
                  >
                    {athlete.first_name} {athlete.last_name}
                  </Link>
                  <p className="mt-0.5 text-sm text-mid-gray">
                    {athlete.age_decimal?.toFixed(1) ?? "-"} años · {athlete.sex}
                  </p>
                </div>
                <PHVBadge status={athlete.latest_maturation_status} />
              </div>

              <div className="mt-2">
                <span className="rounded-full bg-light-gray px-2.5 py-1 text-xs font-medium text-charcoal">
                  {athlete.category ?? "Sin categoría"}
                </span>
              </div>

              <div className="mt-3 flex gap-2">
                <Link
                  to={`/athletes/${athlete.id}`}
                  aria-label={`Ver detalle de ${athlete.first_name} ${athlete.last_name}`}
                  className="flex-1 rounded-lg bg-white py-3 text-center text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
                >
                  Ver
                </Link>
                <Link
                  to={`/athletes/${athlete.id}/edit`}
                  aria-label={`Editar a ${athlete.first_name} ${athlete.last_name}`}
                  className="flex-1 rounded-lg bg-white py-3 text-center text-sm font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
                >
                  Editar
                </Link>
              </div>
            </div>
          </li>
        ))}
      </ul>

      {/* Vista desktop: tabla (md+) */}
      <div className="hidden overflow-x-auto rounded-xl bg-white md:block shadow-card">
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
                  <span className="rounded-full bg-light-gray px-2.5 py-1 text-xs font-medium text-charcoal">
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
                      className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
                    >
                      Ver
                    </Link>
                    <Link
                      to={`/athletes/${athlete.id}/edit`}
                      className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
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
    </>
  );
}
