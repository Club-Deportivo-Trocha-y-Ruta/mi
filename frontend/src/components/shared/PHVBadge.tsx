import { cn } from "@/lib/utils";
import { MaturationStatus } from "@/types/enums";

interface PHVBadgeProps {
  status: MaturationStatus | null;
  size?: "sm" | "md";
}

function badgeClasses(status: MaturationStatus | null): string {
  if (status === MaturationStatus.PrePHV) return "bg-blue-100 text-blue-700";
  if (status === MaturationStatus.CircaPHV) return "bg-amber-100 text-amber-700";
  if (status === MaturationStatus.PostPHV) return "bg-green-100 text-green-700";
  return "bg-slate-100 text-slate-600";
}

export function PHVBadge({ status, size = "sm" }: PHVBadgeProps) {
  return (
    <span
      className={cn(
        "inline-block rounded-full font-medium",
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
        badgeClasses(status),
      )}
    >
      {status ?? "Sin evaluar"}
    </span>
  );
}
