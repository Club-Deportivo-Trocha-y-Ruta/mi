/**
 * CaveatsNote — advertencias de lectura de la progresión histórica
 * (feature 044, US6/US7, `contracts/ui-history.md` §1).
 *
 * Siempre presente (`role="note"`) mientras la tarjeta tenga datos —
 * nunca se oculta condicionalmente por espacio ni por preferencia del
 * usuario: leer una gráfica de varias temporadas sin este contexto
 * (circuitos distintos, clima, categorías de tres corredores…) invita a
 * sacar conclusiones que los datos no sostienen. Si la API llegara a
 * enviar una lista vacía o con solo códigos que el frontend todavía no
 * reconoce (catálogo cerrado, ver `RACE_HISTORY_CAVEAT_LABELS`), se
 * conserva un aviso genérico en vez de desaparecer el bloque.
 */
import { Info } from "lucide-react";

import { cn } from "@/lib/utils";
import { RACE_HISTORY_CAVEAT_LABELS } from "@/types/raceHistory.types";
import type { RaceHistoryCaveatCode } from "@/types/raceHistory.types";

export interface CaveatsNoteProps {
  caveats: RaceHistoryCaveatCode[];
  className?: string;
  /** Ancla para `aria-describedby` desde `HistoryChart`/`HistoryTable`. */
  id?: string;
}

export function CaveatsNote({ caveats, className, id }: CaveatsNoteProps) {
  // Catálogo cerrado — un código que el frontend todavía no reconoce se
  // omite en vez de romper el render (mismo criterio que `KEY_SECTOR_LABELS`
  // en el módulo de circuito).
  const known = caveats.filter(
    (c): c is RaceHistoryCaveatCode => c in RACE_HISTORY_CAVEAT_LABELS,
  );

  return (
    <div
      id={id}
      role="note"
      data-testid="history-caveats-note"
      className={cn(
        "flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900",
        className,
      )}
    >
      <Info size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
      {known.length > 0 ? (
        <ul className="list-disc space-y-1 pl-4">
          {known.map((code) => (
            <li key={code}>{RACE_HISTORY_CAVEAT_LABELS[code]}</li>
          ))}
        </ul>
      ) : (
        <p>
          Compara con cautela: cada temporada tiene su propio contexto de
          circuito, clima y tamaño de pelotón.
        </p>
      )}
    </div>
  );
}
