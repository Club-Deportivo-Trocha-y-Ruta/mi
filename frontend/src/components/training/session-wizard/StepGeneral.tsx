import { Controller } from "react-hook-form";
import type {
  Control,
  FieldErrors,
  UseFormRegister,
} from "react-hook-form";

import { DurationPicker } from "@/components/training/DurationPicker";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  SESSION_KIND_OPTIONS,
  type TrainingSessionFormValues,
} from "@/schemas/trainingSession.schema";

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full min-h-[48px] rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };
const errorClass = "mt-1 text-xs text-red-600";

/** Small "IA" badge rendered next to a field label when AI pre-filled it. */
function AiMarker() {
  return (
    <span
      className="ml-1.5 inline-block rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700 align-middle"
      data-testid="ai-marker"
      aria-label="Sugerido por IA"
      title="Sugerido por el asistente IA. Edita el campo para personalizar."
    >
      IA
    </span>
  );
}

interface StepGeneralProps {
  register: UseFormRegister<TrainingSessionFormValues>;
  control: Control<TrainingSessionFormValues>;
  errors: FieldErrors<TrainingSessionFormValues>;
  /** Fields pre-filled by the AI assistant; shows a marker that clears on edit. */
  aiSeededFields?: Set<string>;
}

export function StepGeneral({ register, control, errors, aiSeededFields }: StepGeneralProps) {
  const seeded = aiSeededFields ?? new Set<string>();

  return (
    <div className="space-y-4" data-testid="session-step-general">
      <div className="grid gap-4 sm:grid-cols-[180px_180px] justify-start">
        <div>
          <label htmlFor="scheduled_date-input" className={labelClass}>
            Fecha
            {seeded.has("scheduled_date") && <AiMarker />}
          </label>
          <input
            id="scheduled_date-input"
            type="date"
            {...register("scheduled_date")}
            className={inputClass}
            style={inputStyle}
            aria-describedby={errors.scheduled_date ? "scheduled_date-error" : undefined}
            aria-invalid={!!errors.scheduled_date}
          />
          {errors.scheduled_date && (
            <p id="scheduled_date-error" className={errorClass}>
              {errors.scheduled_date.message}
            </p>
          )}
        </div>
        <div>
          <label htmlFor="scheduled_start_time-input" className={labelClass}>
            Hora de inicio
            {seeded.has("scheduled_start_time") && <AiMarker />}
          </label>
          <input
            id="scheduled_start_time-input"
            type="time"
            {...register("scheduled_start_time")}
            className={inputClass}
            style={inputStyle}
            aria-describedby={
              errors.scheduled_start_time ? "scheduled_start_time-error" : undefined
            }
            aria-invalid={!!errors.scheduled_start_time}
          />
          {errors.scheduled_start_time && (
            <p id="scheduled_start_time-error" className={errorClass}>
              {errors.scheduled_start_time.message}
            </p>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-start">
        <div className="sm:max-w-[260px]">
          {seeded.has("duration_min") && (
            <div className="mb-0.5 flex items-center gap-1">
              <AiMarker />
              <span className="sr-only">Campo sugerido por el asistente IA</span>
            </div>
          )}
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
          <label htmlFor="location-input" className={labelClass}>
            Lugar
            {seeded.has("location") && <AiMarker />}
          </label>
          <input
            id="location-input"
            type="text"
            placeholder="Ej: Pista XCO La Buitrera"
            {...register("location")}
            className={inputClass}
            style={inputStyle}
            aria-describedby={errors.location ? "location-error" : undefined}
            aria-invalid={!!errors.location}
          />
          {errors.location && (
            <p id="location-error" className={errorClass}>
              {errors.location.message}
            </p>
          )}
        </div>
      </div>

      <div>
        <label htmlFor="technical_focus-input" className={labelClass}>
          Foco técnico
          {seeded.has("technical_focus") && <AiMarker />}
        </label>
        <input
          id="technical_focus-input"
          type="text"
          placeholder="Ej: Técnica de frenada en descenso"
          {...register("technical_focus")}
          className={inputClass}
          style={inputStyle}
          aria-describedby={errors.technical_focus ? "technical_focus-error" : undefined}
          aria-invalid={!!errors.technical_focus}
        />
        {errors.technical_focus && (
          <p id="technical_focus-error" className={errorClass}>
            {errors.technical_focus.message}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="description-input" className={labelClass}>
          Descripción
          {seeded.has("description") && <AiMarker />}
        </label>
        <textarea
          id="description-input"
          rows={4}
          placeholder="Describe el plan de la sesión, objetivos, metodología..."
          {...register("description")}
          className={`${inputClass} resize-none`}
          style={inputStyle}
          aria-describedby={errors.description ? "description-error" : undefined}
          aria-invalid={!!errors.description}
        />
        {errors.description && (
          <p id="description-error" className={errorClass}>
            {errors.description.message}
          </p>
        )}
      </div>

      {/* Tipo de sesión — chips ToggleGroup (≥48px) */}
      <div>
        <span className={labelClass} id="session_kind-label">
          Tipo de sesión
          {seeded.has("session_kind") && <AiMarker />}
        </span>
        <Controller
          name="session_kind"
          control={control}
          render={({ field }) => (
            <ToggleGroup
              type="single"
              value={field.value ?? "entrenamiento"}
              onValueChange={(v) => {
                if (v) field.onChange(v);
              }}
              className="mt-1 flex flex-wrap gap-1.5"
              aria-labelledby="session_kind-label"
              data-testid="session-kind-toggle"
            >
              {SESSION_KIND_OPTIONS.map((opt) => (
                <ToggleGroupItem
                  key={opt.value}
                  value={opt.value}
                  aria-label={opt.label}
                  className="min-h-[48px] rounded-lg border border-[rgba(34,42,53,0.12)] px-3 py-1.5 text-xs font-medium text-charcoal transition-colors data-[state=on]:border-charcoal data-[state=on]:bg-charcoal data-[state=on]:text-white"
                >
                  {opt.label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          )}
        />
      </div>

      <div>
        <label htmlFor="objectives-input" className={labelClass}>
          Objetivos de la sesión{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
          {seeded.has("objectives") && <AiMarker />}
        </label>
        <textarea
          id="objectives-input"
          rows={3}
          placeholder="Lista los objetivos específicos de esta sesión…"
          {...register("objectives")}
          className={`${inputClass} resize-none`}
          style={inputStyle}
          aria-describedby={errors.objectives ? "objectives-error" : undefined}
          aria-invalid={!!errors.objectives}
        />
        {errors.objectives && (
          <p id="objectives-error" className={errorClass}>
            {errors.objectives.message}
          </p>
        )}
      </div>
    </div>
  );
}
