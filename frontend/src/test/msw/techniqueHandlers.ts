/**
 * MSW handlers para el módulo Técnica y Gymkhana (feature 018).
 * Fixtures deterministas; sin datos reales de atletas.
 */
import { http, HttpResponse } from "msw";

import type {
  CatalogList,
  ExerciseListItem,
  MaterialRead,
  SkillRead,
} from "@/types/technique.types";

// ---------------------------------------------------------------------------
// Fixture factories
// ---------------------------------------------------------------------------

export function makeSkill(overrides?: Partial<SkillRead>): SkillRead {
  return {
    code: "SKILL-001",
    slug: "equilibrio",
    name: "Equilibrio",
    order: 1,
    ...overrides,
  };
}

export function makeMaterial(overrides?: Partial<MaterialRead>): MaterialRead {
  return {
    slug: "conos",
    name: "Conos",
    is_none: false,
    ...overrides,
  };
}

export function makeExerciseListItem(
  overrides?: Partial<ExerciseListItem>,
): ExerciseListItem {
  return {
    id: 1,
    slug: "slalom-conos",
    name: "Slalom con conos",
    summary: "Recorrido en slalom entre conos para desarrollar control direccional.",
    difficulty: "facil",
    is_game: false,
    is_gymkhana: false,
    age_bands: ["10-12"],
    skills: [{ code: "SKILL-001", slug: "equilibrio", name: "Equilibrio" }],
    materials: [{ slug: "conos", name: "Conos", is_none: false }],
    is_seeded: true,
    is_hidden: false,
    ...overrides,
  };
}

export function makeCatalogList(
  items: ExerciseListItem[] = [makeExerciseListItem()],
): CatalogList {
  return { items, total: items.length };
}

// ---------------------------------------------------------------------------
// MSW handlers — happy path
// ---------------------------------------------------------------------------

export const techniqueHandlers = [
  // GET /api/technique/exercises — catálogo con filtros opcionales
  http.get("*/api/technique/exercises", () => {
    return HttpResponse.json(
      makeCatalogList([
        makeExerciseListItem({ id: 1 }),
        makeExerciseListItem({
          id: 2,
          slug: "gymkhana-basica",
          name: "Gymkhana básica",
          difficulty: "media",
          is_gymkhana: true,
          age_bands: ["13-15"],
        }),
      ]),
    );
  }),

  // GET /api/technique/skills — taxonomía
  http.get("*/api/technique/skills", () => {
    return HttpResponse.json([
      makeSkill({ code: "SKILL-001", slug: "equilibrio", name: "Equilibrio", order: 1 }),
      makeSkill({ code: "SKILL-002", slug: "frenada", name: "Frenada", order: 2 }),
    ]);
  }),

  // GET /api/technique/materials — materiales disponibles
  http.get("*/api/technique/materials", () => {
    return HttpResponse.json([
      makeMaterial({ slug: "conos", name: "Conos", is_none: false }),
      makeMaterial({ slug: "sin-material", name: "Sin material", is_none: true }),
    ]);
  }),
];

// ---------------------------------------------------------------------------
// Handler variants for specific test scenarios
// ---------------------------------------------------------------------------

/** Catálogo vacío (sin ejercicios). */
export const techniqueEmptyCatalogHandler = http.get(
  "*/api/technique/exercises",
  () => HttpResponse.json(makeCatalogList([])),
);

/** Error de red — simula servidor iniciando (cold-start). */
export const techniqueColdStartHandler = http.get(
  "*/api/technique/exercises",
  () => HttpResponse.error(),
);

/** Error 503 del servidor. */
export const technique503Handler = http.get(
  "*/api/technique/exercises",
  () => new HttpResponse(null, { status: 503 }),
);
