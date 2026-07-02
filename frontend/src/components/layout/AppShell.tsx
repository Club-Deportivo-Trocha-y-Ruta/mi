import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, Link } from "react-router-dom";

import { AthleteSwitcher } from "@/components/parents/AthleteSwitcher";
import { ServerWakingBanner } from "@/components/layout/ServerWakingBanner";
import { warmUp } from "@/api/client";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

interface AppShellProps {
  children: ReactNode;
}

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
    isActive
      ? "bg-charcoal text-white"
      : "text-mid-gray hover:bg-light-gray hover:text-charcoal"
  }`;

export function AppShell({ children }: AppShellProps) {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Feature 012, US2: pre-calienta el backend al montar el shell autenticado
  // (una sola vez por carga) para acortar el cold start de Render Free.
  useEffect(() => {
    warmUp();
  }, []);

  const isAdmin = user?.role === UserRole.admin;
  const isCoach = user?.role === UserRole.coach;
  const isParent = user?.role === UserRole.parent;

  const navLinks = (
    <nav className="flex flex-col gap-1">
      {!isParent && (
        <NavLink
          to="/dashboard"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Dashboard
        </NavLink>
      )}
      {isCoach && (
        <NavLink
          to="/athletes"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Atletas
        </NavLink>
      )}
      {isCoach && (
        <NavLink
          to="/parents"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Padres
        </NavLink>
      )}
      {(isCoach || isAdmin) && (
        <NavLink
          to="/calendar"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Calendario
        </NavLink>
      )}
      {(isCoach || isAdmin) && (
        <NavLink
          to="/training/sessions"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Entrenamientos
        </NavLink>
      )}
      {(isCoach || isAdmin) && (
        <NavLink
          to="/training/reports"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Reportes mensuales
        </NavLink>
      )}
      {(isCoach || isAdmin) && (
        <NavLink
          to="/training/athlete-newsletters"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Boletines Mensuales
        </NavLink>
      )}
      {(isCoach || isAdmin) && (
        <NavLink
          to="/competitions"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Competencias
        </NavLink>
      )}
      {(isCoach || isAdmin) && (
        <NavLink
          to="/anxiety"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Ansiedad competitiva
        </NavLink>
      )}
      {(isCoach || isAdmin) && (
        <NavLink
          to="/technique"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Técnica
        </NavLink>
      )}
      {(isCoach || isAdmin) && (
        <NavLink
          to="/strength"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Fuerza
        </NavLink>
      )}
      {isParent && (
        <NavLink
          to="/my-athletes"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Mis Atletas
        </NavLink>
      )}
      {isParent && (
        <NavLink
          to="/parents/calendar"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Calendario
        </NavLink>
      )}
      {isParent && (
        <NavLink
          to="/parents/training/sessions"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Entrenamientos
        </NavLink>
      )}
      {isParent && (
        <NavLink
          to="/parents/training/overview"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Resumen mensual
        </NavLink>
      )}
      {isAdmin && (
        <NavLink
          to="/admin/ai"
          className={navLinkClass}
          onClick={() => setSidebarOpen(false)}
        >
          Salud IA
        </NavLink>
      )}
    </nav>
  );

  return (
    <div className="flex min-h-screen overflow-x-hidden bg-white text-charcoal">
      {/* ── Skip link — first focusable element for keyboard / screen reader users.
            Permanece visualmente oculto hasta recibir foco. ── */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:rounded-lg focus:bg-charcoal focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-white focus:shadow-ring-soft focus:outline-none focus-visible:outline-none"
      >
        Saltar a contenido
      </a>

      {/* ── Mobile drawer overlay ── */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-midnight/40 md:hidden"
          aria-hidden="true"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Sidebar — hidden on mobile, drawer when open ── */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 shrink-0 bg-white px-4 py-5 transition-transform duration-200 md:static md:translate-x-0 md:z-auto ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 1px 0px 0px 0px" }}
        aria-label="Menú de navegación"
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

        {navLinks}
      </aside>

      {/* ── Main area ── */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Aviso de "servidor despertando" (cold start Render Free) */}
        <ServerWakingBanner />
        {/* Header */}
        <header
          className="sticky top-0 z-50 flex items-center justify-between bg-white px-4 py-3 md:px-6"
          style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 1px 0px 0px" }}
        >
          {/* Left: hamburger (mobile) + user name */}
          <div className="flex min-w-0 items-center gap-3">
            {/* Hamburger — visible only on mobile */}
            <button
              type="button"
              aria-label="Abrir menú"
              aria-expanded={sidebarOpen}
              onClick={() => setSidebarOpen(true)}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-charcoal transition-colors hover:bg-light-gray md:hidden"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 18 18"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M2 4.5h14M2 9h14M2 13.5h14"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </button>
            <p className="truncate text-sm font-medium text-mid-gray">
              {user ? `${user.first_name} ${user.last_name}` : "Usuario"}
            </p>
          </div>

          {/* Right: athlete switcher (parent only) + Mi perfil + logout */}
          <div className="flex items-center gap-2">
            {isParent && <AthleteSwitcher />}
            <Link
              to="/perfil"
              className="shrink-0 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
              style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            >
              Mi perfil
            </Link>
            <button
              type="button"
              onClick={logout}
              className="shrink-0 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-charcoal transition-opacity hover:opacity-70"
              style={{ boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" }}
            >
              Cerrar sesión
            </button>
          </div>
        </header>

        {/* Page content */}
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-y-auto p-4 md:p-6 focus:outline-none"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
