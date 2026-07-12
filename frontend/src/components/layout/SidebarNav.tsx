import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { ChevronDown } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import {
  getVisibleAreas,
  isAreaActive,
  resolveAreaDefaultTo,
  type NavRole,
} from "@/lib/navigation";

interface SidebarNavProps {
  /** Only "coach"/"admin" consume this — parent nav is out of scope (spec.md Assumptions). */
  role: NavRole;
  /** Optional callback fired on any link click (e.g. closing a mobile drawer). */
  onNavigate?: () => void;
}

const activeClasses = "bg-charcoal text-white";
const inactiveClasses =
  "text-mid-gray hover:bg-light-gray hover:text-charcoal";

/**
 * Desktop (≥md) collapsible sidebar navigation (feature 030, research.md R1).
 * Each multi-item area exposes two independent ≥44×44px controls: the area
 * label navigates to its resolved default route, and a separate chevron
 * button only toggles disclosure. The single-item Inicio area renders as a
 * plain link with no disclosure chrome.
 */
export function SidebarNav({ role, onNavigate }: SidebarNavProps) {
  const { pathname } = useLocation();
  const areas = getVisibleAreas(role);
  // Transient — never persisted (data-model.md §4). Auto-expand always wins
  // for the active area; this only tracks manual opens of inactive ones.
  const [manuallyOpened, setManuallyOpened] = useState<Record<string, boolean>>(
    {},
  );

  return (
    <nav className="flex flex-col gap-1" aria-label="Secciones">
      {areas.map((area) => {
        const visibleItems = area.items.filter((item) =>
          item.roles.includes(role),
        );
        const Icon = area.icon;
        const defaultTo = resolveAreaDefaultTo(area, role);

        // Inicio (and any other single-item area): plain link, no disclosure.
        if (visibleItems.length <= 1) {
          return (
            <NavLink
              key={area.id}
              to={defaultTo}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex min-h-11 items-center gap-2 truncate rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive ? activeClasses : inactiveClasses,
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{area.label}</span>
            </NavLink>
          );
        }

        const active = isAreaActive(area, pathname);
        const open = active || !!manuallyOpened[area.id];

        return (
          <Collapsible
            key={area.id}
            open={open}
            onOpenChange={(next) =>
              setManuallyOpened((prev) => ({ ...prev, [area.id]: next }))
            }
          >
            <div className="flex items-center gap-1">
              {/* Control 1 — navigates to the area's resolved default route. */}
              <NavLink
                to={defaultTo}
                onClick={onNavigate}
                className={cn(
                  "flex min-h-11 flex-1 items-center gap-2 truncate rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  active ? activeClasses : inactiveClasses,
                )}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="truncate">{area.label}</span>
              </NavLink>

              {/* Control 2 — only toggles disclosure; never navigates. */}
              <CollapsibleTrigger
                aria-label={
                  open ? `Contraer ${area.label}` : `Expandir ${area.label}`
                }
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-mid-gray transition-colors hover:bg-light-gray hover:text-charcoal"
              >
                <ChevronDown
                  className={cn(
                    "h-4 w-4 transition-transform",
                    open && "rotate-180",
                  )}
                  aria-hidden="true"
                />
              </CollapsibleTrigger>
            </div>

            <CollapsibleContent className="flex flex-col gap-1 py-1 pl-9">
              {visibleItems.map((item) => {
                const to = typeof item.to === "function" ? item.to() : item.to;
                return (
                  <NavLink
                    key={item.id}
                    to={to}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        "block rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                        isActive ? activeClasses : inactiveClasses,
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                );
              })}
            </CollapsibleContent>
          </Collapsible>
        );
      })}
    </nav>
  );
}
