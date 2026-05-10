import type { EventType } from "@/types/calendar.types";

interface EventTypeColor {
  bg: string;       // hex background for FullCalendar events
  text: string;     // hex text color
  badge: string;    // Tailwind classes for badge
  label: string;    // Human-readable label in Spanish
}

export const EVENT_TYPE_COLORS: Record<EventType, EventTypeColor> = {
  training_session: {
    bg: "#2f2f2f",
    text: "#ffffff",
    badge: "bg-charcoal text-white",
    label: "Entrenamiento",
  },
  competition: {
    bg: "#dc2626",
    text: "#ffffff",
    badge: "bg-red-600 text-white",
    label: "Competencia",
  },
  club_event: {
    bg: "#2563eb",
    text: "#ffffff",
    badge: "bg-blue-600 text-white",
    label: "Evento del club",
  },
  personal_training: {
    bg: "#0d9488",
    text: "#ffffff",
    badge: "bg-teal-600 text-white",
    label: "Entrenamiento personal",
  },
  group_training: {
    bg: "#898989",
    text: "#ffffff",
    badge: "bg-mid-gray text-white",
    label: "Entrenamiento grupal",
  },
  rest_day: {
    bg: "#d1d5db",
    text: "#374151",
    badge: "bg-gray-200 text-gray-700",
    label: "Día de descanso",
  },
};

export function colorForEventType(eventType: EventType): EventTypeColor {
  return EVENT_TYPE_COLORS[eventType] ?? EVENT_TYPE_COLORS.club_event;
}

export function bgForEventType(eventType: EventType): string {
  return colorForEventType(eventType).bg;
}

export function labelForEventType(eventType: EventType): string {
  return colorForEventType(eventType).label;
}
