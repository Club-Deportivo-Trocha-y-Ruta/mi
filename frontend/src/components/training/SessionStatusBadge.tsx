import type { SessionStatus } from "@/types/trainingSession.types";

interface SessionStatusBadgeProps {
  status: SessionStatus;
}

const config: Record<SessionStatus, { label: string; className: string }> = {
  planned: {
    label: "Planificada",
    className: "bg-light-gray text-charcoal",
  },
  executed: {
    label: "Ejecutada",
    className: "bg-green-100 text-green-800",
  },
  cancelled: {
    label: "Cancelada",
    className: "bg-red-100 text-red-700",
  },
};

export function SessionStatusBadge({ status }: SessionStatusBadgeProps) {
  const { label, className } = config[status] ?? config.planned;
  return (
    <span
      data-status={status}
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}
    >
      {label}
    </span>
  );
}
