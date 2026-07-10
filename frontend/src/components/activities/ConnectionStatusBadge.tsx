/**
 * ConnectionStatusBadge — píldora de estado de la conexión Strava de un atleta
 * (feature 025, T025).
 *
 * Mirror del patrón `STATE_CONFIG` de `ConsentStatusPanel` / `RelationshipBadge`
 * de `LinkedParentsCard`: un mapeo `status → { label, icon, variant }` sobre el
 * primitivo `Badge` de shadcn/ui.
 *
 * Estados (mirror de `StravaConnectionStatus` en `types/strava.types.ts` y del
 * contrato `contracts/api.md §D`):
 *   - none         → nunca se conectó. Variante neutra.
 *   - active       → sincronizando con normalidad. Variante success (verde).
 *   - broken       → token inválido / revocado desde Strava. Variante warning
 *                    (ámbar) — requiere reconectar, no es un error destructivo.
 *   - disconnected → desconexión intencional (familia o coach). Variante
 *                    secondary (neutra) — estado válido, no un error.
 */
import { CheckCircle2, CircleOff, Link2Off, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { StravaConnectionStatus } from "@/types/strava.types";

interface StatusConfig {
  label: string;
  icon: React.ReactNode;
  variant: "success" | "warning" | "secondary";
}

const STATUS_CONFIG: Record<StravaConnectionStatus, StatusConfig> = {
  none: {
    label: "Sin conectar",
    icon: <CircleOff size={13} aria-hidden="true" />,
    variant: "secondary",
  },
  active: {
    label: "Conectado",
    icon: <CheckCircle2 size={13} aria-hidden="true" />,
    variant: "success",
  },
  broken: {
    label: "Conexión rota",
    icon: <TriangleAlert size={13} aria-hidden="true" />,
    variant: "warning",
  },
  disconnected: {
    label: "Desconectado",
    icon: <Link2Off size={13} aria-hidden="true" />,
    variant: "secondary",
  },
};

interface ConnectionStatusBadgeProps {
  status: StravaConnectionStatus;
  className?: string;
}

export function ConnectionStatusBadge({ status, className }: ConnectionStatusBadgeProps) {
  const config = STATUS_CONFIG[status];

  return (
    <Badge variant={config.variant} className={cn("gap-1", className)}>
      {config.icon}
      {config.label}
    </Badge>
  );
}
