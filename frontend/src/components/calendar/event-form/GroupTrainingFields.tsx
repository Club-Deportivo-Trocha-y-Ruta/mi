/**
 * GroupTrainingFields — campos específicos para event_type="group_training".
 * Extraído de EventForm en B5.
 */
import type { FieldErrors, UseFormRegister } from "react-hook-form";

import type { CalendarEventFormInput } from "@/schemas/calendar.schema";
import {
  INTENSITY_OPTIONS,
  errorClass,
  inputClass,
  labelClass,
} from "./fieldStyles";

export interface GroupTrainingFieldsProps {
  register: UseFormRegister<CalendarEventFormInput>;
  errors: FieldErrors<CalendarEventFormInput>;
}

export function GroupTrainingFields({ register, errors }: GroupTrainingFieldsProps) {
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="gt-intensity" className={labelClass}>
          Intensidad
        </label>
        <select
          id="gt-intensity"
          {...register("data_group_training.intensity")}
          className={inputClass}
        >
          {INTENSITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="gt-group-size" className={labelClass}>
          Máx. atletas{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
        </label>
        <input
          id="gt-group-size"
          type="number"
          min={1}
          max={50}
          {...register("data_group_training.group_size_max", {
            valueAsNumber: true,
          })}
          className={inputClass}
        />
        {errors.data_group_training?.group_size_max && (
          <p className={errorClass}>
            {errors.data_group_training.group_size_max.message}
          </p>
        )}
      </div>
    </div>
  );
}
