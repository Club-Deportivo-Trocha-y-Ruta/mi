import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { AthleteSwitcher } from "@/components/parents/AthleteSwitcher";
import { ParentBottomNav } from "@/components/parents/ParentBottomNav";
import { ParentSidebar } from "@/components/parents/ParentSidebar";
import { ServerWakingBanner } from "@/components/layout/ServerWakingBanner";
import { SidebarNav } from "@/components/layout/SidebarNav";
import { BottomNav } from "@/components/layout/BottomNav";
import { MoreSheet } from "@/components/layout/MoreSheet";
import { KeyboardShortcutsDialog } from "@/components/layout/KeyboardShortcutsDialog";
import { UserMenu } from "@/components/layout/UserMenu";
import { QuickCreate } from "@/components/layout/QuickCreate";
import { warmUp } from "@/api/client";
import { useKeyboardShortcuts } from "@/hooks/layout/useKeyboardShortcuts";
import { useSidebarCollapsed } from "@/hooks/layout/useSidebarCollapsed";
import { useAuthStore } from "@/store/auth.store";
import { CLUB_LOCALE, CLUB_TIMEZONE } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import { UserRole } from "@/types/enums";
import type { NavRole } from "@/lib/navigation";
import {
  applyCoachTheme,
  applyParentSurfaceTheme,
  getStoredThemePreference,
} from "@/lib/theme";

interface AppShellProps {
  children: ReactNode;
}

/**
 * "jueves 27 de agosto de 2026" — hoy en la TZ del club, para el slot
 * izquierdo del header de entrenador/admin (feature 035, `Main.dc.html`):
 * ese lado quedó vacío al mudarse la tarjeta de usuario al pie de la barra,
 * y la fecha no aparece en ninguna otra parte del Inicio (el subtítulo del
 * saludo sólo lleva el número de semana ISO).
 *
 * Se compone en dos formateos en vez de reusar `formatFullDate`: es-CO
 * inserta una coma tras el día de semana ("jueves, 27 de…") y el mockup no
 * la lleva.
 */
function clubTodayLongLabel(): string {
  const now = new Date();
  const weekday = new Intl.DateTimeFormat(CLUB_LOCALE, {
    weekday: "long",
    timeZone: CLUB_TIMEZONE,
  }).format(now);
  const dayMonthYear = new Intl.DateTimeFormat(CLUB_LOCALE, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: CLUB_TIMEZONE,
  }).format(now);
  return `${weekday} ${dayMonthYear}`;
}

