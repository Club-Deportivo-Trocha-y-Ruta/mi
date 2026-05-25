/**
 * PersonalTrainingFields — campos específicos para event_type="personal_training".
 * Extraído de EventForm en B5.
 */
import type { UseFormRegister } from "react-hook-form";

import type { CalendarEventFormInput } from "@/schemas/calendar.schema";
import { INTENSITY_OPTIONS, inputClass, labelClass } from "./fieldStyles";

export interface PersonalTrainingFieldsProps {
  register: UseFormRegister<CalendarEventFormInput>;
}

export function PersonalTrainingFields({ register }: PersonalTrainingFieldsProps) {
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="pt-intensity" className={labelClass}>
          Intensidad
        </label>
        <select
          id="pt-intensity"
          {...register("data_personal_training.intensity")}
          className={inputClass}
        >
          {INTENSITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
