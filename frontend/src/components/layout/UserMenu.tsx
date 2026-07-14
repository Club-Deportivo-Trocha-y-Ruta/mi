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
 * relocated out of the sidebar) → separator → Apariencia (feature 033,
 * US5 / FR-008 — Sistema/Claro/Oscuro dark-mode toggle, optional story)
 * → separator → Atajos de teclado (feature 033, US5 / FR-009, T063 —
 * discoverable entry point for the `useKeyboardShortcuts` bindings, T062)
 * → separator → Cerrar sesión (all roles). Each section is its own
 * `DropdownMenuItem`/`DropdownMenuSeparator` block so entry points can be
 * inserted without restructuring the menu.
 *
 * Built on the existing `ui/dropdown-menu.tsx` primitive (Radix), same
 * pattern as `AthleteSwitcher`/`QuickCreate`. The radio group reuses the
 * same primitive's `DropdownMenuRadioGroup`/`DropdownMenuRadioItem`.
 *
 * `UserMenu` is rendered once per coach/admin page load (`AppShell`'s
 * header, unconditionally for `role === "coach" | "admin"`), so it also
 * doubles as the mount point for `useKeyboardShortcuts` (T062) — the only
 * wiring this component owns is `onOpenShortcutsHelp` -> opening the
 * `KeyboardShortcutsDialog` below; area-jump (`g`+letter) and `n` bindings
 * come for free from the same hook call.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ChevronDown,
  Keyboard,
  LogOut,
  Monitor,
  Moon,
  Sun,
  UserRound,
} from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { KeyboardShortcutsDialog } from "@/components/layout/KeyboardShortcutsDialog";
import { useKeyboardShortcuts } from "@/hooks/layout/useKeyboardShortcuts";
import { useAuthStore } from "@/store/auth.store";
import { cn } from "@/lib/utils";
import type { NavRole } from "@/lib/navigation";
import {
  applyCoachTheme,
  getStoredThemePreference,
  setStoredThemePreference,
  type ThemePreference,
} from "@/lib/theme";

interface UserMenuProps {
  role: NavRole;
}

const THEME_OPTIONS: Array<{
  value: ThemePreference;
  label: string;
  icon: typeof Monitor;
}> = [
  { value: "system", label: "Sistema", icon: Monitor },
  { value: "light", label: "Claro", icon: Sun },
  { value: "dark", label: "Oscuro", icon: Moon },
];

export function UserMenu({ role }: UserMenuProps) {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  // Feature 033, US5: local UI state for the radio group, seeded from the
  // persisted preference. `UserMenu` only ever renders for role === "coach"
  // | "admin" (AppShell gates it), so applyCoachTheme() here is always the
  // correct scope — the parent-portal guardrail lives in AppShell instead
  // (contracts/dark-theme-tokens.md "surface scope").
  const [themePreference, setThemePreference] = useState<ThemePreference>(
    () => getStoredThemePreference(),
  );

  function handleThemeChange(next: string) {
    const preference = next as ThemePreference;
    setThemePreference(preference);
    setStoredThemePreference(preference);
    applyCoachTheme(preference);
  }

  // Feature 033, US5 (T063): "Atajos de teclado" help dialog, opened either
  // from the menu item below or via the `?` binding registered by
  // useKeyboardShortcuts just below.
  const [shortcutsHelpOpen, setShortcutsHelpOpen] = useState(false);

  // Mounts the global `g`-chord / `n` / `?` bindings for the whole coach
  // shell (T062) — this component is always present in the header for
  // role === "coach" | "admin". Only `onOpenShortcutsHelp` is wired here;
  // `onOpenQuickCreate` wiring is out of scope for T063.
  useKeyboardShortcuts({
    role,
    onOpenShortcutsHelp: () => setShortcutsHelpOpen(true),
  });

  const fullName = user ? `${user.first_name} ${user.last_name}` : "Usuario";

  return (
    <>
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

          {/* Feature 033, US5 (FR-008, optional story) — Apariencia
              Sistema/Claro/Oscuro toggle. Coach/admin only by construction
              (this component never renders for parent) — the parent-portal
              "always light" guardrail lives in AppShell.tsx instead. */}
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Apariencia</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={themePreference}
            onValueChange={handleThemeChange}
            data-testid="user-menu-theme-group"
          >
            {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
              <DropdownMenuRadioItem
                key={value}
                value={value}
                data-testid={`user-menu-theme-${value}`}
                className="min-h-12"
              >
                <span className="flex items-center gap-2">
                  <Icon size={14} aria-hidden="true" />
                  {label}
                </span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>

          {/* Feature 033, US5 (FR-009, optional story, T063) — discoverable
              entry point for the keyboard-shortcuts help dialog. Selecting
              it lets the menu close normally (default onSelect behavior,
              same as "Cerrar sesión" below), then opens the dialog on the
              next tick (`setTimeout`) — opening a Radix Dialog in the same
              tick as the DropdownMenu's own close can race with its
              pointer/focus-outside dismiss handlers and immediately
              dismiss the dialog too. */}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => setTimeout(() => setShortcutsHelpOpen(true), 0)}
            data-testid="user-menu-shortcuts-help"
            className="flex min-h-12 items-center gap-2"
          >
            <Keyboard size={14} aria-hidden="true" />
            Atajos de teclado
          </DropdownMenuItem>

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

      <KeyboardShortcutsDialog
        open={shortcutsHelpOpen}
        onOpenChange={setShortcutsHelpOpen}
      />
    </>
  );
}
