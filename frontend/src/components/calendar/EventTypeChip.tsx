import { cn } from "@/lib/utils";
import type { EventType } from "@/types/calendar.types";
import { colorForEventType } from "./colors";

interface EventTypeChipProps {
  eventType: EventType;
  className?: string;
}

export function EventTypeChip({ eventType, className }: EventTypeChipProps) {
  const colors = colorForEventType(eventType);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        colors.badge,
        className,
      )}
    >
      {colors.label}
    </span>
  );
}
