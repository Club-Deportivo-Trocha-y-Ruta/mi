/**
 * AccountStep — Paso 1 del wizard de onboarding.
 *
 * Permite al usuario crear su contraseña. El email viene pre-rellenado
 * desde el token de invitación y es de solo lectura.
 *
 * Usa useFormContext() para acceder al formulario del wizard padre.
 * Validación con accountSchema (password + password_confirm).
 */

import { useFormContext } from "react-hook-form";

import type { OnboardingFormData } from "@/schemas/onboarding.schema";

// ---------------------------------------------------------------------------
// Utilidades de fortaleza de contraseña
// ---------------------------------------------------------------------------

type PasswordStrength = "debil" | "media" | "fuerte";

function getPasswordStrength(password: string): PasswordStrength | null {
  if (!password) return null;

  const hasMinLength = password.length >= 8;
  const hasUppercase = /[A-Z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);
  const isLong = password.length >= 12;

  const score = [hasMinLength, hasUppercase, hasNumber, hasSpecial, isLong].filter(Boolean).length;

  if (score <= 2) return "debil";
  if (score <= 3) return "media";
  return "fuerte";
}

const strengthConfig: Record<
  PasswordStrength,
  { label: string; color: string; barClass: string }
> = {
  debil: {
    label: "Débil",
    color: "text-red-600",
    barClass: "bg-red-400",
  },
  media: {
    label: "Media",
    color: "text-amber-600",
    barClass: "bg-amber-400",
  },
  fuerte: {
    label: "Fuerte",
    color: "text-green-600",
    barClass: "bg-green-500",
  },
};

const strengthWidths: Record<PasswordStrength, string> = {
  debil: "w-1/3",
  media: "w-2/3",
  fuerte: "w-full",
};

// ---------------------------------------------------------------------------
// Estilos compartidos (design system Cal.com)
// ---------------------------------------------------------------------------

const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-link-blue/50 disabled:bg-light-gray disabled:text-mid-gray shadow-ring";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AccountStepProps {
  /** Email pre-rellenado desde el token de invitación — siempre readonly. */
  email: string;
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function AccountStep({ email }: AccountStepProps) {
  const {
    register,
    watch,
    formState: { errors },
  } = useFormContext<OnboardingFormData>();

  const password = watch("password") ?? "";
  const strength = getPasswordStrength(password);
  const strengthInfo = strength ? strengthConfig[strength] : null;

  return (
    <div className="space-y-5">
      {/* Email — readonly */}
      <label className="block text-sm font-medium text-charcoal">
        Correo electrónico
        <input
          type="email"
          value={email}
          readOnly
          disabled
          className={inputClass}
          aria-label="Correo electrónico (pre-rellenado desde tu invitación)"
        />
        <span className="mt-1 block text-xs text-mid-gray">
          Este correo viene de tu invitación y no puede cambiarse.
        </span>
      </label>

      {/* Contraseña */}
      <div>
        <label className="block text-sm font-medium text-charcoal">
          Contraseña
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Min. 8 caracteres, una mayúscula y un número"
            className={inputClass}
            {...register("password")}
          />
        </label>

        {/* Indicador de fortaleza */}
        {password.length > 0 && strengthInfo && strength && (
          <div className="mt-2 space-y-1" aria-live="polite" aria-label="Fortaleza de contraseña">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-light-gray">
              <div
                className={`h-full rounded-full transition-all duration-300 ${strengthWidths[strength]} ${strengthInfo.barClass}`}
              />
            </div>
            <span className={`text-xs font-medium ${strengthInfo.color}`}>
              {strengthInfo.label}
            </span>
          </div>
        )}

        {errors.password && (
          <span className="mt-1 block text-xs text-red-600" role="alert">
            {errors.password.message}
          </span>
        )}
      </div>

      {/* Confirmar contraseña */}
      <label className="block text-sm font-medium text-charcoal">
        Confirmar contraseña
        <input
          type="password"
          autoComplete="new-password"
          placeholder="Repite tu contraseña"
          className={inputClass}
          {...register("password_confirm")}
        />
        {errors.password_confirm && (
          <span className="mt-1 block text-xs text-red-600" role="alert">
            {errors.password_confirm.message}
          </span>
        )}
      </label>
    </div>
  );
}
