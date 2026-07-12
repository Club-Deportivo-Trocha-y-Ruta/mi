import type { LucideIcon } from "lucide-react";
import { BookOpen, CalendarDays, Home, Trophy, Users, UsersRound } from "lucide-react";

import { currentSeason } from "@/lib/datetime";

/**
 * Config-driven navigation model (feature 030) — single source of truth
 * consumed by SidebarNav, BottomNav, and MoreSheet. Parent nav is
 * unchanged/out of scope for this feature (see spec.md Assumptions).
 */

export type NavRole = "coach" | "admin";

export interface NavItem {
  /** Stable key, e.g. "training.calendar". */
  id: string;
  /** es-CO, exact UI copy (see contracts/navigation-model.md). */
  label: string;
  /** Static path, or a getter for a dynamic segment (e.g. season year). */
  to: string | (() => string);
  /** Which roles see this item. */
  roles: NavRole[];
}

export interface NavArea {
  /** e.g. "training". */
  id: string;
  /** es-CO. */
  label: string;
  icon: LucideIcon;
  /** Area-level visibility (e.g. Atletas: coach-only). */
  roles: NavRole[];
  /** Path prefixes counted "inside" this area (active state / auto-expand). */
  matchPrefixes: string[];
  /** Ordered; items[0] is the default-resolution fallback. */
  items: NavItem[];
  /** Which roles get this area a primary bottom-bar slot. */
  bottomBarSlot?: Partial<Record<NavRole, boolean>>;
}

function resolveTo(to: NavItem["to"]): string {
  return typeof to === "function" ? to() : to;
}

function isVisible(roles: NavRole[], role: NavRole): boolean {
  return roles.includes(role);
}

export const NAV_AREAS: NavArea[] = [
  {
    id: "home",
    label: "Inicio",
    icon: Home,
    roles: ["coach", "admin"],
    matchPrefixes: ["/dashboard"],
    items: [
      {
        id: "home.dashboard",
        label: "Inicio",
        to: "/dashboard",
        roles: ["coach", "admin"],
      },
    ],
    bottomBarSlot: { coach: true, admin: true },
  },
  {
    id: "training",
    label: "Entrenamiento",
    icon: CalendarDays,
    roles: ["coach", "admin"],
    matchPrefixes: ["/calendar", "/training/sessions", "/activities"],
    items: [
      {
        id: "training.calendar",
        label: "Calendario",
        to: "/calendar",
        roles: ["coach", "admin"],
      },
      {
        id: "training.sessions",
        label: "Sesiones",
        to: "/training/sessions",
        roles: ["coach", "admin"],
      },
      {
        id: "training.activities",
        label: "Actividades",
        to: "/activities",
        roles: ["coach", "admin"],
      },
    ],
    bottomBarSlot: { coach: true, admin: true },
  },
  {
    id: "competitions",
    label: "Competencias",
    icon: Trophy,
    roles: ["coach", "admin"],
    matchPrefixes: ["/competitions"],
    items: [
      {
        id: "competitions.valid",
        label: "Válidas",
        to: "/competitions",
        roles: ["coach", "admin"],
      },
      {
        id: "competitions.unlinked",
        label: "Sin enlazar",
        to: "/competitions/unlinked",
        roles: ["coach", "admin"],
      },
      {
        id: "competitions.seasonInsights",
        label: "Panorama de temporada",
        to: () => `/competitions/insights/season/${currentSeason()}`,
        roles: ["coach", "admin"],
      },
    ],
    bottomBarSlot: { coach: true, admin: true },
  },
  {
    id: "athletes",
    label: "Atletas",
    icon: Users,
    roles: ["coach"],
    matchPrefixes: ["/athletes", "/anxiety"],
    items: [
      {
        id: "athletes.all",
        label: "Todos",
        to: "/athletes",
        roles: ["coach"],
      },
      {
        id: "athletes.anxiety",
        label: "Ansiedad competitiva",
        to: "/anxiety",
        roles: ["coach"],
      },
    ],
    bottomBarSlot: { coach: true },
  },
  {
    id: "families",
    label: "Familias",
    icon: UsersRound,
    roles: ["coach", "admin"],
    matchPrefixes: [
      "/parents",
      "/training/athlete-newsletters",
      "/training/reports",
    ],
    items: [
      {
        id: "families.parents",
        label: "Padres",
        to: "/parents",
        roles: ["coach"],
      },
      {
        id: "families.newsletters",
        label: "Boletines",
        to: "/training/athlete-newsletters",
        roles: ["coach", "admin"],
      },
      {
        id: "families.reports",
        label: "Informes del club",
        to: "/training/reports",
        roles: ["coach", "admin"],
      },
    ],
  },
  {
    id: "library",
    label: "Biblioteca",
    icon: BookOpen,
    roles: ["coach", "admin"],
    matchPrefixes: ["/technique", "/strength"],
    items: [
      {
        id: "library.technique",
        label: "Técnica y gymkhana",
        to: "/technique",
        roles: ["coach", "admin"],
      },
      {
        id: "library.strength",
        label: "Fuerza",
        to: "/strength",
        roles: ["coach", "admin"],
      },
    ],
    bottomBarSlot: { admin: true },
  },
];

/**
 * Preferred target for an area's label click: the default item's `to` if
 * visible to `role`; otherwise the `to` of the first role-visible item.
 * (research.md R4 — e.g. sends admin to Boletines, never /parents.)
 */
export function resolveAreaDefaultTo(area: NavArea, role: NavRole): string {
  const [defaultItem] = area.items;
  if (defaultItem && isVisible(defaultItem.roles, role)) {
    return resolveTo(defaultItem.to);
  }
  const firstVisible = area.items.find((item) => isVisible(item.roles, role));
  return firstVisible ? resolveTo(firstVisible.to) : "";
}

/**
 * Longest-prefix match over `area.matchPrefixes` against `pathname`.
 * (contracts/navigation-model.md — "Active-state / auto-expand rule".)
 */
export function isAreaActive(area: NavArea, pathname: string): boolean {
  return area.matchPrefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

/** Areas visible to `role`, in `NAV_AREAS` order. */
export function getVisibleAreas(role: NavRole): NavArea[] {
  return NAV_AREAS.filter((area) => isVisible(area.roles, role));
}

/** Exactly 4 areas assigned a primary bottom-bar slot for `role`, ordered. */
export function getBottomBarAreas(role: NavRole): NavArea[] {
  return getVisibleAreas(role).filter((area) => area.bottomBarSlot?.[role]);
}

/** Visible areas for `role` minus those already in the bottom bar. */
export function getMoreSheetAreas(role: NavRole): NavArea[] {
  const bottomBarIds = new Set(getBottomBarAreas(role).map((area) => area.id));
  return getVisibleAreas(role).filter((area) => !bottomBarIds.has(area.id));
}
