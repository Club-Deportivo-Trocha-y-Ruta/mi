import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import type { SessionStatus } from "@/types/trainingSession.types";

/**
 * Adaptador puro `SessionStatus → StatusBadge`
 * (`contracts/status-vocabulary-sweep.md` §3).
 */
export function sessionStatus(status: SessionStatus): { status: Status; label: string } {
  switch (status) {
    case "planned":
      return { status: "neutral", label: "Planificada" };
    case "executed":
      return { status: "success", label: "Ejecutada" };
    case "cancelled":
      return { status: "danger", label: "Cancelada" };
  }
}

interface SessionStatusBadgeProps {
  status: SessionStatus;
}

export function SessionStatusBadge({ status }: SessionStatusBadgeProps) {
  const { status: badgeStatus, label } = sessionStatus(status);
  return <StatusBadge status={badgeStatus} label={label} />;
}
