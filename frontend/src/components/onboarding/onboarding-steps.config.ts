/**
 * Configuración declarativa de pasos del wizard de onboarding.
 *
 * Cada StepConfig define qué roles pueden ver el paso, qué schema Zod
 * valida sus campos y qué ícono de lucide-react lo representa.
 *
 * Uso:
 *   const steps = getStepsForRole("parent");  // [account, parent-profile, consent, confirm]
 *   const steps = getStepsForRole("coach");   // [account, confirm]
 */

import type { LucideIcon } from "lucide-react";
import { CheckCircle2, KeyRound, ShieldCheck, UserCircle } from "lucide-react";
import { z } from "zod";

import {
  accountSchema,
  consentSchema,
  parentProfileSchema,
} from "@/schemas/onboarding.schema";

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

/**
 * Roles posibles durante el onboarding.
 * Se excluye "athlete" porque los atletas no hacen onboarding propio;
 * se excluye null porque las funciones requieren un rol definido.
 */
export type OnboardingRole = "parent" | "coach";

/**
 * Configuración de un paso del wizard.
 */
export interface StepConfig {
  /** Identificador único del paso — usado como key y para routing interno. */
  id: string;
  /** Etiqueta visible en el stepper y accesibilidad. */
  label: string;
  /** Ícono de lucide-react que representa el paso. */
  icon: LucideIcon;
  /** Roles que deben ver este paso. */
  roles: OnboardingRole[];
  /**
   * Schema Zod para validar los campos de este paso.
   * El paso "confirm" no tiene campos propios → z.object({}).
   */
  schema: z.ZodTypeAny;
}

// ---------------------------------------------------------------------------
// Definición de pasos
// ---------------------------------------------------------------------------

/**
 * Array maestro con todos los pasos posibles del wizard.
 * El orden importa: define el orden de renderizado en el stepper.
 */
export const ONBOARDING_STEPS: StepConfig[] = [
  {
    id: "account",
    label: "Crear cuenta",
    icon: KeyRound,
    roles: ["parent", "coach"],
    schema: accountSchema,
  },
  {
    id: "parent-profile",
    label: "Perfil",
    icon: UserCircle,
    roles: ["parent"],
    schema: parentProfileSchema,
  },
  {
    id: "consent",
    label: "Consentimiento",
    icon: ShieldCheck,
    roles: ["parent"],
    schema: consentSchema,
  },
  {
    id: "confirm",
    label: "Confirmar",
    icon: CheckCircle2,
    roles: ["parent", "coach"],
    schema: z.object({}),
  },
];

// ---------------------------------------------------------------------------
// Funciones de utilidad
// ---------------------------------------------------------------------------

/**
 * Filtra los pasos disponibles para un rol dado.
 *
 * @param role - Rol del usuario que está haciendo el onboarding.
 * @returns Subconjunto ordenado de ONBOARDING_STEPS visible para ese rol.
 *
 * @example
 * getStepsForRole("coach")  // → [account, confirm]
 * getStepsForRole("parent") // → [account, parent-profile, consent, confirm]
 */
export function getStepsForRole(role: OnboardingRole): StepConfig[] {
  return ONBOARDING_STEPS.filter((step) => step.roles.includes(role));
}

/**
 * Devuelve el índice (0-based) de un paso dentro de los pasos filtrados
 * para el rol dado. Retorna -1 si el paso no existe o no aplica al rol.
 *
 * @param stepId - id del StepConfig buscado.
 * @param role   - Rol del usuario.
 *
 * @example
 * getStepIndex("confirm", "coach")  // → 1  (account=0, confirm=1)
 * getStepIndex("confirm", "parent") // → 3  (account=0, parent-profile=1, consent=2, confirm=3)
 * getStepIndex("consent", "coach")  // → -1 (el paso no aplica al rol coach)
 */
export function getStepIndex(stepId: string, role: OnboardingRole): number {
  const steps = getStepsForRole(role);
  return steps.findIndex((step) => step.id === stepId);
}
