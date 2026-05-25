import { useCalendarFiltersStore } from "@/store/calendarFilters.store";
import type { EventType } from "@/types/calendar.types";
import { labelForEventType } from "./colors";

const ALL_EVENT_TYPES: EventType[] = [
  "training_session",
  "competition",
  "club_event",
  "personal_training",
  "group_training",
  "rest_day",
];

const inputSelectStyle = { boxShadow: "rgba(34, 42, 53, 0.08) 0px 0px 0px 1px" };

export function CalendarFiltersBar() {
  const {
    eventTypes,
    setEventTypes,
    reset,
  } = useCalendarFiltersStore();

  function toggleEventType(type: EventType) {
    if (eventTypes.includes(type)) {
      setEventTypes(eventTypes.filter((t) => t !== type));
    } else {
      setEventTypes([...eventTypes, type]);
    }
  }

  return (
    <div
      className="rounded-xl bg-white p-4"
    >
      <div className="flex flex-wrap items-end gap-2">
        {/* Event type filter */}
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-mid-gray">Tipo de evento</span>
          <div className="flex flex-wrap gap-1.5">
            {ALL_EVENT_TYPES.map((type) => {
              const active = eventTypes.includes(type);
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() => toggleEventType(type)}
                  className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                    active
                      ? "bg-charcoal text-white"
                      : "bg-white text-charcoal hover:bg-light-gray"
                  }`}
                  style={inputSelectStyle}
                  aria-pressed={active}
                >
                  {labelForEventType(type)}
                </button>
              );
            })}
          </div>
        </div>

        {/* Clear */}
        <button
          type="button"
          onClick={reset}
          className="self-end rounded-lg bg-white px-3 py-2 text-sm font-medium text-mid-gray transition-opacity hover:opacity-70"
          style={inputSelectStyle}
        >
          Limpiar filtros
        </button>
      </div>
    </div>
  );
}

// Named export alias matching the import used in CalendarPage
export { CalendarFiltersBar as FiltersBar };
