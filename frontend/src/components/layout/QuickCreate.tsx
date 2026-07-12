/**
 * QuickCreate — header "Crear" dropdown (feature 030, US4 / FR-006).
 *
 * Trigger is a `Plus` icon button (`aria-label="Crear"`) that opens a
 * role-filtered list of "start a new X" shortcuts. Rendered once in
 * `AppShell`'s header action cluster for `role === "coach" | "admin"` — see
 * `contracts/header-actions.md`. None of the targets take a `?prefill`
 * param: quick-create has no contextual data to seed the create form with
 * (unlike the calendar day-click `?date=` prefill from 028-R11).
 *
 * Built on the existing `ui/dropdown-menu.tsx` primitive (Radix), same
 * pattern as `AthleteSwitcher`.
 */
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

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
        aria-label="Crear"
        className={cn(
          "flex h-12 w-12 shrink-0 items-center justify-center rounded-lg text-charcoal transition-colors hover:bg-light-gray",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
        )}
        data-testid="quick-create-trigger"
      >
        <Plus className="h-5 w-5" aria-hidden="true" />
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
