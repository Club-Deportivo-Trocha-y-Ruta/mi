import { useEffect, useState } from "react";

import { Input } from "@/components/ui/input";

/** Interpreta «72,5» o «72.5». Vacío → undefined; texto inválido → NaN. */
export function parseDecimal(raw: string): number | undefined {
  const text = raw.trim().replace(",", ".");
  if (text === "") return undefined;
  return /^-?\d+(\.\d*)?$|^-?\.\d+$/.test(text) ? Number(text) : Number.NaN;
}

/** «72,0» (coma decimal, un decimal). */
export function formatDecimal(value: number): string {
  return value.toFixed(1).replace(".", ",");
}

export interface DecimalInputProps
  extends Omit<
    React.InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "type" | "inputMode"
  > {
  value: number | null | undefined;
  /** `undefined` = campo vacío; `NaN` = texto no numérico. */
  onValueChange: (value: number | undefined) => void;
}

/**
 * Input numérico controlado con teclado decimal (`inputMode="decimal"`) que
 * acepta coma o punto. Conserva el texto mientras se escribe («7,» no se
 * reescribe) y se resincroniza si el valor externo cambia (reset).
 */
export function DecimalInput({ value, onValueChange, ...rest }: DecimalInputProps) {
  const [text, setText] = useState(() =>
    value === null || value === undefined || Number.isNaN(value) ? "" : String(value).replace(".", ","),
  );

  useEffect(() => {
    const current = parseDecimal(text);
    const external = value === null ? undefined : value;
    const same =
      current === external || (Number.isNaN(current) && Number.isNaN(external));
    if (!same) {
      setText(
        external === undefined || Number.isNaN(external) ? "" : String(external).replace(".", ","),
      );
    }
    // Solo reacciona al valor externo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <Input
      {...rest}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        onValueChange(parseDecimal(event.target.value));
      }}
    />
  );
}
