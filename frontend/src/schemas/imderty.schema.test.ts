/**
 * Paridad del esquema Zod del perfil IMDERTY con el backend (feature 047).
 *
 * `api/imderty.ts` hace `imdertyProfileSchema.parse(...)` sobre la respuesta
 * de `GET /api/athletes/{id}/imderty-profile`, así que un valor de enum que
 * el backend emite y el esquema no conoce rompe la ficha entera. El backend
 * (`services/imderty/profile.py::PhoneSource`) emite cuatro fuentes de
 * teléfono: `athlete`, `primary_guardian`, `first_guardian` y `none`.
 * Todos los datos son ficticios.
 */
import { describe, expect, it } from "vitest";

import { imdertyProfileSchema } from "@/schemas/imderty";

function payload(effective_phone_source: string | null) {
  return {
    athlete_id: 42,
    first_surname: null,
    second_surname: null,
    surname_split: { confirmed: false, proposed_first: "Ficticio", proposed_second: null },
    document_type: null,
    document_number: null,
    address: null,
    barrio: null,
    other_municipality: false,
    school: null,
    grade: null,
    eps: null,
    phone: null,
    guardians: [
      { user_id: 1, display_name: "Acudiente Ficticio", has_phone: true, is_primary_contact: false },
    ],
    effective_phone_source,
    sensitive: { authorization: null },
  };
}

describe("imdertyProfileSchema — effective_phone_source", () => {
  it.each(["athlete", "primary_guardian", "first_guardian", "none", null])(
    "acepta %s (valor emitido por el backend)",
    (source) => {
      const parsed = imdertyProfileSchema.parse(payload(source));
      expect(parsed.effective_phone_source).toBe(source);
    },
  );

  it("rechaza una fuente desconocida", () => {
    expect(() => imdertyProfileSchema.parse(payload("vecino"))).toThrow();
  });
});
