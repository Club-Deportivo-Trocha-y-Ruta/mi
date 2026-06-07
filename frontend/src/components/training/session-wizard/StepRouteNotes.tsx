import type { FieldErrors, UseFormRegister } from "react-hook-form";

import { RouteFileDropzone } from "@/components/training/RouteFileDropzone";
import type { TrainingSessionFormValues } from "@/schemas/trainingSession.schema";

const labelClass = "block text-sm font-medium text-charcoal";
const inputClass =
  "mt-1 w-full min-h-[48px] rounded-lg bg-white px-3 py-2 text-sm text-charcoal placeholder:text-mid-gray outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40";
const inputStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };
const errorClass = "mt-1 text-xs text-red-600";

interface StepRouteNotesProps {
  register: UseFormRegister<TrainingSessionFormValues>;
  errors: FieldErrors<TrainingSessionFormValues>;
  routeFile: File | null;
  onRouteFileChange: (file: File | null) => void;
  routeFileError?: string | null;
}

export function StepRouteNotes({
  register,
  errors,
  routeFile,
  onRouteFileChange,
  routeFileError,
}: StepRouteNotesProps) {
  return (
    <div className="space-y-4" data-testid="session-step-route-notes">
      <div>
        <label htmlFor="route_text-input" className={labelClass}>
          Descripción del recorrido{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
        </label>
        <textarea
          id="route_text-input"
          rows={3}
          placeholder="Describe el recorrido en texto libre (máx. 500 caracteres)..."
          {...register("route_text")}
          className={`${inputClass} resize-none`}
          style={inputStyle}
          aria-describedby={errors.route_text ? "route_text-error" : undefined}
          aria-invalid={!!errors.route_text}
        />
        {errors.route_text && (
          <p id="route_text-error" className={errorClass}>
            {errors.route_text.message}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="strava_url-input" className={labelClass}>
          Link Strava{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
        </label>
        <input
          id="strava_url-input"
          type="url"
          inputMode="url"
          placeholder="https://www.strava.com/activities/..."
          {...register("strava_url")}
          className={inputClass}
          style={inputStyle}
          aria-describedby={errors.strava_url ? "strava_url-error" : undefined}
          aria-invalid={!!errors.strava_url}
        />
        {errors.strava_url && (
          <p id="strava_url-error" className={errorClass}>
            {errors.strava_url.message}
          </p>
        )}
      </div>

      <RouteFileDropzone
        value={routeFile}
        onChange={onRouteFileChange}
        error={routeFileError}
      />

      <div>
        <label htmlFor="coach_notes-input" className={labelClass}>
          Notas del entrenador{" "}
          <span className="font-normal text-mid-gray">(privadas, opcional)</span>
        </label>
        <textarea
          id="coach_notes-input"
          rows={3}
          placeholder="Notas internas — no se comparten con las familias."
          {...register("coach_notes")}
          className={`${inputClass} resize-none`}
          style={inputStyle}
          aria-describedby={errors.coach_notes ? "coach_notes-error" : undefined}
          aria-invalid={!!errors.coach_notes}
        />
        {errors.coach_notes && (
          <p id="coach_notes-error" className={errorClass}>
            {errors.coach_notes.message}
          </p>
        )}
      </div>
    </div>
  );
}
