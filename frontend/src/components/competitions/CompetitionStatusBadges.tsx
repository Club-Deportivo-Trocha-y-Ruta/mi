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
import { Link2, Link2Off, Trophy } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { RaceEventListItem } from "@/types/raceEvents.types";

interface CompetitionStatusBadgesProps {
  item: RaceEventListItem;
}

export function CompetitionStatusBadges({ item }: CompetitionStatusBadgesProps) {
  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex items-center gap-1.5">
        {/* Badge 1 — Resultados */}
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Badge
                variant={item.has_results ? "success" : "secondary"}
                className="gap-1"
              >
                <Trophy
                  size={10}
                  aria-hidden="true"
                  className={item.has_results ? "text-green-700" : "text-mid-gray"}
                />
                {item.has_results ? "Con resultados" : "Sin resultados"}
              </Badge>
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
              <Badge
                variant={item.has_calendar_event ? "success" : "secondary"}
                className="gap-1"
              >
                {item.has_calendar_event ? (
                  <Link2 size={10} aria-hidden="true" className="text-green-700" />
                ) : (
                  <Link2Off size={10} aria-hidden="true" className="text-mid-gray" />
                )}
                {item.has_calendar_event ? "Calendario" : "Sin calendario"}
              </Badge>
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
              <Badge
                variant={
                  item.conditions_completeness === "complete"
                    ? "success"
                    : item.conditions_completeness === "partial"
                      ? "warning"
                      : "secondary"
                }
              >
                {item.conditions_completeness === "complete"
                  ? "Condiciones OK"
                  : item.conditions_completeness === "partial"
                    ? "Condiciones parciales"
                    : "Sin condiciones"}
              </Badge>
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
