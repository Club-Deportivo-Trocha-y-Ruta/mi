/**
 * QuickCreate — header "Crear" dropdown (feature 030, US4 / FR-006).
 *
 * Trigger is la única acción que queda en el header de entrenador/admin
 * (feature 035, `Main.dc.html`): un botón primario *etiquetado* — Plus +
 * «Crear» + chevron — en vez del botón de sólo ícono de la 030. La tarjeta
 * de usuario se mudó al pie de la barra lateral, así que este botón ya no
 * compite con nada por atención en el header y puede llevar su etiqueta.
 * Abre la misma lista de atajos "crear X" filtrada por rol. Rendered once in
 * `AppShell`'s header action cluster for `role === "coach" | "admin"` — see
 * `contracts/header-actions.md`. None of the targets take a `?prefill`
 * param: quick-create has no contextual data to seed the create form with
 * (unlike the calendar day-click `?date=` prefill from 028-R11).
 *
 * Built on the existing `ui/dropdown-menu.tsx` primitive (Radix), same
 * pattern as `AthleteSwitcher`; el trigger reusa `buttonVariants()` de
 * `ui/button.tsx` (variante primaria = los mismos valores del mockup:
 * `bg-primary`/`hover:bg-primary-dark`, `px-4`, `rounded-lg`) con dos
 * correcciones sobre el default de la variante — altura y tinta del texto,
 * documentadas en el propio `className`.
 */
import { Link } from "react-router-dom";
import { ChevronDown, Plus } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { NavRole } from "@/lib/navigation";

interface QuickCreateProps {
  role: NavRole;
}

interface QuickCreateItem {
  id: string;
  label: string;
  to: string;
  roles: NavRole[];
}

// Per contracts/header-actions.md — no `?prefill` params on any target.
const QUICK_CREATE_ITEMS: QuickCreateItem[] = [
  {
    id: "quick-create.session",
    label: "Nueva sesión",
    to: "/training/sessions/new",
    roles: ["coach", "admin"],
  },
  {
    id: "quick-create.competition",
    label: "Nueva competencia",
    to: "/competitions/new",
    roles: ["coach", "admin"],
  },
  {
    id: "quick-create.event",
    label: "Nuevo evento",
    to: "/calendar/events/new",
    roles: ["coach", "admin"],
  },
  {
    id: "quick-create.athlete",
    label: "Nuevo atleta",
    to: "/athletes/new",
    roles: ["coach"],
  },
];

export function QuickCreate({ role }: QuickCreateProps) {
  const items = QUICK_CREATE_ITEMS.filter((item) => item.roles.includes(role));

  if (items.length === 0) {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        // `aria-label` idéntico al texto visible: sigue siendo el nombre
        // accesible estable que usan las pruebas/e2e desde la 030 y no
        // contradice la etiqueta visible (WCAG 2.5.3 Label in Name).
        aria-label="Crear"
        className={cn(
          buttonVariants(),
          // Dos correcciones al default de `buttonVariants()`:
          //  - `min-h-12` (48px): el tamaño `default` sólo garantiza 44px y
          //    el piso táctil del proyecto es 48 (mismo criterio que
          //    `UserMenu` y que los items del propio menú de abajo).
          //  - `text-midnight`: blanco sobre `--color-primary` (#20b7c9) da
          //    2.42:1 y no pasa AA para 14px. #111111 da 7.8:1 (5.3:1 sobre
          //    el hover `--color-primary-dark`). Se usa `midnight` y no
          //    `charcoal` porque `--color-primary` es idéntico en claro y
          //    oscuro mientras `--color-charcoal` se invierte a casi blanco
          //    en oscuro — volvería a fallar allí.
          "min-h-12 shrink-0 font-semibold text-midnight",
        )}
        data-testid="quick-create-trigger"
      >
        <Plus size={16} aria-hidden="true" />
        Crear
        <ChevronDown size={14} aria-hidden="true" />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="min-w-[12rem]">
        {items.map((item) => (
          <DropdownMenuItem
            key={item.id}
            asChild
            data-testid={item.id}
            // min-h-12 (48px) — constitution III / target-size rule; the
            // shared ui/dropdown-menu.tsx default (min-h-11, 44px) undershoots
            // it once real layout is measured (specs/030 T041 e2e sweep).
            className="min-h-12"
          >
            <Link to={item.to}>{item.label}</Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
