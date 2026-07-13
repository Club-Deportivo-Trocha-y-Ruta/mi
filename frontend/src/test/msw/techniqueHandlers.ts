/**
 * MSW handlers para el módulo Técnica y Gymkhana (feature 018).
 * Fixtures deterministas; sin datos reales de atletas.
 */
import { http, HttpResponse } from "msw";

import type {
  AgeBand,
  CatalogList,
  ExerciseListItem,
  MaterialRead,
  SessionSegment,
  SkillRef,
  SkillRead,
  TechniqueSessionItem,
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

// ---------------------------------------------------------------------------
// Attach-to-session handlers (feature 032, T009/T013) — GET/POST
// /api/technique/sessions/:id/exercises with in-memory state, mirroring
// createStatefulProgressHandlers's pattern in strengthHandlers.ts.
// ---------------------------------------------------------------------------

/** Metadata por defecto usada para completar name/age_bands/skills al adjuntar
 * un exercise_id "crudo" — coincide con el catálogo happy-path de este archivo
 * (ids 1 y 2, ver techniqueHandlers). */
const DEFAULT_ATTACH_EXERCISE_META: Record<
  number,
  { name: string; age_bands: AgeBand[]; skills: SkillRef[]; is_gymkhana?: boolean }
> = {
  1: {
    name: "Slalom con conos",
    age_bands: ["10-12"],
    skills: [{ code: "SKILL-001", slug: "equilibrio", name: "Equilibrio" }],
  },
  2: {
    name: "Gymkhana básica",
    age_bands: ["13-15"],
    skills: [],
    is_gymkhana: true,
  },
};

export interface StatefulSessionExercisesOptions {
  exerciseMeta?: Record<
    number,
    { name: string; age_bands: AgeBand[]; skills: SkillRef[]; is_gymkhana?: boolean }
  >;
  /**
   * 1-indexed POST call numbers that must respond with a network error —
   * used to simulate "the server already committed the write, the client
   * only saw an error" (FR-009 regression). The in-memory store is still
   * mutated before the error response is returned, exactly like a real
   * commit whose response never reaches the client.
   */
  failPostCallNumbers?: number[];
}

/**
 * Crea un par de handlers GET/POST con estado en memoria para
 * `/api/technique/sessions/:sessionId/exercises` (contracts/attach-technique-
 * to-session.md). El POST dedupea por `(exercise_id, segment)` igual que el
 * backend real (`assembler.py::attach_exercises_to_session`) — un reintento
 * con el mismo payload no duplica filas.
 */
export function createStatefulSessionExercisesHandlers(
  sessionId: number,
  initialItems: TechniqueSessionItem[] = [],
  options: StatefulSessionExercisesOptions = {},
) {
  const meta = options.exerciseMeta ?? DEFAULT_ATTACH_EXERCISE_META;
  const failOn = new Set(options.failPostCallNumbers ?? []);
  const items: TechniqueSessionItem[] = [...initialItems];
  let postCallCount = 0;

  function computeMixesAgeBands(): boolean {
    const bands = new Set(items.flatMap((i) => i.age_bands));
    return bands.size > 1;
  }

  const getHandler = http.get(
    `*/api/technique/sessions/${sessionId}/exercises`,
    () => HttpResponse.json(items),
  );

  const postHandler = http.post(
    `*/api/technique/sessions/${sessionId}/exercises`,
    async ({ request }) => {
      postCallCount += 1;
      const body = (await request.json()) as {
        items: { exercise_id: number; segment: SessionSegment; position: number }[];
      };

      for (const submitted of body.items) {
        const alreadyPresent = items.some(
          (i) =>
            i.exercise_id === submitted.exercise_id &&
            i.segment === submitted.segment,
        );
        if (alreadyPresent) continue;
        const exerciseMeta = meta[submitted.exercise_id] ?? {
          name: `Ejercicio ${submitted.exercise_id}`,
          age_bands: [] as AgeBand[],
          skills: [] as SkillRef[],
        };
        items.push({
          exercise_id: submitted.exercise_id,
          name: exerciseMeta.name,
          segment: submitted.segment,
          position: items.filter((i) => i.segment === submitted.segment).length,
          age_bands: exerciseMeta.age_bands,
          skills: exerciseMeta.skills,
          is_hidden: false,
          is_gymkhana: exerciseMeta.is_gymkhana ?? false,
        });
      }

      if (failOn.has(postCallCount)) {
        return HttpResponse.error();
      }

      return HttpResponse.json(
        { mixes_age_bands: computeMixesAgeBands(), items: [...items] },
        { status: 201 },
      );
    },
  );

  return { handlers: [getHandler, postHandler], getItems: () => [...items] };
}
