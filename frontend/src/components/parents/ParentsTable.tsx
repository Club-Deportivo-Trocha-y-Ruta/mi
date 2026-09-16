import { Link } from "react-router-dom";

import { TableScrollContainer } from "@/components/ui/table";
import type { UserOut } from "@/types/user.types";

interface ParentsTableProps {
  items: UserOut[];
}

export function ParentsTable({ items }: ParentsTableProps) {
  return (
    <>
      {/* Cards móvil (<md) — F-10: no había vista de cards; ocultaba Estado
          y Acciones desde 390px sin ningún indicador. */}
      <ul role="list" className="flex flex-col gap-3 md:hidden">
        {items.map((parent) => (
          <li key={parent.id}>
            <div className="rounded-xl bg-white p-4 space-y-2 shadow-card">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link
                    to={`/parents/${parent.id}`}
                    className="block truncate text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
                  >
                    {parent.first_name} {parent.last_name}
                  </Link>
                  <p className="truncate text-xs text-mid-gray">{parent.email ?? "—"}</p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${
                    parent.is_active
                      ? "bg-green-50 text-green-700"
                      : "bg-light-gray text-mid-gray"
                  }`}
                >
                  {parent.is_active ? "Activo" : "Inactivo"}
                </span>
              </div>
              <p className="text-xs text-mid-gray">{parent.phone ?? "—"}</p>
              <Link
                to={`/parents/${parent.id}`}
                className="flex min-h-12 items-center justify-center rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
              >
                Ver
              </Link>
            </div>
          </li>
        ))}
      </ul>

      {/* Tabla desktop (≥md) */}
      <div className="hidden rounded-xl bg-white shadow-card md:block">
        <TableScrollContainer className="rounded-xl">
          <table className="min-w-[480px] w-full text-sm">
            <thead
              className="text-left"
              style={{ borderBottom: "1px solid rgba(34, 42, 53, 0.08)" }}
            >
              <tr>
                <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Nombre
                </th>
                <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Email
                </th>
                {/* Columna secundaria: se oculta entre md y lg (F-10) para
                    que Acciones quede visible sin necesidad de scroll. */}
                <th className="hidden lg:table-cell px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Teléfono
                </th>
                <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Estado
                </th>
                <th className="sticky right-0 z-10 bg-white px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((parent) => (
                <tr
                  key={parent.id}
                  className="group transition-colors hover:bg-light-gray"
                  style={{ borderTop: "1px solid rgba(34, 42, 53, 0.06)" }}
                >
                  <td className="px-4 py-3 font-medium text-charcoal">
                    <Link
                      to={`/parents/${parent.id}`}
                      className="transition-opacity hover:opacity-70"
                    >
                      {parent.first_name} {parent.last_name}
                    </Link>
                  </td>
                  <td className="max-w-[180px] truncate px-4 py-3 text-mid-gray">{parent.email ?? "—"}</td>
                  <td className="hidden lg:table-cell px-4 py-3 text-mid-gray">{parent.phone ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                        parent.is_active
                          ? "bg-green-50 text-green-700"
                          : "bg-light-gray text-mid-gray"
                      }`}
                    >
                      {parent.is_active ? "Activo" : "Inactivo"}
                    </span>
                  </td>
                  <td className="sticky right-0 bg-white px-4 py-3 group-hover:bg-light-gray">
                    <Link
                      to={`/parents/${parent.id}`}
                      className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-charcoal transition-opacity hover:opacity-70 shadow-ring"
                    >
                      Ver
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScrollContainer>
      </div>
    </>
  );
}
