/**
 * DurationPicker
 *
 * Control de captura de duración en formato horas:minutos.
 * Internamente opera con dos estados locales (horas, minutos) y notifica
 * al padre con el total en minutos (int) via `onChange`.
 *
 * Integración con react-hook-form: usar con <Controller>.
 * El valor controlado (`value`) debe ser `duration_min` (número entero).
 */

import { useId } from "react";

import { Input } from "@/components/ui/input";

interface DurationPickerProps {
  /** Valor actual en minutos totales (15-240). Undefined antes del primer render. */
  value: number | undefined;
  /** Callback con el nuevo total en minutos. */
  onChange: (totalMinutes: number) => void;
  /** Mensaje de error de Zod/RHF para mostrar vinculado via aria. */
  error?: string;
}

const selectClass =
  "mt-1 w-full rounded-lg bg-white px-3 py-2 text-sm text-charcoal outline-none transition-shadow focus:ring-2 focus:ring-blue-500/40 cursor-pointer shadow-ring";

const MINUTE_STEPS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55];

const PRESETS: { label: string; minutes: number }[] = [
  { label: "30 min", minutes: 30 },
  { label: "45 min", minutes: 45 },
  { label: "1 h", minutes: 60 },
  { label: "1 h 30 min", minutes: 90 },
  { label: "2 h", minutes: 120 },
  { label: "2 h 30 min", minutes: 150 },
];

/** Descompone minutos totales en { hours, minutes } */
function decompose(totalMinutes: number): { hours: number; minutes: number } {
  const safe = Math.max(0, Math.min(totalMinutes, 240));
  return {
    hours: Math.floor(safe / 60),
    minutes: safe % 60,
  };
}

/** Redondea minutos al paso de 5 más cercano hacia abajo */
function snapToStep(min: number): number {
  return Math.floor(min / 5) * 5;
}

export function DurationPicker({ value, onChange, error }: DurationPickerProps) {
  const errorId = useId();
  const hoursId = useId();
  const minutesId = useId();

  // Derivar horas y minutos del valor controlado.
  // Si value es undefined (campo aún sin inicializar), usar 60 min como fallback visual.
  const total = typeof value === "number" && !isNaN(value) ? value : 60;
  const { hours, minutes } = decompose(total);
  // Los minutos mostrados se redondean al step de 5 si el valor viene del backend
  // con un residuo fuera de los steps. Caso: 63 min → 1 h, 5 min (no 3 min).
  const displayMinutes = MINUTE_STEPS.includes(minutes) ? minutes : snapToStep(minutes);

  function handleHoursChange(e: React.ChangeEvent<HTMLInputElement>) {
    const h = Math.max(0, Math.min(4, parseInt(e.target.value, 10) || 0));
    onChange(h * 60 + displayMinutes);
  }

  function handleMinutesChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const m = parseInt(e.target.value, 10);
    onChange(hours * 60 + m);
  }

  function handlePreset(preset: number) {
    onChange(preset);
  }

  const isError = !!error;
  // Texto de resumen para el helper text
  const totalDisplay = hours * 60 + displayMinutes;

  return (
    <div>
      <span id="duration-group-label" className="block text-sm font-medium leading-none text-charcoal">
        Duración
      </span>

      {/* Inputs horas + minutos */}
      <div
        className="mt-1 grid grid-cols-2 gap-2 max-w-[200px]"
        role="group"
        aria-labelledby="duration-group-label"
        aria-describedby={isError ? errorId : "duration-helper"}
        aria-invalid={isError}
      >
        <div>
          <label htmlFor={hoursId} className="sr-only">
            Horas
          </label>
          <div className="relative">
            <Input
              id={hoursId}
              type="number"
              min={0}
              max={4}
              value={hours}
              onChange={handleHoursChange}
              className="py-2"
              aria-label="Horas"
            />
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-mid-gray select-none">
              h
            </span>
          </div>
        </div>

        <div>
          <label htmlFor={minutesId} className="sr-only">
            Minutos
          </label>
          <div className="relative">
            <select
              id={minutesId}
              value={displayMinutes}
              onChange={handleMinutesChange}
              className={selectClass}
              aria-label="Minutos"
            >
              {MINUTE_STEPS.map((m) => (
                <option key={m} value={m}>
                  {String(m).padStart(2, "0")}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-mid-gray select-none">
              min
            </span>
          </div>
        </div>
      </div>

      {/* Chips de presets */}
      <div className="mt-2 flex flex-wrap gap-1.5 max-w-xs" role="group" aria-label="Duraciones frecuentes">
        {PRESETS.map((p) => {
          const isActive = totalDisplay === p.minutes;
          return (
            <button
              key={p.minutes}
              type="button"
              onClick={() => handlePreset(p.minutes)}
              aria-pressed={isActive}
              className={[
                "rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                isActive
                  ? "bg-charcoal text-white"
                  : "bg-white text-mid-gray hover:text-charcoal shadow-ring",
              ].join(" ")}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      {/* Helper text: total en minutos */}
      {!isError && (
        <p id="duration-helper" className="mt-1.5 text-xs text-mid-gray">
          Total: {totalDisplay} minutos
        </p>
      )}

      {/* Error vinculado */}
      {isError && (
        <p id={errorId} className="mt-1 text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
