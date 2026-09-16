/**
 * MSW handlers para el módulo race-course (perfil de circuito de una válida,
 * feature 043).
 *
 * Cubre los endpoints:
 *   - GET    /api/race-analysis/race-events/:id/course
 *   - POST   /api/race-analysis/race-events/:id/course/variants
 *   - PUT    /api/race-analysis/race-events/:id/course/variants/:variantId/file
 *   - PATCH  /api/race-analysis/race-events/:id/course/variants/:variantId
 *   - DELETE /api/race-analysis/race-events/:id/course/variants/:variantId
 *   - PUT    /api/race-analysis/race-events/:id/course/setups
 *   - PATCH  /api/race-analysis/race-events/:id/course/description
 *
 * Uso en tests:
 * ```ts
 * import { raceCourseHandlers, makeCourseRead } from "@/test/msw/raceCourseHandlers";
 *
 * // Registrar en setup global o por suite:
 * mswServer.use(...raceCourseHandlers);
 *
 * // Sobreescribir escenario puntual:
 * mswServer.use(raceCourseEmptyHandler);
 * ```
 */
import { http, HttpResponse } from "msw";

import type {
  CourseDescription,
  CourseRead,
  CourseSetup,
  CourseVariant,
} from "@/types/raceCourse.types";

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function makeCourseVariant(
  overrides?: Partial<CourseVariant>,
): CourseVariant {
  return {
    id: 7,
    label: "Circuito completo",
    lap_distance_km: 4.2,
    lap_distance_m: 4213,
    elevation_gain_m: 110,
    has_elevation: true,
    point_count: 486,
    geometry: [[3.4516, -76.532, 995.4]],
    detection: {
      method: "closed_loop",
      laps_detected: 3,
      total_distance_m: 12640,
    },
    created_at: "2026-09-15T14:02:11Z",
    updated_at: null,
    ...overrides,
  };
}

export function makeCourseSetup(overrides?: Partial<CourseSetup>): CourseSetup {
  return {
    category_id: 12,
    category_code: "INF_M",
    category_label: "Infantil masculino",
    laps: 3,
    variant_id: 7,
    ...overrides,
  };
}

function makeCourseDescription(
  overrides?: Partial<CourseDescription>,
): CourseDescription {
  return {
    terrain_type: "mixto",
    technical_difficulty: 4,
    key_sectors: ["subida_larga", "rock_garden"],
    course_notes: "...",
    ...overrides,
  };
}

/** Vista coach/admin: suggested_setups poblado, my_categories vacío. */
export function makeCourseRead(overrides?: Partial<CourseRead>): CourseRead {
  return {
    race_event_id: 41,
    has_course_data: true,
    variants: [makeCourseVariant()],
    setups: [makeCourseSetup()],
    suggested_setups: [
      {
        category_id: 12,
        category_label: "Sub-15 varones",
        laps: 3,
        variant_label: "Circuito completo",
        source_event_id: 38,
      },
    ],
    description: makeCourseDescription(),
    my_categories: [],
    ...overrides,
  };
}

/** Válida sin datos de circuito aún (has_course_data: false). */
export function makeEmptyCourseRead(
  overrides?: Partial<CourseRead>,
): CourseRead {
  return {
    race_event_id: 41,
    has_course_data: false,
    variants: [],
    setups: [],
    suggested_setups: [],
    description: {
      terrain_type: null,
      technical_difficulty: null,
      key_sectors: [],
      course_notes: null,
    },
    my_categories: [],
    ...overrides,
  };
}

