/**
 * UserMenu — header "user name" dropdown (feature 030, US4 / FR-006).
 *
 * Trigger is the user's full name (already rendered today in the header,
 * `AppShell.tsx`) plus a chevron. Replaces the two standalone "Mi perfil" /
 * "Cerrar sesión" buttons that used to sit in the header action cluster.
 * Rendered once in `AppShell`'s header for `role === "coach" | "admin"` —
 * see `contracts/header-actions.md`.
 *
 * Items: Mi perfil (all roles) → separator + Salud IA (admin only,
 * relocated out of the sidebar) → separator → Cerrar sesión (all roles).
 *
 * Built on the existing `ui/dropdown-menu.tsx` primitive (Radix), same
 * pattern as `AthleteSwitcher`/`QuickCreate`.
 */
import { Link } from "react-router-dom";
import { Activity, ChevronDown, LogOut, UserRound } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthStore } from "@/store/auth.store";
import { cn } from "@/lib/utils";
import type { NavRole } from "@/lib/navigation";

interface UserMenuProps {
  role: NavRole;
}

export function UserMenu({ role }: UserMenuProps) {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const fullName = user ? `${user.first_name} ${user.last_name}` : "Usuario";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          // min-h-12 (48px) — constitution III / target-size rule (CLAUDE.md);
          // the shared ui/dropdown-menu.tsx default (min-h-11, 44px) undershoots
          // it once real layout is measured (specs/030 T041 e2e sweep).
          "flex min-h-12 max-w-[12rem] items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-light-gray",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
        )}
        data-testid="user-menu-trigger"
      >
        <span className="truncate text-sm font-medium text-mid-gray">
          {fullName}
        </span>
        <ChevronDown
          size={14}
          aria-hidden="true"
          className="shrink-0 text-mid-gray"
        />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="min-w-[12rem]">
        <DropdownMenuItem asChild data-testid="user-menu-profile" className="min-h-12">
          <Link to="/perfil" className="flex items-center gap-2">
            <UserRound size={14} aria-hidden="true" />
            Mi perfil
          </Link>
        </DropdownMenuItem>

        {role === "admin" && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild data-testid="user-menu-ai-health" className="min-h-12">
              <Link to="/admin/ai" className="flex items-center gap-2">
                <Activity size={14} aria-hidden="true" />
                Salud IA
              </Link>
            </DropdownMenuItem>
          </>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={logout}
          data-testid="user-menu-logout"
          className="flex min-h-12 items-center gap-2"
        >
          <LogOut size={14} aria-hidden="true" />
          Cerrar sesión
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
