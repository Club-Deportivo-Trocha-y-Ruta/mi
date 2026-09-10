/**
 * Schema Zod de alta de personal (feature 041 — gobernanza multi-coach,
 * US3). Contrato: specs/041-multi-coach-governance/contracts/staff-admin.md
 * §9. Club obligatorio cuando el rol creado es entrenador o administrador
 * (hoy el único rol seleccionable desde la hoja es `coach`, §9 — `role`
 * viaja en el schema porque la regla es una propiedad del rol creado, no
 * del selector visible).
 *
 * El idioma condicional-requerido es el mismo de
 * `frontend/src/schemas/calendar.schema.ts` (superRefine + addIssue con
 * `path`), por R-31.
 */
import { z } from "zod";

export const staffCreateSchema = z
  .object({
    first_name: z.string().trim().min(2, "Mínimo 2 caracteres"),
    last_name: z.string().trim().min(2, "Mínimo 2 caracteres"),
    email: z.string().trim().email("Correo electrónico inválido"),
    phone: z.string().trim().optional().or(z.literal("")),
    role: z.enum(["coach", "admin"]).default("coach"),
    club_id: z.number().int().positive().nullable().default(null),
  })
  .superRefine((val, ctx) => {
    if ((val.role === "coach" || val.role === "admin") && !val.club_id) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "El club es obligatorio para un entrenador",
        path: ["club_id"],
      });
    }
  });

export type StaffCreateValues = z.infer<typeof staffCreateSchema>;
