import { Link, useLocation } from "react-router-dom";
import { MoreHorizontal } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  getBottomBarAreas,
  isAreaActive,
  resolveAreaDefaultTo,
  type NavRole,
} from "@/lib/navigation";

interface BottomNavProps {
  /** Only "coach"/"admin" consume this — parent keeps its existing mobile drawer. */
  role: NavRole;
  /** Whether the "Más" sheet (`MoreSheet.tsx`) is currently open. Same prop names as `MoreSheet` so `AppShell.tsx` (T028) can share one `useState` for both. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const slotClasses =
  "flex min-h-[48px] min-w-[48px] flex-1 flex-col items-center justify-center gap-0.5 px-1 py-1.5 text-[11px] font-medium transition-colors";
const activeClasses = "text-charcoal";
const inactiveClasses = "text-mid-gray hover:text-charcoal";

/**
 * Mobile (<md) persistent bottom navigation bar (feature 030, research.md R2).
 * Renders `getBottomBarAreas(role)` (4 primary areas) plus a 5th "Más"
 * trigger opening `MoreSheet` for the remaining role-visible areas and the
 * profile/sign-out/diagnostics entries. See `contracts/mobile-navigation.md`.
 * Rendered only for role === "coach" | "admin" — parent nav is out of scope.
 */
export function BottomNav({ role, open, onOpenChange }: BottomNavProps) {
  const { pathname } = useLocation();
  const areas = getBottomBarAreas(role);

  return (
    <nav
      aria-label="Navegación principal"
      className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t border-light-gray bg-white md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {areas.map((area) => {
        const Icon = area.icon;
        const to = resolveAreaDefaultTo(area, role);
        // Same isAreaActive logic as SidebarNav (single source of truth,
        // contracts/mobile-navigation.md) — a slot is active whenever the
        // current path is inside the area, not only on its exact default
        // route (e.g. Atletas stays active on /anxiety). Plain `Link` is
        // used instead of `NavLink` because NavLink's own active-match
        // compares the current path only against this single `to`, which
        // would silently override our area-wide `aria-current`.
        const active = isAreaActive(area, pathname);
        return (
          <Link
            key={area.id}
            to={to}
            aria-current={active ? "page" : undefined}
            className={cn(slotClasses, active ? activeClasses : inactiveClasses)}
          >
            <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
            <span className="truncate">{area.label}</span>
          </Link>
        );
      })}

      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
        className={cn(slotClasses, open ? activeClasses : inactiveClasses)}
      >
        <MoreHorizontal className="h-5 w-5 shrink-0" aria-hidden="true" />
        <span className="truncate">Más</span>
      </button>
    </nav>
  );
}