/** Vista parent: suggested_setups vacío, my_categories poblado. */
export function makeParentCourseRead(
  overrides?: Partial<CourseRead>,
): CourseRead {
  return makeCourseRead({
    suggested_setups: [],
    my_categories: [{ athlete_id: 305, category_id: 12 }],
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Handlers por defecto (escenario feliz)
// ---------------------------------------------------------------------------

const BASE = "*/api/race-analysis/race-events";

/** GET /:id/course → circuito completo (vista coach/admin). */
const getCourseHandler = http.get(`${BASE}/:id/course`, () => {
  return HttpResponse.json(makeCourseRead());
});

/** POST /:id/course/variants → variante recién creada; retorna el CourseRead completo. */
const createVariantHandler = http.post(
  `${BASE}/:id/course/variants`,
  () => {
    return HttpResponse.json(makeCourseRead(), { status: 201 });
  },
);

/** PUT /:id/course/variants/:variantId/file → reemplaza la grabación de una variante. */
const replaceVariantFileHandler = http.put(
  `${BASE}/:id/course/variants/:variantId/file`,
  () => {
    return HttpResponse.json(makeCourseRead());
  },
);

/** PATCH /:id/course/variants/:variantId → renombra una variante. */
const renameVariantHandler = http.patch(
  `${BASE}/:id/course/variants/:variantId`,
  () => {
    return HttpResponse.json(makeCourseRead());
  },
);

/** DELETE /:id/course/variants/:variantId → elimina una variante. */
const deleteVariantHandler = http.delete(
  `${BASE}/:id/course/variants/:variantId`,
  () => {
    return HttpResponse.json(makeCourseRead());
  },
);

/** PUT /:id/course/setups → reemplaza la tabla de vueltas por categoría. */
const replaceSetupsHandler = http.put(`${BASE}/:id/course/setups`, () => {
  return HttpResponse.json(makeCourseRead());
});

/** PATCH /:id/course/description → actualiza la descripción cualitativa. */
const updateDescriptionHandler = http.patch(
  `${BASE}/:id/course/description`,
  () => {
    return HttpResponse.json(makeCourseRead());
  },
);

/** Conjunto de handlers del escenario feliz — registrar en setup global. */
export const raceCourseHandlers = [
  getCourseHandler,
  createVariantHandler,
  replaceVariantFileHandler,
  renameVariantHandler,
  deleteVariantHandler,
  replaceSetupsHandler,
  updateDescriptionHandler,
];

// ---------------------------------------------------------------------------
// Handlers de escenarios de error/alternativos — importar por suite según
// necesidad, vía `mswServer.use(...)`.
// ---------------------------------------------------------------------------

/** GET /:id/course 200 — válida sin datos de circuito aún. */
export const raceCourseEmptyHandler = http.get(`${BASE}/:id/course`, () => {
  return HttpResponse.json(makeEmptyCourseRead());
});

/** GET /:id/course 200 — vista de un padre/madre (my_categories poblado). */
export const raceCourseParentHandler = http.get(`${BASE}/:id/course`, () => {
  return HttpResponse.json(makeParentCourseRead());
});

/**
 * GET /:id/course 404 — el circuito no está disponible para este rol/válida
 * (ej. padre consultando una válida sin resultados publicados de su atleta).
 */
export const raceCourseParentNotFoundHandler = http.get(
  `${BASE}/:id/course`,
  () => {
    return HttpResponse.json(
      {
        detail: {
          code: "course_not_available",
          message: "El circuito de esta válida no está disponible.",
        },
      },
      { status: 404 },
    );
  },
);

/**
 * DELETE /:id/course/variants/:variantId 409 — la variante está en uso por
 * al menos una categoría en la tabla de setups.
 */
export const raceCourseVariantInUseHandler = http.delete(
  `${BASE}/:id/course/variants/:variantId`,
  () => {
    return HttpResponse.json(
      {
        detail: {
          code: "variant_in_use",
          message:
            "No se puede eliminar: la usan Infantil masculino, Infantil femenino.",
        },
      },
      { status: 409 },
    );
  },
);

/**
 * POST /:id/course/variants 409 — ya existe una variante con ese label en
 * esta válida.
 */
export const raceCourseVariantLabelTakenHandler = http.post(
  `${BASE}/:id/course/variants`,
  () => {
    return HttpResponse.json(
      {
        detail: {
          code: "variant_label_taken",
          message: "Ya existe una variante con ese nombre en esta válida.",
        },
      },
      { status: 409 },
    );
  },
);

/**
 * POST /:id/course/variants 422 — el recorrido del GPX es demasiado corto
 * para considerarse una vuelta.
 */
export const raceCourseTooShortHandler = http.post(
  `${BASE}/:id/course/variants`,
  () => {
    return HttpResponse.json(
      {
        detail: {
          code: "too_short",
          message:
            "El recorrido es demasiado corto para ser una vuelta (menos de 300 m).",
        },
      },
      { status: 422 },
    );
  },
);
