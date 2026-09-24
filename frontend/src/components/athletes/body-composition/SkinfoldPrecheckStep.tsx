import { useId, useState } from "react";

import { FieldGuideDownloadButton } from "@/components/athletes/body-composition/FieldGuideDownloadButton";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

/**
 * SkinfoldPrecheckStep — primer paso del asistente de captura de pliegues
 * cutáneos (feature 046, T025).
 *
 * Muestra recordatorios del protocolo como checklist **no bloqueante**: son
 * ayuda-memoria para el entrenador, no una condición para avanzar — por eso
 * "Siguiente" está siempre habilitado (spec FR-002/FR-003, mismo criterio
 * que el resto del wizard: nunca bloquear por una casilla de recordatorio).
 *
 * El botón "Hoy prefiere no medirse" es la salida directa: llama a
 * `onDeclineAll` para que `SkinfoldWizard` (T028) arme el payload con los
 * seis sitios en `{declined: true}` y lo envíe sin pasar por los pasos de
 * sitio — nunca pide un motivo (spec FR-002: el atleta puede declinar
 * cualquier sitio sin consecuencia, y sin explicación).
 */
export interface SkinfoldPrecheckStepProps {
  /** Avanza al primer paso de sitio. Nunca deshabilitado. */
  onNext: () => void;
  /** El atleta decide no medirse hoy: arma y envía el set totalmente declinado. */
  onDeclineAll: () => void;
  /** `SkinfoldWizard` puede reflejar el estado de envío del decline-all aquí. */
  isDeclining?: boolean;
}

const PRECHECK_REMINDERS = [
  "El atleta no acaba de entrenar (evita retención de líquido en la piel).",
  "Piel seca, sin loción ni protector solar en las zonas de medición.",
  "Espacio privado, fuera de la vista de otros deportistas.",
  "Hay un segundo adulto presente durante toda la medición.",
  "El atleta está de pie, relajado, sin tensar los músculos.",
] as const;

export function SkinfoldPrecheckStep({
  onNext,
  onDeclineAll,
  isDeclining = false,
}: SkinfoldPrecheckStepProps) {
  const headingId = useId();
  // Estado puramente informativo: no condiciona nada, se reinicia si el
  // entrenador vuelve a este paso — no forma parte del formulario RHF.
  const [checked, setChecked] = useState<Record<number, boolean>>({});

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <div className="flex items-start justify-between gap-3">
          <h2 id={headingId} className="text-lg font-semibold text-charcoal">
            Antes de empezar
          </h2>
          <FieldGuideDownloadButton />
        </div>
        <p className="text-sm text-mid-gray">
          Revisa esta lista antes de tomar las medidas. Son recordatorios,
          no requisitos: puedes continuar aunque no marques ninguna casilla.
        </p>
      </div>

      <ul className="flex flex-col gap-3">
        {PRECHECK_REMINDERS.map((reminder, index) => {
          const itemId = `${headingId}-reminder-${index}`;
          return (
            <li key={itemId}>
              <label
                htmlFor={itemId}
                className="flex min-h-[48px] cursor-pointer items-center gap-3 rounded-control px-2 py-2 hover:bg-light-gray"
              >
                <Checkbox
                  id={itemId}
                  checked={!!checked[index]}
                  onCheckedChange={(value) =>
                    setChecked((prev) => ({ ...prev, [index]: value === true }))
                  }
                />
                <span className="text-sm text-charcoal">{reminder}</span>
              </label>
            </li>
          );
        })}
      </ul>

      <p className="text-sm text-mid-gray">
        El atleta puede decidir no medirse, o saltar cualquier sitio durante
        la toma, sin ninguna consecuencia.
      </p>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        <Button
          type="button"
          variant="secondary"
          size="lg"
          onClick={onDeclineAll}
          disabled={isDeclining}
        >
          Hoy prefiere no medirse
        </Button>
        <Button type="button" size="lg" onClick={onNext}>
          Siguiente
        </Button>
      </div>
    </div>
  );
}
