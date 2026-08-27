import { describe, expect, it } from "vitest";

import {
  NAV_AREAS,
  NAV_GROUPS,
  getBottomBarAreas,
  getGroupedAreas,
  getMoreSheetAreas,
  getVisibleAreas,
  isAreaActive,
  resolveActiveItemId,
  resolveAreaDefaultTo,
  type NavRole,
} from "@/lib/navigation";

const ROLES: NavRole[] = ["coach", "admin"];

function findArea(id: string) {
  const area = NAV_AREAS.find((a) => a.id === id);
  if (!area) throw new Error(`Área no encontrada: ${id}`);
  return area;
}

// T007 — NAV_AREAS shape + full role-visibility matrix (data-model.md §3).
describe("NAV_AREAS", () => {
  it("tiene exactamente 6 áreas", () => {
    expect(NAV_AREAS).toHaveLength(6);
  });

  it("usa los 6 ids esperados, en orden", () => {
    expect(NAV_AREAS.map((a) => a.id)).toEqual([
      "home",
      "training",
      "competitions",
      "athletes",
      "families",
      "library",
    ]);
  });

  it("cada área tiene al menos un item y items[0] visible por al menos un rol", () => {
    for (const area of NAV_AREAS) {
      expect(area.items.length).toBeGreaterThan(0);
      const [defaultItem] = area.items;
      expect(defaultItem.roles.length).toBeGreaterThan(0);
    }
  });
});

// Feature 035 — agrupación visual del sidebar («Operación» / «Club»).
// Es metadata de presentación: no agrega, oculta ni reordena destinos.
describe("grupos de navegación (feature 035)", () => {
  it("declara exactamente dos grupos, en orden: Operación y Club", () => {
    expect(NAV_GROUPS.map((g) => g.id)).toEqual(["operacion", "club"]);
    expect(NAV_GROUPS.map((g) => g.label)).toEqual(["Operación", "Club"]);
  });

  it("cada área declara un grupo válido", () => {
    const validIds = NAV_GROUPS.map((g) => g.id);
    for (const area of NAV_AREAS) {
      expect(validIds).toContain(area.group);
    }
  });

  it("Inicio, Entrenamiento, Competencias y Atletas son «Operación»; Familias y Biblioteca son «Club»", () => {
    const groupOf = (id: string) => findArea(id).group;
    expect(groupOf("home")).toBe("operacion");
    expect(groupOf("training")).toBe("operacion");
    expect(groupOf("competitions")).toBe("operacion");
    expect(groupOf("athletes")).toBe("operacion");
    expect(groupOf("families")).toBe("club");
    expect(groupOf("library")).toBe("club");
  });

  it("getGroupedAreas('coach') reparte las 6 áreas: 4 en Operación, 2 en Club", () => {
    const groups = getGroupedAreas("coach");
    expect(groups.map((g) => g.label)).toEqual(["Operación", "Club"]);
    expect(groups[0].areas.map((a) => a.id)).toEqual([
      "home",
      "training",
      "competitions",
      "athletes",
    ]);
    expect(groups[1].areas.map((a) => a.id)).toEqual(["families", "library"]);
  });

  it("getGroupedAreas('admin') omite Atletas dentro de Operación", () => {
    const groups = getGroupedAreas("admin");
    expect(groups[0].areas.map((a) => a.id)).toEqual([
      "home",
      "training",
      "competitions",
    ]);
    expect(groups[1].areas.map((a) => a.id)).toEqual(["families", "library"]);
  });

  it.each(ROLES)(
    "getGroupedAreas(%s) aplanado === getVisibleAreas(%s): mismos destinos, mismo orden",
    (role) => {
      const flattened = getGroupedAreas(role).flatMap((g) => g.areas);
      expect(flattened.map((a) => a.id)).toEqual(
        getVisibleAreas(role).map((a) => a.id),
      );
    },
  );

  it.each(ROLES)("getGroupedAreas(%s) nunca devuelve un grupo vacío", (role) => {
    for (const group of getGroupedAreas(role)) {
      expect(group.areas.length).toBeGreaterThan(0);
    }
  });
});

