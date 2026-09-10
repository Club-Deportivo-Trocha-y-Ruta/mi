import { describe, expect, it } from "vitest";

import { staffCreateSchema } from "@/schemas/staff.schema";

const validPayload = {
  first_name: "Ana",
  last_name: "Rivera",
  email: "ana.rivera@example.org",
  phone: "3001234567",
  role: "coach" as const,
  club_id: 1,
};

describe("staffCreateSchema", () => {
  it("acepta un payload válido", () => {
    const result = staffCreateSchema.safeParse(validPayload);
    expect(result.success).toBe(true);
  });

  it("role por defecto es 'coach' cuando se omite", () => {
    const { role, ...rest } = validPayload;
    void role;
    const result = staffCreateSchema.safeParse(rest);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.role).toBe("coach");
    }
  });

  it("club_id ausente produce un issue en ['club_id'] con el mensaje exacto", () => {
    const result = staffCreateSchema.safeParse({ ...validPayload, club_id: null });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find(
        (i) => i.path.join(".") === "club_id",
      );
      expect(issue?.message).toBe("El club es obligatorio para un entrenador");
    }
  });

  it("rechaza un correo inválido", () => {
    const result = staffCreateSchema.safeParse({
      ...validPayload,
      email: "no-es-un-correo",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path.join(".") === "email");
      expect(issue?.message).toBe("Correo electrónico inválido");
    }
  });

  it("rechaza nombres/apellidos de menos de 2 caracteres", () => {
    const result = staffCreateSchema.safeParse({
      ...validPayload,
      first_name: "A",
    });
    expect(result.success).toBe(false);
  });
});
