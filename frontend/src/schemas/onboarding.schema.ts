/**
 * Schemas Zod para el wizard de onboarding multi-paso.
 *
 * Estructura de pasos:
 *   Paso 1 — accountSchema        (contraseña + confirmación)
 *   Paso 2 — parentProfileSchema  (datos del padre/madre/acudiente)
 *   Paso 3 — consentSchema        (consentimiento parental)
 *
 * Cada schema es independiente para validación granular con `trigger()` de RHF.
 * El schema combinado `onboardingFormSchema` garantiza type-safety en el wizard.
 *
 * Notas de versión:
 *   - Zod v4: los mensajes se pasan como `{ error: "..." }` (no `{ message: "..." }`)
 *   - Zod v4: `.merge()` está obsoleto — se usa object spread sobre `.shape`
 */

import { z } from "zod";
import { FamilyRelationship } from "@/types/enums";

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

export const PRIVACY_POLICY_VERSION = "v1.1";

/**
 * Regex de teléfono colombiano.
 * Acepta formatos:
 *   +57 300 123 4567
 *   +573001234567
 *   3001234567
 *   300 123 4567
 */
const COLOMBIAN_PHONE_REGEX = /^(\+57[\s-]?)?[3][0-9]{9}$|^(\+57[\s-]?)?[1-8][\s-]?[0-9]{6,7}$/;

// ---------------------------------------------------------------------------
// Paso 1 — Crear cuenta
// ---------------------------------------------------------------------------

export const accountSchema = z
  .object({
    password: z
      .string({ error: "La contraseña es requerida" })
      .min(8, { error: "La contraseña debe tener mínimo 8 caracteres" })
      .refine((val) => /[A-Z]/.test(val), {
        error: "La contraseña debe contener al menos una letra mayúscula",
      })
      .refine((val) => /[0-9]/.test(val), {
        error: "La contraseña debe contener al menos un número",
      }),
    password_confirm: z
      .string({ error: "La confirmación de contraseña es requerida" })
      .min(1, { error: "Debes confirmar la contraseña" }),
  })
  .refine((data) => data.password === data.password_confirm, {
    error: "Las contraseñas no coinciden",
    path: ["password_confirm"],
  });

// ---------------------------------------------------------------------------
// Paso 2 — Perfil del padre (solo rol "parent")
// ---------------------------------------------------------------------------

export const parentProfileSchema = z.object({
  first_name: z
    .string({ error: "El nombre es requerido" })
    .min(1, { error: "El nombre es requerido" })
    .transform((val) => val.trim()),
  last_name: z
    .string({ error: "El apellido es requerido" })
    .min(1, { error: "El apellido es requerido" })
    .transform((val) => val.trim()),
  phone: z
    .union([
      z
        .string()
        .regex(COLOMBIAN_PHONE_REGEX, {
          error: "Ingresa un número colombiano válido (ej: +57 300 123 4567)",
        }),
      z.literal(""),
    ])
    .optional(),
  relationship_type: z.enum(
    [
      FamilyRelationship.padre,
      FamilyRelationship.madre,
      FamilyRelationship.acudiente,
    ],
    {
      error: "Selecciona la relación con el atleta",
    }
  ),
});

// ---------------------------------------------------------------------------
// Paso 3 — Consentimiento parental
// ---------------------------------------------------------------------------

/**
 * Política v1.1 (2026-05-06): solo se solicitan los dos consentimientos
 * correspondientes a tratamientos activos en Fase 1 — datos básicos del
 * atleta y mediciones antropométricas. Cuando se implemente seguimiento
 * de entrenamiento o integración con terceros se bumpeará la política y
 * se solicitará un consentimiento nuevo (Ley 1581/2012, Art. 4 finalidad).
 */
export const consentSchema = z.object({
  accept_data_collection: z.literal(true, {
    error:
      "Debes aceptar el tratamiento de datos básicos del atleta para continuar",
  }),
  accept_anthropometry: z.literal(true, {
    error:
      "Debes aceptar el registro de medidas antropométricas para continuar",
  }),
});

// ---------------------------------------------------------------------------
// Schema de shape de cuenta (sin refine) — usado internamente para componer
// ---------------------------------------------------------------------------

/**
 * Shape puro de los campos de cuenta, sin el `refine` cross-field.
 * Necesario para componer el schema combinado del wizard (Zod v4 integra
 * los refinements dentro del ZodObject; `.shape` ya los excluye del tipo).
 */
const accountShapeSchema = z.object({
  password: z
    .string({ error: "La contraseña es requerida" })
    .min(8, { error: "La contraseña debe tener mínimo 8 caracteres" })
    .refine((val) => /[A-Z]/.test(val), {
      error: "La contraseña debe contener al menos una letra mayúscula",
    })
    .refine((val) => /[0-9]/.test(val), {
      error: "La contraseña debe contener al menos un número",
    }),
  password_confirm: z
    .string({ error: "La confirmación de contraseña es requerida" })
    .min(1, { error: "Debes confirmar la contraseña" }),
});

// ---------------------------------------------------------------------------
// Schema combinado — type safety para el wizard completo
// ---------------------------------------------------------------------------

/**
 * Combina los tres schemas de pasos usando object spread (patrón recomendado
 * en Zod v4 para evitar `.merge()` obsoleto y mantener buen rendimiento tsc).
 *
 * El refine de confirmación de contraseña no se replica aquí — se valida
 * por paso con `accountSchema` directamente al llamar `trigger()` en RHF.
 */
export const onboardingFormSchema = z.object({
  ...accountShapeSchema.shape,
  ...parentProfileSchema.shape,
  ...consentSchema.shape,
});

// ---------------------------------------------------------------------------
// Tipos inferidos
// ---------------------------------------------------------------------------

export type AccountData = z.infer<typeof accountSchema>;
export type ParentProfileData = z.infer<typeof parentProfileSchema>;
export type ConsentData = z.infer<typeof consentSchema>;
export type OnboardingFormData = z.infer<typeof onboardingFormSchema>;
