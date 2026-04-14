import { MaturationStatus } from "@/types/enums";

interface PHVBadgeProps {
  status: MaturationStatus | null;
}

function badgeClasses(status: MaturationStatus | null): string {
  if (status === MaturationStatus.PrePHV) return "bg-emerald-100 text-emerald-800";
  if (status === MaturationStatus.CircaPHV) return "bg-amber-100 text-amber-800";
  if (status === MaturationStatus.PostPHV) return "bg-blue-100 text-blue-800";
  return "bg-slate-100 text-slate-700";
}

export function PHVBadge({ status }: PHVBadgeProps) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-1 text-xs font-medium ${badgeClasses(status)}`}
    >
      {status ?? "Sin evaluar"}
    </span>
  );
}
