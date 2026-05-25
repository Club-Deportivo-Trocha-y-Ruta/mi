/**
 * ClubEventFields — campos específicos para event_type="club_event".
 * Extraído de EventForm en B5.
 */
import type { FieldErrors, UseFormRegister } from "react-hook-form";

import type { CalendarEventFormInput } from "@/schemas/calendar.schema";
import { errorClass, inputClass, labelClass } from "./fieldStyles";

export interface ClubEventFieldsProps {
  register: UseFormRegister<CalendarEventFormInput>;
  errors: FieldErrors<CalendarEventFormInput>;
}

export function ClubEventFields({ register, errors }: ClubEventFieldsProps) {
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="club-event-kind" className={labelClass}>
          Tipo
        </label>
        <select
          id="club-event-kind"
          {...register("data_club_event.kind")}
          className={inputClass}
        >
          <option value="social">Social</option>
          <option value="meeting">Reunión</option>
          <option value="workshop">Taller</option>
        </select>
      </div>
      <div>
        <label htmlFor="club-event-url" className={labelClass}>
          URL de registro{" "}
          <span className="font-normal text-mid-gray">(opcional)</span>
        </label>
        <input
          id="club-event-url"
          type="url"
          placeholder="https://..."
          {...register("data_club_event.registration_url")}
          className={inputClass}
        />
        {errors.data_club_event?.registration_url && (
          <p className={errorClass}>
            {errors.data_club_event.registration_url.message}
          </p>
        )}
      </div>
    </div>
  );
}
