/**
 * ConsentStep — Paso 3 del wizard de onboarding (solo rol "parent").
 *
 * Presenta los 4 consentimientos parentales requeridos para la participación
 * del atleta en el club. Los primeros 3 son obligatorios; el 4to es opcional.
 *
 * Usa useFormContext() para acceder al formulario del wizard padre.
 * Validación con consentSchema (3 z.literal(true) + 1 z.boolean()).
 */

import { useFormContext, useWatch } from "react-hook-form";

import type { OnboardingFormData } from "@/schemas/onboarding.schema";

// ---------------------------------------------------------------------------
// Estilos compartidos (design system Cal.com)
// ---------------------------------------------------------------------------

const checkboxStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

// ---------------------------------------------------------------------------
// Tipos internos
// ---------------------------------------------------------------------------

interface ConsentItemProps {
  id: keyof Pick<
    OnboardingFormData,
    | "accept_data_collection"
    | "accept_training_tracking"
    | "accept_anthropometry"
    | "accept_third_party"
  >;
  label: string;
  description: string;
  required?: boolean;
  subtext?: string;
  error?: string;
  register: ReturnType<typeof useFormContext<OnboardingFormData>>["register"];
}

// ---------------------------------------------------------------------------
// Sub-componente: ítem de consentimiento
// ---------------------------------------------------------------------------

function ConsentItem({
  id,
  label,
  description,
  required = true,
  subtext,
  error,
  register,
}: ConsentItemProps) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 shrink-0">
        <input
          type="checkbox"
          id={id}
          className="h-4 w-4 cursor-pointer rounded accent-charcoal"
          style={checkboxStyle}
          {...register(id)}
          aria-required={required}
          aria-describedby={error ? `${id}-error` : undefined}
        />
      </div>
      <div className="flex-1 space-y-0.5">
        <label
          htmlFor={id}
          className="cursor-pointer text-sm font-medium text-charcoal"
        >
          {label}
          {!required && (
            <span className="ml-1.5 font-normal text-mid-gray">(opcional)</span>
          )}
        </label>
        <p className="text-xs leading-relaxed text-mid-gray">{description}</p>
        {subtext && (
          <p className="text-xs text-mid-gray/80 italic">{subtext}</p>
        )}
        {error && (
          <p
            id={`${id}-error`}
            className="text-xs text-red-600"
            role="alert"
          >
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ConsentStepProps {
  athleteName: string;
  clubName: string;
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function ConsentStep({ athleteName, clubName }: ConsentStepProps) {
  const {
    register,
    formState: { errors },
  } = useFormContext<OnboardingFormData>();

  // Observa accept_third_party para accesibilidad del estado del checkbox
  const acceptThirdParty = useWatch<OnboardingFormData, "accept_third_party">({
    name: "accept_third_party",
  });

  return (
    <div className="space-y-5">
      {/* Descripción contextual */}
      <div
        className="rounded-xl bg-light-gray px-4 py-3.5"
        style={{ boxShadow: "rgba(34, 42, 53, 0.05) 0px 1px 3px 0px" }}
      >
        <p className="text-sm text-charcoal">
          Como padre/acudiente de{" "}
          <strong className="font-semibold">{athleteName}</strong> en{" "}
          <strong className="font-semibold">{clubName}</strong>, autorizas al
          club a:
        </p>
      </div>

      {/* Lista de consentimientos */}
      <fieldset className="space-y-4" aria-label="Consentimientos parentales">
        <legend className="sr-only">
          Consentimientos parentales requeridos y opcionales
        </legend>

        <ConsentItem
          id="accept_data_collection"
          label="Recolectar datos personales de mi hijo/a"
          description="Nombre, fecha de nacimiento, contacto de emergencia y documentos de identificación necesarios para la inscripción y participación en competencias."
          required
          error={errors.accept_data_collection?.message}
          register={register}
        />

        <div className="border-t border-border/50" aria-hidden="true" />

        <ConsentItem
          id="accept_training_tracking"
          label="Registrar seguimiento deportivo"
          description="Sesiones de entrenamiento, resultados en competencias, zonas de frecuencia cardíaca, carga de entrenamiento y observaciones del entrenador."
          required
          error={errors.accept_training_tracking?.message}
          register={register}
        />

        <div className="border-t border-border/50" aria-hidden="true" />

        <ConsentItem
          id="accept_anthropometry"
          label="Registrar mediciones antropométricas"
          description="Talla de pie, talla sentado, peso, envergadura y cálculo de maduración biológica (PHV — Pico de Velocidad de Crecimiento) para personalizar la carga de entrenamiento."
          required
          error={errors.accept_anthropometry?.message}
          register={register}
        />

        <div className="border-t border-border/50" aria-hidden="true" />

        <ConsentItem
          id="accept_third_party"
          label="Compartir datos con herramientas de análisis externas"
          description="Intervals.icu y Google Sheets para análisis deportivo avanzado. Solo datos de rendimiento — nunca datos personales de identificación."
          required={false}
          subtext="Opcional — solo para análisis deportivo avanzado"
          register={register}
        />
      </fieldset>

      {/* Alerta informativa */}
      <div
        className="flex gap-2.5 rounded-xl border border-link-blue/20 bg-link-blue/5 px-4 py-3"
        role="note"
        aria-label="Información importante sobre consentimientos"
      >
        <svg
          className="mt-0.5 h-4 w-4 shrink-0 text-link-blue"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
        >
          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
          <path
            d="M8 5v4M8 11v.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
        <div className="space-y-1">
          <p className="text-xs font-medium text-link-blue">
            Los primeros 3 puntos son requisito para la participación.
          </p>
          <p className="text-xs text-mid-gray">
            Puedes revocar tu consentimiento en cualquier momento desde tu panel
            de padre.
          </p>
        </div>
      </div>

      {/* Enlace a política de privacidad */}
      <p className="text-center text-xs text-mid-gray">
        <a
          href="/privacidad"
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-link-blue underline-offset-2 hover:underline"
          aria-label="Leer política de privacidad completa (se abre en nueva pestaña)"
        >
          Leer política de privacidad completa
        </a>
      </p>

      {/* Accesibilidad: estado visible del checkbox opcional */}
      <span className="sr-only" aria-live="polite">
        {acceptThirdParty
          ? "Has aceptado compartir datos con herramientas externas."
          : "No has aceptado compartir datos con herramientas externas."}
      </span>
    </div>
  );
}
