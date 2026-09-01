import type { LucideIcon } from "lucide-react";
import { BookOpen, CalendarDays, Home, Trophy, Users, UsersRound } from "lucide-react";

import { currentSeason } from "@/lib/datetime";

/**
 * Config-driven navigation model (feature 030) — single source of truth
 * consumed by SidebarNav, BottomNav, and MoreSheet. Parent nav is
 * unchanged/out of scope for this feature (see spec.md Assumptions).
 */

export type NavRole = "coach" | "admin";

/**
 * Agrupación visual del sidebar (feature 035). NO agrega destinos ni cambia
 * rutas: las mismas 6 `NAV_AREAS` se reparten en dos overlines —
 * «Operación» (el día a día del entrenador) y «Club» (familias/biblioteca).
 * `BottomNav`/`MoreSheet` ignoran el grupo por completo.
 */
export type NavGroupId = "operacion" | "club";

export interface NavGroup {
  id: NavGroupId;
  /** es-CO, copy exacta del mockup (NavEntrenador.dc.html). */
  label: string;
}

/** Grupos en orden de render. */
export const NAV_GROUPS: NavGroup[] = [
  { id: "operacion", label: "Operación" },
  { id: "club", label: "Club" },
];

/** Un grupo junto a las áreas visibles que le corresponden. */
export interface NavGroupWithAreas extends NavGroup {
  areas: NavArea[];
}

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
  /** Overline bajo el que se agrupa el área en el sidebar (feature 035). */
  group: NavGroupId;
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
    group: "operacion",
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
    group: "operacion",
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
    group: "operacion",
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
    group: "operacion",
    roles: ["coach"],
    matchPrefixes: ["/athletes"],
    items: [
      {
        id: "athletes.all",
        label: "Todos",
        to: "/athletes",
        roles: ["coach"],
      },
    ],
    bottomBarSlot: { coach: true },
  },
  {
    id: "families",
    label: "Familias",
    icon: UsersRound,
    group: "club",
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
    group: "club",
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

/**
 * Resolves which single item within an area's sub-item list is "active" for
 * `pathname` — same exact-match-first / longest-prefix-fallback algorithm as
 * `SiblingViewTabs.tsx`'s `resolveActiveTo`. Required because sibling items
 * within an area can nest path-wise (e.g. competitions.valid's `/competitions`
 * is a literal prefix of competitions.unlinked's `/competitions/unlinked` and
 * competitions.seasonInsights's `/competitions/insights/season/:year`); a
 * naive `NavLink` default match (prefix, non-`end`) marks multiple siblings
 * active simultaneously.
 */
export function resolveActiveItemId(
  items: NavItem[],
  pathname: string,
): string | undefined {
  const resolved = items.map((item) => ({ item, to: resolveTo(item.to) }));

  const exactMatch = resolved.find(({ to }) => to === pathname);
  if (exactMatch) return exactMatch.item.id;

  const prefixMatches = resolved.filter(({ to }) => pathname.startsWith(`${to}/`));
  if (prefixMatches.length === 0) return undefined;

  return prefixMatches.reduce((longest, current) =>
    current.to.length > longest.to.length ? current : longest,
  ).item.id;
}

/** Areas visible to `role`, in `NAV_AREAS` order. */
export function getVisibleAreas(role: NavRole): NavArea[] {
  return NAV_AREAS.filter((area) => isVisible(area.roles, role));
}

/**
 * Las mismas áreas de `getVisibleAreas(role)` repartidas en los overlines del
 * sidebar (feature 035), en orden de `NAV_GROUPS` y, dentro de cada grupo, en
 * orden de `NAV_AREAS`. Un grupo sin áreas visibles para el rol se omite (hoy
 * no ocurre: admin pierde Atletas pero conserva el resto de «Operación»).
 * Puramente presentacional — no crea, oculta ni reordena destinos.
 */
export function getGroupedAreas(role: NavRole): NavGroupWithAreas[] {
  const visible = getVisibleAreas(role);
  return NAV_GROUPS.map((group) => ({
    ...group,
    areas: visible.filter((area) => area.group === group.id),
  })).filter((group) => group.areas.length > 0);
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
