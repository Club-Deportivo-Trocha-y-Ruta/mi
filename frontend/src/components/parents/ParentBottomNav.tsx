/**
 * ParentBottomNav — Barra de navegación inferior fija para el portal de
 * familias en móvil (feature 035, mockup `PadresInicio.dc.html`).
 *
 * Modelada sobre `components/layout/BottomNav.tsx` (coach/admin): mismo
 * `<nav>` fijo, `md:hidden`, mismo tratamiento del "safe area" del gesto de
 * inicio de Android/iOS. Difiere en dos puntos deliberados del mockup de
 * padres:
 *   - Los cinco destinos son fijos — no hay disparador "Más": el portal de
 *     padres solo tiene 4 áreas + perfil, y todas caben en la barra.
 *   - El estado activo usa el acento teal (`--color-nav-accent`) en el ICONO,
 *     más una barra indicadora de 16×3px en el borde SUPERIOR del slot — así
 *     lo especifica el mockup. El label se queda en charcoal semibold: el
 *     acento sobre blanco da 4.45:1 y no alcanza el piso AA de 4.5:1 para
 *     texto normal (y menos aún al sol). Mismo reparto que `SidebarNav`.
 *
 * Resolución de activo: mismo algoritmo "exact-match primero, luego el
 * prefijo de ruta más largo gana" que `resolveActiveItemId`
 * (`lib/navigation.ts`), reimplementado localmente — el modelo de esa
 * librería es coach/admin-only (`NavRole = "coach" | "admin"`), así que no
 * aplica al portal de padres. Evita que `/parents/training/overview`
 * también encienda "Entrenos", y mantiene "Inicio" activo en subrutas como
 * `/my-athletes/:id`.
 */
import type { LucideIcon } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { BarChart3, CalendarDays, ClipboardList, Home, UserRound } from "lucide-react";

import { cn } from "@/lib/utils";

interface ParentNavSlot {
  id: string;
  label: string;
  to: string;
  icon: LucideIcon;
}

/** Orden de render — igual al mockup (Inicio, Calendario, Entrenos, Resumen, Perfil). */
const SLOTS: ParentNavSlot[] = [
  { id: "home", label: "Inicio", to: "/my-athletes", icon: Home },
  { id: "calendar", label: "Calendario", to: "/parents/calendar", icon: CalendarDays },
  {
    id: "sessions",
    label: "Entrenos",
    to: "/parents/training/sessions",
    icon: ClipboardList,
  },
  {
    id: "overview",
    label: "Resumen",
    to: "/parents/training/overview",
    icon: BarChart3,
  },
  { id: "profile", label: "Perfil", to: "/perfil", icon: UserRound },
];

/**
 * Exact-match primero, luego el prefijo de ruta más largo gana — mismo
 * algoritmo que `resolveActiveItemId` (ver nota de módulo), reimplementado
 * localmente porque `NAV_AREAS`/`NavRole` de `lib/navigation.ts` no
 * modelan el rol "parent".
 */
function resolveActiveSlotId(pathname: string): string | undefined {
  const exactMatch = SLOTS.find((slot) => slot.to === pathname);
  if (exactMatch) return exactMatch.id;

  const prefixMatches = SLOTS.filter((slot) => pathname.startsWith(`${slot.to}/`));
  if (prefixMatches.length === 0) return undefined;

  return prefixMatches.reduce((longest, current) =>
    current.to.length > longest.to.length ? current : longest,
  ).id;
}

const slotClasses =
  "relative flex min-h-[48px] flex-1 flex-col items-center justify-center gap-[3px] px-1 py-1.5 text-[11px] transition-colors";
const activeClasses = "font-semibold text-charcoal";
const inactiveClasses = "font-medium text-mid-gray hover:text-charcoal";

/**
 * Barra indicadora de 16×3px en el borde superior del slot activo (mockup
 * `PadresInicio.dc.html`) — mismo rol que `ActiveBar` de `SidebarNav.tsx`,
 * pero horizontal/superior en vez de vertical/izquierda.
 */
function TopIndicator() {
  return (
    <span
      aria-hidden="true"
      className="absolute top-0 left-1/2 h-[3px] w-4 -translate-x-1/2 rounded-b-xs bg-primary"
    />
  );
}

/**
 * Barra inferior persistente del portal de padres (móvil, <md). Cinco slots
 * fijos: Inicio, Calendario, Entrenos, Resumen, Perfil.
 */
export function ParentBottomNav() {
  const { pathname } = useLocation();
  const activeId = resolveActiveSlotId(pathname);

  return (
    <nav
      aria-label="Navegación principal"
      className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t border-light-gray bg-white md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {SLOTS.map((slot) => {
        const Icon = slot.icon;
        const active = slot.id === activeId;
        return (
          <Link
            key={slot.id}
            to={slot.to}
            aria-current={active ? "page" : undefined}
            className={cn(slotClasses, active ? activeClasses : inactiveClasses)}
          >
            {active && <TopIndicator />}
            <Icon
              className={cn("h-5 w-5 shrink-0", active && "text-nav-accent")}
              aria-hidden="true"
            />
            <span className="truncate">{slot.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
