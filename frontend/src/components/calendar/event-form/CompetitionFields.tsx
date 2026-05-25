/**
 * CompetitionFields — campos específicos para event_type="competition".
 *
 * Incluye el dropdown FE-2 (race_event_id) que enlaza el evento a una
 * válida concreta. La lista viene de useAvailableRaceEvents + override
 * con la válida ya enlazada cuando estamos en modo edit.
 *
 * Extraído de EventForm en B5.
 */
import { Controller, type Control, type FieldErrors, type UseFormRegister } from "react-hook-form";
import { Link as RouterLink } from "react-router-dom";

import type { CalendarEventFormInput } from "@/schemas/calendar.schema";
import type { AvailableRaceEvent } from "@/types/calendar.types";

import {
  COMPETITION_CATEGORIES,
  errorClass,
  inputClass,
  labelClass,
} from "./fieldStyles";

/**
 * Subconjunto del UseQueryResult que necesitamos para los mensajes de
 * loading / error / empty del dropdown FE-2. EventForm extrae los flags
 * y los pasa como un objeto pequeño — esto evita re-renders innecesarios
 * cuando otros campos del UseQueryResult cambian (data, dataUpdatedAt…).
 */
export interface RaceEventsQueryStatus {
  isLoading: boolean;
  isError: boolean;
}

export interface CompetitionFieldsProps {
  control: Control<CalendarEventFormInput>;
  register: UseFormRegister<CalendarEventFormInput>;
  errors: FieldErrors<CalendarEventFormInput>;
  raceEventOptions: AvailableRaceEvent[];
  raceEventsQuery: RaceEventsQueryStatus;
  seasonForRaceEvents: number;
}

export function CompetitionFields({
  control,
  register,
  errors,
  raceEventOptions,
  raceEventsQuery,
  seasonForRaceEvents,
}: CompetitionFieldsProps) {
  return (
    <div className="space-y-4">
      {/* FE-2: dropdown obligatorio que asocia este calendar_event
          a una válida concreta de race_events. La lista viene del
          endpoint /api/race-events/available-for-calendar y excluye
          las válidas ya enlazadas a otro evento del calendario. */}
      <div>
        <label htmlFor="comp-race-event" className={labelClass}>
          Válida asociada
        </label>
        <Controller
          name="race_event_id"
          control={control}
          render={({ field }) => (
            <select
              id="comp-race-event"
              ref={field.ref}
              name={field.name}
              onBlur={field.onBlur}
              value={field.value == null ? "" : String(field.value)}
              onChange={(e) => {
                const v = e.target.value;
                field.onChange(v === "" ? null : Number(v));
              }}
              aria-invalid={!!errors.race_event_id}
              aria-describedby={
                errors.race_event_id ? "comp-race-event-error" : undefined
              }
              disabled={
                raceEventsQuery.isLoading ||
                (raceEventOptions.length === 0 && !raceEventsQuery.isError)
              }
              className={inputClass}
              data-testid="event-race-event-id"
            >
              <option value="">
                {raceEventsQuery.isLoading
                  ? "Cargando válidas…"
                  : "Selecciona una válida…"}
              </option>
              {raceEventOptions.map((r) => (
                <option key={r.id} value={String(r.id)}>
                  {r.sequence_number > 0
                    ? `Válida ${r.sequence_number} — ${r.name} (${r.event_date})`
                    : `${r.name}${r.event_date ? ` (${r.event_date})` : ""}`}
                </option>
              ))}
            </select>
          )}
        />
        {raceEventsQuery.isError && (
          <p className={errorClass}>
            No se pudo cargar la lista de válidas. Intenta de nuevo en unos
            segundos.
          </p>
        )}
        {!raceEventsQuery.isLoading &&
          !raceEventsQuery.isError &&
          raceEventOptions.length === 0 && (
            <p
              className="mt-1 text-xs text-mid-gray"
              data-testid="event-race-event-empty"
            >
              No hay válidas disponibles para {seasonForRaceEvents}. Crea una
              desde el{" "}
              <RouterLink
                to="/coach/race-analysis"
                className="font-medium text-charcoal underline transition-opacity hover:opacity-70"
              >
                módulo de resultados
              </RouterLink>
              .
            </p>
          )}
        {errors.race_event_id && (
          <p id="comp-race-event-error" className={errorClass}>
            {errors.race_event_id.message}
          </p>
        )}
        {/* TODO(FE-3+): permitir crear una válida inline cuando el coach
            está agendando una competencia sin PDF aún. */}
      </div>
      <div>
        <label htmlFor="comp-city" className={labelClass}>
          Ciudad
        </label>
        <input
          id="comp-city"
          type="text"
          placeholder="Ej: Cali"
          {...register("data_competition.city")}
          className={inputClass}
        />
        {errors.data_competition?.city && (
          <p className={errorClass}>{errors.data_competition.city.message}</p>
        )}
      </div>
      <div>
        <label htmlFor="comp-race-category" className={labelClass}>
          Categoría de carrera
        </label>
        <select
          id="comp-race-category"
          {...register("data_competition.race_category")}
          className={inputClass}
        >
          {COMPETITION_CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-charcoal">
        <input
          type="checkbox"
          {...register("data_competition.is_departmental")}
          className="h-4 w-4 rounded border-mid-gray"
        />
        Campeonato Departamental
      </label>
    </div>
  );
}
