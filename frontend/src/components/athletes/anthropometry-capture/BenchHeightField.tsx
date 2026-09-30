import { useId } from "react";

import { DecimalInput, formatDecimal } from "./DecimalInput";
import { Label } from "@/components/ui/label";
import { netSittingHeight } from "@/schemas/anthropometryCapture.schema";
import { setBenchHeightCm } from "@/lib/anthropometry/devicePrefs";

export interface BenchHeightFieldProps {
  /** Altura del banco en cm (0 permitido). */
  benchValue: number | null | undefined;
  onBenchChange: (value: number | undefined) => void;
  /** Lectura bruta del tallímetro, para la línea de talla neta. */
  grossValue: number | null | undefined;
  /** Guarda el valor válido en las preferencias del dispositivo (R8). En edición, false. */
  persist?: boolean;
  error?: string;
}

/**
 * Altura del banco + línea «Talla sentado neta: X cm» (feature 048, R8).
 * La talla neta = lectura del tallímetro − altura del banco.
 */
export function BenchHeightField({
  benchValue,
  onBenchChange,
  grossValue,
  persist = true,
  error,
}: BenchHeightFieldProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const showNet =
    typeof grossValue === "number" &&
    Number.isFinite(grossValue) &&
    grossValue > 0;
  const net = showNet ? netSittingHeight(grossValue, benchValue ?? 0) : null;

  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>Altura del banco (cm)</Label>
      <DecimalInput
        id={id}
        value={benchValue}
        placeholder="0"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        onValueChange={(v) => {
          if (persist && (v === undefined || (Number.isFinite(v) && v >= 0))) {
            setBenchHeightCm(v ?? null);
          }
          onBenchChange(v);
        }}
      />
      {error && (
        <p id={errorId} className="text-xs text-danger">
          {error}
        </p>
      )}
      {net !== null && (
        <p className="text-sm text-charcoal" data-testid="net-sitting-height">
          Talla sentado neta: <span className="font-semibold">{formatDecimal(net)} cm</span>
        </p>
      )}
    </div>
  );
}
