import { Link } from "react-router-dom";
import { Activity, LogOut, UserRound } from "lucide-react";

import {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import {
  getMoreSheetAreas,
  resolveAreaDefaultTo,
  type NavRole,
} from "@/lib/navigation";
import { useAuthStore } from "@/store/auth.store";

interface MoreSheetProps {
  /** Only "coach"/"admin" consume this — parent nav is out of scope (spec.md Assumptions). */
  role: NavRole;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const rowClass =
  "flex min-h-12 w-full items-center gap-3 rounded-lg px-3 text-sm font-medium text-charcoal transition-colors hover:bg-light-gray focus-visible:outline-2 focus-visible:outline-charcoal focus-visible:outline-offset-2";

/**
 * "Más" bottom sheet (feature 030, US3) — the 5th bottom-bar slot's target.
 * Lists the role-visible NavAreas not already promoted to the bottom bar,
 * then account actions (Mi perfil / Salud IA admin-only / Cerrar sesión).
 * Built on the existing ui/sheet.tsx primitive (Radix Dialog under the
 * hood) — focus trap, Escape-to-close, and focus return to the trigger are
 * inherited, no bespoke a11y logic here. Every row wraps in `SheetClose`
 * so selecting it both navigates/acts and closes the sheet.
 */
export function MoreSheet({ role, open, onOpenChange }: MoreSheetProps) {
  const logout = useAuthStore((state) => state.logout);
  const areas = getMoreSheetAreas(role);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="max-h-[85vh] rounded-t-2xl">
        <SheetHeader>
          <SheetTitle>Más</SheetTitle>
        </SheetHeader>
        <SheetBody className="py-2">
          <nav aria-label="Más opciones" className="flex flex-col gap-1">
            {areas.map((area) => {
              const Icon = area.icon;
              const to = resolveAreaDefaultTo(area, role);
              return (
                <SheetClose asChild key={area.id}>
                  <Link to={to} className={rowClass}>
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="truncate">{area.label}</span>
                  </Link>
                </SheetClose>
              );
            })}

            <div
              role="separator"
              aria-orientation="horizontal"
              className="my-2 border-t border-[rgba(34,42,53,0.08)]"
            />

            <SheetClose asChild>
              <Link to="/perfil" className={rowClass}>
                <UserRound className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>Mi perfil</span>
              </Link>
            </SheetClose>

            {role === "admin" && (
              <SheetClose asChild>
                <Link to="/admin/ai" className={rowClass}>
                  <Activity className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>Salud IA</span>
                </Link>
              </SheetClose>
            )}

            <SheetClose asChild>
              <button
                type="button"
                onClick={logout}
                className={cn(rowClass, "text-left")}
              >
                <LogOut className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>Cerrar sesión</span>
              </button>
            </SheetClose>
          </nav>
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
