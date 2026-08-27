/**
 * UserMenu — menú de cuenta del shell de entrenador/admin (feature 030, US4 /
 * FR-006; rediseñado en la feature 035).
 *
 * Un mismo menú con tres presentaciones del trigger (`variant`), porque el
 * mockup `Main.dc.html` mudó la tarjeta de usuario del header al PIE de la
 * barra lateral (el header conserva sólo «Crear»):
 *
 *   - `"sidebar"`     — tarjeta de ancho completo en el pie de la barra
 *                       expandida: avatar de 36px con iniciales sobre el
 *                       tinte de navegación, nombre + rol, y el ícono de
 *                       "más opciones". Es el montaje principal en ≥md.
 *   - `"sidebarRail"` — sólo el avatar, centrado, para el riel de 72px.
 *   - `"header"`      — el trigger clásico (nombre + chevron) de la 030. En
 *                       <md la barra lateral no existe (manda `BottomNav`),
 *                       así que `AppShell` lo monta en el header envuelto en
 *                       `md:hidden`.
 *
 * Items (idénticos en las tres variantes): Mi perfil (todos los roles) →
 * separador + Salud IA (sólo admin, reubicada fuera del sidebar) →
 * separador → Apariencia (feature 033, US5 / FR-008 — Sistema/Claro/Oscuro)
 * → separador → Atajos de teclado (feature 033, US5 / FR-009) → separador →
 * Cerrar sesión. Cada sección es su propio bloque
 * `DropdownMenuItem`/`DropdownMenuSeparator` para poder insertar entradas sin
 * reestructurar el menú.
 *
 * Construido sobre el primitivo existente `ui/dropdown-menu.tsx` (Radix),
 * mismo patrón que `AthleteSwitcher`/`QuickCreate`. El radio group reusa
 * `DropdownMenuRadioGroup`/`DropdownMenuRadioItem` del mismo primitivo.
 *
 * Feature 035: este componente YA NO monta `useKeyboardShortcuts` ni el
 * `KeyboardShortcutsDialog`. Con dos instancias por shell (pie de la barra +
 * header <md) el hook global quedaría registrado por duplicado, así que
 * ambos subieron a `AppShell` — que se monta exactamente una vez por rol — y
 * aquí sólo queda el `onOpenShortcutsHelp` que dispara el item del menú.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ChevronDown,
  EllipsisVertical,
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
import { useAuthStore } from "@/store/auth.store";
import { cn } from "@/lib/utils";
import type { NavRole } from "@/lib/navigation";
import {
  applyCoachTheme,
  getStoredThemePreference,
  setStoredThemePreference,
  type ThemePreference,
} from "@/lib/theme";

/** Presentación del trigger. El contenido del menú es el mismo en las tres. */
export type UserMenuVariant = "header" | "sidebar" | "sidebarRail";

