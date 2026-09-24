import { describe, expect, it } from "vitest";

import { currentSeason } from "@/lib/datetime";
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
      "gobierno",
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

  it("Inicio, Entrenamiento, Competencias y Atletas son «Operación»; Familias y Gobierno son «Club»", () => {
    const groupOf = (id: string) => findArea(id).group;
    expect(groupOf("home")).toBe("operacion");
    expect(groupOf("training")).toBe("operacion");
    expect(groupOf("competitions")).toBe("operacion");
    expect(groupOf("athletes")).toBe("operacion");
    expect(groupOf("families")).toBe("club");
    expect(groupOf("gobierno")).toBe("club");
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
    expect(groups[1].areas.map((a) => a.id)).toEqual(["families", "gobierno"]);
  });

  it("getGroupedAreas('admin') omite Atletas dentro de Operación", () => {
    const groups = getGroupedAreas("admin");
    expect(groups[0].areas.map((a) => a.id)).toEqual([
      "home",
      "training",
      "competitions",
    ]);
    expect(groups[1].areas.map((a) => a.id)).toEqual(["families", "gobierno"]);
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

  it.each(ROLES)("%s ve Inicio, Entrenamiento, Competencias, Familias", (role) => {
    const visibleIds = getVisibleAreas(role).map((a) => a.id);
    expect(visibleIds).toEqual(
      expect.arrayContaining(["home", "training", "competitions", "families"]),
    );
  });

  it("coach ve las 6 áreas; admin ve 5 (sin Atletas)", () => {
    expect(getVisibleAreas("coach")).toHaveLength(6);
    expect(getVisibleAreas("admin")).toHaveLength(5);
  });

  it("coach y admin ven Gobierno (Historial del club)", () => {
    expect(getVisibleAreas("coach").map((a) => a.id)).toContain("gobierno");
    expect(getVisibleAreas("admin").map((a) => a.id)).toContain("gobierno");
    const gobierno = findArea("gobierno");
    expect(gobierno.items.map((i) => i.id)).toEqual([
      "gobierno.history",
      "gobierno.staff",
    ]);
  });

  it("gobierno.staff (Personal del club) es solo para admin", () => {
    const gobierno = findArea("gobierno");
    const staffItem = gobierno.items.find((i) => i.id === "gobierno.staff");
    expect(staffItem).toBeDefined();
    expect(staffItem?.roles).toEqual(["admin"]);

    const adminVisibleIds = gobierno.items
      .filter((i) => i.roles.includes("admin"))
      .map((i) => i.id);
    expect(adminVisibleIds).toContain("gobierno.staff");

    const coachVisibleIds = gobierno.items
      .filter((i) => i.roles.includes("coach"))
      .map((i) => i.id);
    expect(coachVisibleIds).not.toContain("gobierno.staff");
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
      "families.archivedAthletes",
    ]);
  });

  it("Atletas archivados es solo visible para admin (feature 041)", () => {
    const families = findArea("families");
    const archivedItem = families.items.find(
      (i) => i.id === "families.archivedAthletes",
    );
    expect(archivedItem?.roles).toEqual(["admin"]);
    expect(archivedItem?.to).toBe("/admin/atletas-archivados");
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

  it("coach en Atletas resuelve al item por defecto declarado", () => {
    const athletes = findArea("athletes");
    expect(resolveAreaDefaultTo(athletes, "coach")).toBe("/athletes");
  });

  it("coach y admin en Gobierno resuelven a Historial del club", () => {
    const gobierno = findArea("gobierno");
    expect(resolveAreaDefaultTo(gobierno, "coach")).toBe("/club/historial");
    expect(resolveAreaDefaultTo(gobierno, "admin")).toBe("/club/historial");
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

  it("/club/historial activa el área gobierno", () => {
    expect(isAreaActive(findArea("gobierno"), "/club/historial")).toBe(true);
  });

  it("/competitions/season/2026 activa el área competitions", () => {
    expect(
      isAreaActive(findArea("competitions"), "/competitions/season/2026"),
    ).toBe(true);
  });

  it("solo un área queda activa para una ruta dada (sin solapes)", () => {
    const pathname = "/competitions/season/2026";
    const activeAreas = NAV_AREAS.filter((area) =>
      isAreaActive(area, pathname),
    );
    expect(activeAreas.map((a) => a.id)).toEqual(["competitions"]);
  });
});

// Feature 045 (US6, T047) — el área «Competencias» tiene tres ítems y ninguna
// «Válidas»: la lista, «Temporada» y «Cargas e identidades».
describe("área Competencias (feature 045, US6)", () => {
  const competitions = () => findArea("competitions");
  const resolvedTo = (id: string) => {
    const item = competitions().items.find((i) => i.id === id);
    if (!item) throw new Error(`Ítem no encontrado: ${id}`);
    return typeof item.to === "function" ? item.to() : item.to;
  };

  it("el área se llama «Competencias»", () => {
    expect(competitions().label).toBe("Competencias");
  });

  it("los ítems, en orden, son «Competencias», «Temporada» y «Cargas e identidades»", () => {
    expect(competitions().items.map((i) => i.label)).toEqual([
      "Competencias",
      "Temporada",
      "Cargas e identidades",
    ]);
  });

  it("«Válidas», «Sin enlazar» y «Panorama de temporada» ya no son ítems del menú", () => {
    const labels = competitions().items.map((i) => i.label);
    expect(labels).not.toContain("Válidas");
    expect(labels).not.toContain("Sin enlazar");
    expect(labels).not.toContain("Panorama de temporada");
  });

  it("los ítems apuntan a /competitions, /competitions/season/:añoVigente y /competitions/imports", () => {
    expect(resolvedTo("competitions.list")).toBe("/competitions");
    expect(resolvedTo("competitions.season")).toBe(
      `/competitions/season/${currentSeason()}`,
    );
    expect(resolvedTo("competitions.imports")).toBe("/competitions/imports");
  });

  it.each(ROLES)("%s ve los tres ítems", (role) => {
    const visible = competitions().items.filter((i) => i.roles.includes(role));
    expect(visible).toHaveLength(3);
  });

  it.each(ROLES)(
    "el clic en la etiqueta del área (%s) resuelve a la lista /competitions",
    (role) => {
      expect(resolveAreaDefaultTo(competitions(), role)).toBe("/competitions");
    },
  );

  it("sigue con ranura en la barra inferior para coach y admin", () => {
    expect(competitions().bottomBarSlot).toEqual({ coach: true, admin: true });
  });
});

// Regression — SidebarNav sub-item exclusivity within the "competitions" area,
// whose items nest path-wise ("Competencias" /competitions is a literal prefix
// of "Cargas e identidades" /competitions/imports and "Temporada"
// /competitions/season/:year). A naive NavLink prefix match would mark more
// than one sibling active at once.
describe("resolveActiveItemId", () => {
  it("resuelve 'Temporada' (no 'Competencias') en la ruta anidada de la temporada vigente", () => {
    const items = findArea("competitions").items;
    expect(
      resolveActiveItemId(items, `/competitions/season/${currentSeason()}`),
    ).toBe("competitions.season");
  });

  it("'Temporada' sigue activa en cualquier otro año (matchPath), no cae a 'Competencias'", () => {
    const items = findArea("competitions").items;
    expect(resolveActiveItemId(items, "/competitions/season/2024")).toBe(
      "competitions.season",
    );
    expect(resolveActiveItemId(items, "/competitions/season/2099")).toBe(
      "competitions.season",
    );
  });

  it("resuelve 'Cargas e identidades' (no 'Competencias') en /competitions/imports", () => {
    const items = findArea("competitions").items;
    expect(resolveActiveItemId(items, "/competitions/imports")).toBe(
      "competitions.imports",
    );
  });

  it("resuelve 'Competencias' para el detalle de una competencia (/competitions/2)", () => {
    const items = findArea("competitions").items;
    expect(resolveActiveItemId(items, "/competitions/2")).toBe(
      "competitions.list",
    );
  });

  it("resuelve 'Competencias' en /competitions y en el wizard /competitions/import", () => {
    const items = findArea("competitions").items;
    expect(resolveActiveItemId(items, "/competitions")).toBe(
      "competitions.list",
    );
    // `/competitions/import` (singular, wizard) NO es `/competitions/imports`.
    expect(resolveActiveItemId(items, "/competitions/import")).toBe(
      "competitions.list",
    );
  });

  it("nunca resuelve más de un item activo a la vez", () => {
    const items = findArea("competitions").items;
    for (const pathname of [
      "/competitions",
      "/competitions/2",
      "/competitions/imports",
      "/competitions/season/2026",
      "/competitions/season/2025",
    ]) {
      // Varios prefijos crudos pueden coincidir (justo el bug que esto
      // protege) — resolveActiveItemId debe elegir exactamente uno.
      expect(resolveActiveItemId(items, pathname)).toBeDefined();
    }
  });

  it("isAreaActive sigue activando 'competitions' en las rutas nuevas", () => {
    for (const pathname of [
      "/competitions",
      "/competitions/imports",
      "/competitions/season/2026",
    ]) {
      expect(isAreaActive(findArea("competitions"), pathname)).toBe(true);
    }
  });
});

// T010 — getBottomBarAreas / getMoreSheetAreas role variants.
describe("getBottomBarAreas / getMoreSheetAreas", () => {
  it("getBottomBarAreas('coach') incluye 'athletes' y no 'families'", () => {
    const ids = getBottomBarAreas("coach").map((a) => a.id);
    expect(ids).toContain("athletes");
    expect(ids).not.toContain("families");
  });

  it("getBottomBarAreas('admin') excluye 'families' y 'athletes'", () => {
    const ids = getBottomBarAreas("admin").map((a) => a.id);
    expect(ids).not.toContain("families");
    expect(ids).not.toContain("athletes");
  });

  it("getBottomBarAreas('coach') devuelve exactamente 4 áreas; admin devuelve 3", () => {
    expect(getBottomBarAreas("coach")).toHaveLength(4);
    expect(getBottomBarAreas("admin")).toHaveLength(3);
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
