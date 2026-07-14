/**
 * ConnectionStatusBadge — píldora de estado de la conexión Strava de un atleta
 * (feature 025, T025; migrado a `StatusBadge` en feature 033, T016 —
 * `contracts/status-vocabulary-sweep.md` §1).
 *
 * Renderiza el adaptador puro `connectionStatus()` sobre `<StatusBadge>`
 * (color + ícono + texto siempre juntos, Constitution III).
 *
 * Estados (mirror de `StravaConnectionStatus` en `types/strava.types.ts` y del
 * contrato `contracts/api.md §D`):
 *   - none         → nunca se conectó. Estado neutral.
 *   - active       → sincronizando con normalidad. Estado success (verde).
 *   - broken       → token inválido / revocado desde Strava. Estado warning
 *                    (ámbar) — requiere reconectar, no es un error destructivo.
 *   - disconnected → desconexión intencional (familia o coach). Estado
 *                    neutral — estado válido, no un error.
 */
import type { LucideIcon } from "lucide-react";
import { CheckCircle2, CircleOff, Link2Off, TriangleAlert } from "lucide-react";

import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import type { StravaConnectionStatus } from "@/types/strava.types";

/**
 * Adaptador puro `StravaConnectionStatus → StatusBadge`
 * (`contracts/status-vocabulary-sweep.md` §1).
 */
export interface ConnectionStatusAdapterResult {
  status: Status;
  label: string;
  icon: LucideIcon;
}

export function connectionStatus(
  state: StravaConnectionStatus,
): ConnectionStatusAdapterResult {
  switch (state) {
    case "none":
      return { status: "neutral", label: "Sin conectar", icon: CircleOff };
    case "active":
      return { status: "success", label: "Conectado", icon: CheckCircle2 };
    case "broken":
      return { status: "warning", label: "Conexión rota", icon: TriangleAlert };
    case "disconnected":
      return { status: "neutral", label: "Desconectado", icon: Link2Off };
  }
}

interface ConnectionStatusBadgeProps {
  status: StravaConnectionStatus;
}

export function ConnectionStatusBadge({ status }: ConnectionStatusBadgeProps) {
  const { status: badgeStatus, label, icon } = connectionStatus(status);

  return <StatusBadge status={badgeStatus} label={label} icon={icon} />;
}
