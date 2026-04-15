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
  const isParent = user?.role === UserRole.parent;

  return (
    <div className="flex min-h-screen bg-white text-charcoal">
      {/* Sidebar */}
      <aside
        className="w-64 shrink-0 bg-white px-4 py-5"
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 1px 0px 0px 0px" }}
      >
        {/* Logo */}
        <div className="mb-8 px-2">
          <h2
            className="text-lg text-charcoal"
            style={{ fontFamily: "'Cal Sans', system-ui, sans-serif", fontWeight: 600 }}
          >
            Trocha y Ruta
          </h2>
          <p className="mt-0.5 text-xs text-mid-gray">Club Ciclismo XCO</p>
        </div>

        {/* Nav */}
        <nav className="flex flex-col gap-1">
          {!isParent && (
            <NavLink
              to="/dashboard"
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-charcoal text-white"
                    : "text-mid-gray hover:bg-light-gray hover:text-charcoal"
                }`
              }
            >
              Dashboard
            </NavLink>
          )}
          {isCoach && (
            <NavLink
              to="/athletes"
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-charcoal text-white"
                    : "text-mid-gray hover:bg-light-gray hover:text-charcoal"
                }`
              }
            >
              Atletas
            </NavLink>
          )}
          {isCoach && (
            <NavLink
              to="/parents"
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-charcoal text-white"
                    : "text-mid-gray hover:bg-light-gray hover:text-charcoal"
                }`
              }
            >
              Padres
            </NavLink>
          )}
          {isParent && (
            <NavLink
              to="/my-athletes"
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-charcoal text-white"
                    : "text-mid-gray hover:bg-light-gray hover:text-charcoal"
                }`
              }
            >
              Mis Atletas
            </NavLink>
          )}
        </nav>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header
          className="flex items-center justify-between bg-white px-6 py-3"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 1px 0px 0px" }}
        >
          <p className="text-sm font-medium text-mid-gray">
            {user ? `${user.first_name} ${user.last_name}` : "Usuario"}
          </p>
          <button
            type="button"
            onClick={logout}
            className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
            style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
          >
            Cerrar sesión
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
