/**
 * FamilySkinfoldNotice — addendum informativo colapsable para familias
 * (feature 046, US4, T052): explica en qué consiste la medición de pliegues
 * cutáneos. Texto verbatim (con diacríticos completos) del addendum
 * aprobado en `docs/21-body-composition/research-safeguards-referral.md`
 * §5 ("Sample Spanish copy — consent addendum").
 *
 * Se muestra para cualquier deportista de 9 años o más, sin importar si ya
 * hay mediciones registradas (`has_data`) — es información general sobre el
 * protocolo, no un resumen de datos. Por debajo de 9 años el club no toma
 * esta medición (`skinfolds-api.md` §"athlete_too_young"), así que el
 * componente no renderiza nada.
 */
import { ChevronDown } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

export interface FamilySkinfoldNoticeProps {
  /** Edad decimal del deportista, o `null` cuando es desconocida. */
  athleteAgeDecimal: number | null;
}

const ADDENDUM_TEXT =
  "Además de talla y peso, el club también podría tomar pliegues cutáneos (una " +
  "medición no invasiva con un instrumento tipo pinza, en sitios como el brazo, " +
  "la espalda y la pantorrilla) para acompañar el proceso de crecimiento de tu " +
  "hijo/a. La realiza el entrenador en un espacio privado, respetando siempre el " +
  "derecho de tu hijo/a a decir que no en cualquier momento, sin ninguna " +
  "consecuencia. Los resultados se usan solo para el seguimiento individual — " +
  "nunca para comparar deportistas entre sí, ni como una meta a alcanzar. Si en " +
  "algún momento identificamos una señal que amerite la opinión de un " +
  "profesional de la salud, te la compartiremos directamente para decidir " +
  "juntos los siguientes pasos.";

const MIN_AGE_DECIMAL = 9;

export function FamilySkinfoldNotice({ athleteAgeDecimal }: FamilySkinfoldNoticeProps) {
  if (athleteAgeDecimal === null || athleteAgeDecimal < MIN_AGE_DECIMAL) {
    return null;
  }

  return (
    <Collapsible data-testid="family-skinfold-notice" className="rounded-lg border border-light-gray p-3">
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 text-left text-sm font-medium text-charcoal">
        <span>¿Qué es la medición de pliegues?</span>
        <ChevronDown size={16} aria-hidden="true" className="shrink-0 text-mid-gray" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <p className="pt-2 text-sm text-mid-gray">{ADDENDUM_TEXT}</p>
      </CollapsibleContent>
    </Collapsible>
  );
}
