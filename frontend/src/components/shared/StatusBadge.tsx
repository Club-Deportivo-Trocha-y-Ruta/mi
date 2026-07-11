import type { LucideIcon } from "lucide-react";
import { AlertCircle, AlertTriangle, CheckCircle2, Circle } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * StatusBadge — insignia de estado (pill) que combina color + ícono + texto.
 * El color nunca es el único canal (constitution III): `label` siempre se
 * renderiza en un tono neutro de alto contraste y cada estado trae un ícono
 * por defecto si no se pasa uno propio. El tinte bg/border usa el token del
 * estado; el ícono lleva el color del token (soporte visual adicional), pero
 * el texto se mantiene en charcoal/mid-gray porque success/warning solos
 * sobre fondo claro no alcanzan el contraste 4.5:1 de WCAG AA en texto
 * pequeño (mismo patrón que ErrorState: color en ícono, texto en charcoal).
 */
export type Status = "success" | "warning" | "danger" | "neutral";

interface StatusBadgeProps {
  status: Status;
  label: string;
  icon?: LucideIcon;
}

const PILL_CLASSES: Record<Status, string> = {
  success: "bg-success/10 border border-success/30",
  warning: "bg-warning/10 border border-warning/30",
  danger: "bg-danger/10 border border-danger/30",
  neutral: "bg-light-gray border border-transparent",
};

const ICON_CLASSES: Record<Status, string> = {
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  neutral: "text-mid-gray",
};

const LABEL_CLASSES: Record<Status, string> = {
  success: "text-charcoal",
  warning: "text-charcoal",
  danger: "text-charcoal",
  neutral: "text-mid-gray",
};

const DEFAULT_ICONS: Record<Status, LucideIcon> = {
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertCircle,
  neutral: Circle,
};

export function StatusBadge({ status, label, icon }: StatusBadgeProps) {
  const Icon = icon ?? DEFAULT_ICONS[status];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        PILL_CLASSES[status],
        LABEL_CLASSES[status],
      )}
    >
      <Icon size={12} className={cn("shrink-0", ICON_CLASSES[status])} aria-hidden="true" />
      {label}
    </span>
  );
}