describe("matriz de visibilidad por rol (data-model.md §3)", () => {
  it("coach ve el área Atletas completa; admin no la ve", () => {
    expect(getVisibleAreas("coach").map((a) => a.id)).toContain("athletes");
    expect(getVisibleAreas("admin").map((a) => a.id)).not.toContain(
      "athletes",
    );
  });

  it("coach ve Familias → Padres; admin no ve el item Padres", () => {
    const families = findArea("families");
    const padres = families.items.find((i) => i.id === "families.parents");
    expect(padres).toBeDefined();
    expect(padres?.roles).toEqual(["coach"]);
    expect(padres?.roles).not.toContain("admin");
  });

  it.each(ROLES)("%s ve Inicio, Entrenamiento, Competencias, Biblioteca", (role) => {
    const visibleIds = getVisibleAreas(role).map((a) => a.id);
    expect(visibleIds).toEqual(
      expect.arrayContaining(["home", "training", "competitions", "library"]),
    );
  });

  it("coach ve las 6 áreas; admin ve 5 (sin Atletas)", () => {
    expect(getVisibleAreas("coach")).toHaveLength(6);
    expect(getVisibleAreas("admin")).toHaveLength(5);
  });

  it("Familias sigue visible para admin (Boletines/Informes del club)", () => {
    expect(getVisibleAreas("admin").map((a) => a.id)).toContain("families");
    const families = findArea("families");
    const adminVisibleItems = families.items.filter((i) =>
      i.roles.includes("admin"),
    );
    expect(adminVisibleItems.map((i) => i.id)).toEqual([
      "families.newsletters",
      "families.reports",
    ]);
  });
});

// T008 — resolveAreaDefaultTo fallback behavior.
describe("resolveAreaDefaultTo", () => {
  it("admin en Familias resuelve a Boletines, nunca a /parents", () => {
    const families = findArea("families");
    expect(resolveAreaDefaultTo(families, "admin")).toBe(
      "/training/athlete-newsletters",
    );
  });

  it("coach en Familias resuelve a Padres", () => {
    const families = findArea("families");
    expect(resolveAreaDefaultTo(families, "coach")).toBe("/parents");
  });

  it("Inicio (área de un solo item) resuelve igual para ambos roles", () => {
    const home = findArea("home");
    expect(resolveAreaDefaultTo(home, "coach")).toBe("/dashboard");
    expect(resolveAreaDefaultTo(home, "admin")).toBe("/dashboard");
  });

  it("coach y admin en Entrenamiento resuelven a Calendario", () => {
    const training = findArea("training");
    expect(resolveAreaDefaultTo(training, "coach")).toBe("/calendar");
    expect(resolveAreaDefaultTo(training, "admin")).toBe("/calendar");
  });

  it("coach y admin en Atletas/Biblioteca resuelven al item por defecto declarado", () => {
    const athletes = findArea("athletes");
    expect(resolveAreaDefaultTo(athletes, "coach")).toBe("/athletes");

    const library = findArea("library");
    expect(resolveAreaDefaultTo(library, "coach")).toBe("/technique");
    expect(resolveAreaDefaultTo(library, "admin")).toBe("/technique");
  });
});

// T009 — isAreaActive longest-prefix matching.
describe("isAreaActive", () => {
  it("coincide con la ruta exacta del prefijo", () => {
    expect(isAreaActive(findArea("training"), "/calendar")).toBe(true);
  });

  it("coincide con subrutas del prefijo", () => {
    expect(
      isAreaActive(findArea("training"), "/training/sessions/123/edit"),
    ).toBe(true);
  });

  it("no coincide con un prefijo parcial que no continúa en '/'", () => {
    // "/calendarX" no debe matchear "/calendar".
    expect(isAreaActive(findArea("training"), "/calendarX")).toBe(false);
  });

  it("no coincide con rutas fuera de sus matchPrefixes", () => {
    expect(isAreaActive(findArea("athletes"), "/parents")).toBe(false);
  });

  it("/competitions/insights/season/2026 activa el área competitions", () => {
    expect(
      isAreaActive(findArea("competitions"), "/competitions/insights/season/2026"),
    ).toBe(true);
  });

  it("solo un área queda activa para una ruta dada (sin solapes)", () => {
    const pathname = "/competitions/insights/season/2026";
    const activeAreas = NAV_AREAS.filter((area) =>
      isAreaActive(area, pathname),
    );
    expect(activeAreas.map((a) => a.id)).toEqual(["competitions"]);
  });
});