export function AppShell({ children }: AppShellProps) {
  const user = useAuthStore((state) => state.user);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Feature 030, US3: shared open state for the mobile <BottomNav>'s "Más"
  // trigger and the <MoreSheet> it opens (coach/admin only, < md).
  const [moreSheetOpen, setMoreSheetOpen] = useState(false);
  // Feature 035: riel de 72px ↔ barra de 256px (manual, persistido).
  const { collapsed, toggle: toggleCollapsed } = useSidebarCollapsed();

  // Feature 012, US2: pre-calienta el backend al montar el shell autenticado
  // (una sola vez por carga) para acortar el cold start de Render Free.
  useEffect(() => {
    warmUp();
  }, []);

  const isAdmin = user?.role === UserRole.admin;
  const isCoach = user?.role === UserRole.coach;
  const isParent = user?.role === UserRole.parent;

  // Coach/admin navigation is config-driven (feature 030, NAV_AREAS) — el
  // portal de familias tiene su propio par de componentes (feature 035:
  // <ParentSidebar> + <ParentBottomNav>), porque NavRole es coach/admin-only
  // por diseño (spec.md Assumptions).
  const navRole: NavRole | null = isAdmin ? "admin" : isCoach ? "coach" : null;

  // Feature 033, US5 (FR-008, optional story): dark mode "surface scope"
  // guardrail. AppShell is the one shared layout component rendered for
  // every authenticated role (ProtectedRoute.tsx) — it's the single place
  // that decides, from the *same* navRole/isParent this file already
  // computes above, whether to honor the coach's stored theme preference
  // or force light regardless (parent portal — out of scope for this
  // story, contracts/dark-theme-tokens.md). Only acts once the role is
  // definitively known (navRole or isParent), so a brief `user === null`
  // load window never flips `data-theme` away from what the index.html
  // pre-hydration script already set — avoids a flash either direction.
  useEffect(() => {
    if (navRole) {
      applyCoachTheme(getStoredThemePreference());
    } else if (isParent) {
      applyParentSurfaceTheme();
    }
  }, [navRole, isParent]);

  // Feature 033, US5 (T062/T063) — montados AQUÍ, y sólo aquí. El shell se
  // renderiza una vez por carga autenticada, así que los atajos globales
  // (`g`+letra, `n`, `?`) quedan registrados exactamente una vez en
  // cualquier viewport; antes vivían dentro de <UserMenu>, que desde la
  // feature 035 se monta dos veces (pie de la barra + header <md). `enabled`
  // los apaga por completo para el rol parent — el portal de familias no
  // tiene áreas NavArea a las que saltar.
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);
  const openShortcutsHelp = useCallback(() => setShortcutsHelpOpen(true), []);
  useKeyboardShortcuts({
    role: navRole ?? "coach",
    enabled: navRole !== null,
    onOpenShortcutsHelp: openShortcutsHelp,
  });

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  return (
    <div className="flex min-h-screen overflow-x-hidden bg-page-plane text-charcoal">
      {/* bg-page-plane (feature 033, US5): same #ffffff as bg-white in light
          mode (no visible change) but a darker backdrop than card/header/
          sidebar surfaces in dark mode — see style.css's dark token block
          for the elevation rationale. */}
      {/* ── Skip link — first focusable element for keyboard / screen reader users.
            Permanece visualmente oculto hasta recibir foco. ── */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:rounded-lg focus:bg-charcoal focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-white focus:shadow-card focus:outline-none focus-visible:outline-none"
      >
        Saltar a contenido
      </a>

      {/* ── Mobile drawer overlay — parent role only; coach/admin use <BottomNav>/<MoreSheet> instead (feature 030, US3). ── */}
      {sidebarOpen && !navRole && (
        <div
          className="fixed inset-0 z-30 bg-midnight/40 md:hidden"
          aria-hidden="true"
          onClick={closeSidebar}
        />
      )}

      {/* ── Sidebar — coach/admin: hidden below md, static at md+ (bottom bar
            replaces the mobile drawer), y con dos anchos (feature 035): 256px
            expandida o riel de 72px. El riel NO lleva padding horizontal — la
            barra activa de 3px se apoya en el borde mismo del riel
            (NavEntrenador.dc.html). Parent: unchanged mobile drawer, con
            <ParentSidebar> adentro (que trae su propio padding). ── */}
      <aside
        className={cn(
          "shrink-0 flex-col bg-white",
          navRole
            ? [
                "hidden pt-5 pb-4 transition-[width] duration-200 md:flex",
                collapsed ? "w-[72px]" : "w-64 px-4",
              ]
            : [
                // z-[55]: bajo md el drawer tiene que ser la superficie más
                // alta de todo el alto del viewport — por encima del header
                // `sticky z-50` (o su X quedaría tapado y sin poder tocarse)
                // y por encima de <ParentBottomNav> `z-40` (que si no,
                // al ir después en el DOM, se pintaría sobre el pie del
                // drawer y se comería esos toques). Sigue por debajo del
                // skip link (`z-[60]`), que debe ganarle a todo.
                "fixed inset-y-0 left-0 z-[55] flex w-64 transition-transform duration-200 md:static md:z-auto md:translate-x-0",
                sidebarOpen ? "translate-x-0" : "-translate-x-full",
              ],
        )}
        style={{ boxShadow: "rgba(34, 42, 53, 0.08) 1px 0px 0px 0px" }}
        aria-label="Menú de navegación"
      >
        {navRole && (
          <SidebarNav
            role={navRole}
            collapsed={collapsed}
            onToggleCollapsed={toggleCollapsed}
            onNavigate={closeSidebar}
            footer={
              <UserMenu
                role={navRole}
                variant={collapsed ? "sidebarRail" : "sidebar"}
                onOpenShortcutsHelp={openShortcutsHelp}
              />
            }
          />
        )}
        {/* `isParent` y no `!navRole`: mientras el rol aún no se conoce
            (user === null tras un refresh, ver ProtectedRoute) la barra queda
            vacía en vez de disparar las queries del portal de familias. */}
        {isParent && (
          <ParentSidebar onNavigate={closeSidebar} onClose={closeSidebar} />
        )}
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
          {/* Left: hamburger (mobile, parent only) + nombre de usuario
              (parent) / fecha de hoy (coach/admin) */}
          <div className="flex min-w-0 items-center gap-3">
            {/* Hamburger — parent role only; coach/admin use <BottomNav>/<MoreSheet> instead (feature 030, US3). */}
            {!navRole && (
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
            )}
            {/* Coach/admin: el nombre vive en la tarjeta de usuario del pie de
                la barra lateral (feature 035) — este slot lo ocupa la fecha
                de hoy, como en el mockup. Parent: el nombre, como siempre. */}
            {navRole ? (
              <p
                className="truncate text-[13px] text-mid-gray"
                data-testid="header-today-date"
              >
                {clubTodayLongLabel()}
              </p>
            ) : (
              <p className="truncate text-sm font-medium text-mid-gray">
                {user ? `${user.first_name} ${user.last_name}` : "Usuario"}
              </p>
            )}
          </div>

          {/* Right: coach/admin conservan «Crear» (feature 035: es la única
                acción del header en ≥md, porque el menú de usuario pasó al pie
                de la barra). El <UserMenu> del header sólo se muestra bajo md,
                donde no hay barra lateral. Parent: selector de atleta — «Mi
                perfil» y «Cerrar sesión» viven ahora en <ParentSidebar> y en
                la barra inferior. */}
          <div className="flex items-center gap-2">
            {navRole ? (
              <>
                <QuickCreate role={navRole} />
                <div className="md:hidden">
                  <UserMenu
                    role={navRole}
                    variant="header"
                    onOpenShortcutsHelp={openShortcutsHelp}
                  />
                </div>
              </>
            ) : (
              isParent && <AthleteSwitcher />
            )}
          </div>
        </header>

        {/* Page content — pb-24 en móvil para que la barra inferior (coach o
            familias) nunca tape el final del contenido. */}
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-y-auto p-4 pb-24 focus:outline-none md:p-6 md:pb-6"
        >
          {children}
        </main>
      </div>

      {/* ── Mobile bottom navigation — coach/admin (feature 030, US3) y
            familias (feature 035); ambas se ocultan solas en ≥md. ── */}
      {navRole && (
        <>
          <BottomNav
            role={navRole}
            open={moreSheetOpen}
            onOpenChange={setMoreSheetOpen}
          />
          <MoreSheet
            role={navRole}
            open={moreSheetOpen}
            onOpenChange={setMoreSheetOpen}
          />
        </>
      )}
      {isParent && <ParentBottomNav />}

      {/* ── Ayuda de atajos (feature 033, T063) — un único montaje por shell,
            abierto por la tecla `?` o por el item del menú de usuario. ── */}
      {navRole && (
        <KeyboardShortcutsDialog
          open={shortcutsHelpOpen}
          onOpenChange={setShortcutsHelpOpen}
        />
      )}
    </div>
  );
}
