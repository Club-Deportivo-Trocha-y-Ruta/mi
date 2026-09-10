/**
 * Espejo Zod de `backend/app/schemas/coach_activity.py` (feature 041 —
 * gobernanza multi-coach, US7). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §1.2.
 *
 * La forma exacta ya se confirmó leyendo el backend en el árbol
 * (`app/schemas/coach_activity.py`, `app/routers/audit.py::get_coach_activity`)
 * al momento de escribir este módulo — coincide con el contrato al detalle,
 * `from`/`to` incluidos (alias de `period_from`/`period_to`). Aun así los
 * contadores usan `.catch(0)` y las listas `.catch([])`: el mismo margen de
 * tolerancia que US6 le dio a los campos nuevos de `race_imports`, para que
 * un ajuste posterior y no anunciado del backend degrade a "0"/"vacío" en
 * vez de tumbar toda la página con un error de parseo.
 *
 * Un fallo de parseo en el resto de la forma (tipos base, claves
 * requeridas) sigue siendo un bug, no un estado de UI — no se atrapa acá,
 * se deja que TanStack Query lo propague (mismo criterio de
 * `schemas/audit.ts`).
 */
import { z } from "zod";

import { UserRole } from "@/types/enums";

export const coachRefSchema = z.object({
  user_id: z.number(),
  display_name: z.string(),
  // `z.nativeEnum` (no `auditActorRoleSchema`, que infiere el string-union
  // suelto de `schemas/audit.ts`) para que el tipo inferido calce con
  // `CoachRef.role: UserRole` de `types/coachActivity.types.ts`.
  role: z.nativeEnum(UserRole),
  is_active: z.boolean(),
});

export const clubSessionCountersSchema = z.object({
  planned: z.number().catch(0),
  executed: z.number().catch(0),
  cancelled: z.number().catch(0),
  total: z.number().catch(0),
});

export const coachSessionCountersSchema = clubSessionCountersSchema.extend({
  co_led: z.number().catch(0),
});

export const resultsOperationsCountersSchema = z.object({
  imports: z.number().catch(0),
  revisions: z.number().catch(0),
  competitor_links: z.number().catch(0),
  total: z.number().catch(0),
});

export const documentCountersSchema = z.object({
  reports_approved: z.number().catch(0),
  newsletters_approved: z.number().catch(0),
  newsletters_sent: z.number().catch(0),
  exports: z.number().catch(0),
});

export const clubTotalsSchema = z.object({
  sessions: clubSessionCountersSchema,
  attendance_entries_recorded: z.number().catch(0),
  ai_runs_launched: z.number().catch(0),
  results_operations: resultsOperationsCountersSchema,
  documents: documentCountersSchema,
  audit_entries_count: z.number().catch(0),
});

export const coachActivityRowSchema = z.object({
  coach: coachRefSchema,
  sessions: coachSessionCountersSchema,
  attendance_entries_recorded: z.number().catch(0),
  ai_runs_launched: z.number().catch(0),
  results_operations: resultsOperationsCountersSchema,
  documents: documentCountersSchema,
  audit_entries_count: z.number().catch(0),
});

export const coachActivityOutSchema = z.object({
  club_id: z.number(),
  from: z.string(),
  to: z.string(),
  computed_at: z.string(),
  club_totals: clubTotalsSchema,
  coaches: z.array(coachActivityRowSchema).catch([]),
});

export type CoachActivityOutParsed = z.infer<typeof coachActivityOutSchema>;