// Regression — SidebarNav sub-item exclusivity within the "competitions" area,
// whose items nest path-wise ("Válidas" /competitions is a literal prefix of
// "Sin enlazar" /competitions/unlinked and "Panorama de temporada"
// /competitions/insights/season/:year). A naive NavLink prefix match would
// mark more than one sibling active at once.
describe("resolveActiveItemId", () => {
  it("resuelve 'Panorama de temporada' (no 'Válidas') en la ruta anidada", () => {
    const items = findArea("competitions").items;
    expect(
      resolveActiveItemId(items, "/competitions/insights/season/2026"),
    ).toBe("competitions.seasonInsights");
  });

  it("resuelve 'Sin enlazar' (no 'Válidas') en /competitions/unlinked", () => {
    const items = findArea("competitions").items;
    expect(resolveActiveItemId(items, "/competitions/unlinked")).toBe(
      "competitions.unlinked",
    );
  });

  it("resuelve 'Válidas' para el detalle de una válida (/competitions/2)", () => {
    const items = findArea("competitions").items;
    expect(resolveActiveItemId(items, "/competitions/2")).toBe(
      "competitions.valid",
    );
  });

  it("nunca resuelve más de un item activo a la vez", () => {
    const items = findArea("competitions").items;
    for (const pathname of [
      "/competitions",
      "/competitions/2",
      "/competitions/unlinked",
      "/competitions/insights/season/2026",
    ]) {
      const matches = items.filter((item) => {
        const to = typeof item.to === "function" ? item.to() : item.to;
        return to === pathname || pathname.startsWith(`${to}/`);
      });
      // Multiple raw prefix matches are expected (that's the whole bug this
      // guards against) — resolveActiveItemId must still pick exactly one.
      expect(matches.length).toBeGreaterThanOrEqual(1);
      expect(resolveActiveItemId(items, pathname)).toBeDefined();
    }
  });
});

// T010 — getBottomBarAreas / getMoreSheetAreas role variants.
describe("getBottomBarAreas / getMoreSheetAreas", () => {
  it("getBottomBarAreas('coach') incluye 'athletes' y no 'library'", () => {
    const ids = getBottomBarAreas("coach").map((a) => a.id);
    expect(ids).toContain("athletes");
    expect(ids).not.toContain("library");
  });

  it("getBottomBarAreas('admin') incluye 'library' y excluye 'athletes'", () => {
    const ids = getBottomBarAreas("admin").map((a) => a.id);
    expect(ids).toContain("library");
    expect(ids).not.toContain("athletes");
  });

  it.each(ROLES)("getBottomBarAreas(%s) devuelve exactamente 4 áreas", (role) => {
    expect(getBottomBarAreas(role)).toHaveLength(4);
  });

  it.each(ROLES)(
    "getMoreSheetAreas(%s) nunca se solapa con getBottomBarAreas(%s)",
    (role) => {
      const bottomIds = new Set(getBottomBarAreas(role).map((a) => a.id));
      const moreIds = getMoreSheetAreas(role).map((a) => a.id);
      for (const id of moreIds) {
        expect(bottomIds.has(id)).toBe(false);
      }
    },
  );

  it.each(ROLES)(
    "getMoreSheetAreas(%s) ∪ getBottomBarAreas(%s) = getVisibleAreas(%s)",
    (role) => {
      const bottomIds = getBottomBarAreas(role).map((a) => a.id);
      const moreIds = getMoreSheetAreas(role).map((a) => a.id);
      const visibleIds = getVisibleAreas(role).map((a) => a.id);
      expect([...bottomIds, ...moreIds].sort()).toEqual([...visibleIds].sort());
    },
  );

  it("families no tiene bottomBarSlot para ningún rol", () => {
    const moreCoach = getMoreSheetAreas("coach").map((a) => a.id);
    const moreAdmin = getMoreSheetAreas("admin").map((a) => a.id);
    expect(moreCoach).toContain("families");
    expect(moreAdmin).toContain("families");
  });
});
