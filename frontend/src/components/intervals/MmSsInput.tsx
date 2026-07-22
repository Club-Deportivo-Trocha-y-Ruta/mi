/**
 * MmSsInput — entrada reutilizable de duración en minutos y segundos
 * (feature 034, US1/T007). Reemplaza la entrada cruda en segundos: dos
 * campos numéricos (Min ≥ 0, Seg 0–59) que juntos representan un único valor
 * en segundos — la unidad de almacenamiento no cambia (FR-001), solo la
 * semántica de entrada/visualización.
 *
 * Por qué dos campos y no un input enmascarado `mm:ss` (research.md R4):
 * el entrenador usa una tablet a la intemperie, a veces con guantes — dos
 * campos de 48px con teclado numérico nativo son más confiables que un
 * input enmascarado (trampas de cursor, problemas de IME).
 *
 * Contrato:
 *   - `value`/`onChange` trabajan siempre en segundos (`number | null`).
 *     `null` = sin valor (bloque libre, o campo vacío antes de completar).
 *   - El campo Segundos normaliza cualquier entrada > 59 a 59 de inmediato
 *     (FR-002: "constrain or normalize") — nunca permite ambigüedad.
 *   - Ambos campos vacíos ⇒ `onChange(null)`. Un campo vacío y el otro con
 *     valor ⇒ el vacío se trata como 0 (p. ej. "" min + "30" seg ⇒ 30 s).
 *
 * Nota de implementación: el valor mostrado en cada campo vive en estado
 * local (string), re-sincronizado desde `value` solo cuando ese valor
 * cambia por una causa EXTERNA (reordenar bloques, hidratar datos previos,
 * limpiar al cambiar a "libre"). Si sincronizáramos en cada render a partir
 * de `value`, un campo que el usuario deja vacío momentáneamente (que hoy
 * codifica el mismo total en segundos que antes, p. ej. borrar "0" segundos
 * de un bloque de X minutos exactos) se "revertiría" solo, porque el efecto
 * no se dispara si `value` no cambió entre renders.
 *
 * A11y: cada campo tiene su propio `<label>` (visualmente oculto, con pista
 * visible "min"/"seg" al lado) — el nombre accesible es "Minutos"/"Segundos",
 * igual en todas las filas (mismo patrón que "Zona de FC"/"Cadencia (rpm)" en
 * `BlockRow`, que tampoco son únicos por fila). Objetivos táctiles ≥48px.
 */
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Helpers puros (exportados para tests — T005)
// ---------------------------------------------------------------------------

/** Segundos → cadenas `{ min, sec }` para mostrar en los campos. `null` ⇒ ambos vacíos. */
export function splitSeconds(value: number | null | undefined): {
  min: string;
  sec: string;
} {
  if (value == null || Number.isNaN(value)) return { min: "", sec: "" };
  const safe = Math.max(0, Math.trunc(value));
  return { min: String(Math.floor(safe / 60)), sec: String(safe % 60) };
}

/** Parsea un campo individual: vacío o inválido ⇒ 0; nunca negativo. */
function parseFieldInt(raw: string): number {
  if (raw.trim() === "") return 0;
  const parsed = Math.trunc(Number(raw));
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

/**
 * Combina las cadenas de Min/Seg en un valor en segundos. Ambos vacíos ⇒
 * `null` (sin duración). El componente ya garantiza que `sec` nunca
 * representa un valor fuera de 0–59 (se normaliza en el propio handler), por
 * eso acá se vuelve a acotar como defensa adicional.
 */
export function combineMmSs(minRaw: string, secRaw: string): number | null {
  const minEmpty = minRaw.trim() === "";
  const secEmpty = secRaw.trim() === "";
  if (minEmpty && secEmpty) return null;
  const min = minEmpty ? 0 : parseFieldInt(minRaw);
  const sec = secEmpty ? 0 : Math.min(59, parseFieldInt(secRaw));
  return min * 60 + sec;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface MmSsInputProps {
  /** id base — genera `${id}-min` / `${id}-sec`. */
  id: string;
  /** Etiqueta visible del grupo completo (ej. "Duración"). */
  label: string;
  /** Valor en segundos — fuente de verdad. `null` = sin valor. */
  value: number | null;
  onChange: (seconds: number | null) => void;
  onBlur?: () => void;
  disabled?: boolean;
  /** Mensaje de error (RHF/Zod) — se asocia vía `aria-describedby` a ambos campos. */
  error?: string;
  /** ids adicionales para `aria-describedby` (ej. un hint del padre). */
  describedBy?: string;
}

const FIELD_CLASS = cn(
  "min-h-12 min-w-12 w-full rounded-lg border border-border-gray bg-white px-3 py-2",
  "text-sm text-charcoal placeholder:text-mid-gray transition-colors",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
);

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function MmSsInput({
  id,
  label,
  value,
  onChange,
  onBlur,
  disabled,
  error,
  describedBy,
}: MmSsInputProps) {
  const [minStr, setMinStr] = useState(() => splitSeconds(value).min);
  const [secStr, setSecStr] = useState(() => splitSeconds(value).sec);

  // Resincroniza desde `value` solo cuando cambia por una causa externa al
  // propio tipeo del usuario (ver nota de implementación arriba).
  useEffect(() => {
    if (combineMmSs(minStr, secStr) !== value) {
      const next = splitSeconds(value);
      setMinStr(next.min);
      setSecStr(next.sec);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const minId = `${id}-min`;
  const secId = `${id}-sec`;
  const errId = `${id}-err`;
  const describedByIds = cn(describedBy ?? "", error ? errId : "").trim() || undefined;

  const commit = (nextMin: string, nextSec: string) => {
    setMinStr(nextMin);
    setSecStr(nextSec);
    onChange(combineMmSs(nextMin, nextSec));
  };

  const handleMinChange = (raw: string) => {
    commit(raw, secStr);
  };

  const handleSecChange = (raw: string) => {
    if (raw.trim() === "") {
      commit(minStr, "");
      return;
    }
    const clamped = Math.min(59, parseFieldInt(raw));
    commit(minStr, String(clamped));
  };

  return (
    <div>
      <span
        id={`${id}-label`}
        className="mb-1 block text-xs font-medium text-charcoal"
      >
        {label}
      </span>
      <div className="flex items-center gap-2" aria-labelledby={`${id}-label`}>
        <div className="flex-1">
          <label htmlFor={minId} className="sr-only">
            Minutos
          </label>
          <input
            id={minId}
            type="number"
            inputMode="numeric"
            min={0}
            step={1}
            placeholder="0"
            value={minStr}
            disabled={disabled}
            onChange={(e) => handleMinChange(e.target.value)}
            onBlur={onBlur}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedByIds}
            className={FIELD_CLASS}
          />
          <span className="mt-0.5 block text-[10px] text-mid-gray" aria-hidden="true">
            min
          </span>
        </div>
        <span className="pb-3 text-mid-gray" aria-hidden="true">
          :
        </span>
        <div className="flex-1">
          <label htmlFor={secId} className="sr-only">
            Segundos
          </label>
          <input
            id={secId}
            type="number"
            inputMode="numeric"
            min={0}
            max={59}
            step={1}
            placeholder="00"
            value={secStr}
            disabled={disabled}
            onChange={(e) => handleSecChange(e.target.value)}
            onBlur={onBlur}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedByIds}
            className={FIELD_CLASS}
          />
          <span className="mt-0.5 block text-[10px] text-mid-gray" aria-hidden="true">
            seg
          </span>
        </div>
      </div>
      {error && (
        <p id={errId} role="alert" className="mt-1 text-xs text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}

export default MmSsInput;
