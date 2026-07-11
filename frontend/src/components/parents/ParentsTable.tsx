import { Link } from "react-router-dom";

import type { UserOut } from "@/types/user.types";

interface ParentsTableProps {
  items: UserOut[];
}

export function ParentsTable({ items }: ParentsTableProps) {
  return (
    <div className="overflow-x-auto rounded-xl bg-white shadow-card">
      <table className="min-w-full min-w-[560px] text-sm">
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
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
              Teléfono
            </th>
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
              Estado
            </th>
            <th className="px-4 py-3 text-xs font-medium uppercase tracking-wide text-mid-gray">
              Acciones
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((parent) => (
            <tr
              key={parent.id}
              className="transition-colors hover:bg-light-gray"
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
              <td className="px-4 py-3 text-mid-gray">{parent.phone ?? "—"}</td>
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
              <td className="px-4 py-3">
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
    </div>
  );
}
