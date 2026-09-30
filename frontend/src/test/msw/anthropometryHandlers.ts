/**
 * Handlers MSW de la captura antropométrica (feature 048, `contracts/api.md`):
 * dry-run de plausibilidad, alta, edición (PUT), eliminación y las variantes
 * 409. Fixtures ficticias — sólo `athlete_id` numérico, sin nombres ni datos
 * reales de menores (Ley 1581).
 *
 * No se registran por defecto en `test/setup.ts`: cada prueba los activa con
 * `mswServer.use(...anthropometryHandlers)` o con la variante que necesite.
 */
import { http, HttpResponse } from "msw";

import type {
  AnthropometricRecord,
  AnthropometryCreate,
  PlausibilityCheckRequest,
  PlausibilityCheckResponse,
  PlausibilityWarning,
} from "@/types/anthropometry.types";
import { MaturationStatus } from "@/types/enums";

const RECORD_PATH = "*/api/athletes/:athleteId/anthropometry/:recordId";
const COLLECTION_PATH = "*/api/athletes/:athleteId/anthropometry";
const PLAUSIBILITY_PATH = "*/api/athletes/:athleteId/anthropometry/plausibility";

// ---------------------------------------------------------------------------
// Fixture factories
// ---------------------------------------------------------------------------

export function makeAnthropometricRecord(
  overrides?: Partial<AnthropometricRecord>,
): AnthropometricRecord {
  return {
    id: 812,
    athlete_id: 17,
    evaluation_date: "2026-09-20",
    weight_kg: 45.5,
    standing_height_cm: 150,
    arm_span_cm: null,
    sitting_height_cm: 72,
    leg_length_cm: 78,
    leg_sitting_ratio: 1.08,
    maturity_offset: -1.2,
    age_at_phv: 13.4,
    maturation_status: MaturationStatus.PrePHV,
    training_implications: null,
    evaluated_by: 3,
    created_at: "2026-09-20T15:00:00Z",
    notes: null,
    can_modify: true,
    plausibility_flags: [],
    ...overrides,
  };
}

export function makePlausibilityResponse(
  warnings: PlausibilityWarning[] = [],
  previousEvaluationDate: string | null = "2026-06-15",
): PlausibilityCheckResponse {
  return { warnings, previous_evaluation_date: previousEvaluationDate };
}

// ---------------------------------------------------------------------------
// Handlers por defecto (camino feliz)
// ---------------------------------------------------------------------------

export const plausibilityOkHandler = http.post(PLAUSIBILITY_PATH, () =>
  HttpResponse.json(makePlausibilityResponse()),
);

/** Plausibilidad con avisos fijos (p. ej. banco no restado). */
export function plausibilityWarningsHandler(warnings: PlausibilityWarning[]) {
  return http.post(PLAUSIBILITY_PATH, () => HttpResponse.json(makePlausibilityResponse(warnings)));
}

/** Plausibilidad que falla por red: la revisión no bloquea el guardado. */
export const plausibilityNetworkErrorHandler = http.post(PLAUSIBILITY_PATH, () =>
  HttpResponse.error(),
);

export const createAnthropometryHandler = http.post(
  COLLECTION_PATH,
  async ({ params, request }) => {
    const body = (await request.json()) as AnthropometryCreate;
    return HttpResponse.json(
      makeAnthropometricRecord({
        ...body,
        arm_span_cm: body.arm_span_cm ?? null,
        notes: body.notes ?? null,
        athlete_id: Number(params.athleteId),
      }),
      { status: 201 },
    );
  },
);

export const updateAnthropometryHandler = http.put(RECORD_PATH, async ({ params, request }) => {
  const body = (await request.json()) as AnthropometryCreate;
  return HttpResponse.json(
    makeAnthropometricRecord({
      ...body,
      arm_span_cm: body.arm_span_cm ?? null,
      notes: body.notes ?? null,
      id: Number(params.recordId),
      athlete_id: Number(params.athleteId),
    }),
  );
});

export const deleteAnthropometryHandler = http.delete(
  RECORD_PATH,
  () => new HttpResponse(null, { status: 204 }),
);

export const anthropometryHandlers = [
  plausibilityOkHandler,
  createAnthropometryHandler,
  updateAnthropometryHandler,
  deleteAnthropometryHandler,
];

// ---------------------------------------------------------------------------
// Variantes de error
// ---------------------------------------------------------------------------

/** 409 misma fecha (claves de primer nivel, contracts/api.md). */
export function sameDateConflictHandler(
  method: "post" | "put",
  { existingRecordId = 811, sameValues = false } = {},
) {
  const path = method === "post" ? COLLECTION_PATH : RECORD_PATH;
  return http[method](path, () =>
    HttpResponse.json(
      {
        detail: "anthropometry_same_date_exists",
        existing_record_id: existingRecordId,
        same_values: sameValues,
      },
      { status: 409 },
    ),
  );
}

/** 409 de pliegues al cambiar la fecha (forma anidada del 046). */
export function skinfoldConflictHandler(
  code: "athlete_too_young" | "skinfold_interval_too_short",
  nextAllowedDate?: string,
) {
  return http.put(RECORD_PATH, () =>
    HttpResponse.json(
      {
        detail: {
          code,
          ...(nextAllowedDate ? { next_allowed_date: nextAllowedDate } : {}),
        },
      },
      { status: 409 },
    ),
  );
}

/** 403: otro coach (o de otro club) intenta modificar la medición. */
export function forbiddenModifyHandler(method: "put" | "delete") {
  return http[method](RECORD_PATH, () =>
    HttpResponse.json({ detail: "forbidden" }, { status: 403 }),
  );
}

/** Captura la última petición de plausibilidad (para asertar el cuerpo). */
export function capturingPlausibilityHandler(
  sink: PlausibilityCheckRequest[],
  warnings: PlausibilityWarning[] = [],
) {
  return http.post(PLAUSIBILITY_PATH, async ({ request }) => {
    sink.push((await request.json()) as PlausibilityCheckRequest);
    return HttpResponse.json(makePlausibilityResponse(warnings));
  });
}
