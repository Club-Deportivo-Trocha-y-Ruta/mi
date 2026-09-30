import { useId, useState, type Ref } from "react";

import { FieldGuideDownloadButton } from "@/components/athletes/body-composition/FieldGuideDownloadButton";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PRECHECK_CONDITIONS } from "@/lib/anthropometry/measureGuides";
import { todayISO } from "@/schemas/anthropometryCapture.schema";

export interface CapturePrecheckStepProps {
  date: string;
  onDateChange: (date: string) => void;
  /** Jornada grupal: la fecha es la de la sesión. */
  dateLocked?: boolean;
  onStart: () => void;
  /** URL de la ilustración; sin ella no se renderiza nada. */
  illustrationSrc?: string;
  /** Sin conexión: deshabilita «Empezar» y muestra el aviso. */
  isOffline?: boolean;
  headingRef?: Ref<HTMLHeadingElement>;
}

/**
 * Paso «Preparación» del asistente guiado (feature 048): lista NO bloqueante
 * de condiciones, fecha de la medición, «Empezar» e instructivo PDF.
 */
export function CapturePrecheckStep({
  date,
  onDateChange,
  dateLocked = false,
  onStart,
  illustrationSrc,
  isOffline = false,
  headingRef,
}: CapturePrecheckStepProps) {
  const id = useId();
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const dateInvalid = date === "" || date > todayISO();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3">
        <h2
          ref={headingRef}
          tabIndex={-1}
          className="text-lg font-semibold text-charcoal focus:outline-none"
        >
          Preparación
        </h2>
        <FieldGuideDownloadButton />
      </div>

      {illustrationSrc && (
        <img
          src={illustrationSrc}
          alt="Ilustración de la preparación para la medición: sin zapatos, ropa liviana y superficie plana."
          className="mx-auto w-full max-w-[280px] rounded-card"
        />
      )}

      <p className="text-sm text-mid-gray">
        Revisa estas condiciones antes de medir. Son recordatorios, no
        requisitos: puedes continuar aunque no marques ninguna casilla.
      </p>

      <ul className="flex flex-col gap-1">
        {PRECHECK_CONDITIONS.map((condition, index) => {
          const itemId = `${id}-c-${index}`;
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
                <span className="text-sm text-charcoal">{condition}</span>
              </label>
            </li>
          );
        })}
      </ul>

      <div className="flex flex-col gap-1.5 sm:max-w-xs">
        <Label htmlFor={`${id}-date`}>Fecha de la medición</Label>
        <Input
          id={`${id}-date`}
          type="date"
          value={date}
          max={todayISO()}
          disabled={dateLocked}
          aria-invalid={dateInvalid ? true : undefined}
          onChange={(event) => onDateChange(event.target.value)}
        />
        {date > todayISO() && (
          <p className="text-xs text-danger">No puede ser futura</p>
        )}
      </div>

      {isOffline && (
        <p role="alert" className="text-sm text-danger">
          Necesitas conexión a internet para registrar mediciones.
        </p>
      )}

      <Button
        type="button"
        size="lg"
        className="sm:self-start"
        disabled={isOffline || dateInvalid}
        onClick={onStart}
      >
        Empezar
      </Button>
    </div>
  );
}
