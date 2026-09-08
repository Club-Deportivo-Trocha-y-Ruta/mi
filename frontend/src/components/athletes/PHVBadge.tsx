import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { MaturationStatus } from "@/types/enums";

interface PHVBadgeProps {
  status: MaturationStatus | null;
  size?: "sm" | "md";
}

/**
 * Mapeo de `MaturationStatus` a `StatusBadge` (icono + etiqueta, nunca solo
 * color — constitution III). Pre-PHV es neutral (fase temprana, sin
 * urgencia), Circa-PHV es warning (ventana de máxima vulnerabilidad ósea) y
 * Post-PHV es success (brote de crecimiento completado).
 */
const STATUS_MAP: Record<MaturationStatus, { status: Status; label: string }> = {
  [MaturationStatus.PrePHV]: { status: "neutral", label: "Pre-PHV" },
  [MaturationStatus.CircaPHV]: { status: "warning", label: "Circa-PHV" },
  [MaturationStatus.PostPHV]: { status: "success", label: "Post-PHV" },
};

export function PHVBadge({ status, size = "sm" }: PHVBadgeProps) {
  const badge = status !== null ? STATUS_MAP[status] : { status: "neutral" as Status, label: "Sin evaluar" };

  return (
    <span className={size === "md" ? "text-sm" : undefined}>
      <StatusBadge status={badge.status} label={badge.label} />
    </span>
  );
}
