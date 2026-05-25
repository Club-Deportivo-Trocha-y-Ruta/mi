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

import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { FamilyRelationship } from "@/types/enums";
import type { OnboardingFormData } from "@/schemas/onboarding.schema";

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
  const { control } = useFormContext<OnboardingFormData>();

  return (
    <div className="space-y-5">
      {/* Nombre y apellido */}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          control={control}
          name="first_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Nombre</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  autoComplete="given-name"
                  placeholder="María"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={control}
          name="last_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Apellido</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  autoComplete="family-name"
                  placeholder="García"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      {/* Teléfono — opcional */}
      <FormField
        control={control}
        name="phone"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              Teléfono{" "}
              <span className="font-normal text-mid-gray">(opcional)</span>
            </FormLabel>
            <FormControl>
              <Input
                type="tel"
                autoComplete="tel"
                placeholder="+57 300 123 4567"
                {...field}
                value={field.value ?? ""}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      {/* Parentesco */}
      <FormField
        control={control}
        name="relationship_type"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Relación con el atleta</FormLabel>
            <FormControl>
              <div className="relative">
                <select
                  className="w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 appearance-none shadow-ring aria-[invalid=true]:ring-2 aria-[invalid=true]:ring-red-500/40"
                  {...field}
                  value={field.value ?? ""}
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
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
