import type { Ref } from "react";

import { BenchHeightField } from "./BenchHeightField";
import { DecimalInput } from "./DecimalInput";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { MEASURE_GUIDES, type MeasureKey } from "@/lib/anthropometry/measureGuides";

const UNITS: Record<MeasureKey, string> = {
  weight: "kg",
  standing_height: "cm",
  sitting_height: "cm",
  arm_span: "cm",
};

export interface MeasureStepProps {
  measureKey: MeasureKey;
  /** En talla sentado: lectura BRUTA del tallímetro. */
  value: number | null | undefined;
  onChange: (value: number | undefined) => void;
  error?: string;
  /** URL de la ilustración; sin ella no se renderiza nada en su lugar. */
  illustrationSrc?: string;
  onPrev?: () => void;
  onNext: () => void;
  /** Solo envergadura: «Omitir (opcional)». */
  onSkip?: () => void;
  /** Solo talla sentado. */
  benchValue?: number | null;
  onBenchChange?: (value: number | undefined) => void;
  benchError?: string;
  persistBench?: boolean;
  /** Para que el asistente enfoque el encabezado al cambiar de paso. */
  headingRef?: Ref<HTMLHeadingElement>;
}

/**
 * Un paso de medición del asistente guiado: ilustración + «Dónde»/«Cómo» +
 * un campo numérico. Ilustración arriba (máx. 280 px) en teléfono y a la
 * izquierda desde 768 px.
 */
export function MeasureStep({
  measureKey,
  value,
  onChange,
  error,
  illustrationSrc,
  onPrev,
  onNext,
  onSkip,
  benchValue,
  onBenchChange,
  benchError,
  persistBench,
  headingRef,
}: MeasureStepProps) {
  const guide = MEASURE_GUIDES[measureKey];
  const unit = UNITS[measureKey];
  const isSitting = measureKey === "sitting_height";
  const inputLabel = isSitting
    ? "Lectura en el tallímetro (cm)"
    : `${guide.label} (${unit})`;
  const inputId = `measure-${measureKey}`;
  const errorId = `${inputId}-error`;

  return (
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        onNext();
      }}
    >
      <h2
        ref={headingRef}
        tabIndex={-1}
        className="text-lg font-semibold text-charcoal focus:outline-none"
      >
        {guide.label}
      </h2>

      <div className={illustrationSrc ? "grid gap-6 md:grid-cols-2 md:items-start" : "grid gap-6"}>
        {illustrationSrc && (
          <img
            src={illustrationSrc}
            alt={guide.alt}
            className="mx-auto w-full max-w-[280px] rounded-card"
          />
        )}

        <div className="flex flex-col gap-4">
          <div className="text-sm text-charcoal">
            <h3 className="font-semibold">Dónde</h3>
            <p className="text-mid-gray">{guide.donde}</p>
          </div>
          <div className="text-sm text-charcoal">
            <h3 className="font-semibold">Cómo</h3>
            <p className="text-mid-gray">{guide.como}</p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor={inputId}>{inputLabel}</Label>
            <DecimalInput
              id={inputId}
              value={value}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
              onValueChange={onChange}
            />
            {error && (
              <p id={errorId} className="text-xs text-danger">
                {error}
              </p>
            )}
          </div>

          {isSitting && onBenchChange && (
            <BenchHeightField
              benchValue={benchValue}
              onBenchChange={onBenchChange}
              grossValue={value}
              persist={persistBench}
              error={benchError}
            />
          )}
        </div>
      </div>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        <div className="flex flex-col-reverse gap-3 sm:flex-row">
          {onPrev && (
            <Button type="button" variant="secondary" size="lg" onClick={onPrev}>
              Anterior
            </Button>
          )}
          {onSkip && (
            <Button type="button" variant="outline" size="lg" onClick={onSkip}>
              Omitir (opcional)
            </Button>
          )}
        </div>
        <Button type="submit" size="lg">
          Siguiente
        </Button>
      </div>
    </form>
  );
}
