/**
 * CompetitionStatusBadges — 3 badges compactos que resumen el estado de una
 * válida en la lista de competencias.
 *
 * Badges:
 *   1. Resultados  → verde si has_results=true, gris si false
 *   2. Calendario  → ícono Link (verde) / Unlink (gris) según has_calendar_event
 *   3. Condiciones → verde/ámbar/gris según conditions_completeness
 *
 * Principio UX: sin lenguaje de warning para el badge "vacío" — sólo
 * diferencia visual entre completo, parcial y pendiente (mismo patrón que
 * RaceConditionsCard).
 */
import type { LucideIcon } from "lucide-react";
import { Link2, Link2Off, Trophy } from "lucide-react";

import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { RaceEventListItem } from "@/types/raceEvents.types";

/**
 * Adaptadores puros de los 3 sub-badges → `StatusBadge`
 * (`contracts/status-vocabulary-sweep.md` §2).
 */
export interface CompetitionStatusAdapterResult {
  status: Status;
  label: string;
  icon: LucideIcon;
}

export function resultadosStatus(hasResults: boolean): CompetitionStatusAdapterResult {
  return hasResults
    ? { status: "success", label: "Con resultados", icon: Trophy }
    : { status: "neutral", label: "Sin resultados", icon: Trophy };
}

export function calendarioStatus(
  hasCalendarEvent: boolean,
): CompetitionStatusAdapterResult {
  return hasCalendarEvent
    ? { status: "success", label: "Calendario", icon: Link2 }
    : { status: "neutral", label: "Sin calendario", icon: Link2Off };
}

/** `state` viene de `RaceEventListItem.conditions_completeness`, cuyo
 * valor real es `"empty"` (no `"none"`) — el contrato usa "none" solo
 * como nombre descriptivo del estado vacío. */
export function condicionesStatus(
  state: RaceEventListItem["conditions_completeness"],
): { status: Status; label: string } {
  switch (state) {
    case "complete":
      return { status: "success", label: "Condiciones OK" };
    case "partial":
      return { status: "warning", label: "Condiciones parciales" };
    case "empty":
      return { status: "neutral", label: "Sin condiciones" };
  }
}

interface CompetitionStatusBadgesProps {
  item: RaceEventListItem;
}

export function CompetitionStatusBadges({ item }: CompetitionStatusBadgesProps) {
  const resultados = resultadosStatus(item.has_results);
  const calendario = calendarioStatus(item.has_calendar_event);
  const condiciones = condicionesStatus(item.conditions_completeness);

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex items-center gap-1.5">
        {/* Badge 1 — Resultados */}
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <StatusBadge
                status={resultados.status}
                label={resultados.label}
                icon={resultados.icon}
              />
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {item.has_results
              ? "Esta válida tiene resultados importados."
              : "Aún no se han importado resultados para esta válida."}
          </TooltipContent>
        </Tooltip>

        {/* Badge 2 — Calendario */}
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <StatusBadge
                status={calendario.status}
                label={calendario.label}
                icon={calendario.icon}
              />
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {item.has_calendar_event
              ? "Esta válida está vinculada a un evento del calendario."
              : "Esta válida no tiene evento de calendario asociado."}
          </TooltipContent>
        </Tooltip>

        {/* Badge 3 — Condiciones */}
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <StatusBadge status={condiciones.status} label={condiciones.label} />
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {item.conditions_completeness === "complete"
              ? "Todas las condiciones logísticas están registradas."
              : item.conditions_completeness === "partial"
                ? "Algunas condiciones logísticas están pendientes."
                : "No se han registrado condiciones logísticas para esta válida."}
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
}