interface UserMenuProps {
  role: NavRole;
  /** Ver la nota de módulo. Por defecto `"header"` (el trigger de la 030). */
  variant?: UserMenuVariant;
  /**
   * Abre el diálogo de atajos, que ahora vive en `AppShell` (montaje único
   * por shell). Ver la nota de módulo.
   */
  onOpenShortcutsHelp: () => void;
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

/** Etiqueta de rol bajo el nombre, en la tarjeta del pie de la barra. */
const ROLE_LABEL: Record<NavRole, string> = {
  coach: "Entrenador",
  admin: "Administrador",
};

/**
 * `data-testid` del trigger. La variante de la barra lateral se queda con el
 * id canónico porque es el montaje visible en escritorio/tablet (el header
 * sólo aparece bajo `md`), así que los e2e que apuntan a
 * `user-menu-trigger` siguen resolviendo a un único elemento.
 */
const TRIGGER_TEST_ID: Record<UserMenuVariant, string> = {
  header: "user-menu-trigger-header",
  sidebar: "user-menu-trigger",
  sidebarRail: "user-menu-trigger",
};

/** Anillo de foco — mismo tratamiento que `SidebarNav`/`QuickCreate`. */
const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50";

function getInitials(first?: string, last?: string): string {
  const f = (first?.trim().charAt(0) ?? "").toUpperCase();
  const l = (last?.trim().charAt(0) ?? "").toUpperCase();
  return `${f}${l}` || "·";
}

/** Avatar de 36px con iniciales — decorativo (el nombre ya se anuncia aparte). */
function InitialsAvatar({ initials }: { initials: string }) {
  return (
    <span
      aria-hidden="true"
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-nav-active-bg text-[13px] font-semibold text-nav-accent"
    >
      {initials}
    </span>
  );
}

export function UserMenu({
  role,
  variant = "header",
  onOpenShortcutsHelp,
}: UserMenuProps) {
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

  const fullName = user ? `${user.first_name} ${user.last_name}` : "Usuario";
  const initials = getInitials(user?.first_name, user?.last_name);
  const isSidebar = variant === "sidebar" || variant === "sidebarRail";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          focusRing,
          variant === "header" &&
            // min-h-12 (48px) — constitution III / target-size rule (CLAUDE.md);
            // the shared ui/dropdown-menu.tsx default (min-h-11, 44px) undershoots
            // it once real layout is measured (specs/030 T041 e2e sweep).
            "flex min-h-12 max-w-[12rem] items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-light-gray",
          variant === "sidebar" &&
            "flex min-h-12 w-full items-center gap-2.5 rounded-lg px-1 py-1.5 text-left transition-colors hover:bg-light-gray",
          variant === "sidebarRail" &&
            // Avatar visible de 36px dentro de un objetivo táctil real de
            // 44×44 — mismo criterio que el control de colapso de SidebarNav.
            "flex h-11 w-11 items-center justify-center rounded-lg transition-colors hover:bg-light-gray",
        )}
        // El riel no muestra texto: el nombre accesible lo aporta el aria-label.
        aria-label={variant === "sidebarRail" ? "Menú de usuario" : undefined}
        data-testid={TRIGGER_TEST_ID[variant]}
      >
        {variant === "header" && (
          <>
            <span className="truncate text-sm font-medium text-mid-gray">
              {fullName}
            </span>
            <ChevronDown
              size={14}
              aria-hidden="true"
              className="shrink-0 text-mid-gray"
            />
          </>
        )}

        {variant === "sidebar" && (
          <>
            <InitialsAvatar initials={initials} />
            <span className="flex min-w-0 flex-1 flex-col text-left">
              <span className="truncate text-[13px] font-semibold text-charcoal">
                {fullName}
              </span>
              <span className="truncate text-[11px] text-mid-gray">
                {ROLE_LABEL[role]}
              </span>
            </span>
            <EllipsisVertical
              size={16}
              aria-hidden="true"
              className="shrink-0 text-mid-gray"
            />
          </>
        )}

        {variant === "sidebarRail" && <InitialsAvatar initials={initials} />}
      </DropdownMenuTrigger>

      {/* En la barra lateral el trigger está pegado al borde inferior: el
          menú se despliega hacia arriba y alineado a su inicio. */}
      <DropdownMenuContent
        align={isSidebar ? "start" : "end"}
        side={isSidebar ? "top" : "bottom"}
        className="min-w-[12rem]"
      >
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

        {/* Feature 033, US5 (FR-009, optional story, T063) — punto de entrada
            descubrible al diálogo de atajos, que desde la feature 035 vive en
            `AppShell`. Seleccionar el item deja que el menú se cierre con su
            comportamiento normal (igual que "Cerrar sesión") y recién en el
            siguiente tick (`setTimeout`) avisa al shell: abrir un Dialog de
            Radix en el mismo tick que el cierre del DropdownMenu compite con
            sus manejadores de pointer/focus-outside y el diálogo se cerraría
            solo. */}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => setTimeout(onOpenShortcutsHelp, 0)}
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
  );
}
