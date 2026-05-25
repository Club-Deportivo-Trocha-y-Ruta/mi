/**
 * RestDayFields — campos específicos para event_type="rest_day".
 * Extraído de EventForm en B5.
 */
import type { FieldErrors, UseFormRegister } from "react-hook-form";

import type { CalendarEventFormInput } from "@/schemas/calendar.schema";
import { errorClass, inputClass, labelClass } from "./fieldStyles";

export interface RestDayFieldsProps {
  register: UseFormRegister<CalendarEventFormInput>;
  errors: FieldErrors<CalendarEventFormInput>;
}

export function RestDayFields({ register, errors }: RestDayFieldsProps) {
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="rd-scope" className={labelClass}>
          Alcance
        </label>
        <select
          id="rd-scope"
          {...register("data_rest_day.scope")}
          className={inputClass}
        >
          <option value="club">Todo el club</option>
          <option value="category">Por categoría</option>
          <option value="athlete">Atleta específico</option>
        </select>
      </div>
      <div>
        <label htmlFor="rd-reason" className={labelClass}>
          Motivo{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
        </label>
        <input
          id="rd-reason"
          type="text"
          placeholder="Ej: Semana de recuperación post-carrera"
          {...register("data_rest_day.reason")}
          className={inputClass}
        />
        {errors.data_rest_day?.reason && (
          <p className={errorClass}>{errors.data_rest_day.reason.message}</p>
        )}
      </div>
    </div>
  );
}
