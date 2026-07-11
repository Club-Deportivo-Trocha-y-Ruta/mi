/**
 * ParentProfileStep — Paso 2 del wizard de onboarding (solo rol "parent").
 *
 * Recopila los datos personales del padre/madre/acudiente:
 * nombre, apellido, teléfono (opcional) y parentesco con el atleta.
 *
 * Usa useFormContext() para acceder al formulario del wizard padre.
 * Validación con parentProfileSchema (nombre, apellido, teléfono?, parentesco).
 */

import { useFormContext } from "react-hook-form";

import { FamilyRelationship } from "@/types/enums";
import type { OnboardingFormData } from "@/schemas/onboarding.schema";

// ---------------------------------------------------------------------------
// Estilos compartidos (design system Cal.com)
// ---------------------------------------------------------------------------

const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 shadow-ring";
const selectClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 appearance-none shadow-ring";

// ---------------------------------------------------------------------------
// Opciones de parentesco
// ---------------------------------------------------------------------------

const RELATIONSHIP_OPTIONS: { value: FamilyRelationship; label: string }[] = [
  { value: FamilyRelationship.padre, label: "Padre" },
  { value: FamilyRelationship.madre, label: "Madre" },
  { value: FamilyRelationship.acudiente, label: "Acudiente" },
];

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function ParentProfileStep() {
  const {
    register,
    formState: { errors },
  } = useFormContext<OnboardingFormData>();

  return (
    <div className="space-y-5">
      {/* Nombre y apellido */}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-medium text-charcoal">
          Nombre
          <input
            type="text"
            autoComplete="given-name"
            placeholder="María"
            className={inputClass}
            {...register("first_name")}
          />
          {errors.first_name && (
            <span className="mt-1 block text-xs text-red-600" role="alert">
              {errors.first_name.message}
            </span>
          )}
        </label>

        <label className="block text-sm font-medium text-charcoal">
          Apellido
          <input
            type="text"
            autoComplete="family-name"
            placeholder="García"
            className={inputClass}
            {...register("last_name")}
          />
          {errors.last_name && (
            <span className="mt-1 block text-xs text-red-600" role="alert">
              {errors.last_name.message}
            </span>
          )}
        </label>
      </div>

      {/* Teléfono — opcional */}
      <label className="block text-sm font-medium text-charcoal">
        Teléfono{" "}
        <span className="font-normal text-mid-gray">(opcional)</span>
        <input
          type="tel"
          autoComplete="tel"
          placeholder="+57 300 123 4567"
          className={inputClass}
          {...register("phone")}
        />
        {errors.phone && (
          <span className="mt-1 block text-xs text-red-600" role="alert">
            {errors.phone.message}
          </span>
        )}
      </label>

      {/* Parentesco */}
      <div>
        <label
          htmlFor="relationship_type"
          className="block text-sm font-medium text-charcoal"
        >
          Relación con el atleta
        </label>
        <div className="relative mt-1">
          <select
            id="relationship_type"
            className={selectClass}
            {...register("relationship_type")}
          >
            <option value="" disabled>
              Selecciona tu relación
            </option>
            {RELATIONSHIP_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {/* Chevron decorativo */}
          <div
            className="pointer-events-none absolute inset-y-0 right-3 flex items-center"
            aria-hidden="true"
          >
            <svg
              className="h-4 w-4 text-mid-gray"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        </div>
        {errors.relationship_type && (
          <span className="mt-1 block text-xs text-red-600" role="alert">
            {errors.relationship_type.message}
          </span>
        )}
      </div>
    </div>
  );
}
