import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const isCoach = user?.role === UserRole.coach;

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      <aside className="w-64 border-r border-slate-200 bg-white p-4">
        <h2 className="mb-6 text-lg font-semibold">Trocha y Ruta</h2>
        <nav className="flex flex-col gap-2">
          <NavLink
            to="/dashboard"
            className={({ isActive }) =>
              `rounded-md px-3 py-2 text-sm ${isActive ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`
            }
          >
            Dashboard
          </NavLink>
          {isCoach && (
            <NavLink
              to="/athletes"
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm ${isActive ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`
              }
            >
              Atletas
            </NavLink>
          )}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <p className="text-sm text-slate-600">
            {user ? `${user.first_name} ${user.last_name}` : "Usuario"}
          </p>
          <button
            type="button"
            onClick={logout}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100"
          >
            Cerrar sesión
          </button>
        </header>

        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
