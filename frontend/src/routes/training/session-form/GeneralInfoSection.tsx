/**
 * GeneralInfoSection — Sección "Información general" del formulario de sesión.
 *
 * Captura fecha, hora, duración (DurationPicker), lugar, foco técnico y
 * descripción. Extraída de SessionFormPage en B5.
 */
import { Controller, type Control, type FieldErrors, type UseFormRegister } from "react-hook-form";

import { DurationPicker } from "@/components/training/DurationPicker";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 shadow-ring";
const errorClass = "mt-1 text-xs text-red-600";

export interface GeneralInfoSectionProps {
  register: UseFormRegister<TrainingSessionFormValues>;
  control: Control<TrainingSessionFormValues>;
  errors: FieldErrors<TrainingSessionFormValues>;
}

export function GeneralInfoSection({
  register,
  control,
  errors,
}: GeneralInfoSectionProps) {
  return (
    <div className="rounded-xl bg-white p-5 space-y-4 shadow-card">
      <h2 className="text-base font-semibold text-charcoal">Información general</h2>

      {/* Fecha y hora */}
      <div className="grid gap-4 sm:grid-cols-[180px_180px] justify-start">
        <div>
          <label htmlFor="scheduled_date-input" className={labelClass}>Fecha</label>
          <input
            id="scheduled_date-input"
            type="date"
            {...register("scheduled_date")}
            className={inputClass}
            aria-describedby={errors.scheduled_date ? "scheduled_date-error" : undefined}
            aria-invalid={!!errors.scheduled_date}
          />
          {errors.scheduled_date && (
            <p id="scheduled_date-error" className={errorClass}>{errors.scheduled_date.message}</p>
          )}
        </div>
        <div>
          <label htmlFor="scheduled_start_time-input" className={labelClass}>Hora de inicio</label>
          <input
            id="scheduled_start_time-input"
            type="time"
            {...register("scheduled_start_time")}
            className={inputClass}
            aria-describedby={errors.scheduled_start_time ? "scheduled_start_time-error" : undefined}
            aria-invalid={!!errors.scheduled_start_time}
          />
          {errors.scheduled_start_time && (
            <p id="scheduled_start_time-error" className={errorClass}>{errors.scheduled_start_time.message}</p>
          )}
        </div>
      </div>

      {/* Duración y lugar */}
      <div className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-start">
        <div className="sm:max-w-[260px]">
          <Controller
            name="duration_min"
            control={control}
            render={({ field }) => (
              <DurationPicker
                value={field.value}
                onChange={field.onChange}
                error={errors.duration_min?.message}
              />
            )}
          />
        </div>
        <div>
          <label htmlFor="location-input" className={labelClass}>Lugar</label>
          <input
            id="location-input"
            type="text"
            placeholder="Ej: Pista XCO La Buitrera"
            {...register("location")}
            className={inputClass}
            aria-describedby={errors.location ? "location-error" : undefined}
            aria-invalid={!!errors.location}
          />
          {errors.location && (
            <p id="location-error" className={errorClass}>{errors.location.message}</p>
          )}
        </div>
      </div>

      {/* Foco técnico */}
      <div>
        <label htmlFor="technical_focus-input" className={labelClass}>Foco técnico</label>
        <input
          id="technical_focus-input"
          type="text"
          placeholder="Ej: Técnica de frenada en descenso"
          {...register("technical_focus")}
          className={inputClass}
          aria-describedby={errors.technical_focus ? "technical_focus-error" : undefined}
          aria-invalid={!!errors.technical_focus}
        />
        {errors.technical_focus && (
          <p id="technical_focus-error" className={errorClass}>{errors.technical_focus.message}</p>
        )}
      </div>

      {/* Descripción */}
      <div>
        <label htmlFor="description-input" className={labelClass}>Descripción</label>
        <textarea
          id="description-input"
          rows={4}
          placeholder="Describe el plan de la sesión, objetivos, metodología..."
          {...register("description")}
          className={`${inputClass} resize-none`}
          aria-describedby={errors.description ? "description-error" : undefined}
          aria-invalid={!!errors.description}
        />
        {errors.description && (
          <p id="description-error" className={errorClass}>{errors.description.message}</p>
        )}
      </div>
    </div>
  );
}
