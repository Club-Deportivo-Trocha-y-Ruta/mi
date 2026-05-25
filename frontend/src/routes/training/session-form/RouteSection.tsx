/**
 * RouteSection — Sección "Recorrido (opcional)" del formulario de sesión.
 *
 * Captura texto libre y link de Strava. Extraída de SessionFormPage en B5.
 */
import type { FieldErrors, UseFormRegister } from "react-hook-form";

import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 shadow-ring";
const errorClass = "mt-1 text-xs text-red-600";

export interface RouteSectionProps {
  register: UseFormRegister<TrainingSessionFormValues>;
  errors: FieldErrors<TrainingSessionFormValues>;
}

export function RouteSection({ register, errors }: RouteSectionProps) {
  return (
    <div className="rounded-xl bg-white p-5 space-y-4 shadow-card">
      <div>
        <h2 className="text-base font-semibold text-charcoal">
          Recorrido{" "}
          <span className="text-sm font-normal text-mid-gray">(opcional)</span>
        </h2>
      </div>

      <div>
        <label htmlFor="route-description" className={labelClass}>Descripción del recorrido</label>
        <textarea
          id="route-description"
          rows={3}
          placeholder="Describe el recorrido en texto libre (máx. 500 caracteres)..."
          {...register("route_text")}
          className={`${inputClass} resize-none`}
          aria-describedby={errors.route_text ? "route_text-error" : undefined}
          aria-invalid={!!errors.route_text}
        />
        {errors.route_text && (
          <p id="route_text-error" className={errorClass}>{errors.route_text.message}</p>
        )}
      </div>

      <div>
        <label htmlFor="strava-url" className={labelClass}>Link Strava (actividad del entrenador)</label>
        <input
          id="strava-url"
          type="url"
          placeholder="https://www.strava.com/activities/..."
          {...register("strava_url")}
          className={inputClass}
          aria-describedby={errors.strava_url ? "strava_url-error" : undefined}
          aria-invalid={!!errors.strava_url}
        />
        {errors.strava_url && (
          <p id="strava_url-error" className={errorClass}>{errors.strava_url.message}</p>
        )}
      </div>
    </div>
  );
}
